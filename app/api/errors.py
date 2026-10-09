"""统一响应包络与错误码（对齐 V5.0 §5.2 / §5.5 与 Phase 4 计划 §6.1）。

包络：{code, message, data, trace_id}
- 成功：code = 0（数值），message = "ok"
- 失败：code = 错误码字符串（E_TIMEOUT / E_NOT_FOUND / E_INVALID_ARG /
        E_UPSTREAM / E_CONFLICT / E_PERMISSION / E_UNAUTHORIZED / E_INTERNAL），
        前端 `body.code !== 0` 判断同时兼容两种形态

trace_id：由 main.py 中间件按请求生成（uuid4 hex[:16]），经 contextvar 传递，
          同时写入 X-Trace-Id 响应头，便于审计关联（UI 方案 §10.3）。
"""

from __future__ import annotations

from contextvars import ContextVar

# 当前请求 trace_id（中间件写入，包络/日志读取）
_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")


def get_trace_id() -> str:
    return _trace_id.get()


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)


# 错误码 → HTTP 状态码（唯一映射处）
ERROR_STATUS: dict[str, int] = {
    "E_UNAUTHORIZED": 401,   # 未登录 / 会话失效（§5.2 之外补充：登录态）
    "E_PERMISSION": 403,     # 无权限（RBAC / 职责分离）
    "E_NOT_FOUND": 404,
    "E_INVALID_ARG": 422,
    "E_CONFLICT": 409,       # 状态已变更（并发锁 / 幂等冲突）
    "E_TIMEOUT": 504,
    "E_UPSTREAM": 502,
    "E_INTERNAL": 500,       # 未分类服务端错误（兜底，不对外透出细节）
}


class ApiError(Exception):
    """业务错误：携带错误码与人话消息（message 面向用户，不含堆栈）。"""

    def __init__(self, code: str, message: str, data=None):
        if code not in ERROR_STATUS:
            raise ValueError(f"未知错误码：{code}（须在 ERROR_STATUS 登记）")
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"{code}: {message}")

    @property
    def status(self) -> int:
        return ERROR_STATUS[self.code]


def ok(data=None) -> dict:
    """成功包络。"""
    return {"code": 0, "message": "ok", "data": data, "trace_id": get_trace_id()}


def fail(err: ApiError) -> dict:
    """失败包络。"""
    return {"code": err.code, "message": err.message, "data": err.data,
            "trace_id": get_trace_id()}
