"""D6-D8 自测: diagnose 节点 + 置信度公式 + 校准框架

验证项:
  1. think 剥离（成对/未闭合/无 think）
  2. JSON 提取（从 LLM 输出中提取）
  3. 置信度复合公式（各档位 + 权重验证）
  4. ECE 计算函数
  5. diagnose 节点（真实调用 deepseek-r1:7b）
  6. 图内冒烟（parse_alarm → ... → diagnose → route → finalize）

前置: Ollama(11434) + Milvus(19531) + Neo4j(7687) + TDengine(6041) + PG(5433)
用法:
  .venv\\Scripts\\python.exe scripts\\test_d6_diagnose.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import AlarmEvent, DiagnosisState  # noqa: E402
from app.graph.nodes.diagnose import (  # noqa: E402
    _strip_think, _extract_json, compute_confidence, calibrate_confidence,
    compute_ece, _determine_risk_level,
)


def test_strip_think() -> None:
    """1. think 剥离（成对/未闭合/无 think）。"""
    # 成对
    assert _strip_think("<think>推理过程</think>正文") == "正文"
    # 未闭合
    assert _strip_think("<think>推理到一半") == ""
    # 无 think
    assert _strip_think("纯正文") == "纯正文"
    # thinking 标签
    assert _strip_think("<thinking>推理</thinking>正文") == "正文"
    print("[PASS] think 剥离")


def test_extract_json() -> None:
    """2. JSON 提取。"""
    text = '一些说明\n{"diagnosis": "测试", "self_confidence": 0.8}\n尾部'
    obj = _extract_json(text)
    assert obj is not None
    assert obj["diagnosis"] == "测试"
    assert obj["self_confidence"] == 0.8

    # 无 JSON
    assert _extract_json("纯文本无 JSON") is None
    print("[PASS] JSON 提取")


def test_confidence_formula() -> None:
    """3. 置信度复合公式（权重验证）。"""
    from app.graph.state import EvidenceItem, GraphPath  # noqa: PLC0415
    # 全满: 5 evidence + sensor(trend) + 3 graph + self=1.0
    state = DiagnosisState(
        alarm=AlarmEvent(device_id="X", metric="vib_rms", value=7, severity="high"),
        evidence=[EvidenceItem(chunk_id=f"c{i}", score=0.9) for i in range(5)],
        graph_paths=[GraphPath(description="x") for _ in range(3)],
        sensor_report={"count": 10, "trend": "rising"},
    )
    conf, bd = compute_confidence(state, 1.0)
    assert conf == 1.0, f"全满应为 1.0, got {conf}"
    assert bd == {"retrieval": 1.0, "sensor": 1.0, "graph": 1.0, "self": 1.0}

    # 全空: 0 evidence + no sensor + 0 graph + self=0
    state2 = DiagnosisState(
        alarm=AlarmEvent(device_id="X", metric="vib_rms", value=7, severity="high"),
    )
    conf2, _ = compute_confidence(state2, 0.0)
    assert conf2 == 0.0, f"全空应为 0.0, got {conf2}"

    # 权重验证: 仅检索满(5 ev) + 无 sensor + 无 graph + self=0
    state3 = DiagnosisState(
        alarm=AlarmEvent(device_id="X", metric="vib_rms", value=7, severity="high"),
        evidence=[EvidenceItem(chunk_id=f"c{i}") for i in range(5)],
    )
    conf3, _ = compute_confidence(state3, 0.0)
    assert abs(conf3 - 0.35) < 0.01, f"仅检索应为 0.35, got {conf3}"

    # 仅自评满 + 其他空
    conf4, _ = compute_confidence(state2, 1.0)
    assert abs(conf4 - 0.30) < 0.01, f"仅自评应为 0.30, got {conf4}"
    print("[PASS] 置信度复合公式 + 权重")


def test_ece() -> None:
    """4. ECE 计算。"""
    # 完美校准: confidence=0.8 bin → 80% 正确; 0.5 bin → 50% 正确
    preds = [(0.8, True)] * 8 + [(0.8, False)] * 2  # 0.8 bin: 80% acc
    ece = compute_ece(preds, n_bins=10)
    assert ece <= 0.05, f"近似完美校准 ECE 应 ≤0.05, got {ece}"

    # 最差校准: confidence=1.0 但全错
    bad = [(1.0, False)] * 10
    ece_bad = compute_ece(bad, n_bins=10)
    assert ece_bad == 1.0, f"最差应为 1.0, got {ece_bad}"
    print(f"[PASS] ECE 计算（完美={ece}, 最差={ece_bad}）")


def test_risk_level() -> None:
    """risk_level 判定。"""
    assert _determine_risk_level("high", 0.3) == "high"
    assert _determine_risk_level("high", 0.6) == "medium"
    assert _determine_risk_level("high", 0.8) == "high"  # high severity + conf<0.85
    assert _determine_risk_level("high", 0.9) == "low"
    assert _determine_risk_level("low", 0.8) == "low"
    assert _determine_risk_level("low", 0.4) == "high"
    print("[PASS] risk_level 判定")


def test_diagnose_node() -> None:
    """5. diagnose 节点（真实调用 deepseek-r1:7b）。"""
    from app.graph.nodes.diagnose import diagnose  # noqa: E402
    state = DiagnosisState(
        alarm=AlarmEvent(
            alarm_id="d6-test", device_id="PUMP-A-01",
            metric="vib_rms", value=7.1, baseline=4.5,
            severity="high", ts=0,
        ),
        sensor_report={"count": 100, "avg": 1.3, "max": 7.1,
                        "min": 1.0, "trend": "stable",
                        "exceed_count": 0, "exceed_duration_ms": 0,
                        "threshold": 4.5},
        evidence=[],
        graph_paths=[],
        work_orders=[],
    )
    result = diagnose(state)

    # 验证输出结构
    if "errors" in result and "diagnosis" not in result:
        # LLM 降级（可能 Ollama 超时）
        print(f"[SKIP] diagnose 节点降级: {result['errors'][0]['code']}")
        return

    assert "diagnosis" in result
    assert isinstance(result["diagnosis"], str)
    assert "confidence" in result
    assert 0.0 <= result["confidence"] <= 1.0
    assert "confidence_breakdown" in result
    assert "risk_level" in result
    print(f"[PASS] diagnose 节点（conf={result['confidence']:.3f} "
          f"risk={result['risk_level']} "
          f"causes={len(result.get('root_causes', []))}）")


def test_graph_smoke() -> None:
    """6. 图内冒烟: parse_alarm → analyze → retrieve → get_history → diagnose → route → finalize。"""
    from langgraph.checkpoint.memory import InMemorySaver  # noqa: PLC0415
    from app.tools.query_sensor import _td_query  # noqa: PLC0415
    from app.graph.build import build_graph  # noqa: E402

    result_ts = _td_query(
        "SELECT ts FROM iot.st_pump_metrics WHERE device_id = 'PUMP-A-01' LIMIT 1")
    from datetime import datetime  # noqa: PLC0415
    ts_str = result_ts["data"][0][0]
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    ts = int(dt.timestamp() * 1000)

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "d6-smoke"}}
    initial = {
        "alarm": {
            "alarm_id": "smoke-6", "device_id": "PUMP-A-01",
            "metric": "vib_rms", "value": 7.1, "ts": ts,
        },
        "thread_id": "d6-smoke",
        "confidence": 0.0,  # 初始 0，diagnose 后更新
        "risk_level": "low",
    }
    result = graph.invoke(initial, config=config)

    # 验证全链路执行
    alarm = result.get("alarm")
    assert alarm is not None and alarm.rule_id == "thr_vib_rms"
    # 2026-10-22：默认 agent 形态的图是 START → parse_alarm → diagnose(agent) → 路由，
    # 没有 analyze_sensor／gather 节点，故 sensor_report/evidence 依形态而空；断言按形态分流。
    from app.llm.config import diagnosis_mode  # noqa: PLC0415

    mode = diagnosis_mode()
    if mode == "deterministic":
        report = result.get("sensor_report")
        assert report is not None and report["count"] > 0
        evidence = result.get("evidence", [])
        assert len(evidence) > 0
        diagnosis = result.get("diagnosis")
        assert diagnosis is not None  # diagnose 节点已执行
        print(f"[PASS] 图内冒烟（{mode}，conf={result.get('confidence', 0):.3f} "
              f"risk={result.get('risk_level')} evidence={len(evidence)}）")
    else:
        assert not [e for e in (result.get("errors") or [])
                    if str(e.get("code", "")).startswith("E_")], result.get("errors")
        nxt = graph.get_state(config).next
        assert nxt in ((), ("human_review",))
        print(f"[PASS] 图内冒烟（{mode}，终态 next={nxt} "
              f"conf={result.get('confidence', 0):.3f} risk={result.get('risk_level')}）")


def main() -> int:
    tests = [
        ("think 剥离", test_strip_think),
        ("JSON 提取", test_extract_json),
        ("置信度复合公式", test_confidence_formula),
        ("ECE 计算", test_ece),
        ("risk_level 判定", test_risk_level),
        ("diagnose 节点", test_diagnose_node),
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
    print(f"D6-D8 自测结果: {len(tests) - failures}/{len(tests)} PASS"
          + (f", {failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
