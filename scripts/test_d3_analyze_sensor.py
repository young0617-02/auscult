"""D3 自测：query_sensor + analyze_sensor

验证项:
  1. query_sensor 查询真实 TDengine 数据（PUMP-A / vib_rms）
  2. query_sensor 不存在的 device_id → 空结果
  3. query_sensor 非法 device_id → ValueError
  4. _compute_stats 统计摘要（rising/stable/falling + exceed_count）
  5. analyze_sensor 节点（真实告警 → sensor_report）
  6. analyze_sensor alarm=None → errors
  7. 图内冒烟（parse_alarm → analyze_sensor → finalize）

用法:
  .venv\\Scripts\\python.exe scripts\\test_d3_analyze_sensor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import AlarmEvent, DiagnosisState  # noqa: E402
from app.tools.query_sensor import query_sensor  # noqa: E402
from app.graph.nodes.analyze_sensor import _compute_stats, analyze_sensor  # noqa: E402


def _get_first_ts() -> int:
    """从 TDengine 获取第一条数据的 epoch ms（用于构造测试告警）。"""
    from app.tools.query_sensor import _td_query  # noqa: PLC0415
    result = _td_query("SELECT ts FROM iot.st_pump_metrics LIMIT 1")
    ts_str = result["data"][0][0]
    # TDengine REST 返回 ISO 8601 字符串 → epoch ms
    from datetime import datetime, timezone  # noqa: PLC0415
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def test_query_sensor_real() -> None:
    """1. query_sensor 查询真实 TDengine 数据。"""
    ts = _get_first_ts()
    result = query_sensor("PUMP-A", "vib_rms", ts - 60000, ts + 60000)
    assert result["device_id"] == "PUMP-A"
    assert result["metric"] == "vib_rms"
    assert result["count"] > 0
    assert all("ts" in r and "value" in r for r in result["rows"])
    print(f"[PASS] query_sensor 真实查询（{result['count']} 条）")


def test_query_sensor_no_device() -> None:
    """2. 不存在的 device_id → 空结果。"""
    ts = _get_first_ts()
    result = query_sensor("NONEXISTENT", "vib_rms", ts - 60000, ts + 60000)
    assert result["count"] == 0
    assert result["rows"] == []
    print("[PASS] query_sensor 不存在 device → 空结果")


def test_query_sensor_bad_id() -> None:
    """3. 非法 device_id → ValueError。"""
    try:
        query_sensor("PUMP; DROP TABLE--", "vib_rms", 0, 1)
        raise AssertionError("应抛 ValueError")
    except ValueError:
        pass
    print("[PASS] query_sensor 非法 device → ValueError")


def test_compute_stats() -> None:
    """4. _compute_stats 统计摘要 + 趋势判断。"""
    # rising: 后半段高于前半段 10% 以上
    stats = _compute_stats([1.0, 1.1, 1.2, 2.0, 2.1, 2.2], threshold=1.5)
    assert stats["trend"] == "rising", f"应为 rising, got {stats['trend']}"
    assert stats["exceed_count"] == 3
    assert stats["max"] == 2.2
    assert stats["min"] == 1.0

    # falling: 后半段低于前半段 90% 以下
    stats = _compute_stats([2.0, 2.1, 2.2, 1.0, 1.1, 1.2], threshold=1.5)
    assert stats["trend"] == "falling"

    # stable: 前后相近
    stats = _compute_stats([1.0, 1.05, 1.0, 1.02, 1.0, 1.01], threshold=2.0)
    assert stats["trend"] == "stable"
    assert stats["exceed_count"] == 0

    # 空
    stats = _compute_stats([], threshold=1.0)
    assert stats["count"] == 0
    assert stats["trend"] == "unknown"
    print("[PASS] _compute_stats 统计 + 趋势")


def test_analyze_sensor_node() -> None:
    """5. analyze_sensor 节点（真实告警 → sensor_report）。"""
    ts = _get_first_ts()
    state = DiagnosisState(alarm=AlarmEvent(
        alarm_id="d3-test", device_id="PUMP-A",
        metric="vib_rms", value=7.1, baseline=4.5,
        severity="high", ts=ts,
    ))
    result = analyze_sensor(state)
    assert "sensor_report" in result
    report = result["sensor_report"]
    assert report is not None
    assert report["device_id"] == "PUMP-A"
    assert report["metric"] == "vib_rms"
    assert report["count"] > 0
    assert "avg" in report and "max" in report and "trend" in report
    print(f"[PASS] analyze_sensor 节点（count={report['count']}, trend={report['trend']}）")


def test_analyze_sensor_none() -> None:
    """6. analyze_sensor alarm=None → errors。"""
    state = DiagnosisState(alarm=None)
    result = analyze_sensor(state)
    assert "errors" in result
    assert result["errors"][0]["code"] == "E_NO_ALARM"
    print("[PASS] analyze_sensor alarm=None → errors")


def test_graph_smoke() -> None:
    """7. 图内冒烟: parse_alarm → analyze_sensor → finalize。"""
    from langgraph.checkpoint.memory import InMemorySaver  # noqa: PLC0415
    from app.graph.build import build_graph  # noqa: PLC0415

    ts = _get_first_ts()
    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "d3-smoke"}}
    initial = {
        "alarm": {
            "alarm_id": "smoke-3", "device_id": "PUMP-A",
            "metric": "vib_rms", "value": 7.1, "ts": ts,
        },
        "thread_id": "d3-smoke",
        "confidence": 0.8,
        "risk_level": "low",
    }
    result = graph.invoke(initial, config=config)
    # parse_alarm 规范化 + analyze_sensor 查询
    alarm = result.get("alarm")
    assert alarm is not None and alarm.device_id == "PUMP-A"
    report = result.get("sensor_report")
    assert report is not None and report["count"] > 0
    print(f"[PASS] 图内冒烟（sensor count={report['count']}）")


def main() -> int:
    tests = [
        ("query_sensor 真实查询", test_query_sensor_real),
        ("query_sensor 不存在 device", test_query_sensor_no_device),
        ("query_sensor 非法 device", test_query_sensor_bad_id),
        ("_compute_stats 统计", test_compute_stats),
        ("analyze_sensor 节点", test_analyze_sensor_node),
        ("analyze_sensor alarm=None", test_analyze_sensor_none),
        ("图内冒烟", test_graph_smoke),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D3 自测结果: {len(tests) - failures}/{len(tests)} PASS"
          + (f", {failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
