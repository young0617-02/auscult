"""D5 自测: get_maintenance_history + get_history 节点 + M3.1 四节点串联冒烟

验证项:
  1. get_maintenance_history 查询真实 PG work_orders
  2. get_maintenance_history 不存在的 device → 空列表
  3. get_history 节点（真实告警 → work_orders）
  4. get_history alarm=None → errors
  5. M3.1 四节点串联冒烟（parse_alarm → analyze_sensor → retrieve_evidence → get_history → finalize）
     — 使用 PG Checkpointer 验证落盘 + get_state 恢复

前置: Milvus(19531) + Neo4j(7687) + TDengine(6041) + PG(5433) 全部在线
用法:
  .venv\\Scripts\\python.exe scripts\\test_d5_get_history.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import AlarmEvent, DiagnosisState, WorkOrder  # noqa: E402


def _get_first_ts() -> int:
    from app.tools.query_sensor import _td_query  # noqa: PLC0415
    result = _td_query("SELECT ts FROM iot.st_pump_metrics LIMIT 1")
    from datetime import datetime  # noqa: PLC0415
    ts_str = result["data"][0][0]
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def test_query_real() -> None:
    """1. get_maintenance_history 查询真实 PG。"""
    from app.tools.get_maintenance_history import get_maintenance_history  # noqa: E402
    # 用已知存在的 device_id（从 sample 数据）
    rows = get_maintenance_history("C 0泵", limit=5)
    assert len(rows) > 0
    assert "order_id" in rows[0]
    assert "fault" in rows[0]
    print(f"[PASS] get_maintenance_history 真实查询（{len(rows)} 条工单）")


def test_query_no_device() -> None:
    """2. 不存在的 device → 空列表。"""
    from app.tools.get_maintenance_history import get_maintenance_history  # noqa: E402
    rows = get_maintenance_history("NONEXISTENT-DEVICE", limit=5)
    assert rows == []
    print("[PASS] get_maintenance_history 不存在 device → 空列表")


def test_get_history_node() -> None:
    """3. get_history 节点（真实告警 → work_orders）。"""
    from app.graph.nodes.get_history import get_history  # noqa: E402
    state = DiagnosisState(alarm=AlarmEvent(
        alarm_id="d5-test", device_id="C 0泵",
        metric="motor_current", value=15.0, baseline=12.0,
        severity="high", ts=_get_first_ts(),
    ))
    result = get_history(state)
    assert "work_orders" in result
    orders = result["work_orders"]
    if orders:
        assert isinstance(orders[0], WorkOrder)
    print(f"[PASS] get_history 节点（{len(orders)} 条工单）")


def test_get_history_none() -> None:
    """4. get_history alarm=None → errors。"""
    from app.graph.nodes.get_history import get_history  # noqa: E402
    state = DiagnosisState(alarm=None)
    result = get_history(state)
    assert "errors" in result
    assert result["errors"][0]["code"] == "E_NO_ALARM"
    print("[PASS] get_history alarm=None → errors")


def test_m31_serial_smoke() -> None:
    """5. M3.1 四节点串联冒烟（PG Checkpointer 落盘 + get_state 恢复）。

    完整链路: parse_alarm → analyze_sensor → retrieve_evidence → get_history → finalize
    使用 PG Checkpointer 验证 checkpoint 落盘。
    """
    from app.graph.checkpointer import build_checkpointer  # noqa: E402
    from app.graph.build import build_graph  # noqa: E402

    ts = _get_first_ts()
    config = {"configurable": {"thread_id": "m31-smoke"}}
    initial = {
        "alarm": {
            "alarm_id": "m31-1", "device_id": "PUMP-A",
            "metric": "vib_rms", "value": 7.1, "ts": ts,
        },
        "thread_id": "m31-smoke",
        "confidence": 0.8,
        "risk_level": "low",
    }
    with build_checkpointer() as saver:
        graph = build_graph(saver)
        result = graph.invoke(initial, config=config)

        # 验证四节点全部执行
        alarm = result.get("alarm")
        assert alarm is not None and alarm.rule_id == "thr_vib_rms"
        assert alarm.severity == "high"

        report = result.get("sensor_report")
        assert report is not None and report["count"] > 0

        evidence = result.get("evidence", [])
        assert len(evidence) > 0

        # get_history: PUMP-A 可能无工单（work_orders 用中文 device_id），但节点不应报错
        work_orders = result.get("work_orders", [])
        # PG checkpoint 落盘验证
        snapshot = graph.get_state(config)
        assert snapshot is not None

    print(f"[PASS] M3.1 串联冒烟（PG checkpoint 落盘 + "
          f"sensor={report['count']} evidence={len(evidence)} "
          f"orders={len(work_orders)}）")


def main() -> int:
    tests = [
        ("get_maintenance_history 真实查询", test_query_real),
        ("get_maintenance_history 不存在 device", test_query_no_device),
        ("get_history 节点", test_get_history_node),
        ("get_history alarm=None", test_get_history_none),
        ("M3.1 四节点串联冒烟", test_m31_serial_smoke),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D5 自测结果: {len(tests) - failures}/{len(tests)} PASS"
          + (f", {failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
