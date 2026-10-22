"""D0-6 自测：知识准入审核契约补丁（POST /api/knowledge/docs/{id}/admission）。

运行（前置）：
    PG 5433 已启动，迁移 0005_knowledge_admission.sql 已应用。
    .venv\\Scripts\\python.exe scripts\\test_p4_d06_admission.py

覆盖：RBAC（仅 kb_admin）、404/409/422 边界、approve/reject 决策落库、
     knowledge_versions 留痕（version=max+1）、列表返回 admission_status。
通过标准：全部 CHECK 输出 PASS（任一 FAIL 退出码 1）。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import create_app  # noqa: E402
from scripts.seed_users import DEFAULT_PASSWORD, seed  # noqa: E402

# 2026-10-22：随 API_PG_URL 走（集成测试隔离到临时库时需要），不再写死
from app.api.config import POSTGRES_URL  # noqa: E402

PG_DSN = POSTGRES_URL
client = TestClient(create_app())
_results: list[tuple[bool, str, str]] = []
_cleanup_docs: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((bool(cond), name, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def _token(username: str) -> str:
    r = client.post("/api/auth/login",
                    json={"username": username, "password": DEFAULT_PASSWORD})
    assert r.json()["code"] == 0, f"{username} 登录失败：{r.text[:120]}"
    return r.json()["data"]["access_token"]


def _pg_all(sql: str, params: tuple = ()):
    import psycopg                                       # noqa: PLC0415
    with psycopg.connect(PG_DSN) as conn:
        cur = conn.execute(sql, params)
        if cur.description is None:      # DML（DELETE 等）无结果集
            return []
        return cur.fetchall()


def _create_doc(headers: dict, title: str) -> str:
    r = client.post("/api/knowledge/docs", headers=headers,
                    json={"title": title, "doc_type": "manual",
                          "source": "供应商手册", "content": "测试正文"})
    assert r.json()["code"] == 0, r.text[:200]
    doc_id = r.json()["data"]["doc_id"]
    _cleanup_docs.append(doc_id)
    return doc_id


def main() -> int:
    seed(DEFAULT_PASSWORD, reset=False)
    tok_kb = _token("kb_dev")
    tok_eng = _token("eng_dev")
    tok_rev = _token("rev_dev")
    HK = {"Authorization": f"Bearer {tok_kb}"}
    HE = {"Authorization": f"Bearer {tok_eng}"}
    HR = {"Authorization": f"Bearer {tok_rev}"}

    # ---------- 边界 ----------
    r = client.post(f"/api/knowledge/docs/{uuid.uuid4()}/admission",
                    json={"action": "approve"})
    check("R01 未登录 → 401", r.status_code == 401
          and r.json()["code"] == "E_UNAUTHORIZED")

    fake = str(uuid.uuid4())
    r = client.post(f"/api/knowledge/docs/{fake}/admission", headers=HE,
                    json={"action": "approve"})
    check("R02 engineer → 403 E_PERMISSION", r.status_code == 403
          and r.json()["code"] == "E_PERMISSION")
    r = client.post(f"/api/knowledge/docs/{fake}/admission", headers=HR,
                    json={"action": "approve"})
    check("R03 reviewer → 403（准入仅 kb_admin）", r.status_code == 403)

    r = client.post(f"/api/knowledge/docs/{uuid.uuid4()}/admission", headers=HK,
                    json={"action": "approve"})
    check("R04 文档不存在 → 404", r.status_code == 404
          and r.json()["code"] == "E_NOT_FOUND")

    r = client.post(f"/api/knowledge/docs/{fake}/admission", headers=HK,
                    json={"action": "maybe"})
    check("R05 非法 action → 422", r.status_code == 422
          and r.json()["code"] == "E_INVALID_ARG")

    r = client.post("/api/knowledge/docs/not-a-uuid/admission", headers=HK,
                    json={"action": "approve"})
    check("R06 doc_id 非法 UUID → 422", r.status_code == 422)

    # ---------- approve 路径 ----------
    doc_a = _create_doc(HK, "D0-6 自测·准入通过文档")
    r = client.post(f"/api/knowledge/docs/{doc_a}/admission", headers=HK,
                    json={"action": "approve", "comment": "来源可信，准予入库"})
    b = r.json()
    check("R07 kb_dev approve → approved + admitted_by",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["admission_status"] == "approved"
          and b["data"]["admitted_by"] == "kb_dev", b.get("data"))

    rows = _pg_all(
        "SELECT admission_status, admitted_by FROM documents WHERE doc_id=%s",
        (uuid.UUID(doc_a),))
    check("R08 PG documents 落库 approved",
          rows and rows[0][0] == "approved" and rows[0][1] == "kb_dev")
    vers = _pg_all(
        "SELECT version, action, actor FROM knowledge_versions "
        "WHERE doc_id=%s ORDER BY version", (uuid.UUID(doc_a),))
    check("R09 knowledge_versions 留痕 create(v1)+admission_approve(v2)",
          [(v[0], v[1]) for v in vers] == [(1, "create"), (2, "admission_approve")]
          and vers[1][2] == "kb_dev", str(vers))

    r = client.post(f"/api/knowledge/docs/{doc_a}/admission", headers=HK,
                    json={"action": "reject"})
    check("R10 重复决策 → 409 E_CONFLICT", r.status_code == 409
          and r.json()["code"] == "E_CONFLICT")

    # ---------- reject 路径 ----------
    doc_b = _create_doc(HK, "D0-6 自测·准入驳回文档")
    r = client.post(f"/api/knowledge/docs/{doc_b}/admission", headers=HK,
                    json={"action": "reject", "comment": "来源不可信"})
    check("R11 kb_dev reject → rejected",
          r.status_code == 200
          and r.json()["data"]["admission_status"] == "rejected")
    vers_b = _pg_all(
        "SELECT action FROM knowledge_versions WHERE doc_id=%s ORDER BY version",
        (uuid.UUID(doc_b),))
    check("R12 reject 留痕 admission_reject(v2)",
          [v[0] for v in vers_b] == ["create", "admission_reject"], str(vers_b))

    # ---------- 列表返回 admission_status ----------
    r = client.get("/api/knowledge/docs?size=100", headers=HE)
    items = {i["doc_id"]: i for i in r.json()["data"]["items"]}
    check("R13 列表含 admission_status（approved/rejected/pending）",
          r.status_code == 200
          and items.get(doc_a, {}).get("admission_status") == "approved"
          and items.get(doc_b, {}).get("admission_status") == "rejected")

    # ---------- 清理测试文档（按标题前缀全删，含上次中断残留） ----------
    _pg_all("DELETE FROM knowledge_versions WHERE doc_id IN "
            "(SELECT doc_id FROM documents WHERE title LIKE %s)", ("D0-6 自测%",))
    _pg_all("DELETE FROM documents WHERE title LIKE %s", ("D0-6 自测%",))
    left = _pg_all("SELECT count(*) FROM documents WHERE title LIKE %s",
                   ("D0-6 自测%",))
    check("R14 测试文档清理无残留", left[0][0] == 0, f"residual={left[0][0]}")

    failed = [n for ok_, n, _ in _results if not ok_]
    print(f"\n==== D0-6 自测：{len(_results) - len(failed)}/{len(_results)} PASS ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
