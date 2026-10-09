"""D21 自测：Langfuse Trace 全覆盖

验证项（10 项）：
  1. trace_id 唯一性
  2. with_span 写入 JSONL（name + duration_ms + input）
  3. log_llm 记录 LLM 调用（token + think_pct）
  4. log_tool 记录工具调用（input + output + duration）
  5. log_event 记录自定义事件
  6. span_count 递增
  7. JSONL 文件可读 + 结构正确
  8. 嵌套 span（parent_id 关联）
  9. trace_node 装饰器自动追踪（有/无 Tracer 两种路径）
  10. 图内冒烟：Tracer + graph.invoke 不破坏执行 + trace 文件生成

用法：
  .venv\\Scripts\\python.exe scripts\\test_d21_tracing.py
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.observability.tracing import (  # noqa: E402
    Tracer,
    clear_current_tracer,
    end_trace,
    get_current_tracer,
    new_trace_id,
    set_current_tracer,
    start_trace,
    trace_node,
)


# ---------------------------------------------------------------- 测试

def test_trace_id_unique() -> None:
    """1. trace_id 唯一性。"""
    ids = {new_trace_id() for _ in range(100)}
    assert len(ids) == 100, "100 次 new_trace_id 应全唯一"
    assert all(len(tid) == 16 for tid in ids), "trace_id 应为 16 字符"
    t1 = Tracer()
    t2 = Tracer()
    assert t1.trace_id != t2.trace_id, "不同 Tracer 应有不同 trace_id"
    print(f"[PASS] trace_id 唯一（{t1.trace_id[:8]}…）")


def test_span_write() -> None:
    """2. with_span 写入 JSONL。"""
    tracer = Tracer(trace_id="d21-span-test")
    with tracer.span("parse_alarm", input_summary="PUMP-A vib=7.1"):
        pass
    spans = tracer.filter_by_type("span")
    assert len(spans) == 1
    s = spans[0]
    assert s["name"] == "parse_alarm"
    assert s["duration_ms"] >= 0
    assert s["input"] == "PUMP-A vib=7.1"
    assert s["trace_id"] == "d21-span-test"
    print(f"[PASS] with_span 写入（duration={s['duration_ms']}ms）")


def test_log_llm() -> None:
    """3. log_llm 记录 LLM 调用。"""
    tracer = Tracer(trace_id="d21-llm-test")
    tracer.log_llm("diagnose", "deepseek-r1:7b",
                   input_tokens=500, output_tokens=200,
                   think_tokens=80, duration_ms=3200)
    llms = tracer.filter_by_type("llm")
    assert len(llms) == 1
    r = llms[0]
    assert r["model"] == "deepseek-r1:7b"
    assert r["input_tokens"] == 500
    assert r["output_tokens"] == 200
    assert r["total_tokens"] == 700
    assert r["think_tokens"] == 80
    assert r["think_pct"] == 40.0   # 80/200 * 100
    assert r["duration_ms"] == 3200
    print(f"[PASS] log_llm（tokens={r['total_tokens']}, "
          f"think={r['think_pct']}%）")


def test_log_tool() -> None:
    """4. log_tool 记录工具调用。"""
    tracer = Tracer(trace_id="d21-tool-test")
    tracer.log_tool("query_sensor", {"device_id": "PUMP-A"},
                    {"count": 50, "avg": 6.8}, duration_ms=120)
    tools = tracer.filter_by_type("tool")
    assert len(tools) == 1
    t = tools[0]
    assert t["name"] == "query_sensor"
    assert "PUMP-A" in t["input"]
    assert "count" in t["output"]
    assert t["duration_ms"] == 120
    print(f"[PASS] log_tool（{t['name']}, {t['duration_ms']}ms）")


def test_log_event() -> None:
    """5. log_event 记录自定义事件。"""
    tracer = Tracer(trace_id="d21-event-test")
    tracer.log_event("route", target="human_review", reason="risk=high")
    events = tracer.filter_by_type("event")
    assert len(events) == 1
    e = events[0]
    assert e["name"] == "route"
    assert e["target"] == "human_review"
    print(f"[PASS] log_event（{e['name']} → {e['target']}）")


def test_span_count() -> None:
    """6. span_count 递增。"""
    tracer = Tracer(trace_id="d21-count-test")
    assert tracer.span_count() == 0
    with tracer.span("a"):
        pass
    assert tracer.span_count() == 1
    tracer.log_llm("b", "m")
    assert tracer.span_count() == 2
    tracer.log_tool("c", "in", "out")
    assert tracer.span_count() == 3
    tracer.log_event("d")
    assert tracer.span_count() == 4
    print("[PASS] span_count 递增（0→4）")


def test_jsonl_file_readable() -> None:
    """7. JSONL 文件可读 + 结构正确。"""
    tracer = Tracer(trace_id="d21-file-test")
    file = tracer.file_path()
    if file.exists():
        file.unlink()  # 清理旧残留
    with tracer.span("node1", input_summary="hello"):
        tracer.log_llm("llm1", "model-x",
                       input_tokens=10, output_tokens=20)
    file = tracer.file_path()
    assert file.exists(), f"trace 文件应存在: {file}"
    lines = file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2, f"应有 2 行（span + llm），实际 {len(lines)}"
    for line in lines:
        record = json.loads(line)
        assert record["trace_id"] == "d21-file-test"
        assert "span_id" in record
        assert "type" in record
        assert "ts" in record or "start_ts" in record
    print(f"[PASS] JSONL 可读（{len(lines)} 行，结构正确）")


def test_nested_span() -> None:
    """8. 嵌套 span（parent_id 关联）。"""
    tracer = Tracer(trace_id="d21-nest-test")
    with tracer.span("parent") as parent_id:
        with tracer.span("child1", parent_id=parent_id) as child1_id:
            pass
        with tracer.span("child2", parent_id=parent_id) as child2_id:
            pass
    spans = tracer.filter_by_type("span")
    assert len(spans) == 3
    parent = next(s for s in spans if s["name"] == "parent")
    child1 = next(s for s in spans if s["name"] == "child1")
    child2 = next(s for s in spans if s["name"] == "child2")
    assert child1["parent_id"] == parent["span_id"]
    assert child2["parent_id"] == parent["span_id"]
    assert parent["parent_id"] is None
    print("[PASS] 嵌套 span（parent→child1+child2）")


def test_trace_node_decorator() -> None:
    """9. trace_node 装饰器自动追踪。"""
    # 无 Tracer：直接调用原函数（零降级）
    @trace_node("mock_node")
    def mock_node(state):
        return {"result": "ok"}

    clear_current_tracer()
    assert get_current_tracer() is None
    result = mock_node({"x": 1})
    assert result == {"result": "ok"}, "无 Tracer 应正常返回"

    # 有 Tracer：自动记录 span
    tracer = Tracer(trace_id="d21-decorator-test")
    set_current_tracer(tracer)
    try:
        result = mock_node({"x": 1})
        assert result == {"result": "ok"}
        spans = tracer.filter_by_type("span")
        assert len(spans) == 1
        assert spans[0]["name"] == "mock_node"
        events = tracer.filter_by_type("event")
        assert any(e["name"] == "mock_node.output" for e in events)
    finally:
        clear_current_tracer()
    print("[PASS] trace_node 装饰器（有/无 Tracer 两种路径）")


def test_graph_smoke() -> None:
    """10. 图内冒烟：Tracer + graph.invoke 不破坏执行 + trace 文件生成。"""
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

    tracer = start_trace("d21-graph-smoke")
    try:
        config = {"configurable": {"thread_id": "d21-smoke"}}
        initial = {
            "alarm": {"alarm_id": "smoke-1", "device_id": "PUMP-A-01",
                      "metric": "vib_rms", "value": 7.1, "ts": 0},
            "thread_id": "d21-smoke",
        }
        with tracer.span("graph.invoke", input_summary=initial):
            with patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
                 patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
                 patch.object(build_mod, "get_history", _mock_get_history), \
                 patch.object(build_mod, "diagnose", _mock_diagnose):
                graph = build_graph(InMemorySaver())
                graph.invoke(initial, config=config)
                # 挂起在 human_review
                st = graph.get_state(config)
                assert st.next and "human_review" in st.next
                # resume approved
                result = graph.invoke(
                    Command(resume={"action": "approved",
                                    "comment": "ok",
                                    "reviewer_id": "rev-d21"}),
                    config=config)

        assert result.get("report_id", "").startswith("RPT-")
        # trace 文件应存在且有记录
        assert tracer.span_count() >= 1, \
            f"tracer 应有记录（实际 {tracer.span_count()}）"
        file = tracer.file_path()
        assert file.exists()
        # 验证 JSONL 可读
        lines = file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) >= 1
        for line in lines:
            record = json.loads(line)
            assert record["trace_id"] == "d21-graph-smoke"
        print(f"[PASS] 图内冒烟（{tracer.span_count()} 条 trace，"
              f"report={result['report_id']}）")
    finally:
        end_trace()


# ---------------------------------------------------------------- 主入口

def main() -> int:
    tests = [
        ("trace_id 唯一", test_trace_id_unique),
        ("with_span 写入", test_span_write),
        ("log_llm", test_log_llm),
        ("log_tool", test_log_tool),
        ("log_event", test_log_event),
        ("span_count 递增", test_span_count),
        ("JSONL 可读", test_jsonl_file_readable),
        ("嵌套 span", test_nested_span),
        ("trace_node 装饰器", test_trace_node_decorator),
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
    print(f"D21 自测结果：{total - failures}/{total} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
