"""R-4 本地证据归纳/诊断 实验执行器（ISS-014 专项）

对应验证项：R-4（读证据 → 写根因/结论 → 带 evidence_refs 引用）
判据依据：`docs/p0-spec-gate-criteria.md` §3.7（R4）｜ 专项登记：`docs/prj-ledger-known-issues.md` ISS-014
提示词：`prompts/r4_prompt_v1.md` ｜ 用例：`evals/r4_cases.jsonl`

易与 V1 执行器耦合，故同构重写而不 import run_v1（避免后续互相牵连）。

⚠️ 合规锁死：R-4 必须本地执行（宿主 Ollama `127.0.0.1:11434`）。`--endpoint` 或
`模型@endpoint` 中任何非本地端点将直接报错退出，**禁用云端 baseline**（不传证据原文上云）。

执行口径：
  - 默认 1 个本地模型 × 20 用例 × repeat=3；固定参数 temperature=0 / seed=42 /
    num_ctx=8192 / top_p=1.0 / max_tokens=1024 / stream=false；
  - `chat(use_tools=False)`：纯生成式归纳，不引导工具调用；
  - `judge_r4.judge_case` 判定失败时，按维度回灌具体问题（引用幻觉 / 漏引 / 根因关键词缺失等）重试，
    上限 `--max-retry`（默认 3）；**首次即幻觉即便重试改正也须单独计数（红线）**；
  - 原始逐条 append 落盘 `experiments/r4/raw/EXP-R4-<序号>.jsonl`（只增不改），`--resume` 断点续跑；
  - 元数据写入同目录 `.meta.json`，字段对齐 `docs/prj-template-experiment-log.md`。

自检：`python scripts/run_r4.py --selftest`
用法：`python scripts/run_r4.py --models qwen2.5:7b --repeat 3 --seed 42 --num-ctx 8192 \
        --temperature 0.0 --prompt prompts/r4_prompt_v1.md --out experiments/r4/raw/EXP-R4-001.jsonl`
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge_r4                                        # noqa: E402
import llm_adapter                                    # noqa: E402
from llm_adapter import LLMAdapter                    # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "evals" / "r4_cases.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "experiments" / "r4" / "raw" / "EXP-R4-001.jsonl"
DEFAULT_MODELS = "qwen2.5:7b"
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
MAX_RETRY = 3
RETRY_FEEDBACK_TEMPLATE = (
    "上一次回复未通过诊断归纳校验，问题如下：\n{issues}\n"
    "请只输出修正后的 generate_report 参数 JSON，不要任何解释性文字或代码块围栏。"
)


# ---------------------------------------------------------------- 模型解析


def parse_models(spec: str) -> list[tuple[str, str | None]]:
    models: list[tuple[str, str | None]] = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        name, _, endpoint = item.partition("@")
        models.append((name.strip(), endpoint.strip() or None))
    return models


def _host_of_endpoint(endpoint: str) -> str:
    m = re.match(r"https?://([^:/]+)", endpoint)
    return (m.group(1) if m else endpoint).strip()


def enforce_local_endpoint(models: list[tuple[str, str | None]],
                           default_endpoint: str) -> None:
    """合规锁死：R-4 只允许本地端点，否则报错退出（禁用云端）。"""
    for name, endpoint in models:
        ep = endpoint or default_endpoint
        host = _host_of_endpoint(ep)
        if host not in LOCAL_HOSTS:
            print(f"[FAIL] R-4 合规锁死本地，禁止非本地端点：{name} → {ep}（host={host}）")
            sys.exit(2)
    if _host_of_endpoint(default_endpoint) not in LOCAL_HOSTS:
        print(f"[FAIL] R-4 合规锁死本地，默认端点非法：{default_endpoint}")
        sys.exit(2)


# ---------------------------------------------------------------- 断点续跑


def done_groups(raw_path: Path) -> set[tuple[str, str, int]]:
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
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()


# ---------------------------------------------------------------- 回灌


def feed_back_issues(case: dict[str, Any], output: dict[str, Any] | None,
                     judged: dict[str, Any]) -> list[str]:
    """由判分明细生成可执行的回灌反馈（与最终判分同一套规则）。"""
    issues: list[str] = []
    if judged.get("_reason"):
        issues.append(f"请求失败：{judged['_reason']}")
    if not judged["structure_ok"]:
        issues.append("输出不是合法的 generate_report 参数 JSON（需含 diagnosis_summary[10-2000] / "
                      "非空 evidence_refs / severity(info, warning, critical) / "
                      "非空 recommended_actions / idempotency_key[8-64 位字母数字下划线连字符]）")
    for ref in judged.get("hallucinated_refs", []):
        issues.append(f"evidence_refs 引用了证据包之外的 ref：{ref}。只能逐字引用包内真实条目的 ref。")
    for ref in judged.get("over_cited", []):
        issues.append(f"evidence_refs 引用了与根因无关的干扰项 ref：{ref}。请移除。")
    for ref in judged.get("missed", []):
        issues.append(f"支撑根因的 expected ref 未引用：{ref}。请补充引用。")
    if not judged["root_cause_ok"]:
        kw = case.get("golden", {}).get("root_cause_keywords", [])
        issues.append(f"diagnosis_summary 需包含根因关键词：{kw}。")
    if not judged["severity_ok"]:
        issues.append(f"severity 应为 {case.get('golden', {}).get('severity')!r}。")
    if not judged["actions_ok"]:
        issues.append("recommended_actions 不能为空。")
    return issues


def build_retry_messages(messages: list[dict[str, str]], result,
                         issues: list[str]) -> list[dict[str, str]]:
    clean = getattr(result, "content_clean", None) or getattr(result, "content_raw", "") or ""
    return messages + [
        {"role": "assistant", "content": clean or "(空)"},
        {"role": "user", "content": RETRY_FEEDBACK_TEMPLATE.format(
            issues="\n".join(f"- {i}" for i in issues))},
    ]


# ---------------------------------------------------------------- 单组执行


def run_group(adapter: LLMAdapter, model: str, case: dict[str, Any], repeat: int,
              system_prompt: str, prompt_path: Path, max_retry: int, raw_path: Path,
              verbose: bool) -> list[dict[str, Any]]:
    messages = judge_r4.build_r4_messages(case, system_prompt, fewshot=True,
                                          prompt_path=prompt_path)
    records: list[dict[str, Any]] = []
    for attempt in range(1, max_retry + 1):
        result = adapter.chat(messages, model=model, use_tools=False)
        output_txt = result.content_clean or result.content_raw or ""
        output, _parse_err = judge_r4.parse_report_args(output_txt)
        judged = judge_r4.judge_case(case, output, result.to_raw())
        record = {
            "expected": case,
            "result": result.to_raw(),
            "model": model,
            "repeat": repeat,
            "attempt": attempt,
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        record["judged_success"] = judged["success"]
        records.append(record)
        append_record(raw_path, record)

        if verbose:
            mark = "OK " if judged["success"] else "FAIL"
            print(f"    [{mark}] {case['case_id']} repeat={repeat} attempt={attempt} "
                  f"latency={result.latency_ms:.0f}ms failure={judged['failure'] or '-'}")

        if judged["success"] or attempt >= max_retry:
            break
        issues = feed_back_issues(case, output, judged)
        if not issues:
            break
        messages = build_retry_messages(messages, result, issues)
    return records


# ---------------------------------------------------------------- 元数据


def git_commit() -> str:
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:                                    # noqa: BLE001 - 非 git 环境
        return "no-git"
    if not commit:
        return "no-git"
    return f"dirty-{commit}" if dirty else commit


def first_first_success(records: list[dict[str, Any]]) -> float | None:
    """每个 (case,model,repeat) 首次 attempt 即 success 的占比。"""
    firsts = [r for r in records if r.get("attempt") == 1]
    if not firsts:
        return None
    return sum(bool(r.get("judged_success")) for r in firsts) / len(firsts)


def write_meta(meta_path: Path, meta: dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[run_r4] 实验元数据已写入 {meta_path}")


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    failures: list[str] = []
    if parse_models("a@http://127.0.0.1:1,b, c@http://localhost:2") != \
            [("a", "http://127.0.0.1:1"), ("b", None), ("c", "http://localhost:2")]:
        failures.append("--models 规格解析错误")
    try:
        enforce_local_endpoint([("a", "http://127.0.0.1:11434"), ("b", None)], "http://127.0.0.1:11434")
    except SystemExit:
        failures.append("本地端点被误判非法")
    try:
        enforce_local_endpoint([("a", "http://api.cloud.example:8443")], "http://127.0.0.1:11434")
        failures.append("云端端点未被拦截")
    except SystemExit:
        pass

    cases = judge_r4.load_r4_cases()
    tr = {"content_clean": json.dumps(
        {"diagnosis_summary": "驱动端轴承磨损，依据振动。",
         "evidence_refs": [{"type": "sensor", "ref": "PUMP-A-01.vib_x"},
                           {"type": "knowledge", "ref": "doc-fake-oiling"}],
         "severity": "warning", "recommended_actions": ["x"],
         "idempotency_key": "abcDEF12345"})}
    output, _ = judge_r4.parse_report_args(tr["content_clean"])
    judged = judge_r4.judge_case(cases[0], output, tr)
    issues = feed_back_issues(cases[0], output, judged)
    if not any("证据包之外" in i for i in issues):
        failures.append("幻觉回灌文本未含问题项")
    fb = build_retry_messages([{"role": "user", "content": "x"}], type("R", (), {
        "content_clean": tr["content_clean"]})(), issues)[-1]["content"]
    if "未通过诊断归纳校验" not in fb or "- " not in fb:
        failures.append("重试反馈文本格式错误")

    tmp = PROJECT_ROOT / "experiments" / "r4" / "raw" / "_selftest_resume.jsonl"
    try:
        append_record(tmp, {"expected": {"case_id": "r4-001"}, "model": "m", "repeat": 1})
        if ("r4-001", "m", 1) not in done_groups(tmp):
            failures.append("断点续跑键识别失败")
    finally:
        tmp.unlink(missing_ok=True)

    if failures:
        print("[FAIL] run_r4 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] run_r4 自检通过：本地端点强制 / 模型规格 / 回灌文本 / 断点续跑键")
    return 0


# ---------------------------------------------------------------- 入口


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R-4 本地证据归纳/诊断 实验执行器")
    parser.add_argument("--models", default=DEFAULT_MODELS,
                        help="模型列表（逗号分隔）；R-4 仅本地，`@endpoint` 非本地将被拒绝")
    parser.add_argument("--repeat", type=int, default=3, help="每个用例重复次数（默认 3）")
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="用例 JSONL")
    parser.add_argument("--prompt", type=Path, default=judge_r4.PROMPT_PATH,
                        help="R-4 提示词文件")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="原始结果 JSONL（必须位于 experiments/**/raw/）")
    parser.add_argument("--resume", action="store_true", help="断点续跑")
    parser.add_argument("--max-retry", type=int, default=MAX_RETRY, help="单组重试上限（默认 3）")
    parser.add_argument("--seed", type=int, default=llm_adapter.DEFAULT_SEED)
    parser.add_argument("--num-ctx", type=int, default=llm_adapter.DEFAULT_NUM_CTX)
    parser.add_argument("--temperature", type=float, default=llm_adapter.DEFAULT_TEMPERATURE)
    parser.add_argument("--top-p", type=float, default=llm_adapter.DEFAULT_TOP_P)
    parser.add_argument("--max-tokens", type=int, default=llm_adapter.DEFAULT_MAX_TOKENS)
    parser.add_argument("--endpoint", default=llm_adapter.DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=float, default=300.0, help="单次请求超时（秒）")
    parser.add_argument("--dry-run", action="store_true", help="只打印执行计划，不发请求")
    parser.add_argument("--quiet", action="store_true", help="不打印逐条进度")
    parser.add_argument("--selftest", action="store_true", help="运行执行器自检（不联网）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if "raw" not in args.out.parts:
        parser.error(f"--out 必须位于 experiments/**/raw/ 下（当前：{args.out}）")

    models = parse_models(args.models)
    if not models:
        parser.error("--models 为空")
    enforce_local_endpoint(models, args.endpoint)            # 合规锁死本地

    cases = judge_r4.load_r4_cases(args.cases)
    for case in cases:
        errs = judge_r4.validate_case_invariants(case)
        if errs:
            parser.error(f"用例 {case['case_id']} 自检不变量失败：" + "; ".join(errs))

    # 默认仅一个本地模型
    total_groups = len(models) * len(cases) * args.repeat
    print("=" * 72)
    print("R-4 本地证据归纳执行器 —— 固定参数（防止静默漂移）")
    print("=" * 72)
    print(f"models    : {', '.join(m for m, _ in models)}（本地，endpoint={args.endpoint}）")
    print(f"cases     : {len(cases)} 条（{args.cases}）")
    print(f"repeat    : {args.repeat}  → 计划 {total_groups} 组，最多 "
          f"{total_groups * args.max_retry} 次调用")
    print(f"temperature={args.temperature} seed={args.seed} num_ctx={args.num_ctx} "
          f"top_p={args.top_p} max_tokens={args.max_tokens} stream=False")
    print(f"prompt    : {args.prompt}")
    print(f"out       : {args.out}")

    adapter = LLMAdapter(endpoint=args.endpoint, temperature=args.temperature,
                         seed=args.seed, num_ctx=args.num_ctx, top_p=args.top_p,
                         max_tokens=args.max_tokens, timeout_s=args.timeout,
                         schema_path=judge_r4.SCHEMA_PATH,
                         prompt_path=llm_adapter.PROMPT_PATH)   # R-4 自建消息，V1 system 未用
    system_prompt = judge_r4.load_r4_system_prompt(args.prompt, judge_r4.SCHEMA_PATH)

    if args.dry_run:
        print("\n[dry-run] 首个用例消息预览（不发请求）：")
        for msg in judge_r4.build_r4_messages(cases[0], system_prompt, fewshot=True,
                                              prompt_path=args.prompt):
            preview = str(msg["content"])[:120].replace("\n", " ")
            print(f"  - {msg['role']}: {preview}...")
        return 0

    done = done_groups(args.out) if args.resume else set()
    if args.resume:
        print(f"[resume] 已有 {len(done)} 组完成，将跳过")

    started_at = time.perf_counter()
    executed_groups = 0
    skipped_groups = 0
    all_records: list[dict[str, Any]] = []

    for model, _endpoint in models:
        print("\n" + "-" * 72)
        print(f"模型：{model}（endpoint={adapter.endpoint}）")
        print("-" * 72)
        for case in cases:
            for repeat in range(1, args.repeat + 1):
                if (case["case_id"], model, repeat) in done:
                    skipped_groups += 1
                    continue
                executed_groups += 1
                if not args.quiet:
                    print(f"  {case['case_id']} repeat={repeat}")
                all_records.extend(run_group(
                    adapter, model, case, repeat, system_prompt, args.prompt,
                    args.max_retry, args.out, verbose=not args.quiet,
                ))

    meta = {
        "experiment_id": args.out.stem,
        "date": datetime.now().astimezone().date().isoformat(),
        "phase_item": "R-4",
        "models": [m for m, _ in models],
        "endpoints": {m: args.endpoint for m, _ in models},
        "cases": str(args.cases.resolve().relative_to(PROJECT_ROOT)),
        "repeat": args.repeat,
        "max_retry": args.max_retry,
        "seed": args.seed,
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "stream": False,
        "prompt_version": str(args.prompt.resolve().relative_to(PROJECT_ROOT)),
        "schema_version": "tools_v1",
        "code_commit": git_commit(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "raw_data_path": str(args.out.resolve().relative_to(PROJECT_ROOT)),
        "groups_executed": executed_groups,
        "groups_skipped": skipped_groups,
        "records": len(all_records),
        "first_first_success": first_first_success(all_records),
        "conclusion": "【待实测】",
        "elapsed_s": round(time.perf_counter() - started_at, 1),
    }
    write_meta(args.out.with_suffix(".meta.json"), meta)

    print("\n" + "=" * 72)
    print(f"完成：执行 {executed_groups} 组（跳过 {skipped_groups} 组），"
          f"落盘 {len(all_records)} 条 → {args.out}")
    print("下一步：python scripts/judge_r4.py "
          f"--raw {args.out} --out experiments/r4/summary-{args.out.stem}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())