import { describe, expect, it } from "vitest";
import {
  insertAlarmIntoPage,
  shouldInsert,
} from "@/lib/alarms-realtime";
import type { AlarmItem, AlarmPageData, AlarmQuery } from "@/lib/types/alarm";

function makeAlarm(over: Partial<AlarmItem> = {}): AlarmItem {
  return {
    alarm_id: "a-100",
    device_id: "C 0泵",
    metric: "vib_rms",
    value: 7.2,
    severity: "critical",
    status: "open",
    ts: 1760000000000,
    ...over,
  };
}

function makePage(
  over: Partial<AlarmPageData> = {},
): AlarmPageData {
  return { items: [], total: 0, page: 1, size: 20, ...over };
}

function makeQuery(over: Partial<AlarmQuery> = {}): AlarmQuery {
  return { page: 1, size: 20, ...over };
}

describe("shouldInsert（alarm:new 是否应插入该缓存页）", () => {
  const alarm = makeAlarm();

  it("无筛选且第 1 页 → 插入", () => {
    expect(shouldInsert(alarm, makeQuery())).toBe(true);
  });

  it("非第 1 页 → 不插入（由轮询/重连校正）", () => {
    expect(shouldInsert(alarm, makeQuery({ page: 2 }))).toBe(false);
  });

  it("status 筛选不匹配 → 不插入", () => {
    expect(shouldInsert(alarm, makeQuery({ status: "closed" }))).toBe(false);
  });

  it("status 筛选匹配 → 插入", () => {
    expect(shouldInsert(alarm, makeQuery({ status: "open" }))).toBe(true);
  });

  it("severity 筛选不匹配 → 不插入", () => {
    expect(shouldInsert(alarm, makeQuery({ severity: "warning" }))).toBe(false);
  });

  it("device_id 筛选不匹配 → 不插入", () => {
    expect(
      shouldInsert(alarm, makeQuery({ device_id: "M 2电机" })),
    ).toBe(false);
  });

  it("全部筛选匹配 → 插入", () => {
    expect(
      shouldInsert(
        alarm,
        makeQuery({
          status: "open",
          severity: "critical",
          device_id: "C 0泵",
        }),
      ),
    ).toBe(true);
  });
});

describe("insertAlarmIntoPage（头部插入 + 去重 + 满页截尾）", () => {
  it("空页插入：items=[新告警]，total+1", () => {
    const page = makePage({ total: 5 });
    const alarm = makeAlarm();
    const next = insertAlarmIntoPage(page, alarm);
    expect(next.items).toEqual([alarm]);
    expect(next.total).toBe(6);
  });

  it("未满页：头部插入（ts DESC 最新在前），原数组不被修改", () => {
    const older = makeAlarm({ alarm_id: "a-99", ts: 1759999999000 });
    const page = makePage({ items: [older], total: 1 });
    const alarm = makeAlarm();
    const next = insertAlarmIntoPage(page, alarm);
    expect(next.items.map((i) => i.alarm_id)).toEqual(["a-100", "a-99"]);
    expect(next.total).toBe(2);
    expect(page.items.map((i) => i.alarm_id)).toEqual(["a-99"]); // 不可变性
  });

  it("已存在同 alarm_id：原地更新，total 不变", () => {
    const existing = makeAlarm({ status: "open" });
    const page = makePage({ items: [existing], total: 3 });
    const updated = makeAlarm({ status: "acked" });
    const next = insertAlarmIntoPage(page, updated);
    expect(next.items).toHaveLength(1);
    expect(next.items[0]!.status).toBe("acked");
    expect(next.total).toBe(3);
  });

  it("满页截尾：items 长度不超过 size，新告警在最前，total+1", () => {
    const items = Array.from({ length: 3 }, (_, i) =>
      makeAlarm({ alarm_id: `a-${i}`, ts: 1760000000000 - i * 1000 }),
    );
    const page = makePage({ items, total: 3, size: 3 });
    const alarm = makeAlarm();
    const next = insertAlarmIntoPage(page, alarm);
    expect(next.items).toHaveLength(3);
    expect(next.items[0]!.alarm_id).toBe("a-100");
    expect(next.items.map((i) => i.alarm_id)).not.toContain("a-2"); // 尾部被截
    expect(next.total).toBe(4);
  });
});
