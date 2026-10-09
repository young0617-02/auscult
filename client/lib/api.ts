/**
 * 统一 REST 客户端（P4-D2，契约对齐 app/api/errors.py 包络）。
 *
 * 包络：{ code, message, data, trace_id }
 *   - 成功：code = 0（数值）
 *   - 失败：code = E_*（字符串）
 * 错误处理（UI 方案 §10.3）：错误码 → 人话 + 建议动作；trace_id 供排障复制。
 * 401：清除本地会话并跳转 /login（仅浏览器环境）。
 */

import { useAuth } from "@/lib/auth";

/** 后端统一包络（errors.py ok/fail 的形状） */
export interface ApiEnvelope<T> {
  code: number | string;
  message: string;
  data: T;
  trace_id: string;
}

/** 错误码 → 人话 + 建议动作（缺省回退服务端 message） */
const ERROR_HINT: Record<string, string> = {
  E_UNAUTHORIZED: "登录已失效，请重新登录",
  E_PERMISSION: "你的角色无此权限，请联系管理员",
  E_NOT_FOUND: "资源不存在或已被删除",
  E_INVALID_ARG: "请求参数有误，请检查后重试",
  E_CONFLICT: "状态已变更，请刷新后重试",
  E_TIMEOUT: "请求超时，请稍后重试",
  E_UPSTREAM: "依赖服务暂不可用，请稍后重试",
  E_INTERNAL: "服务内部错误，请稍后重试",
  E_NETWORK: "网络连接失败，请检查网络后重试",
};

/** 前端业务错误：携带错误码、人话消息、服务端原消息与 trace_id */
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly humanMessage: string,
    public readonly serverMessage: string,
    public readonly traceId: string,
  ) {
    super(`${code}: ${humanMessage}`);
    this.name = "ApiError";
  }
}

/** 当前会话请求头（token 来自 auth store；未登录不附加） */
function authHeaders(): Record<string, string> {
  const token = useAuth.getState().token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

/** 401 统一处置：清会话 → 跳登录（避免在请求内再触发请求） */
function handleUnauthorized(): void {
  if (!isBrowser()) return;
  useAuth.getState().clear();
  window.location.assign("/login");
}

export interface RequestOptions extends Omit<RequestInit, "headers"> {
  /** 请求头（与 auth 头合并，调用方可覆盖） */
  headers?: Record<string, string>;
  /** 超时毫秒数（UI 超时略大于后端 +30%，缺省 30s） */
  timeoutMs?: number;
  /** 跳过 401 全局跳转（登录接口自身失败时不重定向，由页面展示错误） */
  skipUnauthorizedRedirect?: boolean;
}

/**
 * 请求并解包：返回 data；业务失败抛 ApiError。
 * @param path 以 /api 开头的后端路径（经 Nginx/Next 代理）
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { headers, timeoutMs = 30_000, skipUnauthorizedRedirect = false, ...init } = options;

  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...headers,
      },
      signal: init.signal ?? AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new ApiError("E_TIMEOUT", ERROR_HINT.E_TIMEOUT, "客户端超时", "-");
    }
    throw new ApiError("E_NETWORK", ERROR_HINT.E_NETWORK, String(err), "-");
  }

  // 非 JSON 响应（网关/代理层错误页等）→ 不透出内部细节
  const body = (await res.json().catch(() => null)) as ApiEnvelope<T> | null;
  if (body === null) {
    const trace = res.headers.get("X-Trace-Id") ?? "-";
    throw new ApiError("E_INTERNAL", ERROR_HINT.E_INTERNAL, `非 JSON 响应（HTTP ${res.status}）`, trace);
  }

  if (body.code !== 0) {
    const code = String(body.code);
    const traceId = body.trace_id ?? res.headers.get("X-Trace-Id") ?? "-";
    if (code === "E_UNAUTHORIZED" && !skipUnauthorizedRedirect) handleUnauthorized();
    throw new ApiError(code, ERROR_HINT[code] ?? body.message, body.message, traceId);
  }

  return body.data;
}

/** JSON POST 便捷封装（登录/审核/发起诊断等） */
export function post<T>(path: string, body: unknown, options: RequestOptions = {}): Promise<T> {
  return request<T>(path, { ...options, method: "POST", body: JSON.stringify(body) });
}

/** 登录专用 POST：401 不触发全局跳转（页面自行展示服务端 message） */
export function postLogin<T>(path: string, body: unknown): Promise<T> {
  return post<T>(path, body, { skipUnauthorizedRedirect: true });
}
