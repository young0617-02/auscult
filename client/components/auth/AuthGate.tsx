"use client";

/**
 * AuthGate（RBAC 路由守卫，P4-D3）。
 * - 未登录 → 跳 /login?next=<当前路径>
 * - 指定 roles 且角色不符 → 渲染原因文案页（能力裁剪而非隐藏，UI 方案 §1.2）
 * - 水合前渲染骨架，避免 localStorage 回读造成的闪烁误判
 */

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ShieldX } from "lucide-react";
import { useAuth, hasRole, type Role, ROLE_LABEL } from "@/lib/auth";
import { Skeleton } from "@/components/ui/skeleton";

export function AuthGate({ roles, children }: { roles?: readonly Role[]; children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { token, user, hydrated } = useAuth();

  useEffect(() => {
    if (hydrated && !token) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [hydrated, token, pathname, router]);

  if (!hydrated) {
    return (
      <div className="flex h-dvh flex-col gap-3 bg-surface-base p-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72" />
        <Skeleton className="mt-4 h-64 w-full" />
      </div>
    );
  }

  if (!token) return null; // 跳转进行中

  if (roles && !hasRole(user, roles)) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-3 bg-surface-base p-8 text-center">
        <ShieldX className="size-10 text-risk-high" aria-hidden />
        <h1 className="text-lg font-semibold text-fg-primary">无权访问该页面</h1>
        <p className="max-w-md text-sm text-fg-secondary">
          该页面仅限 {roles.map((r) => ROLE_LABEL[r]).join(" / ")}
          {user && <>访问，你当前的角色为「{ROLE_LABEL[user.role]}」。</>}
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
