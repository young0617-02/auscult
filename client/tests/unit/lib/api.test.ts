/** lib/api.ts 单测（P4-D2）：包络解包 / 错误码人话映射 / 401 会话处置 / 超时 / token 注入 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, post, postLogin, request } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const OK = (data: unknown, traceId = "t-ok") =>
  new Response(JSON.stringify({ code: 0, message: "ok", data, trace_id: traceId }), {
    status: 200,
    headers: { "Content-Type": "application/json", "X-Trace-Id": traceId },
  });

const FAIL = (code: string, message: string, traceId = "t-err", status = 400) =>
  new Response(JSON.stringify({ code, message, data: null, trace_id: traceId }), {
    status,
    headers: { "Content-Type": "application/json", "X-Trace-Id": traceId },
  });

/** 统一 mock 形状：带 path/init 形参，便于读取调用参数 */
function mockFetch(impl: (path: string, init?: RequestInit) => Promise<Response>) {
  return vi.fn(impl as (input: string, init?: RequestInit) => Promise<Response>);
}

async function catchApiError(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
    throw new Error("预期抛出 ApiError，但成功了");
  } catch (e) {
    return e as ApiError;
  }
}

beforeEach(() => {
  localStorage.clear();
  useAuth.setState({ token: null, user: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("request 包络解包", () => {
  it("成功：code=0 返回 data 且不抛错", async () => {
    vi.stubGlobal("fetch", mockFetch(async () => OK({ hello: "world" })));
    await expect(request("/api/ping")).resolves.toEqual({ hello: "world" });
  });

  it("成功：请求自动附加 Content-Type", async () => {
    const fetchMock = mockFetch(async () => OK({}));
    vi.stubGlobal("fetch", fetchMock);
    await request("/api/ping");
    const headers = new Headers(fetchMock.mock.calls[0]![1]!.headers as HeadersInit);
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("未登录：不附加 Authorization 头", async () => {
    const fetchMock = mockFetch(async () => OK({}));
    vi.stubGlobal("fetch", fetchMock);
    await request("/api/ping");
    const headers = new Headers(fetchMock.mock.calls[0]![1]!.headers as HeadersInit);
    expect(headers.get("Authorization")).toBeNull();
  });

  it("已登录：附加 Bearer token（来自 auth store）", async () => {
    useAuth.setState({ token: "jwt-token", user: null });
    const fetchMock = mockFetch(async () => OK({}));
    vi.stubGlobal("fetch", fetchMock);
    await request("/api/ping");
    const headers = new Headers(fetchMock.mock.calls[0]![1]!.headers as HeadersInit);
    expect(headers.get("Authorization")).toBe("Bearer jwt-token");
  });
});

describe("request 错误处置", () => {
  it("业务失败：抛 ApiError，code/人话/trace_id 齐备", async () => {
    vi.stubGlobal("fetch", mockFetch(async () => FAIL("E_CONFLICT", "已被锁定", "trace-abc", 409)));
    const err = await catchApiError(request("/api/x"));
    expect(err.code).toBe("E_CONFLICT");
    expect(err.humanMessage).toBe("状态已变更，请刷新后重试");
    expect(err.traceId).toBe("trace-abc");
  });

  it("未知错误码：人话回退服务端 message", async () => {
    vi.stubGlobal("fetch", mockFetch(async () => FAIL("E_FUTURE", "新错误文案", "t1", 418)));
    const err = await catchApiError(request("/api/x"));
    expect(err.humanMessage).toBe("新错误文案");
  });

  it("401：清空会话并跳转 /login", async () => {
    useAuth.setState({ token: "jwt", user: null });
    const assign = vi.fn();
    vi.stubGlobal("window", Object.assign(window, { location: { assign } }));
    vi.stubGlobal("fetch", mockFetch(async () => FAIL("E_UNAUTHORIZED", "未登录", "t2", 401)));
    await catchApiError(request("/api/x"));
    expect(useAuth.getState().token).toBeNull();
    expect(assign).toHaveBeenCalledWith("/login");
  });

  it("网络失败：抛 E_NETWORK 人话", async () => {
    vi.stubGlobal("fetch", mockFetch(async () => { throw new TypeError("fetch failed"); }));
    const err = await catchApiError(request("/api/x"));
    expect(err.code).toBe("E_NETWORK");
    expect(err.humanMessage).toBe("网络连接失败，请检查网络后重试");
  });

  it("超时：抛 E_TIMEOUT 人话", async () => {
    vi.stubGlobal("fetch", mockFetch((_path, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("The operation was aborted.", "TimeoutError")));
      })));
    const err = await catchApiError(request("/api/x", { timeoutMs: 30 }));
    expect(err.code).toBe("E_TIMEOUT");
    expect(err.humanMessage).toBe("请求超时，请稍后重试");
  });

  it("非 JSON 响应：抛 E_INTERNAL 且不透出内部细节", async () => {
    vi.stubGlobal("fetch", mockFetch(async () => new Response("<html>502</html>", { status: 502 })));
    const err = await catchApiError(request("/api/x"));
    expect(err.code).toBe("E_INTERNAL");
    expect(err.serverMessage).toContain("502");
  });
});

describe("post 便捷封装", () => {
  it("JSON 序列化请求体并解包 data", async () => {
    const fetchMock = mockFetch(async () => OK({ access_token: "t", user: { role: "engineer" } }));
    vi.stubGlobal("fetch", fetchMock);
    const data = await post<{ access_token: string }>("/api/auth/login", { username: "u", password: "p" });
    expect(data.access_token).toBe("t");
    const init = fetchMock.mock.calls[0]![1]!;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ username: "u", password: "p" });
  });

  it("postLogin：登录 401 不触发全局跳转（错误交由页面展示）", async () => {
    useAuth.setState({ token: "jwt", user: null });
    const assign = vi.fn();
    vi.stubGlobal("window", Object.assign(window, { location: { assign } }));
    vi.stubGlobal("fetch", mockFetch(async () => FAIL("E_UNAUTHORIZED", "用户名或密码错误", "t3", 401)));
    const err = await catchApiError(postLogin("/api/auth/login", { username: "u", password: "bad" }));
    expect(err.code).toBe("E_UNAUTHORIZED");
    expect(err.serverMessage).toBe("用户名或密码错误");
    expect(assign).not.toHaveBeenCalled();
    expect(useAuth.getState().token).toBe("jwt"); // 会话不被清除
  });
});
