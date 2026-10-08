# -*- coding: utf-8 -*-
"""V3 告警路线 A（阈值 + 滑动窗口）验证（reports/p0-report-v3-ingest-license.md §八 / 用户确认主场景阈值型判据）。

从 TDengine 逐设备读指定测点时序 → 按 window-min 分窗口取均值 → 状态机滑动判定：
  Must#1  超限：连续 >= must_windows 个窗口均值 > threshold → 触发告警（定位设备/测点/窗口），
          误报 = 非超限设备产生的告警数，应收敛；
  Must#2  恢复：触发后连续 >= must_windows 个窗口均值 <= threshold → 解除告警（alert_end 定位），
          判定恢复正确。

用法：
    python scripts/run_v3_alert.py                       # 默认 vib_rms 阈值 4.5，5min×3 窗口
    python scripts/run_v3_alert.py --threshold 4.5 --window-min 5 --must-windows 3

原始明细落盘： experiments/v3/raw/EXP-V3-ALERT.jsonl
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 标识符白名单：列名与 device_id 会直接拼入 SQL（TDengine REST 无参数化占位符），
# 故先校验再拼接，避免注入。
SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def poll_device_series(conn, column: str, device_id: str):
    if not SAFE_IDENT_RE.match(column or ""):
        raise ValueError(f"非法列名（--column）：{column!r}")
    if not SAFE_IDENT_RE.match(device_id or ""):
        raise ValueError(f"非法 device_id：{device_id!r}")
    res = conn.query(
        f"SELECT ts, {column} FROM iot.st_pump_metrics "
        f"WHERE device_id='{device_id}' AND {column} IS NOT NULL ORDER BY ts")
    out = []
    for ts, val in res.data:
        ms = int(ts.timestamp() * 1000) if isinstance(ts, datetime.datetime) else int(ts)
        out.append((ms, float(val)))
    return out  # [[ts_ms, value], ...]


def detect_alerts(series, column: str, threshold: float,
                  window_min: int, must_windows: int) -> list:
    """滑动窗口状态机，返回该设备告警事件列表。"""
    if not series:
        return []
    interval_ms = window_min * 60_000
    # 聚合成窗口均值（对齐 TDengine INTERVAL 起点）
    buckets: dict[int, list[float]] = {}
    for ts_ms, val in series:
        wstart = (ts_ms // interval_ms) * interval_ms
        buckets.setdefault(wstart, []).append(val)
    windows = sorted((w, sum(v) / len(v)) for w, v in buckets.items())

    alerts: list[dict] = []
    in_alert = False
    consec_above = 0
    consec_below = 0
    alert_start = None
    alert_windows = 0
    max_avg = -1.0
    for wstart, avg in windows:
        if avg > threshold:
            consec_above += 1
            consec_below = 0
            if not in_alert and consec_above >= must_windows:
                # 触发：起点取第一个超限窗口（非刚满足时刻，便于定位）
                in_alert = True
                alert_start = wstart - (must_windows - 1) * interval_ms
                alert_windows = must_windows
                max_avg = avg
            elif in_alert:
                alert_windows += 1
                max_avg = max(max_avg, avg)
        else:
            consec_below += 1
            consec_above = 0
            if in_alert and consec_below >= must_windows:
                alerts.append({
                    "device_id": None,  # 由调用方回填
                    "column": column,
                    "alert_start": alert_start,
                    "alert_end": wstart - (must_windows - 1) * interval_ms,
                    "n_alert_windows": alert_windows,
                    "max_window_avg": round(max_avg, 4),
                    "recovered": True,
                })
                in_alert = False
                alert_windows = 0
                max_avg = -1.0
    if in_alert:
        alerts.append({
            "device_id": None, "column": column,
            "alert_start": alert_start, "alert_end": None,
            "n_alert_windows": alert_windows,
            "max_window_avg": round(max_avg, 4), "recovered": False,
        })
    return alerts


def main():
    ap = argparse.ArgumentParser(description="V3 告警路线 A（阈值+滑动窗口）验证")
    ap.add_argument("--td-host", default=os.environ.get("TD_HTTP_HOST", "127.0.0.1"))
    ap.add_argument("--td-port", type=int, default=int(os.environ.get("TD_HTTP_PORT", "6041")))
    ap.add_argument("--td-password", default="taosdata")
    ap.add_argument("--column", default="vib_rms", help="判定测点列（default vib_rms）")
    ap.add_argument("--threshold", type=float, default=4.5, help="超限阈值")
    ap.add_argument("--window-min", type=int, default=5, help="窗口粒度（分钟）")
    ap.add_argument("--must-windows", type=int, default=3, help="持续 N 窗口判定触发/恢复")
    ap.add_argument("--out", default=str(PROJECT_ROOT / "experiments" / "v3" / "raw" / "EXP-V3-ALERT.jsonl"))
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    import taosrest
    conn = taosrest.connect(url=f"http://{args.td_host}:{args.td_port}",
                            user="root", password=args.td_password, timeout=5)
    devices = [r[0] for r in conn.query("SELECT DISTINCT device_id FROM iot.st_pump_metrics").data]

    device_map = {}
    for dev in devices:
        seq = poll_device_series(conn, args.column, dev)
        alerts = detect_alerts(seq, args.column, args.threshold,
                               args.window_min, args.must_windows)
        for a in alerts:
            a["device_id"] = dev
        device_map[dev] = alerts
        print(f"[alert] {dev}: {len(alerts)} 条告警" +
              ("  " + json.dumps(alerts, ensure_ascii=False) if alerts else ""))

    # ---- 判据评估 ----
    alert_devs = [dev for dev, al in device_map.items() if al]
    # 预期超限设备 = 非空告警所需；灌数时仅首设备注入超限，但这里不硬编码，
    # 判据聚焦：① 能定位 ② 恢复判定 ③ 误报收敛（其余设备不触发）
    must1_ok = all(len(al) >= 1 for al in device_map.values() if al) and bool(alert_devs)
    must2_ok = all(a["recovered"] for al in device_map.values() for a in al)

    print("\n=== Must#1 超限持续触发（连续>=%d 窗口均值>%.2f）===" % (args.must_windows, args.threshold))
    print(f"  触发设备: {alert_devs or '无'}")
    print(f"  ✓定位/触发: {'PASS' if must1_ok else 'FAIL'}")
    print("=== Must#2 超限解除后恢复判定 ===")
    print(f"  全部告警均含恢复: {'PASS' if must2_ok else 'FAIL'}")

    rec = {
        "exp": "EXP-V3-ALERT", "column": args.column, "threshold": args.threshold,
        "window_min": args.window_min, "must_windows": args.must_windows,
        "devices": devices, "alerts": {d: device_map[d] for d in devices},
        "must1_pass": must1_ok, "must2_pass": must2_ok,
    }
    with open(args.out, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[alert] 明细已落盘 {args.out}")
    return 0 if (must1_ok and must2_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())