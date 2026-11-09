"""路径 D harness：用**产品 Agent 本体**跑 V1 判据集（工具打桩 · 判分与聚合复用）

立项依据：`docs/p7-design-gate-product-agent-2026-10-20.md`
对照实验：`experiments/v1/EXP-P7-GATE3.md`（路径 C = 单轮 harness + prompt v4）

与路径 C 的本质差异（也是本 harness 存在的理由）：

| 维度 | C（`run_e2e.py`） | D（本脚本） |
|---|---|---|
| 提示词 | 冻结区 `prompts/tool_call_prompt_v4.md`（含 few-shot） | **产品提示词** `app/agent/prompt.py` |
| 工具面 | `schemas/tools_v4_agent.json`（判据侧） | **`app/agent/tool_registry.load_agent_tools()`**（产品侧，含写操作护栏） |
| 循环 | **单轮**（一次请求出 tool_calls） | **多轮自主循环**（同一份 `agent_diagnose` 语义：工具回灌 → 再规划 → 收口） |
| 步数上限 | 无 | `AUSCULT_AGENT_MAX_STEPS`（达上限走**无工具强制收口**轮） |
| 预算 | 无 BudgetGuard | **每轮过 `BudgetGuard`**（cloud 后端），与产品一致 |
| 收口 | 仅比对 tool_calls | 额外记录 `json_parse_ok` / `forced_final` / `llm_calls` |

**唯一替换**：告警上下文 → 用例输入 + 历史。V1 用例是问答形态（无 AlarmEvent），故用户消息
直接取 `case["input"]`，历史取 `case["context"]`；其余（系统提示词、工具面、消息回灌、
收口解析、预算与步数护栏）**逐字复用产品实现**。

v2 修订（2026-10-20，按 `EXP-P7-GATE-D` §3.4/§3.5 的三项摩擦）：
  1. **告警前置**：`infer_alarm()` 从用例文本抽设备编号，注入最小 `AlarmEvent` 并传给
     `execute_tool`（产品同款调用形态）→ 修掉「`query_sensor` 缺 `sensor_ids` 且无告警可推断」
     的工具级错误。`--no-alarm` 可回到 v1 行为；
  2. **收口形态单列**：`answer_mode ∈ {json, natural_language, none}` 只记录、不进六档
     （问答型用例以自然语言收口不算错误，但必须可见）；
  3. **步数默认取产品值**（`AUSCULT_AGENT_MAX_STEPS`，默认 4），不再为预算压到 2。

工具执行：`tool_registry._EXECUTORS` 被替换为**中性打桩**（不泄漏期望值、与
`run_v1.STEP_CHAIN` 同款口径），白名单校验、写操作护栏、审计落盘**保持真实**。

用法：
    python scripts/run_agent_gate.py --selftest                       # 离线，零网络
    python scripts/run_agent_gate.py --cases evals/v1_cases.jsonl \
        --cases evals/v1_refusal_transfer_v1.jsonl \
        --out experiments/v1/raw/EXP-P7-GATE-D-R1.jsonl --tag p7-gate-d-r1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_ROOT))

import gate_rules as gr                                                # noqa: E402
import judge_tools as jt                                               # noqa: E402
import run_e2e as e2e                                                  # noqa: E402 - 门短路记录形状复用
import run_v1 as rv                                                    # noqa: E402 - append_record 复用

from app.agent.prompt import build_agent_system_prompt                 # noqa: E402
from app.agent import tool_registry as tr                              # noqa: E402
from app.graph.nodes.agent_diagnose import (                           # noqa: E402
    _FORCED_FINAL_INSTRUCTION,
    _Collector,
    _finalize_answer,
)
from app.graph.state import AlarmEvent, DiagnosisState                  # noqa: E402
from app.llm import config as llm_config                               # noqa: E402
from app.llm.client import get_client                                  # noqa: E402
from app.security import sanitizer                                     # noqa: E402

HARNESS = "agent_gate_v1"
# 判据被测工具面 = 产品工具面（ISS-052 处置先例）。2026-10-30 随产品侧升 v6
# （query_sensor 增加分页形参 cursor）派生 `tools_v6_agent.json`；v4_agent 保留为
# EXP-P7-GATE3 等历史实验的可复现快照，不删不改。
DEFAULT_SCHEMA = PROJECT_ROOT / "schemas" / "tools_v6_agent.json"
# 实验审计路径：`AUSCULT_AGENT_GATE_AUDIT_PATH` 可覆盖 —— pytest 根 conftest 会把它指到
# 临时目录，避免回归跑一次就把这份**已跟踪**的实验产物写长（2026-10-22 集成测试隔离）。
AUDIT_PATH = Path(os.environ.get("AUSCULT_AGENT_GATE_AUDIT_PATH")
                  or (PROJECT_ROOT / "experiments" / "v1" / "raw"
                      / "EXP-P7-GATE-D.security_audit.jsonl"))

def apply_audit_redirect() -> None:
    """把审计改写到实验目录（**只在真正跑 gate 时调用**）。

    2026-10-22 修复：这行原先是**模块级副作用** —— 只要有人 `import run_agent_gate`
    （例如 `tests/test_agent_gate.py::test_audit_not_pollute_reports`），进程内的全局
    `sanitizer.AUDIT_LOG_PATH` 就被永久改到 `experiments/v1/raw/…`，于是同一轮回归里
    后续用例（`test_d24_security::test_audit_logging`、
    `test_p5_d12_security::test_tool_whitelist`）写到"自己读不到"的文件里而失败，
    同时把 `experiments/v1/raw/EXP-P7-GATE-D.security_audit.jsonl` 这种**已跟踪产物**越写越长。
    """
    sanitizer.AUDIT_LOG_PATH = AUDIT_PATH


# ---------------------------------------------------------------- 中性打桩

def _stub_sensor(args: dict[str, Any], alarm: Any = None) -> dict[str, Any]:
    series = [{
        "sensor_id": f"{args.get('device_id', 'PUMP-A-01')}.vib_x",
        "column": "vib_rms", "count": 60, "avg": 4.9, "max": 6.8, "min": 4.0,
        "last": 6.5, "exceed_count": 12, "exceed_duration_ms": 3_600_000,
        "threshold": 4.5, "trend": "up",
    }]
    return {"ok": True, "result": {"device_id": args.get("device_id", ""), "series": series}}


def _stub_knowledge(args: dict[str, Any], alarm: Any = None) -> dict[str, Any]:
    return {"ok": True, "result": {"items": [{
        "chunk_id": "KB-9001", "text": "（打桩）振动速度有效值超过 4.5 mm/s 应安排停机检查。",
        "score": 0.81, "routes": ["dense"],
    }]}}


def _stub_graph(args: dict[str, Any], alarm: Any = None) -> dict[str, Any]:
    return {"ok": True, "result": {
        "entities_hit": [str(args.get("start_node") or "PUMP-A-01")],
        "hits": [{"chunk_id": "GR-9001", "score": 0.77}],
    }}


def _stub_history(args: dict[str, Any], alarm: Any = None) -> dict[str, Any]:
    return {"ok": True, "result": {
        "device_id": args.get("device_id", ""),
        "work_orders": [{"order_id": "WO-9001", "fault": "轴承磨损",
                         "action": "更换轴承", "result": "正常", "created_at": "2026-07-01"}],
    }}


STUBS = {"query_sensor": _stub_sensor, "search_knowledge": _stub_knowledge,
         "query_graph": _stub_graph, "get_maintenance_history": _stub_history}


def install_stubs() -> None:
    """把执行体替换为打桩（白名单 / 写操作护栏 / 审计仍走真实实现）。"""
    tr._EXECUTORS.update(STUBS)


def _violation_kind(name: str, err: str) -> str:
    if "写操作护栏" in err:
        return "write_guard"
    if "白名单" in err:
        return "not_whitelisted"
    if "执行异常" in err:
        return "exec_error"
    if not err:
        return "no_result"
    return "other"


# ---------------------------------------------------------------- 用例驱动

def messages_for(case: dict[str, Any], system_prompt: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for turn in case.get("context") or []:
        role = str(turn.get("role") or "")
        if role in ("user", "assistant"):
            msgs.append({"role": role, "content": str(turn.get("content") or "")})
    msgs.append({"role": "user", "content": str(case.get("input") or "")})
    return msgs


#: 设备编号形如 `PUMP-A-01` / `MOTOR-B-12`（与产品告警/图谱同构）
_DEVICE_RE = re.compile(r"\b[A-Z][A-Z0-9]+-[A-Z]-\d+\b")


def infer_alarm(case: dict[str, Any]) -> Any:
    """给用例注入**最小 AlarmEvent**（告警前置）。

    产品入口永远是告警：`query_sensor` 缺 `sensor_ids` 时靠告警推断测点
    （`EXP-P7-GATE-D` §3.4-a 的 4 次工具级错误即由此产生）。V1 用例是问答形态，
    故按「设备编号 + 振动类告警」补一条最小告警，使工具链路与产品一致；
    **只补事实、不补期望值**（不含用例的 expected 内容）。

    设备编号从 `context` 优先、其次 `input` 中抽取；抽不到则返回 None（保持原行为）。
    """
    hay = " ".join(str(t.get("content") or "") for t in (case.get("context") or []))
    hay += " " + str(case.get("input") or "")
    m = _DEVICE_RE.search(hay)
    if not m:
        return None
    return AlarmEvent(alarm_id=f"ALM-GATE-{case['case_id']}",
                      device_id=m.group(0),
                      metric="vib_rms", value=6.8, baseline=4.5,
                      severity="high", ts=int(time.time() * 1000),
                      rule_id="GATE-D-PREFILL")


def answer_mode_of(json_ok: bool, content: str) -> str:
    """收口形态（**不进六档**，仅报告）：`json` / `natural_language` / `none`。

    D 首版发现 `v1-014` 这类**问答型用例**会以表格/段落收口而非诊断 JSON
    （`EXP-P7-GATE-D` §3.5-1）—— 这是判据与产品形态的错配，不是模型错误，
    故单列指标而不判失败。
    """
    if json_ok:
        return "json"
    return "natural_language" if (content or "").strip() else "none"


def run_case(case: dict[str, Any], *, client: Any, tag: str, repeat: int,
             system_prompt: str, tools: list[dict[str, Any]], max_steps: int,
             timeout: float, budget: Any = None, model: str = "",
             alarm: Any = None) -> dict[str, Any]:
    """驱动一次 Agent 循环（语义对齐 `agent_diagnose`），返回判分可用的 raw 记录。"""
    state = DiagnosisState(alarm=alarm,
                           thread_id=f"gate-d-{case['case_id']}-{tag}-r{repeat}")
    messages = messages_for(case, system_prompt)
    collector = _Collector()
    steps: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    started = time.perf_counter()
    error: str | None = None
    content = ""
    final: dict[str, Any] = {}
    llm_calls = 0
    forced = False

    def _chat(**kwargs: Any) -> Any:
        nonlocal llm_calls
        res = client.chat(messages, **kwargs)
        llm_calls += 1
        return res

    for step in range(1, max_steps + 1):
        if budget is not None:
            ok, count, limit, reason = budget.check()
            if not ok:
                error = f"E_BUDGET_EXCEEDED {count}/{limit} {reason}"
                break
        try:
            result = _chat(tools=tools, timeout=timeout)
        except Exception as exc:                                       # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            break
        if budget is not None:
            budget.increment()

        if result.tool_calls:
            messages.append(tr.assistant_tool_calls_message(result.content, result.tool_calls))
            for call in result.tool_calls:
                args = dict(call.arguments or {})
                calls.append({"name": call.name, "arguments": args})
                out = tr.execute_tool(call.name, args, alarm=alarm, thread_id=state.thread_id)
                collector.absorb(call.name, out)
                if not out.get("ok"):
                    violations.append({"tool": call.name, "step": step,
                                       "kind": _violation_kind(call.name, str(out.get("error") or "")),
                                       "error": str(out.get("error") or "")[:200]})
                messages.append(tr.tool_result_message(call.id, call.name, out))
                steps.append({"step": step, "tool": call.name, "ok": bool(out.get("ok")),
                              "args_keys": sorted(args)})
            continue

        final = _finalize_answer(state, result.content, collector, steps)
        content = str(final.get("diagnosis") or result.content or "")
        break
    else:
        # 达步数上限：无工具强制收口轮（与产品一致）
        messages.append({"role": "user", "content": _FORCED_FINAL_INSTRUCTION})
        forced = True
        try:
            result = _chat(tools=None, timeout=timeout)
        except Exception as exc:                                       # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
        else:
            steps.append({"step": max_steps + 1, "tool": None, "ok": True, "forced_final": True})
            final = _finalize_answer(state, result.content, collector, steps)
            content = str(final.get("diagnosis") or result.content or "")

    total_ms = round((time.perf_counter() - started) * 1000, 1)
    json_ok = bool(final) and not any(
        (e or {}).get("code") == "E_JSON_PARSE" for e in (final.get("errors") or []))
    return {
        "model": model,
        "attempt": 1,
        "repeat": repeat,
        "cold_start": repeat == 1,
        "tag": tag,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "harness": HARNESS,
        "expected": case,
        "result": {
            "tool_calls": calls,
            "tool_calls_missing": not calls,
            "content_clean": content,
            "latency_ms": total_ms,
            "error": error,
            # —— D 专属派生指标（只记录，不参与 judge_record 的成功判定）——
            "steps": steps,
            "agent_steps": len(steps),
            "llm_calls": llm_calls,
            "forced_final": forced,
            "json_parse_ok": json_ok,
            # 收口形态（2026-10-20 路径 D v2）：问答型用例允许自然语言收口，单列不进六档
            "answer_mode": answer_mode_of(json_ok, content),
            # 告警前置（v2）：注入的最小 AlarmEvent，供审计追溯（None = 未注入）
            "alarm": ({"device_id": alarm.device_id, "metric": alarm.metric,
                       "value": alarm.value, "baseline": alarm.baseline,
                       "severity": alarm.severity} if alarm is not None else None),
            "confidence": final.get("confidence"),
            "risk_level": final.get("risk_level"),
            "guard_violations": violations,
        },
    }


def load_cases(paths: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    """入口：临时重定向实验审计，跑完**必须还原**（否则污染同进程其它调用方）。"""
    prev_audit = sanitizer.AUDIT_LOG_PATH
    try:
        apply_audit_redirect()
        return _main_impl(argv)
    finally:
        sanitizer.AUDIT_LOG_PATH = prev_audit


def _main_impl(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="路径 D：产品 Agent 本体跑 V1 判据集")
    ap.add_argument("--cases", action="append", default=None, help="用例文件（可多次）")
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="判分用 schema（默认只读 4 工具面）")
    ap.add_argument("--out", default=None, help="raw 输出（.jsonl）")
    ap.add_argument("--tag", default="p7-gate-d", help="标签（写入每行记录）")
    ap.add_argument("--repeat", type=int, default=1, help="每用例重复次数（同日多轮用不同 --out）")
    ap.add_argument("--max-steps", type=int, default=None, help="覆盖 AUSCULT_AGENT_MAX_STEPS")
    ap.add_argument("--quiet", action="store_true", help="不打印逐例结果")
    ap.add_argument("--no-stub", action="store_true",
                    help="不替换工具执行体（默认打桩；仅用于对照真实工具链路）")
    ap.add_argument("--no-alarm", action="store_true",
                    help="不注入最小 AlarmEvent（v1 行为；默认注入，使工具链路与产品一致）")
    ap.add_argument("--selftest", action="store_true", help="离线自检（假客户端，零网络）")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    if not args.cases or not args.out:
        ap.error("需要 --cases 与 --out（或 --selftest）")

    # 打桩必须在驱动循环前安装（EXP-P7-GATE-D 首跑漏装 → 实测走了真实工具，见该实验 §3.4）
    if not args.no_stub:
        install_stubs()

    schemas = jt.load_tool_schemas(Path(args.schema))
    cases = load_cases(args.cases)
    system_prompt = build_agent_system_prompt(tr.tools_json_for_prompt())
    tools = tr.load_agent_tools()
    client = get_client(role=llm_config.ROLE_AGENT)
    backend = llm_config.llm_backend()
    max_steps = args.max_steps or llm_config.agent_max_steps()
    timeout = llm_config.llm_timeout(llm_config.ROLE_AGENT)
    model = getattr(client, "model", "") or os.getenv("AUSCULT_CLOUD_MODEL", "")
    budget = None
    if backend == "cloud":
        from app.router.budget import BudgetGuard                      # noqa: PLC0415
        budget = BudgetGuard()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    records: list[dict[str, Any]] = []
    cloud_calls = bypassed = alarm_injected = 0
    modes: dict[str, int] = {}
    for case in cases:
        decision, reason = gr.decide(case)
        if decision != "allow":
            rec = e2e.gate_record(case, decision, reason, 1, args.tag)
            bypassed += 1
        else:
            alarm = None if args.no_alarm else infer_alarm(case)
            if alarm is not None:
                alarm_injected += 1
            rec = run_case(case, client=client, tag=args.tag, repeat=1,
                           system_prompt=system_prompt, tools=tools,
                           max_steps=max_steps, timeout=timeout, budget=budget,
                           model=model, alarm=alarm)
            cloud_calls += int(rec["result"].get("llm_calls") or 0)
            mode = str(rec["result"].get("answer_mode") or "")
            modes[mode] = modes.get(mode, 0) + 1
        rv.append_record(out_path, rec)
        records.append(rec)
        if not args.quiet:
            ok = jt.judge_record(rec, schemas)["success"]
            tail = "" if rec.get("gate") else \
                f" mode={rec['result'].get('answer_mode')} forced={rec['result'].get('forced_final')}"
            print(f"{case['case_id']:8s} {case['type']:5s} "
                  f"{'gate:' + str(decision) if rec.get('gate') else 'agent'} "
                  f"steps={rec['result'].get('agent_steps')} calls={rec['result'].get('llm_calls')} "
                  f"ok={ok}{tail}")

    meta = {
        "harness": HARNESS,
        "tag": args.tag,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": backend,
        "model": model,
        "prompt": "app/agent/prompt.py（产品提示词）",
        "prompt_sha256": _sha(PROJECT_ROOT / "app" / "agent" / "prompt.py"),
        "schema": str(Path(args.schema).name),
        "schema_sha256": _sha(Path(args.schema)),
        "tool_face": sorted(tr.SCHEMA_TO_PRODUCT) if hasattr(tr, "SCHEMA_TO_PRODUCT") else [],
        "max_steps": max_steps,
        "timeout_s": timeout,
        "records": len(records),
        "cloud_calls": cloud_calls,
        "gate_short_circuits": bypassed,
        "tools_stubbed": [] if args.no_stub else sorted(STUBS),
        # v2（2026-10-20）：告警前置 + 收口形态单列（均不进六档）
        "alarm_injection": not args.no_alarm,
        "alarms_injected": alarm_injected,
        "answer_modes": modes,
    }
    meta_path = out_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[agent_gate] records={len(records)} cloud_calls={cloud_calls} "
          f"gate_short_circuits={bypassed} -> {out_path}")
    return 0


# ---------------------------------------------------------------- 自检（离线）

class _FakeClient:
    """脚本化假客户端：第 1 轮调工具，第 2 轮收口 JSON。"""

    model = "fake"

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        self.calls += 1
        item = self.script[min(self.calls - 1, len(self.script) - 1)]
        return item


class _FakeResult:
    def __init__(self, content: str = "", tool_calls: list[Any] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []
        self.latency_ms = 1.0
        self.error = None


class _FakeCall:
    def __init__(self, name: str, arguments: dict[str, Any], cid: str = "c1") -> None:
        self.id = cid
        self.name = name
        self.arguments = arguments


def _selftest() -> int:
    apply_audit_redirect()      # 自检同样断言"审计落实验路径"，需先重定向
    failures: list[str] = []
    install_stubs()
    case = {"case_id": "t-001", "type": "多轮", "difficulty": "中", "expect_reject": False,
            "context": [{"role": "user", "content": "PUMP-A-01 振动怎么样？"},
                        {"role": "assistant", "content": "偏高。"}],
            "input": "查一下两层关系。",
            "expected_tool_calls": [{"name": "query_graph",
                                     "arguments": {"start_node": "PUMP-A-01", "depth": 2}}]}
    schemas = jt.load_tool_schemas(DEFAULT_SCHEMA)
    system_prompt = build_agent_system_prompt(tr.tools_json_for_prompt())
    tools = tr.load_agent_tools()
    if len(tools) != 4:
        failures.append(f"产品工具面应为 4 个只读工具，实际 {len(tools)}")

    # 1) 工具轮 → 收口轮：应记录 1 次调用、2 次 LLM、判分通过
    final_json = json.dumps({"diagnosis": "驱动端轴承磨损", "self_confidence": 0.8,
                             "root_causes": [{"cause": "轴承磨损", "citations": []}],
                             "suggestions": [{"action": "停机更换", "citations": [], "risk": "high"}]},
                            ensure_ascii=False)
    fake = _FakeClient([_FakeResult(tool_calls=[_FakeCall(
        "query_graph", {"start_node": "PUMP-A-01", "depth": 2})]),
        _FakeResult(content=final_json)])
    rec = run_case(case, client=fake, tag="selftest", repeat=1, system_prompt=system_prompt,
                   tools=tools, max_steps=3, timeout=5.0, budget=None, model="fake")
    judged = jt.judge_record(rec, schemas)
    if not judged["success"]:
        failures.append(f"正常路径应判通过：{judged['failure']} {judged['call_issues']}")
    if rec["result"]["llm_calls"] != 2:
        failures.append(f"应 2 次 LLM 调用，实际 {rec['result']['llm_calls']}")
    if not rec["result"]["json_parse_ok"]:
        failures.append("收口 JSON 应可解析")
    if rec["result"]["guard_violations"]:
        failures.append("正常路径不应有护栏违规")

    # 2) 模型幻觉调用写操作 → 被产品护栏拦截，记 write_guard，不中断循环
    fake2 = _FakeClient([_FakeResult(tool_calls=[_FakeCall("generate_report", {"device_id": "X"})]),
                         _FakeResult(content=final_json)])
    rec2 = run_case(case, client=fake2, tag="selftest", repeat=1, system_prompt=system_prompt,
                    tools=tools, max_steps=3, timeout=5.0, budget=None, model="fake")
    kinds = [v["kind"] for v in rec2["result"]["guard_violations"]]
    if "write_guard" not in kinds:
        failures.append(f"写操作应被护栏拦截并记 write_guard，实际 {kinds}")
    # 拦截 ≠ 免责：模型确实产生了错误调用，本用例应判失败（考点是 query_graph）
    if jt.judge_record(rec2, schemas)["success"]:
        failures.append("越权调用写操作应判失败（护栏只阻止执行，不掩盖选择错误）")

    # 3) 始终调工具 → 达上限后强制收口轮（llm_calls = max_steps + 1）
    fake3 = _FakeClient([_FakeResult(tool_calls=[_FakeCall(
        "query_graph", {"start_node": "PUMP-A-01", "depth": 2})])])
    rec3 = run_case(case, client=fake3, tag="selftest", repeat=1, system_prompt=system_prompt,
                    tools=tools, max_steps=2, timeout=5.0, budget=None, model="fake")
    if not rec3["result"]["forced_final"]:
        failures.append("达步数上限应走强制收口轮")
    if rec3["result"]["llm_calls"] != 3:
        failures.append(f"max_steps=2 应共 3 次 LLM 调用，实际 {rec3['result']['llm_calls']}")

    # 4) 审计必须落到实验路径，不得污染 reports/security_audit.jsonl
    if AUDIT_PATH.exists():
        txt = AUDIT_PATH.read_text(encoding="utf-8")
        if "tool_call" not in txt:
            failures.append("审计未写入实验路径")
    else:
        failures.append("审计未写入实验路径（文件不存在）")

    # 5) v2-① 告警前置：从文本抽设备编号 → 注入最小 AlarmEvent；抽不到则为 None
    al = infer_alarm(case)
    if al is None or al.device_id != "PUMP-A-01" or al.metric != "vib_rms":
        failures.append(f"告警前置应从上下文抽出 PUMP-A-01，实际 {getattr(al, 'device_id', None)!r}")
    if infer_alarm({"case_id": "t-002", "input": "这个标准怎么规定的？", "context": []}) is not None:
        failures.append("无设备编号的用例不应注入告警")
    rec_al = run_case(case, client=_FakeClient([_FakeResult(content=final_json)]),
                      tag="selftest", repeat=1, system_prompt=system_prompt, tools=tools,
                      max_steps=2, timeout=5.0, budget=None, model="fake", alarm=al)
    if (rec_al["result"].get("alarm") or {}).get("device_id") != "PUMP-A-01":
        failures.append("记录里应留下注入的告警事实（可审计）")

    # 6) v2-② 收口形态：自然语言收口不判失败，但必须单列为 natural_language
    table = "| 振动烈度 | 状态 |\n| --- | --- |\n| 4.5 ~ 11.2 | 注意 |"
    fake_nl = _FakeClient([_FakeResult(tool_calls=[_FakeCall(
        "query_graph", {"start_node": "PUMP-A-01", "depth": 2})]),
        _FakeResult(content=table)])
    rec_nl = run_case(case, client=fake_nl, tag="selftest", repeat=1, system_prompt=system_prompt,
                      tools=tools, max_steps=3, timeout=5.0, budget=None, model="fake", alarm=al)
    if rec_nl["result"]["answer_mode"] != "natural_language":
        failures.append(f"表格收口应记 natural_language，实际 {rec_nl['result']['answer_mode']}")
    if rec_nl["result"]["json_parse_ok"]:
        failures.append("表格收口不应被记为 JSON 收口")
    if not jt.judge_record(rec_nl, schemas)["success"]:
        failures.append("自然语言收口不得因此判失败（收口形态不进六档）")
    if answer_mode_of(True, "") != "json" or answer_mode_of(False, "") != "none":
        failures.append("answer_mode_of 边界错误（json/none）")

    if failures:
        for f in failures:
            print("[SELFTEST-FAIL]", f)
        return 1
    print("[SELFTEST-OK] run_agent_gate v2：工具面/循环/护栏/强制收口/审计重定向/"
          "告警前置/收口形态 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
