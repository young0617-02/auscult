"""W2 Dense 召回（Phase 2 · 混合检索，P2-D2）

职责：用 `semantic` 原文经 BGE-M3（本地，ModelScope 路径）编码后，在 Milvus `kb_p1_v1`
     HNSW(COSINE) 索引上取 `top_k=20`。

依赖：复用 `run_v2.EmbeddingClient::embed()`（本地 BGE-M3）+ `retrieval_base` 中 Milvus 拓扑。
独立：单脚本可测、可降级（失败 → 空候选 + degraded 置位，不抛异常中断链路）。

自检：`python scripts/retrieve_dense.py --selftest`
用法：`python scripts/retrieve_dense.py --query "..."`
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from retrieval_base import (MILVUS_COLLECTION, MILVUS_URI,
                            extract_route_inputs, load_retrieval_config, make_hit)


def _scalar_fetch(query: str, embedder: Any | None = None) -> tuple[list[dict[str, Any]], float]:
    """单条查询的 Dense 召回，返回 (hits, latency_ms)。"""
    cfg = load_retrieval_config()
    top_k = int(cfg["dense"]["top_k"])
    ef = int(cfg["dense"]["hnsw"]["ef"])
    try:
        if embedder is None:
            from run_v2 import BGE_M3_MODEL_PATH
            from run_v2 import EmbeddingClient as Emb
            embedder = Emb(BGE_M3_MODEL_PATH)
        from pymilvus import MilvusClient
        client = MilvusClient(uri=MILVUS_URI)
    except ImportError as exc:
        raise RuntimeError(f"Dense 召回依赖缺失：{exc}") from exc

    vector = embedder.embed([query])[0]
    started = time.perf_counter()
    # distance 为搜索保留字段，Milvus 顶层返回，不能列入 output_fields（列入会报 "field distance not exist"）
    res = client.search(collection_name=MILVUS_COLLECTION, data=[vector],
                        anns_field="dense", limit=top_k,
                        search_params={"metric_type": "COSINE", "params": {"ef": ef}},
                        output_fields=["chunk_id"])
    latency_ms = (time.perf_counter() - started) * 1000
    # 顶层 distance 即相似度（检索排序结果自带的保留字段）
    hits = [make_hit(hit["entity"]["chunk_id"], float(hit.get("distance", 0.0)), rank, "dense")
            for rank, hit in enumerate(res[0] if res else [], start=1)]
    return hits, latency_ms


def retrieve_dense(rewrite: dict[str, Any], embedder: Any | None = None) -> dict[str, Any]:
    """编排入口：吃 query_rewrite 输出，返回 `{route, hits, degraded, route_latency_ms}`。

    Args:
      rewrite: 查询改写输出（semantic/keywords/entities）
      embedder: 可注入的常驻 EmbeddingClient（W6 进程内复用）；None → 每次新构造
    """
    inputs = extract_route_inputs(rewrite)
    semantic = inputs["semantic"]
    if not semantic:
        return {"route": "dense", "hits": [], "degraded": True,
                "route_latency_ms": 0.0, "reason": "semantic 为空"}
    try:
        hits, latency = _scalar_fetch(semantic, embedder=embedder)
        return {"route": "dense", "hits": hits, "degraded": False, "route_latency_ms": latency}
    except Exception as exc:                                     # noqa: BLE001 - 降级兜底
        return {"route": "dense", "hits": [], "degraded": True,
                "route_latency_ms": 0.0, "reason": f"{type(exc).__name__}: {exc}"}


def _selftest() -> int:
    fail = 0
    # 1) 输入契约解析
    rw = {"semantic": "离心泵振动烈度超标原因", "keywords": ["离心泵", "振动烈度"],
          "entities": [{"text": "离心泵", "type": "equipment"}], "numeric": ["11.2"]}
    inp = extract_route_inputs(rw)
    if inp["semantic"] != rw["semantic"]:
        print("[FAIL] semantic 抽取不正确")
        fail += 1
    if "离心泵" not in inp["keywords"]:
        print("[FAIL] keywords 抽取不正确")
        fail += 1
    if not inp["entities"] or inp["entities"][0]["text"] != "离心泵":
        print("[FAIL] entities 抽取不正确")
        fail += 1
    # 2) 配置加载
    cfg = load_retrieval_config()
    if int(cfg["dense"]["top_k"]) != 20 or cfg["dense"]["hnsw"]["ef"] != 64:
        print(f"[FAIL] 配置加载不正确 {cfg['dense']}")
        fail += 1
    # 3) Milvus 连通（在线环境可用时验证；离线跳过不算失败）
    try:
        import pymilvus as _p                                        # noqa: PLC0415
        from pymilvus import MilvusClient                            # noqa: PLC0415
        client = MilvusClient(uri=MILVUS_URI)
        ok = client.has_collection(MILVUS_COLLECTION)
        print(f"[在线] Milvus collection 存在={ok}")
    except Exception:                                                # noqa: BLE001 - 离线跳过
        print("[离线] Milvus 不可达，跳过连通断言")
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W2 Dense 召回")
    p.add_argument("--query", help="单条问题")
    p.add_argument("--rewrite-json", type=Path, help="query_rewrite 输出 json 文件")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.rewrite_json:
        rw = json.loads(args.rewrite_json.read_text(encoding="utf-8"))
        out = retrieve_dense(rw)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if args.query:
        rw = {"semantic": args.query, "keywords": [], "entities": [], "numeric": []}
        out = retrieve_dense(rw)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())