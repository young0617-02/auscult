"""预算熔断（D15 · M3.3）

职责：管理 `budget:cloud:{date}` 按天计数，超 `per_day_calls` 熔断 → 强制本地降级。

存储：Redis（INCR 原子计数 + EXPIRE 按天归零 + 7 天审计窗口）
降级：Redis 不可达 → **不阻塞**（允许调用 + 审计记录 redis_unreachable）

对应交付物：plan/Phase 3 §三.3 / §五 D15 / §六.4 预算
"""

from __future__ import annotations

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
    """从 env/cloud.json 读取 per_day_calls（惰性缓存）。"""
    global _limit_cache
    if _limit_cache is None:
        from .cloud import load_cloud_config   # noqa: PLC0415
        cfg = load_cloud_config()
        _limit_cache = int(cfg.get("budget_lock", {}).get("per_day_calls", 20))
    return _limit_cache


def _today_key() -> str:
    return f"{BUDGET_KEY_PREFIX}{date.today().isoformat()}"


# ---------------------------------------------------------------- BudgetGuard

class BudgetGuard:
    """预算熔断守卫（D15）。

    check() → (ok, count, limit, reason)
      - ok=True: 未超限，可调用
      - ok=False: 已超限，熔断
      - Redis 不可达: ok=True（不阻塞），reason="redis_unreachable"
    increment() → count（调用成功后 +1）
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

    def increment(self) -> int:
        """调用成功后计数 +1。返回当前计数（-1 = Redis 不可达）。"""
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
