"""审核 REST（D0-5 · 契约8）。

POST /api/threads/{thread_id}/review   主通道：对等待审核的诊断提交决策（approved/rejected）
POST /api/reports/{report_id}/review   契约补丁别名：由报告反查线程后走同一服务
GET  /api/review/pending               审核队列（注册表内 waiting_review 线程）

流程（runner.submit_review）：等待态校验 → SoD（发起人不得自审）→ ReviewLock 并发锁
→ Command(resume) 恢复执行 → 图外幂等写入 → 释放锁。
4h 通知/24h 超时降级由 runner.start_lifecycle_watcher 后台任务承载。

RBAC：审核 = 仅 reviewer；队列 = reviewer/sys_admin。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import require_roles
from app.api.db import get_conn
from app.api.errors import ApiError, ok
from app.api.runner import get_record, submit_review
from app.report.idempotency import get_report as _fetch_report

router = APIRouter(tags=["review"])

_REVIEW_ACTIONS = {"approved", "rejected"}   # timeout 仅系统触发（24h watcher）


class ReviewRequest(BaseModel):
    """审核决策：意见必填（UI §6.3 驳回必填意见，通过亦建议留痕）。"""

    action: str = Field(description="approved | rejected")
    comment: str = Field(default="", max_length=2000)


@router.post("/api/threads/{thread_id}/review")
async def review_thread(
    thread_id: str,
    body: ReviewRequest,
    user: dict[str, Any] = Depends(require_roles("reviewer")),
) -> dict:
    if body.action not in _REVIEW_ACTIONS:
        raise ApiError("E_INVALID_ARG", f"action 仅支持 {'/'.join(sorted(_REVIEW_ACTIONS))}")
    result = submit_review(thread_id, body.action, body.comment.strip(),
                           reviewer=user["username"])
    return ok(result)


@router.post("/api/reports/{report_id}/review")
async def review_by_report(
    report_id: str,
    body: ReviewRequest,
    user: dict[str, Any] = Depends(require_roles("reviewer")),
) -> dict:
    """契约补丁别名：POST /api/reports/{id}/review（UI 方案 §附录A 冻结口径）。

    报告行在审核完成后才由 finalize 幂等写入；等待审核中的线程以
    /api/threads/{thread_id}/review 为主通道。本别名对已存在报告反查线程，
    若其仍处等待态（如重复幂等键线程）则复用同一服务，否则 409。
    """
    if body.action not in _REVIEW_ACTIONS:
        raise ApiError("E_INVALID_ARG", f"action 仅支持 {'/'.join(sorted(_REVIEW_ACTIONS))}")
    rep = _fetch_report(report_id)
    if rep is None:
        raise ApiError("E_NOT_FOUND", f"报告 {report_id} 不存在")
    thread_id = rep.get("thread_id") or ""
    rec = get_record(thread_id)
    if rec is None or rec.status != "waiting_review":
        raise ApiError("E_CONFLICT", "该报告对应的诊断不在等待审核状态")
    result = submit_review(thread_id, body.action, body.comment.strip(),
                           reviewer=user["username"])
    return ok(result)


@router.get("/api/review/pending")
async def pending_reviews(
    _: dict[str, Any] = Depends(require_roles("reviewer", "sys_admin")),
) -> dict:
    """审核队列：进程注册表内 waiting_review 线程（重启后以 review:required 事件回放为准）。"""
    items = []
    for rec in _iter_waiting():
        items.append({
            "thread_id": rec.thread_id,
            "submitter": rec.submitter,
            "alarm": rec.alarm.model_dump() if rec.alarm else None,
            "review_payload": rec.review_payload,
            "waiting_since": rec.finished_at,
            "notified_4h": rec.notified_4h,
        })
    return ok({"items": items, "total": len(items)})


def _iter_waiting():
    from app.api import runner as _runner   # noqa: PLC0415 - 避免环导入
    return [r for r in _runner._registry.values() if r.status == "waiting_review"]
