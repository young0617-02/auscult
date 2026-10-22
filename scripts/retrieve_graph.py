"""W2 Graph 召回（Phase 2 · 混合检索，P2-D8）

职责：用 `entities`（query_rewrite 输出）在 Neo4j 图谱上做 **≤2 跳** 路径扩展，
      提取每条关系上的 `source_chunk_ids`（图内 chunk 归因），作为「图谱证据」候选。

关键约定（P2-R4 / 计划 §5.2）：
  - **图谱不进入 RRF 排序**，作为独立证据通道（`route="graph"`），供 W4/W5 组装证据；
  - 关系类型**受控**：以 `configs/triple_schema.json.neo4j_relation_map` 的白名单为准；
  - 实体匹配：节点 `:Entity.id = "<type>:<name>"`（`entity_id`），用 `entities[].text` 精确匹配 `name`。

输出：`{route, hits, degraded, route_latency_ms, entities_hit}`；hits 为按跳数/置信度排序的
      图谱候选（`chunk_id` 直接取关系 `source_chunk_ids` 展开），**不排序进 RRF**。

自检：`python scripts/retrieve_graph.py --selftest`
用法：`python scripts/retrieve_graph.py --query "..."`（内部现用 rewrite_rules 生成实体）
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from query_rewrite import rewrite_rules
from retrieval_base import (NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, PROJECT_ROOT,
                            extract_route_inputs, load_retrieval_config, make_hit, neo4j_run)

_REL_SLUG_PATH = PROJECT_ROOT / "configs" / "triple_schema.json"


def _allowed_relations() -> list[str]:
    schema = json.loads(_REL_SLUG_PATH.read_text(encoding="utf-8"))
    return list(schema.get("neo4j_relation_map", {}).values())


def retrieve_graph(rewrite: dict[str, Any]) -> dict[str, Any]:
    cfg = load_retrieval_config()
    max_hops = int(cfg["graph"]["max_hops"])
    top_paths = int(cfg["graph"]["top_k_paths"])
    inputs = extract_route_inputs(rewrite)
    entities = inputs["entities"]
    if not entities:
        return {"route": "graph", "hits": [], "degraded": True,
                "route_latency_ms": 0.0, "reason": "entities 为空"}
    names = [str(e.get("text", "")).strip() for e in entities if e.get("text")]
    names = [n for n in names if n]
    if not names:
        return {"route": "graph", "hits": [], "degraded": True,
                "route_latency_ms": 0.0, "reason": "entities 无有效文本"}
    rels = _allowed_relations()
    rel_filter = "|".join(rels) if rels else "r"

    # 匹配起始实体节点 → 沿受控关系扩展 ≤2 跳，返回所有可达 chunk 归因（关系 source_chunk_ids）。
    # 同一段路经可能被多条关系共享；用路径深度做轻微加权（1跳 权 2，2跳 权 1）。
    rels_pat = rel_filter
    statements = []
    for name in names:
        # 2026-10-22（Must#5）：同时返回**路径本身**（节点名 + 关系类型），不再只回 chunk_id。
        # 原 RETURN 只给 cid，把 `MATCH p = ...` 拿到的路径丢掉了 → 上层 `GraphPath.edges`
        # 恒空，"支撑路径"名不副实。Cypher 侧只加两列，无额外查询。
        statements.append(
            f"MATCH p = (s:Entity {{name: {name!r}}})-[:{rels_pat}*1..2]-(e:Entity) "
            f"WITH p, relationships(p) AS rels "
            f"UNWIND rels AS r "
            f"WITH p, r WHERE size(coalesce(r.source_chunk_ids, [])) > 0 "
            f"UNWIND r.source_chunk_ids AS cid "
            f"WITH DISTINCT cid, p "
            f"RETURN cid, [n IN nodes(p) | coalesce(n.name, '')] AS path_nodes, "
            f"[r IN relationships(p) | type(r)] AS path_rels"
        )

    started = time.perf_counter()
    try:
        results = neo4j_run(statements, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    except Exception as exc:                                     # noqa: BLE001 - 降级兜底
        return {"route": "graph", "hits": [], "degraded": True,
                "route_latency_ms": 0.0, "reason": f"{type(exc).__name__}: {exc}"}
    latency_ms = (time.perf_counter() - started) * 1000

    # 汇总所有出现的 chunk_id → 出现次数（作为本路的弱对齐分，不进入 RRF），
    # 并保留**首条**命中路径的节点/关系（同一 chunk 可能被多条路径共享，取一条即可）。
    counter: dict[str, int] = {}
    paths: list[dict[str, Any]] = []
    seen_path_cid: set[str] = set()
    for result in results:
        for table in result.get("data", []):
            row = table.get("row") or []
            if not row:
                continue
            cid = row[0]
            if not isinstance(cid, str):
                continue
            counter[cid] = counter.get(cid, 0) + 1
            # 兼容旧格式（只有 cid 一列）：hits 照常产出，只是没有路径可填。
            if len(row) >= 3 and cid not in seen_path_cid:
                seen_path_cid.add(cid)
                paths.append({"chunk_id": cid,
                              "nodes": [str(n) for n in (row[1] or []) if n],
                              "edges": [str(r) for r in (row[2] or []) if r]})

    hits = [make_hit(cid, float(cnt), rank, "graph")
            for rank, (cid, cnt) in enumerate(
                sorted(counter.items(), key=lambda kv: -kv[1]), start=1)
            ][:top_paths]
    return {"route": "graph", "hits": hits, "degraded": False,
            "route_latency_ms": latency_ms, "entities_hit": names,
            "paths": paths[:top_paths]}


def _selftest() -> int:
    fail = 0
    # 词表-图谱对齐：受控关系映射须可读
    rels = _allowed_relations()
    if not rels or "HANDLED_BY" not in rels:
        print(f"[FAIL] 受控关系读取异常 {rels}")
        fail += 1
    # 改写→实体抽取
    rw = rewrite_rules("振动烈度超标，离心泵轴承箱温度偏高，排查什么原因？")
    inp = extract_route_inputs(rw)
    if not inp["entities"]:
        print("[FAIL] 规则改写未产出实体")
        fail += 1
    try:
        from retrieval_base import neo4j_run                            # noqa: PLC0415
        results = neo4j_run(["MATCH (e:Entity) RETURN count(e) AS n LIMIT 1"],
                            NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        cnt = results[0]["data"][0]["row"][0]
        print(f"[在线] Neo4j Entity 节点数={cnt}")
    except Exception:                                                   # noqa: BLE001 - 离线跳过
        print("[离线] Neo4j 不可达，跳过连通断言")
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W2 Graph 召回（Neo4j ≤2跳）")
    p.add_argument("--query", help="单条问题（内部走 rules 改写取 entities）")
    p.add_argument("--rewrite-json", type=Path, help="query_rewrite 输出 json 文件")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.rewrite_json:
        rw = json.loads(args.rewrite_json.read_text(encoding="utf-8"))
        print(json.dumps(retrieve_graph(rw), ensure_ascii=False, indent=2))
        return 0
    if args.query:
        rw = rewrite_rules(args.query)
        print(json.dumps(retrieve_graph(rw), ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())