"""get_history 节点（D5）

接入 get_maintenance_history 查询设备历史工单。
超时预算: 2s; 降级: PG 不可达 → work_orders=[] + errors。

对应交付物: plan/Phase 3 §三.2 / §五 D5
"""

from __future__ import annotations

from typing import Any

from ...observability import prom_metrics as pm
from ...tools.get_maintenance_history import get_maintenance_history
from ..state import DiagnosisState, WorkOrder


def get_history(state: DiagnosisState) -> dict[str, Any]:
    """接入 get_maintenance_history 查询历史工单。

    输入: state.alarm（含 device_id）
    输出: {"work_orders": [WorkOrder]} 或 {"errors": [...]}
    降级: PG 不可达 → work_orders=[] + errors
    """
    alarm = state.alarm
    if alarm is None:
        return {"errors": [{"node": "get_history", "code": "E_NO_ALARM",
                            "msg": "缺少告警事件"}]}

    try:
        rows = get_maintenance_history(alarm.device_id, limit=10, timeout=2.0)
        pm.inc_tool_call("get_maintenance_history", "ok" if rows else "empty")
        work_orders = [
            WorkOrder(
                order_id=r["order_id"],
                device_id=r["device_id"],
                fault=r["fault"],
                action=r["action"],
                result=r["result"],
                created_at=str(r["created_at"]) if r["created_at"] else None,
            )
            for r in rows
        ]
        return {"work_orders": work_orders}

    except ConnectionError as exc:
        pm.inc_tool_call("get_maintenance_history", "error")
        return {
            "work_orders": [],
            "errors": [{"node": "get_history", "code": "E_PG_UNREACHABLE",
                        "msg": str(exc)}],
        }
    except Exception as exc:
        pm.inc_tool_call("get_maintenance_history", "error")
        return {
            "work_orders": [],
            "errors": [{"node": "get_history", "code": "E_PG_QUERY_ERROR",
                        "msg": str(exc)}],
        }
