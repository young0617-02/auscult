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

预算纪律：后端为 cloud 时，每一轮 LLM 调用**发起前**都经 BudgetGuard.reserve()
占位计数（ISS-054 先增后调）；单轮超时/连接错误**轮内重试 1 次**（ISS-059），
故一次诊断的云端调用数上限 = (max_steps+1) × 2，日均容量按此折算。

出网脱敏（U1-D1/D2，`docs/p7-review-u1-sanitization-scope-2026-10-21.md`）：
messages 中设备编号一律为 `设备#<sha256[:6]>`（工具执行前还原、结果回灌前再掩码），
工单 `result` 字段不出网 —— 与 `router/cloud.sanitize_state` 同一口径。

对应交付物：docs/p7-design-agent-diagnosis-2026-10-19.md §三/§四。
"""

from __future__ import annotations

import copy
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
from ...router.cloud import hash_device_id
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


# ---------------------------------------------------------------- 出网脱敏（U1-D1/D2）
# 依据：docs/p7-review-u1-sanitization-scope-2026-10-21.md

def _replace_ids(obj: Any, src: str, dst: str) -> Any:
    """递归把 payload 中出现的 `src` 子串替换为 `dst`（dict / list / str）。"""
    if not src:
        return obj
    if isinstance(obj, str):
        return obj.replace(src, dst)
    if isinstance(obj, list):
        return [_replace_ids(x, src, dst) for x in obj]
    if isinstance(obj, dict):
        return {k: _replace_ids(v, src, dst) for k, v in obj.items()}
    return obj


def _outbound_payload(name: str, out: dict[str, Any], device_id: str,
                      token: str) -> dict[str, Any]:
    """工具结果 → 回灌云端 messages 的安全副本（U1-D1/D2）。

    - **D1**：真实设备编号（`result.device_id` / `series[].sensor_id` /
      `entities_hit` 等任意字符串位置）→ `设备#<sha256[:6]>`，与兜底路径
      `cloud._hash_device_id` 同算法；
    - **D2**：工单 `result`（现场处置描述，可能含人名/工位/工艺）**不出网**，
      与 `sanitize_state` 只保留 `fault`/`action` 的口径对齐。

    **2026-10-21 口径变更（合规以本地部署为准）**：`token` 为空串即「本次不出网
    或已豁免脱敏」（`llm_config.sanitize_outbound()` 为假）——此时 D1/D2 均不生效，
    回灌的就是原始结果。本地后端下模型看得到真实设备号，结论质量更好。
    内部状态归集始终用原始 `out`（下游契约不变）。
    """
    if not token:
        return copy.deepcopy(out)
    safe = copy.deepcopy(out)
    if name == "get_maintenance_history" and safe.get("ok"):
        for wo in (safe.get("result") or {}).get("work_orders") or []:
            wo.pop("result", None)
    return _replace_ids(safe, device_id, token)


def _inbound_arguments(args: dict[str, Any], device_id: str,
                       token: str) -> dict[str, Any]:
    """模型给的参数（设备标识为脱敏代号）→ 真实参数（仅进程内使用，不回灌模型）。"""
    return _replace_ids(args or {}, token, device_id)


def _budget_blocked(state: DiagnosisState, count: int, limit: int, reason: str,
                    collector: _Collector, steps: list[dict]) -> dict[str, Any]:
    """预算熔断的统一返回体（先增后调后，熔断时已回滚不占额度）。"""
    return {"degrade_reason": "budget_exceeded",
            "retry_count": state.retry_count + 1,
            "agent_steps": steps,
            "errors": [{"node": "agent_diagnose", "code": "E_BUDGET_EXCEEDED",
                        "msg": f"云端预算熔断（{count}/{limit}）：{reason}"}],
            **collector.increments()}


def _call_llm(client: Any, messages: list[dict], *, tools: Any, timeout: float,
              budget: Any, state: DiagnosisState, collector: _Collector,
              steps: list[dict]) -> tuple[Any, dict[str, Any] | None]:
    """单轮 LLM 调用：**先增后调**（ISS-054）+ **超时/连接错误轮内重试 1 次**（ISS-059）。

    返回 `(result, failure)`：
      - 成功 → `(ChatResult, None)`
      - 预算熔断 / 两次都失败 → `(None, 节点返回 dict)`
    `RuntimeError`（配置缺失 / HTTP 4xx-5xx）不重试，保持既有语义；
    每次**真实发起**的调用都先 `reserve()` 占位（重试同样计费）。
    """
    last_exc: Exception | None = None
    for attempt in (1, 2):
        if budget is not None:
            ok, count, limit, reason = budget.reserve()
            if not ok:
                return None, _budget_blocked(state, count, limit, reason,
                                             collector, steps)
        try:
            return client.chat(messages, tools=tools, timeout=timeout), None
        except (TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt == 2:
                break
        except RuntimeError as exc:
            return None, _llm_failure(state, exc, collector, steps)
    return None, _llm_failure(state, last_exc, collector, steps)


def _build_agent_context(alarm: Any, device_token: str = "") -> str:
    """Agent 用户消息：告警事实 + 任务指令（设备编号出网前已脱敏，U1-D1）。"""
    if alarm is None:
        return "【任务】无告警信息，请说明信息不足，不要调用任何工具。"
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(alarm.ts / 1000)) \
        if alarm.ts else "未知"
    shown = device_token or alarm.device_id or "（未提供）"
    parts = [
        f"【告警】设备={shown} 测点={alarm.metric} "
        f"当前值={alarm.value} 阈值={alarm.baseline} 严重度={alarm.severity} 时间={ts_iso}",
    ]
    if not alarm.device_id:
        parts.append("【注意】告警未提供具体设备编号，按拒绝规则 6a 处理："
                     "说明需要补充的信息，不要调用任何工具。")
        return "\n".join(parts)
    if device_token:
        parts.append(f"【说明】设备标识已脱敏为 `{device_token}`：调用工具时 device_id / "
                     f"start_node 等参数请**原样使用该标识**，执行时由系统还原。")
    parts.append("【任务】请基于以上告警自主规划工具调用完成取证"
                 "（传感器时序 / 知识库 / 图谱 / 历史工单），然后输出诊断结论 JSON。")
    return "\n".join(parts)


#: 拒答/澄清语气词（仅在「零工具调用 + 无 JSON」时参与判定，避免误伤正常诊断文本）
_REFUSAL_PATTERNS = (
    "无法预测", "无法判断", "无法提供", "无法回答", "不能预测", "不能提供",
    "剩余寿命", "预测寿命", "使用寿命",
    "删除", "篡改", "修改数据", "写入",
    "现场", "派人", "操作设备", "停机",
    "超出", "不在职责", "无权", "没有权限",
    "需要提供", "请补充", "请提供", "信息不足",
)


def _classify_refusal(state: DiagnosisState, clean: str,
                      steps: list[dict]) -> dict[str, Any] | None:
    """判定「零工具调用 + 非 JSON」的自然语言回复是否属**合规拒答/澄清**（规则 6a/6b）。

    背景（2026-10-21）：此前这类回复一律落 `E_JSON_PARSE` + `retry_count++`，语义错位——
    拒答是提示词明确要求的**正确行为**，却被当成解析失败并浪费一次云端重试。

    判定条件（保守，宁可判失败也不吞真错误）：
      - `clarification`：告警缺 `device_id`（规则 6a，上下文已明示"不要调用工具"）；
      - `refusal`：零工具调用 且 文本命中越界/拒答语气词；
      - 其余（有工具调用 / 非拒答语气）→ None，保持原 `E_JSON_PARSE` 行为。
    """
    if not clean.strip():
        return None
    if not (state.alarm and (state.alarm.device_id or "").strip()):
        return {"kind": "clarification",
                "reason": "告警未提供具体设备编号（规则 6a），需补充设备信息"}
    if steps:                      # 已经取过证 → 不是拒答场景，按解析失败处理
        return None
    hit = [p for p in _REFUSAL_PATTERNS if p in clean]
    if hit:
        return {"kind": "refusal",
                "reason": f"超出只读/职责边界或需补充信息（命中：{'、'.join(hit[:3])}）"}
    return None


def _restore_device(text: str, state: DiagnosisState, token: str) -> str:
    """把模型复述的脱敏代号还原为真实设备编号（2026-10-21）。

    背景：出网时 `PUMP-A → 设备#f6de90`，模型会在结论里照抄代号，于是
    `reports.payload.diagnosis` 出现 `设备#f6de90 振动速度…`（已实证，2026-10-21）。
    报告是**本地产物**（不出网），故落库前还原为真实编号；无代号时原样返回。
    """
    if not token:
        return text
    real = (state.alarm.device_id if state.alarm else "") or ""
    return text.replace(token, real) if real else text


def _finalize_answer(state: DiagnosisState, content: str,
                     collector: _Collector, steps: list[dict],
                     token: str = "") -> dict[str, Any]:
    """无工具调用的回复 → 诊断结论（与 diagnose 节点同口径）。

    `token` 非空表示本次出网用了脱敏代号，返回前需把代号还原为真实设备号。
    """
    clean = _strip_think(content or "")
    parsed = _extract_json(clean)
    increments = collector.increments()

    if parsed is None:
        refusal = _classify_refusal(state, clean, steps)
        if refusal is not None:
            # 合规拒答/澄清：如实回填文字，confidence=0（无取证无结论），
            # **不 retry**（这是正确行为）；路由据 state.refusal 直达 finalize。
            code = ("W_CLARIFY_NEEDED" if refusal["kind"] == "clarification"
                    else "W_REFUSED_COMPLIANCE")
            return {"diagnosis": _restore_device(clean[:500], state, token),
                    "confidence": 0.0,
                    "risk_level": "low",
                    "refusal": refusal,
                    "agent_steps": steps,
                    "errors": [{"node": "agent_diagnose", "code": code,
                                "msg": refusal["reason"]}],
                    **increments}
        # 与 diagnose E_JSON_PARSE 同口径：正文前 500 字作诊断，retry_count++ 供路由重试
        return {"diagnosis": _restore_device(clean[:500], state, token),
                "retry_count": state.retry_count + 1,
                "agent_steps": steps,
                "errors": [{"node": "agent_diagnose", "code": "E_JSON_PARSE",
                            "msg": "Agent 输出诊断 JSON 解析失败"}],
                **increments}

    root_causes = [
        RootCause(cause=_restore_device(str(rc.get("cause") or ""), state, token),
                  citations=[_normalize_cite(c) for c in rc.get("citations") or []],
                  confidence_hint=float(rc.get("confidence_hint") or 0.0))
        for rc in parsed.get("root_causes") or []
    ]
    suggestions = [
        Suggestion(action=_restore_device(str(s.get("action") or ""), state, token),
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
        "diagnosis": _restore_device(str(parsed.get("diagnosis") or ""), state, token),
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

    # 脱敏随后端翻转（2026-10-21 口径：合规以本地部署为准）——
    # cloud 后端才出网，故 auto 模式下仅 cloud 掩码；本地后端模型看真实编号，
    # 结论质量更好（掩码代号曾被模型复述进报告，见 `_restore_device`）。
    mask = llm_config.sanitize_outbound()
    # U1-D1：设备编号出网前脱敏为 `设备#<sha256[:6]>`（与兜底路径同算法）；
    # 工具执行时再用 `_inbound_arguments` 还原，模型全程只见代号。
    device_token = (hash_device_id(alarm.device_id)
                    if (alarm.device_id and mask) else "")
    tools = load_agent_tools()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": build_agent_system_prompt(tools_json_for_prompt())},
        {"role": "user", "content": _build_agent_context(alarm, device_token)},
    ]

    collector = _Collector()
    steps: list[dict] = []

    for step in range(1, max_steps + 1):
        started = time.perf_counter()
        # 预算先增后调 + 超时轮内重试 1 次（ISS-054 / ISS-059）均在 _call_llm 内
        result, failure = _call_llm(client, messages, tools=tools, timeout=timeout,
                                    budget=budget, state=state,
                                    collector=collector, steps=steps)
        if failure is not None:
            return failure
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        if result.tool_calls:
            messages.append(assistant_tool_calls_message(result.content,
                                                          result.tool_calls))
            for call in result.tool_calls:
                # 模型给的参数是脱敏代号 → 还原为真实编号再执行（仅进程内）
                real_args = _inbound_arguments(call.arguments, alarm.device_id,
                                               device_token)
                out = execute_tool(call.name, real_args,
                                   alarm=alarm, thread_id=state.thread_id)
                collector.absorb(call.name, out)      # 内部状态用真实结果
                pm.inc_tool_call(call.name, "ok" if out.get("ok") else "error")
                # 回灌模型的是脱敏副本（D1 设备号 + D2 工单 result 不出网）
                messages.append(tool_result_message(
                    call.id, call.name,
                    _outbound_payload(call.name, out, alarm.device_id, device_token)))
                # 同一轮多个工具共用**一次** LLM 调用 → token 只记在首条，
                # 否则 steps 汇总会把同一轮 token 重复计 N 次（对账失真）
                first_of_turn = not any(s.get("step") == step for s in steps)
                steps.append({"step": step, "tool": call.name,
                              "ok": bool(out.get("ok")),
                              "args_keys": sorted(call.arguments),
                              "latency_ms": latency_ms,
                              # token 成本可观测（2026-10-21，此前完全不可见）
                              "tokens_in": (result.usage.get("prompt_tokens")
                                            if first_of_turn else None),
                              "tokens_out": (result.usage.get("completion_tokens")
                                             if first_of_turn else None),
                              # 完整 usage（含 cached_tokens 之类供应商扩展字段）——
                              # 用于判定上下文缓存是否生效，勿删
                              "usage": (dict(result.usage) if first_of_turn else None)})
            continue

        # 无工具调用 → 收口
        return _finalize_answer(state, result.content, collector, steps,
                                token=device_token)

    # 达到步数上限：无工具强制收口轮（同样先增后调 + 轮内重试 1 次）
    messages.append({"role": "user", "content": _FORCED_FINAL_INSTRUCTION})
    result, failure = _call_llm(client, messages, tools=None, timeout=timeout,
                                budget=budget, state=state,
                                collector=collector, steps=steps)
    if failure is not None:
        return failure
    steps.append({"step": max_steps + 1, "tool": None, "ok": True,
                  "args_keys": [], "latency_ms": None, "forced_final": True,
                  "tokens_in": result.usage.get("prompt_tokens"),
                  "tokens_out": result.usage.get("completion_tokens")})
    return _finalize_answer(state, content=result.content, collector=collector,
                            steps=steps, token=device_token)
