"""StateGraph 骨架（六节点 + 条件路由）

对应交付物：plan/Phase 3 §三.1–§三.3
D1 产出：骨架可编译 + Checkpointer 可连接 PG
节点为占位实现，D2–D5 逐步替换为真实逻辑：
  D2: parse_alarm（确定性规则解析）
  D3: analyze_sensor（接入 query_sensor）
  D4: retrieve_evidence（接入 retrieve_knowledge + query_graph）
  D5: get_history（接入 get_maintenance_history）
  D6–D8: diagnose（接入 deepseek-r1:7b + 根因/建议抽取）
  P7: diagnose 槽位可按 AUSCULT_DIAGNOSIS_MODE 切换两种实现——
       deterministic（默认，固定编排+单次 LLM 诊断，证据由 gather 节点采集）
       agent（Agent 循环，LLM 自主调工具取证，证据由循环内工具结果归集）；
       两种实现下游契约完全一致（ diagnosis/root_causes/suggestions/confidence/
       risk_level + 条件路由），切换不影响审核/幂等/降级链路。
       详见 docs/p7-design-agent-diagnosis-2026-10-19.md。

条件路由（plan §3.3，严格优先级，首个命中生效）：
  0. diagnose 失败（diagnosis=None）且 0 < retry_count < 3 → 自循环重试 diagnose
     （2026-10-14 修复：否则首次 LLM 失败即被「confidence<0.50」命中 degrade，
       retry_count≥3 护栏对该路径不生效）
  1. retry_count ≥ 3 → degrade
  2. confidence < 0.50 → degrade
  3. confidence < 0.75 → escalate_cloud；云端失败 → degrade
  4. risk_level == "high" → human_review（interrupt）
  5. else → finalize
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ..llm import config as llm_config
from ..observability.tracing import trace_node
from .state import DiagnosisState
from .nodes.parse_alarm import parse_alarm
from .nodes.analyze_sensor import analyze_sensor
from .nodes.retrieve_evidence import retrieve_evidence
from .nodes.get_history import get_history
from .nodes.diagnose import diagnose
from .nodes.agent_diagnose import agent_diagnose
from .nodes.escalate_cloud import escalate_cloud
from .nodes.review import human_review
from .nodes.finalize import finalize


# ---------------------------------------------------------------- 条件路由

def _route_condition(state: DiagnosisState) -> str:
    """严格优先级，首个命中生效（plan §3.3）。返回下一节点名。"""
    # diagnose 因 LLM 不可达/错误失败（diagnosis 仍为 None）且未达重试上限
    # → 自循环重试 diagnose。背景（2026-10-14 修复）：confidence 初始为 0.0，
    # 若无此分支，首次 LLM 失败即被下面「confidence < 0.50」命中 degrade，
    # 「retry_count ≥ 3」的护栏对该路径永远不生效 —— 偶发超时直接降级、零重试。
    # E_JSON_PARSE 路径 diagnosis 非空（取原文前 500 字），故不会进入本分支。
    if 0 < state.retry_count < 3 and state.diagnosis is None:
        return "diagnose"
    if state.retry_count >= 3:
        return "degrade"
    if state.confidence < 0.50:
        return "degrade"
    if state.confidence < 0.75:
        return "escalate_cloud"
    if state.risk_level == "high":
        return "human_review"
    return "finalize"


# ---------------------------------------------------------------- 占位节点（parse_alarm 已在 D2 实现于 nodes/parse_alarm.py）


def degrade(state: DiagnosisState) -> dict[str, Any]:
    """降级：输出初步判断，标注降级原因。"""
    reason = state.degrade_reason or "低置信度或重试超限"
    return {"degrade_reason": reason}


# human_review 已实现于 nodes/review.py（D16）


# ---------------------------------------------------------------- 图组装

def build_graph(checkpointer: Any) -> Any:
    """组装 StateGraph 并 compile。

    图结构（plan §3.1）：
        START → parse_alarm → analyze_sensor → retrieve_evidence
              → get_history → diagnose → [条件路由]
                                              ├→ degrade → finalize
                                              ├→ escalate_cloud → finalize
                                              ├→ human_review → finalize
                                              └→ finalize
                                                                  → END

    P7 agent 模式（AUSCULT_DIAGNOSIS_MODE=agent）：
        START → parse_alarm → diagnose(agent_diagnose) → [条件路由]
        证据由 Agent 循环自主取证（gather 节点不接入边，仍注册以便测试打桩）。
    """
    mode = llm_config.diagnosis_mode()
    diag_impl = agent_diagnose if mode == "agent" else diagnose

    graph = StateGraph(DiagnosisState)

    # 注册节点（P4 接入：trace_node 包裹，无 Tracer 时零开销降级——p3-handover-p4 §三 遗留项）
    graph.add_node("parse_alarm", trace_node("parse_alarm")(parse_alarm))
    graph.add_node("analyze_sensor", trace_node("analyze_sensor")(analyze_sensor))
    graph.add_node("retrieve_evidence", trace_node("retrieve_evidence")(retrieve_evidence))
    graph.add_node("get_history", trace_node("get_history")(get_history))
    graph.add_node("diagnose", trace_node("diagnose")(diag_impl))
    graph.add_node("degrade", trace_node("degrade")(degrade))
    graph.add_node("escalate_cloud", trace_node("escalate_cloud")(escalate_cloud))
    graph.add_node("human_review", trace_node("human_review")(human_review))
    graph.add_node("finalize", trace_node("finalize")(finalize))

    # 线性边
    graph.add_edge(START, "parse_alarm")
    if mode == "agent":
        # Agent 模式：证据由 diagnose 槽位内的 Agent 循环自主取证，跳过 gather 链
        graph.add_edge("parse_alarm", "diagnose")
    else:
        graph.add_edge("parse_alarm", "analyze_sensor")
        graph.add_edge("analyze_sensor", "retrieve_evidence")
        graph.add_edge("retrieve_evidence", "get_history")
        graph.add_edge("get_history", "diagnose")

    # 条件路由（diagnose 后按优先级分流）
    graph.add_conditional_edges("diagnose", _route_condition)

    # 汇聚到 finalize
    graph.add_edge("degrade", "finalize")
    graph.add_edge("escalate_cloud", "finalize")
    graph.add_edge("human_review", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
