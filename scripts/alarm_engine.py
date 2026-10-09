# -*- coding: utf-8 -*-
"""A3 告警引擎（阈值 + 滑动窗口 + Redis 去重 + AlarmEvent 落 PG/JSONL）。

从 TDengine 读取各设备指定测点时序，按 `configs/alarm_rules.yml` 规则判定：
  - 阈值规则：连续 >= must_windows 个窗口均值超过 threshold → 触发（severity 按规则）。
  - 统计异常（Z-Score）：需 >= baseline_days 历史；无基线时段仅用阈值规则，
    规则以 enabled=false 预置（见 configs/alarm_rules.yml），数据就绪后启用。
  - Redis 去重：key = dedup:{prefix}:{device_id}:{metric}，TTL=5min；
    同 key 命中则 dedup_count+1，不重复触发（合并计数）。

输出（AlarmEvent，plan §5.3）：
  {alarm_id, device_id, metric, value, baseline, severity, ts, rule_id, dedup_count}
  - PG `alerts` 表落核心 7 列（alarm_id/device_id/metric/value/severity/status/ts），
    rules 语义字段（rule_id/baseline/dedup_count）写入 JSONL 落盘。
  - alarm_id 幂等 = `{rule_id}:{device_id}:{metric}:{alert_start_ms}`，重跑不重复。

用法：
  .venv\\Scripts\\python.exe scripts\\alarm_engine.py --selftest
  .venv\\Scripts\\python.exe scripts\\alarm_engine.py           # 全量存量判定
  .venv\\Scripts\\python.exe scripts\\alarm_engine.py --rules configs/alarm_rules.yml \
      --out experiments/alarm/EXP-ENGINE.jsonl

注意：metric 列名与 device_id 会直拼 TDengine SQL（无参数化占位符），
须通过 SAFE_IDENT_RE 白名单（复用 run_v3_alert 的注入防护口径）。"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAFE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
# device_id 直接拼入 SQL 常量值（TDengine REST 无参数化占位符），但需引号内值安全：
# 允许连字符等 ASCII 无害字符集，拒绝引号/分号/注释等注入面（对齐 schema-mapping §六 宽松口径）
# 注：列名仍须过 SAFE_IDENT_RE（严格白名单，杜绝 ALTER/注入列）。
SAFE_VALUE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./\-\u4e00-\u9fff]{0,255}$")
# severity 口径映射（P4 前端契约 2026-10-09）：规则词表 high/medium/low → REST/socket 契约 info/warning/critical
_SEV_PG_MAP = {"high": "critical", "medium": "warning", "low": "info"}


def load_rules(path: Path) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def poll_series(conn, column: str, device_id: str, window_min: int):
    """读某设备某列 -> 按窗口聚合窗口均值列表 [[wstart_ts_ms, avg], ...]。"""
    if not SAFE_IDENT_RE.match(column or ""):
        raise ValueError(f"非法列名：{column!r}")
    if not SAFE_VALUE_RE.match(device_id or ""):
        raise ValueError(f"非法 device_id：{device_id!r}")
    res = conn.query(
        f"SELECT ts, {column} FROM iot.st_pump_metrics "
        f"WHERE device_id='{device_id}' AND {column} IS NOT NULL ORDER BY ts")
    interval_ms = window_min * 60_000
    buckets: dict[int, list[float]] = {}
    for ts, val in res.data:
        ms = int(ts.timestamp() * 1000) if isinstance(ts, datetime.datetime) else int(ts)
        buckets.setdefault((ms // interval_ms) * interval_ms, []).append(float(val))
    return sorted((w, sum(v) / len(v)) for w, v in buckets.items())


def rule_windows(windows, rule) -> list:
    """阈值规则：连续 >= must_windows 窗口均值超限 -> 触发窗口起始列表。"""
    must = int(rule["must_windows"])
    thr = float(rule["threshold"])
    triggered = []
    run = 0
    for wstart, avg in windows:
        over = avg > thr if rule.get("op", "gt") == "gt" else avg < thr
        run = run + 1 if over else 0
        if run == must:
            triggered.append(wstart - (must - 1) * 60_000 * int(rule["window_min"]))
            run = 0  # 每个触发窗口只记一条告警起点（后续去重合并）
    return triggered


def eval_threshold(conn, rule, devices) -> list:
    out = []
    for dev in devices:
        try:
            windows = poll_series(conn, rule["metric"], dev, int(rule["window_min"]))
        except Exception as e:
            print(f"[alarm] 读 {dev}/{rule['metric']} 失败: {e}")
            continue
        for wstart_ms in rule_windows(windows, rule):
            # 该窗口均值
            avg = next(a for w2, a in windows if w2 == wstart_ms)
            out.append({
                "device_id": dev, "metric": rule["metric"],
                "rule_id": rule["rule_id"], "severity": rule["severity"],
                "alert_start_ms": wstart_ms, "value": round(avg, 4),
                "baseline": rule.get("threshold"),
            })
    return out


def eval_zscore(conn, rule, devices) -> list:
    """Z-Score 统计异常：滑动窗口内 Z-Score > z_threshold → medium。
    仅当历史跨度 >= baseline_days 时启用；否则按规格不评估（返回空）。"""
    if not rule.get("enabled", False):
        return []
    out = []
    for dev in devices:
        try:
            windows = poll_series(conn, rule["metric"], dev, int(rule["window_min"]))
        except Exception:
            continue
        vals = [avg for _, avg in windows]
        # 需 >= baseline_days 的窗口跨度才可建立基线
        span_days = ((windows[-1][0] - windows[0][0]) / 86_400_000) if len(windows) > 1 else 0
        if span_days < float(rule.get("baseline_days", 7)):
            continue  # 基线不足，按规格不判定
        mu, sd = statistics.mean(vals), statistics.stdev(vals) if len(vals) > 1 else 0.0
        for wstart_ms, avg in windows:
            z = (avg - mu) / sd if sd else 0.0
            if z > float(rule["z_threshold"]):
                out.append({"device_id": dev, "metric": rule["metric"],
                            "rule_id": rule["rule_id"], "severity": rule["severity"],
                            "alert_start_ms": wstart_ms, "value": round(avg, 4),
                            "baseline": round(mu, 4)})
    return out


def dedup_and_emit(events, dedup_cfg, redis_client, pg_conn):
    """Redis 去重（TTL 滑动窗口）+ 5min 同类合并，生成标准 AlarmEvent 落 PG。

    规则（plan §5.3）：key = {prefix}:{device_id}:{metric}，TTL=5min。
    对同一 (device_id, metric) 的候选按触发时间排序，命中前后 5min 内的合并为 1 条；
    首条生成 AlarmEvent 并写 PG（幂等 upsert），合并命中的后续候选仅递增 dedup_count，
    不重复触发新 AlarmEvent。
    """
    emissions = []
    prefix = dedup_cfg.get("key_prefix", "dedup:alarm")
    ttl = int(dedup_cfg.get("ttl_sec", 300))

    # 按 (device, metric) 分组并排序
    groups: dict[tuple, list] = {}
    for ev in events:
        groups.setdefault((ev["device_id"], ev["metric"]), []).append(ev)
    for (dev, metric), cands in groups.items():
        cands.sort(key=lambda e: e["alert_start_ms"])
        merged = []
        for ev in cands:
            if merged and ev["alert_start_ms"] - merged[-1]["alert_start_ms"] <= ttl * 1000:
                merged[-1]["_count"] += 1
                merged[-1]["_last"] = ev["alert_start_ms"]
            else:
                merged.append({**ev, "_count": 1, "_last": ev["alert_start_ms"]})
        for ev in merged:
            key = f"{prefix}:{dev}:{metric}"
            n = redis_client.incr(key)
            if n == 1:
                redis_client.expire(key, ttl)
            alarm = {
                "alarm_id": f"{ev['rule_id']}:{dev}:{metric}:{ev['alert_start_ms']}",
                "device_id": dev, "metric": metric,
                "value": ev["value"], "baseline": ev["baseline"],
                "severity": ev["severity"], "ts": ev["alert_start_ms"],
                "rule_id": ev["rule_id"], "dedup_count": n,
            }
            if pg_conn:
                ts_pg = datetime.datetime.fromtimestamp(ev["alert_start_ms"] / 1000.0, datetime.UTC)
                # 口径对齐（P4 前端契约）：告警规则用 high/medium/low，REST/socket 契约统一 info/warning/critical
                sev_pg = _SEV_PG_MAP.get(ev["severity"], ev["severity"])
                pg_conn.execute(
                    "INSERT INTO alerts (alarm_id, device_id, metric, value, severity, status, ts) "
                    "VALUES (%s,%s,%s,%s,%s,'open',%s) "
                    "ON CONFLICT (alarm_id) DO UPDATE SET value=EXCLUDED.value, status='open'",
                    (alarm["alarm_id"], dev, metric, ev["value"], sev_pg, ts_pg))
            emissions.append(alarm)
    if pg_conn:
        pg_conn.commit()
    return emissions


def _connect_redis(host, port, password=None):
    import redis
    kwargs = {"host": host, "port": port, "db": 0, "decode_responses": True,
              "socket_connect_timeout": 2, "socket_timeout": 2}
    if password:
        kwargs["password"] = password
    return redis.Redis(**kwargs)


class _MemoryDedup:
    """Redis 不可用时的 in-process 去重 fallback（dict + TTL，避免核心告警染色）。

    仅在主流程主动降级时使用（`--allow-no-redis`）；生产该由真实 Redis 承接。
    语义与 Redis 一致：key = {prefix}:{device}:{metric}，TTL 内同 key 计数递增。
    """
    def __init__(self, ttl_sec=300):
        self.ttl_sec = ttl_sec
        self._counts: dict[str, int] = {}
        self._expire: dict[str, float] = {}

    def incr(self, key: str) -> int:
        from time import time
        now = time()
        if key in self._expire and self._expire[key] <= now:
            self._counts.pop(key, None)
            self._expire.pop(key, None)
        n = self._counts.get(key, 0) + 1
        self._counts[key] = n
        if n == 1:
            self._expire[key] = now + self.ttl_sec
        return n

    def expire(self, key: str, ttl_sec: int) -> None:
        from time import time
        self._expire[key] = time() + ttl_sec


def _connect_pg(host, port, db, user, password):
    import psycopg
    return psycopg.connect(host=host, port=port, dbname=db, user=user, password=password)


class SelfTest:
    @staticmethod
    def run() -> bool:
        ok = True
        def check(name, cond, detail=""):
            nonlocal ok
            if not cond:
                ok = False
            print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))

        rule = {"metric": "vib_rms", "op": "gt", "threshold": 4.5,
                "window_min": 1, "must_windows": 2}
        windows = [[0, 1.3], [60000, 1.4], [120000, 4.6], [180000, 4.9], [240000, 1.2]]
        trig = rule_windows(windows, rule)
        check("阈值状态机：2 连续超限才触发", trig == [120000], f"{trig}")
        # 单一超限不触发
        trig2 = rule_windows([[0, 4.7], [60000, 1.0]], rule)
        check("单窗口超限不触发", trig2 == [], f"{trig2}")

        # 5min 同类去重合并：3600s 内多条候选合并为 1 条（仅首条生成 AlarmEvent）
        cands = [
            {"device_id": "PUMP-A", "metric": "vib_rms", "rule_id": "thr_vib_rms",
             "severity": "high", "alert_start_ms": 0, "value": 4.7, "baseline": 4.5},
            {"device_id": "PUMP-A", "metric": "vib_rms", "rule_id": "thr_vib_rms",
             "severity": "high", "alert_start_ms": 120_000, "value": 4.9, "baseline": 4.5},
            {"device_id": "PUMP-A", "metric": "vib_rms", "rule_id": "thr_vib_rms",
             "severity": "high", "alert_start_ms": 240_000, "value": 4.8, "baseline": 4.5},
        ]
        grp: dict = {}
        for e in cands:
            grp.setdefault((e["device_id"], e["metric"]), []).append(e)
        key0 = (cands[0]["device_id"], cands[0]["metric"])
        seq = sorted(grp[key0], key=lambda e: e["alert_start_ms"])
        merged = []
        for ev in seq:
            if merged and ev["alert_start_ms"] - merged[-1]["alert_start_ms"] <= 300_000:
                merged[-1]["_count"] += 1
            else:
                merged.append({**ev, "_count": 1})
        check("5min 内同类合并为 1 条", len(merged) == 1 and merged[0]["_count"] == 3,
              f"merged={len(merged)}, count={merged[0]['_count'] if merged else None}")
        print("SELFTEST " + ("PASS" if ok else "FAIL"))
        return ok


def main():
    ap = argparse.ArgumentParser(description="A3 告警引擎（阈值+Z-Score+Redis 去重）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--rules", default=str(PROJECT_ROOT / "configs" / "alarm_rules.yml"))
    ap.add_argument("--out", default=str(PROJECT_ROOT / "experiments" / "alarm" / "EXP-ENGINE.jsonl"))
    ap.add_argument("--td-host", default=os.environ.get("TD_HTTP_HOST", "127.0.0.1"))
    ap.add_argument("--td-port", type=int, default=int(os.environ.get("TD_HTTP_PORT", "6041")))
    ap.add_argument("--td-password", default="taosdata")
    ap.add_argument("--redis-host", default=os.environ.get("REDIS_HOST", "127.0.0.1"))
    ap.add_argument("--redis-port", type=int, default=int(os.environ.get("REDIS_PORT", "6379")))
    ap.add_argument("--redis-password", default=os.environ.get("REDIS_PASSWORD", "auscult-dev-redis"))
    ap.add_argument("--allow-no-redis", action="store_true",
                    help="Redis 不可达时降级为 in-process 去重（仅本地实验，生产必须真 Redis）")
    ap.add_argument("--pg-host", default=os.environ.get("PG_HOST", "127.0.0.1"))
    ap.add_argument("--pg-port", type=int, default=int(os.environ.get("PG_PORT", "5433")))
    ap.add_argument("--pg-db", default="auscult_v2")
    ap.add_argument("--pg-user", default="root")
    ap.add_argument("--pg-password", default="123456")
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(0 if SelfTest.run() else 1)

    cfg = load_rules(Path(args.rules))
    import taosrest
    td = taosrest.connect(url=f"http://{args.td_host}:{args.td_port}",
                          user="root", password=args.td_password, timeout=8)
    devices = [r[0] for r in td.query("SELECT DISTINCT device_id FROM iot.st_pump_metrics").data]
    pg = _connect_pg(args.pg_host, args.pg_port, args.pg_db, args.pg_user, args.pg_password)

    # Redis 去重：优先真实 Redis；仅显式允许且不可达时降级 in-process（避免核心告警染色）
    rds = _connect_redis(args.redis_host, args.redis_port, args.redis_password)
    try:
        rds.ping()
    except Exception as e:
        if args.allow_no_redis:
            rds = _MemoryDedup(int(cfg.get("dedup", {}).get("ttl_sec", 300)))
            print(f"[alarm] Redis 不可达（{e}），已降级 in-process 去重")
        else:
            raise RuntimeError(f"Redis 不可达（{e}）；本地实验可加 --allow-no-redis 降级") from e

    events = []
    for rule in cfg["rules"]:
        kind = rule.get("type", "threshold")
        res = eval_threshold(td, rule, devices) if kind == "threshold" else eval_zscore(td, rule, devices)
        events.extend(res)
        print(f"[alarm] rule={rule['rule_id']} kind={kind} -> {len(res)} 候选")

    emitted = dedup_and_emit(events, cfg.get("dedup", {}), rds, pg)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for a in emitted:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"[alarm] 触发告警共 {len(emitted)} 条，已落 PG alerts + {args.out}")
    for a in emitted[:20]:
        print("  ", json.dumps(a, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())