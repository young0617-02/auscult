"""告警自动触发诊断（P7 · 补全 README §2.3 在线诊断请求流的「LangGraph 触发」环节）。

背景：告警引擎（scripts/alarm_engine.py，外部进程）完成阈值判定 + Redis 去重后
落 PG `alerts` 表；此前诊断只能由人工调 POST /api/diagnose 发起，
「MQTT 告警 → 去重 → LangGraph 触发」数据流的最后一环缺失。本模块补上。

实现选型（docs/p7-design-redis-cache-layer-2026-10-16.md §四）：
  - **PG 游标扫描**，不引 Redis Stream / MQTT 订阅：告警引擎是批处理式外部
    进程（非长驻流式服务），PG 即天然事件日志；进程重启后扫描条件从
    `diagnosed_thread_id IS NULL` 重建，不回放历史、不丢未触发告警；
  - **双层幂等**：Redis SETNX 快速护栏（cache_guard_trigger，TTL 7d）+
    PG `diagnosed_thread_id` 权威标记（两阶段：trigger-pending → 真实 id）；
  - **默认关闭**（AUSCULT_AUTO_TRIGGER=0）：自动跑 LLM 诊断属行为变更，
    按判据前置纪律须显式启用；启用后可用 AUSCULT_AUTO_TRIGGER_SEVERITY 收敛面。

降级：PG 不可达 → 本轮跳过（下轮重试）；单条 start_diagnosis 异常 → 该条记
      error 打点并保留 pending 标记，不阻断其余告警、下轮不重触发（人工可介入）。

对应交付物：docs/p7-design-redis-cache-layer-2026-10-16.md §四
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from app.api.config import (
    AUTO_TRIGGER_ENABLED,
    AUTO_TRIGGER_INTERVAL_SEC,
    AUTO_TRIGGER_LIMIT,
    AUTO_TRIGGER_SEVERITY,
)
from app.api.db import get_conn
from app.api.errors import ApiError
from app.api.runner import start_diagnosis
from app.cache import cache_guard_trigger
from app.graph.state import AlarmEvent
from app.observability import prom_metrics as pm

logger = logging.getLogger("auscult.auto_trigger")

SUBMITTER = "system:auto-trigger"      # 非人类身份；审核职责分离天然成立


def _severity_allowed(severity: str) -> bool:
    """空过滤集 = 全部放行；否则仅子集。"""
    if not AUTO_TRIGGER_SEVERITY:
        return True
    return severity in AUTO_TRIGGER_SEVERITY


def _row_to_alarm(row: dict[str, Any]) -> AlarmEvent:
    """alerts 行 → AlarmEvent（口径对齐 routes/diagnose._load_alarm_by_id）。"""
    ts = row.get("ts")
    return AlarmEvent(
        alarm_id=row["alarm_id"],
        device_id=row["device_id"],
        metric=row["metric"],
        value=float(row["value"]) if row.get("value") is not None else 0.0,
        severity=row.get("severity") or "medium",
        ts=int(ts.timestamp() * 1000) if ts else 0,
    )


def _fetch_pending(limit: int) -> list[dict[str, Any]]:
    """取未触发告警（status='open' AND diagnosed_thread_id IS NULL，按时间序）。"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT alarm_id, device_id, metric, value, severity, status, ts
                 FROM alerts
                WHERE status = 'open' AND diagnosed_thread_id IS NULL
                ORDER BY ts ASC
                LIMIT %s""",
            (limit,)).fetchall()
    return [dict(r) for r in rows]


def _mark_pending(alarm_id: str) -> bool:
    """两阶段之一：占位标记（条件 UPDATE 的行锁语义防并发双触发）。True = 抢到触发权。"""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE alerts SET diagnosed_thread_id = 'trigger-pending' "
            "WHERE alarm_id = %s AND diagnosed_thread_id IS NULL",
            (alarm_id,))
        return cur.rowcount == 1


def _mark_triggered(alarm_id: str, thread_id: str) -> None:
    """两阶段之二：回写真实 thread_id（失败不影响诊断本身，且 pending 已非 NULL，
    下轮不会重触发；人工可经 SQL 修正）。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE alerts SET diagnosed_thread_id = %s WHERE alarm_id = %s",
            (thread_id, alarm_id))


def trigger_once(limit: int = AUTO_TRIGGER_LIMIT) -> int:
    """单轮扫描 + 触发；返回实际发起的诊断数（禁用时返回 0 并打点 disabled）。"""
    if not AUTO_TRIGGER_ENABLED:
        pm.inc_auto_trigger("disabled")
        return 0
    started = 0
    try:
        rows = _fetch_pending(limit)
    except ApiError as exc:
        logger.warning("自动触发扫描失败（PG 不可达，下轮重试）: %s", exc.message)
        pm.inc_auto_trigger("error")
        return 0
    for row in rows:
        alarm_id = row["alarm_id"]
        try:
            if not _severity_allowed(row.get("severity") or ""):
                pm.inc_auto_trigger("skipped")
                continue
            # 快速护栏：Redis 侧已触发过 → 跳过（权威标记仍在 PG）
            if not cache_guard_trigger(alarm_id):
                pm.inc_auto_trigger("skipped")
                continue
            # 权威占位：防扫描-启动间隙的并发/重试双触发
            if not _mark_pending(alarm_id):
                pm.inc_auto_trigger("skipped")
                continue
            thread_id = start_diagnosis(_row_to_alarm(row), submitter=SUBMITTER)
            _mark_triggered(alarm_id, thread_id)
            started += 1
            pm.inc_auto_trigger("started")
            logger.info("告警自动触发诊断: alarm_id=%s thread_id=%s",
                        alarm_id, thread_id)
        except Exception as exc:                              # noqa: BLE001
            # 单条失败不阻断其余告警；不回写标记（保留 pending，人工可介入）
            pm.inc_auto_trigger("error")
            logger.warning("告警自动触发失败: alarm_id=%s err=%s",
                           alarm_id, type(exc).__name__)
    return started


def _watch_loop() -> None:
    """轮询循环（与 review lifecycle watcher 同模式：daemon 线程，不依赖 socket 循环）。"""
    while True:
        try:
            trigger_once()
        except Exception:                                    # noqa: BLE001 - 循环不中断
            logger.exception("自动触发轮次异常（已吞掉，下轮继续）")
        time.sleep(AUTO_TRIGGER_INTERVAL_SEC)


def start_auto_trigger_watcher() -> None:
    """FastAPI lifespan 启动（main.py）。

    默认关闭时 trigger_once 每轮打点 disabled——/metrics 可持续观测开关状态，
    避免「配置写了但没生效」的静默漂移（与 health cloud_budget 探针同思路）。
    """
    if not AUTO_TRIGGER_ENABLED:
        logger.info("告警自动触发未启用（AUSCULT_AUTO_TRIGGER=0）；"
                    "诊断仍可经 POST /api/diagnose 人工发起")
    threading.Thread(target=_watch_loop, name="alarm-auto-trigger",
                     daemon=True).start()
