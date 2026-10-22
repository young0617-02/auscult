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
       agent（**默认**，2026-10-21 所有者裁决；Agent 循环，LLM 自主调工具取证，
              证据由循环内工具结果归集）
       deterministic（固定编排+单次 LLM 诊断，证据由 gather 节点采集；现为**回退通道**）；
       两种实现下游契约完全一致（ diagnosis/root_causes/suggestions/confidence/
       risk_level + 条件路由），切换不影响审核/幂等/降级链路。
       详见 docs/p7-design-agent-diagnosis-2026-10-19.md。

条件路由（plan §3.3，严格优先级，首个命中生效）：
  -1. 合规拒答/澄清（state.refusal 非空）→ finalize
      （P7 · 2026-10-21：提示词规则 6a/6b 要求「只回文字」，这不是失败；
       置 confidence=0.0 会误命中下面的 degrade，故必须优先短路）
  0. diagnose 失败（diagnosis=None）且 0 < retry_count < 3 → 自循环重试 diagnose
     （2026-10-14 修复：否则首次 LLM 失败即被「confidence<0.50」命中 degrade，
       retry_count≥3 护栏对该路径不生效）
  1. retry_count ≥ 3 → degrade
  2. confidence < 0.50 → degrade
  3. confidence < 0.75 → escalate_cloud；云端失败 → degrade
  3.5 needs_human（模型主动求助，E4）→ human_review（risk 已强制 high，先于 confidence 判定）
  3.6 参数被拒 ≥2（local）或步数用尽未收敛（E5）→ escalate_cloud（失败信号前移）
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

#: 参数/白名单拦截的提前兜底阈值（2026-10-22 · 外部评审增量 E2）：
#: 模型对领域语义的系统性偏差**最早**体现在参数被 `validate_tool_args` 拒绝，
#: 而不是等 `confidence` 一路掉到 0.75 —— 后者要再烧几轮无效工具调用与云端额度。
_REJECTION_ESCALATE_THRESHOLD = 2


def _should_fallback_to_cloud(state: DiagnosisState) -> bool:
    """本地主通道失败（重试耗尽且无结论）→ 是否升级云端兜底。

    2026-10-21 核查发现的架构缺口：`retry_count >= 3` 原直接把状态送 `degrade`，
    而本地 Ollama 不可达/超时时诊断**永远**不会尝试云端 —— 即「云端降为兜底」
    只在「置信度不足」维度成立，在「本地模型故障」维度不成立。
    四个前置条件（任一不满足即维持既有 degrade 语义）：
      1. `AUSCULT_CLOUD_FALLBACK` 未关闭（纯离线开发可关）；
      2. 当前后端是 `local`（后端即云端时 escalate 会空转跳过，走了也无意义）；
      3. 本次流程尚未升级过（`escalate_cloud` 为假，避免二次计费/环回）；
      4. `diagnosis is None`（确认是 LLM 失败；`E_JSON_PARSE` 路径 diagnosis 非空）。
    """
    return (llm_config.cloud_fallback_enabled()
            and llm_config.llm_backend() == "local"
            and not state.escalate_cloud
            and state.diagnosis is None)


def _should_early_escalate(state: DiagnosisState) -> bool:
    """参数/白名单被拒达阈值 → 提前升级云端（评审增量 E2，2026-10-22）。

    触发条件（全部满足）：
      1. `AUSCULT_CLOUD_FALLBACK` 未关闭（与"本地失败兜底"共用开关）；
      2. 当前后端是 `local`（后端即云端时 escalate 空转，且会形成自我触发）；
      3. 本次流程尚未升级过（`escalate_cloud` 为假）；
      4. `state.tool_arg_rejections >= 2`（仅统计 whitelist/arg 两类，
         写操作护栏是**正确行为**，不计入 —— 见 `agent_diagnose` 主循环注释）。
    """
    return (llm_config.cloud_fallback_enabled()
            and llm_config.llm_backend() == "local"
            and not state.escalate_cloud
            and state.tool_arg_rejections >= _REJECTION_ESCALATE_THRESHOLD)


def _should_escalate_not_converged(state: DiagnosisState) -> bool:
    """步数用尽仍未收敛（评审增量 E5，2026-10-22）→ 提前升级云端。

    与 E2 同型：`forced_final`（模型烧完 max_steps 还在调工具、被无工具截停）是比
    confidence 更早的"未收敛"信号——结论是拖出来的，不是收敛出来的。护栏口径与
    E2 完全一致（开关 / local 后端 / 未升级过），云端侧凭 E1 的本地轨迹做二次裁决。
    """
    return (llm_config.cloud_fallback_enabled()
            and llm_config.llm_backend() == "local"
            and not state.escalate_cloud
            and state.not_converged)


def _route_condition(state: DiagnosisState) -> str:
    """严格优先级，首个命中生效（plan §3.3）。返回下一节点名。"""
    # P7 · 2026-10-21：合规拒答/澄清（提示词规则 6a 缺 device_id、6b 越界请求）
    # 是**正确行为**而非失败 —— agent_diagnose 已在零工具调用 + 非 JSON 时置
    # state.refusal 且不自增 retry_count。此处必须最先短路，否则 confidence=0.0
    # 会被下面「confidence < 0.50」命中 degrade，白走降级链并污染指标。
    if state.refusal:
        return "finalize"
    # diagnose 因 LLM 不可达/错误失败（diagnosis 仍为 None）且未达重试上限
    # → 自循环重试 diagnose。背景（2026-10-14 修复）：confidence 初始为 0.0，
    # 若无此分支，首次 LLM 失败即被下面「confidence < 0.50」命中 degrade，
    # 「retry_count ≥ 3」的护栏对该路径永远不生效 —— 偶发超时直接降级、零重试。
    # E_JSON_PARSE 路径 diagnosis 非空（取原文前 500 字），故不会进入本分支。
    if 0 < state.retry_count < 3 and state.diagnosis is None:
        return "diagnose"
    if state.retry_count >= 3:
        # 本地重试耗尽仍无结论 → 云端兜底一次（2026-10-21，架构完整性）
        if _should_fallback_to_cloud(state):
            return "escalate_cloud"
        return "degrade"
    # E4（2026-10-22）：模型主动求助 → 直接人工审核（risk 已强制 high）。
    # 放在 confidence 判定**之前**：求助语义是「结论需人定夺」，不是因为置信度低；
    # 否则会被 escalate_cloud/degrade 吞掉，interrupt 永远走不到。
    if state.needs_human:
        return "human_review"
    # 评审增量 E2（2026-10-22）：参数/白名单被拒 ≥2 次 = 模型对当前任务域存在
    # 系统性理解偏差（如设备号口径不认、测点名不存在）——这是比 confidence 更早
    # 的失败信号，提前升级云端，别等它再烧几轮无效调用把置信度磨下去。
    # 评审增量 E5（2026-10-22）：步数用尽未收敛（not_converged）同理。
    if _should_early_escalate(state) or _should_escalate_not_converged(state):
        return "escalate_cloud"
    # 2026-10-22（Must#9 绕过路径①）：**高风险优先于置信度分流**。
    # 原顺序下 `high + confidence<0.50` 直接走 `degrade`，报告照样落库但
    # `review_status=NULL` 且不在 `waiting_review` 态 —— 既不审核、也永远无法补审，
    # 与"高风险审核覆盖率 100%"直接矛盾。已有先例：E4 的 `needs_human` 同样前置。
    if state.risk_level == "high":
        return "human_review"
    if state.confidence < 0.50:
        return "degrade"
    if state.confidence < 0.75:
        return "escalate_cloud"
    return "finalize"


def _route_after_cloud(state: DiagnosisState) -> str:
    """云端升级后的分流（2026-10-22 修复 Must#9 绕过路径②）。

    原实现 `escalate_cloud → finalize` **直连**：云端回来的结论即使 `risk=high` 也不经审核，
    等于"换个后端就能绕过强制审核"。

    故意**不复用** `_route_condition`：那里的 escalate 分支以 `not state.escalate_cloud`
    为前提，复用会形成升级环回/二次计费。此处只做"升级后收口"：

    - 拒答 → 直接定稿（产出是"无法作答"，无结论可审）
    - 高风险 / 主动求助 → **补人工审核**
    - 云端仍低置信（<0.50）→ 降级为初步判断
    - 其余 → 定稿
    """
    if state.refusal:
        return "finalize"
    if state.risk_level == "high" or state.needs_human:
        return "human_review"
    if state.confidence < 0.50:
        return "degrade"
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

    # 汇聚到 finalize（云端升级后需二次分流，见 `_route_after_cloud`）
    graph.add_edge("degrade", "finalize")
    graph.add_conditional_edges("escalate_cloud", _route_after_cloud)
    graph.add_edge("human_review", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
