/**
 * 线程实时态纯函数（P4-D6/D9）：socket 事件与 REST 水合 → ThreadMeta 不可变更新。
 * 与 alarms-realtime 同模式：逻辑收敛在此，便于单测；store/组件只做调用。
 */

import type { ThreadMeta, ThreadStatusData } from "@/lib/types/thread";

/** diagnosis:progress payload（socket.py _emit_runner_event） */
export interface ProgressPayload {
  node: string;
  nodes_done: string[];
  /** 服务端 time.time()（秒） */
  ts: number;
}

/** diagnosis:done payload（done / error 两态） */
export interface DonePayload {
  status: "done" | "error";
  report_id?: string | null;
  degrade_reason?: string | null;
  error?: string | null;
  ts: number;
}

export function applyProgress(t: ThreadMeta, p: ProgressPayload): ThreadMeta {
  // nodes_done 以服务端权威列表为准（重启回退场景可能比客户端本地多/少节点）
  const done = Array.isArray(p.nodes_done) && p.nodes_done.length > 0 ? p.nodes_done : [...t.nodes_done];
  if (!done.includes(p.node)) done.push(p.node);
  return {
    ...t,
    status: t.status === "running" ? "running" : t.status,
    nodes_done: done,
    node_ts: { ...t.node_ts, [p.node]: p.ts * 1000 },
    updated_at: Date.now(),
  };
}

export function applyDone(t: ThreadMeta, p: DonePayload): ThreadMeta {
  return {
    ...t,
    status: p.status === "done" ? "done" : "error",
    report_id: p.report_id ?? t.report_id,
    degrade_reason: p.degrade_reason ?? t.degrade_reason,
    error: p.error ?? null,
    updated_at: Date.now(),
  };
}

/** waiting_review（review:required 事件 / thread_status 水合） */
export function applyWaitingReview(t: ThreadMeta): ThreadMeta {
  return { ...t, status: "waiting_review", updated_at: Date.now() };
}

/** REST thread_status → ThreadMeta（深链/换浏览器/服务重启后的水合来源） */
export function statusToMeta(d: ThreadStatusData): ThreadMeta {
  const now = Date.now();
  const started = d.started_at ? d.started_at * 1000 : now;
  const alarm = d.alarm ?? {
    alarm_id: "",
    device_id: "未知设备",
    metric: "未知测点",
    value: null,
    severity: "",
    ts: started,
  };
  return {
    thread_id: d.thread_id,
    alarm,
    status: d.status,
    nodes_done: [...(d.nodes_done ?? [])],
    node_ts: {},
    report_id: d.report_id,
    degrade_reason: d.degrade_reason,
    error: d.error,
    created_at: started,
    updated_at: d.finished_at ? d.finished_at * 1000 : started,
  };
}

export type RouteKey = "escalate_cloud" | "degrade" | "human_review" | "finalize";

/** 路由判定：nodes_done 中出现的路由节点（canonical 顺序取最后命中） */
export function deriveRoute(nodesDone: string[]): RouteKey | null {
  const order: RouteKey[] = ["escalate_cloud", "degrade", "human_review", "finalize"];
  let hit: RouteKey | null = null;
  for (const k of order) {
    if (nodesDone.includes(k)) hit = k;
  }
  return hit;
}

/** 当前进行中的主管线节点（running 态下第一个未完成节点） */
export function activeNode(nodesDone: string[]): string | null {
  for (const n of ["parse_alarm", "analyze_sensor", "retrieve_evidence", "get_history", "diagnose"]) {
    if (!nodesDone.includes(n)) return n;
  }
  return null;
}

/**
 * 节点耗时（秒）：下一节点的完成时刻 − 本节点完成时刻；末节点无后继则 null。
 * 入参 nodeTs 值为 epoch ms（由 applyProgress 落）。
 */
export function nodeDurationSec(node: string, nodeTs: Record<string, number>, nodesDone: string[]): number | null {
  const idx = nodesDone.indexOf(node);
  if (idx < 0 || idx === nodesDone.length - 1) return null;
  const next = nodeTs[nodesDone[idx + 1]];
  const cur = nodeTs[node];
  if (next == null || cur == null || next < cur) return null;
  return (next - cur) / 1000;
}
