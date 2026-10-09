"""D17 自测：审核状态机 + resume() 恢复

验证项：
  1. 状态机常量定义（PENDING/APPROVED/REJECTED/TIMEOUT）
  2. resume approved → status=approved，正常通过
  3. resume rejected → degrade_reason="review_rejected"
  4. resume timeout → degrade_reason="review_timeout"
  5. 非法 action → 默认 REJECTED + errors
  6. approved/rejected 无 reviewer_id → errors
  7. timeout 无需 reviewer_id → 合法
  8. payload 含 review_status=pending
  9. 图内 interrupt + resume(approved) → finalize
  10. 图内 interrupt + resume(rejected) → degrade + finalize
  11. 图内 interrupt + resume(timeout) → degrade + finalize

用法：
  .venv\\Scripts\\python.exe scripts\\test_d17_resume.py
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
    APPROVED,
    PENDING,
    REJECTED,
    TIMEOUT,
    _build_review_payload,
    _validate_resume,
    evaluate_high_risk,
    human_review,
)


# ---------------------------------------------------------------- 辅助

def _make_high_risk_state() -> DiagnosisState:
    """构造高风险状态（含'停机'关键词，触发 needs_review）。"""
    return DiagnosisState(
        alarm=AlarmEvent(alarm_id="a1", device_id="PUMP-A",
                         metric="vib_rms", value=7.1, severity="high", ts=0),
        thread_id="d17-test",
        confidence=0.80,
        risk_level="high",
        diagnosis="需立即停机检查轴承",
        root_causes=[RootCause(cause="轴承磨损", citations=["c_001"])],
        suggestions=[Suggestion(action="紧急停机", citations=["c_001"],
                                risk="high")],
        evidence=[EvidenceItem(chunk_id="c_001", text="轴承磨损", score=0.9)],
    )


def _invoke_review_with_resume(state, resume_value):
    """mock interrupt() 返回 resume_value，执行 human_review。"""
    with patch("app.graph.nodes.review.interrupt", return_value=resume_value):
        return human_review(state)


# ---------------------------------------------------------------- 测试

def test_status_constants() -> None:
    """1. 状态机常量。"""
    assert PENDING == "pending"
    assert APPROVED == "approved"
    assert REJECTED == "rejected"
    assert TIMEOUT == "timeout"
    print("[PASS] 状态机常量")


def test_resume_approved() -> None:
    """2. approved → 正常通过。"""
    state = _make_high_risk_state()
    resume = {"action": "approved", "comment": "同意",
              "reviewer_id": "rev-001"}
    result = _invoke_review_with_resume(state, resume)
    assert result["human_review"]["status"] == APPROVED
    assert result["human_review"]["reviewer_id"] == "rev-001"
    assert "degrade_reason" not in result
    print("[PASS] resume approved")


def test_resume_rejected() -> None:
    """3. rejected → degrade_reason。"""
    state = _make_high_risk_state()
    resume = {"action": "rejected", "comment": "不同意",
              "reviewer_id": "rev-002"}
    result = _invoke_review_with_resume(state, resume)
    assert result["human_review"]["status"] == REJECTED
    assert result["degrade_reason"] == "review_rejected"
    print("[PASS] resume rejected")


def test_resume_timeout() -> None:
    """4. timeout → degrade_reason。"""
    state = _make_high_risk_state()
    resume = {"action": "timeout"}
    result = _invoke_review_with_resume(state, resume)
    assert result["human_review"]["status"] == TIMEOUT
    assert result["degrade_reason"] == "review_timeout"
    assert "审核超时" in result["human_review"]["comment"]
    print("[PASS] resume timeout")


def test_invalid_action() -> None:
    """5. 非法 action → 默认 REJECTED + errors。"""
    state = _make_high_risk_state()
    resume = {"action": "maybe", "reviewer_id": "rev-003"}
    result = _invoke_review_with_resume(state, resume)
    assert result["human_review"]["status"] == REJECTED
    assert result["degrade_reason"] == "review_rejected"
    assert any(e["code"] == "E_INVALID_ACTION" for e in result.get("errors", []))
    print("[PASS] 非法 action")


def test_missing_reviewer() -> None:
    """6. approved 无 reviewer_id → errors。"""
    state = _make_high_risk_state()
    resume = {"action": "approved", "comment": "同意"}
    result = _invoke_review_with_resume(state, resume)
    assert any(e["code"] == "E_NO_REVIEWER" for e in result.get("errors", []))
    print("[PASS] 缺 reviewer_id → errors")


def test_timeout_no_reviewer_ok() -> None:
    """7. timeout 无 reviewer_id → 合法。"""
    state = _make_high_risk_state()
    resume = {"action": "timeout"}
    result = _invoke_review_with_resume(state, resume)
    assert not any(e["code"] == "E_NO_REVIEWER" for e in result.get("errors", []))
    print("[PASS] timeout 无需 reviewer_id")


def test_payload_has_pending() -> None:
    """8. payload 含 review_status=pending。"""
    state = _make_high_risk_state()
    risk_eval = evaluate_high_risk(state)
    payload = _build_review_payload(state, risk_eval)
    assert payload["review_status"] == PENDING
    assert "resume_hint" in payload
    print("[PASS] payload 含 review_status=pending")


def test_graph_approved() -> None:
    """9. 图内 interrupt + resume(approved) → finalize。"""
    _graph_resume_test("approved", "rev-g1",
                       expect_degrade=False, expect_report=True)


def test_graph_rejected() -> None:
    """10. 图内 interrupt + resume(rejected) → degrade + finalize。"""
    _graph_resume_test("rejected", "rev-g2",
                       expect_degrade=True, expect_report=True)


def test_graph_timeout() -> None:
    """11. 图内 interrupt + resume(timeout) → degrade + finalize。"""
    _graph_resume_test("timeout", None,
                       expect_degrade=True, expect_report=True)


def _graph_resume_test(action: str, reviewer_id: str | None,
                       expect_degrade: bool, expect_report: bool) -> None:
    """通用图内 interrupt + resume 测试。"""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command
    from app.graph import build as build_mod
    from app.graph.build import build_graph

    def _mock_diagnose(state):
        return {"diagnosis": "需立即停机检查轴承",
                "confidence": 0.80, "risk_level": "high",
                "root_causes": [RootCause(cause="轴承磨损",
                                           citations=["c_001"])],
                "suggestions": [Suggestion(action="紧急停机",
                                           citations=["c_001"], risk="high")]}

    def _mock_analyze_sensor(state):
        return {"sensor_report": {"count": 50, "avg": 6.8, "max": 7.5,
                                  "trend": "up", "exceed_duration_ms": 12000}}

    def _mock_retrieve_evidence(state):
        return {"evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损",
                                           score=0.9)]}

    def _mock_get_history(state):
        return {"work_orders": []}

    config = {"configurable": {"thread_id": f"d17-{action}"}}
    initial = {
        "alarm": {"alarm_id": "smoke-1", "device_id": "PUMP-A-01",
                  "metric": "vib_rms", "value": 7.1, "ts": 0},
        "thread_id": f"d17-{action}",
    }
    with patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
         patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
         patch.object(build_mod, "get_history", _mock_get_history), \
         patch.object(build_mod, "diagnose", _mock_diagnose):
        graph = build_graph(InMemorySaver())
        # 第一次 → interrupt 挂起
        graph.invoke(initial, config=config)
        st = graph.get_state(config)
        assert st.next and "human_review" in st.next, \
            f"应在 human_review 挂起（next={st.next}）"
        # resume
        resume_val = {"action": action}
        if reviewer_id:
            resume_val["reviewer_id"] = reviewer_id
        result = graph.invoke(Command(resume=resume_val), config=config)

    if expect_report:
        assert result.get("report_id", "").startswith("RPT-"), \
            f"应生成 report_id: {result.get('report_id')}"
    if expect_degrade:
        assert result.get("degrade_reason", "").startswith("review_"), \
            f"应有 review 降级标记: {result.get('degrade_reason')}"
    else:
        assert "degrade_reason" not in result, \
            f"approved 不应有降级: {result.get('degrade_reason')}"
    assert result["human_review"]["status"] == action
    print(f"[PASS] 图内 resume({action}) → "
          f"report={result.get('report_id', 'N/A')} "
          f"degrade={result.get('degrade_reason', 'none')}")


def main() -> int:
    tests = [
        ("状态机常量", test_status_constants),
        ("resume approved", test_resume_approved),
        ("resume rejected", test_resume_rejected),
        ("resume timeout", test_resume_timeout),
        ("非法 action", test_invalid_action),
        ("缺 reviewer_id", test_missing_reviewer),
        ("timeout 无需 reviewer", test_timeout_no_reviewer_ok),
        ("payload 含 pending", test_payload_has_pending),
        ("图内 approved", test_graph_approved),
        ("图内 rejected", test_graph_rejected),
        ("图内 timeout", test_graph_timeout),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D17 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
