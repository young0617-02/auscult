"""D0-1 自测：FastAPI 骨架 + users 迁移 + JWT 登录 + RBAC + /api/health。

运行（前置：PG 5433 已启动、迁移 0004 已应用）：
    .venv\\Scripts\\python.exe scripts\\seed_users.py
    .venv\\Scripts\\python.exe scripts\\test_p4_d01_auth.py

通过标准：全部 CHECK 输出 PASS（任一 FAIL 退出码 1）。
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt as pyjwt  # noqa: E402
import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.config import JWT_ALGORITHM, JWT_SECRET, POSTGRES_URL  # noqa: E402
from app.api.deps import require_roles  # noqa: E402
from app.api.errors import ApiError  # noqa: E402
from app.api.main import create_app  # noqa: E402
from scripts.seed_users import DEFAULT_PASSWORD, seed  # noqa: E402

client = TestClient(create_app())
_results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((bool(cond), name, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def main() -> int:
    # ---------- 前置：种子幂等 ----------
    seed(DEFAULT_PASSWORD, reset=False)
    seed(DEFAULT_PASSWORD, reset=False)  # 二次执行应 0 插入
    with psycopg.connect(POSTGRES_URL) as conn:
        roles = [r[0] for r in conn.execute("SELECT role FROM users ORDER BY role").fetchall()]
        n_users = conn.execute("SELECT count(*) FROM users").fetchone()[0]
    check("R01 种子幂等且四角色齐备", n_users == 4 and roles == ["engineer", "kb_admin", "reviewer", "sys_admin"],
          f"users={n_users} roles={roles}")

    # ---------- 根包络 + trace_id ----------
    r = client.get("/api")
    body = r.json()
    check("R02 根包络 {code,message,data,trace_id}",
          r.status_code == 200 and body["code"] == 0 and all(
              k in body for k in ("code", "message", "data", "trace_id")),
          str(body)[:80])
    check("R03 X-Trace-Id 响应头存在", len(r.headers.get("x-trace-id", "")) == 16,
          r.headers.get("x-trace-id", "<缺>"))

    # ---------- /api/health ----------
    r = client.get("/api/health")
    h = r.json()
    keys = {"pg", "milvus", "neo4j", "tdengine", "redis", "cloud_budget"}
    check("R04 health 公开可访问且字段齐备",
          r.status_code == 200 and h["code"] == 0 and keys <= set(h["data"].keys()),
          str(h["data"])[:120])
    check("R05 PG 探测 up（容器已启动）", h["data"]["pg"]["status"] == "up",
          str(h["data"]["pg"]))
    check("R06 health 不抛 500（down 降级）", r.status_code == 200)

    # ---------- 登录边界 ----------
    r = client.post("/api/auth/login", json={"username": "eng_dev", "password": "wrong-pw"})
    check("R07 密码错误 → 401 E_UNAUTHORIZED",
          r.status_code == 401 and r.json()["code"] == "E_UNAUTHORIZED", r.text[:80])
    r = client.post("/api/auth/login", json={"username": "no_such_user", "password": "x"})
    check("R08 用户不存在 → 同文案 401（防账号枚举）",
          r.status_code == 401 and r.json()["message"] == "用户名或密码错误")
    r = client.post("/api/auth/login", json={"password": "x"})
    check("R09 缺字段 → 422 E_INVALID_ARG",
          r.status_code == 422 and r.json()["code"] == "E_INVALID_ARG")
    r = client.post("/api/auth/login", json={"username": "eng_dev", "password": "长" * 80})
    check("R10 密码超 72 字节 → 422（不静默截断）", r.status_code == 422)

    # ---------- 登录成功 + /me ----------
    r = client.post("/api/auth/login", json={"username": "eng_dev", "password": DEFAULT_PASSWORD})
    login_body = r.json()
    check("R11 工程师登录成功", r.status_code == 200 and login_body["code"] == 0
          and login_body["data"]["user"]["role"] == "engineer", str(login_body["data"])[:100])
    token = login_body["data"]["access_token"]

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    check("R12 /me 返回当前用户", r.status_code == 200 and r.json()["data"]["username"] == "eng_dev")
    r = client.get("/api/auth/me")
    check("R13 无 token → 401", r.status_code == 401 and r.json()["code"] == "E_UNAUTHORIZED")
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage.token.here"})
    check("R14 伪造 token → 401", r.status_code == 401)
    expired = pyjwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "exp": 1},
        JWT_SECRET, algorithm=JWT_ALGORITHM)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})
    check("R15 过期 token → 401（非 500）", r.status_code == 401)

    # ---------- RBAC 门控（单元级：require_roles 工厂，协程需显式驱动） ----------
    import asyncio

    engineer = {"role": "engineer"}
    reviewer = {"role": "reviewer"}
    try:
        asyncio.run(require_roles("reviewer")(user=engineer))  # type: ignore[call-arg]
        check("R16 工程师过 reviewer 门控被拒", False, "未抛出")
    except ApiError as e:
        check("R16 工程师过 reviewer 门控被拒", e.code == "E_PERMISSION", e.code)
    try:
        asyncio.run(require_roles("reviewer", "kb_admin")(user=reviewer))  # type: ignore[call-arg]
        check("R17 审核员过 reviewer 门控通过", True)
    except ApiError as e:
        check("R17 审核员过 reviewer 门控通过", False, e.code)

    failed = [n for ok_, n, _ in _results if not ok_]
    print(f"\n==== D0-1 自测：{len(_results) - len(failed)}/{len(_results)} PASS ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
