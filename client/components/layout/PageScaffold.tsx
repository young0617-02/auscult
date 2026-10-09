"use client";

/**
 * PageScaffold（页面统一三段式骨架，§3.3）：PageToolbar → KpiStrip → MainCanvas。
 * 所有一级页面统一遵循该结构，降低认知负担。
 */

import { cn } from "cn";

interface PageScaffoldProps {
  title: string;
  description?: string;
  toolbar?: React.ReactNode;
  kpis?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  /** 覆盖主内容区默认 padding/overflow（如诊断控制台全高三栏布局） */
  contentClassName?: string;
}

export function PageScaffold({
  title,
  description,
  toolbar,
  kpis,
  children,
  className,
  contentClassName,
}: PageScaffoldProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* ① 工具条：左对齐客观动作，右对齐视图选项 */}
      <div className="sticky top-0 z-10 flex items-center gap-4 border-b border-edge-subtle bg-surface-base px-6 py-3">
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold text-fg-primary">{title}</h1>
          {description && (
            <p className="truncate text-xs text-fg-tertiary">{description}</p>
          )}
        </div>
        {toolbar && <div className="ml-auto flex items-center gap-2">{toolbar}</div>}
      </div>

      {/* ② KPI 带（可折叠，D4+ 接真实统计） */}
      {kpis && (
        <div className="border-b border-edge-subtle bg-surface-base px-6 py-3">{kpis}</div>
      )}

      {/* ③ 主内容区 */}
      <div className={contentClassName ?? cn("min-h-0 flex-1 overflow-y-auto px-6 py-4", className)}>
        {children}
      </div>
    </div>
  );
}

/** KPI 指标卡（L2 通用复合层，只绑定语义槽位） */
export function KpiCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "default" | "high" | "medium" | "low";
}) {
  const toneText = {
    default: "text-fg-primary",
    high: "text-risk-high-text",
    medium: "text-risk-medium-text",
    low: "text-risk-low-text",
  }[tone];
  return (
    <div className="min-w-28 rounded-lg border border-edge-subtle bg-surface-raised px-3 py-2">
      <div className="text-xs text-fg-tertiary">{label}</div>
      <div className={`mt-0.5 font-mono text-xl leading-7 ${toneText}`}>{value}</div>
    </div>
  );
}
