"use client";

import { AppShell } from "@/components/layout/AppShell";
import { AuthGate } from "@/components/auth/AuthGate";

/**
 * (main) 路由组布局：登录后的主工作区（App Shell）。
 * AuthGate：未登录跳 /login；各页面的角色限制在页面级再包一层 AuthGate roles。
 */
export default function MainLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <AppShell>{children}</AppShell>
    </AuthGate>
  );
}
