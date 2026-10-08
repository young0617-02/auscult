# -*- coding: utf-8 -*-
"""V3 标准数据集直写 TDengine（绕开 MQTT 逐条链路，供 query_sensor P95 + 告警验证）。

背景：自研解码器为 taosrest 逐条 INSERT（≈80ms/条），2.1 万点经实时链路需 ~25min 且多轮
      乱序不干净。端到端接入链路已在本轮另行验证；此处用 TDengine 批量 VALUES 直接构造
      与模拟器同语义的标准数据集，几分钟内灌入并保证时间戳干净单调。

语义（与 spb_simulator 连续灌数一致）：
  3 台设备(PUMP-A/B/C) × 2h × 1Hz ≈ 2.1万点；PUMP-A 在中段(local 50%~50%+25min)
  注入 vib_rms 超限段（≈5.0~6.2 > 4.5），其余设备正常；用于验证"告警能否精确定位到超限设备"。

用法：
    python scripts/v3_ingest_direct.py [--hours 2 --interval-ms 1000 \
--devices PUMP-A,PUMP-B,PUMP-C]
    （告警设备固定为 --devices 的首个元素，本脚本无 --alert-device 参数）
参考：docs/prj-spec-schema-mapping.md §4.5；reports/p0-report-v3-ingest-license.md §七/§八。
"""

from __future__ import annotations

import argparse
import os
import random
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IOT = "iot"
STABLE = "st_pump_metrics"
GROUP_ID = "plant1"
EDGE_NODE_ID = "gw-pump-01"
DEVICE_TYPE = "PUMP_TYPE"
COLUMNS = ("ts", "vib_rms", "vib_peak", "vib_kurtosis",
           "bearing_temp", "motor_current", "pump_speed", "quality_ok")


def agg_vals(rng, in_alert: bool):
    if in_alert:
        return (5.5 + rng.uniform(-0.5, 0.6), 9.0 + rng.uniform(-0.5, 1.0),
                5.5 + rng.uniform(-0.5, 1.0), 59.5 + rng.uniform(-0.5, 0.8),
                12.5 + rng.uniform(-0.3, 0.5), 1452 + rng.uniform(-3, 3))
    return (1.3 + rng.uniform(-0.3, 0.3), 3.4 + rng.uniform(-0.4, 0.5),
            3.0 + rng.uniform(-0.15, 0.15), 58.7 + rng.uniform(-0.8, 1.2),
            12.3 + rng.uniform(-0.4, 0.7), 1450 + rng.uniform(-8, 8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--td-host", default=os.environ.get("TD_HTTP_HOST", "127.0.0.1"))
    ap.add_argument("--td-port", type=int, default=int(os.environ.get("TD_HTTP_PORT", "6041")))
    ap.add_argument("--td-password", default="taosdata")
    ap.add_argument("--hours", type=float, default=2.0)
    ap.add_argument("--interval-ms", type=int, default=1000)
    ap.add_argument("--devices", default="PUMP-A,PUMP-B,PUMP-C")
    ap.add_argument("--alert-start-ratio", type=float, default=0.5)
    ap.add_argument("--alert-duration-min", type=float, default=25.0)
    ap.add_argument("--seed", type=int, default=20260928)
    ap.add_argument("--batch", type=int, default=500)
    args = ap.parse_args()

    import taosrest
    conn = taosrest.connect(url=f"http://{args.td_host}:{args.td_port}",
                            user="root", password=args.td_password,
                            database=IOT, timeout=5)

    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    alert_dev = devices[0]
    total_ms = int(args.hours * 3600 * 1000)
    alert_start_ms = int(total_ms * args.alert_start_ratio)
    alert_ms = int(args.alert_duration_min * 60 * 1000)
    period = args.interval_ms
    n_points = total_ms // period
    # 起点对齐分钟且位于现有数据之后，保证单调不交织
    base_ts = (int(time.time() * 1000) // 60_000 + 1) * 60_000 + 5_000

    # 每设备分批 INSERT（多行 VALUES）
    total = 0
    for dev in devices:
        rng = random.Random(args.seed + devices.index(dev))
        is_alert_dev = dev == alert_dev
        sub = f"`d_plant1_{dev}`"
        tag_v = (f"'{GROUP_ID}','{EDGE_NODE_ID}','{dev}','{DEVICE_TYPE}'")
        t0 = base_ts
        rows = []
        batches = 0
        for k in range(n_points):
            offset = k * period
            in_alert = is_alert_dev and (alert_start_ms <= offset < alert_start_ms + alert_ms)
            vib_rms, vib_peak, vib_kurt, temp, cur, speed = agg_vals(rng, in_alert)
            ts = t0 + offset
            rows.append((f"{ts},{vib_rms:.4f},{vib_peak:.4f},{vib_kurt:.4f},"
                         f"{temp:.3f},{cur:.3f},{speed:.1f},{True}"))
            if len(rows) >= args.batch:
                sql = (f"INSERT INTO {sub} USING {IOT}.{STABLE} TAGS({tag_v}) "
                       f"({', '.join(COLUMNS)}) VALUES " + ",".join(f"({r})" for r in rows))
                conn.execute(sql)
                batches += 1
                rows = []
        if rows:
            sql = (f"INSERT INTO {sub} USING {IOT}.{STABLE} TAGS({tag_v}) "
                   f"({', '.join(COLUMNS)}) VALUES " + ",".join(f"({r})" for r in rows))
            conn.execute(sql)
            batches += 1
        total += n_points
        print(f"[ingest_direct] {dev}: {n_points} 点 / {batches} 批")

    print(f"[ingest_direct] 完成，共 {total} 点（{devices}，PUMP-A 含超限段 vib_rms>4.5）")


if __name__ == "__main__":
    main()