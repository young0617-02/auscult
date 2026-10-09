"use client";

/**
 * useDiagnose（P4-D6）：POST /api/diagnose 发起诊断。
 * 成功后：线程入册（本机注册表）→ toast → 跳转 /diagnosis?thread=<id>。
 * RBAC：engineer/reviewer/sys_admin（后端 _LAUNCH_ROLES 同口径）。
 */

import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { post } from "@/lib/api";
import { useThreads } from "@/lib/store/threads";
import { THREADS_KEY } from "@/hooks/useThread";
import type { AlarmItem } from "@/lib/types/alarm";

interface DiagnoseResp {
  thread_id: string;
  status: string;
}

function toEpochMs(ts: string | number): number {
  return typeof ts === "number" ? ts : Date.parse(ts) || Date.now();
}

export function useDiagnose() {
  const router = useRouter();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alarm: AlarmItem) =>
      post<DiagnoseResp>("/api/diagnose", { alarm_id: alarm.alarm_id }).then((d) => ({ d, alarm })),
    onSuccess: ({ d, alarm }) => {
      useThreads.getState().upsert({
        thread_id: d.thread_id,
        alarm: {
          alarm_id: alarm.alarm_id,
          device_id: alarm.device_id,
          metric: alarm.metric,
          value: alarm.value,
          severity: alarm.severity,
          ts: toEpochMs(alarm.ts),
        },
        status: "running",
        nodes_done: [],
        node_ts: {},
        report_id: null,
        degrade_reason: null,
        error: null,
        created_at: Date.now(),
        updated_at: Date.now(),
      });
      void qc.invalidateQueries({ queryKey: [THREADS_KEY, d.thread_id] });
      toast.success("诊断已发起", { description: `线程 ${d.thread_id}，节点进度实时推送中` });
      router.push(`/diagnosis?thread=${encodeURIComponent(d.thread_id)}`);
    },
    onError: (e) => {
      toast.error("发起诊断失败", { description: (e as Error).message });
    },
  });
}
