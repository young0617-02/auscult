"""P4 后端 API 应用工厂（FastAPI + Socket.IO 于 D0-4 挂载）。

职责（D0-1）：
- 统一响应包络 {code, message, data, trace_id}（errors.py）
- trace_id 中间件（uuid4 hex[:16]，写入 X-Trace-Id 响应头）
- 异常 → 错误码映射（ApiError / 请求校验 / 兜底 500）

启动：
    .venv\\Scripts\\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000
    （socket_app = FastAPI + Socket.IO；纯 REST 场景亦须用它，/socket.io 路径由 ASGIApp 接管）
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.config import JWT_SECRET
from app.api.errors import ApiError, ERROR_STATUS, fail, get_trace_id, ok, set_trace_id
from app.api.routes import alarms, auth, diagnose, graph, health, knowledge, reports, review
from app.api.socket import sio as sio_server, start_background_tasks
from app.api.runner import start_lifecycle_watcher


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_background_tasks()      # alarm:new 轮询桥接（D0-4）
    start_lifecycle_watcher()     # 审核 4h 通知 / 24h 超时降级（D0-5）
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="auscult-diagnosis-api", version="0.1.0",
                  lifespan=lifespan)

    if JWT_SECRET == "<REDACTED_DEV_SECRET>":  # 开发环境提醒，不中断启动
        import logging
        logging.getLogger("uvicorn.warning").warning(
            "JWT_SECRET 使用开发默认值——仅限本机开发，禁止用于任何外部环境")

    # ---------------- 中间件：trace_id + 统一成功包络 ----------------
    @app.middleware("http")
    async def trace_and_envelope(request: Request, call_next):
        set_trace_id(uuid.uuid4().hex[:16])
        response = await call_next(request)
        response.headers["X-Trace-Id"] = get_trace_id()
        return response

    # ---------------- 异常 → 统一失败包络 ----------------
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=fail(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        err = ApiError("E_INVALID_ARG", "请求参数校验失败",
                       data={"errors": exc.errors()[:10]})
        return JSONResponse(status_code=ERROR_STATUS[err.code], content=fail(err))

    @app.exception_handler(Exception)
    async def fallback_handler(_: Request, exc: Exception) -> JSONResponse:
        # 兜底：不向客户端透出内部细节；trace_id 供服务端日志反查
        err = ApiError("E_INTERNAL", "服务内部错误，请稍后重试")
        return JSONResponse(status_code=ERROR_STATUS[err.code], content=fail(err))

    # ---------------- 根包络（冒烟） ----------------
    @app.get("/api")
    async def root() -> dict:
        return ok({"service": "auscult-diagnosis-api", "version": app.version})

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(alarms.router)
    app.include_router(reports.router)
    app.include_router(graph.router)
    app.include_router(knowledge.router)
    app.include_router(diagnose.router)
    app.include_router(review.router)
    return app


app = create_app()

# Socket.IO 挂载（D0-4）：uvicorn 启动入口为 app.api.main:socket_app
socket_app = socketio.ASGIApp(sio_server, other_asgi_app=app)
