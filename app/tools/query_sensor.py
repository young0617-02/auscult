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
import re
import urllib.error
import urllib.request
from typing import Any

TDENGINE_BASE = "http://127.0.0.1:6041/rest/sql"
TDENGINE_DB = "iot"
TDENGINE_USER = "root"
TDENGINE_PASSWORD = "taosdata"

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

    return {
        "device_id": device_id,
        "metric": metric,
        "rows": rows,
        "count": len(rows),
    }
