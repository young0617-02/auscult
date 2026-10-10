"use client";

/**
 * 报告详情（P4-D11）：结论 + 根因（citations 锚点）+ 建议（risk）+ 审核状态 + 降级横幅。
 * 审核操作区由 D13 的 ReviewActions 组件承载；置信度 breakdown 由 D12 组件承载。
 *
 * P5-Q8：payload 已补持久化 evidence 原文与 confidence_breakdown，
 * 详情页新增「证据原文」区块（标注载体），四分量分解已接通；历史报告无该字段时降级隐藏。
 * 降级报告顶部强制「初步判断」横幅（P2）。
 */

import { AlertTriangle, ArrowLeft, Share2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { PageScaffold } from "@/components/layout/PageScaffold";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfidenceBadge, RiskTag } from "@/components/common/ConfidenceBadge";
import { ConfidenceBreakdown } from "@/components/common/ConfidenceBreakdown";
import { EvidenceChip } from "@/components/common/EvidenceCard";
import { TraceTimeline } from "@/components/common/TraceTimeline";
import { useReportDetail } from "@/hooks/useReports";
import { useThread } from "@/hooks/useThread";
import {
  normalizeReviewStatus,
  REVIEW_STATUS_LABEL,
  REVIEW_STATUS_TONE,
  type ReportDetailData,
} from "@/lib/types/report";
import { FileText } from "lucide-react";
import { cn } from "cn";
import { ReviewActions } from "@/components/review/ReviewActions";

export function ReportDetail({ reportId }: { reportId: string }) {
  const { data, isPending, isError, error } = useReportDetail(reportId);

  return (
    <PageScaffold
      title="报告详情"
      description={`报告 ${reportId}`}
      toolbar={
        <Link
          href="/reports"
          className="inline-flex items-center gap-1 rounded-md border border-edge-subtle px-2.5 py-1 text-xs text-fg-secondary transition-colors hover:bg-surface-raised hover:text-fg-primary"
        >
          <ArrowLeft className="size-3.5" />
          返回列表
        </Link>
      }
    >
      {isPending && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}

      {isError && (
        <EmptyState icon={FileText} title="报告加载失败" reason={`${(error as Error).message}`} />
      )}

      {data && <ReportBody report={data} />}
    </PageScaffold>
  );
}

function ReportBody({ report }: { report: ReportDetailData }) {
  const status = normalizeReviewStatus(report.review_status);
  const payload = report.payload;
  const confidence = Number(report.confidence);
  const degraded = !!report.degrade_reason;
  // D18：线程富数据（Trace 时间线 + 图谱联动的起始实体）
  const { data: thread } = useThread(report.thread_id);
  const graphEntity = thread?.alarm?.device_id ?? null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      {/* 头部：风险 / 置信度 / 审核状态 / 时间 */}
      <div className="flex flex-wrap items-center gap-2">
        <RiskTag level={report.risk_level} />
        <ConfidenceBadge value={Number.isFinite(confidence) ? confidence : 0} />
        <span
          className={cn("rounded-full border px-2 py-0.5 text-xs", REVIEW_STATUS_TONE[status])}
          data-testid="report-review-status"
        >
          {REVIEW_STATUS_LABEL[status]}
        </span>
        <span className="ml-auto font-mono text-xs text-fg-tertiary">{report.report_id}</span>
        <time className="font-mono text-xs text-fg-tertiary" dateTime={report.created_at ?? undefined}>
          {report.created_at ? new Date(report.created_at).toLocaleString("zh-CN", { hour12: false }) : "—"}
        </time>
      </div>

      {/* 降级横幅（P2：初步判断必须与正式结论不可混淆） */}
      {degraded && (
        <p
          className="flex items-start gap-1.5 rounded-md border border-risk-medium-edge bg-risk-medium-surface px-3 py-2 text-xs text-risk-medium-text"
          data-testid="report-degrade-banner"
        >
          <AlertTriangle className="mt-px size-3.5 shrink-0" />
          本报告为降级输出（原因：{report.degrade_reason}），属初步判断，仅供参考，不作为确定结论。
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
        <div className="flex min-w-0 flex-col gap-4">
          {/* 诊断结论 */}
          <Section title="诊断结论" testid="report-diagnosis">
            <p className="whitespace-pre-wrap text-sm leading-6 text-fg-primary">
              {payload.diagnosis ?? "(无诊断结论)"}
            </p>
          </Section>

          {/* 根因 */}
          <Section title={`根因（${payload.root_causes.length}）`} testid="report-root-causes">
            {payload.root_causes.length === 0 ? (
              <p className="text-xs text-fg-tertiary">无根因结论（可能因降级或证据不足）。</p>
            ) : (
              <ol className="flex flex-col gap-2.5">
                {payload.root_causes.map((rc, i) => (
                  <li key={i} className="rounded-md border border-edge-subtle bg-surface-base px-3 py-2">
                    <p className="text-xs leading-5 text-fg-primary">
                      {i + 1}. {rc.cause}
                    </p>
                    {rc.citations.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {rc.citations.map((c) => (
                          <EvidenceChip key={c} chunkId={c} />
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Section>

          {/* 建议 */}
          <Section title={`建议（${payload.suggestions.length}）`} testid="report-suggestions">
            {payload.suggestions.length === 0 ? (
              <p className="text-xs text-fg-tertiary">无建议。</p>
            ) : (
              <ol className="flex flex-col gap-2.5">
                {payload.suggestions.map((s, i) => (
                  <li key={i} className="rounded-md border border-edge-subtle bg-surface-base px-3 py-2">
                    <div className="flex items-center gap-2">
                      <p className="min-w-0 flex-1 text-xs leading-5 text-fg-primary">
                        {i + 1}. {s.action}
                      </p>
                      <RiskTag level={s.risk} />
                    </div>
                    {s.citations.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {s.citations.map((c) => (
                          <EvidenceChip key={c} chunkId={c} />
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Section>

          {/* 证据原文（P5-Q8 持久化；历史报告无此字段则整块隐藏） */}
          {payload.evidence && payload.evidence.length > 0 && (
            <Section title={`证据原文（${payload.evidence.length}）`} testid="report-evidence">
              <ol className="flex flex-col gap-2.5">
                {payload.evidence.map((ev) => (
                  <li key={ev.chunk_id} className="rounded-md border border-edge-subtle bg-surface-base px-3 py-2">
                    <div className="flex items-center gap-2">
                      <EvidenceChip chunkId={ev.chunk_id} />
                      <span className="font-mono text-[11px] text-fg-tertiary">
                        score={Number(ev.score).toFixed(3)} · {ev.source_type}
                      </span>
                    </div>
                    <p className="mt-1.5 whitespace-pre-wrap text-xs leading-5 text-fg-secondary">
                      {ev.text}
                    </p>
                  </li>
                ))}
              </ol>
            </Section>
          )}

          {/* 审核留痕 */}
          {payload.human_review && (
            <Section title="审核记录" testid="report-human-review">
              <div className="flex items-center gap-2 text-xs text-fg-secondary">
                <ShieldCheck className="size-3.5 text-fg-tertiary" />
                <span>
                  {payload.human_review.status ?? payload.human_review.decision ?? "—"}
                  {payload.human_review.reviewer_id ? ` · ${payload.human_review.reviewer_id}` : ""}
                </span>
              </div>
              {payload.human_review.comment && (
                <p className="mt-1.5 whitespace-pre-wrap text-xs leading-5 text-fg-primary">
                  {payload.human_review.comment}
                </p>
              )}
            </Section>
          )}
        </div>

        {/* 右栏：置信度 breakdown + 审核操作区 + Trace/图谱联动（D18） */}
        <aside className="flex flex-col gap-4">
          <ConfidenceBreakdown breakdown={payload.confidence_breakdown ?? null} total={confidence} />
          <ReviewActions report={report} />

          {/* D18：报告→图谱联动（以告警设备为起始实体载入） */}
          {graphEntity && (
            <Link
              href={`/graph?entity=${encodeURIComponent(graphEntity)}`}
              className="flex items-center justify-center gap-1.5 rounded-md border border-edge-subtle bg-surface-raised px-3 py-2 text-xs text-fg-secondary transition-colors hover:border-edge-strong hover:text-fg-primary"
              data-testid="report-graph-link"
            >
              <Share2 className="size-3.5" />
              从当前报告载入图谱（{graphEntity}）
            </Link>
          )}

          {/* D18：Trace 时间线（节点序列 + 总耗时 + thread_id） */}
          <section className="rounded-lg border border-edge-subtle bg-surface-raised p-4" data-testid="report-trace">
            <h3 className="text-xs text-fg-tertiary">Trace 时间线</h3>
            <div className="mt-2">
              {thread ? (
                <TraceTimeline thread={thread} traceId={report.idempotency_key} />
              ) : (
                <p className="text-xs text-fg-tertiary">线程信息加载中…</p>
              )}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function Section({
  title,
  testid,
  children,
}: {
  title: string;
  testid: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="rounded-lg border border-edge-subtle bg-surface-raised p-4"
      data-testid={testid}
    >
      <h3 className="text-xs text-fg-tertiary">{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  );
}
