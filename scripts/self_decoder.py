# -*- coding: utf-8 -*-
"""自研 Sparkplug B 解码器（消费者侧）。

职责：订阅 Mosquitto 上的 Sparkplug B 报文 -> 解析 Protobuf -> 按
``configs/decoder_schema_mapping.json`` 映射写入 TDengine（走 REST 6041）。

- M2  订阅与报文分流（paho-mqtt）
- M3  DBIRTH：建表/校验 + 记录 bdSeq
- M4  DDATA：逐 metric 映射写入（未登记 -> st_unmapped_metrics + schema_drift 告警）
- M5  DDEATH / NDEATH：在线状态翻转
- M6  re-birth / 冲突判定（bdSeq 比对、quality_ok 标注）

用法：
    自检（不依赖网络/容器）：  python scripts/self_decoder.py --selftest
    常驻运行（本地直跑，方案 A，2026-09-29）：
        本地 /venv python 直跑（不再经 compose 容器），默认即连 127.0.0.1
        的 Mosquitto(1883) / TDengine(6041)：
        .venv\\Scripts\\python.exe scripts\\self_decoder.py \
            --prj-spec-schema-mapping configs/decoder_schema_mapping.json \
            --mqtt-host 127.0.0.1 --td-host 127.0.0.1
        # sub-topic 默认取 env SPB_SUB_TOPIC，未设时落到代码默认值
说明：
    曾由 docker/compose.ingest.yml 以容器方式常驻（Dockerfile.decoder），
    2026-09-29 裁决改为本地直跑；Dockerfile.decoder 保留（弃用注释）供审计追溯。
参考：docs/p0-design-sparkplug-decoder.md（M1–M6、四类边界）；docs/prj-spec-schema-mapping.md §5.1–§5.4。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------- 项目根定位（脚本位于 scripts/ 下） ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
for _p in (PROJECT_ROOT / "protos", PROJECT_ROOT / "configs"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import sparkplug_b_pb2 as spb_pb2  # noqa: E402  (生成的 PB 类, M1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("self_decoder")

# Sparkplug B DataType 枚举值（见 sparkplug_b.proto）
DT_DOUBLE = 10
DT_FLOAT = 9
DT_BOOL = 11
DT_STRING = 12


# =====================================================================
# 配置装载（解码器只读 configs/decoder_schema_mapping.json，不硬编码映射）
# =====================================================================
class DecoderConfig:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else PROJECT_ROOT / "configs" / "decoder_schema_mapping.json"
        self.cfg = json.loads(self.path.read_text(encoding="utf-8"))

    def stable(self, name: str) -> dict:
        for s in self.cfg["stables"]:
            if s["name"] == name:
                return s
        raise KeyError(f"超级表未定义: {name}")

    @property
    def group_id(self) -> str:
        return self.cfg["sparkplug"]["group_id"]

    @property
    def database(self) -> dict:
        return self.cfg["database"]

    @property
    def message_types(self) -> dict:
        return self.cfg["message_types"]

    @property
    def device_id_regex(self) -> str:
        return self.cfg["device_id_validation"]["regex"]

    def metric_to_column(self, stable_name: str, metric_name: str) -> Optional[dict]:
        """返回该 metric 在 stable 上的映射项（含 column/tag/datatype），未映射返回 None。"""
        for m in self.stable(stable_name).get("metric_mapping", []):
            if m["metric_name"] == metric_name:
                return m
        return None


# =====================================================================
# Topic 解析（M2）
# =====================================================================
@dataclass
class Topic:
    namespace: str
    group_id: str
    message_type: str
    edge_node_id: str
    device_id: Optional[str] = None

    @property
    def is_device_level(self) -> bool:
        return bool(self.device_id)


class TopicParser:
    """解析 ``spBv1.0/{group}/{message_type}/{edge_node_id}/{device_id:?}``。

    `is_valid_device` 落实 `configs/decoder_schema_mapping.json`
    `device_id_validation.regex`（R-V3-5）。该正则是**解码侧宽松口径**：
    只拦"非法标识符 / SQL 注入面"（反引号、空格、引号等），
    与 `schemas/tools_v1.json` 面向用户的**严格命名口径**
    `^[A-Z][A-Z0-9-]{2,31}$` 用途不同，两者并存关系见 `docs/prj-spec-schema-mapping.md` §六。
    """

    def __init__(self, cfg: DecoderConfig):
        self._regex = re.compile(r"^([^/]+)/([^/]+)/([^/]+)/([^/]+)(?:/([^/]+))?$")
        self._device_re = re.compile(cfg.device_id_regex)

    def is_valid_device(self, device_id: Optional[str]) -> bool:
        """device_id 是否满足解码侧校验规则（None / 空串一律视为非法）。"""
        return bool(device_id) and bool(self._device_re.match(device_id))

    def parse(self, topic_str: str, enforce_device: bool = False) -> Optional[Topic]:
        m = self._regex.match(topic_str)
        if not m:
            return None
        namespace, group_id, message_type, edge_node_id, device_id = m.groups()
        t = Topic(namespace, group_id, message_type, edge_node_id, device_id)
        if enforce_device and (not t.is_device_level or not self.is_valid_device(t.device_id)):
            return None
        return t


# =====================================================================
# Payload / metric 辅助（M1、M4）
# =====================================================================
def decode_payload(buf: bytes) -> spb_pb2.Payload:
    p = spb_pb2.Payload()
    p.ParseFromString(buf)
    return p


def metric_value(metric) -> Tuple[str, object]:
    """返回 (datatype 字符串, python 值)。datatype 字符串取值 Double/Float/Boolean/String。"""
    if metric.HasField("double_value"):
        return "Double", metric.double_value
    if metric.HasField("float_value"):
        return "Float", metric.float_value
    if metric.HasField("boolean_value"):
        return "Boolean", metric.boolean_value
    if metric.HasField("long_value"):
        return "Long", metric.long_value
    if metric.HasField("int_value"):
        return "Int", metric.int_value
    if metric.HasField("string_value"):
        return "String", metric.string_value
    return "None", None


def metric_value_raw(metric) -> object:
    """取 oneof 里已设置分支的原始 python 值（未设置返回 None）。"""
    _, v = metric_value(metric)
    return v


# =====================================================================
# SQL 组装（INSERT ... USING ... TAGS()，prj-spec-schema-mapping §4.4）
# =====================================================================
def _quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _fmt_tag(v: object) -> str:
    return _quote(str(v))


def _fmt_col_val(v: object, col_type: str) -> str:
    t = col_type.upper()
    if "BOOL" in t:
        return "true" if bool(v) else "false"
    if "NCHAR" in t or "VARCHAR" in t or "TEXT" in t:
        return _quote(str(v))
    if "TIMESTAMP" in t:
        return str(int(v))
    # 数值
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


class SqlBuilder:
    """由 stable 定义 + tags + 列值生成 TDengine 插入语句。"""

    def __init__(self, cfg: DecoderConfig):
        self.cfg = cfg

    def create_database_sql(self) -> str:
        db = self.cfg.database
        return (
            f"CREATE DATABASE IF NOT EXISTS {db['name']} "
            f"KEEP {db['keep_days']} DURATION {db['duration_days']} "
            f"PRECISION '{db['precision']}' WAL_LEVEL {db['wal_level']};"
        )

    def create_stable_sql(self, stable: dict) -> str:
        cols = ", ".join(
            f"{c['name']} {c['type']}" for c in stable["columns"]
        )
        tags = ", ".join(f"{t['name']} {t['type']}" for t in stable["tags"])
        return (
            f"CREATE STABLE IF NOT EXISTS {self.cfg.database['name']}.{stable['name']} "
            f"({cols}) TAGS ({tags});"
        )

    def insert_using_sql(
        self,
        stable: dict,
        subtable: str,
        tag_values: List[object],
        column_values: Dict[str, object],
        extra_columns: Optional[Dict[str, object]] = None,
    ) -> str:
        """根据列值生成 ``INSERT INTO sub USING stable TAGS(...) (cols) VALUES (...)``。"""
        col_values = dict(column_values)
        if extra_columns:
            col_values.update(extra_columns)
        tag_types = [t["type"] for t in stable["tags"]]
        # 对齐 stable 定义中的列顺序
        col_defs = {c["name"]: c["type"] for c in stable["columns"]}
        names, vals = [], []
        for cname, ctype in col_defs.items():
            if cname in col_values:
                names.append(cname)
                vals.append(_fmt_col_val(col_values[cname], ctype))
        # 自定义列（加在主列之后）
        for cname, v in col_values.items():
            if cname not in col_defs:
                names.append(cname)
                vals.append(_fmt_col_val(v, "DOUBLE"))
        tag_args = ", ".join(_fmt_tag(v) for v in tag_values)
        db = self.cfg.database["name"]
        # 标识符统一加反引号：子表名含 '-'（如 d_plant1_PUMP-A），TDengine 不加引号会被当作表达式
        return (
            f"INSERT INTO `{db}`.`{subtable}` USING `{db}`.`{stable['name']}` "
            f"TAGS({tag_args}) ({', '.join(names)}) VALUES ({', '.join(vals)})"
        )

    def table_for(self, stable: dict, group_id: str, device_id: str) -> str:
        template = stable.get("subtable_naming", "d_{group_id}_{device_id}")
        return template.format(group_id=group_id, device_id=device_id)


# =====================================================================
# TDengine 写入（taosrest / 6041）
# =====================================================================
# 拼进 SQL 的 TAG 值白名单：与 configs/decoder_schema_mapping.json
# device_id_validation.regex 同口径，防止标识符注入（R-V3-5）
_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class DbWriter:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self._url = f"http://{host}:{port}"
        self._user = user
        self._password = password
        self._database = database
        self._conn = None

    def _ensure_conn(self):
        if self._conn is None:
            import taosrest

            self._conn = taosrest.connect(
                url=self._url, user=self._user, password=self._password, database=self._database
            )
        return self._conn

    def init_schema(self, cfg: DecoderConfig, builder: SqlBuilder):
        conn = self._ensure_conn()
        conn.execute(builder.create_database_sql())
        for name in ("st_pump_metrics", "st_unmapped_metrics", "st_device_status"):
            conn.execute(builder.create_stable_sql(cfg.stable(name)))

    def execute(self, sql: str):
        conn = self._ensure_conn()
        conn.execute(sql)

    def query_last_birth_seq(self, group_id: str, edge_node_id: str, device_id: str) -> Optional[int]:
        """查询 `st_device_status` 中该设备**已持久化**的最近 bdSeq。

        ⚠️ 接入状态：M6 冲突判定当前走**内存** DeviceRegistry.birth_seq（见 `_handle_dbirth`），
        本方法是"以持久化 bdSeq 为权威"的**预留路径，尚未接入主链路**。
        接入前，报告与文档不得声称 "re-birth 比对以 st_device_status 为准"。
        """
        for value in (group_id, edge_node_id, device_id):
            if not _SAFE_TAG_RE.match(value or ""):
                raise ValueError(f"非法标识符，拒绝拼入 SQL：{value!r}")
        conn = self._ensure_conn()
        res = conn.query(
            f"SELECT last(birth_seq) FROM `{self._database}`.st_device_status "
            f"WHERE group_id='{group_id}' AND edge_node_id='{edge_node_id}' "
            f"AND device_id='{device_id}'"
        )
        rows = res.data
        if rows and rows[0] and rows[0][0] is not None:
            return int(rows[0][0])
        return None


# =====================================================================
# 设备状态（M6 re-birth / 冲突判定）
# =====================================================================
@dataclass
class DeviceState:
    device_id: str
    birth_seq: Optional[int] = None
    device_type: Optional[str] = None
    online: bool = False
    last_seq: int = 0


class DeviceRegistry:
    """内存维护设备级状态；bdSeq 冲突判定走 M6 规则。"""

    def __init__(self):
        self._devices: Dict[Tuple[str, str, str], DeviceState] = {}

    def get(self, group: str, edge: str, device: str) -> DeviceState:
        key = (group, edge, device)
        if key not in self._devices:
            self._devices[key] = DeviceState(device_id=device)
        return self._devices[key]

    def all(self) -> List[Tuple[Tuple[str, str, str], DeviceState]]:
        """以**快照列表**返回全部已登记设备，供 NDEATH 批量置离线等场景使用。

        返回副本而非内部容器，调用方无需（也不应）访问 `_devices`。
        """
        return list(self._devices.items())


# =====================================================================
# 解码器主应用（M2–M6 分流 + 边界处置）
# =====================================================================
class SelfDecoder:
    def __init__(self, cfg: DecoderConfig, writer: DbWriter, mqtt_host: str, mqtt_port: int,
                 sub_topic: str, mqtt_user: str = "", mqtt_password: str = ""):
        self.cfg = cfg
        self.writer = writer
        self.builder = SqlBuilder(cfg)
        self.topic_parser = TopicParser(cfg)
        self.registry = DeviceRegistry()
        self._alerts: List[str] = []
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port

        import paho.mqtt.client as mqtt

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="auscult-self-decoder")
        if mqtt_user:
            self._client.username_pw_set(mqtt_user, mqtt_password or None)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._sub_topic = sub_topic

    # ---- MQTT 回调 ----
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        logger.info("MQTT 已连接 reason_code=%s，订阅 %s", reason_code, self._sub_topic)
        client.subscribe(self._sub_topic, qos=0)

    def _on_message(self, client, userdata, msg):
        try:
            self.handle_bytes(msg.topic, msg.payload)
        except Exception as e:  # noqa: BLE001  单条报文异常不中断进程
            logger.exception("处理报文失败 topic=%s: %s", msg.topic, e)

    # ---- 主入口 ----
    def handle_bytes(self, topic_str: str, payload: bytes):
        topic = self.topic_parser.parse(topic_str)
        if topic is None:
            logger.warning("非法主题: %s", topic_str)
            return
        if topic.message_type not in ("DBIRTH", "DDATA", "DDEATH", "NDEATH"):
            logger.info("忽略报文类型 %s (%s)", topic.message_type, topic_str)
            return
        # 设备级报文必须携带合法 device_id：该值会拼进子表名与 SQL 标识符，
        # 故按 configs/decoder_schema_mapping.json 的 device_id_validation 拒绝（R-V3-5）。
        # NDEATH 为网关级报文（无 device_id 段），不适用本校验。
        if topic.message_type in ("DBIRTH", "DDATA", "DDEATH") \
                and not self.topic_parser.is_valid_device(topic.device_id):
            logger.error("非法 device_id=%r，拒绝报文（device_id_validation）: %s",
                         topic.device_id, topic_str)
            self._alert(topic, f"非法 device_id 被拒绝: {topic.device_id!r}")
            return
        p = decode_payload(payload)
        handler = {
            "DBIRTH": self._handle_dbirth,
            "DDATA": self._handle_ddata,
            "DDEATH": self._handle_ddeath,
            "NDEATH": self._handle_ndeath,
        }[topic.message_type]
        handler(topic, p)

    # ---- M3 DBIRTH ----
    def _handle_dbirth(self, topic: Topic, p: spb_pb2.Payload):
        st_dev = self.registry.get(topic.group_id, topic.edge_node_id, topic.device_id)
        st_dev.online = True
        st_dev.last_seq = p.seq

        bdseq = self._extract_bdseq(p, st_dev.birth_seq)
        device_type = self._extract_device_type(p, st_dev.device_type)

        # M6 冲突判定（更新前先比对历史）
        action = "birth"
        old_bdseq = st_dev.birth_seq
        if old_bdseq is None:
            action = "birth"  # 首次
        elif bdseq == old_bdseq:
            action = "duplicate"
        elif bdseq > old_bdseq:
            action = "rebirth"
        else:
            action = "rebirth_rollback"

        st_dev.birth_seq = bdseq
        st_dev.device_type = device_type if device_type is not None else st_dev.device_type

        status_columns = {
            "ts": p.timestamp or self._now_ms(),
            "online": True,
            "birth_seq": bdseq if bdseq is not None else 0,
            "last_seq": p.seq,
            "reason": action,
        }
        if action == "duplicate":
            logger.info("[%s] DBIRTH 重复报文，忽略（bdSeq=%s）", topic.device_id, bdseq)
            return
        if action == "rebirth_rollback":
            # 回退语义：st_device_status 没有 quality_ok 列，故用其可落地的等效字段表达
            # "该设备数据不可信"：online=FALSE + reason='rebirth_rollback'。
            # 与 configs/decoder_schema_mapping.json boundary_handling.rebirth_conflict
            # 及 docs/prj-spec-schema-mapping.md §五 同步表述。
            self._alert(topic, f"bdSeq 回退: old={old_bdseq} new={bdseq}，"
                                "置 st_device_status.online=FALSE reason='rebirth_rollback'")
            status_columns["online"] = False
        st = self.cfg.stable("st_device_status")
        sql = self.builder.insert_using_sql(
            st, self.builder.table_for(st, topic.group_id, topic.device_id),
            [topic.group_id, topic.edge_node_id, topic.device_id],
            status_columns,
        )
        self.writer.execute(sql)
        logger.info("[%s] DBIRTH 处理完成 action=%s bdSeq=%s", topic.device_id, action, bdseq)

    # ---- M4 DDATA ----
    def _handle_ddata(self, topic: Topic, p: spb_pb2.Payload):
        st_pump = self.cfg.stable("st_pump_metrics")
        st_unmapped = self.cfg.stable("st_unmapped_metrics")
        st_dev = self.registry.get(topic.group_id, topic.edge_node_id, topic.device_id)
        device_type = st_dev.device_type or ""
        tags = [topic.group_id, topic.edge_node_id, topic.device_id, device_type]

        column_values: Dict[str, object] = {}
        unmapped_rows = []
        row_ts = p.timestamp or self._now_ms()
        for metric in p.metrics:
            dt_str, val = metric_value(metric)
            if val is None:
                continue  # 无值 metric（如仅 birth 声明）跳过
            # 时间戳优先序（configs.sparkplug.time_precedence）：
            # metric.timestamp -> payload.timestamp -> server_receive_time
            metric_ts = metric.timestamp if metric.HasField("timestamp") else row_ts
            mapping = self.cfg.metric_to_column("st_pump_metrics", metric.name)
            if mapping is None or mapping["is_tag"]:
                # 未登记 -> 旁路 + schema_drift；
                # tag 型 metric（device_type）的值由 DBIRTH 缓存于 registry，此处不写列也不旁路
                if mapping is not None and mapping.get("is_tag"):
                    continue
                unmapped_rows.append((metric_ts, metric.name, val, dt_str))
                self._alert(topic, f"未知 metric '{metric.name}' -> st_unmapped_metrics + schema_drift")
                continue
            col = mapping["column"]
            col_dt = mapping["datatype"]
            if col_dt not in ("Double", "Float", "Boolean"):
                self._alert(topic, f"metric '{metric.name}' datatype '{col_dt}' 超出允许范围，旁路")
                unmapped_rows.append((metric_ts, metric.name, val, dt_str))
                continue
            column_values[col] = val
            if col == "quality_ok":
                column_values[col] = bool(val)
        if not column_values and not unmapped_rows:
            return
        # 主表写入（局部写入原则：只要有一个正常列就不丢整条报文）
        # 主表行时间戳统一取 payload 级（同一报文的多列共享一行），不随 metric 级时间戳漂移。
        if column_values:
            col_defs = {c["name"] for c in st_pump["columns"]}
            # ts 一定在第一列
            cols_for_insert = {"ts": row_ts}
            cols_for_insert.update({k: v for k, v in column_values.items() if k in col_defs})
            sql = self.builder.insert_using_sql(
                st_pump, self.builder.table_for(st_pump, topic.group_id, topic.device_id),
                tags, cols_for_insert,
            )
            self.writer.execute(sql)
            logger.info("[%s] DDATA 写入 %d 列 @ts=%s", topic.device_id, len(cols_for_insert), row_ts)
        # 旁路表写入
        for (rts, name, val, dt_str) in unmapped_rows:
            is_num = dt_str in ("Double", "Float", "Long", "Int")
            ucols = {"ts": rts, "metric_name": name,
                     "value_num": val if is_num else 0,
                     "value_str": str(val) if not is_num else "",
                     "quality_ok": False}
            utags = [topic.group_id, topic.edge_node_id, topic.device_id]
            sql = self.builder.insert_using_sql(
                st_unmapped, self.builder.table_for(st_unmapped, topic.group_id, topic.device_id),
                utags, ucols,
            )
            self.writer.execute(sql)
            logger.warning("[%s] 旁路 metric '%s' 值=%s", topic.device_id, name, val)

    # ---- M5 DDEATH ----
    def _handle_ddeath(self, topic: Topic, p: spb_pb2.Payload):
        st = self.cfg.stable("st_device_status")
        st_dev = self.registry.get(topic.group_id, topic.edge_node_id, topic.device_id)
        st_dev.online = False
        cols = {"ts": p.timestamp or self._now_ms(), "online": False,
                "birth_seq": st_dev.birth_seq or 0, "last_seq": st_dev.last_seq, "reason": "ddeath"}
        sql = self.builder.insert_using_sql(
            st, self.builder.table_for(st, topic.group_id, topic.device_id),
            [topic.group_id, topic.edge_node_id, topic.device_id], cols,
        )
        self.writer.execute(sql)
        logger.warning("[%s] DDEATH 置离线", topic.device_id)

    # ---- M5 NDEATH ----
    def _handle_ndeath(self, topic: Topic, p: spb_pb2.Payload):
        st = self.cfg.stable("st_device_status")
        # 该 edge_node 下所有设备批量置离线（本实现按已登记设备处理）
        for (g, e, d), st_dev in self.registry.all():
            if e != topic.edge_node_id:
                continue
            st_dev.online = False
            cols = {"ts": p.timestamp or self._now_ms(), "online": False,
                    "birth_seq": st_dev.birth_seq or 0, "last_seq": st_dev.last_seq, "reason": "ndeath"}
            sql = self.builder.insert_using_sql(
                st, self.builder.table_for(st, g, d),
                [g, e, d], cols,
            )
            self.writer.execute(sql)
        logger.warning("NDEATH 网关 %s 置离线（聚合告警）", topic.edge_node_id)
        self._alert(topic, f"网关离线: {topic.edge_node_id}")

    # ---- 辅助 ----
    @staticmethod
    def _now_ms() -> int:
        import time
        return int(time.time() * 1000)

    def _extract_bdseq(self, p: spb_pb2.Payload, default: Optional[int]) -> Optional[int]:
        for m in p.metrics:
            if m.name == "bdSeq":
                v = metric_value_raw(m)
                return int(v) if v is not None else default
        return default

    def _extract_device_type(self, p: spb_pb2.Payload, default: Optional[str]) -> Optional[str]:
        for m in p.metrics:
            if m.name == "device_type":
                v = metric_value_raw(m)
                return str(v) if v is not None else default
        return default

    def _alert(self, topic: Topic, msg: str):
        self._alerts.append(msg)
        logger.warning("[%s] schema_drift/告警: %s", topic.device_id, msg)

    def init_schema(self):
        """启动时幂等建库建表（M3 建表边界前置）。"""
        self.writer.init_schema(self.cfg, self.builder)

    def run_forever(self):
        self._client.connect(self._mqtt_host, self._mqtt_port, keepalive=60)
        self._client.loop_forever()


# =====================================================================
# 自检（--selftest）
# =====================================================================
class SelfTest:
    @staticmethod
    def run(cfg: DecoderConfig) -> bool:
        ok = True

        def check(name: str, cond: bool, detail: str = ""):
            nonlocal ok
            status = "PASS" if cond else "FAIL"
            if not cond:
                ok = False
            print(f"[{status}] {name}" + (f"  -> {detail}" if detail else ""))

        # 1) 配置装载 & 三张超级表
        names = [s["name"] for s in cfg.cfg["stables"]]
        check("配置装载 & 三张超级表", set(names) >= {"st_pump_metrics", "st_unmapped_metrics", "st_device_status"},
              ",".join(names))

        # 2) M1 proto 往返
        pm = spb_pb2.Payload()
        pm.timestamp = 1_000_000
        pm.seq = 3
        m = pm.metrics.add()
        m.name = "vibration_rms"
        m.datatype = DT_DOUBLE
        m.double_value = 1.5
        buf = pm.SerializeToString()
        decoded = spb_pb2.Payload()
        decoded.ParseFromString(buf)
        check("M1 proto 往返", len(decoded.metrics) == 1 and decoded.metrics[0].double_value == 1.5)

        # 3) topic 解析
        parser = TopicParser(cfg)
        t = parser.parse("spBv1.0/plant1/DDATA/gw-pump-01/PUMP-A", enforce_device=True)
        check("topic 解析 DDATA", t is not None and t.device_id == "PUMP-A" and t.message_type == "DDATA")
        t2 = parser.parse("spBv1.0/plant1/NDEATH/gw-pump-01", enforce_device=False)
        check("topic 解析 NDEATH(设备级可空)", t2 is not None and t2.device_id is None)
        t3 = parser.parse("spBv1.0/plant1/DDATA/gw-pump-01/坏#id", enforce_device=True)
        check("device_id 正则拒绝非法", t3 is None)

        # 4) metric 映射
        mm = cfg.metric_to_column("st_pump_metrics", "vibration_rms")
        check("映射 vibration_rms->vib_rms", mm is not None and mm["column"] == "vib_rms" and mm["datatype"] == "Double")
        mm2 = cfg.metric_to_column("st_pump_metrics", "metric_quality")
        check("映射 metric_quality->quality_ok(Boolean)", mm2 is not None and mm2["column"] == "quality_ok")
        mm3 = cfg.metric_to_column("st_pump_metrics", "VIB_BAND_1")
        check("未登记 metric->None(旁路)", mm3 is None)

        # 5) SQL 生成
        builder = SqlBuilder(cfg)
        st = cfg.stable("st_pump_metrics")
        sql = builder.insert_using_sql(
            st, builder.table_for(st, "plant1", "PUMP-A"),
            ["plant1", "gw-pump-01", "PUMP-A", "PUMP_TYPE"],
            {"ts": 1111, "vib_rms": 1.5, "quality_ok": True},
        )
        check("INSERT USING 语句", "`d_plant1_PUMP-A` USING `iot`.`st_pump_metrics` TAGS" in sql
              and "'plant1'" in sql and "vib_rms" in sql and "true" in sql, sql)

        # 6) SQL 值格式（局部写入单坏 metric 不丢整条：布尔/NCHAR）
        check("BOOL 值格式 true", _fmt_col_val(True, "BOOL") == "true")
        check("NCHAR 值转义", _fmt_col_val("a'b", "NCHAR(32)") == "'a''b'")

        print("SELFTEST " + ("PASS" if ok else "FAIL"))
        return ok


# =====================================================================
# main
# =====================================================================
def main():
    ap = argparse.ArgumentParser(description="自研 Sparkplug B 解码器")
    ap.add_argument("--selftest", action="store_true", help="本地自检（不依赖网络/容器）")
    ap.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "127.0.0.1"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    ap.add_argument("--mqtt-user", default=os.environ.get("MQTT_USERNAME", ""))
    ap.add_argument("--mqtt-password", default=os.environ.get("MQTT_PASSWORD", ""))
    ap.add_argument("--td-host", default=os.environ.get("TD_HTTP_HOST", "127.0.0.1"))
    ap.add_argument("--td-port", type=int, default=int(os.environ.get("TD_HTTP_PORT", "6041")))
    ap.add_argument("--td-user", default=os.environ.get("TD_USER", "root"))
    ap.add_argument("--td-password", default=os.environ.get("TD_PASSWORD", "taosdata"))
    ap.add_argument("--prj-spec-schema-mapping", default=os.environ.get("SCHEMA_MAPPING", ""),
                    help="configs/decoder_schema_mapping.json 路径")
    ap.add_argument("--sub-topic", default=os.environ.get(
        "SPB_SUB_TOPIC", "spBv1.0/plant1/+/gw-pump-01/#"))
    args = ap.parse_args()

    cfg_path = Path(args.schema_mapping) if args.schema_mapping else None
    cfg = DecoderConfig(cfg_path)

    if args.selftest:
        sys.exit(0 if SelfTest.run(cfg) else 1)

    db_name = cfg.database["name"]
    writer = DbWriter(args.td_host, args.td_port, args.td_user, args.td_password, db_name)
    app = SelfDecoder(cfg, writer, args.mqtt_host, args.mqtt_port,
                      args.sub_topic, args.mqtt_user, args.mqtt_password)
    app.init_schema()  # M3 建表边界：启动即幂等建库建表
    app.run_forever()


if __name__ == "__main__":
    main()