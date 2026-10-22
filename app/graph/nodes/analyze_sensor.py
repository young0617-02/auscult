"""analyze_sensor 节点（D3）

接入 query_sensor 查询告警前后时序窗口 + 统计摘要。
超时预算: 500ms; 重试 3 次（指数退避 100/200/400ms）。
降级: TDengine 不可达 → sensor_report=None + errors。

对应交付物: plan/Phase 3 §三.2 / §五 D3
"""

from __future__ import annotations

import time
from typing import Any

from ...observability import prom_metrics as pm
from ...tools.query_sensor import percentile, query_sensor
from ..state import DiagnosisState

# 查询窗口: 告警前 30 分钟 ~ 告警后 5 分钟
WINDOW_BEFORE_MS = 30 * 60 * 1000
WINDOW_AFTER_MS = 5 * 60 * 1000
MAX_RETRIES = 3
RETRY_DELAYS = [0.1, 0.2, 0.4]  # 指数退避


def _compute_stats(
    values: list[float],
    threshold: float | None,
    sampling_interval_ms: float = 1000.0,
) -> dict[str, Any]:
    """计算统计摘要（Must#3：含 `p95` 与 `anomaly`，对齐 Phase 0 判据）。

    判据原文（`docs/p0-spec-scope-mvp.md:49`）要求 `query_sensor` 返回
    「avg/max/min/**p95**/trend + 异常标记 **anomaly**」；原实现两者皆无。
    """
    if not values:
        return {
            "count": 0, "avg": 0.0, "max": 0.0, "min": 0.0, "last": 0.0,
            "p95": 0.0, "anomaly": False, "anomaly_reasons": [],
            "exceed_count": 0, "exceed_duration_ms": 0.0,
            "threshold": threshold, "trend": "unknown",
        }

    avg = sum(values) / len(values)
    mx = max(values)
    mn = min(values)
    last = values[-1]

    exceed_count = 0
    if threshold is not None:
        exceed_count = sum(1 for v in values if v > threshold)

    # 趋势: 前半段 vs 后半段均值
    mid = len(values) // 2
    if mid > 0 and len(values) > mid:
        first_half = sum(values[:mid]) / mid
        second_half = sum(values[mid:]) / (len(values) - mid)
        if second_half > first_half * 1.1:
            trend = "rising"
        elif second_half < first_half * 0.9:
            trend = "falling"
        else:
            trend = "stable"
    else:
        trend = "unknown"

    # Must#3：p95（线性插值，与 query_sensor 契约同算法）+ 可解释的异常标记
    p95 = round(percentile(values, 0.95), 4)
    anomaly_reasons: list[str] = []
    if threshold is not None and exceed_count > 0:
        anomaly_reasons.append(
            f"{exceed_count}/{len(values)} 个采样点超阈值 {threshold}（峰值 {round(mx, 4)}）")
    if trend == "rising" and avg > 0 and mx > avg * 1.5:
        anomaly_reasons.append(
            f"趋势上升且峰值 {round(mx, 4)} 达均值 {round(avg, 4)} 的 {round(mx / avg, 2)} 倍")

    return {
        "count": len(values),
        "avg": round(avg, 4),
        "max": round(mx, 4),
        "min": round(mn, 4),
        "last": round(last, 4),
        "p95": p95,
        "anomaly": bool(anomaly_reasons),
        "anomaly_reasons": anomaly_reasons,
        "exceed_count": exceed_count,
        "exceed_duration_ms": round(exceed_count * sampling_interval_ms, 1),
        "threshold": threshold,
        "trend": trend,
    }


def analyze_sensor(state: DiagnosisState) -> dict[str, Any]:
    """接入 query_sensor 查询时序数据 + 统计摘要。

    输入: state.alarm（AlarmEvent，含 device_id/metric/ts/baseline）
    输出: {"sensor_report": dict} 或 {"sensor_report": None, "errors": [...]}
    降级: TDengine 不可达 → sensor_report=None + errors
    """
    alarm = state.alarm
    if alarm is None:
        return {"errors": [{"node": "analyze_sensor", "code": "E_NO_ALARM",
                            "msg": "缺少告警事件"}]}

    start_ts = alarm.ts - WINDOW_BEFORE_MS
    end_ts = alarm.ts + WINDOW_AFTER_MS

    last_error: str | None = None
    for attempt in range(MAX_RETRIES):
        try:
            result = query_sensor(
                device_id=alarm.device_id,
                metric=alarm.metric,
                start_ts=start_ts,
                end_ts=end_ts,
                timeout=0.5,
            )
            values = [r["value"] for r in result["rows"]]
            pm.inc_tool_call("query_sensor", "ok" if values else "empty")
            stats = _compute_stats(values, alarm.baseline)
            sensor_report: dict[str, Any] = {
                "device_id": alarm.device_id,
                "metric": alarm.metric,
                "raw_count": result["count"],
                **stats,
            }
            return {"sensor_report": sensor_report}

        except TimeoutError:
            last_error = "E_TD_TIMEOUT"
        except ConnectionError:
            last_error = "E_TD_UNREACHABLE"
        except (RuntimeError, ValueError) as exc:
            # 查询错误不重试
            pm.inc_tool_call("query_sensor", "error")
            return {
                "sensor_report": None,
                "errors": [{"node": "analyze_sensor",
                            "code": "E_TD_QUERY_ERROR",
                            "msg": str(exc)}],
            }

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAYS[attempt])

    pm.inc_tool_call("query_sensor", "error")
    return {
        "sensor_report": None,
        "errors": [{"node": "analyze_sensor", "code": last_error or "E_UNKNOWN",
                    "msg": f"TDengine 查询失败（重试 {MAX_RETRIES} 次后）"}],
    }
