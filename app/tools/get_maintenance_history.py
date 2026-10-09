"""get_maintenance_history 工具执行体（D5）

从 PostgreSQL work_orders 表查询设备历史工单。
使用 psycopg（已安装 3.3.6），连接 auscult_v2 库 @ 5433。

对应交付物: plan/Phase 3 §五 D5 / §四.3
Schema 来源: schemas/tools_v2.json → get_maintenance_history
表: work_orders(order_id, device_id, fault, action, result, created_at)
"""

from __future__ import annotations

import os
from typing import Any

PG_URL = os.environ.get(
    "LANGGRAPH_PG_URL",
    "postgresql://root:123456@127.0.0.1:5433/auscult_v2",
)

_QUERY = (
    "SELECT order_id, device_id, fault, action, result, created_at "
    "FROM work_orders "
    "WHERE device_id = %s "
    "ORDER BY created_at DESC "
    "LIMIT %s"
)


def get_maintenance_history(
    device_id: str,
    *,
    limit: int = 10,
    timeout: float = 2.0,
) -> list[dict[str, Any]]:
    """查询设备历史工单。

    参数:
        device_id: 设备 ID
        limit:     最多返回条数（默认 10）
        timeout:   超时（秒）

    返回:
        [{"order_id", "device_id", "fault", "action", "result", "created_at"}]

    异常:
        ConnectionError: PG 不可达
        RuntimeError: 查询失败
    """
    import psycopg  # noqa: PLC0415

    try:
        with psycopg.connect(PG_URL, connect_timeout=int(timeout)) as conn:
            with conn.cursor() as cur:
                cur.execute(_QUERY, (device_id, limit))
                rows = cur.fetchall()
    except psycopg.OperationalError as exc:
        raise ConnectionError(f"PG 不可达: {exc}")
    except Exception as exc:
        raise RuntimeError(f"PG 查询失败: {exc}")

    columns = ["order_id", "device_id", "fault", "action", "result", "created_at"]
    return [dict(zip(columns, row, strict=False)) for row in rows]
