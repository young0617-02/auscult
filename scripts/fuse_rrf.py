"""W3 RRF 融合（Phase 2 · 混合检索，P2-D4）

职责：把 W2 `retrieve_all` 产出的 `candidates`（Dense + Sparse 两路，各带 route 与 raw rank）
     用加权 RRF 融合排序，取 `top_k=5` 供 W4 父块回填消费。

关键约定：
  - **RRF(k=60)** 与 V2 基准（`run_v2.RRF_K`）一致；
  - **加权**：`w_dense=0.6 / w_sparse=0.4`（来源 plan §5.3），
    同一 chunk 跨路出现时对每路各自的 `w/(k+rank)` 累加；
  - **图谱不参与融合**（P2-R4）：仅消费 `candidates`（已不含 graph），
    graph 由 W4/W5 单独组装；
  - 每路内部 rank ∈ [1, top_k_route]，irrelevant 不进列表。

输出：`{scored: [{chunk_id, score, rank, routes:[{route, w, contribution}]}], weights, k, top_k}`，
      `scored` 按融合分降序，至多 `top_k` 条。

自检：`python scripts/fuse_rrf.py --selftest`
用法：`python scripts/fuse_rrf.py --candidates experiments/p2/w3/candidates.json`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from retrieval_base import PROJECT_ROOT, load_retrieval_config


def fuse_rrf(candidates: list[dict[str, Any]],
             k: int | None = None,
             weights: dict[str, float] | None = None,
             top_k: int | None = None) -> dict[str, Any]:
    """对两路候选加权 RRF 融合，返回 `{scored, weights, k, top_k}`。

    Args:
      candidates: W2 `retrieve_all.candidates`，每条含 `{chunk_id, route, rank}`（route∈{dense,sparse}）
      k: RRF 平滑常数；None → 读 configs/retrieval.yml `rrf.k`
      weights: 各路权重，缺省按 `rrf.weights`
      top_k: 融合后保留条数；None → 读 `rrf.top_k`
    Returns:
      {scored: [...], weights, k, top_k}
    """
    cfg = load_retrieval_config().get("rrf", {})
    if k is None:
        k = int(cfg.get("k", 60))
    if top_k is None:
        top_k = int(cfg.get("top_k", 5))
    w = dict(cfg.get("weights", {})) if weights is None else weights

    acc: dict[str, float] = {}                       # chunk_id -> 加权融合分
    contrib: dict[str, list[dict[str, Any]]] = {}    # chunk_id -> 各路贡献留痕
    for c in candidates:
        cid = c["chunk_id"]
        route = c.get("route", "dense")
        rank = int(c.get("rank", 0))
        if rank <= 0:
            continue
        w_route = float(w.get(route, 1.0))
        part = w_route / (k + rank)
        acc[cid] = acc.get(cid, 0.0) + part
        contrib.setdefault(cid, []).append({
            "route": route, "rank": rank, "w": w_route, "contribution": round(part, 6),
        })

    scored = [{
        "chunk_id": cid,
        "score": round(s, 6),
        "rank": i,
        "routes": contrib[cid],
    } for i, (cid, s) in enumerate(
        sorted(acc.items(), key=lambda kv: -kv[1]), start=1)][:top_k]

    return {"scored": scored, "weights": {rk: float(v) for rk, v in w.items()},
            "k": int(k), "top_k": int(top_k)}


def _selftest() -> int:
    fail = 0
    # 两路都排第一的 chunk（rank=1 both）应居首
    cands = [
        {"chunk_id": "A", "route": "dense", "rank": 1},
        {"chunk_id": "A", "route": "sparse", "rank": 1},
        {"chunk_id": "B", "route": "dense", "rank": 2},
        {"chunk_id": "C", "route": "sparse", "rank": 1},
    ]
    out = fuse_rrf(cands, k=60, weights={"dense": 0.6, "sparse": 0.4}, top_k=5)
    if not out["scored"] or out["scored"][0]["chunk_id"] != "A":
        print(f"[FAIL] A 未居首（两路 rank=1）: {out['scored']}")
        fail += 1
    if len(out["scored"]) > 3:
        print("[FAIL] 融合条数超过候选数")
        fail += 1
    if out["k"] != 60 or out["weights"]["dense"] != 0.6 or out["weights"]["sparse"] != 0.4:
        print(f"[FAIL] rrf 参数不正确 {out['weights']} k={out['k']}")
        fail += 1
    # A 应有 dense+sparse 两条贡献留痕
    a = next((s for s in out["scored"] if s["chunk_id"] == "A"), None)
    if not a or len(a["routes"]) != 2:
        print(f"[FAIL] A 贡献留痕数不正确 {a}")
        fail += 1
    # 加权正确性：A = 0.6/61 + 0.4/61
    expected_a = round(0.6 / 61 + 0.4 / 61, 6)
    if a and abs(a["score"] - expected_a) > 1e-6:
        print(f"[FAIL] A 融合分不正确 {a['score']} 期望 {expected_a}")
        fail += 1
    # 配置驱动测试（读 yml）
    out2 = fuse_rrf([{"chunk_id": "X", "route": "dense", "rank": 1}])
    if out2["k"] != 60 or out2["top_k"] != 5:
        print(f"[FAIL] 配置驱动 rrf 参数 {out2['k']}/{out2['top_k']}")
        fail += 1
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W3 RRF 融合")
    p.add_argument("--candidates", type=Path, help="W2 candidates json 文件（含 candidates 键或列表）")
    p.add_argument("--top-k", type=int, default=None, help="覆盖 top_k")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.candidates:
        doc = json.loads(args.candidates.read_text(encoding="utf-8-sig"))
        cands = doc if isinstance(doc, list) else doc.get("candidates", [])
        out = fuse_rrf(cands, top_k=args.top_k)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())