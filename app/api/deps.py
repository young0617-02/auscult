"""FastAPI 依赖：登录态解析与 RBAC 角色门控（后端强制，非前端体验优化）。

口径（Phase 4 计划 §6.5）：
- 前端守卫仅作体验优化；本模块是安全边界
- 401：未携带 / 无效 / 过期 token；403 E_PERMISSION：已登录但角色不符
"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, Request

from app.api.db import fetch_user_by_id
from app.api.errors import ApiError
from app.api.security import decode_token

_BEARER = "Bearer "


async def get_current_user(request: Request) -> dict[str, Any]:
    """从 Authorization: Bearer <jwt> 解析并加载当前用户（含 is_active 复核）。"""
    auth = request.headers.get("authorization", "")
    if not auth.startswith(_BEARER):
        raise ApiError("E_UNAUTHORIZED", "未登录或会话已失效")
    token = auth[len(_BEARER):].strip()
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise ApiError("E_UNAUTHORIZED", "登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError("E_UNAUTHORIZED", "无效的登录凭证") from exc

    user = fetch_user_by_id(payload["sub"])
    if user is None or not user["is_active"]:
        raise ApiError("E_UNAUTHORIZED", "账号不存在或已停用")
    return user


def require_roles(*roles: str):
    """角色门控工厂：require_roles("reviewer") → 仅审核员可过。

    用法：@router.post(..., dependencies=[Depends(require_roles("reviewer"))])
    """
    allowed = set(roles)

    async def _check(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user["role"] not in allowed:
            raise ApiError("E_PERMISSION", "你的角色无此权限，请联系管理员")
        return user

    return _check
