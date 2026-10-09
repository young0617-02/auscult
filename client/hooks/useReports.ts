"use client";

/**
 * useReports（P4-D11）：GET /api/reports 列表；useReportDetail（D11）：详情。
 * useReviewSubmit（D13）：POST /api/reports/{id}/review（契约补丁别名，reviewer 专属）。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { post, request } from "@/lib/api";
import type { ReportDetailData, ReportListData, ReportQuery } from "@/lib/types/report";

export const REPORTS_KEY = "reports";
export const REPORT_DETAIL_KEY = "report-detail";

function buildQueryString(q: ReportQuery): string {
  const sp = new URLSearchParams({ page: String(q.page), size: String(q.size) });
  if (q.status) sp.set("status", q.status);
  if (q.risk) sp.set("risk", q.risk);
  return sp.toString();
}

export function useReports(query: ReportQuery) {
  return useQuery<ReportListData>({
    queryKey: [REPORTS_KEY, query],
    queryFn: () => request<ReportListData>(`/api/reports?${buildQueryString(query)}`),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });
}

export function useReportDetail(reportId: string | null) {
  return useQuery<ReportDetailData>({
    queryKey: [REPORT_DETAIL_KEY, reportId],
    queryFn: () => request<ReportDetailData>(`/api/reports/${reportId}`),
    enabled: !!reportId,
    staleTime: 10_000,
  });
}

// ---------------------------------------------------------------- 审核提交（D13）

interface ReviewResp {
  status: string;
  report_id?: string;
  degrade_reason?: string | null;
  human_review?: Record<string, unknown>;
}

/** POST /api/reports/{id}/review（契约补丁别名；后端二次校验 reviewer/SoD/锁/等待态） */
export function useReviewSubmit(reportId: string | null, threadId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { action: "approved" | "rejected"; comment: string }) =>
      post<ReviewResp>(`/api/reports/${reportId}/review`, input),
    onSuccess: () => {
      // 审核完成 → 报告详情 + 列表 + 线程详情全部失效（等待 finalize 落库后视图同步）
      void qc.invalidateQueries({ queryKey: [REPORTS_KEY] });
      void qc.invalidateQueries({ queryKey: [REPORT_DETAIL_KEY, reportId] });
      if (threadId) void qc.invalidateQueries({ queryKey: ["thread", threadId] });
      toast.success("审核已提交", { description: "报告状态将在 finalize 落库后更新" });
    },
    onError: (e) => {
      toast.error("审核提交失败", { description: (e as Error).message });
    },
  });
}
