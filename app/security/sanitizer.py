"""输入净化与 Prompt 注入防御（D24 · M3.5）

职责（plan/Phase 3 §8.2 E10 + §六.7 告警）：
  1. 检测并中和 Prompt 注入模式（角色劫持 / 指令覆盖 / 系统提示提取）；
  2. 工具白名单校验（仅允许 schemas/tools_v2.json 中定义的工具）；
  3. 审计落库（安全事件写 reports/security_audit.jsonl）。

净化策略：
  - 检测注入模式 → 标记 + 替换为中性占位文本（不删除，保留可追溯性）；
  - 不依赖 LLM（确定性规则，与 D16 风险判定一致）；
  - 审计日志记录原始输入摘要 + 命中模式 + 处置动作。

对应交付物：plan/Phase 3 §五 D24 / §8.2 E10
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 常量

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG_PATH = PROJECT_ROOT / "reports" / "security_audit.jsonl"

# 工具白名单（对应 schemas/tools_v2.json 中定义的 5 个工具）
TOOL_WHITELIST: frozenset[str] = frozenset({
    "query_sensor",
    "get_maintenance_history",
    "query_graph",
    "retrieve_knowledge",
    "generate_report",
})

# ---------------------------------------------------------------- 注入模式

# 角色劫持 / 指令覆盖 / 系统提示提取
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("role_hijack",
     re.compile(r"(?i)(you\s+are\s+now|ignore\s+(previous|prior|above)\s+"
                r"instructions?|forget\s+(previous|prior|all)|"
                r"disregard\s+(previous|prior|all))")),
    ("instruction_override",
     re.compile(r"(?i)(system\s*:\s*|new\s+system\s+prompt|"
                r"override\s+(system|instructions)|"
                r"act\s+as\s+(if|a)\s+|pretend\s+you\s+are)")),
    ("prompt_extraction",
     re.compile(r"(?i)(reveal\s+(your|the)\s+(system|initial)\s+prompt|"
                r"show\s+me\s+your\s+instructions?|"
                r"what\s+is\s+your\s+system\s+prompt)")),
    ("tool_injection",
     re.compile(r"(?i)(call\s+tool\s*:|execute\s+function\s*:|"
                r"invoke\s+\w+\s*\(|run\s+command\s*:|"
                r"<tool_call>|<function_call>)")),
]

_NEUTRALIZED = "[已净化]"

# ---------------------------------------------------------------- 净化

def sanitize_input(text: str) -> dict[str, Any]:
    """检测并中和 Prompt 注入。

    返回:
      {
        "sanitized": str,         # 净化后文本
        "injected": bool,          # 是否检测到注入
        "patterns_hit": list[str], # 命中的模式名列表
        "original_length": int,
        "sanitized_length": int,
      }
    """
    if not text:
        return {"sanitized": text, "injected": False, "patterns_hit": [],
                "original_length": 0, "sanitized_length": 0}

    sanitized = text
    patterns_hit: list[str] = []

    for name, pattern in _INJECTION_PATTERNS:
        if pattern.search(sanitized):
            patterns_hit.append(name)
            sanitized = pattern.sub(_NEUTRALIZED, sanitized)

    return {
        "sanitized": sanitized,
        "injected": bool(patterns_hit),
        "patterns_hit": patterns_hit,
        "original_length": len(text),
        "sanitized_length": len(sanitized),
    }


def sanitize_state_inputs(state_dict: dict[str, Any]) -> dict[str, Any]:
    """批量净化 state 中的用户可控字段。

    净化对象：alarm.device_id / alarm.metric / diagnosis / evidence text /
              root_causes.cause / suggestions.action。

    返回净化后的 state dict 副本 + 注入摘要。
    """
    result = dict(state_dict)
    injections: list[dict[str, Any]] = []

    # alarm 字段
    alarm = result.get("alarm")
    if isinstance(alarm, dict):
        for field in ("device_id", "metric", "severity"):
            val = alarm.get(field)
            if isinstance(val, str):
                check = sanitize_input(val)
                if check["injected"]:
                    alarm[field] = check["sanitized"]
                    injections.append({"field": f"alarm.{field}",
                                       **check})

    # diagnosis
    diag = result.get("diagnosis")
    if isinstance(diag, str):
        check = sanitize_input(diag)
        if check["injected"]:
            result["diagnosis"] = check["sanitized"]
            injections.append({"field": "diagnosis", **check})

    # root_causes
    rcs = result.get("root_causes", [])
    for i, rc in enumerate(rcs):
        cause = rc.cause if hasattr(rc, "cause") else rc.get("cause", "")
        if isinstance(cause, str):
            check = sanitize_input(cause)
            if check["injected"]:
                if hasattr(rc, "cause"):
                    rc.cause = check["sanitized"]
                else:
                    rc["cause"] = check["sanitized"]
                injections.append({"field": f"root_causes[{i}].cause",
                                   **check})

    # suggestions
    sugs = result.get("suggestions", [])
    for i, s in enumerate(sugs):
        action = s.action if hasattr(s, "action") else s.get("action", "")
        if isinstance(action, str):
            check = sanitize_input(action)
            if check["injected"]:
                if hasattr(s, "action"):
                    s.action = check["sanitized"]
                else:
                    s["action"] = check["sanitized"]
                injections.append({"field": f"suggestions[{i}].action",
                                   **check})

    return {"state": result, "injections": injections}


# ---------------------------------------------------------------- 工具白名单

def validate_tool_call(tool_name: str) -> bool:
    """校验工具名是否在白名单中。"""
    return tool_name in TOOL_WHITELIST


def validate_tool_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """校验工具调用参数（基础校验：必填字段非空）。

    返回 {"valid": bool, "errors": list[str]}。
    """
    errors: list[str] = []
    if not validate_tool_call(tool_name):
        errors.append(f"工具 '{tool_name}' 不在白名单中")
        return {"valid": False, "errors": errors}

    # 各工具的必填字段
    required: dict[str, list[str]] = {
        "query_sensor": ["device_id"],
        "get_maintenance_history": ["device_id"],
        "query_graph": ["query"],
        "retrieve_knowledge": ["query"],
        "generate_report": ["thread_id"],
    }

    req_fields = required.get(tool_name, [])
    for field in req_fields:
        val = args.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"工具 '{tool_name}' 缺少必填字段 '{field}'")

    return {"valid": len(errors) == 0, "errors": errors}


# ---------------------------------------------------------------- 审计落库

def log_security_event(event: str, *,
                        thread_id: str | None = None,
                        detail: dict[str, Any] | None = None,
                        severity: str = "info") -> None:
    """安全事件审计落库。

    写入 reports/security_audit.jsonl（追加模式）。
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "thread_id": thread_id,
        "severity": severity,
        "detail": detail or {},
    }
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    # P5-W4/D12：PG audit_logs 双写（append-only 防篡改，权威审计层）
    # 写入失败不阻断（pg_audit 内部降级），JSONL 主路径保底
    try:
        from .pg_audit import append_audit   # noqa: PLC0415
        append_audit(event, severity=severity, thread_id=thread_id,
                     detail=detail)
    except Exception:   # noqa: BLE001 - PG 不可达时 JSONL 兜底
        pass


def audit_injection_attempt(thread_id: str | None,
                             field: str,
                             patterns_hit: list[str],
                             original_summary: str) -> None:
    """审计 Prompt 注入尝试。"""
    log_security_event(
        "prompt_injection_attempt",
        thread_id=thread_id,
        severity="warning",
        detail={
            "field": field,
            "patterns_hit": patterns_hit,
            "original_summary": original_summary[:100],
        })


def audit_tool_call(thread_id: str | None,
                     tool_name: str,
                     args_summary: dict[str, Any],
                     allowed: bool) -> None:
    """审计工具调用。"""
    log_security_event(
        "tool_call",
        thread_id=thread_id,
        severity="info" if allowed else "warning",
        detail={
            "tool": tool_name,
            "allowed": allowed,
            "args_summary": {k: str(v)[:50] for k, v in args_summary.items()},
        })
