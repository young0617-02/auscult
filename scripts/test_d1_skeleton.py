"""D1 骨架自测

验证项：
  1. DiagnosisState 可实例化（Pydantic 校验）
  2. 条件路由逻辑正确（五档优先级）
  3. StateGraph 可编译（InMemorySaver，不依赖 PG）
  4. 冒烟跑通（固定告警 → finalize 路径，confidence=0.8）
  5. PG Checkpointer 可连接（PostgresSaver.setup() 建表）

用法：
  .venv\\Scripts\\python.exe scripts\\test_d1_skeleton.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import AlarmEvent, DiagnosisState  # noqa: E402
from app.graph.build import _route_condition, build_graph  # noqa: E402


def test_state() -> None:
    """1. DiagnosisState 可实例化 + Pydantic 校验。"""
    state = DiagnosisState(
        alarm=AlarmEvent(
            alarm_id="test-1", device_id="PUMP-A-01",
            metric="vib_rms", value=7.1, severity="high", ts=0,
        ),
        thread_id="t-test",
        confidence=0.8,
        risk_level="low",
    )
    assert state.confidence == 0.8
    assert state.alarm.device_id == "PUMP-A-01"
    assert state.evidence == []
    assert state.risk_level == "low"
    print("[PASS] DiagnosisState 实例化 + Pydantic 校验")


def test_route() -> None:
    """2. 条件路由五档优先级（plan §3.3）。"""
    # ① retry_count ≥ 3 → degrade（最高优先级，先于 confidence）
    s = DiagnosisState(confidence=0.9, risk_level="low", retry_count=3)
    assert _route_condition(s) == "degrade", f"retry≥3 应走 degrade，got {_route_condition(s)}"

    # ② confidence < 0.50 → degrade
    s = DiagnosisState(confidence=0.3, risk_level="low")
    assert _route_condition(s) == "degrade"

    # ③ confidence ∈ [0.50, 0.75) → escalate_cloud
    s = DiagnosisState(confidence=0.6, risk_level="low")
    assert _route_condition(s) == "escalate_cloud"

    # ④ risk_level == "high" → human_review（confidence ≥ 0.75 时）
    s = DiagnosisState(confidence=0.8, risk_level="high")
    assert _route_condition(s) == "human_review"

    # ⑤ else → finalize
    s = DiagnosisState(confidence=0.8, risk_level="low")
    assert _route_condition(s) == "finalize"

    # 边界：confidence=0.50 恰好 → escalate_cloud
    s = DiagnosisState(confidence=0.50, risk_level="low")
    assert _route_condition(s) == "escalate_cloud"

    # 边界：confidence=0.75 恰好 → 不走 escalate_cloud
    s = DiagnosisState(confidence=0.75, risk_level="low")
    assert _route_condition(s) == "finalize"

    print("[PASS] 条件路由五档优先级 + 边界值")


def test_compile() -> None:
    """3. StateGraph 可编译。"""
    from langgraph.checkpoint.memory import InMemorySaver
    graph = build_graph(InMemorySaver())
    assert graph is not None
    print("[PASS] StateGraph 编译（InMemorySaver）")


def test_smoke_finalize() -> None:
    """4a. 冒烟：confidence=0.8 + risk=low → finalize 路径。"""
    from langgraph.checkpoint.memory import InMemorySaver
    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "smoke-finalize"}}
    initial = {
        "alarm": {
            "alarm_id": "smoke-1", "device_id": "PUMP-A-01",
            "metric": "vib_rms", "value": 7.1, "severity": "high", "ts": 0,
        },
        "thread_id": "smoke-finalize",
        "confidence": 0.8,
        "risk_level": "low",
    }
    result = graph.invoke(initial, config=config)
    assert result is not None
    print("[PASS] 冒烟跑通（finalize 路径）")


def test_smoke_degrade() -> None:
    """4b. 冒烟：confidence=0.3 → degrade 路径。"""
    from langgraph.checkpoint.memory import InMemorySaver
    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "smoke-degrade"}}
    initial = {
        "thread_id": "smoke-degrade",
        "confidence": 0.3,
        "risk_level": "low",
    }
    result = graph.invoke(initial, config=config)
    assert result is not None
    assert result.get("degrade_reason") is not None
    print("[PASS] 冒烟跑通（degrade 路径）")


def test_pg_checkpointer() -> None:
    """5. PG Checkpointer 可连接 + setup() 建表。"""
    from app.graph.checkpointer import build_checkpointer
    with build_checkpointer() as saver:
        assert saver is not None
        # setup() 已在 build_checkpointer 内调用（幂等建表）
    print("[PASS] PG Checkpointer 连接 + setup()")


def test_pg_smoke() -> None:
    """6. PG Checkpointer 冒烟：真实 PG 落盘 + 恢复。"""
    from app.graph.checkpointer import build_checkpointer
    config = {"configurable": {"thread_id": "pg-smoke"}}
    initial = {
        "alarm": {
            "alarm_id": "pg-1", "device_id": "PUMP-A-01",
            "metric": "vib_rms", "value": 7.1, "severity": "high", "ts": 0,
        },
        "thread_id": "pg-smoke",
        "confidence": 0.8,
        "risk_level": "low",
    }
    with build_checkpointer() as saver:
        graph = build_graph(saver)
        result = graph.invoke(initial, config=config)
        # 验证 checkpoint 已落盘：get_state 可读取
        snapshot = graph.get_state(config)
        assert snapshot is not None
    print("[PASS] PG Checkpointer 冒烟（落盘 + get_state）")


def main() -> int:
    tests = [
        ("DiagnosisState 实例化", test_state),
        ("条件路由逻辑", test_route),
        ("StateGraph 编译", test_compile),
        ("冒烟 finalize 路径", test_smoke_finalize),
        ("冒烟 degrade 路径", test_smoke_degrade),
        ("PG Checkpointer 连接", test_pg_checkpointer),
        ("PG Checkpointer 冒烟", test_pg_smoke),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D1 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
