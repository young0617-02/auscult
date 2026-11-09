"""Agent 工具注册与执行（P7 · Agent 化）。

职责：
1. **工具面**：从 `schemas/tools_v6.json` 程序化加载**只读子集**（4 个）
   转 OpenAI 兼容 tools 数组（llm_adapter.load_tools 同结构，禁手抄）；
   `generate_report` 按 ADR-007（写操作移出图内）**不进 Agent 工具面**。
2. **执行**：schema 形参 → 产品工具实现（app/tools/*）的适配层。
   产品函数签名与评测 schema 不同（如 query_sensor 产品侧按
   (device_id, metric, start_ts, end_ts) 查单列，schema 侧按
   sensor_ids/time_range/aggregation 描述意图），本模块负责桥接。
3. **安全**：工具名过 `app/security/sanitizer.py` 白名单
   （schema 名 search_knowledge → 产品名 retrieve_knowledge 映射后校验），
   白名单外/写操作一律拒绝执行并回灌拒绝原因（模型可自我纠正）。

已知口径差（已登记 ISS-049）：schema 测点短名 vib_x/vib_y/vib_z 在
TDengine 无分向列（仅 vib_rms），按 SENSOR_COLUMN_MAP 归一并显式告知模型，
不静默丢失精度语义。

对应交付物：docs/p7-design-agent-diagnosis-2026-10-19.md §四。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..device_ids import CANONICAL_TO_LEGACY, device_id_scheme, storage_id
from ..observability import prom_metrics as pm
from ..security.sanitizer import audit_tool_call, validate_tool_args, validate_tool_call

PROJECT_ROOT = Path(__file__).resolve().parents[2]
#: v6（2026-10-30）：query_sensor 增 `cursor` 形参（分页续拉）。v4/v5 冻结快照保留，
#: 判分链路（judge_tools / V1 用例）仍指向 v4，不受影响 —— 依据
#: `docs/prj-ledger-version-lock.md` §一 纪律 4「Schema 变更必须升版」。
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "tools_v6.json"

# ---------------------------------------------------------------- 常量

#: Agent 工具面 = tools_v4 的 4 个只读工具（generate_report 为写操作，除外）
AGENT_TOOL_NAMES: tuple[str, ...] = (
    "query_sensor", "search_knowledge", "query_graph", "get_maintenance_history",
)

#: schema 工具名 → 产品工具名（白名单校验用；sanitizer.TOOL_WHITELIST 用产品名）
SCHEMA_TO_PRODUCT: dict[str, str] = {"search_knowledge": "retrieve_knowledge"}

#: schema 测点短名 → TDengine 列名（ISS-049：三向振动未分向存储）
SENSOR_COLUMN_MAP: dict[str, str] = {
    "vib_x": "vib_rms", "vib_y": "vib_rms", "vib_z": "vib_rms",
    "temp_bearing_de": "bearing_temp", "temp_bearing_nde": "bearing_temp",
    # 直传列名（兼容产品侧命名）
    "vib_rms": "vib_rms", "vib_peak": "vib_peak", "vib_kurtosis": "vib_kurtosis",
    "bearing_temp": "bearing_temp", "motor_current": "motor_current",
    "pump_speed": "pump_speed",
}

#: 产品规范设备号 → 数据层设备号（ISS-056 候选①，2026-10-22）
#: 口径已收敛到 `app.device_ids`（单一事实源）——本常量保留为**只读兼容别名**，
#: 实际查询走 `storage_id()`：由 `AUSCULT_DEVICE_ID_SCHEME`（legacy|canonical）决定
#: 落到"库内当前形态"，使迁移期（新数据规范、旧数据短编号）查询两侧都能命中。
#: 映射未命中时原样透传（真实未知设备仍走 `_device_has_any_data` 分类）。
#: 适用范围：`query_sensor` / `query_graph`（start_node）/ `get_maintenance_history`。
#: 工单侧另配「空结果回灌真实编号样本」兜底：`work_orders.device_id` 源数据是
#: 图纸/台账口径（`A 0泵`、客户号），候选①对其**无迁移对象**，见 `app/device_ids` 头注。
DEVICE_ALIAS_MAP: dict[str, str] = CANONICAL_TO_LEGACY

# ---------------------------------------------------------------- 测点数上限（2026-10-30 重构）
#
# 原实现只有一个常数 `_MAX_SENSORS_PER_CALL = 5`，同时承担了四件互相冲突的事：
# 「单次调用墙钟上限」「单条结果体积上限」「覆盖完整性」「故障隔离」。四者的最优
# 方向不同，任何一个数字都会在某个维度上出错；测点越多错得越明显。
#
# 现拆成两个**语义不同**的量：
#   _MAX_SENSORS_PER_CALL —— **请求上界（防护）**：模型一次能列多少测点。超过即
#       显式拒绝（不是截断）。数值由 SLO 反推，不为「延迟省时间」服务 —— 查询
#       成本已由批量 SQL 压成 O(1) 往返，与测点数几乎无关。
#   _SENSOR_PAGE_SIZE —— **单页渲染预算**：一条 tool result 回灌多少个测点。由
#       回灌体积预算推导，超出部分用 `next_cursor` 续拉，**丢弃永不发生**。
#
# 覆盖完整性的责任随之从「模型自觉」移到「服务端游标」：offset 由服务端计算，
# 每页都回灌权威的 `coverage.remaining`，模型不续拉就是显式放弃，而不是不知道。
_TOOL_CALL_BUDGET_MS = 1_500      # 端到端 P95 目标 3s 中留给单次工具调用的份额
_BATCH_FIXED_COST_MS = 60         # 一条多列 SQL 的固定开销（传输 + 解析 + 序列化）
_PER_COLUMN_COST_MS = 4           # 每增加一列的解析/统计边际开销
_HARD_CAP = 200                   # 与 schema `sensor_ids.maxItems` 对齐的硬帽

_RESULT_CHAR_BUDGET = 2_000       # 单条 tool result 回灌预算（硬截断线 4000 的一半，留余量）
_CHARS_PER_SERIES = 160           # 单测点 series 条目序列化长度（sensor_id+column+6 统计量）


def _env_int(name: str, default: int) -> int:
    """环境变量覆盖（非法值回落默认，不抛异常——护栏不因配置写错而失效）。"""
    try:
        val = int(str(os.environ.get(name, "")).strip())
        return val if val > 0 else default
    except (TypeError, ValueError):
        return default


def _derive_max_sensors() -> int:
    """从 SLO 反推单次请求的测点数**安全上界**。

    推导：`(单次工具调用预算 - 单次 SQL 固定成本) / 每列边际成本`。
    该值只用于「防打爆」（一次请求不得产生超预算的墙钟），**不是**功能边界 ——
    模型真有更多测点要查，靠 cursor 分页而不是被砍掉。
    """
    derived = max(1, (_TOOL_CALL_BUDGET_MS - _BATCH_FIXED_COST_MS) // _PER_COLUMN_COST_MS)
    return min(derived, _HARD_CAP)


_MAX_SENSORS_PER_CALL = _env_int("AUSCULT_SENSOR_MAX_PER_CALL", _derive_max_sensors())

#: 单页测点数：由回灌体积预算反推（12 ≈ 2000/160）。上界本身不作为页大小 ——
#: 一次回灌 200 个测点会撞上 tool_result 的字符上限。
_SENSOR_PAGE_SIZE = max(
    1, min(_RESULT_CHAR_BUDGET // _CHARS_PER_SERIES, _MAX_SENSORS_PER_CALL))

_MAX_WINDOW_MS = 24 * 3_600_000   # 缺省回看窗口（自锚点起算）
_MAX_TEXT_CHARS = 300          # 单条知识块注入 LLM 的最大字符数
_MAX_ROWS = 20                 # 工单/图谱命中注入 LLM 的最大条数

_REL_TIME_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(m|min|分钟|h|小时|d|天)$")
_REL_UNIT_MS = {"m": 60_000, "min": 60_000, "分钟": 60_000,
                "h": 3_600_000, "小时": 3_600_000,
                "d": 86_400_000, "天": 86_400_000}

# 进程内常驻单例（惰性初始化，跨调用复用 embedder/连接）
_retrieval_svc: Any = None


# ---------------------------------------------------------------- 工具面加载

def load_agent_tools(schema_path: Path = SCHEMA_PATH) -> list[dict[str, Any]]:
    """从 tools_v4.json 加载只读子集 → OpenAI 兼容 tools 数组。

    description 追增 when_to_use / when_not_to_use（schema 自带语义，
    程序化拼接，不人工删改原文）。
    """
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    tools: list[dict[str, Any]] = []
    for tool in schema["tools"]:
        if tool["name"] not in AGENT_TOOL_NAMES:
            continue
        description = tool["description"]
        if tool.get("when_to_use"):
            description += f"\n适用：{tool['when_to_use']}"
        if tool.get("when_not_to_use"):
            description += f"\n不适用：{tool['when_not_to_use']}"
        tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": description,
                "parameters": tool["parameters"],
            },
        })
    if len(tools) != len(AGENT_TOOL_NAMES):
        raise RuntimeError(
            f"tools_v4.json 只读子集加载不完整: {[t['function']['name'] for t in tools]}")
    return tools


def tools_json_for_prompt(schema_path: Path = SCHEMA_PATH) -> str:
    """序列化 Agent 工具面的 JSON（注入系统提示词）。"""
    names = set(AGENT_TOOL_NAMES)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    subset = [t for t in schema["tools"] if t["name"] in names]
    return json.dumps(subset, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 时间解析

def parse_timestamp(value: Any, *, now_ms: int | None = None) -> int | None:
    """相对时间（24h/7d/15m/3小时）或 ISO8601 → epoch ms；无法解析返回 None。"""
    if value is None:
        return None
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    text = str(value).strip()
    m = _REL_TIME_RE.match(text)
    if m:
        return now_ms - int(float(m.group(1)) * _REL_UNIT_MS[m.group(2)])
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def _resolve_window(time_range: Any, *, now_ms: int,
                    anchor_ms: int | None = None) -> tuple[int, int]:
    """time_range → (start_ms, end_ms)，以**告警时刻**为缺省锚点。

    锚点语义（2026-10-22 修复）：
    - `anchor_ms`（= `alarm.ts`）存在且合法时，相对时间（"6h"/"24h"）与缺省窗口
      都从告警时刻起算 → 缺省窗口 = `[锚点-24h, 锚点]`；
    - `anchor_ms` 缺失/为 0/在未来（如实时判据里的 `ts=0`）→ 回落 `now_ms`，
      与历史行为一致；
    - 绝对 ISO 时间不受锚点影响（模型给了起止就按模型给）；
    - 终点永不超过 `now_ms`（不查未来数据）。

    为什么必须锚在告警时刻：回放/历史告警（如 10-20 的告警在 10-22 复诊）若按
    now 起算，查的窗口与告警时刻错配 → 模型会拿到无关数据并误判"告警值与存储
    严重矛盾/时间过滤失效"，把本该自动定论的诊断推向人工。

    幻觉出的未来起点（start > 锚点）钳制回缺省窗口——不下发 start > end 的
    非法区间给 TDengine。
    """
    anchor = anchor_ms if isinstance(anchor_ms, int) and 0 < anchor_ms <= now_ms else now_ms
    tr_ = time_range if isinstance(time_range, dict) else {}
    start = parse_timestamp(tr_.get("start"), now_ms=anchor)
    end = parse_timestamp(tr_.get("end"), now_ms=anchor)
    if start is None or start > anchor:
        start = anchor - _MAX_WINDOW_MS
    if end is None or end < start:
        end = anchor
    if end > now_ms:                       # 不查未来
        end = now_ms
    if start > end:                        # 兜底：起点不得晚于终点
        start = end - _MAX_WINDOW_MS
    return start, end


# ---------------------------------------------------------------- 测点分页游标（2026-10-30）

_CURSOR_VERSION = 1


def _coverage_fingerprint(device_id: str, requested: list[str],
                          time_range: Any) -> str:
    """分页上下文的指纹：设备 + 完整测点清单 + **time_range 原始入参**。

    作用：cursor 只携带「页偏移」，清单由模型按原样重复传入，二者用指纹绑定。
    清单一旦被改动（增删测点），指纹不匹配 → **显式拒绝续拉**；否则服务端会按
    新清单继续切页，导致某些测点被静默跳过或重复查询。

    ⚠️ 指纹刻意**不使用解析后的绝对毫秒窗口**：缺省/相对时间（"24h"）以 now 为
    锚点，两页之间必然漂移几秒 —— 用毫秒做指纹会让"正常续拉"也永远被拒。
    页边界错位的真实风险来自**清单**变化，而不是滚动窗口的秒级漂移。
    """
    if isinstance(time_range, dict):
        norm = json.dumps(time_range, sort_keys=True, ensure_ascii=False)
    else:
        norm = str(time_range or "")
    raw = f"{device_id}|{','.join(requested)}|{norm}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


def _encode_cursor(offset: int, fingerprint: str) -> str:
    """页偏移 → 不透明 token（约 40 字符，避免把整份清单塞进上下文）。"""
    raw = json.dumps({"v": _CURSOR_VERSION, "o": offset, "f": fingerprint},
                     separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(token: str) -> tuple[int, str] | None:
    """token → (offset, fingerprint)；非法/跨版本返回 None（调用方显式报错）。"""
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        obj = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:                                        # noqa: BLE001 - 任何畸形都按失效处理
        return None
    if not isinstance(obj, dict) or obj.get("v") != _CURSOR_VERSION:
        return None
    offset, fp = obj.get("o"), obj.get("f")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        return None
    if not isinstance(fp, str) or not fp:
        return None
    return offset, fp


# ---------------------------------------------------------------- 各工具执行体

def _device_has_any_data(device_id: str, *, timeout: float = 1.0) -> bool:
    """该设备在时序库中是否有**任何**记录（不限时间窗）。

    ISS-056 的关键补丁：`query_sensor` 查不到数据时返回 `ok=True, count=0`，
    模型无法区分「设备号写错」与「窗口内确实没数据」。此函数多发一次不限窗口的
    计数查询把两者分开；**探测失败时保守返回 True**（TDengine 抖动不应被谎称成
    "设备不存在"，宁可把空结果归因为窗口问题）。
    """
    from ..tools.query_sensor import (          # noqa: PLC0415
        TDENGINE_DB, _SAFE_ID, _td_query,
    )
    if not _SAFE_ID.match(device_id or ""):
        return False
    try:
        body = _td_query(
            f"SELECT count(*) FROM iot.st_pump_metrics "
            f"WHERE device_id = '{device_id}'",
            db=TDENGINE_DB, timeout=timeout)
        return bool(body.get("data") and int(body["data"][0][0] or 0) > 0)
    except (TimeoutError, ConnectionError, RuntimeError):
        return True


def _storage_id(device_id: str) -> str:
    """`storage_id()` + 口径漂移打点（ISS-056 映射退场判据）。

    - `direction=short_input`：默认 `canonical` 模式下仍收到短编号（客户端没跟上迁移）；
    - `direction=canonical_input`：显式 `legacy` 模式下收到规范编号。

    两类都为 0（连续一周）且 `--verify` 的 `off_scheme` 恒空，才可删除映射层
    （判据见 `app/device_ids` 头注「迁移节奏」第 4 条）。
    """
    stored = storage_id(device_id)
    if stored != (device_id or "").strip():
        pm.inc_device_id_mismatch(
            "short_input" if device_id_scheme() == "canonical" else "canonical_input")
    return stored


def _exec_query_sensor(args: dict[str, Any], alarm: Any) -> dict[str, Any]:
    from ..graph.nodes.analyze_sensor import _compute_stats   # noqa: PLC0415
    # 2026-10-30：改走批量多列接口 —— 本页所有列一条 SQL 查完（原来每列一次往返，
    # 单次工具调用墙钟随测点数线性增长，这才是"必须限 N"的真实原因）。
    from ..tools.query_sensor import query_sensor_columns     # noqa: PLC0415

    device_id = str(args.get("device_id") or "").strip()
    if not device_id:
        return {"ok": False, "error": "缺少必填参数 device_id"}

    # ISS-056 候选①：任意输入（规范/短）→ 库内当前形态（由 AUSCULT_DEVICE_ID_SCHEME
    # 决定；迁移前仍是短编号，迁移后是 PUMP-A-01）。未命中原样透传，真实未知设备
    # 不会被这张表伪装成有数据。
    resolved_id = _storage_id(device_id)

    raw_ids = args.get("sensor_ids") or []
    if not raw_ids and alarm is not None and alarm.metric:
        raw_ids = [f"{alarm.device_id}.{alarm.metric}"]
    # 去重保序：vib_x/vib_y/vib_z 同映射 vib_rms，重复项只会重复查询并白占分页额度
    requested = list(dict.fromkeys(str(s).strip() for s in raw_ids if str(s).strip()))
    if not requested:
        return {"ok": False, "error": "缺少参数 sensor_ids 且无法从告警推断测点"}

    # 安全上界：**显式拒绝**而非截断（2026-10-30）。
    # 上界的作用是让"单次工具调用的最坏墙钟"可计算（防打爆）；截断则会让模型把
    # "没查"当成"没问题"（2026-10-22 已因此产生"温度测点无数据"的错误归因）。
    if len(requested) > _MAX_SENSORS_PER_CALL:
        return {"ok": False,
                "error": (f"sensor_ids 共 {len(requested)} 个，超过单次请求安全上界 "
                          f"{_MAX_SENSORS_PER_CALL}（由工具调用 SLO 反推，非功能边界）。"
                          f"请按诊断优先级拆分：先查最相关的 ≤{_SENSOR_PAGE_SIZE} 个，"
                          f"再用返回的 next_cursor 续拉；不要一次列全。")}

    now_ms = int(time.time() * 1000)
    # 窗口锚在告警时刻（历史/回放告警不再查到与告警无关的 now 窗口）
    anchor_ms = getattr(alarm, "ts", None) if alarm is not None else None
    start_ts, end_ts = _resolve_window(args.get("time_range"), now_ms=now_ms,
                                       anchor_ms=anchor_ms)
    baseline = getattr(alarm, "baseline", None)
    window = {"start_ms": start_ts, "end_ms": end_ts}
    fingerprint = _coverage_fingerprint(resolved_id, requested,
                                        args.get("time_range"))

    # ---- 分页：页偏移由**服务端**计算，模型只回传不透明 token ----
    # 覆盖完整性因此不再依赖"模型记得还有几个没查"，而是由系统保证可枚举。
    offset = 0
    if args.get("cursor"):
        decoded = _decode_cursor(str(args.get("cursor")))
        if decoded is None:
            return {"ok": False,
                    "error": ("cursor 无法解析（已失效或非本工具签发）。请去掉 cursor，"
                              "用与上一页完全相同的 device_id / sensor_ids / time_range "
                              "重新请求，从第一页开始。")}
        offset, cursor_fp = decoded
        if cursor_fp != fingerprint:
            return {"ok": False,
                    "error": ("cursor 与本次请求的 device_id / sensor_ids / time_range "
                              "不匹配 —— 续拉必须原样重复上一页的参数。清单或窗口一旦"
                              "变化，页边界即不可信，系统拒绝在错位处继续（否则会有测点"
                              "被静默跳过或重复查询）。")}
        if offset >= len(requested):
            return {"ok": False,
                    "error": (f"cursor 偏移 {offset} 已到达清单末尾（共 {len(requested)} "
                              f"个），该清单已全部查完，无需续拉。")}

    page = requested[offset:offset + _SENSOR_PAGE_SIZE]
    next_offset = offset + len(page)
    remaining = requested[next_offset:]
    coverage: dict[str, Any] = {
        "requested": len(requested),
        "page": {"from": offset, "to": next_offset, "size": _SENSOR_PAGE_SIZE},
        "queried": list(page),
        "done": not remaining,
    }
    if remaining:
        coverage["remaining"] = list(remaining)
        coverage["next_cursor"] = _encode_cursor(next_offset, fingerprint)

    # ---- 短名 → 列；未登记显式报错（不进 SQL，避免一个坏名字拖垮整页） ----
    errors: list[str] = []
    column_of: dict[str, str] = {}
    for sensor in page:
        short = sensor.split(".")[-1] if "." in sensor else sensor
        column = SENSOR_COLUMN_MAP.get(short)
        if column is None:
            errors.append(f"测点 {sensor} 未登记（无对应时序列）")
            continue
        column_of[sensor] = column

    unique_cols = list(dict.fromkeys(column_of.values()))
    data: dict[str, list[dict[str, Any]]] = {}
    if unique_cols:
        try:
            # 本页所有列一条 SQL（列已去重：vib_x/y/z 同列只查一次）
            data = query_sensor_columns(resolved_id, unique_cols,
                                        start_ts, end_ts, timeout=1.0)
        except (TimeoutError, ConnectionError, RuntimeError) as exc:
            return {"ok": False,
                    "error": f"时序查询失败（本页 {len(unique_cols)} 列一次 SQL）: {exc}",
                    "window": window,
                    "coverage": coverage}       # 查询失败也带游标：下一轮可重试同一页

    # 空结果分类：整页都空才探测一次设备是否存在
    # （原实现每个测点探测一次，N 个测点额外 N 次 count 查询）
    device_exists: bool | None = True if any(data.get(c) for c in unique_cols) else None

    series: list[dict[str, Any]] = []
    empty_reason: str | None = None
    for sensor, column in column_of.items():
        rows = data.get(column) or []
        if not rows:
            # ISS-056：不再把"查不到"静默包装成 count=0 的有效证据 —— 必须告诉
            # 模型是"设备号不存在"还是"窗口内无数据"，它才能自我纠正。
            if device_exists is None:
                device_exists = _device_has_any_data(resolved_id)
            if device_exists:
                errors.append(f"测点 {sensor}（列 {column}）在查询窗口内无数据")
                empty_reason = empty_reason or "no_data_in_window"
            else:
                errors.append(
                    f"设备 {device_id}（数据层编号 {resolved_id}）在时序库中不存在，"
                    f"测点 {sensor} 无从查询")
                empty_reason = empty_reason or "device_not_found"
            continue
        values = [float(r["value"]) for r in rows]
        stats = _compute_stats(values, baseline if column == "vib_rms" else None)
        series.append({"sensor_id": sensor, "column": column, **stats})

    if not series:
        out: dict[str, Any] = {"ok": False,
                               "error": "; ".join(errors) or "无可用测点数据"}
        if empty_reason:
            out["empty_reason"] = empty_reason
        out["window"] = window
        out["coverage"] = coverage          # 本页为空 ≠ 清单查完，游标照给
        return out

    result: dict[str, Any] = {"device_id": resolved_id, "series": series,
                              "window": window, "coverage": coverage}
    if device_id != resolved_id:
        # 透明度：让模型与审计都看到发生了编号归一（ISS-056）
        result["device_id_resolved"] = {"requested": device_id, "used": resolved_id}
    if errors:
        result["partial_errors"] = errors
    if empty_reason:
        result["empty_reason"] = empty_reason
    if remaining:
        # 未查清单是模型判断"这轮证据完整吗"的唯一依据，也是它不能拿未查测点
        # 说事的边界 —— 由服务端签发，不是模型自述。
        result["notices"] = [
            f"本次只查了 {page}；未查询：{remaining}"
            f"（它们**没有**结论，需带 next_cursor 再调一次补齐）"]
    if any(s["column"] == "vib_rms" and s["sensor_id"].endswith(("vib_x", "vib_y", "vib_z"))
           for s in series):
        result["note"] = ("三向振动（vib_x/vib_y/vib_z）当前存储未分向，"
                          "统一按振动有效值 vib_rms 返回（ISS-049）")
    return {"ok": True, "result": result}


def _get_retrieval_service() -> Any:
    global _retrieval_svc
    if _retrieval_svc is None:
        import os                                          # noqa: PLC0415
        from ..tools.retrieve_knowledge import RetrievalService   # noqa: PLC0415
        _retrieval_svc = RetrievalService(
            device=os.environ.get("AUSCULT_RETRIEVAL_DEVICE", "cuda"),
            use_rerank=False,                               # D7 消融最优口径
        )
    return _retrieval_svc


def _exec_search_knowledge(args: dict[str, Any], alarm: Any) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if len(query) < 2:
        return {"ok": False, "error": "缺少有效参数 query（≥2 字符）"}
    top_k = min(int(args.get("top_k") or 5), 10)
    try:
        svc = _get_retrieval_service()
        out = svc.retrieve(query)
    except Exception as exc:                                # noqa: BLE001 - 降级不中断
        return {"ok": False, "error": f"知识检索失败: {exc}"}
    items = out.get("items") or []
    result: dict[str, Any] = {
        "degraded": bool(out.get("degraded")),
        "items": [{"chunk_id": it.get("chunk_id", ""),
                   "score": round(float(it.get("score") or 0.0), 4),
                   "text": str(it.get("text") or "")[:_MAX_TEXT_CHARS]}
                  for it in items[:top_k]],
    }
    if out.get("degraded"):
        result["degraded_routes"] = out.get("degraded_routes")
    return {"ok": True, "result": result}


def _exec_query_graph(args: dict[str, Any], alarm: Any) -> dict[str, Any]:
    from ..tools.query_graph import query_graph            # noqa: PLC0415

    start_node = str(args.get("start_node") or "").strip()
    if not start_node:
        return {"ok": False, "error": "缺少必填参数 start_node"}
    # ISS-056 候选①：图谱实体编号与 query_sensor 同一 `storage_id()` 口径
    # （迁移前短编号、迁移后规范编号；未命中原样透传）。
    resolved_node = _storage_id(start_node)
    relations = [str(r) for r in (args.get("relation_types") or [])]
    question = f"{resolved_node} 设备关系与故障关联"
    if relations:
        question += f"（关注关系: {'、'.join(relations)}）"
    try:
        out = query_graph(question)
    except Exception as exc:                                # noqa: BLE001 - 降级不中断
        return {"ok": False, "error": f"图谱查询失败: {exc}"}
    if out.get("degraded"):
        return {"ok": True, "result": {"degraded": True,
                                       "reason": out.get("reason") or "图谱降级"}}
    hits = out.get("hits") or []
    result: dict[str, Any] = {
        "degraded": False,
        "entities_hit": out.get("entities_hit") or [],
        "hits": [{"chunk_id": h.get("chunk_id", ""),
                  "score": round(float(h.get("score") or 0.0), 4)}
                 for h in hits[:_MAX_ROWS]],
    }
    if start_node != resolved_node:
        # 透明度：让模型与审计都看到发生了编号归一（与 query_sensor 同型）
        result["device_id_resolved"] = {"requested": start_node, "used": resolved_node}
    if not result["hits"] and not result["entities_hit"]:
        # 图谱侧"空结果"也要可解释：实体名不匹配与"确实无关联"是两回事
        result["note"] = (f"图谱未命中实体 `{resolved_node}`（可能编号口径不符或无关联）；"
                          f"可换编号重试或依据其他证据下结论")
    return {"ok": True, "result": result}


def _exec_get_maintenance_history(args: dict[str, Any], alarm: Any) -> dict[str, Any]:
    from ..tools.get_maintenance_history import (          # noqa: PLC0415
        get_maintenance_history, list_known_devices,
    )

    device_id = str(args.get("device_id") or "").strip()
    if not device_id:
        return {"ok": False, "error": "缺少必填参数 device_id"}
    # ISS-056 候选①：工单侧同一 `storage_id()` 口径。注意工单库源数据是图纸/台账口径
    # （`A 0泵`/客户号），本映射对其无作用——靠下面的空结果样本回灌兜底。
    resolved_id = _storage_id(device_id)
    limit = min(int(args.get("limit") or 10), _MAX_ROWS)
    try:
        rows = get_maintenance_history(resolved_id, limit=limit, timeout=2.0)
    except (TimeoutError, ConnectionError, RuntimeError) as exc:
        return {"ok": False, "error": f"工单查询失败: {exc}"}
    result: dict[str, Any] = {
        "device_id": resolved_id,
        "work_orders": [{"order_id": r.get("order_id", ""),
                         "fault": r.get("fault", ""),
                         "action": r.get("action", ""),
                         "result": r.get("result"),
                         "created_at": str(r.get("created_at") or "")[:19]}
                        for r in rows],
    }
    if device_id != resolved_id:
        result["device_id_resolved"] = {"requested": device_id, "used": resolved_id}
    if not rows:
        # ISS-056 空结果可区分：把库里**实际存在的编号样本**回灌（而非猜一个映射），
        # 模型可据此自我纠正；探测失败时保守不给样本（不谎称"无此设备"）。
        known = list_known_devices()
        result["empty_reason"] = "no_work_orders"
        if known:
            result["known_device_ids"] = known
    return {"ok": True, "result": result}


_EXECUTORS = {
    "query_sensor": _exec_query_sensor,
    "search_knowledge": _exec_search_knowledge,
    "query_graph": _exec_query_graph,
    "get_maintenance_history": _exec_get_maintenance_history,
}


# ---------------------------------------------------------------- 统一入口

def execute_tool(name: str, arguments: dict[str, Any], *,
                 alarm: Any = None, thread_id: str | None = None) -> dict[str, Any]:
    """执行一次 Agent 工具调用（白名单 + 写操作护栏 + 执行）。

    返回 {"ok": bool, "result"?: dict, "error"?: str}——ok=False 时 error 为
    回灌给模型的拒绝/失败原因（模型可据此自我纠正，不中断循环）。
    """
    args = arguments if isinstance(arguments, dict) else {}
    product_name = SCHEMA_TO_PRODUCT.get(name, name)

    if name == "generate_report":
        audit_tool_call(thread_id, product_name, {"args_keys": sorted(args)},
                        allowed=False)
        return {"ok": False,
                "rejected": True, "reject_kind": "write_guard",
                "error": "写操作护栏：报告生成需经人工审核通过后由系统统一执行，"
                         "Agent 不直接生成报告。请继续输出诊断结论 JSON。"}

    if not validate_tool_call(product_name):
        audit_tool_call(thread_id, product_name, {"args_keys": sorted(args)},
                        allowed=False)
        return {"ok": False, "rejected": True, "reject_kind": "whitelist",
                "error": f"工具 '{name}' 不在白名单中，已拒绝执行"}

    # 参数级前置校验（2026-10-21 接线）：此前 validate_tool_args 从未被调用，
    # 缺参只能靠各执行体手工兜底 —— 统一在这里拦，模型可据 error 自我纠正。
    arg_check = validate_tool_args(product_name, args)
    if not arg_check["valid"]:
        audit_tool_call(thread_id, product_name,
                        {"args_keys": sorted(args), "invalid": arg_check["errors"]},
                        allowed=False)
        return {"ok": False, "rejected": True, "reject_kind": "arg",
                "error": "参数校验失败：" + "；".join(arg_check["errors"])
                         + "。请补齐参数后重试。"}

    executor = _EXECUTORS.get(name)
    if executor is None:
        return {"ok": False, "error": f"工具 '{name}' 无可用执行体"}
    try:
        out = executor(args, alarm)
    except Exception as exc:                                # noqa: BLE001 - 工具异常不中断循环
        return {"ok": False, "error": f"工具 '{name}' 执行异常: {exc}"}

    audit_tool_call(thread_id, product_name,
                    {"args_keys": sorted(args)}, allowed=bool(out.get("ok")))
    return out


#: 单条 tool result 回灌字符上限（避免一条结果吃掉整个上下文窗口）
_TOOL_RESULT_CHAR_LIMIT = 4_000

#: 失败路径也**必须**保留的诊断字段（2026-10-30）：
#: 原实现 ok=False 时只回 `{"error": ...}`，把 `empty_reason` / `notices` /
#: `coverage` / `window` 全丢了 —— 模型因此分不清「设备不存在」「窗口无数据」
#: 「本页查完但清单没完」，是同一族"静默缩小信息"的缺陷。
_ERROR_KEEP_KEYS = ("error", "rejected", "reject_kind", "empty_reason",
                    "notices", "window", "coverage")


def tool_result_message(call_id: str, name: str, out: dict[str, Any]) -> dict[str, Any]:
    """工具结果 → OpenAI 兼容 role=tool 消息（回灌模型）。

    长度超限时返回**合法 JSON**，而不是把 JSON 字符串硬切一半（2026-10-30）：
    硬切会产生无法解析的残串，模型侧表现为"工具返回损坏"，且丢失是静默的。
    这里改为显式截断对象：保留 coverage/next_cursor，提示模型续拉。
    """
    if out.get("ok"):
        payload: dict[str, Any] = out
    else:
        payload = {k: v for k, v in out.items() if k in _ERROR_KEEP_KEYS}
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > _TOOL_RESULT_CHAR_LIMIT:
        coverage = (out.get("result") or {}).get("coverage") or out.get("coverage") or {}
        payload = {
            "ok": bool(out.get("ok")),
            "truncated": True,
            "char_limit": _TOOL_RESULT_CHAR_LIMIT,
            "note": ("结果超出单条回灌上限已省略部分内容。**不要据此认为未展示的测点/"
                     "条目正常**；需要完整数据请按 next_cursor 续拉，或缩小 sensor_ids。"),
        }
        if coverage:
            payload["coverage"] = coverage
        if not out.get("ok"):
            payload["error"] = out.get("error")
        text = json.dumps(payload, ensure_ascii=False)
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": text}


def assistant_tool_calls_message(content: str,
                                 calls: list[Any]) -> dict[str, Any]:
    """模型工具调用轮 → OpenAI 兼容 assistant 消息（含 tool_calls，供回灌）。"""
    return {
        "role": "assistant",
        "content": content or "",
        "tool_calls": [{"id": c.id, "type": "function",
                        "function": {"name": c.name,
                                     "arguments": json.dumps(c.arguments,
                                                             ensure_ascii=False)}}
                       for c in calls],
    }
