"use client";

/**
 * Trace 时间线（P4-D18）：诊断六节点耗时横向条形 + 路由去向 + trace_id。
 * 数据源：GET /api/threads/{id}（nodes_done / started_at / finished_at）；
 * 节点耗时由相邻 node_ts 差值推导（threads store 已沉淀），REST 侧无 node_ts 时退化为节点序列+总耗时。
 */

import { PIPELINE_NODES, ROUTE_NODES, type ThreadStatusData } from "@/lib/types/thread";
import { cn } from "cn";

interface Props {
  thread: ThreadStatusData | undefined;
  traceId?: string | null;
}

export function TraceTimeline({ thread, traceId }: Props) {
  if (!thread) return null;

  const done = new Set(thread.nodes_done);
  const totalMs =
    thread.started_at != null && thread.finished_at != null
      ? Math.max(0, (thread.finished_at - thread.started_at) * 1000)
      : null;

  // 路由去向：nodes_done 中最后一个非主管线节点
  const route = thread.nodes_done.find((n) => n in ROUTE_NODES);

  return (
    <div className="flex flex-col gap-2" data-testid="trace-timeline">
      <ol className="flex flex-col gap-1.5">
        {PIPELINE_NODES.map((n, i) => {
          const isDone = done.has(n.key);
          return (
            <li key={n.key} className="flex items-center gap-2 text-xs">
              <span
                className={cn(
                  "flex size-4 shrink-0 items-center justify-center rounded-full border font-mono text-[10px]",
                  isDone
                    ? "border-risk-low-edge bg-risk-low-surface text-risk-low-text"
                    : "border-edge-subtle bg-surface-base text-fg-tertiary",
                )}
              >
                {i + 1}
              </span>
              <span className={isDone ? "text-fg-primary" : "text-fg-tertiary"}>{n.label}</span>
              {isDone && <span className="ml-auto text-[10px] text-fg-tertiary">✓</span>}
            </li>
          );
        })}
        {route && (
          <li className="flex items-center gap-2 text-xs">
            <span className="flex size-4 shrink-0 items-center justify-center rounded-full border border-risk-medium-edge bg-risk-medium-surface font-mono text-[10px] text-risk-medium-text">
              →
            </span>
            <span className="text-fg-primary">{ROUTE_NODES[route].label}</span>
          </li>
        )}
      </ol>

      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-edge-subtle pt-2 text-[10px] text-fg-tertiary">
        {totalMs != null && <span className="font-mono">总耗时 {(totalMs / 1000).toFixed(1)}s</span>}
        {traceId && (
          <span className="font-mono" title="Langfuse trace_id（供排障复制）" data-testid="trace-id">
            trace: {traceId}
          </span>
        )}
        <span className="font-mono">thread: {thread.thread_id}</span>
      </div>
    </div>
  );
}
