"""审计事件 PG 持久化（P5-W4/D12 · Q2=A）

audit_logs 表为 append-only（防篡改触发器见 db/migrations/0006_audit_logs.sql）。
与既有 JSONL 审计（sanitizer.log_security_event / lifecycle._audit）双轨：
- JSONL：进程本地可读，延续既有消费方
- PG：集中可查询 + 触发器防篡改（权威审计层）

失败策略：PG 写入失败不阻断业务（返回 False + logger.warning），
与 budget.py「Redis 不可达不阻塞」的降级哲学一致。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("auscult.audit")

PG_URL = os.environ.get(
    "LANGGRAPH_PG_URL",
    "postgresql://root:123456@127.0.0.1:5433/auscult_v2",
)


def append_audit(
    event: str,
    *,
    severity: str = "info",
    thread_id: str | None = None,
    actor: str | None = None,
    detail: dict[str, Any] | None = None,
    trace_id: str | None = None,
    timeout: float = 2.0,
) -> bool:
    """追加一条审计记录到 PG audit_logs（append-only）。

    参数:
        event:     事件名（prompt_injection_attempt / tool_call /
                   rate_limit_exceeded / review_submit / ...）
        severity:  info / warning / critical
        thread_id: 关联诊断会话（可空）
        actor:     操作者（用户名或 system，可空）
        detail:    结构化明细（JSONB）
        trace_id:  请求追踪 ID（缺省取当前请求 contextvar）
        timeout:   连接超时（秒）

    返回:
        True=写入成功；False=PG 不可达/写入失败（已记日志，不抛错）。
    """
    if trace_id is None:
        from ..api.errors import get_trace_id   # noqa: PLC0415
        trace_id = get_trace_id()

    sql = (
        "INSERT INTO audit_logs (trace_id, event, severity, thread_id, actor, detail) "
        "VALUES (%s, %s, %s, %s, %s, %s::jsonb)"
    )
    try:
        import psycopg   # noqa: PLC0415

        with psycopg.connect(PG_URL, connect_timeout=max(1, int(timeout))) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    (trace_id[:32] if trace_id else None),
                    event[:64],
                    (severity or "info")[:16],
                    (thread_id[:64] if thread_id else None),
                    (actor[:64] if actor else None),
                    json.dumps(detail or {}, ensure_ascii=False),
                ))
        return True
    except Exception as exc:   # noqa: BLE001 - 审计失败不阻断业务
        logger.warning("audit_logs 写入失败（event=%s）: %s", event, exc)
        return False
