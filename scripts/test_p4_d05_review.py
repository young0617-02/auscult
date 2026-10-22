"""D0-5 自测：审核 REST（锁 + SoD + 4h/24h 生命周期）+ P3 遗留接入验证。

运行（前置）：
    PG 5433 已启动（checkpointer + reports 表）；Neo4j 可选；
    Milvus/TDengine/Redis 可缺（图内降级 + ReviewLock 降级放行）。
    .venv\\Scripts\\python.exe scripts\\test_p4_d05_review.py

确定性挂起方案：
    - patch app.graph.build._route_condition 恒返 "human_review"；
    - patch app.graph.nodes.diagnose._call_ollama 返回含「停机」关键词的
      合法诊断 JSON（risk_rules.yml 关键词命中 → needs_review 必真）。
    resume 后仅 human_review→finalize 两节点，无需再调 LLM。

通过标准：全部 CHECK 输出 PASS（任一 FAIL 退出码 1）。
"""

from __future__ import annotations

import json
import sys
import time
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import runner as runner_mod  # noqa: E402
from app.api.main import create_app  # noqa: E402
from app.graph import build as build_mod  # noqa: E402
from app.graph.nodes import diagnose as diagnose_node_mod  # noqa: E402
from scripts.seed_users import DEFAULT_PASSWORD, seed  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
from app.observability import paths as _paths  # noqa: E402
from app.api.config import POSTGRES_URL  # noqa: E402

TRACE_DIR = _paths.TRACE_DIR
AUDIT_LOG = _paths.reports_file("review_audit.jsonl")
# 2026-10-22：不再写死 DSN —— 否则集成测试隔离（API_PG_URL）对这个脚本失效
PG_DSN = POSTGRES_URL

client = TestClient(create_app())
_results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((bool(cond), name, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def _token(username: str) -> str:
    r = client.post("/api/auth/login",
                    json={"username": username, "password": DEFAULT_PASSWORD})
    assert r.json()["code"] == 0, f"{username} 登录失败：{r.text[:120]}"
    return r.json()["data"]["access_token"]


def _fake_ollama(messages, timeout=30.0) -> str:      # noqa: ANN001, ARG001
    """确定性诊断输出：含「停机」关键词 + 合法 JSON 契约。"""
    return json.dumps({
        "diagnosis": "主轴承磨损导致振动超标，建议立即停机检查",
        "root_causes": [{"cause": "轴承磨损", "citations": [], "confidence_hint": 0.8}],
        "suggestions": [{"action": "停机检查并更换轴承", "citations": [], "risk": "high"}],
        "self_confidence": 0.9,
    }, ensure_ascii=False)


def _start_and_wait(headers: dict, submitter_token_headers: dict | None = None,
                    timeout_s: float = 180.0) -> tuple[str, dict]:
    """发起诊断并轮询至 waiting_review。返回 (thread_id, 最终 status dict)。"""
    r = client.post("/api/diagnose", headers=headers,
                    json={"alarm": {"device_id": "PUMP-A", "metric": "vib_rms",
                                    "value": 12.5, "severity": "high",
                                    "ts": int(time.time() * 1000)}})
    assert r.json()["code"] == 0, f"发起失败：{r.text[:200]}"
    tid = r.json()["data"]["thread_id"]
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        last = client.get(f"/api/threads/{tid}", headers=headers).json()["data"]
        if last.get("status") in ("waiting_review", "done", "error"):
            break
        time.sleep(1.0)
    assert last.get("status") == "waiting_review", \
        f"线程 {tid} 未达 waiting_review：{json.dumps(last, ensure_ascii=False)[:300]}"
    return tid, last


def _pg_one(sql: str, params: tuple):
    import psycopg                                       # noqa: PLC0415
    with psycopg.connect(PG_DSN) as conn:
        row = conn.execute(sql, params).fetchone()
    return row


def main() -> int:
    seed(DEFAULT_PASSWORD, reset=False)

    # ---------- 确定性挂起补丁（覆盖全部后台线程执行期） ----------
    p1 = unittest.mock.patch.object(build_mod, "_route_condition",
                                    lambda state: "human_review")
    p2 = unittest.mock.patch.object(diagnose_node_mod, "_call_ollama", _fake_ollama)
    p1.start()
    p2.start()

    try:
        tok_eng = _token("eng_dev")
        tok_rev = _token("rev_dev")
        HE = {"Authorization": f"Bearer {tok_eng}"}
        HR = {"Authorization": f"Bearer {tok_rev}"}

        # ---------- 边界 ----------
        r = client.post("/api/threads/thr-nonexistent00000000/review",
                        json={"action": "approved", "comment": "x"})
        check("R01 未登录审核 → 401", r.status_code == 401
              and r.json()["code"] == "E_UNAUTHORIZED")

        r = client.post("/api/threads/thr-nonexistent00000000/review", headers=HR,
                        json={"action": "approved", "comment": "x"})
        check("R02 线程不存在 → 404 E_NOT_FOUND", r.status_code == 404
              and r.json()["code"] == "E_NOT_FOUND")

        r = client.post("/api/threads/thr-x/review", headers=HE,
                        json={"action": "approved", "comment": "x"})
        check("R03 engineer 角色 → 403 E_PERMISSION（仅 reviewer）",
              r.status_code == 403 and r.json()["code"] == "E_PERMISSION")

        # ---------- 线程 A：挂起 → SoD → 通过 ----------
        tid_a, st_a = _start_and_wait(HE)
        check("R04 确定性挂起至 waiting_review + payload 就绪",
              st_a["status"] == "waiting_review"
              and isinstance(st_a.get("review_payload"), dict)
              and st_a["review_payload"].get("risk_eval", {}).get("needs_review") is True,
              f"nodes={st_a.get('nodes_done')}")

        r = client.post(f"/api/threads/{tid_a}/review", headers=HE,
                        json={"action": "approved", "comment": "自审尝试"})
        check("R05 职责分离：发起人 eng_dev 自审 → 403 E_PERMISSION",
              r.status_code == 403 and r.json()["code"] == "E_PERMISSION")

        r = client.post(f"/api/threads/{tid_a}/review", headers=HR,
                        json={"action": "maybe", "comment": ""})
        check("R06 非法 action → 422 E_INVALID_ARG", r.status_code == 422
              and r.json()["code"] == "E_INVALID_ARG")

        r = client.get("/api/review/pending", headers=HE)
        check("R07 审核队列 engineer → 403", r.status_code == 403)
        r = client.get("/api/review/pending", headers=HR)
        pend = r.json()["data"]
        item = next((i for i in pend["items"] if i["thread_id"] == tid_a), None)
        check("R08 审核队列含线程 A（submitter/payload/notified_4h=False）",
              r.status_code == 200 and pend["total"] >= 1 and item is not None
              and item["submitter"] == "eng_dev"
              and item["notified_4h"] is False,
              f"total={pend['total']}")

        r = client.post(f"/api/threads/{tid_a}/review", headers=HR,
                        json={"action": "approved", "comment": "证据充分，同意结论"})
        b = r.json()
        check("R09 rev_dev 通过 → done + report_id(RPT-*)",
              r.status_code == 200 and b["code"] == 0
              and b["data"]["status"] == "done"
              and str(b["data"].get("report_id", "")).startswith("RPT-"),
              f"report_id={b['data'].get('report_id')}")
        report_a = b["data"]["report_id"]

        row = _pg_one("SELECT review_status, thread_id FROM reports WHERE report_id=%s",
                      (report_a,))
        check("R10 PG reports.review_status=approved 且 thread_id 回填",
              row is not None and row[0] == "approved" and row[1] == tid_a,
              f"row={row}")

        r = client.post(f"/api/threads/{tid_a}/review", headers=HR,
                        json={"action": "approved", "comment": "重复审核"})
        check("R11 终态后重复审核 → 409 E_CONFLICT", r.status_code == 409
              and r.json()["code"] == "E_CONFLICT")

        # ---------- 契约补丁别名：POST /api/reports/{report_id}/review ----------
        r = client.post("/api/reports/RPT-DOES-NOT-EXIST/review", headers=HR,
                        json={"action": "approved", "comment": ""})
        check("R12 别名：报告不存在 → 404", r.status_code == 404
              and r.json()["code"] == "E_NOT_FOUND")
        r = client.post(f"/api/reports/{report_a}/review", headers=HR,
                        json={"action": "approved", "comment": ""})
        check("R13 别名：已完成线程 → 409 E_CONFLICT（非等待态）",
              r.status_code == 409 and r.json()["code"] == "E_CONFLICT")

        # ---------- 线程 B：驳回路径 ----------
        tid_b, _ = _start_and_wait(HE)
        r = client.post(f"/api/threads/{tid_b}/review", headers=HR,
                        json={"action": "rejected", "comment": "证据不足，需补检测"})
        b = r.json()
        check("R14 rev_dev 驳回 → done + degrade_reason=review_rejected",
              r.status_code == 200 and b["code"] == 0
              and b["data"]["status"] == "done"
              and b["data"].get("degrade_reason") == "review_rejected"
              and b["data"].get("human_review", {}).get("status") == "rejected",
              f"degrade={b['data'].get('degrade_reason')}")
        report_b = b["data"].get("report_id")
        row = _pg_one("SELECT review_status FROM reports WHERE report_id=%s",
                      (report_b,))
        check("R15 PG reports.review_status=rejected", row is not None
              and row[0] == "rejected", f"row={row}")

        # ---------- P3 遗留接入：trace 文件 + 指标 ----------
        check("R16 trace JSONL 落盘（thread_id 命名）",
              (TRACE_DIR / f"{tid_a}.jsonl").exists(),
              str(TRACE_DIR / f"{tid_a}.jsonl"))
        counts = runner_mod.METRICS.review_status_counts()
        check("R17 MetricsCollector 审核计数（approved/rejected）",
              counts.get("approved", 0) >= 1 and counts.get("rejected", 0) >= 1,
              f"counts={counts}")

        # ---------- 生命周期：4h 通知（线程 C） ----------
        tid_c, _ = _start_and_wait(HE)
        rec_c = runner_mod.get_record(tid_c)
        rec_c.finished_at -= (4 * 3600 + 60)   # 回拨至 4h+60s 前
        runner_mod._lifecycle_tick()
        audit_text = AUDIT_LOG.read_text(encoding="utf-8") if AUDIT_LOG.exists() else ""
        check("R18 4h 通知：notified_4h=True + 审计留痕",
              rec_c.notified_4h is True
              and "notify_backup_reviewer" in audit_text
              and tid_c in audit_text)
        # C 仍处等待（4h 仅通知不降级）
        check("R19 4h 通知后线程仍 waiting_review", rec_c.status == "waiting_review")

        # ---------- 生命周期：24h 超时降级（线程 D） ----------
        tid_d, _ = _start_and_wait(HE)
        rec_d = runner_mod.get_record(tid_d)
        rec_d.finished_at -= (25 * 3600)       # 回拨至 25h 前
        runner_mod._lifecycle_tick()
        check("R20 24h 超时：系统 resume → done + review_timeout",
              rec_d.status == "done" and rec_d.degrade_reason == "review_timeout",
              f"status={rec_d.status} degrade={rec_d.degrade_reason}")
        row = _pg_one("SELECT review_status, degrade_reason FROM reports "
                      "WHERE thread_id=%s", (tid_d,))
        check("R21 PG 报告 review_status=timeout", row is not None
              and row[0] == "timeout" and row[1] == "review_timeout", f"row={row}")

        # ---------- Socket.IO review:submit 接线（源级冒烟，D0-4 已测传输层） ----------
        socket_src = (PROJECT_ROOT / "app" / "api" / "socket.py").read_text(encoding="utf-8")
        check("R22 socket review:submit 已接 submit_review 真实服务",
              "submit_review" in socket_src and "asyncio.to_thread" in socket_src)

    finally:
        p1.stop()
        p2.stop()

    failed = [n for ok_, n, _ in _results if not ok_]
    print(f"\n==== D0-5 自测：{len(_results) - len(failed)}/{len(_results)} PASS ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
