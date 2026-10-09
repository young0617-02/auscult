"use client";

/**
 * 登录页（P4-D3）：POST /api/auth/login → 存会话 → 按角色落地。
 * 交互约束（§10.3）：提交后立即禁用按钮（幂等双保险的前端侧）；
 * 失败提示三段式：人话 + 建议动作 + trace_id 可复制。
 */

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Loader2, LogIn } from "lucide-react";
import { ApiError, postLogin } from "@/lib/api";
import { useAuth, defaultRouteForRole, type AuthUser } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setAuth = useAuth((s) => s.setAuth);
  const token = useAuth((s) => s.token);
  const user = useAuth((s) => s.user);

  // 已登录用户访问 /login → 直接送回默认工作台
  useEffect(() => {
    if (token && user) {
      router.replace(defaultRouteForRole(user.role));
    }
  }, [token, user, router]);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<{ msg: string; traceId: string } | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (pending) return; // 提交中禁止重复提交
    setPending(true);
    setError(null);
    try {
      const data = await postLogin<{ access_token: string; user: AuthUser }>("/api/auth/login", {
        username,
        password,
      });
      setAuth(data.access_token, data.user);
      // next 参数优先（守卫带回来的原始目标），否则按角色默认落地
      const next = searchParams.get("next");
      router.replace(next && next.startsWith("/") ? next : defaultRouteForRole(data.user.role));
    } catch (err) {
      const apiErr = err as ApiError;
      // 登录场景直出服务端 message（"用户名或密码错误"等服务端人话）
      setError({ msg: apiErr.serverMessage ?? apiErr.humanMessage ?? "登录失败，请稍后重试", traceId: apiErr.traceId ?? "-" });
      setPending(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <div className="mb-1 flex items-center gap-2">
          <span className="inline-block size-2.5 rounded-full bg-accent-primary" aria-hidden />
          <span className="text-sm font-semibold tracking-wide">AUSCULT · 工业设备诊断</span>
        </div>
        <CardTitle className="text-xl">登录工作台</CardTitle>
        <CardDescription>使用运维分配的账号登录（工程师 / 审核员 / 知识库管理员 / 系统管理员）</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4" data-testid="login-form">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="username">用户名</Label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={pending}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={pending}
            />
          </div>

          {error && (
            <div
              role="alert"
              data-testid="login-error"
              className="rounded-md border border-notice-warning-edge bg-notice-warning-surface px-3 py-2 text-sm text-notice-warning-text"
            >
              <p>{error.msg}</p>
              <p className="mt-0.5 font-mono text-xs opacity-80">trace_id: {error.traceId}</p>
            </div>
          )}

          <Button type="submit" disabled={pending || !username || !password}>
            {pending ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden /> 登录中…
              </>
            ) : (
              <>
                <LogIn className="size-4" aria-hidden /> 登录
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <main className="flex h-dvh items-center justify-center bg-surface-base p-6">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
