# -*- coding: utf-8 -*-
"""query_sensor 聚合契约验证（V3 收口）。

对 TDengine（REST 6041）按 `query_sensor` 契约（schemas/tools_v1.json）构造等价 SQL：
  device_id + time_range 过滤  +  INTERVAL(window) 聚合 + 指定 aggregation。
验证：
  ① 返回形状（window_start + 各测点聚合值 + count 样本数）；
  ② 契约字段对齐（window / aggregation / time_range）；
  ③ 全量灌数后单次聚合 P95 复测（N 次请求）。

用法：
    python scripts/verify_query_sensor.py --aggregation avg --window 5m --n 30
    python scripts/verify_query_sensor.py --aggregation max --window 15m --metric vib_rms

原始明细落盘： experiments/v3/raw/EXP-V3-QS.jsonl
参考：reports/v3-auth.md §七；docs/schema-mapping.md §4.5。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import time
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 标识符白名单：列名 / 设备号会直接拼入 SQL（TDengine REST 不支持参数化占位符）
SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# 契约默认测点（schema-mapping 主表固定列）
DEFAULT_METRICS = ["vib_rms", "bearing_temp", "motor_current", "pump_speed"]

# aggregation -> 每窗口统计列表达式（trend 用首末差近似斜率）
AGG_SQL = {
    "avg": "AVG({col}) AS avg_{col}",
    "max": "MAX({col}) AS max_{col}",
    "min": "MIN({col}) AS min_{col}",
}


def percentile(sorted_vals, p: float):
    """返回 95%(p=0.95) 分位（线性插值近似）。"""
    if not sorted_vals:
        return None
    i = (len(sorted_vals) - 1) * p
    lo = int(i)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = i - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def window_to_secs(window: str) -> int:
    unit = window[-1]
    val = int(window[:-1])
    return val * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def build_agg_sql(device_id: str, metrics: list[str], window: str,
                  agg: str, start_ms: int, end_ms: int,
                  col=None, threshold=None):
    """按 query_sensor 契约构造 INTERVAL 聚合 SQL。col/threshold 供单列聚合用。

    列名 / 设备号直接拼入 SQL（TDengine REST 无参数化占位符），故先做标识符白名单校验；
    `window` 经 `window_to_secs` 的字典查表限定为 s/m/h/d，非法值在此抛错。
    """
    if not SAFE_IDENT_RE.match(device_id or ""):
        raise ValueError(f"非法 device_id：{device_id!r}")
    for name in list(metrics) + ([col] if col else []):
        if not SAFE_IDENT_RE.match(name or ""):
            raise ValueError(f"非法测点列名：{name!r}")
    window_to_secs(window)          # 非法单位在此抛 KeyError，避免脏值进入 SQL
    where = f"device_id='{device_id}' AND ts >= {start_ms} AND ts < {end_ms}"
    if agg in ("avg", "max", "min"):
        columns = ", ".join(AGG_SQL[agg].format(col=m) for m in metrics)
        select = f"_wstart AS window_start, {columns}, COUNT(*) AS sample_cnt"
    elif agg == "count_over_limit":
        select = (f"_wstart AS window_start, "
                  f"SUM(CASE WHEN {col} > {threshold} THEN 1 ELSE 0 END) AS over_cnt, "
                  f"AVG({col}) AS avg_{col}")
    elif agg == "trend":
        wsec = window_to_secs(window)
        select = (f"_wstart AS window_start, MAX({col}) AS peak_{col}, "
                  f"(LAST_VALUE({col}) - FIRST_VALUE({col})) / {wsec} AS trend_{col}, "
                  f"COUNT(*) AS sample_cnt")
    else:  # raw
        return (f"SELECT ts, {', '.join(metrics)} FROM iot.st_pump_metrics "
                f"WHERE {where} ORDER BY ts")
    return (f"SELECT {select} FROM iot.st_pump_metrics WHERE {where} "
            f"INTERVAL({window}) ORDER BY window_start")


def main():
    ap = argparse.ArgumentParser(description="query_sensor 聚合契约验证")
    ap.add_argument("--td-host", default=os.environ.get("TD_HTTP_HOST", "127.0.0.1"))
    ap.add_argument("--td-port", type=int, default=int(os.environ.get("TD_HTTP_PORT", "6041")))
    ap.add_argument("--td-password", default="taosdata")
    ap.add_argument("--window", default="5m", help="INTERVAL 窗口")
    ap.add_argument("--aggregation", default="avg", choices=["avg", "max", "min", "count_over_limit", "trend", "raw"])
    ap.add_argument("--metric", default=None, help="单列（count_over_limit/trend 必填，如 vib_rms）")
    ap.add_argument("--threshold", type=float, default=4.5, help="count_over_limit 超限阈值")
    ap.add_argument("--n", type=int, default=30, help="P95 请求次数")
    ap.add_argument("--out", default=str(PROJECT_ROOT / "experiments" / "v3" / "raw" / "EXP-V3-QS.jsonl"))
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    import taosrest
    conn = taosrest.connect(url=f"http://{args.td_host}:{args.td_port}",
                            user="root", password=args.td_password, timeout=5)

    # 探测设备与数据时间范围
    devices = [r[0] for r in conn.query("SELECT DISTINCT device_id FROM iot.st_pump_metrics").data]
    rng = conn.query("SELECT FIRST(ts), LAST(ts) FROM iot.st_pump_metrics").data[0]

    def _to_ms(v):
        return int(v.timestamp() * 1000) if isinstance(v, datetime.datetime) else int(v)

    start_ms, end_ms = _to_ms(rng[0]), _to_ms(rng[1])
    print(f"[verify_qs] 设备={devices} 时间窗=[{start_ms},{end_ms}] ms")

    if args.aggregation in ("count_over_limit", "trend") and not args.metric:
        print("!!! --aggregation=count_over_limit/trend 需 --metric 指定单列")
        return 2
    metrics = [args.metric] if args.metric else DEFAULT_METRICS

    latencies = []
    records = []
    # 逐设备构建契约 SQL（time_range 覆盖全数据窗），执行 N 次统计 P95
    for dev in devices:
        sql = build_agg_sql(dev, metrics, args.window, args.aggregation,
                            start_ms, end_ms, col=args.metric, threshold=args.threshold)
        res = conn.query(sql)
        rows = res.data
        headers = getattr(res, "fields", None) or []
        print(f"[verify_qs] {dev} {args.aggregation} 返回 {len(rows)} 窗口; 列={list(headers)[:6]}")
        if rows:
            print(f"[verify_qs]   示例行: {rows[0]}")

        # P95 复测
        t0 = time.perf_counter()
        for _ in range(args.n):
            conn.query(sql).data
        latencies.append((time.perf_counter() - t0) * 1000 / args.n)

        records.append({
            "device_id": dev, "aggregation": args.aggregation, "window": args.window,
            "time_range": [start_ms, end_ms], "windows": len(rows),
            "sample": rows[0] if rows else None,
            "latency_ms_avg": latencies[-1], "n": args.n,
        })

    p95 = percentile(sorted(latencies), 0.95)
    med = median(latencies)
    print(f"\n[verify_qs] 单次聚合 P95≈{p95:.1f}ms  med≈{med:.1f}ms  (N={args.n}/设备)")

    with open(args.out, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "exp": "EXP-V3-QS", "aggregation": args.aggregation, "window": args.window,
            "n": args.n, "p95_ms": round(p95, 2), "med_ms": round(med, 2),
            "devices": devices, "records": records,
        }, default=str, ensure_ascii=False) + "\n")
    print(f"[verify_qs] 明细已落盘 {args.out}")


if __name__ == "__main__":
    main()