"""D19 自测：幂等写入 + 写操作移出图内

验证项：
  1. compute_idempotency_key 与 finalize 同口径
  2. compute_report_id 格式 RPT-<16hex>
  3. state_to_payload 结构完整
  4. generate_report 新建 → is_new=True
  5. generate_report 幂等 → is_new=False（相同 key 返回既有 report_id）
  6. get_report 按 report_id 查询
  7. report_exists 幂等键检查
  8. 不同 thread_id → 不同 report_id
  9. 图外写入验证：finalize 不写 PG（report_id 在 state，PG 无记录直到 generate_report）

用法：
  .venv\\Scripts\\python.exe scripts\\test_d19_idempotency.py
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import EvidenceItem, RootCause, Suggestion  # noqa: E402
from app.graph.nodes.finalize import _compute_idempotency_key  # noqa: E402
from app.report.idempotency import (  # noqa: E402
    compute_idempotency_key,
    compute_report_id,
    generate_report,
    get_report,
    report_exists,
    state_to_payload,
)


# ---------------------------------------------------------------- 辅助

def _make_state_dict(thread_id="d19-test", risk="low",
                     citations=None, confidence=0.85):
    root_causes = [RootCause(cause="轴承磨损",
                             citations=citations or ["c_001", "c_002"])]
    return {
        "thread_id": thread_id,
        "risk_level": risk,
        "confidence": confidence,
        "diagnosis": "轴承磨损导致振动超标",
        "root_causes": root_causes,
        "suggestions": [Suggestion(action="检查润滑",
                                   citations=["c_002"])],
        "evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损特征频谱：外圈故障频率突出",
                                  score=0.92, source_type="knowledge",
                                  routes=["dense", "sparse"])],
        "confidence_breakdown": {"retrieval": 0.8, "sensor": 0.5,
                                 "graph": 1.0, "self": 0.75},
        "escalate_cloud": False,
        "human_review": None,
        "degrade_reason": None,
        "errors": [],
    }


# ---------------------------------------------------------------- 测试

def test_key_consistency() -> None:
    """1. compute_idempotency_key 与 finalize 同口径。"""
    state = _make_state_dict()
    citations = ["c_001", "c_002"]
    key_mine = compute_idempotency_key("d19-test", citations, "low")
    # finalize 的 _compute_idempotency_key 接收 DiagnosisState
    from app.graph.state import AlarmEvent, DiagnosisState
    ds = DiagnosisState(
        alarm=AlarmEvent(alarm_id="a", device_id="d", metric="vib_rms", ts=0),
        thread_id="d19-test", risk_level="low",
        root_causes=[RootCause(cause="x", citations=citations)],
    )
    key_finalize = _compute_idempotency_key(ds)
    assert key_mine == key_finalize, \
        f"幂等键不一致: mine={key_mine}, finalize={key_finalize}"
    print(f"[PASS] 幂等键一致（{key_mine}）")


def test_report_id_format() -> None:
    """2. report_id 格式。"""
    key = compute_idempotency_key("t1", ["c1"], "low")
    rid = compute_report_id(key)
    assert rid.startswith("RPT-"), f"应以 RPT- 开头: {rid}"
    assert len(rid) == 20, f"应为 20 字符: {rid}"
    print(f"[PASS] report_id 格式（{rid}）")


def test_payload_structure() -> None:
    """3. payload 结构（含 P5-Q8 evidence 原文 + confidence_breakdown）。"""
    state = _make_state_dict()
    payload = state_to_payload(state)
    for key in ("diagnosis", "root_causes", "suggestions", "confidence",
                "confidence_breakdown", "evidence",
                "risk_level", "escalate_cloud", "human_review",
                "degrade_reason", "errors"):
        assert key in payload, f"payload 缺 {key}"
    assert payload["root_causes"][0]["cause"] == "轴承磨损"
    # P5-Q8：证据原文逐字段
    ev = payload["evidence"][0]
    assert ev["chunk_id"] == "c_001"
    assert "轴承磨损特征频谱" in ev["text"]
    assert ev["score"] == 0.92
    assert ev["source_type"] == "knowledge"
    assert ev["routes"] == ["dense", "sparse"]
    # P5-Q8：四分量 breakdown
    bd = payload["confidence_breakdown"]
    assert bd == {"retrieval": 0.8, "sensor": 0.5, "graph": 1.0, "self": 0.75}
    print("[PASS] payload 结构（含 evidence 原文 + confidence_breakdown）")


def test_generate_new() -> None:
    """4. 新建报告 → is_new=True（thread_id 加 uuid 保证可重复运行）。"""
    state = _make_state_dict(thread_id=f"d19-new-{uuid.uuid4().hex[:8]}")
    result = generate_report(state)
    assert result["is_new"] is True, "应为新建"
    assert result["report_id"].startswith("RPT-")
    print(f"[PASS] 新建（{result['report_id']}）")


def test_generate_idempotent() -> None:
    """5. 幂等：相同 key → is_new=False（同一 state 调两次）。"""
    state = _make_state_dict(thread_id=f"d19-idem-{uuid.uuid4().hex[:8]}")
    first = generate_report(state)
    second = generate_report(state)
    assert first["report_id"] == second["report_id"], "幂等应返回相同 report_id"
    assert second["is_new"] is False, "重复应 is_new=False"
    print(f"[PASS] 幂等（{second['report_id']}）")


def test_get_report() -> None:
    """6. 按 report_id 查询。"""
    state = _make_state_dict(thread_id=f"d19-get-{uuid.uuid4().hex[:8]}")
    result = generate_report(state)
    fetched = get_report(result["report_id"])
    assert fetched is not None, "应能查到"
    assert fetched["report_id"] == result["report_id"]
    assert fetched["risk_level"] == "low"
    print(f"[PASS] get_report（{fetched['report_id']}）")


def test_report_exists() -> None:
    """7. report_exists 检查。"""
    state = _make_state_dict(thread_id=f"d19-exists-{uuid.uuid4().hex[:8]}")
    result = generate_report(state)
    assert report_exists(result["idempotency_key"]) is True
    assert report_exists("nonexistent_key") is False
    print("[PASS] report_exists")


def test_different_thread() -> None:
    """8. 不同 thread_id → 不同 report_id。"""
    s1 = _make_state_dict(thread_id="d19-a")
    s2 = _make_state_dict(thread_id="d19-b")
    r1 = generate_report(s1)
    r2 = generate_report(s2)
    assert r1["report_id"] != r2["report_id"], "不同 thread 应有不同 report_id"
    print(f"[PASS] 不同 thread_id → 不同 report_id")


def test_graph_external_write() -> None:
    """9. 图外写入验证：finalize 不写 PG。

    运行图（mock 中间节点）到 finalize，验证：
    - finalize 生成了 report_id
    - 但 PG 中无该 report（直到调用 generate_report）
    """
    from langgraph.checkpoint.memory import InMemorySaver
    from app.graph.state import AlarmEvent, DiagnosisState, EvidenceItem
    from app.graph import build as build_mod
    from app.graph.build import build_graph

    def _mock_diagnose(state):
        return {"diagnosis": "正常", "confidence": 0.85,
                "risk_level": "low",
                "root_causes": [RootCause(cause="x", citations=["c_001"])],
                "suggestions": [Suggestion(action="检查")]}

    def _mock_analyze_sensor(state):
        return {"sensor_report": {"count": 10, "avg": 5, "max": 6,
                                  "trend": "stable", "exceed_duration_ms": 0}}

    def _mock_retrieve_evidence(state):
        return {"evidence": [EvidenceItem(chunk_id="c_001", text="x", score=0.9)]}

    def _mock_get_history(state):
        return {"work_orders": []}

    tid = f"d19-external-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": tid}}
    initial = {
        "alarm": {"alarm_id": "e1", "device_id": "PUMP-A",
                  "metric": "vib_rms", "value": 5.0, "ts": 0},
        "thread_id": tid,
    }
    with patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
         patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
         patch.object(build_mod, "get_history", _mock_get_history), \
         patch.object(build_mod, "diagnose", _mock_diagnose):
        graph = build_graph(InMemorySaver())
        result = graph.invoke(initial, config=config)

    # finalize 生成了 report_id
    assert result.get("report_id", "").startswith("RPT-"), \
        "finalize 应生成 report_id"
    # 但 PG 中不应有该记录（图内不写 PG）
    assert not report_exists(result["report_id"].replace("RPT-", "")), \
        "图内 finalize 不应写 PG"
    # 图外写入
    write_result = generate_report(result)
    assert write_result["is_new"] is True
    assert report_exists(write_result["idempotency_key"])
    print(f"[PASS] 图外写入（finalize 生成={result['report_id']}，"
          f"写入后={write_result['report_id']}）")


def main() -> int:
    tests = [
        ("幂等键一致", test_key_consistency),
        ("report_id 格式", test_report_id_format),
        ("payload 结构", test_payload_structure),
        ("新建报告", test_generate_new),
        ("幂等重复", test_generate_idempotent),
        ("get_report", test_get_report),
        ("report_exists", test_report_exists),
        ("不同 thread_id", test_different_thread),
        ("图外写入验证", test_graph_external_write),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D19 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
