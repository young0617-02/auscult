/** threads-realtime 纯函数单测（P4-D6/D9）：进度推进 / 终态 / 水合 / 路由与耗时推导 */

import { describe, expect, it } from "vitest";
import {
  activeNode,
  applyDone,
  applyProgress,
  applyWaitingReview,
  deriveRoute,
  nodeDurationSec,
  statusToMeta,
} from "@/lib/threads-realtime";
import type { ThreadMeta } from "@/lib/types/thread";

function baseThread(over: Partial<ThreadMeta> = {}): ThreadMeta {
  return {
    thread_id: "thr-test",
    alarm: {
      alarm_id: "ALM-1",
      device_id: "PUMP-A",
      metric: "vib_rms",
      value: 7.8,
      severity: "critical",
      ts: 1_700_000_000_000,
    },
    status: "running",
    nodes_done: [],
    node_ts: {},
    report_id: null,
    degrade_reason: null,
    error: null,
    created_at: 1_700_000_000_000,
    updated_at: 1_700_000_000_000,
    ...over,
  };
}

describe("applyProgress", () => {
  it("追加节点并落 node_ts（服务端秒→ms）", () => {
    const next = applyProgress(baseThread(), { node: "parse_alarm", nodes_done: ["parse_alarm"], ts: 1000.5 });
    expect(next.nodes_done).toEqual(["parse_alarm"]);
    expect(next.node_ts["parse_alarm"]).toBe(1_000_500);
    expect(next.status).toBe("running");
  });

  it("以服务端权威 nodes_done 为准并去重本地重复", () => {
    const t = baseThread({ nodes_done: ["parse_alarm"] });
    const next = applyProgress(t, {
      node: "parse_alarm",
      nodes_done: ["parse_alarm", "analyze_sensor"],
      ts: 1002,
    });
    expect(next.nodes_done).toEqual(["parse_alarm", "analyze_sensor"]);
  });

  it("终态后不再回退 running", () => {
    const t = baseThread({ status: "done" });
    const next = applyProgress(t, { node: "parse_alarm", nodes_done: ["parse_alarm"], ts: 1000 });
    expect(next.status).toBe("done");
  });
});

describe("applyDone", () => {
  it("done：写入 report_id 与 degrade_reason", () => {
    const next = applyDone(baseThread(), {
      status: "done",
      report_id: "RPT-abc",
      degrade_reason: null,
      ts: 1010,
    });
    expect(next.status).toBe("done");
    expect(next.report_id).toBe("RPT-abc");
    expect(next.error).toBeNull();
  });

  it("error：error 字段落位，report_id 保留原值", () => {
    const next = applyDone(baseThread({ report_id: null }), {
      status: "error",
      error: "E_UPSTREAM: 本地推理暂不可用",
      ts: 1010,
    });
    expect(next.status).toBe("error");
    expect(next.error).toContain("E_UPSTREAM");
  });
});

describe("applyWaitingReview", () => {
  it("置 waiting_review 态", () => {
    expect(applyWaitingReview(baseThread()).status).toBe("waiting_review");
  });
});

describe("statusToMeta（REST 水合）", () => {
  it("完整字段映射（epoch 秒→ms）", () => {
    const meta = statusToMeta({
      thread_id: "thr-x",
      status: "done",
      submitter: "eng_dev",
      alarm: { alarm_id: "A1", device_id: "D1", metric: "m", value: 1, severity: "high", ts: 0 },
      nodes_done: ["parse_alarm", "finalize"],
      report_id: "RPT-1",
      review_payload: null,
      degrade_reason: "review_timeout",
      qa_log: [],
      error: null,
      started_at: 1000,
      finished_at: 1060,
    });
    expect(meta.created_at).toBe(1_000_000);
    expect(meta.updated_at).toBe(1_060_000);
    expect(meta.alarm.device_id).toBe("D1");
    expect(meta.degrade_reason).toBe("review_timeout");
  });

  it("alarm 缺失（重启回退态）时给中性兜底，不渲染裸 null", () => {
    const meta = statusToMeta({
      thread_id: "thr-y",
      status: "waiting_review",
      submitter: null,
      alarm: null,
      nodes_done: [],
      report_id: null,
      review_payload: null,
      degrade_reason: null,
      qa_log: [],
      error: null,
      started_at: null,
      finished_at: null,
    });
    expect(meta.alarm.device_id).toBe("未知设备");
    expect(meta.alarm.value).toBeNull();
  });
});

describe("deriveRoute / activeNode / nodeDurationSec", () => {
  it("路由取 canonical 顺序最后命中（human_review→finalize 序列）", () => {
    expect(deriveRoute(["diagnose", "human_review"])).toBe("human_review");
    expect(deriveRoute(["diagnose", "human_review", "finalize"])).toBe("finalize");
    expect(deriveRoute(["diagnose", "degrade", "finalize"])).toBe("finalize");
    expect(deriveRoute(["parse_alarm"])).toBeNull();
  });

  it("activeNode 返回第一个未完成管线节点", () => {
    expect(activeNode([])).toBe("parse_alarm");
    expect(activeNode(["parse_alarm", "analyze_sensor"])).toBe("retrieve_evidence");
    expect(activeNode(["parse_alarm", "analyze_sensor", "retrieve_evidence", "get_history", "diagnose"])).toBeNull();
  });

  it("节点耗时 = 后继完成时刻差；末节点为 null", () => {
    const nodeTs = { parse_alarm: 1000, analyze_sensor: 2500 };
    const done = ["parse_alarm", "analyze_sensor"];
    expect(nodeDurationSec("parse_alarm", nodeTs, done)).toBe(1.5);
    expect(nodeDurationSec("analyze_sensor", nodeTs, done)).toBeNull();
    expect(nodeDurationSec("retrieve_evidence", nodeTs, done)).toBeNull();
  });
});
