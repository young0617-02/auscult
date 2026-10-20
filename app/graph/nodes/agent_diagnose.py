"""agent_diagnose 节点（P7 · Agent 化核心）

LLM 自主工具循环诊断（替代确定性诊断段时可经 AUSCULT_DIAGNOSIS_MODE=agent 切换）：

    parse_alarm → agent_diagnose → [条件路由]（路由契约与 diagnose 完全一致）

循环形态（plan/p0-design-m02-hybrid-form.md 方案④：拆单工具多次调用）：
  1. 每轮把当前 messages + 只读工具面发给 LLM（tools 通道，tool_choice=auto）；
  2. 模型产出 tool_calls → 白名单校验 → 执行 → role=tool 回灌 → 进入下一轮；
  3. 模型不再调用工具 → 解析诊断 JSON → 置信度复合公式 → 路由；
  4. 达到 max_steps（默认 4）仍未收口 → 无工具强制收口轮；
  5. 任一步 LLM 传输失败 → retry_count++ + errors（既有重试/降级路由接管）。

下游契约不变：diagnosis / root_causes / suggestions / confidence /
confidence_breakdown / risk_level + evidence / sensor_report / work_orders /
graph_paths 增量，finalize 的引用校验与人工审核 interrupt 原样生效。
写操作护栏：generate_report 不进工具面，幻觉调用由 tool_registry 拦截
（ADR-007：写操作移出图内）。

预算纪律：后端为 cloud 时，每一轮 LLM 调用都过 BudgetGuard 计数
（一次诊断最多 max_steps+1 次调用，日均容量 = 340 / 调用数，见设计文档 §六）。

对应交付物：docs/p7-design-agent-diagnosis-2026-10-19.md §三/§四。
"""

from __future__ import annotations

import time
from typing import Any

from ...agent.prompt import build_agent_system_prompt
from ...agent.tool_registry import (
    assistant_tool_calls_message,
    execute_tool,
    load_agent_tools,
    tool_result_message,
    tools_json_for_prompt,
)
from ...llm import config as llm_config
from ...llm.client import get_client
from ...observability import prom_metrics as pm
from ..state import DiagnosisState, EvidenceItem, GraphPath, RootCause, Suggestion, WorkOrder

# ---------------------------------------------------------------- 复用 diagnose 既有纯函数
# （think 剥离 / JSON 抽取 / 置信度复合公式 / 风险分级——与确定性路径逐字同口径，
#   保证两种诊断形态的下游契约一致）

from .diagnose import (  # noqa: E402
    _determine_risk_level,
    _extract_json,
    _normalize_cite,
    _strip_think,
    calibrate_confidence,
    compute_confidence,
)

#: 达到步数上限后的强制收口指令（无工具）
_FORCED_FINAL_INSTRUCTION = (
    "工具调用步数已达上限。请停止调用工具，基于已获得的工具结果，"
    "直接输出最终诊断结论 JSON（citations 只能引用工具结果中出现过的 chunk_id，"
    "不得编造）。"
)


class _Collector:
    """把工具结果归集为 LangGraph 状态增量（与确定性节点的产出形状对齐）。"""

    def __init__(self) -> None:
        self.evidence: list[EvidenceItem] = []
        self.graph_paths: list[GraphPath] = []
        self.work_orders: list[WorkOrder] = []
        self.sensor_report: dict | None = None

    def absorb(self, name: str, out: dict[str, Any]) -> None:
        if not out.get("ok"):
            return
        result = out.get("result") or {}
        if name == "query_sensor":
            self._absorb_sensor(result)
        elif name == "search_knowledge":
            for item in result.get("items") or []:
                routes = item.get("routes")
                self.evidence.append(EvidenceItem(
                    chunk_id=str(item.get("chunk_id") or ""),
                    text=str(item.get("text") or ""),
                    score=float(item.get("score") or 0.0),
                    routes=[str(r) for r in routes] if isinstance(routes, list) else [],
                    source_type="knowledge",
                ))
        elif name == "query_graph":
            if result.get("degraded"):
                return
            entities = [str(e) for e in (result.get("entities_hit") or [])]
            for hit in result.get("hits") or []:
                self.evidence.append(EvidenceItem(
                    chunk_id=str(hit.get("chunk_id") or ""),
                    text="",                       # 图谱证据形态同 retrieve_evidence（设计使然）
                    score=float(hit.get("score") or 0.0),
                    routes=["graph"],
                    source_type="graph",
                ))
            if entities:
                self.graph_paths.append(GraphPath(
                    nodes=entities,
                    description=f"图谱命中实体: {', '.join(entities)}",
                ))
        elif name == "get_maintenance_history":
            for wo in result.get("work_orders") or []:
                self.work_orders.append(WorkOrder(
                    order_id=str(wo.get("order_id") or ""),
                    device_id=str(result.get("device_id") or ""),
                    fault=str(wo.get("fault") or ""),
                    action=str(wo.get("action") or ""),
                    result=wo.get("result"),
                    created_at=wo.get("created_at"),
                ))

    def _absorb_sensor(self, result: dict[str, Any]) -> None:
        series = result.get("series") or []
        if not series:
            return
        primary = series[0]
        report: dict[str, Any] = {
            "device_id": result.get("device_id") or primary.get("sensor_id", ""),
            "metric": primary.get("column", ""),
            "raw_count": sum(int(s.get("count") or 0) for s in series),
            "series": series,
        }
        for key in ("count", "avg", "max", "min", "last", "exceed_count",
                    "exceed_duration_ms", "threshold", "trend"):
            if key in primary:
                report[key] = primary[key]
        self.sensor_report = report

    def increments(self) -> dict[str, Any]:
        """状态增量（evidence/graph_paths/work_orders 为追加语义字段）。"""
        out: dict[str, Any] = {}
        if self.evidence:
            out["evidence"] = self.evidence
        if self.graph_paths:
            out["graph_paths"] = self.graph_paths
        if self.work_orders:
            out["work_orders"] = self.work_orders
        if self.sensor_report is not None:
            out["sensor_report"] = self.sensor_report
        return out


def _build_agent_context(alarm: Any) -> str:
    """Agent 用户消息：告警事实 + 任务指令。"""
    if alarm is None:
        return "【任务】无告警信息，请说明信息不足，不要调用任何工具。"
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(alarm.ts / 1000)) \
        if alarm.ts else "未知"
    parts = [
        f"【告警】设备={alarm.device_id or '（未提供）'} 测点={alarm.metric} "
        f"当前值={alarm.value} 阈值={alarm.baseline} 严重度={alarm.severity} 时间={ts_iso}",
    ]
    if not alarm.device_id:
        parts.append("【注意】告警未提供具体设备编号，按拒绝规则 6a 处理："
                     "说明需要补充的信息，不要调用任何工具。")
        return "\n".join(parts)
    parts.append("【任务】请基于以上告警自主规划工具调用完成取证"
                 "（传感器时序 / 知识库 / 图谱 / 历史工单），然后输出诊断结论 JSON。")
    return "\n".join(parts)


def _finalize_answer(state: DiagnosisState, content: str,
                     collector: _Collector, steps: list[dict]) -> dict[str, Any]:
    """无工具调用的回复 → 诊断结论（与 diagnose 节点同口径）。"""
    clean = _strip_think(content or "")
    parsed = _extract_json(clean)
    increments = collector.increments()

    if parsed is None:
        # 与 diagnose E_JSON_PARSE 同口径：正文前 500 字作诊断，retry_count++ 供路由重试
        return {"diagnosis": clean[:500],
                "retry_count": state.retry_count + 1,
                "agent_steps": steps,
                "errors": [{"node": "agent_diagnose", "code": "E_JSON_PARSE",
                            "msg": "Agent 输出诊断 JSON 解析失败"}],
                **increments}

    root_causes = [
        RootCause(cause=str(rc.get("cause") or ""),
                  citations=[_normalize_cite(c) for c in rc.get("citations") or []],
                  confidence_hint=float(rc.get("confidence_hint") or 0.0))
        for rc in parsed.get("root_causes") or []
    ]
    suggestions = [
        Suggestion(action=str(s.get("action") or ""),
                   citations=[_normalize_cite(c) for c in s.get("citations") or []],
                   risk=str(s.get("risk") or "low"))
        for s in parsed.get("suggestions") or []
    ]
    self_conf = float(parsed.get("self_confidence") or 0.5)

    # 置信度复合公式需要「本次取证后的状态」——用 model_copy 合并增量后计算
    # （不写回 state，仅作计算输入；LangGraph 合并由返回值完成）
    merged = state.model_copy(update={
        "evidence": list(state.evidence) + collector.evidence,
        "graph_paths": list(state.graph_paths) + collector.graph_paths,
        "sensor_report": collector.sensor_report or state.sensor_report,
    })
    raw_conf, breakdown = compute_confidence(merged, self_conf)
    confidence = calibrate_confidence(raw_conf)
    risk = _determine_risk_level(state.alarm.severity if state.alarm else "medium",
                                 confidence)

    return {
        "diagnosis": str(parsed.get("diagnosis") or ""),
        "root_causes": root_causes,
        "suggestions": suggestions,
        "confidence": confidence,
        "confidence_breakdown": breakdown,
        "risk_level": risk,
        "agent_steps": steps,
        **increments,
    }


def _llm_failure(state: DiagnosisState, exc: Exception,
                 collector: _Collector, steps: list[dict]) -> dict[str, Any]:
    """LLM 传输失败 → 与 diagnose 节点同契约（retry_count++，路由接管重试/降级）。"""
    if isinstance(exc, (TimeoutError, ConnectionError)):
        code = "E_LLM_UNREACHABLE"
    else:
        code = "E_LLM_ERROR"
    # 客户端异常消息已自含上下文（超时秒数/端点），直接透传不重复包装
    return {"retry_count": state.retry_count + 1,
            "agent_steps": steps,
            "errors": [{"node": "agent_diagnose", "code": code, "msg": str(exc)}],
            **collector.increments()}


def agent_diagnose(state: DiagnosisState) -> dict[str, Any]:
    """Agent 循环诊断节点（AUSCULT_DIAGNOSIS_MODE=agent 时替代 diagnose）。

    输入: state（至少含 alarm；agent 模式下证据由本节点自主取证）
    输出: 同 diagnose 的诊断契约 + agent_steps 轨迹
    降级: LLM 不可达/超时/配置缺失 → retry_count++ + errors（路由重试 ≤3 后降级）
    """
    alarm = state.alarm
    if alarm is None:
        return {"errors": [{"node": "agent_diagnose", "code": "E_NO_ALARM",
                            "msg": "缺少告警事件"}]}

    try:
        client = get_client(role=llm_config.ROLE_AGENT)
    except RuntimeError as exc:
        # 云端配置缺失等：按 E_LLM_ERROR 走重试/降级（不静默）
        return {"retry_count": state.retry_count + 1,
                "errors": [{"node": "agent_diagnose", "code": "E_LLM_CONFIG",
                            "msg": str(exc)}]}

    backend = llm_config.llm_backend()
    max_steps = llm_config.agent_max_steps()
    # 角色化超时：agent 角色默认 90s（云端 tools 通道实测单轮 5.5–23s，2026-10-20）
    timeout = llm_config.llm_timeout(llm_config.ROLE_AGENT)
    budget = None
    if backend == "cloud":
        from ...router.budget import BudgetGuard            # noqa: PLC0415
        budget = BudgetGuard()

    tools = load_agent_tools()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_agent_system_prompt(tools_json_for_prompt())},
        {"role": "user", "content": _build_agent_context(alarm)},
    ]

    collector = _Collector()
    steps: list[dict] = []

    for step in range(1, max_steps + 1):
        # 预算熔断（仅 cloud 后端；本地无云端成本）
        if budget is not None:
            ok, count, limit, reason = budget.check()
            if not ok:
                return {"degrade_reason": "budget_exceeded",
                        "retry_count": state.retry_count + 1,
                        "agent_steps": steps,
                        "errors": [{"node": "agent_diagnose",
                                    "code": "E_BUDGET_EXCEEDED",
                                    "msg": f"云端预算熔断（{count}/{limit}）：{reason}"}],
                        **collector.increments()}

        started = time.perf_counter()
        try:
            result = client.chat(messages, tools=tools, timeout=timeout)
        except (TimeoutError, ConnectionError, RuntimeError) as exc:
            return _llm_failure(state, exc, collector, steps)
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        if budget is not None:
            budget.increment()      # 仅成功调用计费（失败不计，同 escalate 口径）

        if result.tool_calls:
            messages.append(assistant_tool_calls_message(result.content,
                                                          result.tool_calls))
            for call in result.tool_calls:
                out = execute_tool(call.name, call.arguments,
                                   alarm=alarm, thread_id=state.thread_id)
                collector.absorb(call.name, out)
                pm.inc_tool_call(call.name, "ok" if out.get("ok") else "error")
                messages.append(tool_result_message(call.id, call.name, out))
                steps.append({"step": step, "tool": call.name,
                              "ok": bool(out.get("ok")),
                              "args_keys": sorted(call.arguments),
                              "latency_ms": latency_ms})
            continue

        # 无工具调用 → 收口
        return _finalize_answer(state, result.content, collector, steps)

    # 达到步数上限：无工具强制收口轮
    messages.append({"role": "user", "content": _FORCED_FINAL_INSTRUCTION})
    try:
        result = client.chat(messages, tools=None, timeout=timeout)
    except (TimeoutError, ConnectionError, RuntimeError) as exc:
        return _llm_failure(state, exc, collector, steps)
    steps.append({"step": max_steps + 1, "tool": None, "ok": True,
                  "args_keys": [], "latency_ms": None, "forced_final": True})
    return _finalize_answer(state, result.content, collector, steps)
