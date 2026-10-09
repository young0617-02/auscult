"use client";

/**
 * ConfidenceBadge / RiskTag（P4-D9）：终态消息与报告页共用的语义徽章。
 * 置信度分档口径对齐路由阈值（build.py：≥0.75 正常 / [0.50,0.75) 云端复核 / <0.50 降级）。
 */

import { cn } from "cn";

export function ConfidenceBadge({ value, className }: { value: number; className?: string }) {
  const v = Number(value);
  const safe = Number.isFinite(v) ? v : 0;
  const tone =
    safe >= 0.75
      ? "border-risk-low-edge bg-risk-low-surface text-risk-low-text"
      : safe >= 0.5
        ? "border-risk-medium-edge bg-risk-medium-surface text-risk-medium-text"
        : "border-risk-high-edge bg-risk-high-surface text-risk-high-text";
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-mono", tone, className)}
      title="置信度（检索/传感器/图谱/模型加权）"
      data-testid="confidence-badge"
    >
      置信度 {safe.toFixed(2)}
    </span>
  );
}

const RISK_LABEL: Record<string, string> = { low: "低风险", medium: "中风险", high: "高风险" };

export function RiskTag({ level, className }: { level: string; className?: string }) {
  const tone =
    level === "high"
      ? "border-risk-high-edge bg-risk-high-surface text-risk-high-text"
      : level === "medium"
        ? "border-risk-medium-edge bg-risk-medium-surface text-risk-medium-text"
        : "border-edge-subtle bg-surface-raised text-fg-secondary";
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs", tone, className)} data-testid="risk-tag">
      {RISK_LABEL[level] ?? level}
    </span>
  );
}
