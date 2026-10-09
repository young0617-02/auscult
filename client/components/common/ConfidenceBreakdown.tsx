"use client";

/**
 * ConfidenceBreakdown（P4-D12）：置信度四分量分解可视化。
 * 口径：plan §6.2 / nodes/diagnose.py compute_confidence
 *   检索覆盖 0.35 · 传感器一致性 0.20 · 图谱支撑 0.15 · 模型自评（校准）0.30
 * 目的：让审核人看到「为什么系统这么判断」（安全边界的一部分）。
 * 注意：confidence_breakdown 未入 reports.payload（M4.3 已知边界），
 *   详情页暂以总置信度为唯一锚点；四分量分解待后端补持久化后接入。
 * 组件已就绪（纯函数条形），接入点留待 M4.4/P5 数据补齐。
 */

import { cn } from "cn";

const COMPONENTS = [
  { key: "retrieval", label: "检索覆盖", weight: 0.35, hint: "命中证据数量 / 期望 5 条" },
  { key: "sensor", label: "传感器一致性", weight: 0.2, hint: "多测点交叉验证一致度" },
  { key: "graph", label: "图谱支撑", weight: 0.15, hint: "关系路径命中（有/无）" },
  { key: "self", label: "模型自评", weight: 0.3, hint: "LLM 自评（经校准）" },
] as const;

export interface BreakdownInput {
  retrieval?: number;
  sensor?: number;
  graph?: number;
  self?: number;
}

export function ConfidenceBreakdown({
  breakdown,
  total,
  className,
}: {
  breakdown: BreakdownInput | null;
  total: number;
  className?: string;
}) {
  const safeTotal = Number.isFinite(Number(total)) ? Number(total) : 0;
  return (
    <section
      className={cn("rounded-lg border border-edge-subtle bg-surface-raised p-4", className)}
      data-testid="confidence-breakdown"
    >
      <h3 className="text-xs text-fg-tertiary">置信度构成</h3>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-2xl text-fg-primary">{safeTotal.toFixed(2)}</span>
        <span className="text-xs text-fg-tertiary">综合置信度</span>
      </div>

      {breakdown ? (
        <ul className="mt-3 flex flex-col gap-2">
          {COMPONENTS.map((c) => {
            const v = Number(breakdown[c.key] ?? 0);
            const safe = Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0;
            return (
              <li key={c.key}>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-fg-secondary" title={c.hint}>
                    {c.label} <span className="text-fg-tertiary">×{c.weight}</span>
                  </span>
                  <span className="font-mono text-fg-tertiary">{safe.toFixed(2)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-base">
                  <div
                    className={cn(
                      "h-full rounded-full transition-[width]",
                      safe >= 0.7 ? "bg-risk-low" : safe >= 0.4 ? "bg-risk-medium" : "bg-risk-high",
                    )}
                    style={{ width: `${(safe * 100).toFixed(1)}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-fg-tertiary">
          四分量分解数据未随报告持久化（M4.3 已知边界），暂以总置信度为准。
        </p>
      )}
    </section>
  );
}
