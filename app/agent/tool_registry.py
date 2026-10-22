"""Agent 工具注册与执行（P7 · Agent 化）。

职责：
1. **工具面**：从 `schemas/tools_v4.json` 程序化加载**只读子集**（4 个）
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

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..device_ids import CANONICAL_TO_LEGACY, device_id_scheme, storage_id
from ..observability import prom_metrics as pm
from ..security.sanitizer import audit_tool_call, validate_tool_args, validate_tool_call

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "tools_v4.json"

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

_MAX_SENSORS_PER_CALL = 5      # 单次工具调用最多查 5 个测点（延迟护栏；超限必回灌 notices）
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
    from ..tools.query_sensor import query_sensor             # noqa: PLC0415

    device_id = str(args.get("device_id") or "").strip()
    if not device_id:
        return {"ok": False, "error": "缺少必填参数 device_id"}

    # ISS-056 候选①：任意输入（规范/短）→ 库内当前形态（由 AUSCULT_DEVICE_ID_SCHEME
    # 决定；迁移前仍是短编号，迁移后是 PUMP-A-01）。未命中原样透传，真实未知设备
    # 不会被这张表伪装成有数据。
    resolved_id = _storage_id(device_id)

    sensor_ids = args.get("sensor_ids") or []
    if not sensor_ids and alarm is not None and alarm.metric:
        sensor_ids = [f"{alarm.device_id}.{alarm.metric}"]
    requested = [str(s) for s in sensor_ids]
    sensor_ids = requested[:_MAX_SENSORS_PER_CALL]
    if not sensor_ids:
        return {"ok": False, "error": "缺少参数 sensor_ids 且无法从告警推断测点"}

    # 超限**必须显式回灌**（2026-10-22 修复）：此前静默截断，模型把"没查"当成
    # "无数据"，于是 human_reason 里出现"温度测点无数据"的错误归因。
    notices: list[str] = []
    dropped = requested[_MAX_SENSORS_PER_CALL:]
    if dropped:
        notices.append(
            f"sensor_ids 超过单次上限 {_MAX_SENSORS_PER_CALL}，本次只查 "
            f"{sensor_ids}；未查询：{dropped}（它们**没有**结论，需另调用一次补齐）")

    now_ms = int(time.time() * 1000)
    # 窗口锚在告警时刻（历史/回放告警不再查到与告警无关的 now 窗口）
    anchor_ms = getattr(alarm, "ts", None) if alarm is not None else None
    start_ts, end_ts = _resolve_window(args.get("time_range"), now_ms=now_ms,
                                       anchor_ms=anchor_ms)
    baseline = getattr(alarm, "baseline", None)

    series: list[dict[str, Any]] = []
    errors: list[str] = []
    empty_reason: str | None = None
    for sensor in sensor_ids:
        short = sensor.split(".")[-1] if "." in sensor else sensor
        column = SENSOR_COLUMN_MAP.get(short)
        if column is None:
            errors.append(f"测点 {sensor} 未登记（无对应时序列）")
            continue
        try:
            rows = query_sensor(device_id=resolved_id, metric=column,
                                start_ts=start_ts, end_ts=end_ts,
                                timeout=1.0)["rows"]
        except (TimeoutError, ConnectionError, RuntimeError) as exc:
            errors.append(f"{sensor} 查询失败: {exc}")
            continue
        if not rows:
            # ISS-056：不再把"查不到"静默包装成 count=0 的有效证据 —— 必须告诉
            # 模型是"设备号不存在"还是"窗口内无数据"，它才能自我纠正。
            if _device_has_any_data(resolved_id):
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
        if notices:
            out["notices"] = notices
        out["window"] = {"start_ms": start_ts, "end_ms": end_ts}
        return out
    result: dict[str, Any] = {"device_id": resolved_id, "series": series,
                              "window": {"start_ms": start_ts, "end_ms": end_ts}}
    if device_id != resolved_id:
        # 透明度：让模型与审计都看到发生了编号归一（ISS-056）
        result["device_id_resolved"] = {"requested": device_id, "used": resolved_id}
    if errors:
        result["partial_errors"] = errors
    if empty_reason:
        result["empty_reason"] = empty_reason
    if notices:
        result["notices"] = notices
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


def tool_result_message(call_id: str, name: str, out: dict[str, Any]) -> dict[str, Any]:
    """工具结果 → OpenAI 兼容 role=tool 消息（回灌模型）。"""
    payload = out if out.get("ok") else {"error": out.get("error")}
    return {"role": "tool", "tool_call_id": call_id, "name": name,
            "content": json.dumps(payload, ensure_ascii=False)[:4000]}


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
