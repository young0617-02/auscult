# -*- coding: utf-8 -*-
"""M2 里程碑配套评测集指标脚本（P2 · 混合检索 M2.3）

针对 `evals/m2_acc_set.jsonl`（基于真实语料可覆盖主题的配套评测集，相关标注用真实
chunk_id）评测 W1→W5 检索管线的检索质量指标：

      Recall@5 / MRR / NDCG@5 / P95 端到端延迟

口径：
   - 判定用 `relevant_chunk_ids`（配套集真实相关子块），命中判定=检索 top-5 items 的
     chunk_id 是否出现在相关集。
   - Recall@5 = 有任一相关块进入 top5 的问题占比。
   - MRR / NDCG@5 按 top-5 排序 + 二值相关（每条相关块得分 1）。
   - NDCG：DCG = sum rel_i / log2(i+2)（i 从 0 起，log2(2)=1 保证第一档=rel）。
     IDCG = 取 min(相关块数,5) 个理想位的得分。
   - P95 延迟用每题 `latency.total_ms` 分位数（配套集逐题串联，冷启动后再统计）。

用法：
      .venv\\Scripts\\python.exe scripts\\eval_m2.py            # 全量配套集
      .venv\\Scripts\\python.exe scripts\\eval_m2.py --cases 5  # 冒烟前 5 条
落盘：experiments/p2/m2/RAW-m2-metrics.jsonl + meta
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

from retrieve_knowledge import RetrievalService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_SET = PROJECT_ROOT / "evals" / "m2_acc_set.jsonl"
OUT_DIR = PROJECT_ROOT / "experiments" / "p2" / "m2"
RAW = OUT_DIR / "RAW-m2-metrics.jsonl"
META = OUT_DIR / "meta-m2.json"

TOP_K = 5


def _ndcg(ranks: list[int], n_rel: int) -> float:
    """ranks=相关块在 top-N 的位置(0-based)，全部转 1-derived 计 DCG。"""
    hits = [1 if r is not None else 0 for r in ranks[:TOP_K]]
    dcg = sum(h * (1.0 / math.log2(i + 2)) for i, h in enumerate(hits))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(n_rel, TOP_K)))
    return dcg / idcg if idcg else 0.0


def _rr(ranks: list[int], n_rel: int) -> float:
    return 1.0 / (min(ranks) + 1) if ranks else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="M2 配套评测集指标")
    ap.add_argument("--cases", type=int, default=0, help=">0 只看前 N 条")
    ap.add_argument("--top-k", type=int, default=TOP_K)
    ap.add_argument("--device", default="cpu", help="cpu / cuda / cuda:0")
    ap.add_argument("--no-rerank", action="store_true", help="跳过重排（D7消融：RRF-only）")
    args = ap.parse_args()

    cases = [json.loads(l) for l in EVAL_SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.cases:
        cases = cases[: args.cases]

    svc = RetrievalService(top_k=args.top_k, mode="rules", device=args.device,
                           use_rerank=not args.no_rerank)
    # 预热：模型/索引加载不计入 P95
    _ = svc.retrieve(cases[0]["question"])
    time.sleep(0.1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    lat_all = []
    for c in cases:
        rel = set(c["relevant_chunk_ids"])
        r = svc.retrieve(c["question"])
        top_ids = [it.get("chunk_id") for it in r["items"][: args.top_k]]
        ranks = [i for i, cid in enumerate(top_ids) if cid in rel]
        rec = len(ranks) > 0
        row = {
            "qid": c["qid"], "category": c["category"], "question": c["question"],
            "relevant_chunk_ids": sorted(rel), "top_k": args.top_k,
            "hit_chunk_ids": ranks, "recall@k": rec,
            "mrr_singleton": _rr(ranks, len(rel)), "ndcg@k": round(_ndcg(ranks + [None] * args.top_k, len(rel)), 4),
            "latency_ms": r["latency"], "degraded": r["degraded"],
        }
        lat_all.append(r["latency"]["total_ms"])
        rows.append(row)

    with RAW.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    n = len(rows)
    n_rel_total = sum(len(c["relevant_chunk_ids"]) for c in cases)
    recall = sum(r["recall@k"] for r in rows) / n
    mrr = sum(r["mrr_singleton"] for r in rows) / n
    ndcg = sum(r["ndcg@k"] for r in rows) / n
    lat_sorted = sorted(lat_all)
    p95 = lat_sorted[int(math.ceil(0.95 * n)) - 1] if n else 0.0
    p50 = statistics.median(lat_all) if lat_all else 0.0

    meta = {
        "eval_set": str(EVAL_SET.name), "n_cases": n, "top_k": args.top_k,
        "device": args.device,
        "use_rerank": not args.no_rerank,
        "metrics": {
            "Recall@k": round(recall, 4), "MRR": round(mrr, 4),
            "NDCG@k": round(ndcg, 4), "P95_total_ms": round(p95, 1),
            "P50_total_ms": round(p50, 1),
        },
        "n_relevant_blocks_total": n_rel_total,
        "degraded_cases": [r["qid"] for r in rows if r["degraded"]],
        "missing_cases": [r["qid"] for r in rows if not r["recall@k"]],
    }
    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"cases={n}  top_k={args.top_k}")
    print(f"  Recall@{args.top_k}={meta['metrics']['Recall@k']}  "
          f"MRR={meta['metrics']['MRR']}  NDCG@{args.top_k}={meta['metrics']['NDCG@k']}")
    print(f"  P50={meta['metrics']['P50_total_ms']}ms  P95={meta['metrics']['P95_total_ms']}ms")
    print(f"  missing(未达相关): {meta['missing_cases']}")
    print(f"  degraded: {meta['degraded_cases']}")
    print(f"落盘 RAW={RAW}")
    print(f"       META={META}")
    return 0


if __name__ == "__main__":
    sys.exit(main())