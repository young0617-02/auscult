# -*- coding: utf-8 -*-
"""B3 Milvus 建库（P1-D4/D5 · B3）：把 B2 子块写入 Milvus，做召回冒烟。

把 `chunks/chunks_v1.jsonl` 的子块向量化（BGE-M3 本地，1024 维）并写入
Milvus collection **kb_p1_v1**（与 V2 的 `kb_v1` 隔离，不触碰 V2 对照基线）。

复用 V2 基座（`scripts/run_v2.py`）：
  - `EmbeddingClient`（本地 BGE-M3，dim=1024）做稠密向量化；
  - 建库参数与 V2 一致：decensus BGE-M3 HNSW/COSINE + 服务端 BM25 稀疏（jieba analyzer）。

Schema（在 V2 的 `chunk_id/text/dense/sparse` 基础上补保有 meta 标量字段）：
  chunk_id(VARCHAR,key) / text(VARCHAR,jieba analyzer) / dense(FLOAT 1024) /
  sparse(SPARSE BM25) / doc_id / parent_id / section / page / doc_type

召回冒烟：自建 10 条贴近 B2 语料的 query（synthetic=true，非正式指标，
仅做链路验证；正式评测见 Phase 2），dense/sparse/hybrid(RRF) 各算 Recall@5。

用法：
    .venv\\Scripts\\python.exe scripts\\build_milvus_v1.py --selftest
    .venv\\Scripts\\python.exe scripts\\build_milvus_v1.py \
        --chunks chunks/chunks_v1.jsonl --collection kb_p1_v1 --uri http://127.0.0.1:19531

依赖：pymilvus、sentence-transformers（`docs/prj-ledger-version-lock.md` §二.2.8）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from milvus_endpoint import milvus_uri  # noqa: E402

DEFAULT_CHUNKS = PROJECT_ROOT / "chunks" / "chunks_v1.jsonl"
# ISS-042：默认端点跟 deploy 栈走（19531）；不再硬编码 Phase-0 基线 19530
DEFAULT_URI = milvus_uri()
DEFAULT_COLLECTION = "kb_p1_v1"
EMBED_DIM = 1024
RRF_K = 60
TOP_K = 5

# 自建冒烟 query（贴近 B2 各章节标题，synthetic bool 由报告标记）
SMOKE_DOC_TYPE = {
    "criteria_1": "标准判据", "fault_case_1": "故障案例",
    "workorders_A": "维修工单", "topo_plant": "拓扑",
    "manual_impeller_series": "设备手册",
}


def import_v2():
    """导入 run_v2 的 EmbeddingClient / Milvus 相关；仅模块级常量与类，无副作用。"""
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import run_v2  # noqa: PLC0415
    return run_v2


def load_chunks(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 仅取子块（is_parent=False）；父块不落 Milvus（由子块 parent_id 回填）
    return [r for r in rows if not r.get("is_parent")]


def build_schema(collection: str, DataType, Function, FunctionType, analyzer: str):
    """kb_p1_v1 schema：V2 参数 + meta 标量字段。"""
    from pymilvus import MilvusClient
    client = MilvusClient(uri=_URI)
    if client.has_collection(collection):
        client.drop_collection(collection)

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)
    schema.add_field("text", DataType.VARCHAR, max_length=65535,
                     enable_analyzer=True, analyzer_params={"tokenizer": analyzer})
    schema.add_field("dense", DataType.FLOAT_VECTOR, dim=EMBED_DIM)
    schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
    for name in ("doc_id", "parent_id", "section", "doc_type"):
        schema.add_field(name, DataType.VARCHAR, max_length=128)
    schema.add_field("page", DataType.INT64)
    schema.add_function(Function(name="bm25", function_type=FunctionType.BM25,
                                 input_field_names=["text"],
                                 output_field_names=["sparse"]))

    index = client.prepare_index_params()
    index.add_index(field_name="dense", index_type="HNSW",
                    metric_type="COSINE", params={"M": 16, "efConstruction": 200})
    index.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX",
                    metric_type="BM25")
    client.create_collection(collection, schema=schema, index_params=index)
    return client


def main() -> int:
    ap = argparse.ArgumentParser(description="B3 Milvus 建库")
    ap.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    ap.add_argument("--collection", default=DEFAULT_COLLECTION)
    ap.add_argument("--uri", default=DEFAULT_URI)
    ap.add_argument("--analyzer", default="jieba")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    global _URI, _client_coll
    _URI = args.uri
    _client_coll = args.collection

    if args.selftest:
        return _selftest()

    from pymilvus import DataType, Function, FunctionType

    chunks = load_chunks(args.chunks)
    if not chunks:
        print(f"[ERROR] 无子块可入库：{args.chunks}")
        return 2
    run_v2 = import_v2()
    embedder = run_v2.EmbeddingClient(
        model=run_v2.BGE_M3_MODEL_PATH,
        cache_path=PROJECT_ROOT / "experiments" / "p1" / "b3" / "embed_cache.json")

    print(f"[run] 子块数={len(chunks)} 向量化(本地 BGE-M3, dim={EMBED_DIM})...")
    vectors = embedder.embed([c["text"] for c in chunks])
    print(f"[run] 向量化完成，维度={len(vectors[0]) if vectors else 'N/A'}")

    print(f"[run] 建库 {args.collection} ...")
    client = build_schema(args.collection, DataType, Function, FunctionType, args.analyzer)
    rows = [{
        "chunk_id": c["id"], "text": c["text"], "dense": vec,
        "doc_id": c.get("doc_id"), "parent_id": c.get("parent_id"),
        "section": c.get("section"), "doc_type": c.get("doc_type"),
        "page": c.get("page") if isinstance(c.get("page"), int) else None,
    } for c, vec in zip(chunks, vectors)]
    client.insert(args.collection, rows)
    client.flush(args.collection)
    stats = client.get_collection_stats(args.collection)
    count = stats.get("row_count", 0)
    print(f"[run] 已入库 {count} 行")

    # 召回冒烟：自建 10 条 query
    smoke = _build_smoke_queries(chunks, run_v2, embedder, client, TOP_K, RRF_K)
    print("\n=== 召回冒烟（非正式，链路验证）===")
    for q in smoke:
        print(f"  doc={q['doc_type']:6s} dense={q['recall_dense']:.2f} "
              f"sparse={q['recall_sparse']:.2f} hybrid={q['recall_hybrid']:.2f} | {q['text'][:24]}")
    summary = {"collection": args.collection, "row_count": count, "smoke": smoke,
               "synthetic": True}
    out = PROJECT_ROOT / "experiments" / "p1" / "b3" / "milvus_smoke.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 摘要 → {out}")
    return 0


def _as_query(text: str) -> str:
    return text


def _build_smoke_queries(chunks, run_v2, embedder, client, top_k, rrf_k):
    """自建 10 条贴近各章节标题的 query（doc_type 合理区分布点）。返回带 Recall 的 list。"""
    # 取每个 doc_type 的代表性子块 title/一段，作为 query 文本
    picked = []
    seen = set()
    for c in chunks:
        dt = c.get("doc_type")
        if dt and dt not in seen and len(picked) < 10:
            seen.add(dt)
            picked.append(c)
    # 若类型不足 10，补 4 个手册章节 query
    if len(picked) < 10:
        for c in chunks:
            if c.get("doc_id", "").startswith("manual_") and len(picked) < 10:
                picked.append(c)
    picked = picked[:10]

    queries = []
    for c in picked:
        q = {
            "text": c["text"][:200] if False else _as_query(c.get("section") or c["text"][:60]),
            "relevant_chunk_ids": [c["id"]],
            "doc_type": c.get("doc_type"),
        }
        queries.append(_eval_one(q, embedder, client, top_k, rrf_k))
    return queries


def _eval_one(q, embedder, client, top_k, rrf_k):
    import numpy as np
    dense = embedder.embed([q["text"]])
    # dense search
    qvec = dense[0]
    res = client.search(collection_name=client_collection(), data=[qvec],
                        anns_field="dense", limit=top_k,
                        output_fields=["chunk_id"])
    hit_ids = [r.get("entity", {}).get("chunk_id") for r in res[0]]
    recall_dense = float(q["relevant_chunk_ids"][0] in hit_ids)
    # sparse (BM25, 服务端) — search 传 text 到 sparse
    res2 = client.search(collection_name=client_collection(), data=[q["text"]],
                         anns_field="sparse", limit=top_k, output_fields=["chunk_id"])
    hit_ids2 = [r.get("entity", {}).get("chunk_id") for r in res2[0]]
    recall_sparse = float(q["relevant_chunk_ids"][0] in hit_ids2)
    # hybrid (RRF)
    anns = []
    for field, data in (("dense", qvec), ("sparse", q["text"])):
        from pymilvus import AnnSearchRequest
        request = AnnSearchRequest(data=[data], anns_field=field,
                                   param={"metric_type": "COSINE" if field == "dense" else "BM25"},
                                   limit=top_k)
        anns.append(request)
    from pymilvus import RRFRanker
    res3 = client.hybrid_search(collection_name=client_collection(), reqs=anns,
                                ranker=RRFRanker(k=rrf_k), limit=top_k,
                                output_fields=["chunk_id"])
    hit_ids3 = [r.get("entity", {}).get("chunk_id") for r in res3[0]]
    recall_hybrid = float(q["relevant_chunk_ids"][0] in hit_ids3)
    return {"text": q["text"], "doc_type": q.get("doc_type"), "relevant": q["relevant_chunk_ids"][0],
            "recall_dense": recall_dense, "recall_sparse": recall_sparse,
            "recall_hybrid": recall_hybrid}


_client_coll = DEFAULT_COLLECTION


def client_collection():
    return _client_coll


def _selftest() -> int:
    ok = True
    # 无副作用自检：chunk 过滤
    rows = [{"id": "a", "is_parent": True, "text": "父"}] + \
           [{"id": "b", "is_parent": False, "text": "子"}]
    subs = [r for r in rows if not r.get("is_parent")]
    if len(subs) != 1:
        ok = False
        print(f"[FAIL] is_parent 过滤: {subs}")
    print(f"[selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


_URI = DEFAULT_URI


if __name__ == "__main__":
    raise SystemExit(main())