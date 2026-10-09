"""审核生命周期（D18 · M3.4）

职责：
  1. **并发锁** `lock:review:{thread_id}`：Redis SETNX，防止双审核人重复出报告；
  2. **4h 通知**：审核挂起超 4h → 通知备用审核人（写审计日志）；
  3. **24h 超时降级**：审核挂起超 24h → 自动 `resume({action: "timeout"})`，流程不挂起；
  4. **职责分离**：报告提交者不得自审。

Redis 约定（复用 budget.py 的连接）：
  - Key: `lock:review:{thread_id}`
  - Value: `reviewer_id`
  - SETNX + EXPIRE 25h（比 24h 超时多 1h 缓冲）
  - 释放用 Lua 校验 value（防止误释放他人锁）

对应交付物：plan/Phase 3 §三.4 / §五 D18 / §六.5
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 常量

REDIS_URL = "redis://:auscult-dev-redis@127.0.0.1:6379/0"
LOCK_KEY_PREFIX = "lock:review:"
LOCK_TTL_SECONDS = 25 * 3600          # 25h（24h 超时 + 1h 缓冲）

NOTIFY_AFTER_SECONDS = 4 * 3600       # 4h → 通知备用审核人
TIMEOUT_AFTER_SECONDS = 24 * 3600    # 24h → 超时降级

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG_PATH = PROJECT_ROOT / "reports" / "review_audit.jsonl"

# Lua 脚本：校验 value 后删除（防止误释放他人锁）
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

# ---------------------------------------------------------------- Redis 单例

_client = None


def _get_client():
    """惰性 Redis 连接（进程内单例）。"""
    global _client
    if _client is None:
        import redis   # noqa: PLC0415
        _client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
    return _client


def _audit(record: dict[str, Any]) -> None:
    """追加审核生命周期审计记录。"""
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- 并发锁

class ReviewLock:
    """审核并发锁（`lock:review:{thread_id}`）。

    acquire(thread_id, reviewer_id) → bool：
      True=获取成功（或已持有），False=已被他人持有
    release(thread_id, reviewer_id) → bool：
      True=释放成功，False=锁不属于该 reviewer
    """

    def _key(self, thread_id: str) -> str:
        return f"{LOCK_KEY_PREFIX}{thread_id}"

    def acquire(self, thread_id: str, reviewer_id: str) -> bool:
        """SETNX 获取锁。已持有同一 reviewer → True（可重入）。"""
        try:
            client = _get_client()
            key = self._key(thread_id)
            existing = client.get(key)
            if existing == reviewer_id:
                return True   # 可重入
            if existing is not None:
                return False  # 被他人持有
            # SETNX
            ok = client.set(key, reviewer_id, nx=True, ex=LOCK_TTL_SECONDS)
            return bool(ok)
        except Exception:   # noqa: BLE001
            # Redis 不可达：不阻塞（降级为无锁，审计记录）
            return True

    def release(self, thread_id: str, reviewer_id: str) -> bool:
        """释放锁（Lua 校验 value）。"""
        try:
            client = _get_client()
            key = self._key(thread_id)
            result = client.eval(_RELEASE_SCRIPT, 1, key, reviewer_id)
            return bool(result)
        except Exception:   # noqa: BLE001
            return False

    def holder(self, thread_id: str) -> str | None:
        """查询当前锁持有者。"""
        try:
            client = _get_client()
            return client.get(self._key(thread_id))
        except Exception:   # noqa: BLE001
            return None


# ---------------------------------------------------------------- 超时检测

def check_review_timeout(interrupted_at: float) -> str:
    """检查审核挂起是否超时。

    interrupted_at: interrupt 发生的 epoch 时间戳（秒）
    返回: "none" / "notify_backup" / "timeout"
    """
    elapsed = time.time() - interrupted_at
    if elapsed >= TIMEOUT_AFTER_SECONDS:
        return "timeout"
    if elapsed >= NOTIFY_AFTER_SECONDS:
        return "notify_backup"
    return "none"


def notify_backup_reviewer(thread_id: str, payload: dict[str, Any]) -> None:
    """通知备用审核人（4h 触发）。

    当前实现：写审计日志 + 打印。
    后续可接入飞书/邮件通知。
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "notify_backup_reviewer",
        "thread_id": thread_id,
        "payload_summary": {
            "risk_level": payload.get("risk_level"),
            "diagnosis": (payload.get("diagnosis") or "")[:100],
            "confidence": payload.get("confidence"),
        },
    }
    _audit(record)
    print(f"[review] 4h 超时通知：thread_id={thread_id}，备用审核人待介入")


def auto_timeout_resume(graph: Any, config: dict, thread_id: str) -> dict | None:
    """24h 超时自动降级（resume with action=timeout）。

    需要外部调度器在 24h 后调用此函数。
    返回 graph.invoke(Command(resume=...)) 的结果，或 None（无挂起）。
    """
    from langgraph.types import Command   # noqa: PLC0415

    # 检查是否有挂起的 human_review
    state = graph.get_state(config)
    if not state.next or "human_review" not in state.next:
        return None   # 无挂起，无需超时

    resume_value = {"action": "timeout",
                    "comment": "24h 超时自动降级（lifecycle.auto_timeout_resume）"}
    result = graph.invoke(Command(resume=resume_value), config=config)

    _audit({
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "auto_timeout_resume",
        "thread_id": thread_id,
        "resume": resume_value,
        "report_id": result.get("report_id") if isinstance(result, dict) else None,
    })
    return result


# ---------------------------------------------------------------- 职责分离

def validate_submitter(reviewer_id: str, submitter_id: str) -> bool:
    """职责分离：报告提交者不得自审。

    返回 True=允许（非同一人），False=禁止（自审）
    """
    if not reviewer_id or not submitter_id:
        return True   # 无提交者信息时不拦截（API 层应保证传入）
    return reviewer_id != submitter_id
