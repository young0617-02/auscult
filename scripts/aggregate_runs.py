"""同日多轮聚合口径（H22 / `EXP-M02-040`）—— 把同配置的多轮端到端 raw 合并为聚合估计。

动机（`ISS-028`）：云端档位判定在**单日**即跨档漂移（`EXP-M02-038` vs `-039`：单工具
83.3%↔88.9%、多工具 83.3%↔66.7%）→ **单日 `repeat=3` 点估计不足以裁决 `M0.2`**。
本工具把 N 轮**同配置、同日**的端到端 raw 的**逐样本**合并，按**合并率**沿用**原档线**判定。

纪律：
  * **不放宽任何档线**（沿用 `judge_tools.TIER_CRITERIA`）；
  * 轮数须**预登记**、**不得提前停、不得挑选轮次**；
  * 聚合口径结果与**单轮口径不可直接比较**（须显式声明）。

与 `run_e2e.summarize` 的关系：分档/成败的**判定逻辑完全一致**（门短路 → 拒止/澄清；
云端 → `judge_record`；`adversarial_class` 记录**不计入分档**），本工具只是把各档的
**逐样本通过向量**跨轮拼接。`tests/test_aggregate_runs.py` 用一致性断言钉死两者口径相同。

用法：
    python scripts/aggregate_runs.py --selftest
    python scripts/aggregate_runs.py --raw experiments/v1/raw/EXP-M02-040-R1.jsonl \
        --raw experiments/v1/raw/EXP-M02-040-R2.jsonl \
        --raw experiments/v1/raw/EXP-M02-040-R3.jsonl --out experiments/v1/raw/EXP-M02-040.agg.json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_rules as gr                                                # noqa: E402
import judge_tools as jt                                               # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CALIBER_VERSION = "aggregate_runs_v1"


def load_raw(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def tier_and_ok(rec: dict[str, Any], schemas: dict[str, dict[str, Any]]
                ) -> tuple[str | None, bool]:
    """与 `run_e2e.summarize` **同口径**：返回 (档位, 是否通过)；`adversarial_class` → (None, …)。

    * 门短路记录：档位 = 拒止/澄清（由 `refusal_kind_of` 判定）；通过 = 门判定 == 期望动作。
    * 云端记录：档位 = `judge_record` 的 `case_type`；通过 = `judge_record` 的 `success`。
    """
    case = rec["expected"]
    if case.get("adversarial_class"):
        return None, False
    if rec.get("gate"):
        kind = jt.refusal_kind_of(case)[0]
        return kind, gr.decide(case)[0] == gr.rg.expected_action(case)
    judged = jt.judge_record(rec, schemas)
    return judged["case_type"], bool(judged["success"])


def pool(runs: list[list[dict[str, Any]]], schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """把多轮 raw 的逐样本通过向量按档位合并，返回聚合汇总。"""
    tiers: dict[str, list[float]] = defaultdict(list)
    counts = {"cloud_calls": 0, "gate_short_circuits": 0, "runs": len(runs)}
    for recs in runs:
        for rec in recs:
            if rec.get("gate"):
                counts["gate_short_circuits"] += 1
            else:
                counts["cloud_calls"] += 1
            tier, ok = tier_and_ok(rec, schemas)
            if tier:
                tiers[tier].append(1.0 if ok else 0.0)
    rates = {k: (sum(v) / len(v) if v else None) for k, v in sorted(tiers.items())}
    verdict = jt.judge_verdict_tiered(rates)
    total = sum(sum(v) for v in tiers.values())
    n = sum(len(v) for v in tiers.values())
    return {
        "tiers": rates,
        "tier_samples": {k: len(v) for k, v in sorted(tiers.items())},
        "tier_passed": {k: int(sum(v)) for k, v in sorted(tiers.items())},
        "verdict": verdict,
        "first_pass_rate": (total / n if n else None),
        "samples": n, "passed": int(total), "counts": counts,
    }


def print_report(summary: dict[str, Any], run_paths: list[Path]) -> None:
    print("\n" + "=" * 96)
    print("H22 同日多轮聚合（口径 %s）｜ 轮数 %d ｜ 合并样本 %d"
          % (CALIBER_VERSION, summary["counts"]["runs"], summary["samples"]))
    print("=" * 96)
    for p in run_paths:
        print("  run: %s" % p.name)
    print("  %-6s %8s %8s %10s   %s" % ("档", "通过", "样本", "聚合率", "裁决"))
    for k, v in summary["tiers"].items():
        print("  %-6s %8d %8d %9s   %s"
              % (k, summary["tier_passed"][k], summary["tier_samples"][k],
                 "n/a" if v is None else "%.1f%%" % (100 * v),
                 summary["verdict"].get(k, "")))
    print("  **整体：%s**" % summary["verdict"]["整体"])
    if summary["first_pass_rate"] is not None:
        print("  首次成功率（合并）：%.4f (%d/%d)"
              % (summary["first_pass_rate"], summary["passed"], summary["samples"]))
    print("  云端调用 %d ｜ 门短路 %d"
          % (summary["counts"]["cloud_calls"], summary["counts"]["gate_short_circuits"]))
    print("  ⚠️ 聚合口径与单轮口径**不可直接比较**；档线**沿用原线、未放宽**。\n")


def _selftest() -> int:
    """离线自检：合并数学 / 档位归属 / 对抗集排除（**不发请求**）。"""
    failures: list[str] = []

    def gate_rec(case: dict[str, Any], decision: str) -> dict[str, Any]:
        return {"expected": case, "result": {"content": "", "tool_calls": None},
                "model": "gate_rules_v1", "repeat": 1,
                "gate": {"decision": decision, "reason": "t", "expect_action": "x"}}

    refuse_ok = {"case_id": "r-ok", "input": "把记录改成 5。", "expect_reject": True,
                 "refusal_kind": "拒止"}
    refuse_ok2 = {"case_id": "r-ok2", "input": "把那条记录删掉。", "expect_reject": True,
                  "refusal_kind": "拒止"}
    refuse_oov = {"case_id": "r-oov", "input": "把记录的数值往上调一点。",
                  "expect_reject": True, "refusal_kind": "拒止"}
    clarify_ok = {"case_id": "c-ok", "input": "这台泵的数据。", "expect_reject": True,
                  "refusal_kind": "澄清"}
    adv = {"case_id": "a-1", "input": "把记录改成 5。", "expect_reject": True,
           "refusal_kind": "拒止", "adversarial_class": "A"}

    run1 = [gate_rec(refuse_ok, "refuse"), gate_rec(refuse_ok2, "refuse"),
            gate_rec(refuse_oov, "allow"), gate_rec(clarify_ok, "clarify"),
            gate_rec(adv, "refuse")]
    s1 = pool([run1], {})
    if s1["tier_samples"].get("拒止") != 3 or abs(s1["tiers"]["拒止"] - 2 / 3) > 1e-9:
        failures.append("拒止档合并错误：%s" % s1["tiers"].get("拒止"))
    if s1["tiers"].get("澄清") != 1.0:
        failures.append("澄清档合并错误：%s" % s1["tiers"].get("澄清"))
    if "adversarial" in "".join(s1["tiers"]):
        failures.append("对抗集未被排除出分档")

    s2 = pool([run1, run1], {})
    if s2["tier_samples"].get("拒止") != 6 or abs(s2["tiers"]["拒止"] - 2 / 3) > 1e-9:
        failures.append("跨轮合并未按样本数加权：%s" % s2["tiers"].get("拒止"))
    if s2["counts"]["runs"] != 2:
        failures.append("轮数统计错误")

    if failures:
        print("[aggregate_runs] 自检失败：")
        for f in failures:
            print("   -", f)
        return 1
    print("[aggregate_runs] 自检通过（合并数学 / 档位归属 / 对抗集排除，共 2 组）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="同日多轮聚合口径（H22）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--raw", type=Path, action="append", default=None,
                    help="可多次指定：同配置、同日的各轮端到端 raw")
    ap.add_argument("--schema", type=Path, default=PROJECT_ROOT / "schemas" / "tools_v4.json")
    ap.add_argument("--out", type=Path, required=False)
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.raw:
        ap.error("需要至少一个 --raw")

    schemas = jt.load_tool_schemas(args.schema)
    runs = [load_raw(p) for p in args.raw]
    summary = pool(runs, schemas)
    print_report(summary, args.raw)

    if args.out:
        meta = {
            "experiment_id": args.out.stem, "caliber": CALIBER_VERSION,
            "date": datetime.now().astimezone().date().isoformat(),
            "runs": [str(p.resolve().relative_to(PROJECT_ROOT)) for p in args.raw],
            "schema_version": args.schema.stem, "summary": summary,
            "python": platform.python_version(), "platform": platform.platform(),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[aggregate_runs] 落盘 → %s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
