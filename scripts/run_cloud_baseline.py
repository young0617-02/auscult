"""云端 baseline 上界校准执行器（V1 · p0-decision-model-role §七）

一次性跑「20 用例 × 1 重复」作为**上界校准**：仅衡量用例难度与本地差距定位，
**不作为 Pass/No-Go 判据依据**（判据只针对本地模型）。

两种模式：
  - 默认：裸跑（OpenAI 兼容 tools 引导），落盘 `EXP-V1-002.jsonl`（= 云端**下界**，repeat=1）；
  - `--constrain`：云端约束解码（OpenAI `response_format: json_schema` 结构化输出），
    落盘 `EXP-V1-005.jsonl`（= 与本地「约束解码 + few-shot」对等口径的云端上界）。

配置：`env/cloud.json`（endpoint / model / api_key，key 无需入库——本目录非 git 仓库，
      且已由 `.gitignore` 忽略兜底）。
判分：复用 `judge_tools.judge_record`（含语义缺省 + 数组超集口径）与 V1 固定参数。

用法：
  python scripts/run_cloud_baseline.py --limit 1 --constrain   # 先 dry-run 1 条验证 structured_output 连通
  python scripts/run_cloud_baseline.py --constrain             # 全量 20 条 × 1 约束解码
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gbnf_grammar                                                    # noqa: E402
import judge_tools                                                    # noqa: E402
import llm_adapter                                                    # noqa: E402
from llm_adapter import LLMAdapter                                     # noqa: E402
from run_v1 import append_record, history_of, load_cases                # noqa: E402

CLOUD_CONFIG = PROJECT_ROOT / "env" / "cloud.json"
DEFAULT_OUT_BARE = PROJECT_ROOT / "experiments" / "v1" / "raw" / "EXP-V1-002.jsonl"
DEFAULT_OUT_CONSTRAINED = PROJECT_ROOT / "experiments" / "v1" / "raw" / "EXP-V1-005.jsonl"


def load_config(path: Path = CLOUD_CONFIG) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in ("provider", "model", "endpoint", "api_key") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"[cloud] env/cloud.json 缺以下必填项：{missing}")
    return cfg


def schemas_from_tools() -> dict[str, dict[str, Any]]:
    schema = json.loads((PROJECT_ROOT / "schemas" / "tools_v1.json").read_text(encoding="utf-8"))
    return {t["name"]: t["parameters"] for t in schema["tools"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="云端 baseline 上界校准（20×1，一次性）")
    parser.add_argument("--config", type=Path, default=CLOUD_CONFIG)
    parser.add_argument("--out", type=Path, default=None,
                        help="原始结果 JSONL（默认：裸跑 EXP-V1-002；--constrain 时 EXP-V1-005）")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（dry-run 验证用）")
    parser.add_argument("--no-tools", action="store_true", help="不带 tools 引导（云端不支持 function calling 时）")
    parser.add_argument("--constrain", action="store_true",
                        help="云端约束解码：OpenAI response_format json_schema 结构化输出"
                             "（EXP-V1-005，与本地约束解码 + few-shot 对等口径）")
    parser.add_argument("--selftest", action="store_true",
                        help="运行自检（纯离线；不读取 env/cloud.json 的密钥、不联网）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    cfg = load_config(args.config)
    grammar = None
    if args.constrain:
        grammar = gbnf_grammar.generate_grammar(judge_tools.SCHEMA_PATH)
    out = args.out or (DEFAULT_OUT_CONSTRAINED if args.constrain else DEFAULT_OUT_BARE)
    tag = f"cloud-{cfg.get('provider', 'unknown')}-" + \
          ("native-constrained" if args.constrain else "upper-bound")

    # V1 固定实验参数显式传入，不依赖类默认值（防静默漂移；见 docs/prj-ledger-version-lock.md §2.5）
    adapter = LLMAdapter(
        endpoint=cfg["endpoint"], api_key=cfg["api_key"],
        temperature=llm_adapter.DEFAULT_TEMPERATURE,
        seed=llm_adapter.DEFAULT_SEED,
        num_ctx=llm_adapter.DEFAULT_NUM_CTX,
        top_p=llm_adapter.DEFAULT_TOP_P,
        max_tokens=llm_adapter.DEFAULT_MAX_TOKENS,
        grammar=grammar, structured_output=args.constrain,
    )
    schemas = schemas_from_tools()
    cases = load_cases()

    print("[cloud] 云端 baseline 上界校准（20×1 一次性，不作为判据依据）")
    print(adapter.describe())
    print(f"model     : {cfg['model']}")
    print(f"tag       : {tag}  | out: {out}" + ("  | --limit=" + str(args.limit) if args.limit else ""))

    processed = 0
    for i, case in enumerate(cases):
        if args.limit and i >= args.limit:
            break
        messages = build_case_messages(case, adapter)
        # 约束解码：expect_reject 用例不施加工具调用数组 schema（应不调用工具），其余按需约束
        adapter.grammar = None if (args.constrain and case.get("expect_reject")) else grammar
        result = adapter.chat(messages, model=cfg["model"], use_tools=not args.no_tools)
        record = {
            "expected": case,
            "result": result.to_raw(),
            "model": cfg["model"],
            "repeat": 1,
            "attempt": 1,
            "tag": tag,
            "cold_start": True,
            "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        judged = judge_tools.judge_record(record, schemas)
        record["judged_success"] = judged["success"]
        append_record(out, record)
        processed += 1
        mark = "OK " if judged["success"] else "FAIL"
        print(f"  [{mark}] {case.get('case_id')} success={judged['success']} "
              f"failure={judged.get('failure') or '-'} "
              f"calls={len(result.to_raw().get('tool_calls', []))} "
              f"latency={result.latency_ms:.0f}ms")

    print(f"[cloud] 完成 {processed} 条（用例总数 {len(cases)}）→ {out}")
    print("[cloud] 提示：汇总请用 judge_tools --raw 输出（首/重试成功率、8 指标）")
    return 0


def build_case_messages(case: dict[str, Any], adapter: LLMAdapter) -> list[dict[str, str]]:
    """按 llm_adapter 的统一装配规则构造单条用例的消息列表（含 few-shot）。

    与 `llm_adapter` 模块名区分开：本函数只是"用例 → 消息"的薄封装，
    装配规则本身仍由 `llm_adapter.build_messages` 单一实现（避免两套口径）。
    """
    return llm_adapter.build_messages(
        case["input"], history=history_of(case), fewshot=True,
        system_prompt=adapter.system_prompt,
    )


def _selftest() -> int:
    """纯离线自检：校验装配链、固定参数与落盘编号；不读取密钥、不联网。"""
    failures: list[str] = []

    if (llm_adapter.DEFAULT_TEMPERATURE, llm_adapter.DEFAULT_SEED,
            llm_adapter.DEFAULT_NUM_CTX, llm_adapter.DEFAULT_TOP_P,
            llm_adapter.DEFAULT_MAX_TOKENS) != (0.0, 42, 8192, 1.0, 1024):
        failures.append("V1 固定实验参数被改动（见 docs/prj-ledger-version-lock.md §2.5）")

    cases = load_cases()
    if len(cases) != 20:
        failures.append(f"用例数应为 20，实际 {len(cases)}")

    schemas = schemas_from_tools()
    if set(schemas) != {"query_sensor", "search_knowledge", "query_graph",
                        "get_maintenance_history", "generate_report"}:
        failures.append(f"工具集与 tools_v1.json 不一致：{sorted(schemas)}")

    grammar = gbnf_grammar.generate_grammar(judge_tools.SCHEMA_PATH)
    branches = grammar.get("items", {}).get("oneOf", [])
    if len(branches) != 5:
        failures.append(f"约束 schema 分支数应为 5，实际 {len(branches)}")

    if not DEFAULT_OUT_BARE.name.startswith("EXP-V1-002"):
        failures.append("裸跑落盘文件名应为 EXP-V1-002")
    if not DEFAULT_OUT_CONSTRAINED.name.startswith("EXP-V1-005"):
        failures.append("约束解码落盘文件名应为 EXP-V1-005")

    if failures:
        print("[FAIL] run_cloud_baseline 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] run_cloud_baseline 自检通过：用例 20 / 5 工具 / 约束 schema 5 分支 / "
          "V1 固定参数 / 落盘编号（EXP-V1-002 裸跑、EXP-V1-005 约束解码）")
    return 0


if __name__ == "__main__":
    sys.exit(main())