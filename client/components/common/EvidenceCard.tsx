"use client";

/**
 * EvidenceCard（P4-D8）：证据卡片（来源 / 得分 / 路由线索 / 原文摘录）。
 * - 完整形态：报告详情与审核界面使用（有 text/score/routes 的 EvidenceItem）
 * - EvidenceChip：追问回答中的引用锚点（仅 chunk_id），M4.3 报告页接原文后升级为可下钻
 */

import { cn } from "cn";
import { BookOpen, Network, Wrench, Activity, FileText } from "lucide-react";

export type EvidenceSourceType = "knowledge" | "sensor" | "graph" | "maintenance" | string;

const SOURCE_META: Record<string, { label: string; icon: typeof BookOpen }> = {
  knowledge: { label: "知识库", icon: BookOpen },
  sensor: { label: "传感器", icon: Activity },
  graph: { label: "图谱", icon: Network },
  maintenance: { label: "历史工单", icon: Wrench },
};

export interface EvidenceCardProps {
  chunkId: string;
  text?: string;
  score?: number;
  routes?: string[];
  sourceType?: EvidenceSourceType;
  className?: string;
}

export function EvidenceCard({ chunkId, text, score, routes, sourceType = "knowledge", className }: EvidenceCardProps) {
  const meta = SOURCE_META[sourceType] ?? { label: sourceType || "知识库", icon: FileText };
  const Icon = meta.icon;
  return (
    <article
      className={cn("rounded-lg border border-edge-subtle bg-surface-raised px-3 py-2", className)}
      data-testid="evidence-card"
      data-chunk-id={chunkId}
    >
      <div className="flex items-center gap-2 text-xs">
        <Icon className="size-3.5 shrink-0 text-fg-tertiary" />
        <span className="text-fg-secondary">{meta.label}</span>
        <span className="font-mono text-fg-tertiary">{chunkId}</span>
        {typeof score === "number" && Number.isFinite(score) && (
          <span className="ml-auto font-mono text-fg-tertiary" title="检索得分">
            {score.toFixed(3)}
          </span>
        )}
      </div>
      {text && <p className="mt-1.5 line-clamp-3 text-xs leading-5 text-fg-primary">{text}</p>}
      {routes && routes.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {routes.map((r) => (
            <span key={r} className="rounded bg-surface-base px-1.5 py-0.5 text-[10px] text-fg-tertiary">
              {r}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

/** 引用锚点（追问 citations）：无原文数据时的最小展示，title 提示下钻入口 */
export function EvidenceChip({ chunkId }: { chunkId: string }) {
  return (
    <span
      className="inline-flex cursor-default items-center rounded border border-edge-subtle bg-surface-base px-1.5 py-0.5 font-mono text-[10px] text-fg-tertiary"
      title={`引用证据 ${chunkId}（原文可在报告详情查看）`}
    >
      [{chunkId}]
    </span>
  );
}
