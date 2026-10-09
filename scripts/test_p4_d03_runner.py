"""D0-3 自测：诊断执行服务（POST /api/diagnose + GET /api/threads/{id} + ask）。

运行（前置）：
    PG 5433 已启动；Neo4j/Milvus/TDengine/Redis 可缺（图内降级路径兜底）；
    Ollama 11434 可达时追问走真实推理，不可达时验证 E_UPSTREAM 降级。
    .venv\\Scripts\\python.exe scripts\\test_p4_d03_runner.py

通过标准：全部 CHECK 输出 PASS（任一 FAIL 退出码 1）。
"""

from __future__ import annotations

import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import create_app  # noqa: E402
from app.api import runner as runner_mod  # noqa: E402
from scripts.seed_users import DEFAULT_PASSWORD, seed  # noqa: E402

client = TestClient(create_app())
_results: list[tuple[bool, str, str]] = []
_collected: list[dict] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((bool(cond), name, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def _token(username: str) -> str:
    r = client.post("/api/auth/login", json={"username": username, "password": DEFAULT_PASSWORD})
    assert r.json()["code"] == 0, f"{username} 登录失败：{r.text[:120]}"
    return r.json()["data"]["access_token"]


def _ollama_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3):
            return True
    except Exception:                                        # noqa: BLE001
        return False


def main() -> int:
    seed(DEFAULT_PASSWORD, reset=False)
    tok_eng = _token("eng_dev")
    tok_kb = _token("kb_dev")
    HE = {"Authorization": f"Bearer {tok_eng}"}
    HK = {"Authorization": f"Bearer {tok_kb}"}

    # ---------- 边界 ----------
    r = client.post("/api/diagnose", json={"alarm": {"device_id": "PUMP-A", "metric": "vib_rms"}})
    check("R01 无 token 发起 → 401", r.status_code == 401 and r.json()["code"] == "E_UNAUTHORIZED")

    r = client.post("/api/diagnose", headers=HK,
                    json={"alarm": {"device_id": "PUMP-A", "metric": "vib_rms"}})
    check("R02 kb_admin 发起 → 403 E_PERMISSION", r.status_code == 403)

    r = client.post("/api/diagnose", headers=HE, json={})
    check("R03a alarm_id/alarm 均缺 → 422", r.status_code == 422
          and r.json()["code"] == "E_INVALID_ARG")
    r = client.post("/api/diagnose", headers=HE,
                    json={"alarm_id": "ALM-D02-SEED-001",
                          "alarm": {"device_id": "PUMP-A", "metric": "vib_rms"}})
    check("R03b 二者同给 → 422", r.status_code == 422)

    r = client.post("/api/diagnose", headers=HE, json={"alarm_id": "ALM-NOT-EXIST"})
    check("R04 alarm_id 不存在 → 404", r.status_code == 404
          and r.json()["code"] == "E_NOT_FOUND")

    r = client.post("/api/diagnose", headers=HE,
                    json={"alarm": {"metric": "vib_rms", "value": 9.6}})
    check("R05 内联告警缺 device_id → 422", r.status_code == 422)

    # ---------- 事件总线订阅（D0-4 桥接点验证） ----------
    runner_mod.subscribe(lambda ev: _collected.append(ev))

    # ---------- 真实执行（端到端；下游不可用走降级路径） ----------
    r = client.post("/api/diagnose", headers=HE,
                    json={"alarm": {"device_id": "PUMP-A", "metric": "vib_rms",
                                    "value": 12.5, "severity": "medium",
                                    "ts": int(time.time() * 1000)}})
    b = r.json()
    check("R06 发起成功返回 thread_id",
          r.status_code == 200 and b["code"] == 0
          and b["data"]["thread_id"].startswith("thr-"), b["data"]["thread_id"])
    tid = b["data"]["thread_id"]

    deadline = time.time() + 180
    status = None
    last = None
    while time.time() < deadline:
        r = client.get(f"/api/threads/{tid}", headers=HE)
        last = r.json()["data"]
        status = last["status"]
        if status in ("done", "error", "waiting_review"):
            break
        time.sleep(2)
    check("R07 线程推进至终态（done/waiting_review/error）",
          status in ("done", "waiting_review", "error"),
          f"status={status} nodes={last.get('nodes_done')} err={last.get('error')}")

    check("R08 节点序列完整（parse_alarm→analyze_sensor→retrieve_evidence→get_history→diagnose）",
          all(n in last.get("nodes_done", []) for n in
              ("parse_alarm", "analyze_sensor", "retrieve_evidence", "get_history", "diagnose")),
          str(last.get("nodes_done")))

    check("R09 事件总线收到 progress + 终态事件",
          any(e["type"] == "diagnosis:progress" and e["thread_id"] == tid for e in _collected)
          and any(e["type"] in ("diagnosis:done", "review:required")
                  and e["thread_id"] == tid for e in _collected),
          f"events={len(_collected)}")

    if status == "done":
        check("R10 报告已幂等写入并可查（D0-2 集成）",
              last.get("report_id")
              and client.get(f"/api/reports/{last['report_id']}", headers=HE).json()["code"] == 0,
              f"report_id={last.get('report_id')} degrade={last.get('degrade_reason')}")
    else:
        check("R10 报告写入（线程未完成，跳过断言）", True, f"status={status}")

    # ---------- chat:ask 追问 ----------
    if status in ("done", "waiting_review"):
        r = client.post(f"/api/threads/{tid}/ask", headers=HE,
                        json={"question": "轴承磨损通常还伴随哪些迹象？"})
        if _ollama_up():
            ab = r.json()
            check("R11 追问返回 {answer, citations}（本地推理）",
                  r.status_code == 200 and ab["code"] == 0
                  and isinstance(ab["data"].get("answer"), str)
                  and isinstance(ab["data"].get("citations"), list),
                  f"answer={ab['data'].get('answer', '')[:60]}… cites={len(ab['data'].get('citations', []))}")
        else:
            check("R11 追问（Ollama 不可达 → E_UPSTREAM 降级）",
                  r.status_code == 502 and r.json()["code"] == "E_UPSTREAM", r.text[:80])
        r = client.get(f"/api/threads/{tid}", headers=HE)
        check("R12 追问留痕入 qa_log",
              len(r.json()["data"].get("qa_log", [])) >= 1)
    else:
        check("R11 追问（线程未完成，跳过）", True)
        check("R12 qa_log（跳过）", True)

    # ---------- 重启回退：清空注册表后从 checkpointer 推断 ----------
    runner_mod._registry.clear()
    r = client.get(f"/api/threads/{tid}", headers=HE)
    b = r.json()
    check("R13 注册表清空后 checkpointer 回退可查",
          r.status_code == 200 and b["code"] == 0 and b["data"]["status"] == "done"
          and b["data"].get("report_id") == (last or {}).get("report_id"),
          f"status={b['data'].get('status')} report_id={b['data'].get('report_id')}")

    r = client.get("/api/threads/thr-nonexistent0000", headers=HE)
    check("R14 线程不存在 → 404", r.status_code == 404)

    failed = [n for ok_, n, _ in _results if not ok_]
    print(f"\n==== D0-3 自测：{len(_results) - len(failed)}/{len(_results)} PASS ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
