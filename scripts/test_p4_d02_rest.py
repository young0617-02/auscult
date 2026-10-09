"""D0-2 自测：REST 五契约（alarms / reports 列表+详情 / graph neighbors / knowledge）。

运行（前置）：
    1. PG 5433 已启动、迁移已应用、users 已种子
       .venv\\Scripts\\python.exe scripts\\seed_users.py
    2. Neo4j 已启动（docker start auscult-neo4j）且图谱已有 B4 实体数据
    .venv\\Scripts\\python.exe scripts\\test_p4_d02_rest.py

通过标准：全部 CHECK 输出 PASS（任一 FAIL 退出码 1）。
种子策略：告警/文档种子幂等保留（ALM-D02-SEED-001 等），临时报告测后清理。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.config import POSTGRES_URL  # noqa: E402
from app.api.main import create_app  # noqa: E402
from scripts.seed_users import DEFAULT_PASSWORD, seed  # noqa: E402

client = TestClient(create_app())
_results: list[tuple[bool, str, str]] = []

ALARM_ID = "ALM-D02-SEED-001"
DOC_ID = uuid.UUID("00000000-0000-0000-0000-00000000d002")
TMP_REPORT_ID = "RPT-d02test000000001"      # 4+16=20 字符，与列宽一致
TMP_IDEM_KEY = "d02test000000001"


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((bool(cond), name, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def _token(username: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": DEFAULT_PASSWORD})
    assert r.json()["code"] == 0, f"{username} 登录失败：{r.text[:120]}"
    return r.json()["data"]["access_token"]


def seed_rows() -> None:
    """种子样例告警 + 文档（幂等保留）；临时报告先删后插（测后清理）。"""
    with psycopg.connect(POSTGRES_URL) as conn:
        conn.execute(
            """INSERT INTO alerts (alarm_id, device_id, metric, value, severity, status, ts)
               VALUES (%s, 'PUMP-A', 'vib_rms', 9.6, 'warning', 'open', %s)
               ON CONFLICT (alarm_id) DO NOTHING""",
            (ALARM_ID, dt.datetime.now(dt.timezone.utc)))
        conn.execute(
            """INSERT INTO documents
                   (doc_id, title, source, doc_type, device_model, checksum, status)
               VALUES (%s, 'D0-2 自测样例文档', 'test-seed', 'manual', 'PUMP-A', 'seed-d02', 'pending')
               ON CONFLICT (doc_id) DO NOTHING""",
            (DOC_ID,))
        # 临时报告：先清理可能的历史残留再插入
        conn.execute("DELETE FROM reports WHERE report_id = %s", (TMP_REPORT_ID,))
        conn.execute(
            """INSERT INTO reports
                   (report_id, idempotency_key, thread_id, payload, risk_level,
                    confidence, review_status, degrade_reason)
               VALUES (%s, %s, 'thread-d02-test', %s, 'high', 0.88, NULL, NULL)""",
            (TMP_REPORT_ID, TMP_IDEM_KEY,
             json.dumps({"diagnosis": "D0-2 自测诊断结论：轴承磨损特征明显",
                         "root_causes": [], "suggestions": [], "confidence": 0.88,
                         "risk_level": "high", "human_review": None,
                         "degrade_reason": None, "errors": []},
                        ensure_ascii=False)))
        conn.commit()


def cleanup() -> None:
    with psycopg.connect(POSTGRES_URL) as conn:
        conn.execute("DELETE FROM reports WHERE report_id = %s", (TMP_REPORT_ID,))
        conn.commit()


def main() -> int:
    seed_rows()

    # ---------- 契约1：GET /api/alarms ----------
    r = client.get("/api/alarms")
    check("R01 无 token 读告警 → 401 包络",
          r.status_code == 401 and r.json()["code"] == "E_UNAUTHORIZED", r.text[:80])

    tok = _token("eng_dev")
    H = {"Authorization": f"Bearer {tok}"}

    r = client.get("/api/alarms?page=1&size=5", headers=H)
    b = r.json()
    items = b["data"]["items"]
    check("R02 告警分页包络 {items,total,page,size} + X-Trace-Id",
          r.status_code == 200 and b["code"] == 0
          and all(k in b["data"] for k in ("items", "total", "page", "size"))
          and len(r.headers.get("x-trace-id", "")) == 16,
          f"total={b['data']['total']} items={len(items)}")
    check("R03 告警种子在列且字段齐备",
          any(it["alarm_id"] == ALARM_ID for it in items)
          and all(k in items[0] for k in ("alarm_id", "device_id", "metric", "value",
                                          "severity", "status", "ts")),
          str(items[0])[:100] if items else "<空>")
    r = client.get("/api/alarms?status=open&size=100", headers=H)
    in_open = any(it["alarm_id"] == ALARM_ID for it in r.json()["data"]["items"])
    r = client.get("/api/alarms?status=closed&size=100", headers=H)
    in_closed = any(it["alarm_id"] == ALARM_ID for it in r.json()["data"]["items"])
    check("R04 状态筛选生效（open 含种子 / closed 不含）", in_open and not in_closed,
          f"open={in_open} closed={in_closed}")
    r = client.get("/api/alarms?severity=critical&size=100", headers=H)
    check("R05 严重度筛选（critical 不含 warning 种子）",
          all(it["severity"] == "critical" for it in r.json()["data"]["items"]))

    # ---------- 契约2：GET /api/reports ----------
    r = client.get("/api/reports?page=1&size=50", headers=H)
    b = r.json()
    check("R06 报告列表分页包络 + 临时报告在列",
          r.status_code == 200 and b["code"] == 0
          and all(k in b["data"] for k in ("items", "total", "page", "size"))
          and any(it["report_id"] == TMP_REPORT_ID for it in b["data"]["items"]),
          f"total={b['data']['total']}")
    row = next((it for it in b["data"]["items"] if it["report_id"] == TMP_REPORT_ID), {})
    check("R07 列表行含 diagnosis 摘要字段",
          "D0-2 自测诊断结论" in (row.get("diagnosis") or ""), str(row)[:100])

    r = client.get("/api/reports?risk=high&size=100", headers=H)
    check("R08 risk=high 筛选含临时报告",
          any(it["report_id"] == TMP_REPORT_ID for it in r.json()["data"]["items"]))
    r = client.get("/api/reports?risk=low&size=100", headers=H)
    check("R09 risk=low 筛选不含临时报告",
          all(it["report_id"] != TMP_REPORT_ID for it in r.json()["data"]["items"]))
    r = client.get("/api/reports?status=pending&size=100", headers=H)
    check("R10 status=pending（review_status IS NULL）含临时报告",
          all(it["review_status"] is None for it in r.json()["data"]["items"])
          and any(it["report_id"] == TMP_REPORT_ID for it in r.json()["data"]["items"]))
    r = client.get("/api/reports?status=bogus", headers=H)
    check("R11 非法 status → 422 E_INVALID_ARG",
          r.status_code == 422 and r.json()["code"] == "E_INVALID_ARG", r.text[:80])

    # ---------- 契约3：GET /api/reports/{id} ----------
    r = client.get(f"/api/reports/{TMP_REPORT_ID}", headers=H)
    b = r.json()
    check("R12 报告详情全量结构",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["report_id"] == TMP_REPORT_ID
          and b["data"]["risk_level"] == "high"
          and b["data"]["payload"]["diagnosis"] == "D0-2 自测诊断结论：轴承磨损特征明显",
          str(b["data"])[:120])
    r = client.get("/api/reports/RPT-notexist000001", headers=H)
    check("R13 报告不存在 → 404 E_NOT_FOUND",
          r.status_code == 404 and r.json()["code"] == "E_NOT_FOUND")

    # ---------- 契约4：GET /api/graph/neighbors（Neo4j 实联测） ----------
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from retrieval_base import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, neo4j_run  # noqa: E402

    entity_name = None
    try:
        res = neo4j_run(["MATCH (n:Entity) RETURN n.name AS name LIMIT 1"],
                        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        data = res[0].get("data", [])
        entity_name = data[0]["row"][0] if data else None
    except Exception as exc:                                     # noqa: BLE001
        print(f"  [WARN] Neo4j 不可达：{exc}")

    if entity_name is None:
        check("R14 图谱邻居查询（跳过：Neo4j 无实体数据，请先跑 B4 入库）", True,
              "实体名=None")
    else:
        r = client.get(f"/api/graph/neighbors?entity={entity_name}", headers=H)
        b = r.json()
        nodes, edges = b["data"]["nodes"], b["data"]["edges"]
        check("R14 图谱邻居查询（Neo4j 实联测）结构完整",
              r.status_code == 200 and b["code"] == 0 and b["data"]["degraded"] is False
              and len(nodes) >= 1 and nodes[0]["name"] == entity_name
              and all(k in nodes[0] for k in ("id", "entity_id", "name", "type")),
              f"entity={entity_name} nodes={len(nodes)} edges={len(edges)} "
              f"latency={b['data']['latency_ms']}ms")
        if edges:
            e0 = edges[0]
            check("R15 邻居边含受控关系/归因字段",
                  all(k in e0 for k in ("source", "target", "relation", "chunk_ids")),
                  f"{e0['source'][:8]}…-[{e0['relation']}]->{e0['target'][:8]}… "
                  f"chunks={len(e0['chunk_ids'])}")
            node_ids = {n["id"] for n in nodes}
            check("R16 边端点均在节点集中", e0["source"] in node_ids and e0["target"] in node_ids)
        else:
            check("R15 邻居边（该实体无边，跳过断言）", True)
            check("R16 边端点一致性（无边，跳过断言）", True)
        r = client.get("/api/graph/neighbors?entity=__绝对不存在__", headers=H)
        check("R17 实体不存在 → 404 E_NOT_FOUND",
              r.status_code == 404 and r.json()["code"] == "E_NOT_FOUND")

    # ---------- 契约5：GET/POST /api/knowledge/docs ----------
    r = client.get("/api/knowledge/docs?size=50", headers=H)
    b = r.json()
    check("R18 文档列表分页包络 + 种子在列",
          r.status_code == 200 and b["code"] == 0
          and all(k in b["data"] for k in ("items", "total", "page", "size"))
          and any(str(it["doc_id"]) == str(DOC_ID) for it in b["data"]["items"]),
          f"total={b['data']['total']}")

    r = client.post("/api/knowledge/docs", headers=H,
                    json={"title": "越权上传", "doc_type": "manual", "source": "x"})
    check("R19 工程师上传 → 403 E_PERMISSION",
          r.status_code == 403 and r.json()["code"] == "E_PERMISSION")

    tok_kb = _token("kb_dev")
    HK = {"Authorization": f"Bearer {tok_kb}"}
    r = client.post("/api/knowledge/docs", headers=HK,
                    json={"title": "D0-2 临时上传测试", "doc_type": "procedure",
                          "source": "test-seed", "content": "测试正文"})
    b = r.json()
    check("R20 kb_admin 上传占位 → pending 登记",
          r.status_code == 200 and b["code"] == 0 and b["data"]["status"] == "pending",
          str(b["data"])[:100])
    tmp_doc_id = b["data"]["doc_id"]

    with psycopg.connect(POSTGRES_URL) as conn:
        ver = conn.execute(
            "SELECT action, actor FROM knowledge_versions WHERE doc_id = %s",
            (tmp_doc_id,)).fetchone()
    check("R21 knowledge_versions 审计落库（create/kb_dev）",
          ver is not None and ver[0] == "create" and ver[1] == "kb_dev",
          str(ver))

    r = client.post("/api/knowledge/docs", headers=HK,
                    json={"title": "坏类型", "doc_type": "blog", "source": "x"})
    check("R22 非法 doc_type → 422 E_INVALID_ARG",
          r.status_code == 422 and r.json()["code"] == "E_INVALID_ARG")

    # ---------- 清理临时数据 ----------
    with psycopg.connect(POSTGRES_URL) as conn:
        conn.execute("DELETE FROM knowledge_versions WHERE doc_id = %s", (tmp_doc_id,))
        conn.execute("DELETE FROM documents WHERE doc_id = %s AND title = 'D0-2 临时上传测试'",
                     (tmp_doc_id,))
        conn.commit()
    cleanup()

    failed = [n for ok_, n, _ in _results if not ok_]
    print(f"\n==== D0-2 自测：{len(_results) - len(failed)}/{len(_results)} PASS ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
