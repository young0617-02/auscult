"""图谱邻居查询 REST（D0-2 · 契约4）。

GET /api/graph/neighbors?entity=&hops=
- 供 /graph 图谱页（P4 D17，react-force-graph 邻居查询 + 关系过滤）
- 复用 Phase 2 资产：scripts/retrieval_base.neo4j_run（HTTP tx 端点）+
  configs/triple_schema.json 受控关系白名单（不重写 P0 资产）
- 起始节点按 Entity.name 精确匹配（与 retrieve_graph 同口径）
- Neo4j 不可达 → 200 + degraded=true 降级返回（图谱页展示「图谱暂不可用」，
  不作 502 打断监盘）；实体不存在 → 404 E_NOT_FOUND

返回结构（force-graph 直用）：
  {entity, hops, degraded, reason, latency_ms,
   nodes: [{id, entity_id, name, type}],           # id = Neo4j elementId
   edges: [{source, target, relation, chunk_ids, confidence, source_count}]}
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.api.errors import ApiError, ok

# 复用 Phase 2 检索基座（与 app/tools/query_graph.py 同一引导方式）
PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from retrieval_base import neo4j_run  # noqa: E402

router = APIRouter(prefix="/api/graph", tags=["graph"])

_TRIPLE_SCHEMA_PATH = PROJECT_ROOT / "configs" / "triple_schema.json"
_EDGE_LIMIT = 400   # 单次邻居查询边数上限（UI 渲染保护）


def _load_relations() -> list[str]:
    """受控关系白名单（triple_schema.json neo4j_relation_map）。"""
    schema = json.loads(_TRIPLE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return list(schema.get("neo4j_relation_map", {}).values())


def _cypher_literal(s: str) -> str:
    """转义为安全的 Cypher 字符串字面量（反斜杠 + 单引号）。"""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


@router.get("/neighbors")
async def neighbors(
    entity: str = Query(..., min_length=1, max_length=64, description="起始实体名称（精确匹配）"),
    hops: int = Query(2, ge=1, le=2, description="扩展跳数"),
    _: dict[str, Any] = Depends(get_current_user),
) -> dict:
    rels = _load_relations()
    rel_pat = "|".join(rels) if rels else "r"
    lit = _cypher_literal(entity)

    stmt_start = (
        f"MATCH (n:Entity {{name: {lit}}}) "
        "RETURN elementId(n) AS eid, coalesce(n.id, '') AS entity_id, "
        "coalesce(n.name, '') AS name, coalesce(n.type, '') AS type "
        "LIMIT 1"
    )
    stmt_edges = (
        f"MATCH (s:Entity {{name: {lit}}}) "
        f"MATCH p = (s)-[:{rel_pat}*1..{hops}]-(e:Entity) "
        "WITH nodes(p) AS ns, relationships(p) AS rs "
        "UNWIND range(0, size(rs)-1) AS i "
        "RETURN DISTINCT elementId(ns[i]) AS src, coalesce(ns[i].id, '') AS src_eid, "
        "coalesce(ns[i].name, '') AS src_name, coalesce(ns[i].type, '') AS src_type, "
        "type(rs[i]) AS relation, "
        "elementId(ns[i+1]) AS dst, coalesce(ns[i+1].id, '') AS dst_eid, "
        "coalesce(ns[i+1].name, '') AS dst_name, coalesce(ns[i+1].type, '') AS dst_type, "
        "coalesce(rs[i].source_chunk_ids, []) AS chunk_ids, "
        "rs[i].confidence AS confidence, rs[i].source_count AS source_count "
        f"LIMIT {_EDGE_LIMIT}"
    )

    started = time.perf_counter()
    try:
        results = neo4j_run([stmt_start, stmt_edges])
    except Exception as exc:                                     # noqa: BLE001 - 降级兜底
        return ok({"entity": entity, "hops": hops, "degraded": True,
                   "reason": f"{type(exc).__name__}: {exc}",
                   "nodes": [], "edges": [],
                   "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    start_rows = results[0].get("data", [])
    if not start_rows:
        raise ApiError("E_NOT_FOUND", f"图谱中未找到实体「{entity}」")

    def _node(eid: str, entity_id: str, name: str, ntype: str) -> dict:
        return {"id": eid, "entity_id": entity_id, "name": name, "type": ntype}

    r0 = start_rows[0]["row"]
    nodes: dict[str, dict] = {r0[0]: _node(r0[0], r0[1], r0[2], r0[3])}

    edges: list[dict] = []
    for table in results[1].get("data", []):
        (src, src_eid, src_name, src_type, relation,
         dst, dst_eid, dst_name, dst_type, chunk_ids, conf, scount) = table["row"]
        nodes.setdefault(src, _node(src, src_eid, src_name, src_type))
        nodes.setdefault(dst, _node(dst, dst_eid, dst_name, dst_type))
        edges.append({"source": src, "target": dst, "relation": relation,
                      "chunk_ids": chunk_ids or [],
                      "confidence": conf, "source_count": scount})

    return ok({"entity": entity, "hops": hops, "degraded": False, "reason": None,
               "nodes": list(nodes.values()), "edges": edges,
               "latency_ms": latency_ms})
