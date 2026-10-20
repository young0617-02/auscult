"""健康检查路由（公开）：存储/数据源延迟 + 云端预算（契约补丁 §3）。

口径：
- 全部探测带 1s 超时、异常降级为 down，health 永不 500
- 延迟单位 ms；down 时 latency 为 null
- cloud_budget 读取 Redis `budget:cloud:{YYYY-MM-DD}`（§5.7）；Redis 不可达时 used=null
"""

from __future__ import annotations

import datetime as dt
import socket
import time

from fastapi import APIRouter

from app.api.config import (
    CLOUD_BUDGET_LIMIT, HEALTH_TIMEOUT_S, MILVUS_HOST, MILVUS_PORT,
    NEO4J_HOST, NEO4J_PORT, REDIS_HOST, REDIS_PASSWORD, REDIS_PORT,
    TDENGINE_HOST, TDENGINE_PORT,
    POSTGRES_URL,
)
from app.api.errors import ok

router = APIRouter(prefix="/api/health", tags=["health"])


def _tcp_probe(host: str, port: int) -> dict:
    """TCP 连通性探测（milvus/neo4j/tdengine/redis 通用）。"""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=HEALTH_TIMEOUT_S):
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            return {"status": "up", "latency_ms": latency_ms}
    except OSError:
        return {"status": "down", "latency_ms": None}


def _pg_probe() -> dict:
    """PG 真实查询探测（不仅 TCP，验证鉴权与库可用）。"""
    import psycopg

    start = time.perf_counter()
    try:
        with psycopg.connect(POSTGRES_URL, connect_timeout=HEALTH_TIMEOUT_S) as conn:
            conn.execute("SELECT 1")
        return {"status": "up", "latency_ms": round((time.perf_counter() - start) * 1000, 1)}
    except psycopg.Error:
        return {"status": "down", "latency_ms": None}


def _cloud_budget_probe() -> dict:
    """云端预算余量（当日已用次数）。Redis 故障时降级 used=None。"""
    today = dt.date.today().isoformat()
    try:
        import redis  # redis==6.3.0，已在 requirements.txt 锁定

        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                             password=REDIS_PASSWORD,   # ISS-051：db 0 需鉴权
                             socket_connect_timeout=HEALTH_TIMEOUT_S, db=0)
        used = client.get(f"budget:cloud:{today}")
        return {"used": int(used) if used is not None else 0, "limit": CLOUD_BUDGET_LIMIT}
    except Exception:  # noqa: BLE001 — health 降级路径，任何异常都不外抛
        return {"used": None, "limit": CLOUD_BUDGET_LIMIT}


def _llm_probe() -> dict:
    """LLM 后端与诊断模式快照（P7 · Agent 化；不含密钥）。

    配置非法（env 写错）时降级为 error 标记，health 仍 200——
    运营侧据此一眼确认「当前跑的是云端还是本地、Agent 还是确定性」。
    """
    from app.llm import config as llm_config

    try:
        return llm_config.describe()
    except Exception:  # noqa: BLE001 — health 降级路径，任何异常都不外抛
        return {"backend": None, "diagnosis_mode": None, "error": "config_invalid"}


@router.get("")
async def health() -> dict:
    return ok({
        "pg": _pg_probe(),
        "milvus": _tcp_probe(MILVUS_HOST, MILVUS_PORT),
        "neo4j": _tcp_probe(NEO4J_HOST, NEO4J_PORT),
        "tdengine": _tcp_probe(TDENGINE_HOST, TDENGINE_PORT),
        "redis": _tcp_probe(REDIS_HOST, REDIS_PORT),
        "cloud_budget": _cloud_budget_probe(),
        "llm": _llm_probe(),
    })
