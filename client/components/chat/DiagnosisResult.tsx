"use client";

/**
 * DiagnosisResult（P4-D9）：diagnosis:done / review:required 的会话内终态消息。
 * - done：置信度徽章 + 风险标签 + 查看报告入口；降级时强制「初步判断」横幅（P2：与正式结论不可混淆）
 * - error：失败通知 + 建议动作
 * - waiting_review：挂起提示 + 审核要点预览（审核操作区在 M4.3 报告工作台）
 */

import Link from "next/link";
import { AlertTriangle, CircleAlert, FileText, ShieldCheck } from "lucide-react";
import { ConfidenceBadge, RiskTag } from "@/components/common/ConfidenceBadge";
import { useReportDetail } from "@/hooks/useReports";
import type { ReviewPayload } from "@/lib/types/thread";

export function DoneMessage({
  reportId,
  degradeReason,
}: {
  reportId: string | null;
  degradeReason: string | null;
}) {
  const { data: report } = useReportDetail(reportId);
  const confidence = report ? Number(report.confidence) : null;
  const risk = report?.risk_level ?? "";

  return (
    <section
      className="rounded-lg border border-edge-subtle bg-surface-raised p-4"
      data-testid="diagnosis-done"
    >
      <div className="flex flex-wrap items-center gap-2">
        <ShieldCheck className="size-4 text-risk-low-text" />
        <span className="text-sm font-medium text-fg-primary">
          {degradeReason ? "诊断完成（初步判断）" : "诊断完成"}
        </span>
        {confidence != null && Number.isFinite(confidence) && <ConfidenceBadge value={confidence} />}
        {risk && <RiskTag level={risk} />}
        {reportId && (
          <Link
            href={`/reports/${reportId}`}
            className="ml-auto inline-flex items-center gap-1 rounded-md border border-edge-subtle px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-surface-base hover:text-fg-primary"
          >
            <FileText className="size-3.5" />
            查看报告
          </Link>
        )}
      </div>

      {degradeReason && (
        <p
          className="mt-3 flex items-start gap-1.5 rounded-md border border-risk-medium-edge bg-risk-medium-surface px-2.5 py-2 text-xs text-risk-medium-text"
          data-testid="degrade-banner"
        >
          <AlertTriangle className="mt-px size-3.5 shrink-0" />
          本报告为降级输出（原因：{degradeReason}），属初步判断，仅供参考，不作为确定结论。
        </p>
      )}
      {!reportId && !degradeReason && (
        <p className="mt-3 text-xs text-fg-tertiary">报告落库稍后可达；若持续未出现请刷新或查看服务日志。</p>
      )}
    </section>
  );
}

export function ErrorMessage({ error }: { error: string | null }) {
  return (
    <section
      className="rounded-lg border border-risk-high-edge bg-risk-high-surface p-4"
      data-testid="diagnosis-error"
    >
      <div className="flex items-center gap-2 text-sm text-risk-high-text">
        <CircleAlert className="size-4 shrink-0" />
        诊断执行失败
      </div>
      <p className="mt-2 break-all font-mono text-xs text-fg-secondary">{error ?? "未知异常"}</p>
      <p className="mt-2 text-xs text-fg-tertiary">建议：确认本地推理/依赖服务可用后，回到告警看板重新发起诊断。</p>
    </section>
  );
}

export function WaitingReviewMessage({ payload }: { payload: ReviewPayload | null }) {
  const confidence = payload?.confidence != null ? Number(payload.confidence) : null;
  const risk = payload?.risk_level ?? "";
  const reasons = payload?.risk_eval?.reasons ?? [];
  return (
    <section
      className="rounded-lg border border-risk-medium-edge bg-risk-medium-surface p-4"
      data-testid="waiting-review"
    >
      <div className="flex flex-wrap items-center gap-2 text-sm text-risk-medium-text">
        <ShieldCheck className="size-4 shrink-0" />
        高风险诊断已挂起，等待人工审核
        {confidence != null && Number.isFinite(confidence) && <ConfidenceBadge value={confidence} />}
        {risk && <RiskTag level={risk} />}
      </div>
      {payload?.diagnosis && (
        <p className="mt-2 line-clamp-4 text-xs leading-5 text-fg-primary">结论预览：{payload.diagnosis}</p>
      )}
      {reasons.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs text-fg-secondary">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-fg-tertiary">
        审核操作入口：报告工作台（报告生成后进入审核队列）。
      </p>
    </section>
  );
}
