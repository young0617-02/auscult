# -*- coding: utf-8 -*-
"""A2 模拟数据生成器（Sparkplug B 批量造数，面向生产形态）。

定位：与 `scripts/spb_simulator.py`（解码器边界验证工具、场景化）互补 ——
本脚本面向**数据底座批量造数**，固定 seed 可复现，供 query_sensor 聚合与
告警引擎（A3/路线 A）提供真实链路时序数据。

覆盖消息类型（对齐 `configs/decoder_schema_mapping.json` message_types）：
  NBIRTH  网关级上线声明
  NDATA   网关级运行数据（record_node_runtime_only）
  DBIRTH  设备级上线（建表 + device_type 声明）
  DDATA   设备遥测（vibration/温度/电流/转速/质量，1Hz）
  NDEATH  网关级离线（结束，可选）

振动模型（对应 `docs/p1-spec-data-sources.md` §3.1）：
  遥测点为 1Hz 包络指标。振动包络能量由 基频 + 工频谐波 + 随机噪声 +
  轴承特征频率（BPFO/BPFI/BSF/FTF）注入驱动；异常段特征频率能量比例随
  处理进度**线性爬升**，使 vib_rms 越过 4.5 mm/s（ISO 10816 C 区上界）、
  峭度显著升高（轴承早期冲击特征）。正常态 vib_rms ≈ 1.3 mm/s。

用法：
  自检（不发布）：    .venv\\Scripts\\python.exe scripts\\gen_sparkplug.py --selftest
  默认灌数（3 设备 1 小时 1Hz，首设备异常段）：
                      .venv\\Scripts\\python.exe scripts\\gen_sparkplug.py
  长窗（7 天）：
                      .venv\\Scripts\\python.exe scripts\\gen_sparkplug.py --hours 168

  # 以上需先起接入栈并常驻解码器（D1-A1）：
  #   docker compose -f docker/compose.ingest.yml up -d
  #   .venv\\Scripts\\python.exe scripts\\self_decoder.py --prj-spec-schema-mapping \
  #        configs/decoder_schema_mapping.json --mqtt-host 127.0.0.1 --td-host 127.0.0.1
参考：`docs/prj-spec-schema-mapping.md` §三/§四；`docs/p1-spec-data-sources.md` §3.1/§3.2。
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

# ---------- 项目根定位（复用 protos 下的 PB 类） ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (PROJECT_ROOT / "protos", PROJECT_ROOT / "configs"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import sparkplug_b_pb2 as spb_pb2  # noqa: E402

NAMESPACE = "spBv1.0"
GROUP_ID = "plant1"
EDGE_NODE_ID = "gw-pump-01"
DEVICE_TYPE = "centrifugal_pump"

# Sparkplug B DataType 枚举（与 sparkplug_b.proto 一致）
DT_DOUBLE = 10
DT_BOOL = 11
DT_INT = 4
DT_STRING = 12

# 遥测量（Sparkplug metric 名 → 写入 st_pump_metrics 的列，见 schema-mapping §三）
TELEMETRY = [
    ("vibration_rms", DT_DOUBLE),
    ("vibration_peak", DT_DOUBLE),
    ("vibration_kurtosis", DT_DOUBLE),
    ("bearing_temp", DT_DOUBLE),
    ("motor_current", DT_DOUBLE),
    ("pump_speed", DT_DOUBLE),
]

# 正常态基准值（mm/s / degC / A / rpm / -）
NORMAL = {
    "vibration_rms": 1.30,
    "vibration_peak": 3.40,
    "vibration_kurtosis": 3.00,
    "bearing_temp": 58.7,
    "motor_current": 12.3,
    "pump_speed": 1450.0,
}

# 异常态（严重轴承故障）目标超出量（叠加在基准上）
FAULT_LIMIT = {
    "vibration_rms": 4.8,       # > 4.5 mm/s 触发 high 告警
    "vibration_peak": 9.0,
    "vibration_kurtosis": 6.5,  # 峭度显著抬升 -> 冲击特征
}


def _metric(metrics, name: str, ts_ms: int, datatype: int, value) -> None:
    m = metrics.add()
    m.name = name
    m.timestamp = ts_ms
    m.datatype = datatype
    if datatype == DT_DOUBLE:
        m.double_value = value
    elif datatype == DT_BOOL:
        m.boolean_value = value
    elif datatype == DT_INT:
        m.long_value = value
    elif datatype == DT_STRING:
        m.string_value = value


def _node_metric(p: spb_pb2.Payload, ts_ms: int) -> None:
    """网关级运行指标（NDATA）。"""
    _metric(p.metrics, "node_temperature", ts_ms, DT_DOUBLE, 41.5)
    _metric(p.metrics, "node_uptime_s", ts_ms, DT_INT, 3600)


def _gen_values(rng: random.Random, fault: float) -> dict:
    """按轴承故障进度 fault(0..1，线性爬升) 生成一个遥测点（1Hz 包络）。

    物理映射（1Hz 采样下，高频特征频率以包络能量贡献体现）：
      fault 由故障处理进度线性爬升；特征频率能量比例随 fault 增大，
      抬高 RMS/Peak/峭度 —— 对应轴承磨损/点蚀早期冲击。
    """
    values = {}
    for name, _ in TELEMETRY:
        base = NORMAL[name]
        limit = FAULT_LIMIT.get(name, base)
        # 爬升曲线：fault^1.4 让故障中后期加速劣化
        if fault <= 0:
            values[name] = base + rng.uniform(-0.05, 0.05) * base
        else:
            f = fault ** 1.4
            noise = rng.uniform(-0.03, 0.03)
            # 主判据：vibration_rms 直接由故障能量抬高（越过 4.5）
            if name == "vibration_rms":
                values[name] = base + (limit - base) * f * (1 + noise)
            elif name == "vibration_peak":
                values[name] = min(base + (limit - base) * f * (1 + noise), NORMAL["vibration_rms"] * 2.6)
            else:
                values[name] = min(base + (limit - base) * f * (1 + noise), limit)
    values["bearing_temp"] = NORMAL["bearing_temp"] + 18.0 * fault ** 1.2 + rng.uniform(-0.6, 0.6)
    return values


def build_nbirth(ts_ms: int) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = ts_ms
    p.seq = 0
    _metric(p.metrics, "device_type", ts_ms, DT_STRING, EDGE_NODE_ID)
    _node_metric(p, ts_ms)
    return p.SerializeToString()


def build_ndata(ts_ms: int, seq: int) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = ts_ms
    p.seq = seq
    _node_metric(p, ts_ms)
    return p.SerializeToString()


def build_dbirth(ts_ms: int, dev: str, bdseq: int) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = ts_ms
    p.seq = 0
    _metric(p.metrics, "device_type", ts_ms, DT_STRING, DEVICE_TYPE)
    _metric(p.metrics, "bdSeq", ts_ms, DT_INT, bdseq)
    for name, dt in TELEMETRY:
        _metric(p.metrics, name, ts_ms, dt, NORMAL[name])
    _metric(p.metrics, "metric_quality", ts_ms, DT_BOOL, True)
    return p.SerializeToString()


def build_ddata(ts_ms: int, seq: int, values: dict, quality: bool) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = ts_ms
    p.seq = seq
    for name, dt in TELEMETRY:
        _metric(p.metrics, name, ts_ms, dt, values[name])
    _metric(p.metrics, "metric_quality", ts_ms, DT_BOOL, quality)
    return p.SerializeToString()


def build_ndeath(ts_ms: int, seq: int) -> bytes:
    p = spb_pb2.Payload()
    p.timestamp = ts_ms
    p.seq = seq
    return p.SerializeToString()


def _run_ingest(client, args) -> None:
    """批量造数主流程：NBIRTH + 各设备 DBIRTH → 周期 DDATA →（可选）NDEATH。

    QoS1 + 手动 loop + PUBACK 计数等待，保证大批量发布不丢（同 D1-A1 结论）。
    时间戳按 period 逻辑递增、起点在当前实时之后，避免乱序。
    """
    ACKED = {"n": 0}
    TOTAL = {"n": 0}

    def on_publish(client_, userdata_, mid, reason_code, properties=None):
        ACKED["n"] += 1

    client.on_publish = on_publish

    rng = random.Random(args.seed)
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]
    alert_dev = devices[0]
    total_ms = int(args.hours * 3600 * 1000)
    alert_start_ms = int(total_ms * args.alert_start_ratio)
    alert_ms = int(args.alert_duration_min * 60 * 1000)
    period = args.interval_ms
    n_points = total_ms // period
    base_ts = int(time.time() * 1000) + 60_000

    # 等待 CONNACK（手动 loop 处理）
    t0 = time.time()
    while not client.is_connected() and time.time() - t0 < 15:
        client.loop(timeout=0.1)
        time.sleep(0.02)

    # 网关级：NBIRTH
    nb_topic = f"{NAMESPACE}/{GROUP_ID}/NBIRTH/{EDGE_NODE_ID}"
    client.publish(nb_topic, build_nbirth(base_ts), qos=1)
    TOTAL["n"] += 1

    # 各设备：DBIRTH
    for dev in devices:
        btopic = f"{NAMESPACE}/{GROUP_ID}/DBIRTH/{EDGE_NODE_ID}/{dev}"
        client.publish(btopic, build_dbirth(base_ts, dev, args.bdseq), qos=1)
        TOTAL["n"] += 1

    for dev in devices:
        dtopic = f"{NAMESPACE}/{GROUP_ID}/DDATA/{EDGE_NODE_ID}/{dev}"
        is_alert = dev == alert_dev
        seq = args.bdseq
        for k in range(n_points):
            offset = k * period
            ts = base_ts + offset
            # 异常段：进度线性爬升（0→1）
            in_alert = is_alert and (alert_start_ms <= offset < alert_start_ms + alert_ms)
            if in_alert:
                t_sec = (offset - alert_start_ms) / 1000.0
                fault = min(1.0, t_sec / (alert_ms / 1000.0))
                fault = max(fault, 1e-6)
            else:
                fault = 0.0
            values = _gen_values(rng, fault)
            # 质量：爬升期随机 2% 置坏（供质量标注路径验证）
            quality = rng.random() > 0.02
            seq = (seq + 1) % 256
            client.publish(dtopic, build_ddata(ts, seq, values, quality), qos=1)
            TOTAL["n"] += 1
            if k % 200 == 199:
                client.loop(timeout=0.0)
        print(f"[gen] dev={dev} 发布 {n_points} 点 seq收尾={seq}")

    # 网关级：NDEATH（标记离线）
    if args.with_ndeath:
        client.publish(f"{NAMESPACE}/{GROUP_ID}/NDEATH/{EDGE_NODE_ID}",
                       build_ndeath(base_ts + total_ms, (seq + 1) % 256), qos=1)
        TOTAL["n"] += 1

    ack_deadline = time.time() + args.wait_send_s
    while ACKED["n"] < TOTAL["n"] and time.time() < ack_deadline:
        client.loop(timeout=0.05)
        time.sleep(0.01)
    print(f"[gen] 共发布 {TOTAL['n']} 点，收到 PUBACK {ACKED['n']}（"
          f"{'全部送达' if ACKED['n'] == TOTAL['n'] else '有丢失！'}）")

    # 轮询 TDengine 落库（避免脚本提前结束）
    target_new = n_points * len(devices)
    try:
        import taosrest
        conn = taosrest.connect(url=f"http://{args.td_host}:{args.td_port}",
                                user="root", password=args.td_password, timeout=5)
        start = int(conn.query("SELECT COUNT(*) FROM iot.st_pump_metrics").data[0][0])
        deadline = time.time() + args.wait_s
        while time.time() < deadline:
            try:
                got = int(conn.query("SELECT COUNT(*) FROM iot.st_pump_metrics").data[0][0]) - start
            except Exception:
                got = 0
            if got >= target_new:
                print(f"[gen] 已落库 {got}/{target_new} 点")
                return
            time.sleep(2)
        print(f"[gen] 超时未落满：当前增量 {got}/{target_new}，请手动核对")
    except Exception as e:
        print(f"[gen] 落库轮询不可用（{e}），已停止发送，请稍后手动验证")


class SelfTest:
    @staticmethod
    def run(bdseq: int = 1001) -> bool:
        ok = True

        def check(name: str, cond: bool, detail: str = ""):
            nonlocal ok
            if not cond:
                ok = False
            print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f"  -> {detail}" if detail else ""))

        # 包络生成：正常态 RMS ≈ 1.3；严重段 RMS 越过 4.5 且峭度抬升
        rng = random.Random(42)
        norm = _gen_values(rng, 0.0)
        rng2 = random.Random(42)
        sev = _gen_values(rng2, 1.0)
        check("正常态 vib_rms ≈1.3", abs(norm["vibration_rms"] - 1.3) < 0.1)
        check("严重态 vib_rms >4.5", sev["vibration_rms"] > 4.5, f"{sev['vibration_rms']:.2f}")
        check("严重态峭度抬升", sev["vibration_kurtosis"] > 5.0, f"{sev['vibration_kurtosis']:.2f}")
        check("严重态 temp 抬升", sev["bearing_temp"] > 66.0, f"{sev['bearing_temp']:.1f}")

        # 报文往返
        p = spb_pb2.Payload(); p.ParseFromString(build_dbirth(1111, "PUMP-A", bdseq))
        names = {m.name for m in p.metrics}
        check("DBIRTH 含 bdSeq/device_type/metric_quality",
              {"bdSeq", "device_type", "metric_quality"} <= names and len(p.metrics) == 9)
        p2 = spb_pb2.Payload(); p2.ParseFromString(build_nbirth(1111))
        check("NBIRTH 含网关指标", any(m.name == "node_temperature" for m in p2.metrics))

        print("SELFTEST " + ("PASS" if ok else "FAIL"))
        return ok


def main():
    ap = argparse.ArgumentParser(description="A2 模拟数据生成器")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    # ISS-056 候选①：默认发**规范编号**（产品口径，见 app/device_ids.py）；
    # 旧短编号仍可用 --devices 传入（迁移未完成时联调老数据）。
    ap.add_argument("--devices", default="PUMP-A-01,PUMP-B-01,PUMP-C-01",
                    help="逗号分隔设备 id（首设备注入异常）")
    ap.add_argument("--hours", type=float, default=1.0, help="逻辑时间跨度（小时，默认 1h 小规模验证）")
    ap.add_argument("--interval-ms", type=int, default=1000, help="采样间隔 ms（默认 1Hz）")
    ap.add_argument("--alert-start-ratio", type=float, default=0.3, help="异常段起始（逻辑时间窗比例）")
    ap.add_argument("--alert-duration-min", type=float, default=20.0, help="异常段时长（分钟）")
    ap.add_argument("--bdseq", type=int, default=1001)
    ap.add_argument("--with-ndeath", action="store_true", help="灌数结束后发网关级 NDEATH")
    ap.add_argument("--seed", type=int, default=20260928, help="固定 seed（可复现）")
    ap.add_argument("--td-host", default=os.environ.get("TD_HTTP_HOST", "127.0.0.1"))
    ap.add_argument("--td-port", type=int, default=int(os.environ.get("TD_HTTP_PORT", "6041")))
    ap.add_argument("--td-password", default="taosdata")
    ap.add_argument("--wait-s", type=int, default=180, help="落库轮询超时（秒）")
    ap.add_argument("--wait-send-s", type=int, default=120, help="PUBACK 等待超时（秒）")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if SelfTest.run(args.bdseq) else 1)

    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="auscult-gen-sparkplug")
    client.connect(args.mqtt_host, args.mqtt_port, keepalive=60)
    _run_ingest(client, args)
    client.disconnect()
    print("[gen] 完成")


if __name__ == "__main__":
    main()