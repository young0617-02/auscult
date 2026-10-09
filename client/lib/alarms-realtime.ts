/**
 * alarm:new 实时插入缓存（D5，纯函数供单测）。
 * 规则：只定向插入「筛选匹配且位于第 1 页」的缓存页（ts DESC 最新在前）；
 * 非首页 / 筛选不匹配的缓存由 30s 轮询 + 重连 invalidate 兜底校正。
 */

import type { AlarmItem, AlarmPageData, AlarmQuery } from "@/lib/types/alarm";

/** 新告警是否应插入该查询参数对应的第一页缓存 */
export function shouldInsert(alarm: AlarmItem, query: AlarmQuery): boolean {
  if (query.page !== 1) return false;
  if (query.status && query.status !== alarm.status) return false;
  if (query.severity && query.severity !== alarm.severity) return false;
  if (query.device_id && query.device_id !== alarm.device_id) return false;
  return true;
}

/**
 * 将新告警插入首页数据：
 * - 已存在同 alarm_id → 原地更新（不重复、不新增 total）
 * - 否则头部插入；满页截尾保持 size 不变；total 始终 +1
 */
export function insertAlarmIntoPage(
  page: AlarmPageData,
  alarm: AlarmItem,
): AlarmPageData {
  const idx = page.items.findIndex((it) => it.alarm_id === alarm.alarm_id);
  if (idx >= 0) {
    const items = page.items.slice();
    items[idx] = alarm;
    return { ...page, items };
  }
  const items = [alarm, ...page.items].slice(0, page.size);
  return { ...page, items, total: page.total + 1 };
}
