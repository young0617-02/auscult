"""D0-4 自测：Socket.IO 服务（鉴权连接 / chat:ask / alarm:new / runner 事件桥接）。

运行（前置）：
    PG 5433 已启动、users 已种子；Ollama 可达时追问走真实推理。
    .venv\\Scripts\\python.exe scripts\\test_p4_d04_socket.py

机制：子进程启动 uvicorn app.api.main:socket_app @ 8907，SimpleClient 真连。
通过标准：全部 CHECK 输出 PASS（任一 FAIL 退出码 1）。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402
import socketio as sio_lib  # noqa: E402
from socketio.exceptions import ConnectionRefusedError as SioRefused  # noqa: E402

from app.api.config import POSTGRES_URL  # noqa: E402
from scripts.seed_users import DEFAULT_PASSWORD  # noqa: E402

PORT = 8907
BASE = f"http://127.0.0.1:{PORT}"
ALARM_ID = "ALM-D04-EVT-001"

_results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _results.append((bool(cond), name, detail))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))


def _http(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"status": resp.status, **json.loads(resp.read().decode())}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, **json.loads(exc.read().decode())}


def _login(username: str) -> str:
    b = _http("POST", "/api/auth/login",
              body={"username": username, "password": DEFAULT_PASSWORD})
    assert b["code"] == 0, f"{username} 登录失败"
    return b["data"]["access_token"]


def _receive_until(client: sio_lib.SimpleClient, want: set[str],
                   timeout: float) -> dict[str, tuple]:
    """循环 receive 直到收齐 want 集合或超时；返回 {事件名: (event, data)}。"""
    got: dict[str, tuple] = {}
    deadline = time.time() + timeout
    while time.time() < deadline and not want.issubset(got):
        try:
            ev = client.receive(timeout=min(5, deadline - time.time()))
        except Exception:                                    # noqa: BLE001 - 空超时继续
            continue
        if ev and ev[0] in want and ev[0] not in got:
            got[ev[0]] = tuple(ev)
    return got


def main() -> int:
    # ---------- 启动子进程服务 ----------
    root = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": root}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api.main:socket_app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ready = False
        for _ in range(60):
            try:
                with urllib.request.urlopen(BASE + "/api", timeout=2) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:                                # noqa: BLE001
                time.sleep(0.5)
        check("R00 服务子进程就绪", ready)
        if not ready:
            return 1

        tok = _login("eng_dev")

        # ---------- 连接鉴权 ----------
        c_bad = sio_lib.SimpleClient()
        try:
            c_bad.connect(BASE, socketio_path="socket.io", transports=["polling"])
            check("R01 无 token 连接被拒", False, "未拒绝")
        except (SioRefused, Exception) as exc:                # noqa: BLE001 - 拒连形态两种皆可
            check("R01 无 token 连接被拒",
                  isinstance(exc, SioRefused) or "failed to connect" in str(exc),
                  f"异常形态: {exc}")

        c_garbage = sio_lib.SimpleClient()
        try:
            c_garbage.connect(BASE, auth={"token": "garbage.token.here"},
                              socketio_path="socket.io", transports=["polling"])
            check("R02 伪造 token 连接被拒", False, "未拒绝")
        except (SioRefused, Exception) as exc:                # noqa: BLE001
            check("R02 伪造 token 连接被拒",
                  isinstance(exc, SioRefused) or "failed to connect" in str(exc),
                  f"异常形态: {exc}")

        c = sio_lib.SimpleClient()
        c.connect(BASE, auth={"token": tok}, socketio_path="socket.io", transports=["polling"])
        check("R03 有效 token 连接成功", c.connected)

        # ---------- chat:ask ----------
        r = c.call("chat:ask", {"thread_id": "thr-nonexistent0000", "question": "测试？"},
                   timeout=15)
        check("R04 chat:ask 线程不存在 → ack E_NOT_FOUND",
              r.get("code") == "E_NOT_FOUND", str(r)[:80])
        r = c.call("chat:ask", {"thread_id": "x"}, timeout=15)
        check("R05 chat:ask 缺 question → ack E_INVALID_ARG",
              r.get("code") == "E_INVALID_ARG")

        # ---------- alarm:new 轮询桥接 ----------
        with psycopg.connect(POSTGRES_URL) as conn:
            conn.execute("DELETE FROM alerts WHERE alarm_id = %s", (ALARM_ID,))
            conn.execute(
                """INSERT INTO alerts (alarm_id, device_id, metric, value, severity, status, ts)
                   VALUES (%s, 'PUMP-B', 'temp_bearing', 88.5, 'critical', 'open', %s)""",
                (ALARM_ID, dt.datetime.now(dt.timezone.utc)))
            conn.commit()
        got = _receive_until(c, {"alarm:new"}, timeout=15)
        ok_new = "alarm:new" in got and got["alarm:new"][1].get("alarm_id") == ALARM_ID
        check("R06 插入告警 → 收到 alarm:new 广播", ok_new,
              str(got.get("alarm:new", ("<超时>",)))[:100])
        with psycopg.connect(POSTGRES_URL) as conn:
            conn.execute("DELETE FROM alerts WHERE alarm_id = %s", (ALARM_ID,))
            conn.commit()

        # ---------- 诊断事件桥接（progress/done） ----------
        r = _http("POST", "/api/diagnose", token=tok,
                  body={"alarm": {"device_id": "PUMP-A", "metric": "vib_rms",
                                  "value": 11.8, "severity": "medium",
                                  "ts": int(time.time() * 1000)}})
        check("R07 REST 发起诊断成功", r.get("code") == 0, str(r)[:100])
        got = _receive_until(c, {"diagnosis:progress", "diagnosis:done"}, timeout=180)
        check("R08 收到 diagnosis:progress（节点级进度桥接）",
              "diagnosis:progress" in got,
              f"node={got.get('diagnosis:progress', (None, {}))[1].get('node')}")
        done = got.get("diagnosis:done", (None, {}))[1]
        check("R09 收到 diagnosis:done（含 report_id）",
              "diagnosis:done" in got and done.get("report_id", "").startswith("RPT-"),
              f"status={done.get('status')} report_id={done.get('report_id')} "
              f"degrade={done.get('degrade_reason')}")

        # ---------- 追问真实链路（若线程已完成） ----------
        if done.get("status") == "done" and done.get("report_id"):
            # 借助 REST 查 thread_id（done 事件里带的是 thread_id）
            tid = done.get("thread_id")
            r = c.call("chat:ask", {"thread_id": tid, "question": "总结一下当前风险点"},
                       timeout=60)
            check("R10 chat:ask 真实线程 ack code=0 且含 answer",
                  r.get("code") == 0 and isinstance((r.get("data") or {}).get("answer"), str),
                  str(r)[:100])
        else:
            check("R10 chat:ask 真实线程（线程未完成，跳过）", True, f"done={done}")

        # ---------- review:submit 占位（D0-5 替换） ----------
        r = c.call("review:submit", {"thread_id": "x"}, timeout=10)
        check("R11 review:submit 占位通道返回 E_CONFLICT", r.get("code") == "E_CONFLICT")

        c.disconnect()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    failed = [n for ok_, n, _ in _results if not ok_]
    print(f"\n==== D0-4 自测：{len(_results) - len(failed)}/{len(_results)} PASS ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
