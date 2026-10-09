"""Socket.IO 服务与事件桥接（D0-4）。

冻结事件契约（UI 方案 §4.6，2026-10 确认）：
  服务端 → 客户端：
    alarm:new           告警看板实时插入（PG 轮询桥接，告警引擎为外部进程）
    diagnosis:progress  节点级进度（runner 事件桥接）
    diagnosis:done      诊断终态（done/error）
    review:required     高风险审核提醒（含审核 payload）
  客户端 → 服务端：
    chat:ask            对话式追问（ack 回调返回 {answer, citations}）
    review:submit       审核提交（D0-5 接入真实审核服务后注册）

鉴权：connect 时 auth={"token": <JWT>}，无效即拒连（后端安全边界）。
挂载：main.py 导出 socket_app = ASGIApp(sio, other_asgi_app=fastapi_app)；
      uvicorn 启动入口为 app.api.main:socket_app。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from typing import Any

import jwt as pyjwt
import socketio

from app.api.db import fetch_user_by_id, get_conn
from app.api.errors import ApiError
from app.api.runner import ask_question, subscribe, submit_review
from app.api.security import decode_token

# dev 默认放开跨域（本地 Next dev :3000 / Nginx 同源 9763），生产必须 SOCKETIO_ORIGINS 白名单
_origins = os.environ.get("SOCKETIO_ORIGINS", "*")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=_origins)

# sid → 已认证用户（连接即鉴权，断开即清除）
_sessions: dict[str, dict[str, Any]] = {}

# 主事件循环引用（runner 后台线程 → 主循环线程安全派发）
_loop: asyncio.AbstractEventLoop | None = None


# ---------------------------------------------------------------- 连接鉴权

@sio.on("connect")
async def _connect(sid: str, environ: dict, auth: dict | None = None):
    global _loop
    _loop = asyncio.get_running_loop()

    token = (auth or {}).get("token", "")
    try:
        payload = decode_token(token)
        user = fetch_user_by_id(payload["sub"])
        if user is None or not user["is_active"]:
            raise pyjwt.InvalidTokenError("用户不存在或已停用")
    except (pyjwt.InvalidTokenError, KeyError) as exc:
        raise socketio.exceptions.ConnectionRefusedError("未登录或会话已失效") from exc

    _sessions[sid] = {"user_id": user["user_id"], "username": user["username"],
                      "role": user["role"]}


@sio.on("disconnect")
async def _disconnect(sid: str):
    _sessions.pop(sid, None)


# ---------------------------------------------------------------- chat:ask（客户端 → 服务端）

@sio.on("chat:ask")
async def _chat_ask(sid: str, data: dict):
    """对话式追问；ack 回调返回统一包络 {code, message, data}。"""
    sess = _sessions.get(sid)
    if sess is None:
        return {"code": "E_UNAUTHORIZED", "message": "未登录或会话已失效"}
    thread_id = (data or {}).get("thread_id", "")
    question = str((data or {}).get("question", "")).strip()
    if not thread_id or not question:
        return {"code": "E_INVALID_ARG", "message": "thread_id 与 question 必填"}
    if len(question) > 2000:
        return {"code": "E_INVALID_ARG", "message": "question 超长（≤2000）"}

    def _ask() -> dict:
        return ask_question(thread_id, question, user=sess["username"])

    try:
        answer = await asyncio.to_thread(_ask)
        return {"code": 0, "message": "ok", "data": answer}
    except ApiError as exc:
        return {"code": exc.code, "message": exc.message}
    except Exception as exc:                                 # noqa: BLE001
        return {"code": "E_INTERNAL", "message": f"追问处理失败：{exc}"}


# ---------------------------------------------------------------- runner 事件桥接（服务端 → 客户端）

async def _emit_runner_event(event: dict) -> None:
    etype = event.get("type", "")
    if etype == "diagnosis:progress":
        await sio.emit("diagnosis:progress", {
            "thread_id": event["thread_id"], "node": event["node"],
            "nodes_done": event["nodes_done"], "ts": event["ts"]})
    elif etype == "diagnosis:done":
        payload = {"thread_id": event["thread_id"], "status": event.get("status"),
                   "report_id": event.get("report_id"),
                   "degrade_reason": event.get("degrade_reason"), "ts": event["ts"]}
        if event.get("error"):
            payload["error"] = event["error"]
        await sio.emit("diagnosis:done", payload)
    elif etype == "review:required":
        await sio.emit("review:required", {
            "thread_id": event["thread_id"], "payload": event.get("payload"),
            "ts": event["ts"]})
    elif etype == "diagnosis:error":
        await sio.emit("diagnosis:done", {
            "thread_id": event["thread_id"], "status": "error",
            "error": event.get("error"), "ts": event["ts"]})


def _bridge(event: dict) -> None:
    """runner 后台线程 → 主事件循环（线程安全派发）。"""
    if _loop is None or _loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(_emit_runner_event(event), _loop)


subscribe(_bridge)   # 挂入 runner 事件总线


# ---------------------------------------------------------------- alarm:new 轮询桥接

_ALARM_POLL_SEC = 2.0
_last_ts: dt.datetime | None = None


def _fetch_new_alarms() -> list[dict]:
    """取 _last_ts 之后的新告警（游标推进；进程启动时初始化为当前时间，不回放历史）。

    返回 JSON 安全字段（ts=epoch ms，value=float）——socketio 默认 JSON 序列化器
    不支持 datetime/Decimal，混入会被 emit 静默丢弃。
    """
    global _last_ts
    with get_conn() as conn:
        if _last_ts is None:
            row = conn.execute("SELECT max(ts) AS m FROM alerts").fetchone()
            _last_ts = row["m"] if row and row["m"] else dt.datetime.now(dt.timezone.utc)
            return []
        rows = conn.execute(
            """SELECT alarm_id, device_id, metric, value, severity, status, ts
               FROM alerts WHERE ts > %s ORDER BY ts ASC LIMIT 100""",
            (_last_ts,)).fetchall()
    items = []
    for r in rows:
        items.append({
            "alarm_id": r["alarm_id"], "device_id": r["device_id"],
            "metric": r["metric"],
            "value": float(r["value"]) if r["value"] is not None else None,
            "severity": r["severity"], "status": r["status"],
            "ts": int(r["ts"].timestamp() * 1000) if r["ts"] else None,
        })
    if rows:
        _last_ts = rows[-1]["ts"]
    return items


async def _alarm_poller() -> None:
    """后台轮询 alerts 表 → alarm:new 广播。"""
    while True:
        try:
            new_items = await asyncio.to_thread(_fetch_new_alarms)
            for row in new_items:
                await sio.emit("alarm:new", row)
        except Exception:                                    # noqa: BLE001 - 轮询失败静默重试
            pass
        await asyncio.sleep(_ALARM_POLL_SEC)


def start_background_tasks() -> None:
    """FastAPI lifespan 启动时调用（main.py）。"""
    sio.start_background_task(_alarm_poller)


# ---------------------------------------------------------------- review:submit（客户端 → 服务端）

@sio.on("review:submit")
async def _review_submit(sid: str, data: dict):
    """审核提交 socket 通道（D0-5）：与 REST /api/threads/{id}/review 同一服务。"""
    sess = _sessions.get(sid)
    if sess is None:
        return {"code": "E_UNAUTHORIZED", "message": "未登录或会话已失效"}
    if sess["role"] != "reviewer":
        return {"code": "E_PERMISSION", "message": "你的角色无此权限，请联系管理员"}
    d = data or {}
    thread_id = str(d.get("thread_id", ""))
    action = str(d.get("action", ""))
    comment = str(d.get("comment", ""))[:2000]
    if not thread_id or action not in ("approved", "rejected"):
        return {"code": "E_INVALID_ARG",
                "message": "thread_id 必填，action 仅支持 approved/rejected"}

    def _submit() -> dict:
        return submit_review(thread_id, action, comment, reviewer=sess["username"])

    try:
        result = await asyncio.to_thread(_submit)
        return {"code": 0, "message": "ok", "data": result}
    except ApiError as exc:
        return {"code": exc.code, "message": exc.message}
    except Exception as exc:                                 # noqa: BLE001
        return {"code": "E_INTERNAL", "message": f"审核提交失败：{exc}"}
