"use client";

/**
 * ProgressSteps（P4-D7）：节点级进度条（diagnosis:progress 驱动）。
 * 五节点主管线 + 条件路由四去向（build.py 图结构），running 态下
 * 第一个未完成节点显示进行中动画；有 node_ts 时推每步耗时。
 */

import { Loader2 } from "lucide-react";
import { cn } from "cn";
import { PIPELINE_NODES, ROUTE_NODES, type ThreadStatus } from "@/lib/types/thread";
import { activeNode, deriveRoute, nodeDurationSec } from "@/lib/threads-realtime";

export function ProgressSteps({
  nodesDone,
  nodeTs,
  status,
  className,
}: {
  nodesDone: string[];
  nodeTs?: Record<string, number>;
  status: ThreadStatus;
  className?: string;
}) {
  const active = status === "running" ? activeNode(nodesDone) : null;
  const route = deriveRoute(nodesDone);
  const ts = nodeTs ?? {};

  const rowState = (node: string): "done" | "running" | "pending" => {
    if (nodesDone.includes(node)) return "done";
    if (node === active) return "running";
    return "pending";
  };

  return (
    <ol className={cn("flex flex-col gap-0.5", className)} data-testid="progress-steps">
      {PIPELINE_NODES.map((n) => (
        <StepRow
          key={n.key}
          label={n.label}
          state={rowState(n.key)}
          durationSec={nodeTs ? nodeDurationSec(n.key, ts, nodesDone) : null}
        />
      ))}
      {/* 路由段：仅渲染已发生的路由节点（canonical 顺序） */}
      {(["escalate_cloud", "degrade", "human_review", "finalize"] as const).map((k) =>
        nodesDone.includes(k) ? (
          <StepRow
            key={k}
            label={ROUTE_NODES[k].label}
            state="done"
            durationSec={nodeTs ? nodeDurationSec(k, ts, nodesDone) : null}
            tone={k === "degrade" || k === "human_review" ? "warn" : undefined}
          />
        ) : null,
      )}
      {/* running 且主管线全部完成但路由未落：等待路由决策 */}
      {status === "running" && active === null && route === null && (
        <StepRow label="路由决策" state="running" durationSec={null} />
      )}
      {/* waiting_review：human_review 挂起等待中 */}
      {status === "waiting_review" && !nodesDone.includes("human_review") && (
        <StepRow label="人工审核" state="running" durationSec={null} tone="warn" />
      )}
    </ol>
  );
}

function StepRow({
  label,
  state,
  durationSec,
  tone,
}: {
  label: string;
  state: "done" | "running" | "pending";
  durationSec: number | null;
  tone?: "warn";
}) {
  return (
    <li
      className={cn(
        "flex items-center gap-2 rounded px-2 py-1.5 text-xs",
        state === "done" && "text-fg-secondary",
        state === "running" && "bg-surface-raised text-fg-primary",
        state === "pending" && "text-fg-tertiary",
      )}
    >
      {state === "done" && (
        <span className={cn("font-mono", tone === "warn" ? "text-risk-medium-text" : "text-risk-low-text")}>✓</span>
      )}
      {state === "running" && <Loader2 className="size-3.5 shrink-0 animate-spin text-state-running" />}
      {state === "pending" && <span className="font-mono opacity-50">○</span>}
      <span className="truncate">{label}</span>
      {durationSec != null && (
        <span className="ml-auto shrink-0 font-mono text-[10px] text-fg-tertiary">
          {durationSec >= 10 ? Math.round(durationSec) : durationSec.toFixed(1)}s
        </span>
      )}
    </li>
  );
}
