"""预算熔断（D15 · M3.3）

职责：管理 `budget:cloud:{date}` 按天计数，超 `per_day_calls` 熔断 → 强制本地降级。

存储：Redis（INCR 原子计数 + EXPIRE 按天归零 + 7 天审计窗口）
降级：Redis 不可达 → **不阻塞**（允许调用 + 审计记录 redis_unreachable）

对应交付物：plan/Phase 3 §三.3 / §五 D15 / §六.4 预算
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

# ---------------------------------------------------------------- 常量

REDIS_URL = "redis://:auscult-dev-redis@127.0.0.1:6379/0"
BUDGET_KEY_PREFIX = "budget:cloud:"
EXPIRY_SECONDS = 7 * 24 * 3600   # 7 天（审计窗口 + 次日归零兜底）

# ---------------------------------------------------------------- 单例

_client = None
_limit_cache: int | None = None


def _get_client():
    """惰性 Redis 连接（进程内单例）。"""
    global _client
    if _client is None:
        import redis   # noqa: PLC0415
        _client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
    return _client


def _get_limit() -> int:
    """日预算上限：env AUSCULT_CLOUD_BUDGET_LIMIT 优先，其次 env/cloud.json。

    P7 起 Agent 模式一次诊断含多轮调用（≤max_steps+1），上限需按
    「日均诊断容量 × 单次调用数」重定，故开放 env 覆盖（见设计文档 §六）。
    """
    global _limit_cache
    if _limit_cache is None:
        env_limit = os.environ.get("AUSCULT_CLOUD_BUDGET_LIMIT")
        if env_limit:
            _limit_cache = int(env_limit)
        else:
            from .cloud import load_cloud_config   # noqa: PLC0415
            cfg = load_cloud_config()
            _limit_cache = int(cfg.get("budget_lock", {}).get("per_day_calls", 20))
    return _limit_cache


def _today_key() -> str:
    return f"{BUDGET_KEY_PREFIX}{date.today().isoformat()}"


# ---------------------------------------------------------------- BudgetGuard

class BudgetGuard:
    """预算熔断守卫（D15）。

    reserve() → (ok, count, limit, reason)   ← **推荐路径（ISS-054 先增后调）**
      - 调用**之前**先占 1 次额度：超时/异常/进程崩溃路径也计费
        （客户端断连 ≠ 服务端停止计费，实测 20s 断连的调用照样计入账单）；
      - 超限时不占额度（即时回滚）→ ok=False 熔断；
      - Redis 不可达: ok=True（不阻塞），reason="redis_unreachable"。
    check() → (ok, count, limit, reason)     ← 只读预览（health/审计用，不计费）
    increment() → count（"调用成功后 +1"，旧口径，保留兼容）
    """

    def check(self) -> tuple[bool, int, int, str]:
        """检查预算是否充足。"""
        limit = _get_limit()
        try:
            client = _get_client()
            current = int(client.get(_today_key()) or 0)
            if current >= limit:
                return False, current, limit, f"budget_exceeded({current}/{limit})"
            return True, current, limit, "ok"
        except Exception as exc:   # noqa: BLE001
            # Redis 不可达：不阻塞主流程，审计记录
            return True, -1, limit, f"redis_unreachable:{type(exc).__name__}"

    def reserve(self) -> tuple[bool, int, int, str]:
        """**调用前**占位计数（先增后调，ISS-054）。

        与 check()+increment() 的差别：把「计数」挪到真正发起调用之前——
        旧口径只在成功路径 `increment()`，导致超时/异常/进程崩溃的调用
        **零记账**（实测漏计 10–31%，Agent 形态单次诊断多轮调用漏得更多）。

        语义：
          - 正常：`INCR` 后返回 (True, 含本次的计数, limit, "ok")；
          - 超限：`INCR` 后立刻 `DECR` 回滚（熔断不占额度），返回 (False, 回滚后计数, limit, reason)；
          - Redis 不可达：不阻塞，返回 (True, -1, limit, "redis_unreachable:...")。
        """
        limit = _get_limit()
        try:
            client = _get_client()
            key = _today_key()
            count = int(client.incr(key))
            if count == 1:
                client.expire(key, EXPIRY_SECONDS)
            if count > limit:
                client.decr(key)                      # 熔断不占额度
                return False, count - 1, limit, f"budget_exceeded({count - 1}/{limit})"
            return True, count, limit, "ok"
        except Exception as exc:   # noqa: BLE001
            # Redis 不可达：不阻塞主流程，审计记录（与 check 同口径）
            return True, -1, limit, f"redis_unreachable:{type(exc).__name__}"

    def increment(self) -> int:
        """调用成功后计数 +1（**旧口径，仅保留兼容**；新代码用 reserve()）。"""
        try:
            client = _get_client()
            key = _today_key()
            count = client.incr(key)
            if count == 1:
                client.expire(key, EXPIRY_SECONDS)
            return int(count)
        except Exception:   # noqa: BLE001
            return -1


# ---------------------------------------------------------------- 兼容 cloud.py 的函数接口

def check_budget() -> bool:
    """cloud.py 旧接口兼容：返回 True=允许，False=熔断。"""
    ok, _, _, _ = BudgetGuard().check()
    return ok


def budget_status() -> dict[str, Any]:
    """供审计/监控用的预算状态快照。"""
    ok, count, limit, reason = BudgetGuard().check()
    return {"ok": ok, "count": count, "limit": limit, "reason": reason}
