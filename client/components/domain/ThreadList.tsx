"use client";

/**
 * ThreadList（P4-D6）：左栏诊断会话列表（客户端注册表驱动）。
 * 会话 = 一次诊断线程；状态胶囊随 socket 实时翻转（running→waiting_review/done/error）。
 */

import { useRouter } from "next/navigation";
import { Stethoscope } from "lucide-react";
import { cn } from "cn";
import { useThreads } from "@/lib/store/threads";
import { THREAD_STATUS_LABEL, type ThreadStatus } from "@/lib/types/thread";
import { EmptyState } from "@/components/common/EmptyState";

const STATUS_PILL: Record<ThreadStatus, string> = {
  running: "border-state-running/40 bg-state-running/10 text-state-running",
  waiting_review: "border-risk-medium-edge bg-risk-medium-surface text-risk-medium-text",
  done: "border-risk-low-edge bg-risk-low-surface text-risk-low-text",
  error: "border-risk-high-edge bg-risk-high-surface text-risk-high-text",
};

function relTime(ms: number): string {
  const diff = Date.now() - ms;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return new Date(ms).toLocaleDateString("zh-CN");
}

export function ThreadList({ activeId }: { activeId: string | null }) {
  const router = useRouter();
  const threads = useThreads((s) => s.threads);
  const order = useThreads((s) => s.order);
  const items = order.map((id) => threads[id]).filter(Boolean);

  if (items.length === 0) {
    return (
      <div className="p-3">
        <EmptyState
          icon={Stethoscope}
          title="暂无会话"
          reason="在告警看板点击「发起诊断」创建线程。"
          className="min-h-32 border-none p-4"
        />
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-1 p-2" data-testid="thread-list">
      {items.map((t) => (
        <li key={t.thread_id}>
          <button
            type="button"
            onClick={() => router.push(`/diagnosis?thread=${encodeURIComponent(t.thread_id)}`, { scroll: false })}
            className={cn(
              "w-full rounded-lg border px-2.5 py-2 text-left transition-colors",
              t.thread_id === activeId
                ? "border-edge-strong bg-surface-raised"
                : "border-transparent hover:border-edge-subtle hover:bg-surface-raised/60",
            )}
          >
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-xs text-fg-primary">
                {t.alarm.device_id} · {t.alarm.metric}
              </span>
              <span className={cn("shrink-0 rounded-full border px-1.5 py-px text-[10px]", STATUS_PILL[t.status])}>
                {THREAD_STATUS_LABEL[t.status]}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2 text-[10px] text-fg-tertiary">
              <span className="font-mono">{t.thread_id.slice(0, 12)}…</span>
              <span className="ml-auto">{relTime(t.updated_at)}</span>
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
