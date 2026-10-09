# -*- coding: utf-8 -*-
"""D7 重排消融：对比 RRF-only vs rerank 的逐题排位与 MRR（P2 · 混合检索）

输出：
  1. RRF-only（无重排）的 Recall@5 / MRR / NDCG@5
  2. rerank 后的 Recall@5 / MRR / NDCG@5（复用已有 RAW 或重跑）
  3. 逐题排位对比表，定位 rerank 帮助/伤害了哪些题

用法：
  $env:PYTHONPATH = "scripts"
  & "D:\py312-torch\Scripts\python.exe" scripts\d7_ablation.py --device cuda
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from query_rewrite import rewrite_rules
from retrieval import retrieve_all
from fuse_rrf import fuse_rrf
from rerank import rerank, _text_index
from retrieval_base import RERANKER_MODEL_PATH, PROJECT_ROOT
from retrieve_knowledge import RetrievalService

EVAL_SET = PROJECT_ROOT / "evals" / "m2_acc_set.jsonl"
OUT_DIR = PROJECT_ROOT / "experiments" / "p2" / "d7"
TOP_K = 5


def _ndcg(ranks: list[int], n_rel: int) -> float:
    hits = [1 if i in ranks else 0 for i in range(TOP_K)]
    dcg = sum(h * (1.0 / math.log2(i + 2)) for i, h in enumerate(hits))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(n_rel, TOP_K)))
    return dcg / idcg if idcg else 0.0


def _rr(ranks: list[int]) -> float:
    return 1.0 / (min(ranks) + 1) if ranks else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="D7 重排消融")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    cases = [json.loads(l) for l in EVAL_SET.read_text(encoding="utf-8").splitlines() if l.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 共享 embedder + reranker（GPU 常驻）
    svc = RetrievalService(top_k=TOP_K, mode="rules", device=args.device)
    svc.retrieve(cases[0]["question"])  # 预热
    embedder = svc._embedder_once()
    reranker = svc._reranker_once()
    texts, subs, pars = svc._load_chunk_index()

    rows = []
    for c in cases:
        rel = set(c["relevant_chunk_ids"])
        rw = rewrite_rules(c["question"])
        recall = retrieve_all(rw, parallel=True, embedder=embedder)
        fused = fuse_rrf(recall["candidates"], top_k=TOP_K)
        rrf_ids = [s["chunk_id"] for s in fused["scored"][:TOP_K]]

        # RRF-only 排位
        rrf_ranks = [i for i, cid in enumerate(rrf_ids) if cid in rel]
        rrf_rec = len(rrf_ranks) > 0
        rrf_mrr = _rr(rrf_ranks)
        rrf_ndcg = _ndcg(rrf_ranks, len(rel))

        # rerank 后排位
        rr = rerank(rw.get("semantic", c["question"]), fused["scored"],
                    top_k=TOP_K, device=args.device,
                    text_index=texts, model=reranker)
        rr_ids = [r["chunk_id"] for r in rr["reranked"][:TOP_K]]
        rr_ranks = [i for i, cid in enumerate(rr_ids) if cid in rel]
        rr_rec = len(rr_ranks) > 0
        rr_mrr = _rr(rr_ranks)
        rr_ndcg = _ndcg(rr_ranks, len(rel))

        delta = rr_mrr - rrf_mrr
        tag = "↑帮助" if delta > 0.01 else ("↓伤害" if delta < -0.01 else "→持平")
        rows.append({
            "qid": c["qid"], "category": c["category"],
            "relevant": sorted(rel),
            "rrf_top5": rrf_ids, "rrf_rank": rrf_ranks,
            "rrf_mrr": round(rrf_mrr, 4), "rrf_ndcg": round(rrf_ndcg, 4),
            "rr_top5": rr_ids, "rr_rank": rr_ranks,
            "rr_mrr": round(rr_mrr, 4), "rr_ndcg": round(rr_ndcg, 4),
            "delta_mrr": round(delta, 4), "tag": tag,
        })

    n = len(rows)
    rrf_recall = sum(1 for r in rows if r["rrf_rank"]) / n
    rrf_mrr_avg = sum(r["rrf_mrr"] for r in rows) / n
    rrf_ndcg_avg = sum(r["rrf_ndcg"] for r in rows) / n
    rr_recall = sum(1 for r in rows if r["rr_rank"]) / n
    rr_mrr_avg = sum(r["rr_mrr"] for r in rows) / n
    rr_ndcg_avg = sum(r["rr_ndcg"] for r in rows) / n

    out = OUT_DIR / "ablation-d7.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "n": n,
        "RRF_only": {"Recall@5": round(rrf_recall, 4), "MRR": round(rrf_mrr_avg, 4), "NDCG@5": round(rrf_ndcg_avg, 4)},
        "rerank": {"Recall@5": round(rr_recall, 4), "MRR": round(rr_mrr_avg, 4), "NDCG@5": round(rr_ndcg_avg, 4)},
        "delta_MRR": round(rr_mrr_avg - rrf_mrr_avg, 4),
        "helped": [r["qid"] for r in rows if r["delta_mrr"] > 0.01],
        "hurt": [r["qid"] for r in rows if r["delta_mrr"] < -0.01],
        "neutral": [r["qid"] for r in rows if -0.01 <= r["delta_mrr"] <= 0.01],
    }
    (OUT_DIR / "summary-d7.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== D7 重排消融 ({n} 题, device={args.device}) ===")
    print(f"RRF-only:  Recall@5={summary['RRF_only']['Recall@5']}  MRR={summary['RRF_only']['MRR']}  NDCG@5={summary['RRF_only']['NDCG@5']}")
    print(f"rerank:    Recall@5={summary['rerank']['Recall@5']}  MRR={summary['rerank']['MRR']}  NDCG@5={summary['rerank']['NDCG@5']}")
    print(f"ΔMRR={summary['delta_MRR']}  helped={summary['helped']}  hurt={summary['hurt']}")
    print(f"\n逐题对比:")
    for r in rows:
        print(f"  {r['qid']}  RRF_rank={r['rrf_rank']} RR_rank={r['rr_rank']}  "
              f"ΔMRR={r['delta_mrr']:+.3f} {r['tag']}  cat={r['category']}")
    print(f"\n落盘 {out}")
    print(f"     {OUT_DIR / 'summary-d7.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
