"""知识库文档 REST（D0-2 · 契约5）。

GET  /api/knowledge/docs?page=&size=&status=&doc_type=   列表
POST /api/knowledge/docs                                 上传占位（元数据登记，status=pending）

上传占位口径（Phase 4 计划 §4.6，2026-10 方案确认）：
- 本步只做「元数据登记 + knowledge_versions 审计（action=create, actor=当前用户）」，
  status 置 pending；
- 解析/分块/向量化流水线（Phase 1 B2/B3 脚本）由流水线任务推进 status；
- 准入审核 POST /api/knowledge/docs/{doc_id}/admission（D0-6 契约补丁）：
  仅 kb_admin，approve/reject 一次性决策，写 documents.admission_* 三列 +
  knowledge_versions 留痕（action=admission_approve / admission_reject）。

RBAC：GET 任意已登录角色；POST 上传/准入 仅 kb_admin（知识资产管理职责）。
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.db import get_conn
from app.api.deps import get_current_user, require_roles
from app.api.errors import ApiError, ok

router = APIRouter(prefix="/api/knowledge/docs", tags=["knowledge"])

_DOC_TYPES = {"manual", "work_order", "procedure"}
_DOC_STATUS = {"pending", "indexed", "failed"}


@router.get("")
async def list_docs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="pending/indexed/failed"),
    doc_type: str | None = Query(None, description="manual/work_order/procedure"),
    _: dict[str, Any] = Depends(get_current_user),
) -> dict:
    if status is not None and status not in _DOC_STATUS:
        raise ApiError("E_INVALID_ARG", f"status 仅支持 {'/'.join(sorted(_DOC_STATUS))}")
    if doc_type is not None and doc_type not in _DOC_TYPES:
        raise ApiError("E_INVALID_ARG", f"doc_type 仅支持 {'/'.join(sorted(_DOC_TYPES))}")

    conds: list[str] = []
    params: list[Any] = []
    if status:
        conds.append("status = %s")
        params.append(status)
    if doc_type:
        conds.append("doc_type = %s")
        params.append(doc_type)
    where = f"WHERE {' AND '.join(conds)}" if conds else ""

    with get_conn() as conn:
        total = conn.execute(
            f"SELECT count(*) AS n FROM documents {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"""SELECT doc_id, title, source, doc_type, device_model, status,
                       admission_status, created_at
                FROM documents {where}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s""",
            [*params, size, (page - 1) * size]).fetchall()
    return ok({"items": [dict(r) for r in rows],
               "total": total, "page": page, "size": size})


class DocCreate(BaseModel):
    """上传占位请求体（仅元数据；正文文件传输待流水线接入时定稿）。"""

    title: str = Field(min_length=1, max_length=200)
    doc_type: str = Field(description="manual/work_order/procedure")
    source: str = Field(min_length=1, max_length=100, description="来源（如 供应商手册/工单系统）")
    device_model: str | None = Field(default=None, max_length=100)
    content: str | None = Field(default=None, max_length=200_000,
                                description="可选正文文本；仅用于计算 checksum，暂不分块")


@router.post("")
async def create_doc(
    body: DocCreate,
    user: dict[str, Any] = Depends(require_roles("kb_admin")),
) -> dict:
    if body.doc_type not in _DOC_TYPES:
        raise ApiError("E_INVALID_ARG", f"doc_type 仅支持 {'/'.join(sorted(_DOC_TYPES))}")

    doc_id = str(uuid.uuid4())
    checksum = hashlib.sha256(
        (body.content or f"{body.title}:{doc_id}").encode("utf-8")).hexdigest()

    with get_conn() as conn:   # 两写同事务：登记 + 版本审计
        conn.execute(
            """INSERT INTO documents
                   (doc_id, title, source, doc_type, device_model, checksum, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'pending')""",
            (doc_id, body.title, body.source, body.doc_type,
             body.device_model, checksum))
        conn.execute(
            "INSERT INTO knowledge_versions (doc_id, version, action, actor) "
            "VALUES (%s, 1, 'create', %s)",
            (doc_id, user["username"]))

    return ok({"doc_id": doc_id, "status": "pending",
               "note": "元数据已登记（pending）；解析/分块/向量化由索引流水线推进，准入审核见 admission 接口"})


# ---------------------------------------------------------------- 准入审核（D0-6 契约补丁）

class AdmissionRequest(BaseModel):
    """准入决策：approve=准予入库（流水线可索引）；reject=驳回（永不索引）。"""

    action: str = Field(description="approve | reject")
    comment: str = Field(default="", max_length=2000)


@router.post("/{doc_id}/admission")
async def admit_doc(
    doc_id: str,
    body: AdmissionRequest,
    user: dict[str, Any] = Depends(require_roles("kb_admin")),
) -> dict:
    """知识准入审核（V5.0 §7.1 R-M3 防知识库投毒）。

    一次性决策：pending → approved / rejected；已决策再次提交 → E_CONFLICT。
    双写同事务：documents.admission_* 三列 + knowledge_versions 留痕
    （action=admission_approve / admission_reject，version=max+1）。
    """
    if body.action not in ("approve", "reject"):
        raise ApiError("E_INVALID_ARG", "action 仅支持 approve/reject")
    target = "approved" if body.action == "approve" else "rejected"
    ver_action = f"admission_{body.action}"

    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError as exc:
        raise ApiError("E_INVALID_ARG", "doc_id 非法 UUID") from exc

    with get_conn() as conn:
        row = conn.execute(
            "SELECT admission_status FROM documents WHERE doc_id = %s",
            (doc_uuid,)).fetchone()
        if row is None:
            raise ApiError("E_NOT_FOUND", f"文档 {doc_id} 不存在")
        if row["admission_status"] != "pending":
            raise ApiError(
                "E_CONFLICT",
                f"该文档准入已决策（{row['admission_status']}），不可重复审核")

        conn.execute(
            """UPDATE documents
               SET admission_status = %s, admitted_by = %s, admitted_at = now()
               WHERE doc_id = %s""",
            (target, user["username"], doc_uuid))
        conn.execute(
            """INSERT INTO knowledge_versions (doc_id, version, action, actor)
               SELECT %s, COALESCE(MAX(version), 0) + 1, %s, %s
               FROM knowledge_versions WHERE doc_id = %s""",
            (doc_uuid, ver_action, user["username"], doc_uuid))

    return ok({"doc_id": doc_id, "admission_status": target,
               "admitted_by": user["username"],
               "comment": body.comment.strip()})
