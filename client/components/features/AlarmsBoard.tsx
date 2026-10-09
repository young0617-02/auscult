"use client";

/**
 * 告警看板装配层（P4-D4）：筛选写入 URL（可分享/可回放，§10.2）+ 分页 + 严重度可视化。
 * alarm:new 实时插入由 D5 的 SocketProvider 定向更新本页缓存。
 */

import { useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Bell } from "lucide-react";
import { PageScaffold, KpiCard } from "@/components/layout/PageScaffold";
import { EmptyState } from "@/components/common/EmptyState";
import { AlarmCard } from "@/components/domain/AlarmCard";
import { useAlarms } from "@/hooks/useAlarms";
import { useDiagnose } from "@/hooks/useDiagnose";
import { hasRole, useAuth } from "@/lib/auth";
import type { AlarmQuery } from "@/lib/types/alarm";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

const PAGE_SIZE = 20;

export function AlarmsBoard() {
  const router = useRouter();
  const sp = useSearchParams();

  const query: AlarmQuery = {
    page: Number(sp.get("page") ?? 1) || 1,
    size: PAGE_SIZE,
    status: sp.get("status") || undefined,
    severity: sp.get("severity") || undefined,
    device_id: sp.get("device_id") || undefined,
  };

  const { data, isPending, isError, error } = useAlarms(query);

  // 发起诊断入口（后端 _LAUNCH_ROLES 同口径；kb_admin 只读）
  const user = useAuth((s) => s.user);
  const canDiagnose = hasRole(user, ["engineer", "reviewer", "sys_admin"]);
  const diagnose = useDiagnose();

  const setParam = useCallback(
    (patch: Record<string, string | undefined>) => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === "") next.delete(k);
        else next.set(k, v);
      }
      // 筛选变更回第一页（page 显式带上，避免残留旧页码）
      if (!("page" in patch)) next.set("page", "1");
      router.replace(`/alarms?${next.toString()}`, { scroll: false });
    },
    [router, sp],
  );

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;

  return (
    <PageScaffold
      title="告警看板"
      description="告警由解码器写入 alerts 表后经 alarm:new 实时推送（D5 接入）"
      toolbar={
        <div className="flex items-center gap-2">
          <Select
            value={sp.get("severity") ?? "all"}
            onValueChange={(v) => setParam({ severity: v === "all" ? undefined : v })}
          >
            <SelectTrigger size="sm" className="w-28" aria-label="严重度筛选">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部严重度</SelectItem>
              <SelectItem value="critical">高</SelectItem>
              <SelectItem value="warning">中</SelectItem>
              <SelectItem value="info">低</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={sp.get("status") ?? "all"}
            onValueChange={(v) => setParam({ status: v === "all" ? undefined : v })}
          >
            <SelectTrigger size="sm" className="w-28" aria-label="状态筛选">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="open">活跃</SelectItem>
              <SelectItem value="acked">已确认</SelectItem>
              <SelectItem value="closed">已关闭</SelectItem>
            </SelectContent>
          </Select>

          <Input
            placeholder="设备 ID"
            className="h-7 w-32 text-xs"
            defaultValue={sp.get("device_id") ?? ""}
            onBlur={(e) => setParam({ device_id: e.target.value || undefined })}
            aria-label="设备 ID 筛选"
          />
        </div>
      }
      kpis={
        <div className="grid grid-cols-5 gap-3">
          <KpiCard label="当前筛选告警" value={data?.total ?? 0} />
          <KpiCard label="已去重合并" value={0} />
          <KpiCard label="今日已诊断" value={0} />
          <KpiCard label="待审核" value={0} tone="medium" />
          <KpiCard label="降级态" value={0} tone="high" />
        </div>
      }
    >
      {isPending && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <EmptyState
          icon={Bell}
          title="告警列表加载失败"
          reason={`${(error as Error).message}（请刷新重试）`}
        />
      )}

      {data && data.items.length === 0 && (
        <EmptyState
          icon={Bell}
          title="当前无告警"
          reason="为什么空：解码器尚未写入告警，或筛选条件过滤了全部记录。新告警到达时将置顶插入并高亮脉冲 3s。"
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="flex flex-col gap-2">
            {data.items.map((alarm) => (
              <AlarmCard
                key={alarm.alarm_id}
                alarm={alarm}
                action={
                  canDiagnose ? (
                    <Button
                      size="sm"
                      variant="outline"
                      data-testid={`diagnose-btn-${alarm.alarm_id}`}
                      disabled={diagnose.isPending}
                      onClick={() => diagnose.mutate(alarm)}
                    >
                      发起诊断
                    </Button>
                  ) : undefined
                }
              />
            ))}
          </div>
          <div className="mt-4 flex items-center justify-end gap-2 text-xs text-fg-secondary">
            <span className="font-mono">
              第 {data.page} / {totalPages} 页 · 共 {data.total} 条
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={data.page <= 1}
              onClick={() => setParam({ page: String(data.page - 1) })}
            >
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
