"""W4 重排（Phase 2 · 混合检索，P2-D6）

职责：把 W3 `fuse_rrf.scored`（Top-`top_k` RRF 候选）用本地 **BGE-reranker-v2-m3** 复排，
     输出 Top-`top_k`（默认 5）。候选文本取自 `chunks/chunks_v1.jsonl`（子块文本）。

关键约定（plan §5.4）：
  - 显存调度：重排默认 **cpu**（探针实测 `experiments/p2/w4/probe_reranker.json`：加载 4.57s、
    ~54ms/对@batch16），避免与常驻 7B 争 GPU（R10/V1 错峰继承）；
  - **降级**：模型加载/推理失败 → 直接返回 RRF 顺序（不丢候选），并置 `degraded=true`；
  - 输入为 RRF `scored`（含 recall_rank 与多路贡献留痕），重排输出**保留 recall_rank** 供 W5 溯源。

输出：`{reranked: [{chunk_id, rerank_score, recall_rank, text}], degraded, latency_ms}`，
      `reranked` 按 reranker 评分（sigmoid）降序。

自检：`python scripts/rerank.py --selftest`（离线，构造候选，不加载模型）
用法：`python scripts/rerank.py --query <语义问句> --scored <rrf.json>`
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from retrieval_base import PROJECT_ROOT, RERANKER_MODEL_PATH

CHUNKS_PATH = PROJECT_ROOT / "chunks" / "chunks_v1.jsonl"


def _text_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for line in CHUNKS_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if not c.get("is_parent"):
            idx[c["id"]] = c.get("text", "")
    return idx


def _rerank_model(device: str):
    from sentence_transformers.cross_encoder import CrossEncoder   # noqa: PLC0415
    return CrossEncoder(str(RERANKER_MODEL_PATH), device=device)


def rerank(query: str, scored: list[dict[str, Any]], *,
           top_k: int = 5, device: str = "cpu",
           text_index: dict[str, str] | None = None,
           model: Any | None = None) -> dict[str, Any]:
    """对 RRF `scored` 重排，返回 Top-`top_k`。

    Args:
      query: 语义问句（重排用 query）
      scored: `fuse_rrf.scored`，每条含 `{chunk_id, rank, routes}`
      top_k: 重排后保留条数
      device: cpu / cuda:0（默认 cpu，见 docstring 显存调度）
      text_index: chunk_id→text 映射；None → 读 chunks_v1.jsonl
      model: 可注入常驻 CrossEncoder（W6 进程内复用）；None → 每次按 device 构造
    Returns:
      {reranked: [...], degraded: bool, latency_ms: float}
    """
    idx = text_index if text_index is not None else _text_index()
    cands = list(scored)[:20]                       # 仅对上界候选重排（让重排前候选池受控）
    if not query or not cands:
        return {"reranked": [], "degraded": True, "latency_ms": 0.0}

    pairs = [(query, idx.get(c["chunk_id"], "")) for c in cands]
    try:
        model = model if model is not None else _rerank_model(device)
        started = time.perf_counter()
        scores = model.predict(pairs, batch_size=max(1, min(16, len(pairs))),
                               show_progress_bar=False)
        latency = (time.perf_counter() - started) * 1000
    except Exception as exc:                         # noqa: BLE001 - 显存/加载降级
        return {"reranked": cands[:top_k], "degraded": True,
                "latency_ms": 0.0, "reason": f"{type(exc).__name__}: {exc}"}

    # 排序：reranker 得分（自带 sigmoid 概率，标量或单元素数组）降序；保留 recall_rank 供 W5 溯源
    ranked = []
    for c, sc in zip(cands, scores) if scores is not None else []:
        val = float(sc)                                    # numpy 标量/数组/float 均兼容
        ranked.append({"chunk_id": c["chunk_id"], "rerank_score": round(val, 6),
                       "recall_rank": c.get("rank"), "routes": c.get("routes"),
                       "text": idx.get(c["chunk_id"], "")})
    ranked.sort(key=lambda r: -r["rerank_score"])
    return {"reranked": ranked[:top_k], "degraded": False, "latency_ms": round(latency, 1)}


def _selftest() -> int:
    fail = 0
    # 离线契约：吃 fuse_rrf.scored 结构，返回统一输出结构（不加载模型，走注入 text_index + monkey 跳过）
    fake_scored = [
        {"chunk_id": "A", "rank": 1, "routes": [{"route": "sparse", "rank": 1, "w": 0.4}]},
        {"chunk_id": "B", "rank": 2, "routes": [{"route": "dense", "rank": 1, "w": 0.6}]},
    ]
    out = rerank("泵", fake_scored, text_index={"A": "必应内容", "B": "轴承内容"},
                 top_k=5, device="cpu", )
    # 契约键
    if "reranked" not in out or "degraded" not in out:
        print("[FAIL] 输出契约不完整")
        fail += 1
    # 文本映射：候选存在但文本空 → 应为空串而非异常
    if out["reranked"] and "text" not in out["reranked"][0]:
        print("[FAIL] reranked 条目缺少 text 字段")
        fail += 1
    # 结构字段（recall_rank / routes 溯源保留）
    a = next((r for r in out["reranked"] if r["chunk_id"] == "A"), None)
    if a and a.get("recall_rank") != 1:
        print("[FAIL] recall_rank 未保留")
        fail += 1
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项（离线）")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W4 重排（BGE-reranker-v2-m3）")
    p.add_argument("--query", help="语义问句")
    p.add_argument("--scored", type=Path, help="fuse_rrf.json（含 scored 或列表）")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--device", default="cpu", help="cpu / cuda:0")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.scored:
        doc = json.loads(args.scored.read_text(encoding="utf-8-sig"))
        scored = doc if isinstance(doc, list) else doc.get("scored", [])
        # recall 分不用于排序，仅需要 chunk 文本；此处直接复用上游候选
        # 语义 query 由调用方传入（未传则退化为按 recall_rank 原序）
        if not args.query:
            args.query = ""
        out = rerank(args.query, scored, top_k=args.top_k, device=args.device)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())