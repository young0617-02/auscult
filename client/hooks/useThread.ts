"use client";

/**
 * useThread（P4-D6）：GET /api/threads/{id} 线程详情查询。
 * - 实时态由 socket（SocketProvider → threads store）驱动；本查询提供
 *   qa_log / review_payload / submitter 等富数据，并在 socket 事件后失效刷新
 * - running 态 8s 轮询兜底（socket 丢事件时自愈）
 * 报告详情查询收敛在 hooks/useReports.ts（useReportDetail），M4.3 统一。
 */

import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { ThreadStatusData } from "@/lib/types/thread";

export const THREADS_KEY = "thread";

export function useThread(threadId: string | null) {
  return useQuery<ThreadStatusData>({
    queryKey: [THREADS_KEY, threadId],
    queryFn: () => request<ThreadStatusData>(`/api/threads/${threadId}`),
    enabled: !!threadId,
    refetchInterval: (q) => (q.state.data?.status === "running" ? 8_000 : false),
    placeholderData: (prev) => prev,
    retry: 1,
  });
}
