/** 告警相关 TS 类型（对齐 app/api/routes/alarms.py 契约） */

export interface AlarmItem {
  alarm_id: string;
  device_id: string;
  metric: string;
  /** DB 中可能为 NULL；REST 返 ISO、alarm:new 返 epoch ms，由 alarmTime 归一 */
  value: number | null;
  severity: "info" | "warning" | "critical";
  status: "open" | "acked" | "closed";
  /** REST 返回 ISO8601 字符串；alarm:new 推送为 epoch 毫秒（前端统一转 Date） */
  ts: string | number;
}

export interface AlarmPageData {
  items: AlarmItem[];
  total: number;
  page: number;
  size: number;
}

/** 查询参数（URL searchParams 同形） */
export interface AlarmQuery {
  page: number;
  size: number;
  status?: string;
  severity?: string;
  device_id?: string;
}

export const SEVERITY_LABEL: Record<AlarmItem["severity"], string> = {
  info: "低",
  warning: "中",
  critical: "高",
};

export const STATUS_LABEL: Record<AlarmItem["status"], string> = {
  open: "活跃",
  acked: "已确认",
  closed: "已关闭",
};
