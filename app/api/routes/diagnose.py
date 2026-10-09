"""诊断发起与线程查询 REST（D0-3 · 契约6/7）。

POST /api/diagnose                  发起诊断（alarm_id 或 alarm 对象二选一），返回 thread_id
GET  /api/threads/{thread_id}       查询线程状态/进度/追问记录（含重启后 checkpointer 回退）
POST /api/threads/{thread_id}/ask   追问（chat:ask 的 REST twin，D0-4 socket 事件复用同一服务）

RBAC：发起/追问 = engineer/reviewer/sys_admin；查询 = 任意已登录角色。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_roles
from app.api.db import get_conn
from app.api.errors import ApiError, ok
from app.api.runner import ask_question, start_diagnosis, thread_status
from app.graph.state import AlarmEvent

router = APIRouter(tags=["diagnosis"])

_LAUNCH_ROLES = ("engineer", "reviewer", "sys_admin")


class DiagnoseRequest(BaseModel):
    """发起诊断请求：alarm_id（从 alerts 表取）与 alarm（内联对象）二选一。"""

    alarm_id: str | None = Field(default=None, max_length=64)
    alarm: dict | None = Field(default=None,
                               description="内联告警对象 {device_id, metric, value, ...}")


def _load_alarm_by_id(alarm_id: str) -> AlarmEvent:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT alarm_id, device_id, metric, value, severity, ts "
            "FROM alerts WHERE alarm_id = %s", (alarm_id,)).fetchone()
    if row is None:
        raise ApiError("E_NOT_FOUND", f"告警 {alarm_id} 不存在")
    ts = row["ts"]
    return AlarmEvent(
        alarm_id=row["alarm_id"], device_id=row["device_id"], metric=row["metric"],
        value=float(row["value"]) if row["value"] is not None else 0.0,
        severity=row["severity"],
        ts=int(ts.timestamp() * 1000) if ts else 0,
    )


@router.post("/api/diagnose")
async def create_diagnosis(
    body: DiagnoseRequest,
    user: dict[str, Any] = Depends(require_roles(*_LAUNCH_ROLES)),
) -> dict:
    if (body.alarm_id is None) == (body.alarm is None):
        raise ApiError("E_INVALID_ARG", "alarm_id 与 alarm 必须二选一")

    if body.alarm_id:
        alarm = _load_alarm_by_id(body.alarm_id)
    else:
        try:
            alarm = AlarmEvent(**body.alarm)      # type: ignore[arg-type]
        except Exception as exc:                  # noqa: BLE001 - Pydantic 校验失败
            raise ApiError("E_INVALID_ARG", f"告警对象字段校验失败：{exc}") from exc

    if not alarm.device_id or not alarm.metric:
        raise ApiError("E_INVALID_ARG", "alarm 缺少 device_id 或 metric")

    thread_id = start_diagnosis(alarm, submitter=user["username"])
    return ok({"thread_id": thread_id, "status": "running",
               "note": "诊断已后台启动，进度经 GET /api/threads/{id} 或 Socket.IO diagnosis:progress 获取"})


@router.get("/api/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    _: dict[str, Any] = Depends(get_current_user),
) -> dict:
    return ok(thread_status(thread_id))


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@router.post("/api/threads/{thread_id}/ask")
async def ask_thread(
    thread_id: str,
    body: AskRequest,
    user: dict[str, Any] = Depends(require_roles(*_LAUNCH_ROLES)),
) -> dict:
    answer = ask_question(thread_id, body.question.strip(), user=user["username"])
    return ok(answer)
