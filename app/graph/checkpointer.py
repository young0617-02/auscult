"""PostgreSQL Checkpointer 工厂（Phase 0 已定稿）

采纳方案：langgraph-checkpoint-postgres==3.1.2（候选 B，官方实现）
决策依据：docs/p0-decision-checkpoint.md §2.1（Redis 候选 A 因 B7 阻塞弃用）
连接：postgresql://root:123456@127.0.0.1:5433/auscult_v2

用法（contextmanager，连接生命周期由 with 块界定）：
    with build_checkpointer() as checkpointer:
        graph = build_graph(checkpointer)
        result = graph.invoke(initial, config=config)
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

POSTGRES_URL = os.environ.get(
    "LANGGRAPH_PG_URL",
    "postgresql://root:123456@127.0.0.1:5433/auscult_v2",
)


@contextmanager
def build_checkpointer(url: str | None = None):
    """构造 PostgreSQL checkpointer 生命周期（contextmanager）。

    langgraph 官方 PostgresSaver.from_conn_string() 返回上下文管理器：
    连接池的连接生命周期由 with 块界定。graph.compile + invoke/get_state
    必须位于 with 块内，块退出即关连接。
    """
    from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415

    conn_str = url or POSTGRES_URL
    with PostgresSaver.from_conn_string(conn_str) as saver:
        saver.setup()           # 建表（幂等，首次执行时创建 checkpoint 表）
        yield saver
