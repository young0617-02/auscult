"""Must#3（`p95`/`anomaly`）与 Must#5（真实图谱路径）的字段级回归锁（2026-10-22）。

## 背景

- **#3**：Phase 0 判据要求 `query_sensor` 返回「avg/max/min/**p95**/trend + 异常标记 **anomaly**」，
  但 `_compute_stats` 只有 avg/max/min/trend，`query_sensor` 只回 rows/count → 判据与实现差两项。
- **#5**：判据要求 `query_graph` 返回 **≥1 条支撑路径**（含 nodes/relations）。实现里 Cypher 虽然
  `MATCH p = ...` 拿到了路径，却只 `RETURN cid` 把路径丢掉 → 上层 `GraphPath.edges` 恒空，
  所谓"路径"其实是"命中实体 + chunk 归因"。

本文件锁住修复后的字段契约（不依赖 Neo4j/TDengine，全部打桩）。
"""

from __future__ import annotations

from app.graph.nodes.analyze_sensor import _compute_stats
from app.graph.nodes.retrieve_evidence import retrieve_evidence
from app.graph.state import AlarmEvent, DiagnosisState
from app.tools import query_sensor as qs
from scripts import retrieve_graph as rg


# ------------------------------------------------ Must#3：p95 / anomaly

def test_stats_has_p95_with_linear_interpolation():
    """[1..100] 的 P95 = 95.05（线性插值，不是 nearest-rank 的 95）。"""
    st = _compute_stats([float(i) for i in range(1, 101)], threshold=None)
    assert st["p95"] == 95.05


def test_stats_flags_anomaly_when_threshold_exceeded():
    st = _compute_stats([float(i) for i in range(1, 101)], threshold=95.0)
    assert st["exceed_count"] == 5
    assert st["anomaly"] is True
    assert any("超阈值" in r for r in st["anomaly_reasons"])


def test_stats_not_anomaly_when_within_threshold():
    st = _compute_stats([1.0, 2.0, 3.0], threshold=10.0)
    assert st["anomaly"] is False
    assert st["anomaly_reasons"] == []


def test_stats_flags_rising_spike_without_threshold():
    """无阈值时仍能识别"上升 + 尖峰"（峰值 > 1.5×均值）。"""
    st = _compute_stats([1.0] * 10 + [10.0] * 10, threshold=None)
    assert st["trend"] == "rising"
    assert st["anomaly"] is True
    assert any("趋势上升" in r for r in st["anomaly_reasons"])


def test_stats_empty_keeps_field_contract():
    st = _compute_stats([], threshold=4.5)
    assert st["p95"] == 0.0 and st["anomaly"] is False
    assert st["count"] == 0


def test_query_sensor_returns_profile(monkeypatch):
    """工具契约补 `stats`（avg/max/min/p95），否则模型看不到分布。"""
    monkeypatch.setattr(qs, "_td_query",
                        lambda sql, timeout=0.5: {"data": [[1, 4.0], [2, 6.0], [3, 5.0]]})
    out = qs.query_sensor("PUMP-A-01", "vib_rms", 0, 9_999_999_999_999)
    assert out["count"] == 3
    assert out["stats"]["max"] == 6.0
    assert 5.0 <= out["stats"]["p95"] <= 6.0


# ------------------------------------------------ Must#5：真实图谱路径

def test_retrieve_graph_returns_paths(monkeypatch):
    """解析 Cypher 三列（cid / path_nodes / path_rels）→ 输出 `paths`。"""
    monkeypatch.setattr(rg, "extract_route_inputs", lambda rw: {"entities": [{"text": "振动烈度"}]})
    monkeypatch.setattr(rg, "load_retrieval_config",
                        lambda: {"graph": {"max_hops": 2, "top_k_paths": 5}})
    monkeypatch.setattr(rg, "neo4j_run", lambda stmts, *a, **kw: [
        {"data": [{"row": ["c1", ["振动烈度", "1.8"], ["THRESHOLDS"]]},
                  {"row": ["c2", ["泵轴", "轴承箱"], ["HAS_PART", "HAS_FAULT"]]}]}
    ])
    out = rg.retrieve_graph({})
    assert out["degraded"] is False
    assert {h["chunk_id"] for h in out["hits"]} == {"c1", "c2"}
    by_cid = {p["chunk_id"]: p for p in out["paths"]}
    assert by_cid["c1"]["edges"] == ["THRESHOLDS"]
    assert by_cid["c2"]["nodes"] == ["泵轴", "轴承箱"]
    assert by_cid["c2"]["edges"] == ["HAS_PART", "HAS_FAULT"]


def test_retrieve_graph_tolerates_legacy_rows(monkeypatch):
    """旧格式（只有 cid 一列）不应崩，只是没有 paths。"""
    monkeypatch.setattr(rg, "extract_route_inputs", lambda rw: {"entities": [{"text": "泵"}]})
    monkeypatch.setattr(rg, "load_retrieval_config",
                        lambda: {"graph": {"max_hops": 2, "top_k_paths": 5}})
    monkeypatch.setattr(rg, "neo4j_run", lambda stmts, *a, **kw: [{"data": [{"row": ["c9"]}]}])
    out = rg.retrieve_graph({})
    assert out["paths"] == []
    assert out["hits"][0]["chunk_id"] == "c9"


def test_retrieve_evidence_builds_path_with_edges(monkeypatch):
    """`graph_paths` 必须带真实 edges，而不是只有实体簇。"""
    from app.graph.nodes import retrieve_evidence as re_mod

    class _Svc:
        def retrieve(self, question, *, mode=None, cache_key=None):
            return {"degraded": False, "items": [{"chunk_id": "c0", "score": 0.9, "text": "手册"}]}

    monkeypatch.setattr(re_mod, "_get_service", lambda: _Svc())
    monkeypatch.setattr(re_mod, "query_graph", lambda q: {
        "degraded": False,
        "hits": [{"chunk_id": "c1", "score": 2.0}],
        "entities_hit": ["振动烈度"],
        "paths": [{"chunk_id": "c1", "nodes": ["振动烈度", "1.8"], "edges": ["THRESHOLDS"]}],
    })
    state = DiagnosisState(
        thread_id="thr-g",
        alarm=AlarmEvent(device_id="PUMP-A-01", metric="vib_rms", value=6.2, severity="high"),
    )
    out = retrieve_evidence(state)
    paths = out["graph_paths"]
    assert paths, "未产出 graph_paths"
    assert paths[0].edges == ["THRESHOLDS"]
    assert paths[0].nodes == ["振动烈度", "1.8"]
    assert "THRESHOLDS" in paths[0].description
