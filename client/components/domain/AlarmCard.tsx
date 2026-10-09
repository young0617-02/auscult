"use client";

/**
 * AlarmCard（L3 领域组件）：严重度色条 + 设备/指标 + 实测值 + 状态胶囊。
 * 去重计数徽标（DedupBadge）位与诊断状态联动胶囊在 M4.2 接 thread 数据后补全。
 */

import { cn } from "cn";
import { SEVERITY_LABEL, STATUS_LABEL, type AlarmItem } from "@/lib/types/alarm";

const SEVERITY_TONE = {
  info: { bar: "bg-risk-low", pill: "bg-risk-low-surface text-risk-low-text border-risk-low-edge" },
  warning: { bar: "bg-risk-medium", pill: "bg-risk-medium-surface text-risk-medium-text border-risk-medium-edge" },
  critical: { bar: "bg-risk-high", pill: "bg-risk-high-surface text-risk-high-text border-risk-high-edge" },
} as const;

const STATUS_TONE = {
  open: "text-state-running",
  acked: "text-state-pending",
  closed: "text-state-skipped",
} as const;

/** 未知 severity 的中性降级（防御历史脏数据，避免看板崩溃） */
const NEUTRAL_TONE = {
  bar: "bg-state-skipped",
  pill: "border-edge-subtle bg-surface-raised text-fg-tertiary",
} as const;

/** REST(ISO) 与 alarm:new(epoch ms) 双形态时间归一 */
export function alarmTime(ts: string | number): Date {
  return typeof ts === "number" ? new Date(ts) : new Date(ts);
}

export function formatAlarmTime(ts: string | number): string {
  const d = alarmTime(ts);
  return d.toLocaleTimeString("zh-CN", { hour12: false });
}

export function AlarmCard({
  alarm,
  highlight,
  action,
}: {
  alarm: AlarmItem;
  highlight?: boolean;
  /** 右侧动作槽（如「发起诊断」，由装配层按 RBAC 注入） */
  action?: React.ReactNode;
}) {
  const tone = SEVERITY_TONE[alarm.severity] ?? NEUTRAL_TONE;
  return (
    <article
      className={cn(
        "relative flex items-stretch gap-3 overflow-hidden rounded-lg border border-edge-subtle bg-surface-raised pr-4",
        highlight && "alarm-pulse border-risk-high-edge",
      )}
    >
      {/* 严重度色条 */}
      <span className={cn("w-1 shrink-0", tone.bar)} aria-hidden />
      <div className="flex min-w-0 flex-1 items-center gap-3 py-2.5">
        <span
          className={cn(
            "shrink-0 rounded-full border px-2 py-0.5 text-xs",
            tone.pill,
          )}
        >
          {SEVERITY_LABEL[alarm.severity] ?? alarm.severity}
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm text-fg-primary">
            {alarm.device_id} · {alarm.metric}
          </div>
          <div className="text-xs text-fg-tertiary">
            {STATUS_LABEL[alarm.status]}
            <span className={cn("ml-2", STATUS_TONE[alarm.status])}>
              ● {STATUS_LABEL[alarm.status]}
            </span>
          </div>
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-3">
          <div className="text-right">
            <div className="font-mono text-sm text-fg-primary">{alarm.value ?? "—"}</div>
            <time className="font-mono text-xs text-fg-tertiary" dateTime={new Date(alarmTime(alarm.ts)).toISOString()}>
              {formatAlarmTime(alarm.ts)}
            </time>
          </div>
          {action}
        </div>
      </div>
    </article>
  );
}
