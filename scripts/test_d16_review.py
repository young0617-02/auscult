"""D16 自测：高风险确定性规则判定 + interrupt() 审核节点

验证项：
  1. 规则加载：risk_rules.yml 可读
  2. 关键词命中：诊断含"停机" → needs_review=True
  3. 操作类型命中：建议含"更换轴承" → needs_review=True
  4. 无命中 + risk!=high → needs_review=False
  5. 无命中 + risk=high → needs_review=True（保守审核）
  6. 审核 payload 结构完整
  7. interrupt + resume 流程（图内冒烟：risk=high → human_review → resume → finalize）
  8. auto_approved：risk=high 但无规则命中 → 安全阀自动通过

用法：
  .venv\\Scripts\\python.exe scripts\\test_d16_review.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import (  # noqa: E402
    AlarmEvent,
    DiagnosisState,
    EvidenceItem,
    RootCause,
    Suggestion,
)
from app.graph.nodes.review import (  # noqa: E402
    _build_review_payload,
    _load_rules,
    evaluate_high_risk,
    human_review,
)


# ---------------------------------------------------------------- 辅助

def _make_state(*, diagnosis="轴承磨损", risk="high",
                suggestions=None, root_causes=None) -> DiagnosisState:
    return DiagnosisState(
        alarm=AlarmEvent(alarm_id="a1", device_id="PUMP-A",
                         metric="vib_rms", value=7.1, severity="high", ts=0),
        thread_id="d16-test",
        confidence=0.80,
        risk_level=risk,
        diagnosis=diagnosis,
        root_causes=root_causes or [RootCause(cause="轴承磨损",
                                              citations=["c_001"])],
        suggestions=suggestions or [Suggestion(action="检查润滑",
                                              citations=["c_001"])],
        evidence=[EvidenceItem(chunk_id="c_001", text="轴承磨损",
                               score=0.9)],
    )


# ---------------------------------------------------------------- 测试

def test_rules_load() -> None:
    """1. risk_rules.yml 可读。"""
    rules = _load_rules()
    assert "high_risk_keywords" in rules
    assert "high_risk_operations" in rules
    assert "停机" in rules["high_risk_keywords"]
    assert "更换轴承" in rules["high_risk_operations"]
    print("[PASS] 规则加载")


def test_keyword_hit() -> None:
    """2. 关键词命中：诊断含'停机' → needs_review。"""
    state = _make_state(diagnosis="建议立即停机检查")
    result = evaluate_high_risk(state)
    assert result["needs_review"] is True
    assert "停机" in result["keywords_hit"] or "紧急停机" in result["keywords_hit"]
    print(f"[PASS] 关键词命中（{result['keywords_hit']}）")


def test_operation_hit() -> None:
    """3. 操作类型命中：建议含'更换轴承' → needs_review。"""
    state = _make_state(
        diagnosis="轴承磨损",
        suggestions=[Suggestion(action="更换轴承", citations=["c_001"])],
    )
    result = evaluate_high_risk(state)
    assert result["needs_review"] is True
    assert "更换轴承" in result["operations_hit"]
    print(f"[PASS] 操作类型命中（{result['operations_hit']}）")


def test_no_hit_low_risk() -> None:
    """4. 无命中 + risk!=high → needs_review=False。"""
    state = _make_state(diagnosis="轴承磨损", risk="low",
                        suggestions=[Suggestion(action="检查润滑")])
    result = evaluate_high_risk(state)
    assert result["needs_review"] is False
    print("[PASS] 无命中 + low risk → 不需审核")


def test_no_hit_high_risk() -> None:
    """5. 无命中 + risk=high → needs_review=True（保守审核）。"""
    state = _make_state(diagnosis="轴承磨损", risk="high",
                        suggestions=[Suggestion(action="检查润滑")])
    result = evaluate_high_risk(state)
    assert result["needs_review"] is True
    assert "risk_level=high" in " ".join(result["reasons"])
    print("[PASS] 无命中 + high risk → 保守审核")


def test_payload_structure() -> None:
    """6. 审核 payload 结构完整。"""
    state = _make_state()
    risk_eval = evaluate_high_risk(state)
    payload = _build_review_payload(state, risk_eval)
    for key in ("thread_id", "risk_level", "diagnosis", "root_causes",
                "suggestions", "evidence_count", "confidence", "risk_eval",
                "question"):
        assert key in payload, f"payload 缺 {key}"
    assert payload["risk_eval"]["needs_review"] is True
    print("[PASS] payload 结构完整")


def test_auto_approved() -> None:
    """7. auto_approved：risk=high 但无规则命中 → 安全阀。

    但 always_interrupt_when_high=true → 仍需审核。
    测试关闭该策略时 auto_approved 生效。
    """
    state = _make_state(diagnosis="轴承磨损", risk="high",
                        suggestions=[Suggestion(action="检查润滑")])
    # mock 关闭 always_interrupt_when_high
    with patch("app.graph.nodes.review._load_rules",
               return_value={"high_risk_keywords": [],
                             "high_risk_operations": [],
                             "review_policy": {"always_interrupt_when_high": False}}):
        result = human_review(state)
    assert result["human_review"]["decision"] == "auto_approved"
    print("[PASS] auto_approved（安全阀）")


def test_graph_interrupt_resume() -> None:
    """8. 图内冒烟：risk=high → human_review → interrupt → resume → finalize。

    使用 Command(resume=...) 恢复流程。
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command
    from app.graph import build as build_mod
    from app.graph.build import build_graph

    def _mock_diagnose(state):
        return {"diagnosis": "需立即停机检查轴承",
                "confidence": 0.80,
                "risk_level": "high",
                "root_causes": [RootCause(cause="轴承磨损",
                                           citations=["c_001"])],
                "suggestions": [Suggestion(action="紧急停机",
                                           citations=["c_001"],
                                           risk="high")]}

    def _mock_analyze_sensor(state):
        return {"sensor_report": {"count": 50, "avg": 6.8, "max": 7.5,
                                  "trend": "up", "exceed_duration_ms": 12000}}

    def _mock_retrieve_evidence(state):
        return {"evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损",
                                           score=0.9)]}

    def _mock_get_history(state):
        return {"work_orders": []}

    config = {"configurable": {"thread_id": "d16-smoke"}}
    initial = {
        "alarm": {"alarm_id": "smoke-1", "device_id": "PUMP-A-01",
                  "metric": "vib_rms", "value": 7.1, "ts": 0},
        "thread_id": "d16-smoke",
    }
    with patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
         patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
         patch.object(build_mod, "get_history", _mock_get_history), \
         patch.object(build_mod, "diagnose", _mock_diagnose):
        graph = build_graph(InMemorySaver())
        # 第一次 invoke → 到 human_review 时 interrupt 挂起
        result = graph.invoke(initial, config=config)
        assert result is None or "human_review" not in result, \
            "interrupt 应挂起流程，不应直接返回结果"
        # 获取 interrupt 信息
        state = graph.get_state(config)
        assert state.next, "应有待恢复节点"
        assert "human_review" in state.next, \
            f"应在 human_review 节点挂起，实际 next={state.next}"
        # resume 恢复
        resume_value = {"action": "approved", "comment": "同意停机检查",
                        "reviewer_id": "reviewer-001"}
        result = graph.invoke(Command(resume=resume_value), config=config)
        assert result.get("report_id", "").startswith("RPT-"), \
            f"resume 后应生成 report_id: {result.get('report_id')}"
        assert result.get("human_review", {}).get("status") == "approved"
        print(f"[PASS] 图内 interrupt+resume（report_id={result['report_id']}）")


def main() -> int:
    tests = [
        ("规则加载", test_rules_load),
        ("关键词命中", test_keyword_hit),
        ("操作类型命中", test_operation_hit),
        ("无命中+low→不审核", test_no_hit_low_risk),
        ("无命中+high→保守", test_no_hit_high_risk),
        ("payload 结构", test_payload_structure),
        ("auto_approved 安全阀", test_auto_approved),
        ("图内 interrupt+resume", test_graph_interrupt_resume),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D16 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
