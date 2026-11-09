"""query_sensor 工具执行体（D3）

从 TDengine 查询设备时序数据。使用 REST API（端口 6041），不依赖 taospy。

对应交付物：plan/Phase 3 §五 D3 / §四.3
Schema 来源：schemas/tools_v2.json → query_sensor
表：iot.st_pump_metrics（超级表，TAG=device_id）
列：ts, vib_rms, vib_peak, vib_kurtosis, bearing_temp, motor_current, pump_speed, quality_ok
"""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

TDENGINE_BASE = "http://127.0.0.1:6041/rest/sql"
TDENGINE_DB = "iot"
TDENGINE_USER = "root"
TDENGINE_PASSWORD = os.environ.get("TDENGINE_PASSWORD", "taosdata")

# 白名单校验（防 SQL 注入：只允许字母数字/下划线/连字符）
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]+$")


def _td_query(sql: str, db: str = TDENGINE_DB, timeout: float = 0.5) -> dict:
    """执行 TDengine REST 查询。

    返回: {column_meta, data, rows}
    异常: TimeoutError / ConnectionError / RuntimeError
    """
    auth = base64.b64encode(
        f"{TDENGINE_USER}:{TDENGINE_PASSWORD}".encode(),
    ).decode()
    url = f"{TDENGINE_BASE}/{db}"
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "text/plain",
    }
    req = urllib.request.Request(
        url, data=sql.encode("utf-8"), headers=headers, method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("code") != 0:
                raise RuntimeError(f"TDengine 错误: {body.get('desc', body)}")
            return body
    except TimeoutError:
        raise
    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            raise TimeoutError(f"TDengine 超时: {e}")
        raise ConnectionError(f"TDengine 不可达: {e}")


def percentile(values: list[float], q: float) -> float:
    """线性插值分位数（`q=0.95` → P95）。

    与 `reports/p0-report-v3-ingest-license.md` §七 的 P95 口径一致（线性插值，非 nearest-rank），
    供 `analyze_sensor` 与工具层复用，避免两套算法各算各的。
    """
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def profile(values: list[float]) -> dict[str, float]:
    """窗口内分布摘要（avg/max/min/p95）——`query_sensor` 契约补齐（Must#3）。"""
    if not values:
        return {"avg": 0.0, "max": 0.0, "min": 0.0, "p95": 0.0}
    return {
        "avg": round(sum(values) / len(values), 4),
        "max": round(max(values), 4),
        "min": round(min(values), 4),
        "p95": round(percentile(values, 0.95), 4),
    }


def query_sensor_columns(
    device_id: str,
    columns: list[str],
    start_ts: int,
    end_ts: int,
    *,
    timeout: float = 0.5,
) -> dict[str, list[dict[str, Any]]]:
    """**一次 SQL 查多列**（同设备、同窗口），返回 `{column: [{"ts","value"}...]}`。

    为什么需要（2026-10-30）：`query_sensor` 是单列接口，N 个测点 = N 次 REST
    往返。串行时单次工具调用的最坏墙钟 = N × timeout，测点多就只能靠「限 N」
    来兜底 —— 而限 N 并没有省时间：它把「一次慢」变成「多次慢」，每批还要多付
    一轮 LLM 往返（`⌈M/N⌉ × C`）。一条 SELECT 查多列把往返压到 1 次，
    使「单次请求测点数」的上限由**延迟**决定回归为**防护**决定。

    口径：
      - `columns` 去重保序（`vib_x/vib_y/vib_z` 同映射 `vib_rms`，重复列只会白查）；
      - 该列为 NULL 的行**跳过**（不把 NULL 当 0 计入统计）；
      - 列名非法/不存在 → 整条 SQL 报错，由调用方按「未登记」分类，不静默返回空。
    """
    uniq = list(dict.fromkeys(c for c in columns if c))
    if not uniq:
        return {}
    for name, val in [("device_id", device_id), *[("column", c) for c in uniq]]:
        if not _SAFE_ID.match(val):
            raise ValueError(f"非法 {name}: {val}")

    if len(uniq) == 1:
        # 单列没有批量收益，直接复用单列接口：行为与改造前**逐字节一致**（回归安全），
        # 也让既有打桩（patch `query_sensor`）继续生效。
        rows = query_sensor(device_id=device_id, metric=uniq[0],
                            start_ts=start_ts, end_ts=end_ts,
                            timeout=timeout)["rows"]
        return {uniq[0]: rows}

    sql = (
        f"SELECT ts, {', '.join(uniq)} "
        f"FROM iot.st_pump_metrics "
        f"WHERE device_id = '{device_id}' "
        f"AND ts >= {start_ts} AND ts < {end_ts} "
        f"ORDER BY ts ASC"
    )

    body = _td_query(sql, timeout=timeout)
    meta = body.get("column_meta") or []
    # 返回列顺序即 meta 顺序；第 0 列固定是 ts
    index_of: dict[str, int] = {}
    for idx, item in enumerate(meta):
        if isinstance(item, (list, tuple)) and item:
            index_of[str(item[0])] = idx

    out: dict[str, list[dict[str, Any]]] = {c: [] for c in uniq}
    for row in body.get("data") or []:
        if not isinstance(row, (list, tuple)) or not row:
            continue
        ts = row[0]
        for col in uniq:
            idx = index_of.get(col)
            if idx is None or idx >= len(row):
                continue
            val = row[idx]
            if val is None:                       # 缺值不当 0（否则均值/最大值全被拉低）
                continue
            out[col].append({"ts": ts, "value": val})
    return out


def query_sensor(
    device_id: str,
    metric: str,
    start_ts: int,
    end_ts: int,
    *,
    timeout: float = 0.5,
) -> dict[str, Any]:
    """查询传感器时序数据。

    参数:
        device_id: 设备 ID（如 "PUMP-A"）
        metric: 测点名（vib_rms / bearing_temp / motor_current ...）
        start_ts: 起始时间戳（epoch ms）
        end_ts:   结束时间戳（epoch ms）
        timeout:  超时（秒）

    返回:
        {"device_id", "metric", "rows": [{"ts", "value"}], "count"}

    异常:
        TimeoutError / ConnectionError / RuntimeError / ValueError
    """
    for name, val in [("device_id", device_id), ("metric", metric)]:
        if not _SAFE_ID.match(val):
            raise ValueError(f"非法 {name}: {val}")

    sql = (
        f"SELECT ts, {metric} "
        f"FROM iot.st_pump_metrics "
        f"WHERE device_id = '{device_id}' "
        f"AND ts >= {start_ts} AND ts < {end_ts} "
        f"ORDER BY ts ASC"
    )

    result = _td_query(sql, timeout=timeout)
    data = result.get("data", [])
    rows = [{"ts": row[0], "value": row[1]} for row in data]

    values = [r["value"] for r in rows if isinstance(r["value"], (int, float))]
    return {
        "device_id": device_id,
        "metric": metric,
        "rows": rows,
        "count": len(rows),
        # Must#3：判据要求 avg/max/min/**p95**/trend，原返回只有 rows/count → 补齐分布摘要
        "stats": profile(values),
    }
