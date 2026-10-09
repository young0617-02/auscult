"use client";

/**
 * TopStatusBar（顶部全局状态栏，常驻不滚动）。
 * 全局态指示 + 用户菜单；健康类状态只做指示灯，点击展开详情（§3.2）。
 * D5 接 Socket 连接状态，D3 接真实用户会话，D19/D20 接 /api/health。
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Bell, LogOut, PanelRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useInspector } from "@/lib/store/inspector";
import { useConn } from "@/lib/store/connection";
import { useAuth, ROLE_LABEL } from "@/lib/auth";

export function TopStatusBar() {
  const showInspector = useInspector((s) => s.show);
  const user = useAuth((s) => s.user);
  const unread = useConn((s) => s.unreadAlarms);
  const clearUnread = useConn((s) => s.clearUnread);
  const router = useRouter();

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-edge-subtle bg-surface-base px-4">
      {/* 品牌标识 */}
      <div className="flex items-center gap-2">
        <span className="inline-block size-2.5 rounded-full bg-accent-primary" aria-hidden />
        <span className="text-sm font-semibold tracking-wide">
          AUSCULT · 工业设备诊断
        </span>
      </div>

      {/* 全局命令面板入口（⌘K，后续迭代接入） */}
      <Button
        variant="outline"
        size="sm"
        className="ml-2 w-56 justify-start text-fg-tertiary"
        disabled
      >
        <Search className="size-3.5" aria-hidden />
        全局搜索 ⌘K
      </Button>

      {/* 全局指标占位：活跃诊断 / 云端预算 / 数据源健康（D5+ 接真实数据） */}
      <div className="ml-4 hidden items-center gap-4 text-xs text-fg-secondary md:flex">
        <span>● 诊断中 0</span>
        <span>◐ 数据源 0/6</span>
      </div>

      <div className="ml-auto flex items-center gap-2">
        {/* 告警铃（未读 + 去重聚合数，alarm:new 累计；点击跳看板并清零） */}
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={unread > 0 ? `告警通知（${unread} 条未读）` : "告警通知"}
          onClick={() => {
            router.push("/alarms");
            clearUnread();
          }}
          className="relative"
        >
          <Bell className="size-4" aria-hidden />
          {unread > 0 && (
            <span
              data-testid="unread-badge"
              className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-risk-high px-1 text-[10px] font-medium leading-none text-white"
            >
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>

        {/* Inspector 全局入口 */}
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="打开上下文检查器"
          onClick={() =>
            showInspector({ tab: "citation", title: "检查器（空）" })
          }
        >
          <PanelRight className="size-4" aria-hidden />
        </Button>

        <Separator orientation="vertical" className="mx-1 h-5" />

        {/* 用户菜单（会话 + 退出，D3） */}
        {user ? <UserMenu /> : (
          <Button asChild variant="outline" size="sm">
            <Link href="/login">登录</Link>
          </Button>
        )}
      </div>
    </header>
  );
}

function UserMenu() {
  const user = useAuth((s) => s.user)!;
  const clear = useAuth((s) => s.clear);
  const router = useRouter();

  function handleLogout() {
    clear();
    router.replace("/login");
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2" data-testid="user-menu">
          <span className="flex items-center gap-1.5">
            <span className="font-medium text-fg-primary">{user.display_name}</span>
            <span className="rounded-sm bg-accent-subtle px-1.5 py-0.5 text-xs text-accent-primary">
              {ROLE_LABEL[user.role]}
            </span>
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel className="text-xs text-fg-tertiary">
          {user.username}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={handleLogout} data-testid="logout">
          <LogOut className="size-4" aria-hidden />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
