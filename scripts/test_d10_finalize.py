"""D10 自测: finalize 节点（证据校验 + 幂等键）

验证项:
  1. 正常诊断 → report_id 生成 + 无 warnings
  2. 空诊断 → W_NO_DIAGNOSIS warning
  3. 无效引用 → W_INVALID_CITATION warning
  4. 幂等性: 相同输入 → 相同 report_id
  5. 图内全链路冒烟（PG Checkpointer）

用法:
  .venv\\Scripts\\python.exe scripts\\test_d10_finalize.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import (  # noqa: E402
    AlarmEvent, DiagnosisState, EvidenceItem, RootCause, Suggestion,
)
from app.graph.nodes.finalize import finalize, _compute_idempotency_key  # noqa: E402


def test_normal() -> None:
    """1. 正常诊断 → report_id + 无 warnings。"""
    state = DiagnosisState(
        alarm=AlarmEvent(device_id="PUMP-A", metric="vib_rms", value=7.1, severity="high"),
        thread_id="t1",
        diagnosis="轴承磨损导致振动超标",
        evidence=[EvidenceItem(chunk_id="c1"), EvidenceItem(chunk_id="c2")],
        root_causes=[RootCause(cause="磨损", citations=["c1", "c2"])],
        suggestions=[Suggestion(action="更换轴承", citations=["c1"])],
        confidence=0.82,
        risk_level="low",
    )
    result = finalize(state)
    assert result["report_id"].startswith("RPT-")
    assert "errors" not in result  # 无 warnings
    print(f"[PASS] 正常诊断（report_id={result['report_id']}）")


def test_empty_diagnosis() -> None:
    """2. 空诊断 → W_NO_DIAGNOSIS。"""
    state = DiagnosisState(
        thread_id="t2",
        diagnosis=None,
        confidence=0.3,
        risk_level="high",
    )
    result = finalize(state)
    assert result["report_id"] is None           # 2026-10-22：空诊断 + 零引用 → 阻断定稿
    assert result["blocked"] is True
    codes = [e["code"] for e in result["errors"]]
    assert "W_NO_DIAGNOSIS" in codes
    assert "E_NO_CITATION" in codes
    print("[PASS] 空诊断 + 零引用 → 阻断（W_NO_DIAGNOSIS + E_NO_CITATION）")


def test_invalid_citation() -> None:
    """3. 无效引用 → W_INVALID_CITATION。"""
    state = DiagnosisState(
        thread_id="t3",
        diagnosis="测试",
        evidence=[EvidenceItem(chunk_id="c1")],
        root_causes=[RootCause(cause="原因", citations=["c1", "BAD_ID"])],
        confidence=0.7,
        risk_level="medium",
    )
    result = finalize(state)
    assert result["report_id"] is None           # 2026-10-14 起 E_ 级即阻断；本断言 2026-10-22 同步
    codes = [e["code"] for e in result.get("errors", [])]
    assert "E_INVALID_CITATION" in codes
    print("[PASS] 无效引用 → 阻断（E_INVALID_CITATION）")


def test_idempotency() -> None:
    """4. 幂等性: 相同输入 → 相同 report_id。"""
    base = DiagnosisState(
        thread_id="t4",
        diagnosis="测试",
        evidence=[EvidenceItem(chunk_id="c1"), EvidenceItem(chunk_id="c2")],
        root_causes=[RootCause(cause="A", citations=["c2", "c1"])],  # 顺序无关
        confidence=0.8,
        risk_level="low",
    )
    key1 = _compute_idempotency_key(base)
    key2 = _compute_idempotency_key(base)
    assert key1 == key2, "相同输入应产生相同幂等键"

    # 不同 thread → 不同 key
    other = base.model_copy(update={"thread_id": "t5"})
    key3 = _compute_idempotency_key(other)
    assert key1 != key3, "不同 thread 应产生不同幂等键"

    # 不同 risk → 不同 key
    other2 = base.model_copy(update={"risk_level": "high"})
    key4 = _compute_idempotency_key(other2)
    assert key1 != key4, "不同 risk 应产生不同幂等键"
    print(f"[PASS] 幂等性（key={key1}）")


def test_graph_smoke() -> None:
    """5. 图内全链路冒烟（PG Checkpointer 落盘 + report_id 生成）。"""
    from app.graph.checkpointer import build_checkpointer  # noqa: PLC0415
    from app.tools.query_sensor import _td_query  # noqa: PLC0415
    from app.graph.build import build_graph  # noqa: E402

    # 2026-10-22：设备号统一规范编号（TDengine TAG 已迁移），取首 ts 必须带设备过滤
    result_ts = _td_query(
        "SELECT ts FROM iot.st_pump_metrics WHERE device_id = 'PUMP-A-01' LIMIT 1")
    from datetime import datetime  # noqa: PLC0415
    ts_str = result_ts["data"][0][0]
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    ts = int(dt.timestamp() * 1000)

    config = {"configurable": {"thread_id": "d10-smoke"}}
    initial = {
        "alarm": {
            "alarm_id": "smoke-10", "device_id": "PUMP-A-01",
            "metric": "vib_rms", "value": 7.1, "severity": "low", "ts": ts,
        },
        "thread_id": "d10-smoke",
        "confidence": 0.0,
        "risk_level": "low",
    }
    with build_checkpointer() as saver:
        graph = build_graph(saver)
        result = graph.invoke(initial, config=config)

        # 2026-10-22（Must#9）：真实诊断走 agent 形态，若模型判定 risk=high/主动求助，
        # 图会挂在 human_review；本用例考的是 finalize 出报告，故按审核语义补一次 resume。
        if "human_review" in (graph.get_state(config).next or ()):
            from langgraph.types import Command  # noqa: PLC0415

            result = graph.invoke(
                Command(resume={"action": "approved", "reviewer_id": "rev-d10",
                                "comment": "集成冒烟：人工确认"}), config=config)

        report_id = result.get("report_id")
        assert report_id is not None and report_id.startswith("RPT-")
        assert result.get("diagnosis") is not None
        assert result.get("confidence", 0) > 0
        snapshot = graph.get_state(config)
        assert snapshot is not None

    print(f"[PASS] 图内全链路冒烟（report_id={report_id} "
          f"conf={result['confidence']:.3f} risk={result['risk_level']}）")


def main() -> int:
    tests = [
        ("正常诊断", test_normal),
        ("空诊断 → warning", test_empty_diagnosis),
        ("无效引用 → warning", test_invalid_citation),
        ("幂等性", test_idempotency),
        ("图内全链路冒烟", test_graph_smoke),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D10 自测结果: {len(tests) - failures}/{len(tests)} PASS"
          + (f", {failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
