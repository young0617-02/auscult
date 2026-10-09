"""告警列表 REST（D0-2 · 契约1）。

GET /api/alarms?page=&size=&status=&severity=&device_id=
- 供 /alarms 告警看板（P4 D4）列表 + 筛选 + 分页 + 严重度可视化；
  Socket.IO alarm:new（D0-4）推送的兜底刷新通道
- 排序 ts DESC；返回 {items, total, page, size}

RBAC：任意已登录角色可读（工程师/审核员均为告警消费方）。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.db import get_conn
from app.api.deps import get_current_user
from app.api.errors import ok

router = APIRouter(prefix="/api/alarms", tags=["alarms"])


@router.get("")
async def list_alarms(
    page: int = Query(1, ge=1, description="页码，从 1 起"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: str | None = Query(None, max_length=20, description="按状态筛选（open/acked/closed）"),
    severity: str | None = Query(None, max_length=20, description="按严重度筛选（info/warning/critical）"),
    device_id: str | None = Query(None, max_length=100, description="按设备筛选"),
    _: dict[str, Any] = Depends(get_current_user),
) -> dict:
    conds: list[str] = []
    params: list[Any] = []
    if status:
        conds.append("status = %s")
        params.append(status)
    if severity:
        conds.append("severity = %s")
        params.append(severity)
    if device_id:
        conds.append("device_id = %s")
        params.append(device_id)
    where = f"WHERE {' AND '.join(conds)}" if conds else ""

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM alerts {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT alarm_id, device_id, metric, value, severity, status, ts
                FROM alerts {where}
                ORDER BY ts DESC
                LIMIT %s OFFSET %s""",
            [*params, size, (page - 1) * size]).fetchall()
    return ok({"items": [dict(r) for r in rows],
               "total": total, "page": page, "size": size})
