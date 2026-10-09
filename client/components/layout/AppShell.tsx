"use client";

/**
 * AppShell（应用外壳，L5）：TopStatusBar / NavRail / Workspace / StatusBar + 全局 Inspector。
 * 三栏结构与区域职责对齐 UI 方案 §3.1。
 */

import { TopStatusBar } from "@/components/layout/TopStatusBar";
import { NavRail } from "@/components/layout/NavRail";
import { StatusBar } from "@/components/layout/StatusBar";
import { InspectorDrawer } from "@/components/layout/InspectorDrawer";
import { ConnectionBanner } from "@/components/layout/ConnectionBanner";
import { SocketProvider } from "@/components/providers/SocketProvider";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    // SocketProvider 包整个外壳：横幅/铃铛/看板统一消费实时层
    <SocketProvider>
      <div className="grid h-dvh grid-rows-[auto_auto_minmax(0,1fr)_auto]">
        <TopStatusBar />
        <ConnectionBanner />
        <div className="grid min-h-0 grid-cols-[auto_minmax(0,1fr)] overflow-hidden">
          <NavRail />
          <main className="min-h-0 overflow-y-auto">{children}</main>
        </div>
        <StatusBar />
        <InspectorDrawer />
      </div>
    </SocketProvider>
  );
}
