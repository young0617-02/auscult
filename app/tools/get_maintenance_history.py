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


#: 库里实际存在的设备编号样本（ISS-056：空结果时回灌给模型自我纠正）
_KNOWN_DEVICES_QUERY = (
    "SELECT DISTINCT device_id FROM work_orders ORDER BY 1 LIMIT %s"
)


def list_known_devices(*, limit: int = 5, timeout: float = 1.0) -> list[str] | None:
    """工单库里实际存在的设备编号样本（ISS-056 · 2026-10-22）。

    背景：`work_orders.device_id` 的口径与告警/TDengine 的编号体系**未核查一致**
    （离线环境无法连库实证；parsed 源文件里甚至是客户号/“A 0泵”这类值）——
    硬编码别名映射有"猜错方向"的风险。故空结果时改为把库里**真实样本**回灌模型，
    让它自己纠正编号，比任何猜测都可靠。

    返回: 编号列表；库不可达/查询失败返回 None（调用方保守处理，不谎称"无此设备"）。
    """
    import psycopg  # noqa: PLC0415

    try:
        with psycopg.connect(PG_URL, connect_timeout=int(timeout)) as conn:
            with conn.cursor() as cur:
                cur.execute(_KNOWN_DEVICES_QUERY, (limit,))
                return [str(r[0]) for r in cur.fetchall()]
    except Exception:                                       # noqa: BLE001 - 探测失败不阻塞
        return None
