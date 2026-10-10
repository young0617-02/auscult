"""Redis 令牌桶限流（P5-W4/D13 · Q5=A 自研）

职责：高成本端点（云端升级入口 POST /api/diagnose）按客户端 IP 限流；
      触发限流 → 429 E_RATE_LIMITED（统一包络）+ 审计 + Prometheus 打点
      （429 经 trace_and_envelope 统一计入 auscult_http_requests_total）。

实现：Redis Lua 原子令牌桶（tokens + ts 双字段，按流逝时间惰性补充）。
降级：Redis 不可达 → fail-open 放行（不拖垮服务），审计记录
      rate_limit_redis_unreachable（与 budget.py「Redis 不可达不阻塞」一致）。

参数：容量 10、回填 10/分（约每 6s 补 1 token）——单 IP 首波突发 ≤10 次，
      持续压力约 10 次/分钟。可用环境变量 AUSCULT_RATE_LIMIT="capacity:refill_per_sec"
      覆盖（例如 "5:0.2"）。

对应交付物：plan/Phase 5 §5.4 W4（限流：高频调用云端接口 → 触发限流并记录）
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Any

logger = logging.getLogger("auscult.ratelimit")

REDIS_URL = os.environ.get(
    "AUSCULT_REDIS_URL",
    "redis://:auscult-dev-redis@127.0.0.1:6379/0",
)
KEY_PREFIX = "ratelimit:"

# 默认参数：容量 10 / 回填 10 每分钟（0.1667/s）
_DEFAULT_CAPACITY = 10
_DEFAULT_REFILL = 10.0 / 60.0


def _parse_env() -> tuple[int, float]:
    raw = os.environ.get("AUSCULT_RATE_LIMIT", "").strip()
    if not raw or ":" not in raw:
        return _DEFAULT_CAPACITY, _DEFAULT_REFILL
    try:
        cap, refill = raw.split(":", 1)
        return max(1, int(cap)), max(0.001, float(refill))
    except ValueError:
        return _DEFAULT_CAPACITY, _DEFAULT_REFILL


# 限流规则：(method, path 前缀, bucket_id)
# 只限高成本/云端升级入口；GET 查询与 /metrics 不限。
DEFAULT_RULES: tuple[tuple[str, str, str], ...] = (
    ("POST", "/api/diagnose", "diagnose"),
)

# Lua：原子令牌桶（HMGET tokens/ts → 补充 → 扣减 → 回写 + 过期兜底）
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now_ns = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil or ts == nil then
  tokens = capacity
  ts = now_ns
end

local elapsed = (now_ns - ts) / 1e9
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now_ns)
redis.call('EXPIRE', key, math.ceil(capacity / refill) * 2 + 60)
return {allowed, string.format('%.3f', tokens)}
"""

_client = None
_script: Any = None


def _get_client():
    """惰性 Redis 连接 + 预注册 Lua 脚本（进程内单例）。"""
    global _client, _script
    if _client is None:
        import redis   # noqa: PLC0415
        _client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        _script = _client.register_script(_TOKEN_BUCKET_LUA)
    return _script


def consume(
    bucket: str,
    client_key: str,
    *,
    capacity: int,
    refill_per_sec: float,
    cost: int = 1,
) -> tuple[bool, float]:
    """从指定桶取 cost 个令牌（原子）。

    返回:
        (allowed, remaining_tokens)；Redis 不可达 → (True, -1)（fail-open）。
    """
    try:
        allowed, remaining = _get_client()(
            keys=[f"{KEY_PREFIX}{bucket}:{client_key}"],
            args=[capacity, refill_per_sec, time.perf_counter_ns(), cost],
        )
        return int(allowed) == 1, float(remaining)
    except Exception as exc:   # noqa: BLE001 - fail-open
        logger.warning("限流 Redis 不可达，fail-open 放行: %s", exc)
        try:
            from .pg_audit import append_audit   # noqa: PLC0415
            append_audit("rate_limit_redis_unreachable", severity="warning",
                         detail={"error": type(exc).__name__})
        except Exception:   # noqa: BLE001
            pass
        return True, -1.0


async def check_rate_limit(request) -> Any | None:
    """中间件入口：按规则限流，命中返回 429 JSONResponse，放行返回 None。

    在 trace_and_envelope 内、call_next 之前 await 调用——429 仍走统一
    打点与 X-Trace-Id 响应头。（内部 Redis 为同步客户端，socket_timeout=2s）
    """
    # 动态读参（便于测试注入小桶）
    capacity, refill = _parse_env()
    rules = DEFAULT_RULES

    for method, path_prefix, bucket in rules:
        if request.method != method or not request.url.path.startswith(path_prefix):
            continue
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        allowed, remaining = consume(bucket, client_ip,
                                     capacity=capacity, refill_per_sec=refill)
        if allowed:
            return None

        # 触发限流：审计 + 429
        try:
            from .pg_audit import append_audit   # noqa: PLC0415
            append_audit("rate_limit_exceeded", severity="warning",
                         detail={"bucket": bucket, "client_ip": client_ip,
                                 "path": request.url.path,
                                 "capacity": capacity,
                                 "refill_per_sec": refill})
        except Exception:   # noqa: BLE001
            pass

        from fastapi.responses import JSONResponse   # noqa: PLC0415
        from ..api.errors import ApiError, fail   # noqa: PLC0415
        retry_after = max(1, math.ceil(1.0 / refill))
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content=fail(ApiError(
                "E_RATE_LIMITED",
                f"请求过于频繁，请 {retry_after} 秒后重试",
                data={"bucket": bucket, "retry_after": retry_after},
            )),
        )
    return None
