"""API 层数据库访问（psycopg 3，短连接 + 超时保护）。

开发期单机负载下按请求短连接即可（psycopg 3 连接建立 ≈1ms 本机）；
如后续压测成为瓶颈再升 psycopg_pool（依赖已在 requirements.txt 锁定）。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
import psycopg.rows

from app.api.config import POSTGRES_URL
from app.api.errors import ApiError


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """获取一个 PG 连接（with 块界定生命周期，异常自动回滚）。"""
    try:
        with psycopg.connect(POSTGRES_URL, connect_timeout=5,
                             row_factory=psycopg.rows.dict_row) as conn:
            yield conn
    except psycopg.OperationalError as exc:
        raise ApiError("E_UPSTREAM", "数据库暂不可用，请稍后重试") from exc


def fetch_user_by_username(username: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, username, password_hash, display_name, role, is_active "
            "FROM users WHERE username = %s", (username,)).fetchone()
    return dict(row) if row else None


def fetch_user_by_id(user_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, username, display_name, role, is_active "
            "FROM users WHERE user_id = %s", (user_id,)).fetchone()
    return dict(row) if row else None
