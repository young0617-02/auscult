"""V1 实验执行器（T2.1 / T2.3）

对应交付物：`p0-plan-detailed-d1-d10.md` §三 D2–D3 · T2.1 / T2.3
判据依据：`reports/p0-report-v1-tool-call.md` §3.3、§7.1 ｜ 提示词：`prompts/tool_call_prompt_v1.md`
实验登记：`docs/prj-template-experiment-log.md`（raw 落盘与断点续跑纪律）

执行口径（与上游计划 §四 V1 逐字对齐）：
  - 默认 2 个本地模型 × 20 用例 × 3 次重复 = 120 次；云端 baseline 可选（+20 次）；
  - 固定参数 temperature=0 / seed=42 / num_ctx=8192 / top_p=1.0 / max_tokens=1024 / stream=false，
    由脚本默认值写死并**在开跑前打印**，防止静默漂移；
  - 重试上限 3 次，重试时把**校验错误回灌**给模型（R-V1 参数类失败的主要对策）；
  - `think` 剥离由 `llm_adapter` 强制完成，**先剥离再判 JSON**（R-V1-1）；
  - 原始响应逐条 append 落盘，**只增不改**；中断后 `--resume` 跳过已完成组续跑。

原始数据落盘路径（必须位于 experiments/**/raw/）：
  experiments/v1/raw/EXP-V1-001.jsonl

自检：`python scripts/run_v1.py --selftest`
用法：`python scripts/run_v1.py --models qwen2.5:7b,deepseek-r1:7b --repeat 3 --seed 42 \
        --num-ctx 8192 --temperature 0.0 --prompt prompts/tool_call_prompt_v1.md \
        --out experiments/v1/raw/EXP-V1-001.jsonl`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge_tools                                                    # noqa: E402
import gbnf_grammar                                                    # noqa: E402
import llm_adapter                                                    # noqa: E402
from llm_adapter import AdapterResult, LLMAdapter                     # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "evals" / "v1_cases.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "experiments" / "v1" / "raw" / "EXP-V1-001.jsonl"
DEFAULT_MODELS = "qwen2.5:7b,deepseek-r1:7b"

MAX_RETRY = judge_tools.MAX_RETRY          # 3
RETRY_FEEDBACK_TEMPLATE = (
    "上一次回复未通过工具调用校验，问题如下：\n{issues}\n"
    "请只输出修正后的工具调用（JSON 数组或标准 tool_calls），不要任何解释性文字。"
)


# ---------------------------------------------------------------- 用例加载


def load_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def history_of(case: dict[str, Any]) -> list[dict[str, str]] | None:
    """多轮用例的 `context` 转为 messages 历史（仅保留 user/assistant 两角色）。"""
    context = case.get("context")
    if not context:
        return None
    history: list[dict[str, str]] = []
    for turn in context:
        role = turn.get("role")
        if role in ("user", "assistant") and turn.get("content"):
            history.append({"role": role, "content": str(turn["content"])})
    return history or None


# ---------------------------------------------------------------- 断点续跑


def done_groups(raw_path: Path) -> set[tuple[str, str, int]]:
    """扫描已落盘 JSONL，返回已完成的 (case_id, model, repeat) 组集合。

    组内只要有记录即视为已完成（组是最小续跑单位，避免重复与半组数据混算）。
    """
    if not raw_path.exists():
        return set()
    done: set[tuple[str, str, int]] = set()
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        done.add((rec["expected"]["case_id"], rec["model"], int(rec.get("repeat", 1))))
    return done


def append_record(raw_path: Path, record: dict[str, Any]) -> None:
    """逐条 append 落盘（只增不改）。"""
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()


# ---------------------------------------------------------------- 校验回灌


def validation_issues(case: dict[str, Any], result: AdapterResult,
                      schemas: dict[str, dict[str, Any]]) -> list[str]:
    """复用判分器的口径生成「校验错误回灌」文本（与最终判分同一套规则）。

    口径一致性：`match_expected_calls` 必须带上用例的 `lenient_param_defaults`，
    否则回灌会因"语义缺省"口径差异产生判分器认为已通过的伪错误，触发无谓重试
    （见 `judge_tools.judge_record` 的同一调用）。
    """
    if result.error:
        return [f"请求失败：{result.error}"]
    if not result.tool_calls:
        return ["没有产出任何工具调用（tool_calls 为空）"]

    issues: list[str] = []
    for call in result.tool_calls:
        tool_schema = schemas.get(call.name)
        if tool_schema is None:
            issues.append(f"工具名 {call.name!r} 不在允许的 {len(schemas)} 个工具内")
            continue
        if call.arguments is None:
            issues.append(f"{call.name} 的 arguments 不是合法 JSON 对象"
                          f"（{call.arguments_parse_error}）")
            continue
        issues.extend(judge_tools.validate(tool_schema, call.arguments, f"$.{call.name}"))

    expected_calls = case.get("expected_tool_calls", [])
    forbidden = [str(x) for x in (case.get("forbidden_tool_calls") or [])]
    if case.get("expect_reject"):
        issues.append("该问题信息不足或超出范围，不应调用任何工具")
    elif forbidden:
        # 禁调用例（2026-10-20 v1-019 重释义）：只回报被禁调用，不要求正向匹配
        hit = [c.name for c in result.tool_calls if c.name in forbidden]
        if hit:
            issues.append("写操作不在图内执行，不得调用：%s；报告生成由系统在审核后完成"
                          % "、".join(sorted(set(hit))))
    else:
        ok, call_issues = judge_tools.match_expected_calls(
            expected_calls,
            [{"name": c.name, "arguments": c.arguments} for c in result.tool_calls],
            schemas,
            case.get("lenient_param_defaults") or {},
        )
        if not ok:
            issues.extend(call_issues)
    return issues


def build_retry_messages(messages: list[dict[str, str]], result: AdapterResult,
                         issues: list[str]) -> list[dict[str, str]]:
    """在既有对话后追加「模型上次回复 + 校验反馈」，形成回灌后的新请求。"""
    return messages + [
        {"role": "assistant", "content": result.content_clean or result.content_raw or "(空)"},
        {"role": "user", "content": RETRY_FEEDBACK_TEMPLATE.format(
            issues="\n".join(f"- {i}" for i in issues))},
    ]


# ---------------------------------------------------------------- 单组执行


def run_group(adapter: LLMAdapter, model: str, case: dict[str, Any], repeat: int,
              tag: str, cold_start: bool, schemas: dict[str, dict[str, Any]],
              max_retry: int, raw_path: Path, verbose: bool,
              grammar: dict | None = None,
              tool_choice: str = llm_adapter.DEFAULT_TOOL_CHOICE) -> list[dict[str, Any]]:
    """跑一个 (用例, 模型, 重复序) 组，含重试；逐条落盘并返回本轮记录。"""
    messages = llm_adapter.build_messages(
        case["input"], history=history_of(case), fewshot=True,
        system_prompt=adapter.system_prompt,
        prompt_path=adapter.prompt_path,   # 修缺陷：few-shot 须与 --prompt 同源
    )
    # 约束解码：expect_reject 用例不施加工具调用数组语法（应不调用工具），其余用例按需约束
    adapter.grammar = None if case.get("expect_reject") else grammar
    # H5 / ISS-027：tool_choice="required" 会**强制**产生工具调用 → 对 expect_reject 用例必须
    # 回退为 auto，否则"应拒绝"判据会被通道本身破坏（强行调用 → 误判「该拒绝却调用」）。
    # 每个用例入口都显式重设，故无需恢复。
    adapter.tool_choice = (llm_adapter.DEFAULT_TOOL_CHOICE if case.get("expect_reject")
                           else tool_choice)
    records: list[dict[str, Any]] = []

    for attempt in range(1, max_retry + 1):
        result = adapter.chat(messages, model=model)
        record = {
            "expected": case,
            "result": result.to_raw(),
            "model": model,
            "repeat": repeat,
            "attempt": attempt,
            "tag": tag,
            "cold_start": bool(cold_start and attempt == 1),
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        judged = judge_tools.judge_record(record, schemas)
        record["judged_success"] = judged["success"]
        records.append(record)
        append_record(raw_path, record)

        if verbose:
            mark = "OK " if judged["success"] else "FAIL"
            print(f"    [{mark}] {case['case_id']} {model} repeat={repeat} "
                  f"attempt={attempt} latency={result.latency_ms:.0f}ms "
                  f"failure={judged['failure'] or '-'}")

        if judged["success"] or attempt >= max_retry:
            break

        issues = validation_issues(case, result, schemas)
        if not issues:
            break                          # 判分失败但无法生成具体反馈，避免无效重试
        messages = build_retry_messages(messages, result, issues)
    return records


# ---------------------------------------------------------------- 步骤链执行（D4 / P6 拆步）

# 步骤链模式下追加到本轮输入末尾的执行约束（提示词层面，配合 tool_call_step_prompt_v1.md）
STEP_CHAIN_INSTRUCTION = (
    "\n\n【分步执行】请只输出一个工具调用；若所需工具都已调用完毕，输出空数组 []。"
)
# 上一步的 mock 工具结果回灌模板（Phase 0 无真实工具后端，仅用于驱动下一步）
STEP_CHAIN_FOLLOWUP = (
    "[系统回灌] 步骤 {step} 已完成，工具 {name} 返回：{result}"
    "请继续：本次只输出下一个需要调用的工具；若已全部完成，输出 []。"
)
# 各工具的 mock 返回（中性、不泄漏期望参数值，仅提供「已执行」信号）
MOCK_TOOL_RESULTS: dict[str, str] = {
    "query_sensor": "查询成功，返回若干条时序聚合结果。",
    "search_knowledge": "检索成功，返回若干条知识片段。",
    "query_graph": "查询成功，返回若干条拓扑关系。",
    "get_maintenance_history": "查询成功，返回若干条历史工单。",
    "generate_report": "报告已生成（图外执行）。",
}


def run_step_chain_group(adapter: LLMAdapter, model: str, case: dict[str, Any], repeat: int,
                         tag: str, cold_start: bool, schemas: dict[str, dict[str, Any]],
                         raw_path: Path, verbose: bool, grammar: dict | None = None,
                         step_prompt_path: Path | None = None,
                         schema_path: Path | None = None,
                         tool_choice: str = llm_adapter.DEFAULT_TOOL_CHOICE) -> list[dict[str, Any]]:
    """D4（P6 拆步）：把多工具用例拆成「按序的单工具步骤」，逐步驱动并落盘。

    与 `run_group` 的差别：
      - 每次只期望**一个**工具调用；上一步以 mock tool result 回灌为下一步上下文；
      - 终止条件：模型某步不产出工具调用（含输出 `[]`），或达
        `max_steps = 期望步数 + 1`（防死循环）；
      - **不启用重试**（链式重试语义复杂；判据取「首次成功率」口径），`attempt` 固定 1。
    """
    expected = case.get("expected_tool_calls", [])
    max_steps = len(expected) + 1
    system_prompt = None
    if step_prompt_path is not None:
        system_prompt = llm_adapter.load_system_prompt(step_prompt_path, schema_path)
    messages = llm_adapter.build_messages(
        case["input"] + STEP_CHAIN_INSTRUCTION,
        history=history_of(case), fewshot=True,
        system_prompt=system_prompt or adapter.system_prompt,
        prompt_path=step_prompt_path or adapter.prompt_path,   # few-shot 与 step 提示词同源
    )
    adapter.grammar = grammar
    adapter.tool_choice = (llm_adapter.DEFAULT_TOOL_CHOICE if case.get("expect_reject")
                           else tool_choice)

    steps: list[dict[str, Any]] = []
    total_latency = 0.0
    total_completion: int | None = None
    total_think: int | None = None
    token_source = "usage"
    error: str | None = None

    for step in range(1, max_steps + 1):
        result = adapter.chat(messages, model=model)
        total_latency += result.latency_ms
        if result.completion_tokens:
            total_completion = (total_completion or 0) + result.completion_tokens
        if result.think_tokens:
            total_think = (total_think or 0) + result.think_tokens
        if result.token_source == "char_fallback":
            token_source = "char_fallback"
        if result.error:
            error = result.error
        steps.append({
            "step": step,
            "tool_calls": [
                {"name": c.name, "arguments": c.arguments,
                 "raw_arguments": c.raw_arguments,
                 "arguments_parse_error": c.arguments_parse_error}
                for c in result.tool_calls
            ],
            "content_clean": result.content_clean,
            "latency_ms": round(result.latency_ms, 3),
        })
        if verbose:
            names = ",".join(c.name for c in result.tool_calls) or "(无/[])"
            print(f"    [step {step}] {case['case_id']} {model} repeat={repeat} "
                  f"tools={names} latency={result.latency_ms:.0f}ms")
        if error or not result.tool_calls:
            break                              # 链结束（含模型输出 [] 表示完成）
        name = result.tool_calls[0].name
        messages = messages + [
            {"role": "assistant",
             "content": result.content_clean or result.content_raw or "[]"},
            {"role": "user", "content": STEP_CHAIN_FOLLOWUP.format(
                step=step, name=name,
                result=MOCK_TOOL_RESULTS.get(name, "查询成功。"))},
        ]

    flat = [c for s in steps for c in s["tool_calls"]]
    record = {
        "expected": case,
        "result": {
            "mode": "step_chain",
            "steps": steps,
            "tool_calls": flat,                # 展平，供 schema_valid 与集合覆盖复用
            "tool_calls_missing": not flat,
            "latency_ms": round(total_latency, 3),
            "completion_tokens": total_completion,
            "think_tokens": total_think,
            "token_source": token_source,
            "error": error,
        },
        "model": model,
        "repeat": repeat,
        "attempt": 1,
        "tag": tag,
        "cold_start": bool(cold_start),
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    judged = judge_tools.judge_record(record, schemas)
    record["judged_success"] = judged["success"]
    append_record(raw_path, record)
    if verbose:
        mark = "OK " if judged["success"] else "FAIL"
        print(f"    [{mark}] {case['case_id']} {model} repeat={repeat} 步骤链 "
              f"steps={judged['steps_passed']}/{judged['steps_total']} "
              f"failure={judged['failure'] or '-'}")
    return [record]


# ---------------------------------------------------------------- 元数据


def git_commit() -> str:
    """取当前 commit（短 hash）；有未提交改动时前缀 dirty-。"""
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:                                             # noqa: BLE001 - 非 git 环境
        return "no-git"
    if not commit:
        return "no-git"
    return f"dirty-{commit}" if dirty else commit


def file_sha256(path: Path | None) -> str | None:
    """实验输入的**内容指纹**（ISS-034 / ISS-033）。

    动机：`prompt_version` / `cases` 只记录**路径**，一旦文件被改名、覆盖或替换，
    事后**无法自证实验当时的输入是什么**（2026-10-06 的 `ISS-033` 命名事故即因此暴露）。
    故对提示词 / 用例集 / Schema 一律落盘 sha256，事后可逐字节校验。
    """
    if path is None or not Path(path).exists():
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_meta(meta_path: Path, meta: dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[run_v1] 实验元数据已写入 {meta_path}")


def parse_models(spec: str) -> list[tuple[str, str | None]]:
    """解析 `--models`：每项为 `模型名` 或 `模型名@endpoint`（云端 baseline 用后者）。"""
    models: list[tuple[str, str | None]] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, _, endpoint = item.partition("@")
        models.append((name.strip(), endpoint.strip() or None))
    return models


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    failures: list[str] = []
    schemas = judge_tools.load_tool_schemas()

    cases = load_cases()
    if len(cases) != 20:
        failures.append(f"用例数应为 20，实际 {len(cases)}")
    if len({c["case_id"] for c in cases}) != len(cases):
        failures.append("用例 case_id 存在重复")
    if not all("expected_tool_calls" in c for c in cases):
        failures.append("用例缺少 expected_tool_calls 字段")

    # 多轮用例必须带 context，且能被转成 messages 历史
    multi = [c for c in cases if c["type"] == "多轮"]
    if not multi:
        failures.append("用例集缺少「多轮」类型")
    for case in multi:
        if not history_of(case):
            failures.append(f"{case['case_id']} 为多轮用例但 context 无法转为历史")

    # 模型规格解析
    if parse_models("a@http://x/y,b") != [("a", "http://x/y"), ("b", None)]:
        failures.append("--models 规格解析错误")

    # 校验回灌：坏参数应生成非空问题列表，且反馈文本含问题项
    case = next(c for c in cases if c["type"] == "单工具")
    bad = AdapterResult(model="mock", content_raw="", content_clean="",
                        think_text="", tool_calls_missing=True)
    issues = validation_issues(case, bad, schemas)
    if not issues:
        failures.append("空 tool_calls 未生成校验反馈")
    fb = build_retry_messages([{"role": "user", "content": "x"}], bad, issues)[-1]["content"]
    if "未通过工具调用校验" not in fb or "- " not in fb:
        failures.append("重试反馈文本格式错误")

    # 断点续跑键
    tmp = PROJECT_ROOT / "experiments" / "v1" / "raw" / "_selftest_resume.jsonl"
    try:
        append_record(tmp, {"expected": {"case_id": "v1-001"}, "model": "m", "repeat": 1})
        if ("v1-001", "m", 1) not in done_groups(tmp):
            failures.append("断点续跑键识别失败")
    finally:
        tmp.unlink(missing_ok=True)

    # 步骤链（D4 / P6 拆步）：v3 用例集可加载、step_chain 用例存在、step 提示词可解析
    v3_path = PROJECT_ROOT / "evals" / "v3_cases.jsonl"
    if v3_path.exists():
        v3_cases = load_cases(v3_path)
        sc_cases = [c for c in v3_cases if c.get("execution_mode") == "step_chain"]
        if not sc_cases:
            failures.append("v3 用例集缺少 execution_mode=step_chain 用例")
        if any(c.get("expect_reject") for c in sc_cases):
            failures.append("步骤链用例不应为 expect_reject（链式拒止不在本口径内）")
        step_prompt = PROJECT_ROOT / "prompts" / "tool_call_step_prompt_v1.md"
        try:
            sp = llm_adapter.load_system_prompt(step_prompt)
            fs = llm_adapter.load_fewshot(step_prompt)
        except Exception as exc:                                       # noqa: BLE001
            failures.append(f"步骤链提示词解析失败：{type(exc).__name__}: {exc}")
        else:
            if "本次回复只输出一个工具调用" not in sp:
                failures.append("步骤链 System Prompt 缺少「只输出一个工具」规则")
            if len(fs) < 4:
                failures.append(f"步骤链 few-shot 条数异常（{len(fs) // 2} 条对）")

    if failures:
        print("[FAIL] run_v1 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] run_v1 自检通过：用例集 / 多轮历史 / 模型规格 / 校验回灌 / 断点续跑键 / "
          "步骤链（v3 用例 + step 提示词）")
    return 0


# ---------------------------------------------------------------- 入口


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V1 实验执行器（T2.1 / T2.3）")
    parser.add_argument("--models", default=DEFAULT_MODELS,
                        help="模型列表，逗号分隔；云端 baseline 用 `模型名@endpoint`")
    parser.add_argument("--repeat", type=int, default=3, help="每个用例重复次数（默认 3）")
    parser.add_argument("--tag", default="main",
                        help="实验标签，如 main / constrained-decoding / fewshot-8")
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="用例 JSONL")
    parser.add_argument("--schema", type=Path, default=llm_adapter.SCHEMA_PATH,
                        help="工具 Schema v1（程序化注入提示词与 tools 字段）")
    parser.add_argument("--prompt", type=Path, default=llm_adapter.PROMPT_PATH,
                        help="提示词文件（v1 固定输入，改动须升版）")
    parser.add_argument("--prompt-step", type=Path,
                        default=PROJECT_ROOT / "prompts" / "tool_call_step_prompt_v1.md",
                        help="步骤链用例（execution_mode=step_chain）使用的提示词文件")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="原始结果 JSONL（必须位于 experiments/**/raw/）")
    parser.add_argument("--resume", action="store_true",
                        help="断点续跑：跳过已落盘的 (用例, 模型, 重复序) 组")
    parser.add_argument("--max-retry", type=int, default=MAX_RETRY,
                        help="单组重试上限（含首次，默认 3）")
    parser.add_argument("--seed", type=int, default=llm_adapter.DEFAULT_SEED)
    parser.add_argument("--num-ctx", type=int, default=llm_adapter.DEFAULT_NUM_CTX)
    parser.add_argument("--temperature", type=float, default=llm_adapter.DEFAULT_TEMPERATURE)
    parser.add_argument("--top-p", type=float, default=llm_adapter.DEFAULT_TOP_P)
    parser.add_argument("--max-tokens", type=int, default=llm_adapter.DEFAULT_MAX_TOKENS)
    parser.add_argument("--endpoint", default=llm_adapter.DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=float, default=300.0, help="单次请求超时（秒）")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY",
                        help="云端 baseline 的 API Key 环境变量名")
    parser.add_argument("--warm", action="store_true",
                        help="全部记为热启动（默认每个模型本轮首次调用记为冷启动）")
    parser.add_argument("--dry-run", action="store_true", help="只打印执行计划，不发请求")
    parser.add_argument("--constrain", action="store_true",
                        help="步骤① 约束解码：用 gbnf_grammar 生成的 JSON Schema"
                             "（走 Ollama 原生 /api/chat + format 结构化输出）"
                             "约束工具调用输出为合法 JSON 数组")
    parser.add_argument("--transport", choices=("auto", "response_format", "tools"),
                        default="auto",
                        help="工具调用通道（H5 / ISS-027 / R-V1-9）："
                             "auto=保持既有行为（云端 response_format json_schema；"
                             "本地 Ollama 原生 format）；"
                             "response_format=显式声明走约束解码；"
                             "tools=云端改走 OpenAI 原生 function calling"
                             "（发送 tools + tool_choice=auto，不使用 response_format），"
                             "输出落在标准 message.tool_calls 字段，"
                             "用于消除 response_format 未被强制导致的「裸 arguments」形态漂移。"
                             "注意：tool_choice=required 实测不被 provider 支持（返回空），"
                             "本执行器一律用 auto")
    parser.add_argument("--quiet", action="store_true", help="不打印逐条进度")
    parser.add_argument("--selftest", action="store_true", help="运行执行器自检（不联网）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if "raw" not in args.out.parts:
        parser.error(f"--out 必须位于 experiments/**/raw/ 下（当前：{args.out}）")

    schemas = judge_tools.load_tool_schemas(args.schema)
    cases = load_cases(args.cases)
    models = parse_models(args.models)
    if not models:
        parser.error("--models 为空")

    # --transport tools（H5）：云端改走原生 function calling，不使用 response_format，
    # 因此无需构建约束 grammar（构建了也不会被发送，且会让 describe 误报为"已约束"）。
    use_native_tools = args.transport == "tools"
    grammar: dict | None = None
    if args.constrain and use_native_tools:
        print("[transport] tools 优先：本次不使用 response_format 约束解码，"
              "改走 tools + tool_choice=auto（--constrain 的 grammar 不构建）")
    if args.constrain and not use_native_tools:
        try:
            grammar = gbnf_grammar.generate_grammar(args.schema)
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            parser.error(f"--constrain 生成约束 JSON Schema 失败：{type(exc).__name__}: {exc}")
        if not grammar.get("items", {}).get("oneOf"):
            parser.error("--constrain 生成的约束 JSON Schema 不含任何工具分支")

    total_groups = len(models) * len(cases) * args.repeat
    print("=" * 72)
    print("V1 实验执行器 —— 固定参数（防止静默漂移）")
    print("=" * 72)
    print(f"models    : {', '.join(m for m, _ in models)}")
    print(f"cases     : {len(cases)} 条（{args.cases}）")
    print(f"repeat    : {args.repeat}  → 计划 {total_groups} 组，最多 "
          f"{total_groups * args.max_retry} 次调用")
    print(f"temperature={args.temperature} seed={args.seed} num_ctx={args.num_ctx} "
          f"top_p={args.top_p} max_tokens={args.max_tokens} stream=False")
    print(f"prompt    : {args.prompt}")
    print(f"prompt步链: {args.prompt_step}")
    print(f"schema    : {args.schema}")
    print(f"out       : {args.out}")
    print(f"tag       : {args.tag} ｜ resume={args.resume} ｜ max_retry={args.max_retry}"
          f" ｜ constrain={args.constrain} ｜ transport={args.transport}")
    if not args.warm:
        print("提示：默认把每个模型本轮第 1 次调用记为冷启动；如需严格冷启动，"
              "请先执行 `ollama stop <model>` 再开跑。")

    if args.dry_run:
        print("\n[dry-run] 首个用例的首个模型消息预览：")
        adapter = LLMAdapter(endpoint=args.endpoint, temperature=args.temperature,
                             seed=args.seed, num_ctx=args.num_ctx, top_p=args.top_p,
                             max_tokens=args.max_tokens, timeout_s=args.timeout,
                             schema_path=args.schema, prompt_path=args.prompt,
                             grammar=grammar)
        for msg in llm_adapter.build_messages(
                cases[0]["input"], history=history_of(cases[0]), fewshot=True,
                system_prompt=adapter.system_prompt, prompt_path=args.prompt)[:3]:
            preview = msg["content"][:120].replace("\n", " ")
            print(f"  - {msg['role']}: {preview}...")
        return 0

    done = done_groups(args.out) if args.resume else set()
    if args.resume:
        print(f"[resume] 已有 {len(done)} 组完成，将跳过")

    started_at = time.perf_counter()
    executed_groups = 0
    skipped_groups = 0
    all_records: list[dict[str, Any]] = []

    for model, endpoint in models:
        # 通道选择：`模型名@endpoint` 形式（云端 baseline）走 OpenAI 兼容端点的
        # response_format json_schema；否则走 Ollama 原生 /api/chat 的 format。
        # 若不区分，云端 endpoint 会被 _chat_native 改写成 `<base>/api/chat` 导致 404。
        is_cloud = bool(endpoint)
        # H5 / ISS-027：tools 通道固定 tool_choice="auto"
        # （实测 "required" 不被 ModelScope provider 支持 → HTTP 200 但内容为空，故不用）
        transport_tool_choice = llm_adapter.DEFAULT_TOOL_CHOICE
        adapter = LLMAdapter(
            endpoint=endpoint or args.endpoint,
            temperature=args.temperature, seed=args.seed, num_ctx=args.num_ctx,
            top_p=args.top_p, max_tokens=args.max_tokens, timeout_s=args.timeout,
            api_key=os.environ.get(args.api_key_env) if is_cloud else None,
            schema_path=args.schema, prompt_path=args.prompt,
            grammar=grammar,
            structured_output=is_cloud and bool(grammar),
            tool_choice=transport_tool_choice,
        )
        print("\n" + "-" * 72)
        print(f"模型：{model}（endpoint={adapter.endpoint}）")
        print("-" * 72)
        first_call = True
        for case in cases:
            for repeat in range(1, args.repeat + 1):
                if (case["case_id"], model, repeat) in done:
                    skipped_groups += 1
                    continue
                cold = first_call and not args.warm
                first_call = False
                executed_groups += 1
                if not args.quiet:
                    print(f"  {case['case_id']} repeat={repeat} "
                          f"({'cold' if cold else 'warm'})")
                # D4（P6 拆步）：execution_mode=step_chain 的用例走逐步驱动；
                # 其余用例路径不变（零回归）。
                if case.get("execution_mode") == "step_chain":
                    all_records.extend(run_step_chain_group(
                        adapter, model, case, repeat, args.tag, cold, schemas,
                        args.out, verbose=not args.quiet, grammar=grammar,
                        step_prompt_path=args.prompt_step, schema_path=args.schema,
                        tool_choice=transport_tool_choice,
                    ))
                else:
                    all_records.extend(run_group(
                        adapter, model, case, repeat, args.tag, cold, schemas,
                        args.max_retry, args.out, verbose=not args.quiet,
                        grammar=grammar, tool_choice=transport_tool_choice,
                    ))

    judged = [judge_tools.judge_record(r, schemas) for r in all_records]
    summary = judge_tools.aggregate(judged) if judged else {}

    meta = {
        "experiment_id": args.out.stem,
        "date": datetime.now().astimezone().date().isoformat(),
        "phase_item": "V1",
        "models": [m for m, _ in models],
        "endpoints": {m: (e or args.endpoint) for m, e in models},
        "cases": str(args.cases.resolve().relative_to(PROJECT_ROOT)),
        "repeat": args.repeat,
        "tag": args.tag,
        "constrain": args.constrain,
        "transport": args.transport,
        "tool_choice": llm_adapter.DEFAULT_TOOL_CHOICE,
        "max_retry": args.max_retry,
        "seed": args.seed,
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "stream": False,
        "prompt_version": str(args.prompt.resolve().relative_to(PROJECT_ROOT)),
        "prompt_step_version": (str(args.prompt_step.resolve().relative_to(PROJECT_ROOT))
                                if args.prompt_step else None),
        "step_chain_cases": sum(1 for c in cases if c.get("execution_mode") == "step_chain"),
        "schema_version": args.schema.stem,  # 记录实际使用的 schema 文件名（如 tools_v1 / tools_v2），不再写死
        # ISS-034：实验输入的内容指纹（路径之外的权威标识）—— 改名/覆盖后仍可逐字节自证
        "input_sha256": {
            "prompt": file_sha256(args.prompt),
            "prompt_step": file_sha256(args.prompt_step),
            "cases": file_sha256(args.cases),
            "schema": file_sha256(args.schema),
        },
        "code_commit": git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "raw_data_path": str(args.out.resolve().relative_to(PROJECT_ROOT)),
        "groups_executed": executed_groups,
        "groups_skipped": skipped_groups,
        "records": len(all_records),
        "elapsed_s": round(time.perf_counter() - started_at, 1),
        "summary": summary,
    }
    write_meta(args.out.with_suffix(".meta.json"), meta)

    print("\n" + "=" * 72)
    print(f"完成：执行 {executed_groups} 组（跳过 {skipped_groups} 组），"
          f"落盘 {len(all_records)} 条 → {args.out}")
    print("下一步：python scripts/judge_tools.py "
          f"--raw {args.out} --out experiments/v1/summary.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
