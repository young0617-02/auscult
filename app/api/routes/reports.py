"""诊断报告 REST（D0-2 · 契约2/3）。

GET /api/reports?status=&risk=&page=&size=   列表（契约补丁冻结口径，2026-10 确认）
GET /api/reports/{report_id}                 详情（复用 app.report.idempotency.get_report）

status 语义（review_status 列）：
- pending        → review_status IS NULL（待审核，含 risk=high 刚生成未走完审核的）
- approved / rejected / timeout / auto_approved → 精确匹配

RBAC：任意已登录角色可读；审核写操作在 D0-5 另立路由。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.db import get_conn
from app.api.deps import get_current_user
from app.api.errors import ApiError, ok
from app.device_ids import canonicalize_ids
from app.report.idempotency import get_report as _fetch_report

router = APIRouter(prefix="/api/reports", tags=["reports"])

_STATUS_MAP: dict[str, str | None] = {
    "pending": None,
    "approved": "approved",
    "rejected": "rejected",
    "timeout": "timeout",
    "auto_approved": "auto_approved",
}
_RISKS = {"low", "medium", "high"}


@router.get("")
async def list_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="pending/approved/rejected/timeout/auto_approved"),
    risk: str | None = Query(None, description="low/medium/high"),
    _: dict[str, Any] = Depends(get_current_user),
) -> dict:
    if status is not None and status not in _STATUS_MAP:
        raise ApiError("E_INVALID_ARG", f"status 仅支持 {'/'.join(_STATUS_MAP)}")
    if risk is not None and risk not in _RISKS:
        raise ApiError("E_INVALID_ARG", f"risk 仅支持 {'/'.join(sorted(_RISKS))}")

    conds: list[str] = []
    params: list[Any] = []
    if status is not None:
        mapped = _STATUS_MAP[status]
        if mapped is None:                      # pending → review_status IS NULL
            conds.append("review_status IS NULL")
        else:
            conds.append("review_status = %s")
            params.append(mapped)
    if risk is not None:
        conds.append("risk_level = %s")
        params.append(risk)
    where = f"WHERE {' AND '.join(conds)}" if conds else ""

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM reports {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT report_id, thread_id, risk_level, confidence, review_status,
                       degrade_reason, created_at,
                       payload->>'diagnosis' AS diagnosis
                FROM reports {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s""",
            [*params, size, (page - 1) * size]).fetchall()
    # ISS-056 展示口径：历史 payload 里的短编号（迁移前写入）统一显示为规范编号；
    # 库内证据不改写（`canonicalize_ids` 纯展示层归一、幂等）。
    return ok({"items": [canonicalize_ids(dict(r)) for r in rows],
               "total": total, "page": page, "size": size})


@router.get("/{report_id}")
async def get_report_detail(
    report_id: str,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict:
    rep = _fetch_report(report_id)
    if rep is None:
        raise ApiError("E_NOT_FOUND", f"报告 {report_id} 不存在")
    return ok(canonicalize_ids(rep))     # 展示口径统一，库内 payload 不变
