"""D14 自测：escalate_cloud 节点（云端路由 + 脱敏 + 超时降级 + 审计）

验证项：
  1. 脱敏：device_id → 设备#<hash>，work_orders.device_id 同步脱敏
  2. 成功路径：mock call_cloud 返回有效 JSON → 诊断覆盖 + 置信度重算
  3. 超时降级：call_cloud 抛 TimeoutError → degrade_reason="cloud_unavailable"
  4. JSON 解析失败降级
  5. 审计记录写入 reports/cloud_audit.jsonl
  6. 预算 hook（check_budget 恒 True，D15 待接入）
  7. 图内冒烟（confidence ∈ [0.50,0.75) → escalate_cloud → finalize）

用法：
  .venv\\Scripts\\python.exe scripts\\test_d14_escalate_cloud.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import (  # noqa: E402
    AlarmEvent,
    DiagnosisState,
    EvidenceItem,
    GraphPath,
    RootCause,
    Suggestion,
    WorkOrder,
)
from app.router import cloud  # noqa: E402
from app.router.cloud import CloudRouter, sanitize_state  # noqa: E402
from app.graph.nodes.escalate_cloud import escalate_cloud  # noqa: E402


# ---------------------------------------------------------------- 测试辅助

def _make_state(*, confidence: float = 0.6, severity: str = "medium") -> DiagnosisState:
    """构造完整诊断后状态（模拟 diagnose 输出）。"""
    return DiagnosisState(
        alarm=AlarmEvent(
            alarm_id="alm-1", device_id="PUMP-A-01",
            metric="vib_rms", value=7.1, baseline=4.5,
            severity=severity, ts=0,
        ),
        thread_id="d14-test",
        sensor_report={"count": 50, "avg": 6.8, "max": 7.5,
                       "trend": "up", "exceed_duration_ms": 12000},
        evidence=[
            EvidenceItem(chunk_id="c_001", text="轴承磨损会导致振动烈度升高",
                         score=0.92, source_type="knowledge"),
            EvidenceItem(chunk_id="c_002", text="润滑不良加速轴承失效",
                         score=0.88, source_type="knowledge"),
        ],
        graph_paths=[GraphPath(description="轴承磨损 → 振动超标")],
        work_orders=[WorkOrder(order_id="WO-2024-01",
                               device_id="PUMP-A-01",
                               fault="轴承磨损", action="更换轴承")],
        diagnosis="本地初步诊断：轴承磨损",
        root_causes=[RootCause(cause="轴承磨损", citations=["c_001"],
                               confidence_hint=0.6)],
        suggestions=[Suggestion(action="检查润滑", citations=["c_002"],
                                risk="low")],
        confidence=confidence,
        risk_level="medium",
    )


_VALID_CLOUD_RESPONSE = json.dumps({
    "diagnosis": "云端复核：轴承严重磨损，建议立即停机检查",
    "root_causes": [
        {"cause": "轴承磨损严重", "citations": ["c_001"], "confidence_hint": 0.85},
    ],
    "suggestions": [
        {"action": "停机检查轴承并更换", "citations": ["c_001", "c_002"], "risk": "high"},
    ],
    "self_confidence": 0.82,
})


# ---------------------------------------------------------------- 测试用例

def test_sanitize() -> None:
    """1. 脱敏：device_id → 设备#<hash>。"""
    state = _make_state()
    sanitized = sanitize_state(state)
    dev = sanitized["alarm"]["device_id"]
    assert dev.startswith("设备#"), f"device_id 未脱敏: {dev}"
    assert dev != "PUMP-A-01", "device_id 未被替换"
    assert "PUMP-A-01" not in json.dumps(sanitized, ensure_ascii=False), \
        "脱敏后仍含原始 device_id"
    # work_orders 也脱敏
    wo_dev = sanitized["work_orders"][0]["device_id"]
    assert wo_dev.startswith("设备#"), "work_orders.device_id 未脱敏"
    # 证据文本保留（通用知识）
    assert sanitized["evidence"][0]["text"], "证据文本不应被清空"
    print("[PASS] 脱敏：device_id → 设备#<hash>")


def test_cloud_success() -> None:
    """2. 成功路径：mock call_cloud → 诊断覆盖 + 置信度重算。"""
    state = _make_state()
    router = CloudRouter()
    with patch.object(cloud, "call_cloud", return_value=_VALID_CLOUD_RESPONSE):
        result = router.escalate(state)
    assert result.get("escalate_cloud") is True
    assert "云端复核" in result["diagnosis"], "诊断未更新"
    assert result["root_causes"][0].cause == "轴承磨损严重"
    assert result["suggestions"][0].risk == "high"
    assert result["confidence"] > 0, "置信度应已重算"
    assert "degrade_reason" not in result, "成功路径不应有 degrade_reason"
    print(f"[PASS] 成功路径（conf={result['confidence']:.4f}）")


def test_cloud_timeout() -> None:
    """3. 超时降级：call_cloud 抛 TimeoutError → degrade_reason。"""
    state = _make_state()
    router = CloudRouter()
    with patch.object(cloud, "call_cloud", side_effect=TimeoutError("timeout")):
        result = router.escalate(state)
    assert result.get("degrade_reason") == "cloud_unavailable"
    assert result.get("escalate_cloud") is True
    assert result["errors"][0]["code"] == "E_CLOUD_UNAVAILABLE"
    print("[PASS] 超时降级")


def test_cloud_unreachable() -> None:
    """3b. 不可达降级：call_cloud 抛 ConnectionError。"""
    state = _make_state()
    router = CloudRouter()
    with patch.object(cloud, "call_cloud",
                      side_effect=ConnectionError("unreachable")):
        result = router.escalate(state)
    assert result.get("degrade_reason") == "cloud_unavailable"
    print("[PASS] 不可达降级")


def test_cloud_json_parse_fail() -> None:
    """4. JSON 解析失败降级。"""
    state = _make_state()
    router = CloudRouter()
    with patch.object(cloud, "call_cloud", return_value="这不是JSON"):
        result = router.escalate(state)
    assert result.get("degrade_reason") == "cloud_unavailable"
    assert result["errors"][0]["code"] == "E_CLOUD_JSON_PARSE"
    print("[PASS] JSON 解析失败降级")


def test_audit_written() -> None:
    """5. 审计记录写入 reports/cloud_audit.jsonl。"""
    audit_path = PROJECT_ROOT / "reports" / "cloud_audit.jsonl"
    count_before = 0
    if audit_path.exists():
        count_before = sum(1 for _ in audit_path.open(encoding="utf-8"))
    state = _make_state()
    router = CloudRouter()
    with patch.object(cloud, "call_cloud", return_value=_VALID_CLOUD_RESPONSE):
        router.escalate(state)
    # 失败也写审计
    with patch.object(cloud, "call_cloud", side_effect=TimeoutError("t")):
        router.escalate(state)
    count_after = sum(1 for _ in audit_path.open(encoding="utf-8"))
    assert count_after >= count_before + 2, \
        f"审计记录应增加 ≥2 条，实际增加 {count_after - count_before}"
    # 检查最后一条含 hash_post
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    last = json.loads(lines[-1])
    assert "hash_pre" in last and "hash_post" in last
    assert last["success"] is False  # 最后是超时
    print(f"[PASS] 审计记录写入（+{count_after - count_before} 条）")


def test_budget_hook() -> None:
    """6. 预算 hook：check_budget 当前恒 True（D15 待接入）。"""
    assert cloud.check_budget() is True
    print("[PASS] 预算 hook（恒 True，D15 待接入）")


def test_graph_smoke_escalate() -> None:
    """7. 图内冒烟：confidence ∈ [0.50,0.75) → escalate_cloud → finalize。

    mock 中间节点（analyze_sensor/retrieve_evidence/get_history/diagnose）
    使 diagnose 返回 conf=0.6（触发 escalate_cloud），
    mock call_cloud 返回有效 JSON（云端成功），
    验证最终 report_id 生成且诊断含云端复核。
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from app.graph import build as build_mod
    from app.graph.build import build_graph

    # mock 中间节点：返回足够数据使置信度落在 [0.50, 0.75)
    def _mock_analyze_sensor(state):
        return {"sensor_report": {"count": 50, "avg": 6.8, "max": 7.5,
                                  "trend": "up", "exceed_duration_ms": 12000}}

    def _mock_retrieve_evidence(state):
        return {
            # c_002 必须存在：`_VALID_CLOUD_RESPONSE` 的 suggestions 引用了 ["c_001", "c_002"]，
            # 引用硬校验（finalize）要求被引 chunk_id 必须在 evidence 内，否则直接 blocked 降级
            # （2026-10-22 复跑发现：只给 c_001 时图会因引用校验失败而不出报告）。
            "evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损",
                                      score=0.9, source_type="knowledge"),
                         EvidenceItem(chunk_id="c_002", text="振动超标处置规程",
                                      score=0.85, source_type="knowledge")],
            "graph_paths": [GraphPath(description="轴承磨损 → 振动超标")],
        }

    def _mock_get_history(state):
        return {"work_orders": [WorkOrder(order_id="WO-1",
                                          device_id="PUMP-A-01",
                                          fault="轴承磨损", action="更换")]}

    # mock diagnose：self_confidence=0.6 → 复合置信度≈0.636 ∈ [0.50,0.75)
    def _mock_diagnose(state):
        raw_conf, bd = cloud.compute_confidence(state, 0.6)
        conf = cloud.calibrate_confidence(raw_conf)
        risk = cloud._determine_risk_level(state.alarm.severity, conf)
        return {"diagnosis": "本地诊断", "confidence": conf,
                "risk_level": risk,
                "confidence_breakdown": bd,
                "root_causes": [], "suggestions": []}

    config = {"configurable": {"thread_id": "d14-smoke"}}
    initial = {
        "alarm": {"alarm_id": "smoke-1", "device_id": "PUMP-A-01",
                  "metric": "vib_rms", "value": 7.1, "ts": 0},
        "thread_id": "d14-smoke",
    }
    # 2026-10-22：云端升级（escalate）是 **deterministic 链**的专属环节；默认 agent 形态下
    # agent 循环自己取证、不经过 escalate 节点，本用例的断言（escalate_cloud / 云端复核）
    # 在 agent 形态下无意义。故此处显式把形态钉在 deterministic，保持用例原意不变。
    with patch.dict("os.environ", {"AUSCULT_DIAGNOSIS_MODE": "deterministic"}), \
         patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
         patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
         patch.object(build_mod, "get_history", _mock_get_history), \
         patch.object(build_mod, "diagnose", _mock_diagnose), \
         patch.object(cloud, "call_cloud", return_value=_VALID_CLOUD_RESPONSE):
        graph = build_graph(InMemorySaver())
        result = graph.invoke(initial, config=config)
        # 2026-10-22（Must#9）：云端复核结论含「停机/更换」等高风险操作词 → 挂 human_review，
        # 需人工批准才 finalize；本用例关心的是"升级链路已走通"，故补一次 resume。
        if graph.get_state(config).next == ("human_review",):
            from langgraph.types import Command  # noqa: PLC0415

            result = graph.invoke(
                Command(resume={"action": "approved", "reviewer_id": "rev-d14",
                                "comment": "云端复核结论：人工确认"}), config=config)
    assert result.get("report_id", "").startswith("RPT-"), \
        f"report_id 未生成: {result.get('report_id')}"
    assert result.get("escalate_cloud") is True, "escalate_cloud 标记未置位"
    assert "云端复核" in result.get("diagnosis", ""), \
        f"诊断未含云端结论: {result.get('diagnosis')}"
    print(f"[PASS] 图内冒烟（report_id={result['report_id']}）")


def main() -> int:
    tests = [
        ("脱敏 device_id", test_sanitize),
        ("云端成功路径", test_cloud_success),
        ("超时降级", test_cloud_timeout),
        ("不可达降级", test_cloud_unreachable),
        ("JSON 解析失败降级", test_cloud_json_parse_fail),
        ("审计记录写入", test_audit_written),
        ("预算 hook", test_budget_hook),
        ("图内冒烟", test_graph_smoke_escalate),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D14 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
