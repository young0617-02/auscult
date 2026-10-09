"""W2 Sparse 召回（Phase 2 · 混合检索，P2-D3）

职责：用 `keywords`（query_rewrite 输出）原文在 Milvus `kb_p1_v1` 的服务端 BM25（jieba）索引
     上取 `top_k=20`。

★ R-V2-2：稀疏检索走服务端 BM25 函数，**不得**客户端自实现后冒充原生能力。
依赖：`pymilvus` + `retrieval_base` 拓扑；BM25 由服务端 analyzer 完成，查询侧传原始文本。

自检：`python scripts/retrieve_sparse.py --selftest`
用法：`python scripts/retrieve_sparse.py --query "..."`
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


def _scalar_fetch(keywords_text: str) -> tuple[list[dict[str, Any]], float]:
    cfg = load_retrieval_config()
    top_k = int(cfg["sparse"]["top_k"])
    try:
        from pymilvus import MilvusClient                              # noqa: PLC0415
        client = MilvusClient(uri=MILVUS_URI)
    except ImportError as exc:
        raise RuntimeError(f"Sparse 召回依赖缺失：{exc}") from exc
    started = time.perf_counter()
    res = client.search(collection_name=MILVUS_COLLECTION, data=[keywords_text],
                        anns_field="sparse", limit=top_k,
                        output_fields=["chunk_id"])
    latency_ms = (time.perf_counter() - started) * 1000
    hits = [make_hit(hit["entity"]["chunk_id"], float(hit.get("distance", 0.0)), rank, "sparse")
            for rank, hit in enumerate(res[0] if res else [], start=1)]
    return hits, latency_ms


def retrieve_sparse(rewrite: dict[str, Any]) -> dict[str, Any]:
    inputs = extract_route_inputs(rewrite)
    keywords = inputs["keywords"]
    if not keywords:
        return {"route": "sparse", "hits": [], "degraded": True,
                "route_latency_ms": 0.0, "reason": "keywords 为空"}
    try:
        hits, latency = _scalar_fetch(keywords)
        return {"route": "sparse", "hits": hits, "degraded": False, "route_latency_ms": latency}
    except Exception as exc:                                     # noqa: BLE001 - 降级兜底
        return {"route": "sparse", "hits": [], "degraded": True,
                "route_latency_ms": 0.0, "reason": f"{type(exc).__name__}: {exc}"}


def _selftest() -> int:
    fail = 0
    rw = {"semantic": "离心泵振动烈度超标原因", "keywords": ["离心泵", "振动烈度"],
          "entities": [{"text": "离心泵", "type": "equipment"}], "numeric": ["11.2"]}
    inp = extract_route_inputs(rw)
    if "振动烈度" not in inp["keywords"]:
        print("[FAIL] keywords 拼接不正确")
        fail += 1
    cfg = load_retrieval_config()
    if int(cfg["sparse"]["top_k"]) != 20 or cfg["sparse"]["bm25_k1"] != 1.2:
        print("[FAIL] sparse 配置加载不正确")
        fail += 1
    try:
        from pymilvus import MilvusClient                            # noqa: PLC0415
        client = MilvusClient(uri=MILVUS_URI)
        ok = client.has_collection(MILVUS_COLLECTION)
        print(f"[在线] Milvus collection 存在={ok}")
    except Exception:                                                # noqa: BLE001 - 离线跳过
        print("[离线] Milvus 不可达，跳过连通断言")
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W2 Sparse 召回")
    p.add_argument("--query", help="单条问题")
    p.add_argument("--rewrite-json", type=Path, help="query_rewrite 输出 json 文件")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.rewrite_json:
        rw = json.loads(args.rewrite_json.read_text(encoding="utf-8"))
        print(json.dumps(retrieve_sparse(rw), ensure_ascii=False, indent=2))
        return 0
    if args.query:
        rw = {"semantic": args.query, "keywords": [args.query], "entities": [], "numeric": []}
        print(json.dumps(retrieve_sparse(rw), ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())