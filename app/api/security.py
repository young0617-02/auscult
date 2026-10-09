"""密码哈希（bcrypt）与 JWT 签发/校验。

口径：
- bcrypt 5.x：72 字节上限在 login 入口校验（超限直接 E_INVALID_ARG，不静默截断）
- JWT：HS256，payload = {sub, username, role, exp}；不塞敏感字段
"""

from __future__ import annotations

import datetime as dt

import bcrypt
import jwt

from app.api.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET

# ---------------- 密码 ----------------
BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    pw = plain.encode("utf-8")
    if len(pw) > BCRYPT_MAX_BYTES:
        raise ValueError("密码超过 bcrypt 72 字节上限")
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, UnicodeError):
        return False


# ---------------- JWT ----------------
def create_access_token(user_id: str, username: str, role: str) -> str:
    now = dt.datetime.now(dt.UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """校验并解出 payload；任何失败抛 jwt.InvalidTokenError（由 deps 转 401）。"""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
