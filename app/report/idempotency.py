"""图外幂等写入（D19 · M3.4）

职责：将 finalize 生成的 report_id 幂等写入 PG `reports` 表。
      **写操作在图外**——finalize 节点仅生成 report_id，不直接写 PG。

幂等策略（plan §六.6）：
  - `idempotency_key = sha256(thread_id:sorted_citations:risk_level)[:16]`
  - PG `reports.idempotency_key` 唯一索引
  - 重复调用返回既有 `report_id`（不新建）

对应交付物：plan/Phase 3 §五 D19 / §六.6
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

POSTGRES_URL = os.environ.get(
    "LANGGRAPH_PG_URL",
    "postgresql://root:123456@127.0.0.1:5433/auscult_v2",
)


# ---------------------------------------------------------------- 幂等键

def compute_idempotency_key(thread_id: str, citations: list[str],
                             risk_level: str) -> str:
    """幂等键: sha256(thread_id:sorted_citations:risk_level)[:16]。

    与 finalize._compute_idempotency_key 同口径，复用算法。
    """
    sorted_cites = sorted(c for c in citations if c)
    raw = f"{thread_id}:{':'.join(sorted_cites)}:{risk_level}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_report_id(idempotency_key: str) -> str:
    """report_id = RPT-<idempotency_key>。"""
    return f"RPT-{idempotency_key}"


def state_to_payload(state_dict: dict[str, Any]) -> dict[str, Any]:
    """从最终 state dict 提取报告 payload 快照。

    P5-Q8：补持久化 evidence 原文（chunk_id/text/score/source_type/routes）
           与 confidence_breakdown 四分量，支撑报告详情展示与评测标注
           （引用正确率/幻觉率标注依赖证据原文可见）。
    """
    return {
        "diagnosis": state_dict.get("diagnosis"),
        "root_causes": [
            {"cause": rc.cause if hasattr(rc, "cause") else rc.get("cause", ""),
             "citations": rc.citations if hasattr(rc, "citations") else rc.get("citations", []),
             "confidence_hint": rc.confidence_hint if hasattr(rc, "confidence_hint") else rc.get("confidence_hint", 0.0)}
            for rc in state_dict.get("root_causes", [])
        ],
        "suggestions": [
            {"action": s.action if hasattr(s, "action") else s.get("action", ""),
             "citations": s.citations if hasattr(s, "citations") else s.get("citations", []),
             "risk": s.risk if hasattr(s, "risk") else s.get("risk", "low")}
            for s in state_dict.get("suggestions", [])
        ],
        "confidence": state_dict.get("confidence", 0.0),
        "confidence_breakdown": _serialize_breakdown(state_dict.get("confidence_breakdown")),
        "evidence": [_serialize_evidence(ev) for ev in state_dict.get("evidence", [])],
        "risk_level": state_dict.get("risk_level", "low"),
        "escalate_cloud": state_dict.get("escalate_cloud", False),
        "human_review": _serialize_review(state_dict.get("human_review")),
        "degrade_reason": state_dict.get("degrade_reason"),
        "errors": state_dict.get("errors", []),
    }


def _serialize_evidence(ev: Any) -> dict[str, Any]:
    """序列化证据条目（EvidenceItem Pydantic 模型或 dict 均兼容）。"""
    if isinstance(ev, dict):
        get = ev.get
    else:
        get = lambda k, d=None: getattr(ev, k, d)  # noqa: E731
    return {
        "chunk_id": get("chunk_id", ""),
        "text": get("text", ""),
        "score": float(get("score", 0.0) or 0.0),
        "source_type": get("source_type", "knowledge"),
        "routes": list(get("routes", []) or []),
    }


def _serialize_breakdown(breakdown: Any) -> dict[str, float]:
    """序列化置信度四分量（retrieval/sensor/graph/self）。"""
    if not isinstance(breakdown, dict):
        return {}
    return {k: float(v) for k, v in breakdown.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}


def _serialize_review(human_review: Any) -> dict | None:
    """序列化 human_review 字段。"""
    if human_review is None:
        return None
    if isinstance(human_review, dict):
        return human_review
    return {"status": str(human_review)}


# ---------------------------------------------------------------- PG 操作

def _get_conn():
    """惰性 PG 连接（psycopg）。"""
    import psycopg   # noqa: PLC0415
    return psycopg.connect(POSTGRES_URL)


def generate_report(state_dict: dict[str, Any]) -> dict[str, Any]:
    """图外幂等写入报告到 PG。

    输入: state_dict（graph.invoke 返回的最终 state dict）
    输出: {report_id, idempotency_key, is_new, payload}
          is_new=False 表示已存在（幂等返回既有 report_id）

    幂等：相同 idempotency_key → 返回既有 report_id，不新建。
    """
    thread_id = state_dict.get("thread_id", "")
    risk_level = state_dict.get("risk_level", "low")
    citations = []
    for rc in state_dict.get("root_causes", []):
        cites = rc.citations if hasattr(rc, "citations") else rc.get("citations", [])
        citations.extend(cites or [])

    idempotency_key = compute_idempotency_key(thread_id, citations, risk_level)
    report_id = compute_report_id(idempotency_key)
    payload = state_to_payload(state_dict)

    review_status = None
    hr = state_dict.get("human_review")
    if isinstance(hr, dict):
        review_status = hr.get("status") or hr.get("decision")
    elif hr is not None:
        review_status = str(hr)

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # 幂等：先查
            cur.execute(
                "SELECT report_id FROM reports WHERE idempotency_key = %s",
                (idempotency_key,))
            existing = cur.fetchone()
            if existing:
                conn.commit()
                return {"report_id": existing[0], "idempotency_key": idempotency_key,
                        "is_new": False, "payload": payload}

            # 新建
            cur.execute(
                """INSERT INTO reports
                   (report_id, idempotency_key, thread_id, payload,
                    risk_level, confidence, review_status, degrade_reason)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (report_id, idempotency_key, thread_id,
                 json.dumps(payload, ensure_ascii=False),
                 risk_level,
                 state_dict.get("confidence"),
                 review_status,
                 state_dict.get("degrade_reason")))
            conn.commit()
        return {"report_id": report_id, "idempotency_key": idempotency_key,
                "is_new": True, "payload": payload}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_report(report_id: str) -> dict[str, Any] | None:
    """按 report_id 查询报告。"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT report_id, idempotency_key, thread_id, payload,
                          risk_level, confidence, review_status,
                          degrade_reason, created_at
                   FROM reports WHERE report_id = %s""",
                (report_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "report_id": row[0], "idempotency_key": row[1],
                "thread_id": row[2], "payload": row[3],
                "risk_level": row[4], "confidence": row[5],
                "review_status": row[6], "degrade_reason": row[7],
                "created_at": str(row[8]) if row[8] else None,
            }
    finally:
        conn.close()


def report_exists(idempotency_key: str) -> bool:
    """检查幂等键是否已存在。"""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM reports WHERE idempotency_key = %s",
                (idempotency_key,))
            return cur.fetchone() is not None
    finally:
        conn.close()
