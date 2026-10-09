"""W2 多路召回并行编排（Phase 2 · 混合检索，P2-D2~D8）

职责：并行执行 **Dense + Sparse**（`ThreadPoolExecutor`），**Graph 独立通道**（P2-R4：
      图谱不进入 RRF 排序，仅作独立证据通道），统一汇总各路候选与降级标记。

输入：`query_rewrite` 输出（`{semantic, keywords, entities}`）。
输出：`{routes: {...}, candidates, degraded_routes, total_latency_ms}`；其中 `routes.dense/sparse`
      为**参与 RRF** 的候选（W3 消费），`routes.graph` 为**独立证据通道**（W4/W5 组装）。

资源纪律：Dense/Sparse 并发、Graph 并发执行；任一路失败 → 该路空 + `degraded_routes` 置位，
          不阻断整条链路。纯 CPU（Dense 编码本地 BGE-M3），不占 GPU（R10/V1 错峰继承）。

自检：`python scripts/retrieval.py --selftest`
用法：`python scripts/retrieval.py --query "..."`（内部先走 rules 改写，再三路召回）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from query_rewrite import rewrite_rules
from retrieve_dense import retrieve_dense
from retrieve_graph import retrieve_graph
from retrieve_sparse import retrieve_sparse


def retrieve_all(rewrite: dict[str, Any],
                 parallel: bool = True,
                 embedder: Any | None = None) -> dict[str, Any]:
    """并行执行 Dense+Sparse+Graph，返回统一结果。

    Args:
      rewrite: query_rewrite 输出（含 semantic/keywords/entities）
      parallel: True → Dense 与 Sparse 并发；Graph 独立
      embedder: 可注入常驻 EmbeddingClient（W6 进程内复用）；None → dense 每次新构造
    Returns:
      {"routes": {dense, sparse, graph}, "candidates": Dense+Sparse 合并(供 W3),
       "degraded_routes": [...], "graph_paths": 独立图谱证据, "total_latency_ms": float}
    """
    started = time.perf_counter()
    if parallel:
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_d = pool.submit(retrieve_dense, rewrite, embedder)
            f_s = pool.submit(retrieve_sparse, rewrite)
            f_g = pool.submit(retrieve_graph, rewrite)
            dense, sparse, graph = f_d.result(), f_s.result(), f_g.result()
    else:
        dense = retrieve_dense(rewrite, embedder)
        sparse = retrieve_sparse(rewrite)
        graph = retrieve_graph(rewrite)

    candidates = dense["hits"] + sparse["hits"]          # 参与 RRF（W3）的候选
    degraded = []
    for route, res in (("dense", dense), ("sparse", sparse), ("graph", graph)):
        if res["degraded"]:
            degraded.append(route)
    total_ms = (time.perf_counter() - started) * 1000
    return {
        "routes": {"dense": dense, "sparse": sparse, "graph": graph},
        "candidates": candidates,
        "degraded_routes": degraded,
        "graph_paths": graph["hits"],                     # 独立证据通道，不进 RRF
        "graph_entities_hit": graph.get("entities_hit", []),
        "total_latency_ms": round(total_ms, 1),
        "route_latency_ms": {"dense": dense["route_latency_ms"],
                             "sparse": sparse["route_latency_ms"],
                             "graph": graph["route_latency_ms"]},
    }


def _selftest() -> int:
    fail = 0
    # 1) 改写→三路输入
    rw = rewrite_rules("离心泵驱动端振动烈度超标，轴承箱温度偏高，排查什么原因？")
    if not rw["semantic"] or not rw["entities"]:
        print("[FAIL] 规则改写未产出完整输入")
        fail += 1
    # 2) 编排契约（在线环境跑真召回；离线 skip 连通断言但检查结构）
    out = retrieve_all(rw, parallel=True)
    for route in ("dense", "sparse", "graph"):
        r = out["routes"][route]
        if "route" not in r or "hits" not in r or "degraded" not in r:
            print(f"[FAIL] {route} 结果契约不完整 {list(r.keys())}")
            fail += 1
    if not isinstance(out["candidates"], list) or not isinstance(out["degraded_routes"], list):
        print("[FAIL] 编排输出结构不正确")
        fail += 1
    # 3) Dense 与 Sparse 并发生效（无法在 selftest 断言时序，仅确认可运行）
    print("[OK] 编排可运行（Dense+Sparse 并行，Graph 独立通道）")
    print(f"[信息] 各路由命中数: dense={len(out['routes']['dense']['hits'])}, "
          f"sparse={len(out['routes']['sparse']['hits'])}, "
          f"graph={len(out['routes']['graph']['hits'])}")
    print(f"[信息] degraded_routes={out['degraded_routes']}")
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W2 多路召回并行编排")
    p.add_argument("--query", help="单条问题")
    p.add_argument("--rewrite-json", type=Path, help="query_rewrite 输出 json 文件")
    p.add_argument("--serial", action="store_true", help="关闭并行（对比用）")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.rewrite_json:
        rw = json.loads(args.rewrite_json.read_text(encoding="utf-8"))
        print(json.dumps(retrieve_all(rw, parallel=not args.serial), ensure_ascii=False, indent=2))
        return 0
    if args.query:
        rw = rewrite_rules(args.query)
        print(json.dumps(retrieve_all(rw, parallel=not args.serial), ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())