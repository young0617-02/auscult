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

_MAX_SENSORS_PER_CALL = 3      # 单次工具调用最多查 3 个测点（延迟护栏）
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


def _resolve_window(time_range: Any, *, now_ms: int) -> tuple[int, int]:
    """time_range → (start_ms, end_ms)；缺省 start = now-24h，end = now。

    幻觉出的未来起点（start > now）钳制回 24h 窗口——不下发 start > end 的
    非法区间给 TDengine。
    """
    tr_ = time_range if isinstance(time_range, dict) else {}
    start = parse_timestamp(tr_.get("start"), now_ms=now_ms)
    end = parse_timestamp(tr_.get("end"), now_ms=now_ms)
    if start is None or start > now_ms:
        start = now_ms - 24 * 3_600_000
    if end is None or end < start or end > now_ms:
        end = now_ms
    return start, end


# ---------------------------------------------------------------- 各工具执行体

def _exec_query_sensor(args: dict[str, Any], alarm: Any) -> dict[str, Any]:
    from ..graph.nodes.analyze_sensor import _compute_stats   # noqa: PLC0415
    from ..tools.query_sensor import query_sensor             # noqa: PLC0415

    device_id = str(args.get("device_id") or "").strip()
    if not device_id:
        return {"ok": False, "error": "缺少必填参数 device_id"}

    sensor_ids = args.get("sensor_ids") or []
    if not sensor_ids and alarm is not None and alarm.metric:
        sensor_ids = [f"{alarm.device_id}.{alarm.metric}"]
    sensor_ids = [str(s) for s in sensor_ids][:_MAX_SENSORS_PER_CALL]
    if not sensor_ids:
        return {"ok": False, "error": "缺少参数 sensor_ids 且无法从告警推断测点"}

    now_ms = int(time.time() * 1000)
    start_ts, end_ts = _resolve_window(args.get("time_range"), now_ms=now_ms)
    baseline = getattr(alarm, "baseline", None)

    series: list[dict[str, Any]] = []
    errors: list[str] = []
    for sensor in sensor_ids:
        short = sensor.split(".")[-1] if "." in sensor else sensor
        column = SENSOR_COLUMN_MAP.get(short)
        if column is None:
            errors.append(f"测点 {sensor} 未登记（无对应时序列）")
            continue
        try:
            rows = query_sensor(device_id=device_id, metric=column,
                                start_ts=start_ts, end_ts=end_ts,
                                timeout=1.0)["rows"]
        except (TimeoutError, ConnectionError, RuntimeError) as exc:
            errors.append(f"{sensor} 查询失败: {exc}")
            continue
        values = [float(r["value"]) for r in rows]
        stats = _compute_stats(values, baseline if column == "vib_rms" else None)
        series.append({"sensor_id": sensor, "column": column, **stats})

    if not series:
        return {"ok": False, "error": "; ".join(errors) or "无可用测点数据"}
    result: dict[str, Any] = {"device_id": device_id, "series": series}
    if errors:
        result["partial_errors"] = errors
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
    relations = [str(r) for r in (args.get("relation_types") or [])]
    question = f"{start_node} 设备关系与故障关联"
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
    return {"ok": True, "result": {
        "degraded": False,
        "entities_hit": out.get("entities_hit") or [],
        "hits": [{"chunk_id": h.get("chunk_id", ""),
                  "score": round(float(h.get("score") or 0.0), 4)}
                 for h in hits[:_MAX_ROWS]],
    }}


def _exec_get_maintenance_history(args: dict[str, Any], alarm: Any) -> dict[str, Any]:
    from ..tools.get_maintenance_history import get_maintenance_history  # noqa: PLC0415

    device_id = str(args.get("device_id") or "").strip()
    if not device_id:
        return {"ok": False, "error": "缺少必填参数 device_id"}
    limit = min(int(args.get("limit") or 10), _MAX_ROWS)
    try:
        rows = get_maintenance_history(device_id, limit=limit, timeout=2.0)
    except (TimeoutError, ConnectionError, RuntimeError) as exc:
        return {"ok": False, "error": f"工单查询失败: {exc}"}
    return {"ok": True, "result": {
        "device_id": device_id,
        "work_orders": [{"order_id": r.get("order_id", ""),
                         "fault": r.get("fault", ""),
                         "action": r.get("action", ""),
                         "result": r.get("result"),
                         "created_at": str(r.get("created_at") or "")[:19]}
                        for r in rows],
    }}


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
                "error": "写操作护栏：报告生成需经人工审核通过后由系统统一执行，"
                         "Agent 不直接生成报告。请继续输出诊断结论 JSON。"}

    if not validate_tool_call(product_name):
        audit_tool_call(thread_id, product_name, {"args_keys": sorted(args)},
                        allowed=False)
        return {"ok": False, "error": f"工具 '{name}' 不在白名单中，已拒绝执行"}

    # 参数级前置校验（2026-10-21 接线）：此前 validate_tool_args 从未被调用，
    # 缺参只能靠各执行体手工兜底 —— 统一在这里拦，模型可据 error 自我纠正。
    arg_check = validate_tool_args(product_name, args)
    if not arg_check["valid"]:
        audit_tool_call(thread_id, product_name,
                        {"args_keys": sorted(args), "invalid": arg_check["errors"]},
                        allowed=False)
        return {"ok": False,
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
