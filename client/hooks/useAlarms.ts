"use client";

/**
 * useAlarms（P4-D4）：GET /api/alarms 列表查询。
 * 缓存键含全部筛选参数；D5 的 alarm:new 事件将定向 setQueryData 插入，
 * 断线重连后 invalidateQueries 全量校正。
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "@/lib/api";
import type { AlarmPageData, AlarmQuery } from "@/lib/types/alarm";

export const ALARMS_KEY = "alarms";

export function buildQueryString(q: AlarmQuery): string {
  const sp = new URLSearchParams({
    page: String(q.page),
    size: String(q.size),
  });
  if (q.status) sp.set("status", q.status);
  if (q.severity) sp.set("severity", q.severity);
  if (q.device_id) sp.set("device_id", q.device_id);
  return sp.toString();
}

export function useAlarms(query: AlarmQuery) {
  return useQuery<AlarmPageData>({
    queryKey: [ALARMS_KEY, query],
    queryFn: () => request<AlarmPageData>(`/api/alarms?${buildQueryString(query)}`),
    // 告警流实时性要求高：15s 内允许复用，30s 轮询兜底（socket 为主通道）
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });
}

/** 供 Socket 层定向更新缓存使用 */
export function useAlarmsCache() {
  const qc = useQueryClient();
  return {
    invalidate: () => qc.invalidateQueries({ queryKey: [ALARMS_KEY] }),
  };
}
