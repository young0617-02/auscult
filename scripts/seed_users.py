"""种子用户写入（幂等）—— RBAC 四角色开发账号。

角色 ↔ 账号（V5.0 §7.2 / UI 方案 §1.2）：
    engineer  → eng_dev  张工（工程）
    reviewer  → rev_dev  李工（审核）
    kb_admin  → kb_dev   王工（知识库）
    sys_admin → sys_dev  系统管理员

用法：
    .venv\\Scripts\\python.exe scripts\\seed_users.py                # 写入（幂等，已存在跳过）
    .venv\\Scripts\\python.exe scripts\\seed_users.py --password X   # 重设全部密码（--reset）
⚠️ 开发默认密码 Auscult#Dev2026 仅限本机；生产必须改密 + 换 JWT_SECRET。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from app.api.config import POSTGRES_URL  # noqa: E402
from app.api.security import hash_password  # noqa: E402

DEFAULT_PASSWORD = "Auscult#Dev2026"

SEED_USERS = [
    # username, display_name, role
    ("eng_dev", "张工（工程）", "engineer"),
    ("rev_dev", "李工（审核）", "reviewer"),
    ("kb_dev", "王工（知识库）", "kb_admin"),
    ("sys_dev", "系统管理员", "sys_admin"),
]


def seed(password: str, reset: bool) -> int:
    password_hash = hash_password(password)
    inserted = 0
    with psycopg.connect(POSTGRES_URL, connect_timeout=5) as conn:
        for username, display_name, role in SEED_USERS:
            if reset:
                cur = conn.execute(
                    "UPDATE users SET password_hash = %s, updated_at = now() "
                    "WHERE username = %s", (password_hash, username))
            else:
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash, display_name, role) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    (username, password_hash, display_name, role))
            inserted += cur.rowcount
        conn.commit()
    return inserted


def main() -> None:
    ap = argparse.ArgumentParser(description="RBAC 种子用户写入（幂等）")
    ap.add_argument("--password", default=DEFAULT_PASSWORD, help="开发默认密码")
    ap.add_argument("--reset", action="store_true", help="已存在账号也重设密码")
    args = ap.parse_args()

    n = seed(args.password, args.reset)
    action = "重设密码" if args.reset else "写入/跳过"
    print(f"[seed_users] {action} {n} 个账号（共 {len(SEED_USERS)} 角色）；"
          f"默认密码：{'<自定义>' if args.password != DEFAULT_PASSWORD else 'Auscult#Dev2026'}")


if __name__ == "__main__":
    main()
