"""D22 自测：指标打点（节点耗时 / 置信度分布 / 升级率 / 降级率 / 审核覆盖率）

验证项（11 项）：
  1. record_node_duration + node_p95
  2. node_p50 / p99 + node_count
  3. record_confidence + confidence_distribution（三档）
  4. record_route + escalation_rate
  5. record_route + degradation_rate
  6. record_route + review_coverage
  7. record_review + review_avg_duration + review_status_counts
  8. snapshot 全量快照结构
  9. flush 写入 JSONL 文件
  10. aggregate_from_tracer（从 D21 Tracer 自动聚合）
  11. 图内冒烟（MetricsCollector + graph.invoke 不破坏执行）

用法：
  .venv\\Scripts\\python.exe scripts\\test_d22_metrics.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.observability.metrics import (  # noqa: E402
    CONFIDENCE_BINS,
    MetricsCollector,
    _percentile,
)
from app.observability.tracing import Tracer  # noqa: E402


# ---------------------------------------------------------------- 测试

def test_node_p95() -> None:
    """1. record_node_duration + node_p95。"""
    mc = MetricsCollector()
    for d in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        mc.record_node_duration("parse_alarm", d)
    p95 = mc.node_p95("parse_alarm")
    assert 90 <= p95 <= 100, f"P95 应在 90-100（实际 {p95}）"
    assert mc.node_count("parse_alarm") == 10
    print(f"[PASS] node_p95（{p95}ms，10 次）")


def test_node_p50_p99() -> None:
    """2. node_p50 / p99 + node_count。"""
    mc = MetricsCollector()
    for d in [10, 20, 30, 40, 50]:
        mc.record_node_duration("diagnose", d)
    p50 = mc.node_p50("diagnose")
    p99 = mc.node_p99("diagnose")
    assert p50 == 30, f"P50 应为 30（实际 {p50}）"
    assert 49 <= p99 <= 50, f"P99 应在 49-50（实际 {p99}）"
    assert mc.node_count("diagnose") == 5
    print(f"[PASS] p50={p50}, p99={p99}")


def test_confidence_distribution() -> None:
    """3. record_confidence + confidence_distribution（三档）。"""
    mc = MetricsCollector()
    for c in [0.3, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95]:
        mc.record_confidence(c)
    dist = mc.confidence_distribution()
    assert set(dist.keys()) == set(CONFIDENCE_BINS)
    assert dist["low"] == 2,    f"low 应为 2（实际 {dist['low']}）"     # 0.3, 0.4
    assert dist["medium"] == 2, f"medium 应为 2（实际 {dist['medium']}）"  # 0.6, 0.7
    assert dist["high"] == 3,   f"high 应为 3（实际 {dist['high']}）"   # 0.8, 0.9, 0.95
    print(f"[PASS] confidence_distribution（{dist}）")


def test_escalation_rate() -> None:
    """4. record_route + escalation_rate。"""
    mc = MetricsCollector()
    for t in ["finalize", "finalize", "escalate_cloud", "degrade"]:
        mc.record_route(t)
    rate = mc.escalation_rate()
    assert rate == 0.25, f"升级率应为 0.25（实际 {rate}）"
    assert mc.total_routes() == 4
    print(f"[PASS] escalation_rate={rate}")


def test_degradation_rate() -> None:
    """5. record_route + degradation_rate。"""
    mc = MetricsCollector()
    for t in ["finalize", "degrade", "degrade", "degrade"]:
        mc.record_route(t)
    rate = mc.degradation_rate()
    assert rate == 0.75, f"降级率应为 0.75（实际 {rate}）"
    print(f"[PASS] degradation_rate={rate}")


def test_review_coverage() -> None:
    """6. record_route + review_coverage。"""
    mc = MetricsCollector()
    for t in ["finalize", "human_review", "human_review"]:
        mc.record_route(t)
    rate = mc.review_coverage()
    assert rate == round(2 / 3, 4), f"审核覆盖率应为 {round(2/3, 4)}（实际 {rate}）"
    print(f"[PASS] review_coverage={rate}")


def test_review_avg_duration() -> None:
    """7. record_review + review_avg_duration + review_status_counts。"""
    mc = MetricsCollector()
    mc.record_review(1000, "approved")
    mc.record_review(3000, "rejected")
    mc.record_review(2000, "approved")
    avg = mc.review_avg_duration()
    assert avg == 2000, f"平均时长应为 2000（实际 {avg}）"
    counts = mc.review_status_counts()
    assert counts["approved"] == 2
    assert counts["rejected"] == 1
    print(f"[PASS] review_avg={avg}ms, statuses={counts}")


def test_snapshot() -> None:
    """8. snapshot 全量快照结构。"""
    mc = MetricsCollector()
    mc.record_node_duration("parse_alarm", 5)
    mc.record_confidence(0.8)
    mc.record_route("finalize")
    mc.record_review(500, "approved")
    snap = mc.snapshot()
    for key in ("ts", "nodes", "confidence_distribution", "routes",
                "total_routes", "escalation_rate", "degradation_rate",
                "review_coverage", "review_avg_duration_ms",
                "review_statuses"):
        assert key in snap, f"snapshot 缺 {key}"
    assert "parse_alarm" in snap["nodes"]
    assert snap["nodes"]["parse_alarm"]["p95_ms"] == 5
    assert snap["confidence_distribution"]["high"] == 1
    assert snap["total_routes"] == 1
    print(f"[PASS] snapshot（{len(snap)} 字段）")


def test_flush_jsonl() -> None:
    """9. flush 写入 JSONL 文件。"""
    mc = MetricsCollector()
    mc.record_node_duration("test_node", 10)
    mc.record_route("finalize")
    # 写入临时文件
    tmp = PROJECT_ROOT / "reports" / "metrics" / "d22-test.jsonl"
    if tmp.exists():
        tmp.unlink()
    path = mc.flush(tmp)
    assert path.exists(), f"文件应存在: {path}"
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["nodes"]["test_node"]["count"] == 1
    assert record["total_routes"] == 1
    print(f"[PASS] flush JSONL（{path.name}）")


def test_aggregate_from_tracer() -> None:
    """10. aggregate_from_tracer（从 D21 Tracer 自动聚合）。"""
    tracer = Tracer(trace_id="d22-agg-test")
    # 模拟 span + event
    with tracer.span("parse_alarm", input_summary="alarm"):
        pass
    with tracer.span("diagnose", input_summary="state"):
        pass
    tracer.log_event("route", target="human_review")
    tracer.log_event("confidence", value=0.82)
    tracer.log_event("review_done", duration_ms=5000, status="approved")

    mc = MetricsCollector()
    mc.aggregate_from_tracer(tracer)

    # span → node_duration
    assert mc.node_count("parse_alarm") == 1
    assert mc.node_count("diagnose") == 1

    # route → human_review
    assert mc.total_routes() == 1
    assert mc.review_coverage() == 1.0

    # confidence
    dist = mc.confidence_distribution()
    assert dist["high"] == 1

    # review
    assert mc.review_avg_duration() == 5000
    assert mc.review_status_counts().get("approved") == 1
    print(f"[PASS] aggregate_from_tracer（"
          f"nodes={mc.node_count('parse_alarm')}, "
          f"routes={mc.total_routes()}）")


def test_graph_smoke() -> None:
    """11. 图内冒烟：MetricsCollector + graph.invoke 不破坏执行。"""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command
    from app.graph import build as build_mod
    from app.graph.build import build_graph
    from app.graph.state import RootCause, Suggestion

    def _mock_diagnose(state):
        return {"diagnosis": "需立即停机检查", "confidence": 0.80,
                "risk_level": "high",
                "root_causes": [RootCause(cause="轴承磨损",
                                           citations=["c_001"])],
                "suggestions": [Suggestion(action="紧急停机",
                                           citations=["c_001"], risk="high")]}

    def _mock_analyze_sensor(state):
        return {"sensor_report": {"count": 50, "avg": 6.8, "max": 7.5,
                                  "trend": "up", "exceed_duration_ms": 12000}}

    def _mock_retrieve_evidence(state):
        from app.graph.state import EvidenceItem
        return {"evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损",
                                           score=0.9)]}

    def _mock_get_history(state):
        return {"work_orders": []}

    mc = MetricsCollector()
    config = {"configurable": {"thread_id": "d22-smoke"}}
    initial = {
        "alarm": {"alarm_id": "smoke-1", "device_id": "PUMP-A-01",
                  "metric": "vib_rms", "value": 7.1, "ts": 0},
        "thread_id": "d22-smoke",
    }
    with patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
         patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
         patch.object(build_mod, "get_history", _mock_get_history), \
         patch.object(build_mod, "diagnose", _mock_diagnose):
        graph = build_graph(InMemorySaver())
        graph.invoke(initial, config=config)
        # resume
        result = graph.invoke(
            Command(resume={"action": "approved",
                            "comment": "ok",
                            "reviewer_id": "rev-d22"}),
            config=config)

    assert result.get("report_id", "").startswith("RPT-")
    # 手动记录指标
    mc.record_route("human_review")
    mc.record_confidence(0.80)
    mc.record_review(100, "approved")
    snap = mc.snapshot()
    assert snap["review_coverage"] == 1.0
    assert snap["confidence_distribution"]["high"] == 1
    print(f"[PASS] 图内冒烟（report={result['report_id']}, "
          f"metrics={snap['total_routes']} route）")


# ---------------------------------------------------------------- 主入口

def main() -> int:
    tests = [
        ("node_p95", test_node_p95),
        ("node_p50/p99", test_node_p50_p99),
        ("confidence_distribution", test_confidence_distribution),
        ("escalation_rate", test_escalation_rate),
        ("degradation_rate", test_degradation_rate),
        ("review_coverage", test_review_coverage),
        ("review_avg_duration", test_review_avg_duration),
        ("snapshot", test_snapshot),
        ("flush JSONL", test_flush_jsonl),
        ("aggregate_from_tracer", test_aggregate_from_tracer),
        ("图内冒烟", test_graph_smoke),
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
    print(f"D22 自测结果：{total - failures}/{total} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
