"""retrieve_evidence 节点（D4）

并行调用 retrieve_knowledge + query_graph，合并证据到 state。
推荐配置: device="cuda", use_rerank=False（D7 消融最优，P95=86ms）

降级: 任一路失败 → degraded 标记 + errors（不中断图执行）。

对应交付物: plan/Phase 3 §三.2 / §五 D4
"""

from __future__ import annotations

import time
from typing import Any

from ...observability import prom_metrics as pm
from ...tools.query_graph import query_graph
from ...tools.retrieve_knowledge import RetrievalService
from ..state import DiagnosisState, EvidenceItem, GraphPath

# 常驻单例（惰性初始化，跨调用复用 embedder/reranker）
_retrieval_svc: RetrievalService | None = None


def _get_service() -> RetrievalService:
    """惰性初始化 RetrievalService（D7 最优: cuda + no-rerank）。"""
    global _retrieval_svc
    if _retrieval_svc is None:
        _retrieval_svc = RetrievalService(device="cuda", use_rerank=False)
    return _retrieval_svc


def _build_question(alarm) -> str:
    """从告警事件构造检索问题。"""
    metric_map = {
        "vib_rms": "振动烈度",
        "vib_peak": "振动峰值",
        "bearing_temp": "轴承温度",
        "motor_current": "电机电流",
    }
    metric_cn = metric_map.get(alarm.metric, alarm.metric)
    return (
        f"{alarm.device_id} {metric_cn}值 {alarm.value} "
        f"超阈值 {alarm.baseline} 的故障原因"
    )


def retrieve_evidence(state: DiagnosisState) -> dict[str, Any]:
    """并行调用 retrieve_knowledge + query_graph，合并证据。

    输入: state.alarm（含 device_id/metric/value/baseline）
    输出: {"evidence": [EvidenceItem], "graph_paths": [GraphPath]}
          降级时追加 {"errors": [...]}
    """
    alarm = state.alarm
    if alarm is None:
        return {"errors": [{"node": "retrieve_evidence", "code": "E_NO_ALARM",
                            "msg": "缺少告警事件"}]}

    question = _build_question(alarm)

    evidence_items: list[EvidenceItem] = []
    graph_paths: list[GraphPath] = []
    errors: list[dict] = []

    # 1) retrieve_knowledge（W1→W5 全链路）
    try:
        svc = _get_service()
        t0 = time.perf_counter()
        result = svc.retrieve(question)
        pm.observe_retrieval("total", (time.perf_counter() - t0) * 1000)
        items = result.get("items", [])
        pm.inc_tool_call("retrieve_knowledge", "ok" if items else "empty")
        for item in items:
            evidence_items.append(EvidenceItem(
                chunk_id=item.get("chunk_id", ""),
                text=item.get("text", ""),
                score=item.get("score", 0.0),
                routes=item.get("routes", []),
                source_type="knowledge",
            ))
    except Exception as exc:  # noqa: BLE001 - 降级不中断
        pm.inc_tool_call("retrieve_knowledge", "error")
        errors.append({"node": "retrieve_evidence", "code": "E_RETRIEVE_FAIL",
                        "msg": f"retrieve_knowledge 失败: {exc}"})

    # 2) query_graph（Neo4j ≤2 跳，独立证据通道不进 RRF）
    try:
        graph_result = query_graph(question)
        if not graph_result.get("degraded"):
            hits = graph_result.get("hits", [])
            pm.inc_tool_call("query_graph", "ok" if hits else "empty")
            for hit in hits:
                evidence_items.append(EvidenceItem(
                    chunk_id=hit.get("chunk_id", ""),
                    text="",
                    score=hit.get("score", 0.0),
                    routes=["graph"],
                    source_type="graph",
                ))
            entities_hit = graph_result.get("entities_hit", [])
            if entities_hit:
                graph_paths.append(GraphPath(
                    nodes=entities_hit,
                    description=f"图谱命中实体: {', '.join(entities_hit)}",
                ))
        else:
            pm.inc_tool_call("query_graph", "empty")
            reason = graph_result.get("reason", "未知")
            errors.append({"node": "retrieve_evidence", "code": "E_GRAPH_DEGRADED",
                           "msg": f"图谱召回降级: {reason}"})
    except Exception as exc:  # noqa: BLE001
        pm.inc_tool_call("query_graph", "error")
        errors.append({"node": "retrieve_evidence", "code": "E_GRAPH_FAIL",
                        "msg": f"query_graph 失败: {exc}"})

    result_dict: dict[str, Any] = {
        "evidence": evidence_items,
        "graph_paths": graph_paths,
    }
    if errors:
        result_dict["errors"] = errors
    return result_dict
