# -*- coding: utf-8 -*-
"""自建 Sparkplug B 模拟器（验证工具，不进 compose）。

连 Mosquitto 1883，发布 Sparkplug B 报文灌数，覆盖五类边界（docs/sparkplug-b-decoder.md §8）：
  birth      正常 DBIRTH + DDATA（建表 + 写入）
  new_metric DDATA 里新增未知 metric `VIB_BAND_1`（-> st_unmapped_metrics + schema_drift）
  rebirth    重发 DBIRTH，bdSeq 递增（正常 re-birth）
  offline    DDEATH（设备离线）
  ndeath     网关级 NDEATH（该 edge_node 下所有设备置离线 + 聚合告警）

`--scenario` 默认值 = birth,new_metric,rebirth,offline（ndeath 需显式指定）。
发送可靠性：DDATA 走 QoS1；DBIRTH 亦走 QoS1 并计入 PUBACK 等待，避免建表声明丢失。

用法：
    自检（不发布）：       python scripts/spb_simulator.py --selftest
    灌数：                python scripts/spb_simulator.py --scenario birth,new_metric,rebirth,offline
参考：docs/sparkplug-b-decoder.md §八；configs/decoder_schema_mapping.json。
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

# ---------- 项目根定位 ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (PROJECT_ROOT / "protos", PROJECT_ROOT / "configs"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import sparkplug_b_pb2 as spb_pb2  # noqa: E402

NAMESPACE = "spBv1.0"
GROUP_ID = "plant1"
EDGE_NODE_ID = "gw-pump-01"
DEVICE_ID = "PUMP-A"
DEVICE_TYPE = "PUMP_TYPE"

DT_DOUBLE = 10
DT_BOOL = 11
DT_LONG = 4
DT_STRING = 12

NORMAL_METRICS = [
    ("vibration_rms", DT_DOUBLE, 1.25),
    ("vibration_peak", DT_DOUBLE, 3.42),
    ("vibration_kurtosis", DT_DOUBLE, 3.01),
    ("bearing_temp", DT_DOUBLE, 58.7),
    ("motor_current", DT_DOUBLE, 12.3),
    ("pump_speed", DT_DOUBLE, 1450),
]


def add_double(metrics, name, value):
    m = metrics.add()
    m.name = name
    m.timestamp = time.time_ns() // 1_000_000
    m.datatype = DT_DOUBLE
    m.double_value = value
    return m


def add_int(metrics, name, value):
    m = metrics.add()
    m.name = name
    m.timestamp = time.time_ns() // 1_000_000
    m.datatype = DT_LONG
    m.long_value = value
    return m


def add_string(metrics, name, value):
    m = metrics.add()
    m.name = name
    m.timestamp = time.time_ns() // 1_000_000
    m.datatype = DT_STRING
    m.string_value = value
    return m


def add_bool(metrics, name, value):
    m = metrics.add()
    m.name = name
    m.timestamp = time.time_ns() // 1_000_000
    m.datatype = DT_BOOL
    m.boolean_value = value
    return m


def build_dbirth(bdseq: int) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = time.time_ns() // 1_000_000
    p.seq = 0
    add_string(p.metrics, "device_type", DEVICE_TYPE)
    add_int(p.metrics, "bdSeq", bdseq)
    for name, dt, val in NORMAL_METRICS:
        add_double(p.metrics, name, val)
    add_bool(p.metrics, "metric_quality", True)
    return p.SerializeToString()


def build_ddata(seq: int, include_new_metric: bool = False) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = time.time_ns() // 1_000_000
    p.seq = seq
    base = [v * (1 + (seq % 5) * 0.01) for _, _, v in NORMAL_METRICS]
    for (name, dt, _), v in zip(NORMAL_METRICS, base):
        add_double(p.metrics, name, v)
    add_bool(p.metrics, "metric_quality", seq % 10 != 0)
    if include_new_metric:
        add_double(p.metrics, "VIB_BAND_1", 0.77)  # 未登记 -> 旁路
    return p.SerializeToString()


def _add_metric_at(metrics, name, value, ts_ms, datatype):
    """构造 metric，时间戳显式指定（供连续灌数用，替代实时 ts）。"""
    m = metrics.add()
    m.name = name
    m.timestamp = ts_ms
    m.datatype = datatype
    if datatype == DT_DOUBLE:
        m.double_value = value
    elif datatype == DT_BOOL:
        m.boolean_value = value
    return m


# 连续灌数用的值生成（每点独立，支持超限注入）
def _ingest_values(rng, in_alert: bool) -> dict:
    if in_alert:
        # 振动烈度超限段：vib_rms 远超 4.5 mm/s（ISO10816 C区边界）
        vib_rms = 5.5 + rng.uniform(-0.5, 0.6)
        vib_peak = 9.0 + rng.uniform(-0.5, 1.0)
        vib_kurt = 5.5 + rng.uniform(-0.5, 1.0)
    else:
        vib_rms = 1.3 + rng.uniform(-0.3, 0.3)
        vib_peak = 3.4 + rng.uniform(-0.4, 0.5)
        vib_kurt = 3.0 + rng.uniform(-0.15, 0.15)
    return {
        "vibration_rms": vib_rms,
        "vibration_peak": vib_peak,
        "vibration_kurtosis": vib_kurt,
        "bearing_temp": 58.7 + rng.uniform(-0.8, 1.2),
        "motor_current": 12.3 + rng.uniform(-0.4, 0.7),
        "pump_speed": 1450 + rng.uniform(-8, 8),
    }


def build_ddata_t(seq: int, ts_ms: int, values: dict, quality: bool = True) -> bytes:
    """显式时间戳 + 显式值的 DDATA（连续灌数专用）。values: {源metric名: 浮点值}。"""
    p = spb_pb2.Payload()
    p.timestamp = ts_ms
    p.seq = seq
    for name, val in values.items():
        _add_metric_at(p.metrics, name, val, ts_ms, DT_DOUBLE)
    _add_metric_at(p.metrics, "metric_quality", quality, ts_ms, DT_BOOL)
    return p.SerializeToString()


def build_ddeath(seq: int) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = time.time_ns() // 1_000_000
    p.seq = seq
    return p.SerializeToString()


def build_ndeath(seq: int) -> bytes:
    return build_ddeath(seq)


def topic(message_type: str) -> str:
    return f"{NAMESPACE}/{GROUP_ID}/{message_type}/{EDGE_NODE_ID}/{DEVICE_ID}"


def edge_topic(message_type: str) -> str:
    """网关级主题（无 device_id），用于 NBIRTH/NDATA/NDEATH。"""
    return f"{NAMESPACE}/{GROUP_ID}/{message_type}/{EDGE_NODE_ID}"


def run_ingest(client, args) -> None:
    """连续灌数模式：多设备 × 长时间窗 × 1Hz，首设备注入振动超限段。

    供 query_sensor 聚合测试 + 路线 A（阈值+滑动窗口）告警验证提供真实链路数据。
    时间戳按 interval_ms 逻辑递增（加速灌入），起始时间在当前实时之后，避免乱序。
    仅首设备（args.devices[0]）注入超限段，其余设备正常，用于验证告警精确定位。

    发送可靠性：QoS1 + 手动单线程 loop（不用 loop_start）+ PUBACK 计数等待，
    避免 QoS0 大批量发布在断开时丢弃未发送报文。
    """
    # MAGIC: QoS1 可靠发送（QoS0 大批量发布会被 paho 在断开时丢弃，导致灌数不完整）
    ACKED = {"n": 0}
    TOTAL = {"n": 0}

    def on_publish(client_, userdata_, mid, reason_code, properties=None):
        ACKED["n"] += 1

    client.on_publish = on_publish

    # 等待连接就绪（CONNACK 由手动 loop 处理）
    t0 = time.time()
    while not client.is_connected() and time.time() - t0 < 15:
        client.loop(timeout=0.1)
        time.sleep(0.02)

    rng = random.Random(args.seed)
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    alert_dev = devices[0]
    total_ms = int(args.hours * 3600 * 1000)
    alert_start_ms = int(total_ms * args.alert_start_ratio)
    alert_ms = int(args.alert_duration_min * 60 * 1000)
    period = args.interval_ms
    n_points = total_ms // period
    base_ts = int(time.time() * 1000) + 60_000  # 现有最新数据之后

    for dev in devices:
        dtopic = f"{NAMESPACE}/{GROUP_ID}/DDATA/{EDGE_NODE_ID}/{dev}"
        btopic = f"{NAMESPACE}/{GROUP_ID}/DBIRTH/{EDGE_NODE_ID}/{dev}"
        client.publish(btopic, build_dbirth(args.bdseq), qos=1)
        TOTAL["n"] += 1          # DBIRTH 也计入 PUBACK 等待，确保建表/设备类型声明送达
        seq = args.bdseq
        is_alert_dev = dev == alert_dev
        for k in range(n_points):
            offset = k * period
            in_alert = is_alert_dev and (alert_start_ms <= offset < alert_start_ms + alert_ms)
            vals = _ingest_values(rng, in_alert)
            seq = (seq + 1) % 256
            client.publish(dtopic, build_ddata_t(seq, base_ts + offset, vals), qos=1)
            TOTAL["n"] += 1
            if k % 200 == 199:
                client.loop(timeout=0.0)
        print(f"[simulator] ingest dev={dev} 发布 {n_points} 点 seq收尾={seq}")

    # 等待所有 PUBACK（确认全部送达 broker）
    ack_deadline = time.time() + args.wait_send_s
    while ACKED["n"] < TOTAL["n"] and time.time() < ack_deadline:
        client.loop(timeout=0.05)
        time.sleep(0.01)
    print(f"[simulator] ingest 共发布 {TOTAL['n']} 点，收到 PUBACK {ACKED['n']}（"
          f"{'全部送达' if ACKED['n'] == TOTAL['n'] else '有丢失！'}，首设备 {alert_dev} 含超限段）")

    # 轮询 TDengine 落库行数（REST 6041），避免脚本提前结束导致数据未写完
    target_new = TOTAL["n"]
    try:
        import taosrest
        conn = taosrest.connect(
            url=f"http://{args.td_host}:{args.td_port}",
            user="root", password=args.td_password, timeout=5,
        )
        start = int(conn.query("SELECT COUNT(*) FROM iot.st_pump_metrics").data[0][0])
        deadline = time.time() + args.wait_s
        while time.time() < deadline:
            try:
                got = int(conn.query("SELECT COUNT(*) FROM iot.st_pump_metrics").data[0][0]) - start
            except Exception:
                got = 0
            if got >= target_new:
                print(f"[simulator] 已落库 {got}/{target_new} 点")
                return
            time.sleep(2)
        print(f"[simulator] 超时未落满：当前增量 {got}/{target_new}，请手动核对 debug 落库")
    except Exception as e:
        print(f"[simulator] 落库轮询不可用（{e}），已停止发送，请稍后手动验证")


def run_scenario(client, scenario: str, bdseq: int) -> int:
    seq = 0
    ns = {  # 各场景发布条数（供摘要）
        "birth": 3, "new_metric": 2, "rebirth": 2, "offline": 1, "ndeath": 1,
    }.get(scenario, 1)
    if scenario == "birth":
        client.publish(topic("DBIRTH"), build_dbirth(bdseq), qos=0)
        time.sleep(0.2)
        for _ in range(2):
            seq += 1
            client.publish(topic("DDATA"), build_ddata(seq), qos=0)
            time.sleep(0.2)
    elif scenario == "new_metric":
        seq += 1
        client.publish(topic("DDATA"), build_ddata(seq, include_new_metric=True), qos=0)
    elif scenario == "rebirth":
        bdseq += 1
        client.publish(topic("DBIRTH"), build_dbirth(bdseq), qos=0)
        time.sleep(0.2)
        seq += 1
        client.publish(topic("DDATA"), build_ddata(seq), qos=0)
    elif scenario == "offline":
        client.publish(topic("DDEATH"), build_ddeath(seq + 1), qos=0)
    elif scenario == "ndeath":
        client.publish(edge_topic("NDEATH"), build_ndeath(seq + 1), qos=0)
    print(f"[simulator] scenario={scenario} 发布 {ns} 条 flow，bdSeq={bdseq}")
    return bdseq


class SelfTest:
    @staticmethod
    def run(bdseq: int = 1001) -> bool:
        ok = True

        def check(name: str, cond: bool, detail: str = ""):
            nonlocal ok
            if not cond:
                ok = False
            print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))

        # DBIRTH 往返
        buf = build_dbirth(bdseq)
        p = spb_pb2.Payload()
        p.ParseFromString(buf)
        names = {m.name for m in p.metrics}
        check("DBIRTH 往返 & 含 bdSeq/device_type",
              "bdSeq" in names and "device_type" in names and len(p.metrics) == 9)
        bd = [m.long_value for m in p.metrics if m.name == "bdSeq"][0]
        check("bdSeq 值", bd == bdseq, str(bd))

        # DDATA new_metric 含未登记 metric
        buf2 = build_ddata(5, include_new_metric=True)
        p2 = spb_pb2.Payload()
        p2.ParseFromString(buf2)
        has_unknown = any(m.name == "VIB_BAND_1" for m in p2.metrics)
        check("DDATA 含未知 metric VIB_BAND_1", has_unknown)
        check("DDATA seq", p2.seq == 5)

        # DDEATH 往返
        buf3 = build_ddeath(9)
        p3 = spb_pb2.Payload()
        p3.ParseFromString(buf3)
        check("DDEATH 往返 & seq", p3.seq == 9)

        print("SELFTEST " + ("PASS" if ok else "FAIL"))
        return ok


def main():
    ap = argparse.ArgumentParser(description="自建 Sparkplug B 模拟器")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--host", default=os.environ.get("MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    ap.add_argument("--scenario", default="birth,new_metric,rebirth,offline",
                    help="逗号分隔场景")
    ap.add_argument("--bdseq", type=int, default=1001, help="初始 bdSeq")

    # ---- 连续灌数模式（query_sensor 聚合 + 告警验证用）----
    ap.add_argument("--ingest", action="store_true", help="启用连续灌数模式（替代 --scenario）")
    ap.add_argument("--hours", type=float, default=2.0, help="逻辑时间跨度（小时）")
    ap.add_argument("--interval-ms", type=int, default=1000, help="采样间隔 ms（默认 1Hz）")
    ap.add_argument("--devices", default="PUMP-A,PUMP-B,PUMP-C", help="逗号分隔设备 id（首设备注入超限）")
    ap.add_argument("--alert-start-ratio", type=float, default=0.5, help="超限段起始位置（逻辑时间窗比例）")
    ap.add_argument("--alert-duration-min", type=float, default=25.0, help="超限段持续时间（分钟）")
    ap.add_argument("--seed", type=int, default=20260928, help="随机种子")
    ap.add_argument("--td-host", default=os.environ.get("TD_HTTP_HOST", "127.0.0.1"))
    ap.add_argument("--td-port", type=int, default=int(os.environ.get("TD_HTTP_PORT", "6041")))
    ap.add_argument("--td-password", default="taosdata")
    ap.add_argument("--wait-s", type=int, default=180, help="落库轮询超时（秒）")
    ap.add_argument("--wait-send-s", type=int, default=120, help="PUBACK 等待超时（秒）")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if SelfTest.run(args.bdseq) else 1)

    if args.ingest:
        # 连续灌数：QoS1 手动 loop（run_ingest 内部驱动），不使用 loop_background
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="auscult-spb-simulator")
        client.connect(args.host, args.port, keepalive=60)
        run_ingest(client, args)
        client.disconnect()
        print("[simulator] 完成")
        return

    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="auscult-spb-simulator")
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    bdseq = args.bdseq
    for sc in [s.strip() for s in args.scenario.split(",") if s.strip()]:
        bdseq = run_scenario(client, sc, bdseq)
        time.sleep(0.4)
    client.loop_stop()
    client.disconnect()
    print("[simulator] 完成")


if __name__ == "__main__":
    main()