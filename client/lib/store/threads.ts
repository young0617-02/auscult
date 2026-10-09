"use client";

/**
 * 诊断线程注册表（P4-D6）：客户端侧 thread 列表（zustand persist）。
 * 后端无 GET /api/threads 列表契约（单机单人场景，冻结契约不新增）：
 * - 本机发起的诊断经 useDiagnose / socket 事件入册，localStorage 持久化
 * - 深链 /diagnosis?thread=xxx 打开未见过的线程时由 REST thread_status 水合（statusToMeta）
 * - 上限 50 条，超出淘汰最旧
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import {
  applyDone,
  applyProgress,
  applyWaitingReview,
  statusToMeta,
  type DonePayload,
  type ProgressPayload,
} from "@/lib/threads-realtime";
import type { ThreadMeta, ThreadStatusData } from "@/lib/types/thread";

const MAX_THREADS = 50;

interface ThreadsState {
  threads: Record<string, ThreadMeta>;
  /** 最近活跃在前 */
  order: string[];
  upsert: (t: ThreadMeta) => void;
  /** REST 水合：仅当本地未见该线程，或 REST 快照比本地新时才覆盖 */
  hydrateFromStatus: (d: ThreadStatusData) => void;
  applyProgress: (threadId: string, p: ProgressPayload) => void;
  applyDone: (threadId: string, p: DonePayload) => void;
  markWaitingReview: (threadId: string) => void;
  forget: (threadId: string) => void;
}

function upsertOrdered(
  threads: Record<string, ThreadMeta>,
  order: string[],
  t: ThreadMeta,
): Pick<ThreadsState, "threads" | "order"> {
  const nextOrder = [t.thread_id, ...order.filter((id) => id !== t.thread_id)];
  const nextThreads = { ...threads, [t.thread_id]: t };
  // 淘汰最旧（保留最近 MAX_THREADS 条）
  while (nextOrder.length > MAX_THREADS) {
    const dropped = nextOrder.pop();
    if (dropped) delete nextThreads[dropped];
  }
  return { threads: nextThreads, order: nextOrder };
}

export const useThreads = create<ThreadsState>()(
  persist(
    (set) => ({
      threads: {},
      order: [],
      upsert: (t) =>
        set((s) => {
          const existing = s.threads[t.thread_id];
          // 陈旧快照不覆盖新鲜 socket 态（updated_at 单调）
          if (existing && existing.updated_at > t.updated_at) return s;
          return upsertOrdered(s.threads, s.order, t);
        }),
      hydrateFromStatus: (d) =>
        set((s) => {
          const meta = statusToMeta(d);
          const existing = s.threads[d.thread_id];
          if (existing && existing.updated_at > meta.updated_at) return s;
          return upsertOrdered(s.threads, s.order, meta);
        }),
      applyProgress: (threadId, p) =>
        set((s) => {
          const t = s.threads[threadId];
          if (!t) return s;
          return upsertOrdered(s.threads, s.order, applyProgress(t, p));
        }),
      applyDone: (threadId, p) =>
        set((s) => {
          const t = s.threads[threadId];
          if (!t) return s;
          return upsertOrdered(s.threads, s.order, applyDone(t, p));
        }),
      markWaitingReview: (threadId) =>
        set((s) => {
          const t = s.threads[threadId];
          if (!t) return s;
          return upsertOrdered(s.threads, s.order, applyWaitingReview(t));
        }),
      forget: (threadId) =>
        set((s) => {
          if (!s.threads[threadId]) return s;
          const threads = { ...s.threads };
          delete threads[threadId];
          return { threads, order: s.order.filter((id) => id !== threadId) };
        }),
    }),
    {
      name: "auscult-threads",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ threads: s.threads, order: s.order }),
    },
  ),
);
