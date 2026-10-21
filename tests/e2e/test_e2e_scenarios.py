"""端到端场景测试（D23 · M3.5）

对应 plan/Phase 3 §8.2 E1–E6：
  E1  主场景：离心泵轴承振动异常（中风险） → 正常出报告，含引用
  E2  高风险（涉及停机）                   → 触发 interrupt() 人工审核
  E3  低置信度（<0.5）                     → 输出降级"初步判断"
  E4  中置信度（0.5–0.75，云端可用）        → 升级云端并成功出报告
  E5  中置信度 + 云端不可用                → 离线降级，标注原因
  E6  工具超时/失败                        → 重试 ≥3 次后降级

E7–E9（重启恢复/并发 resume/审核超时）见 scripts/test_d20_reliability.py
E10（Prompt 注入）属 D24 安全加固范围

用法：
  .venv\\Scripts\\python.exe -m pytest tests/e2e/test_e2e_scenarios.py -v
  或
  .venv\\Scripts\\python.exe tests/e2e/test_e2e_scenarios.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pytest                                             # noqa: E402

from langgraph.checkpoint.memory import InMemorySaver   # noqa: E402
from langgraph.types import Command                       # noqa: E402

from app.graph import build as build_mod                  # noqa: E402
from app.graph.build import build_graph                   # noqa: E402
from app.graph.state import (  # noqa: E402
    EvidenceItem,
    RootCause,
    Suggestion,
)


# ---------------------------------------------------------------- 形态锁定

@pytest.fixture(autouse=True)
def _deterministic_mode(monkeypatch):
    """E1–E6 场景针对**确定性编排**（gather 链 + 单次 diagnose 打桩）。

    2026-10-21 默认形态转 agent 后必须显式锁定：agent 模式下
    `parse_alarm → diagnose` 直连会绕过 gather 节点打桩，并触发真实 LLM 调用
    （离线纪律 + 场景语义双重破坏）。
    """
    monkeypatch.setenv("AUSCULT_DIAGNOSIS_MODE", "deterministic")


# ---------------------------------------------------------------- mock 工厂

def _mock_analyze_sensor(state):
    return {"sensor_report": {"count": 50, "avg": 6.8, "max": 7.5,
                              "trend": "up", "exceed_duration_ms": 12000}}


def _mock_retrieve_evidence(state):
    return {"evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损",
                                       score=0.9)]}


def _mock_get_history(state):
    return {"work_orders": []}


def _make_diagnose(*, confidence=0.82, risk="medium",
                   diagnosis="轴承磨损导致振动超标",
                   cause="轴承磨损", citations=None,
                   action="检查润滑", retry_count=0):
    """生成 diagnose mock，参数化 confidence / risk / retry_count。"""
    def _mock(state):
        return {
            "diagnosis": diagnosis,
            "confidence": confidence,
            "risk_level": risk,
            "retry_count": retry_count,
            "root_causes": [RootCause(cause=cause,
                                       citations=citations or ["c_001"])],
            "suggestions": [Suggestion(action=action,
                                       citations=citations or ["c_001"],
                                       risk=risk)],
        }
    return _mock


def _mock_escalate_cloud_success(state):
    """云端升级成功：覆盖诊断结论 + 提升 confidence。"""
    return {
        "diagnosis": "云端二次诊断：轴承严重磨损，建议立即更换",
        "confidence": 0.88,
        "risk_level": "medium",
        "root_causes": [RootCause(cause="轴承内圈磨损",
                                   citations=["c_001"])],
        "suggestions": [Suggestion(action="更换轴承",
                                    citations=["c_001"], risk="medium")],
        "escalate_cloud": True,
    }


def _mock_escalate_cloud_failure(state):
    """云端升级失败：降级标注。"""
    return {
        "degrade_reason": "cloud_unavailable",
        "escalate_cloud": True,
        "errors": [{"node": "escalate_cloud", "code": "E_CLOUD_TIMEOUT",
                     "msg": "云端 20s 超时"}],
    }


def _run_graph(diagnose_fn, escalate_fn=None, *, thread_id=None,
               resume_value=None):
    """通用图执行器：mock 节点 + 可选 resume。

    返回 (result, config)。
    """
    tid = thread_id or f"e2e-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": tid}}
    initial = {
        "alarm": {"alarm_id": "alarm-1", "device_id": "PUMP-A-01",
                  "metric": "vib_rms", "value": 7.1, "ts": 0},
        "thread_id": tid,
    }

    patches = [
        patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor),
        patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence),
        patch.object(build_mod, "get_history", _mock_get_history),
        patch.object(build_mod, "diagnose", diagnose_fn),
    ]
    if escalate_fn is not None:
        patches.append(patch.object(build_mod, "escalate_cloud", escalate_fn))

    with patches[0] if False else _multi_patch(patches):
        graph = build_graph(InMemorySaver())
        graph.invoke(initial, config=config)
        # 检查是否挂起
        st = graph.get_state(config)
        if st.next and "human_review" in st.next:
            if resume_value is None:
                resume_value = {"action": "approved",
                                "comment": "审核通过",
                                "reviewer_id": "rev-e2e"}
            result = graph.invoke(Command(resume=resume_value), config=config)
        else:
            result = graph.invoke(None, config=config) \
                if st.next else graph.get_state(config).values
    return result, config


from contextlib import ExitStack   # noqa: E402

def _multi_patch(patches):
    """多 patch context manager。"""
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


# ================================================================
# E1 主场景：离心泵轴承振动异常（中风险）
# ================================================================

def test_e1_main_scenario() -> None:
    """E1. 中风险 → finalize → 正常出报告，含引用。"""
    diagnose = _make_diagnose(confidence=0.82, risk="medium")
    result, _ = _run_graph(diagnose)
    assert result.get("report_id", "").startswith("RPT-"), \
        f"应生成 report_id: {result.get('report_id')}"
    assert "degrade_reason" not in result, "中风险不应降级"
    assert "human_review" not in result or \
        result.get("human_review", {}).get("status") == "auto_approved", \
        "中风险无需人工审核"
    print(f"[PASS] E1 主场景（{result['report_id']}）")


# ================================================================
# E2 高风险（涉及停机）→ interrupt + resume
# ================================================================

def test_e2_high_risk_review() -> None:
    """E2. 高风险 + '停机'关键词 → human_review interrupt → resume(approved)。"""
    diagnose = _make_diagnose(confidence=0.80, risk="high",
                              diagnosis="需立即停机检查轴承",
                              action="紧急停机")
    result, _ = _run_graph(diagnose)
    assert result.get("report_id", "").startswith("RPT-")
    assert result.get("human_review", {}).get("status") == "approved", \
        f"应审核通过: {result.get('human_review')}"
    assert "degrade_reason" not in result, "approved 不应降级"
    print(f"[PASS] E2 高风险审核（{result['report_id']}）")


def test_e2b_high_risk_rejected() -> None:
    """E2b. 高风险 → resume(rejected) → degrade + report。"""
    diagnose = _make_diagnose(confidence=0.80, risk="high",
                              diagnosis="需立即停机检查",
                              action="紧急停机")
    result, _ = _run_graph(diagnose,
                           resume_value={"action": "rejected",
                                         "comment": "不同意",
                                         "reviewer_id": "rev-e2b"})
    assert result.get("report_id", "").startswith("RPT-")
    assert result.get("degrade_reason") == "review_rejected", \
        f"rejected 应降级: {result.get('degrade_reason')}"
    print(f"[PASS] E2b 高风险 rejected（{result['report_id']}）")


# ================================================================
# E3 低置信度（<0.5）→ 降级
# ================================================================

def test_e3_low_confidence_degrade() -> None:
    """E3. confidence < 0.50 → degrade → 初步判断。"""
    diagnose = _make_diagnose(confidence=0.35, risk="low",
                              diagnosis="依据不足，初步判断为传感器漂移")
    result, _ = _run_graph(diagnose)
    assert result.get("report_id", "").startswith("RPT-")
    assert result.get("degrade_reason") is not None, \
        "低置信度应降级"
    print(f"[PASS] E3 低置信度降级（{result['report_id']}, "
          f"reason={result.get('degrade_reason')}）")


# ================================================================
# E4 中置信度 + 云端可用 → 升级成功
# ================================================================

def test_e4_cloud_escalation_success() -> None:
    """E4. confidence ∈ [0.50, 0.75) → escalate_cloud 成功 → report。"""
    diagnose = _make_diagnose(confidence=0.60, risk="low",
                              diagnosis="本地诊断：可能轴承磨损")
    result, _ = _run_graph(diagnose, escalate_fn=_mock_escalate_cloud_success)
    assert result.get("report_id", "").startswith("RPT-")
    assert "degrade_reason" not in result, \
        "云端成功不应降级"
    # 云端覆盖了诊断结论
    assert "云端" in result.get("diagnosis", "") or \
        result.get("confidence", 0) >= 0.80, \
        "云端应提升 confidence 或更新诊断"
    print(f"[PASS] E4 云端升级成功（{result['report_id']}, "
          f"conf={result.get('confidence')}）")


# ================================================================
# E5 中置信度 + 云端不可用 → 离线降级
# ================================================================

def test_e5_cloud_unavailable_degrade() -> None:
    """E5. confidence ∈ [0.50, 0.75) + 云端超时 → 降级标注。"""
    diagnose = _make_diagnose(confidence=0.60, risk="low",
                              diagnosis="本地诊断：可能轴承磨损")
    result, _ = _run_graph(diagnose, escalate_fn=_mock_escalate_cloud_failure)
    assert result.get("report_id", "").startswith("RPT-")
    assert result.get("degrade_reason") == "cloud_unavailable", \
        f"应标注 cloud_unavailable: {result.get('degrade_reason')}"
    print(f"[PASS] E5 云端不可用降级（{result['report_id']}, "
          f"reason={result['degrade_reason']}）")


# ================================================================
# E6 工具超时/失败 → 重试 ≥3 次后降级
# ================================================================

def test_e6_retry_exhausted_degrade() -> None:
    """E6. retry_count >= 3 → degrade。"""
    diagnose = _make_diagnose(confidence=0.40, risk="low",
                              diagnosis="工具连续超时，无法完成诊断",
                              retry_count=3)
    result, _ = _run_graph(diagnose)
    assert result.get("report_id", "").startswith("RPT-")
    assert result.get("degrade_reason") is not None, \
        "重试超限应降级"
    print(f"[PASS] E6 重试超限降级（{result['report_id']}, "
          f"reason={result['degrade_reason']}）")


# ================================================================
# 主入口
# ================================================================



# ================================================================
# E6b/E6c LLM 不可达 -> diagnose 自循环重试（2026-10-14 修复覆盖）
# ================================================================

def _make_flaky_diagnose(fail_times: int):
    """前 fail_times 次返回 E_LLM_UNREACHABLE（不设 diagnosis、retry_count++），
    之后转为成功。模拟 Ollama 偶发超时（对应审计实证的第 3 次诊断失败）。"""
    calls = {"n": 0}

    def _mock(state):
        calls["n"] += 1
        if calls["n"] <= fail_times:
            return {
                "retry_count": state.retry_count + 1,
                "errors": [{"node": "diagnose", "code": "E_LLM_UNREACHABLE",
                            "msg": f"Ollama 第 {calls['n']} 次超时"}],
            }
        return _make_diagnose(confidence=0.82, risk="medium")(state)

    _mock.calls = calls  # 便于断言调用次数
    return _mock


def test_e6b_llm_unreachable_retry_success() -> None:
    """E6b. LLM 偶发失败 2 次后成功 -> 自循环重试 -> 正常出报告。"""
    diagnose = _make_flaky_diagnose(fail_times=2)
    result, _ = _run_graph(diagnose)
    assert diagnose.calls["n"] == 3, \
        f"应重试至第 3 次成功，实际调用 {diagnose.calls['n']} 次"
    assert result.get("report_id", "").startswith("RPT-"), \
        "重试成功后应正常出报告"
    assert "degrade_reason" not in result, \
        "重试成功不应降级"
    print(f"[PASS] E6b LLM 偶发失败重试成功（{result.get('report_id')}, "
          f"diagnose 调用 {diagnose.calls['n']} 次）")


def test_e6c_llm_unreachable_retry_exhausted(monkeypatch) -> None:
    """E6c. LLM 连续失败 3 次 -> 重试耗尽 -> degrade（**关闭云端兜底**时的语义）。

    2026-10-21：兜底默认开启，故此处显式关掉 —— 保留"无兜底可用时仍能降级出报告"
    的既有护栏；开启兜底的路径由 E6d/E6e 覆盖。
    """
    monkeypatch.setenv("AUSCULT_CLOUD_FALLBACK", "0")
    diagnose = _make_flaky_diagnose(fail_times=99)
    result, _ = _run_graph(diagnose)
    assert diagnose.calls["n"] == 3, \
        f"应最多重试 3 次，实际调用 {diagnose.calls['n']} 次"
    assert result.get("report_id", "").startswith("RPT-")
    assert result.get("degrade_reason") is not None, \
        "重试耗尽应降级"
    codes = [e.get("code") for e in result.get("errors", [])]
    assert codes.count("E_LLM_UNREACHABLE") == 3, \
        f"应记录 3 次 E_LLM_UNREACHABLE: {codes}"
    print(f"[PASS] E6c LLM 连续失败重试耗尽降级（{result.get('report_id')}, "
          f"reason={result.get('degrade_reason')}）")


def test_e6d_local_llm_failure_falls_back_to_cloud(monkeypatch) -> None:
    """E6d. 本地 LLM 连续失败 -> 重试耗尽 -> **升级云端兜底**（2026-10-21 架构补齐）。

    此前该路径直接 degrade，云端完全不介入 →「云端降为兜底」只在置信度维度成立，
    在"本地模型故障"维度不成立。目标形态（本地为主）下必须补上这条边。
    """
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    monkeypatch.delenv("AUSCULT_CLOUD_FALLBACK", raising=False)
    diagnose = _make_flaky_diagnose(fail_times=99)
    result, _ = _run_graph(diagnose, escalate_fn=_mock_escalate_cloud_success)
    assert diagnose.calls["n"] == 3, "本地应重试到上限 3 次"
    assert result.get("escalate_cloud") is True, "应已升级云端兜底"
    assert result.get("diagnosis", "").startswith("云端二次诊断"), \
        "应以云端结论定稿"
    assert result.get("degrade_reason") is None, "云端兜底成功不应降级"
    assert result.get("report_id", "").startswith("RPT-")
    print(f"[PASS] E6d 本地失败 -> 云端兜底（{result.get('report_id')}）")


def test_e6e_cloud_fallback_failure_still_degrades(monkeypatch) -> None:
    """E6e. 兜底也失败 -> 仍以 degrade 收口（兜底不得把失败变成异常）。"""
    monkeypatch.setenv("AUSCULT_LLM_BACKEND", "local")
    monkeypatch.delenv("AUSCULT_CLOUD_FALLBACK", raising=False)
    diagnose = _make_flaky_diagnose(fail_times=99)
    result, _ = _run_graph(diagnose, escalate_fn=_mock_escalate_cloud_failure)
    assert result.get("escalate_cloud") is True
    assert result.get("degrade_reason") == "cloud_unavailable"
    assert result.get("report_id", "").startswith("RPT-"), \
        "兜底失败仍须能出降级报告"
    print(f"[PASS] E6e 云端兜底失败 -> 降级（{result.get('degrade_reason')}）")


def _run_with_monkeypatch(fn) -> None:
    """脚本直跑（非 pytest）时给用例注入 MonkeyPatch 并保证 env 还原。"""
    mp = pytest.MonkeyPatch()
    try:
        fn(mp)
    finally:
        mp.undo()


def main() -> int:
    tests = [
        ("E1 主场景", test_e1_main_scenario),
        ("E2 高风险审核", test_e2_high_risk_review),
        ("E2b 高风险 rejected", test_e2b_high_risk_rejected),
        ("E3 低置信度降级", test_e3_low_confidence_degrade),
        ("E4 云端升级成功", test_e4_cloud_escalation_success),
        ("E5 云端不可用降级", test_e5_cloud_unavailable_degrade),
        ("E6 重试超限降级", test_e6_retry_exhausted_degrade),
        ("E6b LLM 偶发失败重试成功", test_e6b_llm_unreachable_retry_success),
        ("E6c LLM 连续失败重试耗尽",
         lambda: _run_with_monkeypatch(test_e6c_llm_unreachable_retry_exhausted)),
        ("E6d 本地失败 -> 云端兜底",
         lambda: _run_with_monkeypatch(test_e6d_local_llm_failure_falls_back_to_cloud)),
        ("E6e 云端兜底失败 -> 降级",
         lambda: _run_with_monkeypatch(test_e6e_cloud_fallback_failure_still_degrades)),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    total = len(tests)
    print(f"\n{'=' * 50}")
    print(f"D23 端到端场景测试结果：{total - failures}/{total} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
