"""Phase 2 W7 `retrieve_knowledge` 云端工具调用评测执行器（对齐 V1 R-2/R-3）

职责与口径：
  - 读取 `evals/v2_retrieve_cases.jsonl`（仅单工具纯检索用例，预期工具一律 `retrieve_knowledge`）；
  - 用 `LLMAdapter(schema_path=schemas/tools_p2_retrieve.json)` 走 OpenAI 兼容 `tools` 通道调用云端
    `Qwen/Qwen3.8-27B`（模型/端点/密钥取自 `env/cloud.json`），固定 seed=42 / temperature=0 对齐 V1；
  - 用 `judge_tools.judge_record(...)` 判分，**让 judge 用 tools_p2_retrieve.json 校验参数**
    （`load_tool_schemas(schema_path)`），再经 `judge_verdict_tiered` 按类型分档；
  - 逐条追加 JSONL 落盘（只增不改），并写 .meta.json 供追溯。

对齐既有 V1 R-2/R-3 判据（`docs/p0-spec-gate-criteria.md` §3.1.2）：
  - 单工具/参数校验/多轮 档 pass ≥85%（条第 ≥90% / 中间 ≥70%）；
  - 判据对象 = 首次成功率（重试后成功率仅作辅助，**本执行器默认不重试**）。

`--selftest`：离线自检，不调用云端；断言用例可读、tools_p2_retrieve 工具 schema 与
`retrieve_knowledge.RETRIEVE_KNOWLEDGE_TOOL` 一致、run_v2 能解析用例。0 失败即通过。

用法：
  python scripts/run_v2_tools.py --selftest
  python scripts/run_v2_tools.py --limit 2
  python scripts/run_v2_tools.py --limit 16 --out experiments/p2/w7/RAW-v2-tools.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge_tools                                                        # noqa: E402
import llm_adapter                                                        # noqa: E402
import retrieve_knowledge                                                 # noqa: E402
from llm_adapter import LLMAdapter                                        # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "evals" / "v2_retrieve_cases.jsonl"
TOOLS_P2_PATH = PROJECT_ROOT / "schemas" / "tools_p2_retrieve.json"
CLOUD_CFG_PATH = PROJECT_ROOT / "env" / "cloud.json"
DEFAULT_OUT = PROJECT_ROOT / "experiments" / "p2" / "w7" / "RAW-v2-tools.jsonl"


# ---------------------------------------------------------------- 用例加载


def load_cases(path: Path) -> list[dict[str, Any]]:
    """按行读取 JSONL 用例；空行跳过。"""
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def load_cloud_config(path: Path = CLOUD_CFG_PATH) -> dict[str, Any]:
    """读取云端连接配置（端点 / 模型 / 密钥）。"""
    return json.loads(path.read_text(encoding="utf-8"))


def history_of(case: dict[str, Any]) -> list[dict[str, str]] | None:
    """多轮用例的 `context` 转 messages 历史（仅 user/assistant 两角色）。"""
    context = case.get("context")
    if not context:
        return None
    history: list[dict[str, str]] = []
    for turn in context:
        role = turn.get("role")
        if role in ("user", "assistant") and turn.get("content"):
            history.append({"role": role, "content": str(turn["content"])})
    return history or None


# ---------------------------------------------------------------- 落盘


def append_record(raw_path: Path, record: dict[str, Any]) -> None:
    """逐条追加落盘（只增不改）。"""
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()


def write_meta(meta_path: Path, meta: dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[run_v2_tools] 实验元数据已写入 {meta_path}")


def file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def git_commit() -> str:
    import subprocess
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=PROJECT_ROOT,
                               capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:                                        # noqa: BLE001 - 非 git 环境
        return "no-git"
    if not commit:
        return "no-git"
    return f"dirty-{commit}" if dirty else commit


# ---------------------------------------------------------------- 主流程


def run_case(adapter: LLMAdapter, model: str, case: dict[str, Any],
             schemas: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """跑单条用例（不重试）：装配消息 → chat → 判分 → 返回(原始记录, 判分明细)。

    judge_record 用传入的 `schemas`（由 tools_p2_retrieve.json 构建）校验参数，
    确保 schema_valid 与 compare_arguments 都按 tools_p2_retrieve 口径执行。
    """
    messages = llm_adapter.build_messages(
        case["input"], history=history_of(case), fewshot=False,
        system_prompt=adapter.system_prompt, prompt_path=adapter.prompt_path,
    )
    # tools_p2_retrieve 提示词默认走 V1 的 system 块（规则"只使用列出工具"为通用约束，注入已切换为 tools_p2_retrieve）
    result = adapter.chat(messages, model=model, use_tools=True)
    record = {
        "expected": case,
        "result": result.to_raw(),
        "model": model,
        "repeat": 1,
        "attempt": 1,
        "tag": "p2-w7-retrieve",
        "cold_start": False,
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    judged = judge_tools.judge_record(record, schemas)
    record["judged_success"] = judged["success"]
    return record, judged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 2 W7 retrieve_knowledge 云端工具调用评测")
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="用例 JSONL")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    parser.add_argument("--model", default=None, help="云端模型名（默认取 env/cloud.json 的 model）")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="原始 JSONL 落盘路径")
    parser.add_argument("--selftest", action="store_true", help="离线自检（不调用云端）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    schemas = judge_tools.load_tool_schemas(TOOLS_P2_PATH)
    cases = load_cases(args.cases)
    if args.limit:
        cases = cases[: args.limit]

    cloud = load_cloud_config()
    endpoint = cloud["endpoint"]
    api_key = cloud.get("api_key") or os.environ.get("OPENAI_API_KEY")
    model = args.model or cloud["model"]

    adapter = LLMAdapter(
        endpoint=endpoint,
        temperature=llm_adapter.DEFAULT_TEMPERATURE,
        seed=llm_adapter.DEFAULT_SEED,
        num_ctx=llm_adapter.DEFAULT_NUM_CTX,
        top_p=llm_adapter.DEFAULT_TOP_P,
        max_tokens=llm_adapter.DEFAULT_MAX_TOKENS,
        timeout_s=300.0,
        api_key=api_key,
        schema_path=TOOLS_P2_PATH,
        prompt_path=llm_adapter.PROMPT_PATH,
        tool_choice=llm_adapter.DEFAULT_TOOL_CHOICE,
    )

    print("=" * 72)
    print("Phase 2 W7 retrieve_knowledge 云端评测 —— 固定参数（对齐 V1）")
    print("=" * 72)
    print(f"model     : {model}（endpoint={endpoint}）")
    print(f"cases     : {len(cases)} 条（{args.cases}）")
    print(f"temperature={llm_adapter.DEFAULT_TEMPERATURE} seed={llm_adapter.DEFAULT_SEED} "
          f"num_ctx={llm_adapter.DEFAULT_NUM_CTX} top_p={llm_adapter.DEFAULT_TOP_P} "
          f"max_tokens={llm_adapter.DEFAULT_MAX_TOKENS}") 
    print(f"schema    : {TOOLS_P2_PATH}")
    print(f"prompt    : {adapter.prompt_path}（few-shot 关闭）")
    print(f"out       : {args.out}")

    started_at = __import__("time").perf_counter()
    judged_rows: list[dict[str, Any]] = []
    for case in cases:
        record, judged = run_case(adapter, model, case, schemas)
        judged_rows.append(judged)
        append_record(args.out, record)
        mark = "OK " if judged["success"] else "FAIL"
        tool_names = ", ".join(c["name"] for c in record["result"]["tool_calls"]) or "(无)"
        print(f"  [{mark}] {judged['case_id']} tools={tool_names} "
              f"failure={judged['failure'] or '-'} latency={record['result']['latency_ms']:.0f}ms")

    # 按类型分档（判据对齐 V1 R-2/R-3，§3.1.2：单工具 pass≥85%）
    first_success_by_type = _first_success_by_type(judged_rows)
    verdicts = judge_tools.judge_verdict_tiered(first_success_by_type)
    for k, v in verdicts.items():
        print(f"  档位 {k}: {v}")
    print(f"  整体裁决: {verdicts.get('整体', '无数据')}")

    meta = {
        "experiment_id": args.out.stem,
        "date": datetime.now().astimezone().date().isoformat(),
        "phase_item": "P2-W7",
        "model": model,
        "endpoint": endpoint,
        "cases": str(args.cases.resolve().relative_to(PROJECT_ROOT)),
        "limit": args.limit,
        "seed": llm_adapter.DEFAULT_SEED,
        "temperature": llm_adapter.DEFAULT_TEMPERATURE,
        "num_ctx": llm_adapter.DEFAULT_NUM_CTX,
        "top_p": llm_adapter.DEFAULT_TOP_P,
        "max_tokens": llm_adapter.DEFAULT_MAX_TOKENS,
        "schema_version": "tools_p2_retrieve",
        "input_sha256": {
            "cases": file_sha256(args.cases),
            "schema": file_sha256(TOOLS_P2_PATH),
            "cloud_cfg": file_sha256(CLOUD_CFG_PATH),
        },
        "code_commit": git_commit(),
        "python": platform.python_version(),
        "records": len(judged_rows),
        "success_count": sum(1 for r in judged_rows if r["success"]),
        "elapsed_s": round(__import__("time").perf_counter() - started_at, 1),
        "summary": judge_tools.aggregate(judged_rows),
        "tiered_verdicts": verdicts,
    }
    write_meta(args.out.with_suffix(".meta.json"), meta)

    print(f"\n完成：{len(cases)} 条，成功 {meta['success_count']} 条 → {args.out}")
    return 0


def _first_success_by_type(judged_rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """按类型统计首次成功率（本执行器不重试，attempt 恒为 1，即整体成功率按类型分档）。"""
    from collections import defaultdict
    by_type: dict[str, list[int]] = defaultdict(list)
    for r in judged_rows:
        by_type[r["tier_key"]].append(1 if r["success"] else 0)
    return {t: (sum(v) / len(v)) for t, v in by_type.items()}


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    failures: list[str] = []

    # 1) 用例集可读、字段结构正确
    cases = load_cases(CASES_PATH)
    if len(cases) < 1:
        failures.append("用例集为空")
    if len({c["case_id"] for c in cases}) != len(cases):
        failures.append("用例 case_id 存在重复")
    for c in cases:
        if c.get("expected_tool_calls", [{}])[0].get("name") != "retrieve_knowledge":
            failures.append(f"{c['case_id']} 预期工具不是 retrieve_knowledge")

    # 2) tools_p2_retrieve 工具 schema 与 retrieve_knowledge.RETRIEVE_KNOWLEDGE_TOOL 一致
    v2_schema = json.loads(TOOLS_P2_PATH.read_text(encoding="utf-8"))
    tool = v2_schema["tools"][0]
    ref = retrieve_knowledge.RETRIEVE_KNOWLEDGE_TOOL
    for key in ("name", "description"):
        if tool.get(key) != ref.get(key):
            failures.append(f"tools_p2_retrieve.{key} 与 RETRIEVE_KNOWLEDGE_TOOL 不一致")
    if tool.get("parameters") != ref.get("parameters"):
        failures.append("tools_p2_retrieve.parameters 与 RETRIEVE_KNOWLEDGE_TOOL 不一致")
    if tool.get("type") != "read_only":
        failures.append("tools_p2_retrieve.type 应为 read_only")
    if len(v2_schema["tools"]) != 1:
        failures.append("tools_p2_retrieve 应仅含 1 个工具")

    # 3) judge 用 tools_p2_retrieve 也能加载 schema（retrieve_knowledge 参数可被校验）
    schemas = judge_tools.load_tool_schemas(TOOLS_P2_PATH)
    if "retrieve_knowledge" not in schemas:
        failures.append("load_tool_schemas(tools_p2_retrieve) 未含 retrieve_knowledge")
    if "question" not in schemas["retrieve_knowledge"].get("required", []):
        failures.append("retrieve_knowledge 参数缺 required question")

    # 4) run_v2 能解析用例（含 limit 切片）
    cases2 = load_cases(CASES_PATH)
    if args_limit_ok(cases2, 2) != 2 or args_limit_ok(cases2, None) != len(cases2):
        failures.append("limit 切片解析异常")

    if not llm_adapter_selftest_ok():
        failures.append("llm_adapter 默认 self-test 回归失败")

    if failures:
        print("[FAIL] run_v2_tools 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] run_v2_tools 自检通过：用例可读 / tools_p2_retrieve 与 RETRIEVE_KNOWLEDGE_TOOL 一致 / "
          "judge 可校验 / 用例解析正常")
    return 0


def args_limit_ok(cases: list[dict[str, Any]], limit: int | None) -> int:
    return len(cases) if limit is None else len(cases[:limit])


def llm_adapter_selftest_ok() -> bool:
    """在子进程中跑 llm_adapter 默认 self-test，确认 V1（5 工具）不回归。"""
    import subprocess
    cp = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "llm_adapter.py"),
                         "--selftest"], capture_output=True, text=True)
    return cp.returncode == 0


if __name__ == "__main__":
    sys.exit(main())