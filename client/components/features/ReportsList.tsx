"use client";

/**
 * 报告列表（P4-D11）：状态/风险筛选 + 分页 + 严重度与审核状态徽章。
 * 报告 = finalize 落库的产出；review_status NULL → 前端语义「待审核」。
 */

import { useCallback } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FileText } from "lucide-react";
import { PageScaffold, KpiCard } from "@/components/layout/PageScaffold";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useReports } from "@/hooks/useReports";
import {
  normalizeReviewStatus,
  REVIEW_STATUS_LABEL,
  REVIEW_STATUS_TONE,
  RISK_LABEL,
  type ReportListItem,
  type ReportQuery,
} from "@/lib/types/report";
import { RiskTag } from "@/components/common/ConfidenceBadge";
import { cn } from "cn";

const PAGE_SIZE = 20;

export function ReportsList() {
  const router = useRouter();
  const sp = useSearchParams();

  const query: ReportQuery = {
    page: Number(sp.get("page") ?? 1) || 1,
    size: PAGE_SIZE,
    status: sp.get("status") || undefined,
    risk: sp.get("risk") || undefined,
  };
  const { data, isPending, isError, error } = useReports(query);

  const setParam = useCallback(
    (patch: Record<string, string | undefined>) => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === "") next.delete(k);
        else next.set(k, v);
      }
      if (!("page" in patch)) next.set("page", "1");
      router.replace(`/reports?${next.toString()}`, { scroll: false });
    },
    [router, sp],
  );

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const pendingCount = data?.items.filter((i) => i.review_status === null).length ?? 0;

  return (
    <PageScaffold
      title="报告工作台"
      description="报告列表 + 详情（审核内嵌于详情页）"
      toolbar={
        <div className="flex items-center gap-2">
          <Select
            value={sp.get("status") ?? "all"}
            onValueChange={(v) => setParam({ status: v === "all" ? undefined : v })}
          >
            <SelectTrigger size="sm" className="w-32" aria-label="审核状态筛选">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="pending">待审核</SelectItem>
              <SelectItem value="approved">已通过</SelectItem>
              <SelectItem value="rejected">已驳回</SelectItem>
              <SelectItem value="timeout">已超时</SelectItem>
              <SelectItem value="auto_approved">自动通过</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={sp.get("risk") ?? "all"}
            onValueChange={(v) => setParam({ risk: v === "all" ? undefined : v })}
          >
            <SelectTrigger size="sm" className="w-28" aria-label="风险等级筛选">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部风险</SelectItem>
              <SelectItem value="high">高风险</SelectItem>
              <SelectItem value="medium">中风险</SelectItem>
              <SelectItem value="low">低风险</SelectItem>
            </SelectContent>
          </Select>
        </div>
      }
      kpis={
        <div className="grid grid-cols-4 gap-3">
          <KpiCard label="当前筛选报告" value={data?.total ?? 0} />
          <KpiCard label="本页待审核" value={pendingCount} tone={pendingCount > 0 ? "medium" : "default"} />
          <KpiCard label="高风险（本页）" value={data?.items.filter((i) => i.risk_level === "high").length ?? 0} tone="high" />
          <KpiCard label="降级（本页）" value={data?.items.filter((i) => i.degrade_reason).length ?? 0} tone="medium" />
        </div>
      }
    >
      {isPending && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <EmptyState icon={FileText} title="报告列表加载失败" reason={`${(error as Error).message}（请刷新重试）`} />
      )}

      {data && data.items.length === 0 && (
        <EmptyState
          icon={FileText}
          title="暂无报告"
          reason="为什么空：尚无完成的诊断落库，或筛选条件过滤了全部记录。诊断完成后报告在此排队；高风险报告需人工审核。"
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <ul className="flex flex-col gap-2" data-testid="report-list">
            {data.items.map((r) => (
              <ReportRow key={r.report_id} report={r} />
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-end gap-2 text-xs text-fg-secondary">
            <span className="font-mono">
              第 {data.page} / {totalPages} 页 · 共 {data.total} 条
            </span>
            <Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => setParam({ page: String(data.page - 1) })}>
              上一页
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={data.page >= totalPages}
              onClick={() => setParam({ page: String(data.page + 1) })}
            >
              下一页
            </Button>
          </div>
        </>
      )}
    </PageScaffold>
  );
}

function ReportRow({ report }: { report: ReportListItem }) {
  const status = normalizeReviewStatus(report.review_status);
  const confidence = Number(report.confidence);
  const degraded = !!report.degrade_reason;
  return (
    <li>
      <Link
        href={`/reports/${report.report_id}`}
        className={cn(
          "flex items-stretch gap-3 overflow-hidden rounded-lg border border-edge-subtle bg-surface-raised pr-4 transition-colors hover:border-edge-strong",
          degraded && "border-risk-medium-edge",
        )}
        data-testid={`report-row-${report.report_id}`}
      >
        <span
          className={cn(
            "w-1 shrink-0",
            report.risk_level === "high" ? "bg-risk-high" : report.risk_level === "medium" ? "bg-risk-medium" : "bg-risk-low",
          )}
          aria-hidden
        />
        <div className="flex min-w-0 flex-1 items-center gap-3 py-2.5">
          <RiskTag level={report.risk_level} />
          <div className="min-w-0">
            <div className="truncate text-sm text-fg-primary">{report.diagnosis ?? "(无诊断结论)"}</div>
            <div className="mt-0.5 flex items-center gap-2 text-xs text-fg-tertiary">
              <span className="font-mono">{report.report_id}</span>
              {degraded && <span className="text-risk-medium-text">降级：{report.degrade_reason}</span>}
            </div>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-3">
            <span className="font-mono text-sm text-fg-primary">
              {Number.isFinite(confidence) ? confidence.toFixed(2) : "—"}
            </span>
            <span className={cn("rounded-full border px-2 py-0.5 text-xs", REVIEW_STATUS_TONE[status])} data-testid={`review-status-${report.report_id}`}>
              {REVIEW_STATUS_LABEL[status]}
            </span>
            <time className="font-mono text-xs text-fg-tertiary" dateTime={report.created_at}>
              {new Date(report.created_at).toLocaleString("zh-CN", { hour12: false })}
            </time>
          </div>
        </div>
      </Link>
    </li>
  );
}

/** RISK_LABEL 供详情页复用（避免重复映射） */
export { RISK_LABEL };
