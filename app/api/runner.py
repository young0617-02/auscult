"""诊断执行服务（D0-3）。

职责：
  1. start_diagnosis：接受告警 → 后台线程执行 graph.invoke（checkpointer 持久化）
  2. 逐节点进度：graph.stream(stream_mode="updates") → events 总线（D0-4 Socket.IO 桥接）
  3. 挂起检测：run 结束后 get_state().next 含 human_review → waiting_review，
     提取 interrupt payload 供审核界面展示
  4. resume_review：审核决策 Command(resume=...) 继续执行（D0-5 REST 调用）
  5. ask_question：chat:ask 追问服务——复用 thread 上下文（证据/工单/告警），
     本地 LLM 带引用回答（新结论强制带 chunk_id 引用，不新建 thread）
  6. thread_status：内存注册表优先，进程重启后回退 checkpointer 推断

对应交付物：plan/Phase 4 前置 D0-3（2026-10 方案确认）
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Any, Callable

from langgraph.types import Command

from app.api.errors import ApiError
from app.graph.build import build_graph
from app.graph.checkpointer import build_checkpointer
from app.graph.nodes.diagnose import (
    OLLAMA_MODEL,
    TIMEOUT_SEC,
    _call_ollama,
    _extract_json,
    _strip_think,
)
from app.graph.state import AlarmEvent
from app.observability.metrics import MetricsCollector
from app.observability.tracing import end_trace, start_trace
from app.report.idempotency import generate_report
from app.review.lifecycle import (
    NOTIFY_AFTER_SECONDS,
    TIMEOUT_AFTER_SECONDS,
    ReviewLock,
    notify_backup_reviewer,
    validate_submitter,
)
from app.security.sanitizer import (
    audit_injection_attempt,
    sanitize_input,
    sanitize_state_inputs,
)
from app.cache import (
    cache_get_state,
    cache_get_values,
    cache_invalidate_thread,
    cache_set_state,
    cache_set_values,
)

# 进程级指标单例（P3 遗留接入：路由/置信度/审核事件 → MetricsCollector）
METRICS = MetricsCollector()

# ---------------------------------------------------------------- 事件总线（D0-4 桥接点）

Subscriber = Callable[[dict], None]
_subscribers: list[Subscriber] = []
_sub_lock = threading.Lock()


def subscribe(fn: Subscriber) -> None:
    """注册事件订阅者（D0-4 Socket.IO emitter 在此挂入）。"""
    with _sub_lock:
        _subscribers.append(fn)


def _emit(event: dict) -> None:
    """广播事件；订阅者异常不阻断 runner。"""
    with _sub_lock:
        subs = list(_subscribers)
    for fn in subs:
        try:
            fn(event)
        except Exception:                                    # noqa: BLE001
            traceback.print_exc()


def _absorb_agent_steps(rec: ThreadRecord | None, node: str, update: Any) -> None:
    """P7：把 diagnose 节点增量中的 agent_steps 归集到线程记录。

    Agent 循环的工具调用轨迹随 diagnose 节点一次返回（state 追加语义），
    在此捕获供 thread_status 实时读出（前端 InspectorDrawer「工具出入参」消费）。
    """
    if rec is None or node != "diagnose" or not isinstance(update, dict):
        return
    steps = update.get("agent_steps")
    if isinstance(steps, list):
        rec.agent_steps.extend(s for s in steps if isinstance(s, dict))


# ---------------------------------------------------------------- 线程注册表（内存态）

class ThreadRecord:
    """单次诊断线程的运行时记录（内存；持久真相在 checkpointer/reports）。"""

    def __init__(self, thread_id: str, alarm: AlarmEvent, submitter: str):
        self.thread_id = thread_id
        self.alarm = alarm
        self.submitter = submitter
        self.status = "running"          # running / waiting_review / done / error
        self.nodes_done: list[str] = []
        self.events: list[dict] = []     # 事件留痕（回放用）
        self.report_id: str | None = None
        self.review_payload: dict | None = None
        self.degrade_reason: str | None = None
        self.qa_log: list[dict] = []     # chat:ask 追问留痕
        self.agent_steps: list[dict] = []  # P7：Agent 循环工具调用轨迹（diagnose 增量归集）
        self.error: str | None = None
        self.notified_4h: bool = False   # 4h 备用审核人通知已触发
        self.started_at = time.time()
        self.finished_at: float | None = None


_registry: dict[str, ThreadRecord] = {}
_reg_lock = threading.Lock()


def get_record(thread_id: str) -> ThreadRecord | None:
    with _reg_lock:
        return _registry.get(thread_id)


# ---------------------------------------------------------------- 执行

def _execute_graph(thread_id: str, alarm: AlarmEvent) -> None:
    """后台线程体：stream 逐节点推进 → 挂起/完成判定 → 图外幂等写入。"""
    rec = get_record(thread_id)
    config = {"configurable": {"thread_id": thread_id}}

    # P3 遗留接入·安全净化：入口即净化用户可控告警字段（diagnose/cloud prompt 均源自 state）
    sanitized = sanitize_state_inputs({"alarm": alarm.model_dump()})
    if sanitized["injections"]:
        for inj in sanitized["injections"]:
            audit_injection_attempt(thread_id, inj["field"], inj["patterns_hit"],
                                    str(inj.get("sanitized", ""))[:100])
    initial = {"alarm": sanitized["state"]["alarm"], "thread_id": thread_id}

    def _progress(node: str) -> None:
        if rec:
            rec.nodes_done.append(node)
        event = {"type": "diagnosis:progress", "thread_id": thread_id,
                 "node": node, "nodes_done": list(rec.nodes_done) if rec else [node],
                 "ts": time.time()}
        if rec:
            rec.events.append(event)
        _emit(event)

    tracer = start_trace(thread_id)   # P3 遗留接入：trace_node span（build.py 节点已包裹）
    try:
        with build_checkpointer() as saver:
            graph = build_graph(saver)
            interrupt_payload: dict | None = None
            for chunk in graph.stream(initial, config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    intr = chunk["__interrupt__"]
                    value = getattr(intr[0], "value", None) if intr else None
                    interrupt_payload = value if isinstance(value, dict) else None
                    continue
                for node in chunk:
                    if not node.startswith("__"):
                        _progress(node)
                        _absorb_agent_steps(rec, node, chunk[node])

            snap = graph.get_state(config)
            next_nodes = tuple(snap.next or ())

            if "human_review" in next_nodes:
                # 挂起：等待人工审核（resume 由 D0-5 审核 REST 触发）
                if interrupt_payload is None:
                    # 兜底：从 task interrupts 提取
                    for task in snap.tasks:
                        for intr in getattr(task, "interrupts", ()) or ():
                            v = getattr(intr, "value", None)
                            if isinstance(v, dict):
                                interrupt_payload = v
                                break
                if rec:
                    rec.status = "waiting_review"
                    rec.review_payload = interrupt_payload
                    rec.finished_at = time.time()
                event = {"type": "review:required", "thread_id": thread_id,
                         "payload": interrupt_payload, "ts": time.time()}
                if rec:
                    rec.events.append(event)
                _emit(event)
                return

            # 正常完成：图外幂等写入报告
            values = dict(snap.values or {})
            report_id = values.get("report_id")
            if report_id:
                try:
                    gen = generate_report(values)
                    report_id = gen["report_id"]
                except Exception as exc:                        # noqa: BLE001
                    if rec:
                        rec.error = f"报告写入失败: {exc}"
                    _emit({"type": "diagnosis:error", "thread_id": thread_id,
                           "error": str(exc), "ts": time.time()})
            if rec:
                rec.status = "done"
                rec.report_id = report_id
                rec.degrade_reason = values.get("degrade_reason")
                rec.finished_at = time.time()
            # P3 遗留接入：置信度 + 路由指标
            METRICS.record_confidence(float(values.get("confidence") or 0.0))
            done_nodes = rec.nodes_done if rec else []
            if "degrade" in done_nodes:
                METRICS.record_route("degrade")
            elif "escalate_cloud" in done_nodes:
                METRICS.record_route("escalate_cloud")
            else:
                METRICS.record_route("finalize")
            _emit({"type": "diagnosis:done", "thread_id": thread_id,
                   "status": "done", "report_id": report_id,
                   "degrade_reason": values.get("degrade_reason"),
                   "ts": time.time()})
    except Exception as exc:                                 # noqa: BLE001
        if rec:
            rec.status = "error"
            rec.error = str(exc)
            rec.finished_at = time.time()
        _emit({"type": "diagnosis:done", "thread_id": thread_id,
               "status": "error", "error": str(exc), "ts": time.time()})
    finally:
        # P3 遗留接入：trace 聚合 → 指标（节点耗时/置信度/路由）
        METRICS.aggregate_from_tracer(tracer)
        end_trace()


def start_diagnosis(alarm: AlarmEvent, submitter: str) -> str:
    """发起诊断：登记线程 → 后台执行 → 立即返回 thread_id。"""
    thread_id = f"thr-{uuid.uuid4().hex[:20]}"
    with _reg_lock:
        _registry[thread_id] = ThreadRecord(thread_id, alarm, submitter)
    t = threading.Thread(target=_execute_graph, args=(thread_id, alarm),
                         name=f"diag-{thread_id}", daemon=True)
    t.start()
    return thread_id


def resume_review(thread_id: str, decision: dict, reviewer_id: str) -> dict:
    """审核决策恢复（D0-5 审核 REST 的服务层）。

    decision: {action: approved|rejected|timeout, comment?, reviewer_id}
    返回 {status, report_id?, degrade_reason?}
    """
    rec = get_record(thread_id)
    if rec is None or rec.status != "waiting_review":
        raise ApiError("E_CONFLICT", "该诊断不在等待审核状态")
    rec.status = "running"

    resume_value = {**decision, "reviewer_id": reviewer_id}
    config = {"configurable": {"thread_id": thread_id}}
    try:
        with build_checkpointer() as saver:
            graph = build_graph(saver)
            for chunk in graph.stream(Command(resume=resume_value), config,
                                      stream_mode="updates"):
                for node in chunk:
                    if not node.startswith("__") and rec:
                        rec.nodes_done.append(node)
            snap = graph.get_state(config)
            values = dict(snap.values or {})
            report_id = values.get("report_id")
            if report_id:
                try:
                    gen = generate_report(values)
                    report_id = gen["report_id"]
                except Exception as exc:                        # noqa: BLE001
                    rec.error = f"报告写入失败: {exc}"
            rec.status = "done"
            rec.report_id = report_id
            rec.degrade_reason = values.get("degrade_reason")
            rec.finished_at = time.time()
            # P7：resume 后 values 变更（report_id/human_review/degrade_reason）
            # → 失效两层只读缓存（TTL 为最终兜底）
            cache_invalidate_thread(thread_id)
            METRICS.record_review(
                (rec.finished_at - rec.started_at) * 1000,
                (values.get("human_review") or {}).get("status", "unknown")
                if isinstance(values.get("human_review"), dict) else "unknown")
            _emit({"type": "diagnosis:done", "thread_id": thread_id,
                   "status": "done", "report_id": report_id,
                   "degrade_reason": values.get("degrade_reason"),
                   "ts": time.time()})
            return {"status": "done", "report_id": report_id,
                    "degrade_reason": values.get("degrade_reason"),
                    "human_review": values.get("human_review")}
    except Exception as exc:                                 # noqa: BLE001
        rec.status = "error"
        rec.error = str(exc)
        rec.finished_at = time.time()
        raise ApiError("E_INTERNAL", f"审核恢复执行失败：{exc}") from exc


def submit_review(thread_id: str, action: str, comment: str, reviewer: str) -> dict:
    """审核提交服务（D0-5；REST 与 Socket.IO review:submit 共用）。

    流程：等待态校验 → 职责分离（发起人不得自审）→ 并发锁 → resume 执行 → 释放锁。
    action 仅允许 approved / rejected（timeout 由生命周期 watcher 系统触发）。
    """
    rec = get_record(thread_id)
    if rec is None:
        raise ApiError("E_NOT_FOUND", f"诊断线程 {thread_id} 不存在或服务已重启")
    if rec.status != "waiting_review":
        raise ApiError("E_CONFLICT", "该诊断不在等待审核状态")

    # 职责分离：诊断发起人不得自审（p3-handover-p4 §2.2 / plan §六.5）
    if not validate_submitter(reviewer, rec.submitter):
        raise ApiError("E_PERMISSION", "诊断发起人不能自审该报告，请更换审核员")

    lock = ReviewLock()
    if not lock.acquire(thread_id, reviewer):
        raise ApiError("E_CONFLICT",
                       f"审核锁被 {lock.holder(thread_id) or '其他审核员'} 持有，请稍后再试")
    try:
        return resume_review(thread_id, {"action": action, "comment": comment},
                             reviewer_id=reviewer)
    finally:
        lock.release(thread_id, reviewer)


# ---------------------------------------------------------------- 生命周期 watcher（4h/24h）

_WATCH_INTERVAL_SEC = 60


def _lifecycle_tick() -> None:
    """单次扫描：4h → 通知备用审核人（转派）；24h → 自动超时降级。"""
    now = time.time()
    for rec in list(_registry.values()):
        if rec.status != "waiting_review" or not rec.finished_at:
            continue
        elapsed = now - rec.finished_at
        if elapsed >= TIMEOUT_AFTER_SECONDS:
            try:
                from app.observability import prom_metrics as pm   # noqa: PLC0415
                pm.inc_review_timeout("degrade_24h")
            except Exception:                                    # noqa: BLE001
                pass
            try:
                resume_review(rec.thread_id,
                              {"action": "timeout",
                               "comment": "24h 超时自动降级（API 生命周期 watcher）"},
                              reviewer_id="system")
            except Exception:                                # noqa: BLE001
                traceback.print_exc()
        elif elapsed >= NOTIFY_AFTER_SECONDS and not rec.notified_4h:
            rec.notified_4h = True
            try:
                from app.observability import prom_metrics as pm   # noqa: PLC0415
                pm.inc_review_timeout("notify_4h")
            except Exception:                                    # noqa: BLE001
                pass
            try:
                notify_backup_reviewer(rec.thread_id, rec.review_payload or {})
            except Exception:                                # noqa: BLE001
                traceback.print_exc()


def start_lifecycle_watcher() -> None:
    """FastAPI lifespan 启动（与 alarm 轮询桥接并列的后台任务）。"""
    threading.Thread(target=_watch_loop, name="review-lifecycle-watcher",
                     daemon=True).start()


def _watch_loop() -> None:
    while True:
        time.sleep(_WATCH_INTERVAL_SEC)
        try:
            _lifecycle_tick()
        except Exception:                                    # noqa: BLE001 - watcher 不中断
            traceback.print_exc()


# ---------------------------------------------------------------- chat:ask 追问服务

_ASK_SYSTEM = """你是工业设备故障诊断助手。基于该诊断线程的既有上下文（告警、证据、历史工单）回答工程师追问。

严格要求：
- 回答必须给出依据：citations 引用证据中的 chunk_id（无可用依据时 citations 为空数组并明确说明）
- 不编造证据中不存在的事实
输出严格 JSON：{"answer": "回答（人话）", "citations": ["chunk_id", ...]}
"""


def _load_thread_values(thread_id: str) -> dict | None:
    """从 checkpointer 读取线程最终 state（供追问注入真实证据）。

    P7：先查 Redis values 缓存（ask 路径每次构建 graph + PG 连接，
    代价高；证据在诊断终态后冻结，缓存安全）。变更点（resume_review）
    会显式失效，TTL 为最终兜底。
    """
    cached = cache_get_values(thread_id)
    if cached is not None:
        return cached
    config = {"configurable": {"thread_id": thread_id}}
    with build_checkpointer() as saver:
        graph = build_graph(saver)
        snap = graph.get_state(config)
    if snap is None or not snap.values:
        return None
    values = dict(snap.values)
    cache_set_values(thread_id, values)
    return values


def _ask_user_prompt(rec: ThreadRecord, values: dict | None, question: str) -> str:
    a = rec.alarm
    parts = [f"【告警】设备={a.device_id} 测点={a.metric} 值={a.value} 严重度={a.severity}"]
    if rec.report_id:
        parts.append(f"【既有结论】{rec.degrade_reason or '诊断已完成'}（report_id={rec.report_id}）")
    elif rec.degrade_reason:
        parts.append(f"【降级原因】{rec.degrade_reason}")

    # 注入真实证据（chunk_id + 摘要），使 citations 可落地
    evidence = (values or {}).get("evidence") or []
    for i, ev in enumerate(evidence[:10], 1):
        cid = getattr(ev, "chunk_id", None) or (ev.get("chunk_id") if isinstance(ev, dict) else "")
        text = getattr(ev, "text", None) or (ev.get("text", "") if isinstance(ev, dict) else "")
        parts.append(f"【证据{i}】chunk_id={cid} text={str(text)[:120]}")

    parts.append(f"【追问】{question}")
    parts.append("请基于上述上下文回答，输出严格 JSON。")
    return "\n".join(parts)


def ask_question(thread_id: str, question: str, user: str) -> dict:
    """chat:ask 追问（REST twin，D0-4 socket 事件将调用同一服务）。

    复用 thread 上下文（不新建 thread）；本地 LLM 回答，新结论强制带引用。
    """
    rec = get_record(thread_id)
    if rec is None:
        raise ApiError("E_NOT_FOUND", f"诊断线程 {thread_id} 不存在或服务已重启")
    if rec.status not in ("done", "waiting_review"):
        raise ApiError("E_CONFLICT", "诊断尚未完成，暂不能追问")

    try:
        values = _load_thread_values(thread_id)
    except ApiError:
        raise
    except Exception as exc:                                 # noqa: BLE001
        raise ApiError("E_UPSTREAM", f"状态存储暂不可用：{exc}") from exc

    # P3 遗留接入·安全净化：追问文本同样过注入检测
    q_check = sanitize_input(question)
    if q_check["injected"]:
        audit_injection_attempt(thread_id, "ask.question",
                                q_check["patterns_hit"], question[:100])
    question = q_check["sanitized"]

    messages = [
        {"role": "system", "content": _ASK_SYSTEM},
        {"role": "user", "content": _ask_user_prompt(rec, values, question)},
    ]
    try:
        raw = _call_ollama(messages, timeout=TIMEOUT_SEC)
    except (TimeoutError, ConnectionError, RuntimeError) as exc:
        raise ApiError("E_UPSTREAM", f"本地推理暂不可用：{exc}") from exc

    clean = _strip_think(raw)
    parsed = _extract_json(clean)
    if parsed is None:
        answer = {"answer": clean[:1000], "citations": []}
    else:
        answer = {"answer": str(parsed.get("answer", ""))[:2000],
                  "citations": [c for c in parsed.get("citations", []) if isinstance(c, str)]}

    entry = {"question": question, "answer": answer["answer"],
             "citations": answer["citations"], "user": user,
             "model": OLLAMA_MODEL, "ts": time.time()}
    rec.qa_log.append(entry)
    # P7：qa_log 是 thread_status payload 的组成部分 → 失效两层缓存
    cache_invalidate_thread(thread_id)
    return answer


# ---------------------------------------------------------------- 状态查询（含重启回退）

def thread_status(thread_id: str) -> dict:
    """线程状态：注册表优先；服务重启后从 checkpointer 推断。"""
    rec = get_record(thread_id)
    if rec is not None:
        return {
            "thread_id": thread_id,
            "status": rec.status,
            "submitter": rec.submitter,
            "alarm": rec.alarm.model_dump() if rec.alarm else None,
            "nodes_done": list(rec.nodes_done),
            "agent_steps": list(rec.agent_steps),
            "report_id": rec.report_id,
            "review_payload": rec.review_payload,
            "degrade_reason": rec.degrade_reason,
            "qa_log": list(rec.qa_log),
            "error": rec.error,
            "started_at": rec.started_at,
            "finished_at": rec.finished_at,
        }

    # P7：注册表未命中（进程重启场景）→ 先查 Redis 只读缓存
    # （PG 前 read-through；非权威，未命中/不可达回落 checkpointer）
    cached = cache_get_state(thread_id)
    if cached is not None:
        return cached

    # 回退：从 checkpointer 推断（进程重启场景）
    config = {"configurable": {"thread_id": thread_id}}
    try:
        with build_checkpointer() as saver:
            graph = build_graph(saver)
            snap = graph.get_state(config)
    except Exception as exc:                                 # noqa: BLE001
        raise ApiError("E_UPSTREAM", f"状态存储暂不可用：{exc}") from exc

    if snap is None or not snap.values:
        raise ApiError("E_NOT_FOUND", f"诊断线程 {thread_id} 不存在")

    values = dict(snap.values)
    next_nodes = tuple(snap.next or ())
    # P7：Agent 循环工具调用轨迹（确定性模式为[]；dict 载荷对 Redis 缓存友好）
    agent_steps = [s for s in (values.get("agent_steps") or []) if isinstance(s, dict)]
    if "human_review" in next_nodes:
        status = "waiting_review"
        payload = None
        for task in snap.tasks:
            for intr in getattr(task, "interrupts", ()) or ():
                v = getattr(intr, "value", None)
                if isinstance(v, dict):
                    payload = v
                    break
        result = {"thread_id": thread_id, "status": status,
                  "review_payload": payload, "qa_log": [],
                  "nodes_done": [], "agent_steps": agent_steps,
                  "report_id": None,
                  "degrade_reason": values.get("degrade_reason"),
                  "submitter": None, "alarm": None, "error": None,
                  "started_at": None, "finished_at": None}
        cache_set_state(thread_id, result)
        return result

    result = {"thread_id": thread_id, "status": "done",
              "report_id": values.get("report_id"),
              "degrade_reason": values.get("degrade_reason"),
              "review_payload": None, "qa_log": [], "nodes_done": [],
              "agent_steps": agent_steps,
              "submitter": None, "alarm": None, "error": None,
              "started_at": None, "finished_at": None}
    cache_set_state(thread_id, result)
    return result
