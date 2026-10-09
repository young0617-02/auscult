"use client";

/**
 * NavRail（左导航栏，L5 布局层）。
 * 五页面 + 审计（仅系统管理员可见，D3 接入角色后生效）；
 * 徽标待办数位（待审核/待准入/未处理告警）为 D5+ 接入点。
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Bell,
  BookOpen,
  FileText,
  Radio,
  Share2,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { cn } from "cn";
import { useAuth, hasRole } from "@/lib/auth";

const NAV_ITEMS = [
  { href: "/alarms", label: "告警看板", icon: Bell, roles: null },
  { href: "/diagnosis", label: "诊断控制台", icon: Stethoscope, roles: null },
  { href: "/reports", label: "报告工作台", icon: FileText, roles: null },
  { href: "/knowledge", label: "知识库", icon: BookOpen, roles: null },
  { href: "/graph", label: "图谱探索", icon: Share2, roles: null },
  { href: "/audit", label: "审计日志", icon: ShieldCheck, roles: ["sys_admin"] },
] as const;

export function NavRail() {
  const pathname = usePathname();
  const user = useAuth((s) => s.user);

  const items = NAV_ITEMS.filter(
    (item) => !item.roles || hasRole(user, item.roles),
  );

  return (
    <nav
      aria-label="主导航"
      className="flex w-[200px] shrink-0 flex-col gap-1 border-r border-edge-subtle bg-surface-base px-2 py-3"
    >
      {items.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors duration-(--motion-fast)",
              active
                ? "bg-surface-selected text-fg-primary"
                : "text-fg-secondary hover:bg-surface-hover hover:text-fg-primary",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            <span>{label}</span>
            {/* 待办徽标位（D5+ 接入：待审核/待准入/未处理告警） */}
            <span data-nav-badge className="ml-auto" />
          </Link>
        );
      })}

      <div className="mt-auto px-3 pt-3">
        <div className="flex items-center gap-2 text-xs text-fg-tertiary">
          <Radio className="size-3" aria-hidden />
          <span>实时通道 D5 接入</span>
        </div>
      </div>
    </nav>
  );
}
