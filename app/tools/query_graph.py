"""query_graph 工具执行体（D4）

从 Neo4j 图谱查询与告警相关的路径（≤2 跳），返回 chunk_id 归因。
复用 Phase 2 的 retrieve_graph.py 逻辑（不重写 P0 资产）。

对应交付物: plan/Phase 3 §五 D4 / §四.3
Schema 来源: schemas/tools_v2.json → query_graph
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from query_rewrite import rewrite_rules  # noqa: E402
from retrieve_graph import retrieve_graph as _retrieve_graph_impl  # noqa: E402


def query_graph(question: str) -> dict[str, Any]:
    """图谱路径查询（≤2 跳）。

    参数:
        question: 检索问题（如 "PUMP-A 振动烈度超标的原因"）

    返回:
        {"hits": [...], "degraded": bool, "entities_hit": [...],
         "route_latency_ms": float, "reason": str | None}

    降级: Neo4j 不可达 → degraded=True
    """
    rewrite = rewrite_rules(question)
    return _retrieve_graph_impl(rewrite)
