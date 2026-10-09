"""D2 自测：parse_alarm 节点

验证项：
  1. dict → AlarmEvent 转换 + 规则补全（vib_rms → baseline=4.5, rule_id=thr_vib_rms, severity=high）
  2. 已有 AlarmEvent 不覆盖（baseline/rule_id 保留原值）
  3. alarm=None → errors
  4. alarm 缺 device_id → errors
  5. 图内冒烟（parse_alarm → finalize 路径，验证 alarm 规范化生效）

用法：
  .venv\\Scripts\\python.exe scripts\\test_d2_parse_alarm.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import AlarmEvent, DiagnosisState  # noqa: E402
from app.graph.nodes.parse_alarm import parse_alarm  # noqa: E402


def test_dict_to_alarmevent() -> None:
    """1. dict → AlarmEvent + 规则补全。"""
    state = DiagnosisState(alarm={
        "alarm_id": "test-1", "device_id": "PUMP-A-01",
        "metric": "vib_rms", "value": 7.1, "ts": 0,
    })
    result = parse_alarm(state)
    assert "alarm" in result
    alarm: AlarmEvent = result["alarm"]
    assert isinstance(alarm, AlarmEvent)
    assert alarm.device_id == "PUMP-A-01"
    # 规则补全：vib_rms → baseline=4.5, rule_id=thr_vib_rms, severity=high
    assert alarm.baseline == 4.5, f"baseline 应为 4.5，got {alarm.baseline}"
    assert alarm.rule_id == "thr_vib_rms", f"rule_id 应为 thr_vib_rms，got {alarm.rule_id}"
    assert alarm.severity == "high", f"severity 应为 high，got {alarm.severity}"
    print("[PASS] dict → AlarmEvent + 规则补全")


def test_preserve_existing() -> None:
    """2. 已有 AlarmEvent 非默认值不覆盖 baseline/rule_id/severity。"""
    state = DiagnosisState(alarm=AlarmEvent(
        alarm_id="test-2", device_id="PUMP-A-01",
        metric="vib_rms", value=7.1, baseline=5.0,
        rule_id="custom-rule", severity="low", ts=0,
    ))
    result = parse_alarm(state)
    alarm: AlarmEvent = result["alarm"]
    assert alarm.baseline == 5.0, "已有 baseline 不应被覆盖"
    assert alarm.rule_id == "custom-rule", "已有 rule_id 不应被覆盖"
    assert alarm.severity == "low", "非默认 severity 不应被覆盖"
    print("[PASS] 已有 AlarmEvent 非默认值保留")


def test_none_alarm() -> None:
    """3. alarm=None → errors。"""
    state = DiagnosisState(alarm=None)
    result = parse_alarm(state)
    assert "errors" in result
    assert result["errors"][0]["code"] == "E_NO_ALARM"
    print("[PASS] alarm=None → errors")


def test_no_device_id() -> None:
    """4. alarm 缺 device_id → errors。"""
    state = DiagnosisState(alarm={"metric": "vib_rms", "value": 7.1, "ts": 0})
    result = parse_alarm(state)
    assert "errors" in result
    assert result["errors"][0]["code"] == "E_NO_DEVICE"
    print("[PASS] alarm 缺 device_id → errors")


def test_bearing_temp() -> None:
    """5. 另一规则：bearing_temp → baseline=85, severity=high。"""
    state = DiagnosisState(alarm={
        "alarm_id": "test-3", "device_id": "MOTOR-B-03",
        "metric": "bearing_temp", "value": 90.0, "ts": 0,
    })
    result = parse_alarm(state)
    alarm: AlarmEvent = result["alarm"]
    assert alarm.baseline == 85
    assert alarm.rule_id == "thr_bearing_temp"
    assert alarm.severity == "high"
    print("[PASS] bearing_temp 规则补全")


def test_graph_smoke() -> None:
    """6. 图内冒烟：parse_alarm → finalize（验证 alarm 规范化在图内生效）。"""
    from langgraph.checkpoint.memory import InMemorySaver
    from app.graph.build import build_graph

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "d2-smoke"}}
    initial = {
        "alarm": {
            "alarm_id": "smoke-1", "device_id": "PUMP-A-01",
            "metric": "vib_rms", "value": 7.1, "ts": 0,
        },
        "thread_id": "d2-smoke",
        "confidence": 0.8,
        "risk_level": "low",
    }
    result = graph.invoke(initial, config=config)
    # 验证 parse_alarm 已将 dict 转为 AlarmEvent 并补全规则
    alarm = result.get("alarm")
    assert alarm is not None
    assert alarm.baseline == 4.5
    assert alarm.rule_id == "thr_vib_rms"
    assert alarm.severity == "high"
    print("[PASS] 图内冒烟（parse_alarm 规范化生效）")


def main() -> int:
    tests = [
        ("dict → AlarmEvent + 规则补全", test_dict_to_alarmevent),
        ("已有 AlarmEvent 保留原值", test_preserve_existing),
        ("alarm=None → errors", test_none_alarm),
        ("alarm 缺 device_id → errors", test_no_device_id),
        ("bearing_temp 规则补全", test_bearing_temp),
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
    print(f"D2 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
