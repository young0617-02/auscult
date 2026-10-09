"""认证路由：登录 + 当前用户（D0-1）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.db import fetch_user_by_username
from app.api.deps import get_current_user
from app.api.errors import ApiError, ok
from app.api.security import BCRYPT_MAX_BYTES, create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


def _validate_password_length(pw: str) -> None:
    if len(pw.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ApiError("E_INVALID_ARG", "密码长度超限")


@router.post("/login")
async def login(body: LoginIn) -> dict:
    _validate_password_length(body.password)
    user = fetch_user_by_username(body.username)
    # 统一 401 文案：不区分「用户不存在 / 密码错误」，避免账号枚举
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise ApiError("E_UNAUTHORIZED", "用户名或密码错误")
    if not user["is_active"]:
        raise ApiError("E_UNAUTHORIZED", "账号已停用，请联系管理员")

    token = create_access_token(str(user["user_id"]), user["username"], user["role"])
    return ok({
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": str(user["user_id"]),
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        },
    })


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> dict:
    """当前登录用户（RBAC 校验锚点，e2e 用其验证 401/403）。"""
    return ok({
        "user_id": str(user["user_id"]),
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    })
