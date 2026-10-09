"use client";

/**
 * SocketProvider（P4-D5）：Socket.IO 事件消费唯一入口（UI 方案 §10.2）。
 * - 登录态变化驱动连接建立 / 销毁（token 由 connect auth 携带，后端拒连无效会话）
 * - alarm:new → 未读数 +1，并定向插入「第 1 页且筛选匹配」的告警缓存
 * - 重连成功 → invalidateQueries 全量校正（重连窗口可能漏事件）
 * - review:required → 低打扰 toast（右上角）
 * - 连接状态写入 useConn 供 TopStatusBar / ConnectionBanner / D14 审核消费
 */

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { closeSocket, getSocket, type AlarmNewPayload } from "@/lib/socket";
import { useAuth } from "@/lib/auth";
import { useConn } from "@/lib/store/connection";
import { useThreads } from "@/lib/store/threads";
import { ALARMS_KEY } from "@/hooks/useAlarms";
import { THREADS_KEY } from "@/hooks/useThread";
import { REPORTS_KEY } from "@/hooks/useReports";
import { insertAlarmIntoPage, shouldInsert } from "@/lib/alarms-realtime";
import type { AlarmItem, AlarmPageData, AlarmQuery } from "@/lib/types/alarm";

export function SocketProvider({ children }: { children: React.ReactNode }) {
  const token = useAuth((s) => s.token);
  const hydrated = useAuth((s) => s.hydrated);
  const qc = useQueryClient();

  useEffect(() => {
    if (!hydrated) return;
    if (!token) {
      closeSocket();
      useConn.getState().setStatus("disconnected");
      return;
    }

    const conn = useConn.getState();
    const socket = getSocket(token);

    const onConnect = () => {
      conn.setStatus("connected");
      conn.setAttempt(0);
      // 首连或重连成功都全量校正一次（幂等，仅标记过期不强制网络风暴）
      void qc.invalidateQueries({ queryKey: [ALARMS_KEY] });
    };
    const onDisconnect = () => conn.setStatus("disconnected");
    const onReconnectAttempt = (n: number) => {
      conn.setAttempt(n);
      conn.setStatus("connecting");
    };
    const onAlarmNew = (payload: AlarmNewPayload) => {
      conn.bumpUnread();
      // epoch ms → AlarmItem（ts 理论非空，兜底取当前时间）
      const alarm: AlarmItem = { ...payload, ts: payload.ts ?? Date.now() };
      // 遍历告警缓存逐页定向插入（v5 setQueriesData 谓词形式拿不到 queryKey）
      const queries = qc.getQueryCache().findAll({ queryKey: [ALARMS_KEY] });
      for (const q of queries) {
        qc.setQueryData<AlarmPageData>(q.queryKey, (page) => {
          if (!page) return page;
          const queryParams = q.queryKey[1] as AlarmQuery;
          if (!shouldInsert(alarm, queryParams)) return page;
          return insertAlarmIntoPage(page, alarm);
        });
      }
    };
    const onReviewRequired = (p: { thread_id?: string }) => {
      if (p.thread_id) useThreads.getState().markWaitingReview(p.thread_id);
      // 报告列表可能含 pending 项（等审核中），失效以触发刷新
      void qc.invalidateQueries({ queryKey: [REPORTS_KEY] });
      toast.warning("高风险诊断待审核", {
        description: p.thread_id
          ? `线程 ${p.thread_id} 已挂起，请前往审核队列处理`
          : "有诊断已挂起，请前往审核队列处理",
      });
    };
    // D6/D9：诊断节点进度 → 线程注册表（诊断页订阅渲染节点流）
    const onProgress = (p: {
      thread_id: string;
      node: string;
      nodes_done: string[];
      ts: number;
    }) => {
      useThreads.getState().applyProgress(p.thread_id, p);
    };
    // D9：诊断终态 → 注册表 + 线程详情查询失效（拉 qa_log/report 引用）
    const onDone = (p: {
      thread_id: string;
      status: "done" | "error";
      report_id?: string | null;
      degrade_reason?: string | null;
      error?: string;
      ts: number;
    }) => {
      useThreads.getState().applyDone(p.thread_id, p);
      void qc.invalidateQueries({ queryKey: [THREADS_KEY, p.thread_id] });
      if (p.status === "error") {
        toast.error("诊断执行失败", { description: p.error ?? "执行异常，请到诊断控制台查看详情" });
      }
    };

    socket.on("connect", onConnect);
    socket.on("disconnect", onDisconnect);
    socket.io.on("reconnect_attempt", onReconnectAttempt);
    socket.on("alarm:new", onAlarmNew);
    socket.on("review:required", onReviewRequired);
    socket.on("diagnosis:progress", onProgress);
    socket.on("diagnosis:done", onDone);

    // token 未变的重挂载（StrictMode 双执行）：已连接则直接对齐状态，防卡 connecting
    if (socket.connected) onConnect();
    else conn.setStatus("connecting");

    return () => {
      socket.off("connect", onConnect);
      socket.off("disconnect", onDisconnect);
      socket.io.off("reconnect_attempt", onReconnectAttempt);
      socket.off("alarm:new", onAlarmNew);
      socket.off("review:required", onReviewRequired);
      socket.off("diagnosis:progress", onProgress);
      socket.off("diagnosis:done", onDone);
    };
  }, [token, hydrated, qc]);

  return <>{children}</>;
}
