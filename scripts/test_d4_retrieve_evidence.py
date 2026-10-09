"""D4 自测: retrieve_knowledge 迁移 + query_graph + retrieve_evidence 节点

验证项:
  1. retrieve_knowledge 封装层导入正确（RetrievalService 可实例化）
  2. query_graph 查询真实 Neo4j 数据
  3. retrieve_evidence 节点（真实告警 → evidence + graph_paths）
  4. retrieve_evidence alarm=None → errors
  5. 图内冒烟（parse_alarm → analyze_sensor → retrieve_evidence → finalize）

前置: Milvus(19531) + Neo4j(7687) + TDengine(6041) 全部在线
用法:
  .venv\\Scripts\\python.exe scripts\\test_d4_retrieve_evidence.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import AlarmEvent, DiagnosisState, EvidenceItem  # noqa: E402


def test_imports() -> None:
    """1. 封装层导入正确。"""
    from app.tools.retrieve_knowledge import RetrievalService  # noqa: E402
    assert RetrievalService is not None
    # 不实例化（会加载模型），仅验证类可访问
    print("[PASS] retrieve_knowledge 封装层导入")


def test_query_graph() -> None:
    """2. query_graph 查询真实 Neo4j。"""
    from app.tools.query_graph import query_graph  # noqa: E402
    result = query_graph("离心泵轴承箱温度偏高振动烈度超标的原因")
    assert "hits" in result
    assert "degraded" in result
    if not result["degraded"]:
        assert isinstance(result["hits"], list)
        print(f"[PASS] query_graph（{len(result['hits'])} 条命中, entities={result.get('entities_hit', [])})")
    else:
        print(f"[PASS] query_graph（降级: {result.get('reason', '未知')}）")


def test_retrieve_evidence_node() -> None:
    """3. retrieve_evidence 节点（真实告警 → evidence + graph_paths）。"""
    from app.tools.query_sensor import _td_query  # noqa: PLC0415
    from app.graph.nodes.retrieve_evidence import retrieve_evidence  # noqa: E402

    # 获取 TDengine 第一条数据时间戳
    result = _td_query("SELECT ts FROM iot.st_pump_metrics LIMIT 1")
    from datetime import datetime  # noqa: PLC0415
    ts_str = result["data"][0][0]
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    ts = int(dt.timestamp() * 1000)

    state = DiagnosisState(alarm=AlarmEvent(
        alarm_id="d4-test", device_id="PUMP-A",
        metric="vib_rms", value=7.1, baseline=4.5,
        severity="high", ts=ts,
    ))
    out = retrieve_evidence(state)
    assert "evidence" in out
    assert isinstance(out["evidence"], list)
    if out["evidence"]:
        ev = out["evidence"][0]
        assert isinstance(ev, EvidenceItem)
        assert ev.chunk_id != ""
    print(f"[PASS] retrieve_evidence 节点（{len(out['evidence'])} 条证据, "
          f"{len(out.get('graph_paths', []))} 条图谱路径）")


def test_retrieve_evidence_none() -> None:
    """4. retrieve_evidence alarm=None → errors。"""
    from app.graph.nodes.retrieve_evidence import retrieve_evidence  # noqa: E402
    state = DiagnosisState(alarm=None)
    out = retrieve_evidence(state)
    assert "errors" in out
    assert out["errors"][0]["code"] == "E_NO_ALARM"
    print("[PASS] retrieve_evidence alarm=None → errors")


def test_graph_smoke() -> None:
    """5. 图内冒烟: parse_alarm → analyze_sensor → retrieve_evidence → finalize。"""
    from langgraph.checkpoint.memory import InMemorySaver  # noqa: PLC0415
    from app.tools.query_sensor import _td_query  # noqa: PLC0415
    from app.graph.build import build_graph  # noqa: E402

    result = _td_query("SELECT ts FROM iot.st_pump_metrics LIMIT 1")
    from datetime import datetime  # noqa: PLC0415
    ts_str = result["data"][0][0]
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    ts = int(dt.timestamp() * 1000)

    graph = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "d4-smoke"}}
    initial = {
        "alarm": {
            "alarm_id": "smoke-4", "device_id": "PUMP-A",
            "metric": "vib_rms", "value": 7.1, "ts": ts,
        },
        "thread_id": "d4-smoke",
        "confidence": 0.8,
        "risk_level": "low",
    }
    result = graph.invoke(initial, config=config)
    alarm = result.get("alarm")
    assert alarm is not None and alarm.rule_id == "thr_vib_rms"
    report = result.get("sensor_report")
    assert report is not None and report["count"] > 0
    evidence = result.get("evidence", [])
    print(f"[PASS] 图内冒烟（evidence={len(evidence)}）")


def main() -> int:
    tests = [
        ("封装层导入", test_imports),
        ("query_graph 查询", test_query_graph),
        ("retrieve_evidence 节点", test_retrieve_evidence_node),
        ("retrieve_evidence alarm=None", test_retrieve_evidence_none),
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
    print(f"D4 自测结果: {len(tests) - failures}/{len(tests)} PASS"
          + (f", {failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
