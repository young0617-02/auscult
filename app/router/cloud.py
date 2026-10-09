"""云端路由（D14-D15 · M3.3 混合推理）

职责：当本地 diagnose 置信度 ∈ [0.50, 0.75) 时，将**脱敏后**的诊断上下文
转发至云端 Qwen/Qwen3.8-27B（ModelScope，OpenAI 兼容端点）做二次诊断，
用云端结论覆盖本地诊断结果并重算置信度。

关键设计（plan §六.4）：
  - **脱敏前置**：送云端前剥离 device_id / 厂区 / 工艺参数标识，只保留
    "故障现象 + 通用知识 + 统计摘要"（V5.0 §七 防线①）；
  - **超时 20s**：失败 → degrade_reason="cloud_unavailable"，保留本地诊断；
  - **审计**：每次升级写 `reports/cloud_audit.jsonl`（含脱敏前后 hash + 预算计数）；
  - **预算熔断**（D15）：`budget:cloud:{day}` Redis 按天计数，超 `per_day_calls` 熔断 →
    `degrade_reason="budget_exceeded"`；Redis 不可达 → 不阻塞（审计记录）。

对应交付物：plan/Phase 3 §三.3 / §五 D14-D15 / §六.4
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from ..graph.nodes.diagnose import (
    _SYSTEM_PROMPT,
    _determine_risk_level,
    _extract_json,
    _strip_think,
    calibrate_confidence,
    compute_confidence,
)
from ..graph.state import DiagnosisState, RootCause, Suggestion

# ---------------------------------------------------------------- 路径与常量

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLOUD_CONFIG_PATH = PROJECT_ROOT / "env" / "cloud.json"
AUDIT_LOG_PATH = PROJECT_ROOT / "reports" / "cloud_audit.jsonl"

CLOUD_TIMEOUT_SEC = 20.0   # plan §六.4：超时 20s


# ---------------------------------------------------------------- 配置加载

_config_cache: dict | None = None


def load_cloud_config(path: Path = CLOUD_CONFIG_PATH) -> dict[str, Any]:
    """惰性加载 env/cloud.json（进程内缓存）。

    返回 keys: provider / model / endpoint / api_key / budget_lock
    """
    global _config_cache
    if _config_cache is None:
        cfg = json.loads(path.read_text(encoding="utf-8"))
        missing = [k for k in ("model", "endpoint", "api_key") if not cfg.get(k)]
        if missing:
            raise RuntimeError(f"env/cloud.json 缺必填项: {missing}")
        _config_cache = cfg
    return _config_cache


# ---------------------------------------------------------------- 预算熔断（D15 接入 budget.py）

from .budget import BudgetGuard, budget_status   # noqa: E402


def check_budget() -> bool:
    """预算熔断检查（D15 已接入 budget.py）。"""
    ok, _, _, _ = BudgetGuard().check()
    return ok


# ---------------------------------------------------------------- 脱敏

def _hash_device_id(device_id: str) -> str:
    """device_id → 设备#<sha256[:6]>（可追溯不可逆）。"""
    digest = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:6]
    return f"设备#{digest}"


def sanitize_state(state: DiagnosisState) -> dict[str, Any]:
    """脱敏：剥离 device_id / 厂区 / 工艺参数标识。

    保留：
      - metric / value / baseline / severity（诊断必需，非 PII）
      - sensor 统计摘要（count/avg/max/trend，无 PII）
      - evidence text（知识库通用内容）
      - graph_paths description（通用关系）
      - work_orders 的 fault/action 文本（剥离 device_id）

    剥离：
      - alarm.device_id → 设备#<hash>
      - work_orders[].device_id → 设备#<hash>
    """
    alarm = state.alarm
    safe_device = _hash_device_id(alarm.device_id) if alarm and alarm.device_id else "设备#unknown"

    safe_alarm: dict[str, Any] = {}
    if alarm:
        safe_alarm = {
            "device_id": safe_device,
            "metric": alarm.metric,
            "value": alarm.value,
            "baseline": alarm.baseline,
            "severity": alarm.severity,
        }

    safe_wo = [
        {
            "order_id": wo.order_id,
            "device_id": _hash_device_id(wo.device_id) if wo.device_id else safe_device,
            "fault": wo.fault,
            "action": wo.action,
        }
        for wo in state.work_orders
    ]

    return {
        "alarm": safe_alarm,
        "sensor_report": state.sensor_report,
        "evidence": [
            {"chunk_id": ev.chunk_id, "text": ev.text, "score": ev.score,
             "source_type": ev.source_type}
            for ev in state.evidence
        ],
        "graph_paths": [{"description": gp.description} for gp in state.graph_paths],
        "work_orders": safe_wo,
    }


def _build_cloud_prompt(sanitized: dict[str, Any]) -> str:
    """从脱敏后的 dict 构造 user prompt（与 diagnose 同结构，但 device_id 已脱敏）。"""
    alarm = sanitized["alarm"]
    parts: list[str] = []
    parts.append(f"【告警】设备={alarm['device_id']} 测点={alarm['metric']} "
                 f"当前值={alarm['value']} 阈值={alarm.get('baseline')} "
                 f"严重度={alarm['severity']}")

    sr = sanitized.get("sensor_report")
    if sr:
        parts.append(f"【传感器】数据点={sr.get('count')} 均值={sr.get('avg')} "
                     f"峰值={sr.get('max')} 趋势={sr.get('trend')} "
                     f"超阈值持续={sr.get('exceed_duration_ms', 0)}ms")

    ev_list = sanitized.get("evidence", [])
    if ev_list:
        ev_lines = []
        for i, ev in enumerate(ev_list[:10], 1):
            ev_lines.append(f"  [{i}] chunk_id={ev['chunk_id']} "
                            f"score={ev.get('score', 0):.3f} "
                            f"type={ev.get('source_type', 'knowledge')} "
                            f"text={ev.get('text', '')[:80]}")
        parts.append("【知识证据】\n" + "\n".join(ev_lines))

    gp_list = sanitized.get("graph_paths", [])
    if gp_list:
        gp_lines = [f"  {gp['description']}" for gp in gp_list]
        parts.append("【图谱路径】\n" + "\n".join(gp_lines))

    wo_list = sanitized.get("work_orders", [])
    if wo_list:
        wo_lines = [f"  [{wo['order_id']}] {wo['fault']} → {wo['action']}"
                    for wo in wo_list]
        parts.append("【历史工单】\n" + "\n".join(wo_lines))

    parts.append("请根据以上信息，输出故障诊断 JSON。")
    return "\n".join(parts)


# ---------------------------------------------------------------- 审计

def _sha256_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def write_audit(record: dict[str, Any]) -> None:
    """追加审计记录到 reports/cloud_audit.jsonl。

    record keys: ts / thread_id / hash_pre / hash_post / model /
                 success / latency_ms / error / budget_ok
    """
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- 云端调用

def call_cloud(messages: list[dict], *, timeout: float = CLOUD_TIMEOUT_SEC) -> str:
    """调用云端 OpenAI 兼容端点，返回 content 文本。

    异常: TimeoutError / ConnectionError / RuntimeError
    """
    cfg = load_cloud_config()
    payload = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 2048,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        cfg["endpoint"], data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg['api_key']}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except TimeoutError:
        raise
    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            raise TimeoutError(f"云端超时: {e}")
        raise ConnectionError(f"云端不可达: {e}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"云端响应异常: {e}")


# ---------------------------------------------------------------- 路由编排

class CloudRouter:
    """云端升级路由（D14）。

    escalate(state) → dict（LangGraph 增量）：
      成功: {diagnosis, root_causes, suggestions, confidence,
             confidence_breakdown, risk_level, escalate_cloud: True}
      失败: {degrade_reason: "cloud_unavailable", escalate_cloud: True, errors}
      预算熔断: {degrade_reason: "budget_exceeded", escalate_cloud: True, errors}
    """

    def escalate(self, state: DiagnosisState) -> dict[str, Any]:
        ts_start = time.perf_counter()
        ts_iso = datetime.now().isoformat()
        _budget = BudgetGuard()

        # 预算熔断（D15）
        b_ok, b_count, b_limit, b_reason = _budget.check()
        if not b_ok:
            write_audit({"ts": ts_iso, "thread_id": state.thread_id,
                         "model": "N/A", "success": False,
                         "latency_ms": 0, "error": b_reason,
                         "budget_ok": False,
                         "budget_count": b_count, "budget_limit": b_limit})
            return {"degrade_reason": "budget_exceeded",
                    "escalate_cloud": True,
                    "errors": [{"node": "escalate_cloud",
                                "code": "E_BUDGET_EXCEEDED",
                                "msg": f"云端预算熔断（{b_count}/{b_limit}），强制本地降级"}]}

        # 脱敏
        sanitized = sanitize_state(state)
        user_prompt = _build_cloud_prompt(sanitized)
        hash_post = _sha256_short(user_prompt)

        # 脱敏前原文 hash（审计用：取未脱敏 prompt）
        from ..graph.nodes.diagnose import _build_user_prompt as _build_local  # noqa: PLC0415
        local_prompt = _build_local(state)
        hash_pre = _sha256_short(local_prompt)

        # 调用云端
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        cfg = load_cloud_config()
        try:
            raw_content = call_cloud(messages, timeout=CLOUD_TIMEOUT_SEC)
        except (TimeoutError, ConnectionError, RuntimeError) as exc:
            latency_ms = round((time.perf_counter() - ts_start) * 1000, 1)
            write_audit({"ts": ts_iso, "thread_id": state.thread_id,
                         "hash_pre": hash_pre, "hash_post": hash_post,
                         "model": cfg["model"], "success": False,
                         "latency_ms": latency_ms,
                         "error": f"{type(exc).__name__}: {exc}",
                         "budget_ok": True,
                         "budget_count": b_count, "budget_limit": b_limit})
            return {"degrade_reason": "cloud_unavailable",
                    "escalate_cloud": True,
                    "errors": [{"node": "escalate_cloud",
                                "code": "E_CLOUD_UNAVAILABLE",
                                "msg": str(exc)}]}

        # 剥离 think + 解析 JSON（复用 diagnose）
        clean = _strip_think(raw_content)
        parsed = _extract_json(clean)

        latency_ms = round((time.perf_counter() - ts_start) * 1000, 1)

        if parsed is None:
            write_audit({"ts": ts_iso, "thread_id": state.thread_id,
                         "hash_pre": hash_pre, "hash_post": hash_post,
                         "model": cfg["model"], "success": False,
                         "latency_ms": latency_ms,
                         "error": "JSON parse failed",
                         "budget_ok": True,
                         "budget_count": b_count, "budget_limit": b_limit})
            return {"degrade_reason": "cloud_unavailable",
                    "escalate_cloud": True,
                    "errors": [{"node": "escalate_cloud",
                                "code": "E_CLOUD_JSON_PARSE",
                                "msg": "云端输出 JSON 解析失败"}]}

        # 提取字段（与 diagnose 同结构）
        diagnosis_text = parsed.get("diagnosis", "")
        root_causes = [
            RootCause(
                cause=rc.get("cause", ""),
                citations=rc.get("citations", []),
                confidence_hint=rc.get("confidence_hint", 0.0),
            )
            for rc in parsed.get("root_causes", [])
        ]
        suggestions = [
            Suggestion(
                action=s.get("action", ""),
                citations=s.get("citations", []),
                risk=s.get("risk", "low"),
            )
            for s in parsed.get("suggestions", [])
        ]
        self_conf = float(parsed.get("self_confidence", 0.5))

        # 重算置信度 + 风险等级（复用 diagnose）
        raw_conf, breakdown = compute_confidence(state, self_conf)
        confidence = calibrate_confidence(raw_conf)
        alarm_severity = state.alarm.severity if state.alarm else "medium"
        risk = _determine_risk_level(alarm_severity, confidence)

        # 预算计数 +1（D15）
        new_count = _budget.increment()

        # 审计
        write_audit({"ts": ts_iso, "thread_id": state.thread_id,
                     "hash_pre": hash_pre, "hash_post": hash_post,
                     "model": cfg["model"], "success": True,
                     "latency_ms": latency_ms,
                     "confidence": confidence, "risk_level": risk,
                     "budget_ok": True, "budget_count": new_count,
                     "budget_limit": b_limit})

        return {
            "diagnosis": diagnosis_text,
            "root_causes": root_causes,
            "suggestions": suggestions,
            "confidence": confidence,
            "confidence_breakdown": breakdown,
            "risk_level": risk,
            "escalate_cloud": True,
        }
