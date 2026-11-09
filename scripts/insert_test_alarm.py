"""插入一条测试告警到 alerts 表（D5 E2E 用：验证前端 alarm:new 实时插入链路）。

用法：
  <REPO>/.venv/Scripts/python.exe scripts/insert_test_alarm.py [--severity critical] [--device "C 0泵"]

说明：
  - 后端 Socket.IO alarm:new 由 2s PG 轮询桥接，插入后 ≤2s 内前端应收到广播。
  - 仅测试用途，数据可由 /api/alarms 看板识别（metric 前缀 e2e_）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
import sys

sys.path.insert(0, ".")

from app.api.db import get_conn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--severity", choices=["info", "warning", "critical"], default="critical")
    parser.add_argument("--device", default="C 0泵")
    parser.add_argument("--metric", default=None)
    args = parser.parse_args()

    metric = args.metric or f"e2e_test_{random.randint(100, 999)}"
    now = dt.datetime.now(dt.timezone.utc)
    alarm_id = f"e2e-{int(now.timestamp() * 1000)}-{random.randint(100, 999)}"
    with get_conn() as conn:
        row = conn.execute(
            """INSERT INTO alerts (alarm_id, device_id, metric, value, severity, status, ts)
               VALUES (%s, %s, %s, %s, %s, 'open', %s)
               RETURNING alarm_id, ts""",
            (alarm_id, args.device, metric, round(random.uniform(5, 9), 2), args.severity, now),
        ).fetchone()
    print(f"INSERTED alarm_id={row['alarm_id']} metric={metric} severity={args.severity}")


if __name__ == "__main__":
    main()
