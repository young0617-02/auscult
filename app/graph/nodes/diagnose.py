"""diagnose 节点（D6-D8）

D6: 接入本地 deepseek-r1:7b（Ollama）推理 + think 剥离 + JSON 解析
D7: 置信度复合公式（检索 0.35 / 传感器 0.20 / 图谱 0.15 / 自评 0.30）
D8: 置信度校准框架（当前恒等映射，后续 Platt scaling）

超时预算: 30s; 降级: Ollama 不可达 → degraded + retry_count++

对应交付物: plan/Phase 3 §三.2 / §五 D6-D8 / §六.2 置信度公式
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from ..state import DiagnosisState, RootCause, Suggestion


def _normalize_cite(cite: str) -> str:
    """规范化证据引用：兼容 LLM 产出的 `chunk_id=<id>` 与纯 `<id>` 两种形态。

    背景（2026-10-14 修复）：diagnose 提示词示例给出的是纯 id，但模型实际常输出
    `chunk_id=<id>`；而 evidence 的 chunk_id 为纯 id。不规范化会导致
    finalize 的引用校验恒判「无效」→ 误报 + 幂等键随格式漂移。
    """
    c = (cite or "").strip()
    return c[len("chunk_id="):].strip() if c.startswith("chunk_id=") else c

# ---------------------------------------------------------------- Ollama 配置

OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
OLLAMA_MODEL = "deepseek-r1:7b"
TIMEOUT_SEC = 30.0

# ---------------------------------------------------------------- think 剥离（复用 llm_adapter 正则模式）

_T_OPEN = "<" + "think" + ">"
_T_CLOSE = "<" + "/" + "think" + ">"
_T_OPEN_LONG = "<" + "thinking" + ">"
_T_CLOSE_LONG = "<" + "/" + "thinking" + ">"
_R1_END = "<\u2768end\u2581of\u2581thinking\u2769>"

_THINK_BLOCK_RE = re.compile(
    "(" + _T_OPEN + "|" + _T_OPEN_LONG + ")(.*?)(?:" + _T_CLOSE + "|"
    + _T_CLOSE_LONG + "|" + re.escape(_R1_END) + ")", re.S,
)
_UNCLOSED_THINK_RE = re.compile(
    "(" + _T_OPEN + "|" + _T_OPEN_LONG + ")(.*)$", re.S,
)

_JSON_DECODER = json.JSONDecoder()


def _strip_think(text: str) -> str:
    """剥离 think 区块（成对 + 未闭合）。"""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _UNCLOSED_THINK_RE.sub("", text)
    return text.strip()


def _extract_json(text: str) -> dict | None:
    """从文本中提取第一个顶层 JSON 对象。"""
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start < 0:
            break
        try:
            obj, end = _JSON_DECODER.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = start + 1
    return None


# ---------------------------------------------------------------- prompt 装配

_SYSTEM_PROMPT = """你是工业设备故障诊断专家。根据告警信息、传感器数据、知识证据、图谱路径和历史工单，分析故障根因并给出建议。

输出要求（严格 JSON 格式，不要输出其他内容）：
{
  "diagnosis": "诊断结论（一句话概述）",
  "root_causes": [
    {"cause": "根因描述", "citations": ["chunk_id1"], "confidence_hint": 0.8}
  ],
  "suggestions": [
    {"action": "建议动作", "citations": ["chunk_id1"], "risk": "low"}
  ],
  "self_confidence": 0.75
}

注意：
- citations 引用 evidence 中的 chunk_id
- confidence_hint ∈ [0,1]，表示该根因的置信度
- risk ∈ {low, medium, high}
- self_confidence ∈ [0,1]，表示你对整体诊断的置信度
"""


def _build_user_prompt(state: DiagnosisState) -> str:
    """从 state 构造 user prompt（注入全部上下文）。"""
    alarm = state.alarm
    parts: list[str] = []

    # 告警
    parts.append(f"【告警】设备={alarm.device_id} 测点={alarm.metric} "
                 f"当前值={alarm.value} 阈值={alarm.baseline} "
                 f"严重度={alarm.severity}")

    # 传感器数据
    sr = state.sensor_report
    if sr:
        parts.append(f"【传感器】数据点={sr['count']} 均值={sr['avg']} "
                     f"峰值={sr['max']} 趋势={sr['trend']} "
                     f"超阈值持续={sr.get('exceed_duration_ms', 0)}ms")

    # 知识证据
    if state.evidence:
        ev_lines = []
        for i, ev in enumerate(state.evidence[:10], 1):
            ev_lines.append(f"  [{i}] chunk_id={ev.chunk_id} "
                            f"score={ev.score:.3f} type={ev.source_type} "
                            f"text={ev.text[:80]}")
        parts.append("【知识证据】\n" + "\n".join(ev_lines))

    # 图谱路径
    if state.graph_paths:
        gp_lines = [f"  {gp.description}" for gp in state.graph_paths]
        parts.append("【图谱路径】\n" + "\n".join(gp_lines))

    # 历史工单
    if state.work_orders:
        wo_lines = [f"  [{wo.order_id}] {wo.fault} → {wo.action}"
                     for wo in state.work_orders]
        parts.append("【历史工单】\n" + "\n".join(wo_lines))

    parts.append("请根据以上信息，输出故障诊断 JSON。")
    return "\n".join(parts)


# ---------------------------------------------------------------- Ollama 调用

def _call_ollama(messages: list[dict], timeout: float = TIMEOUT_SEC) -> str:
    """调用 Ollama /v1/chat/completions，返回 content 文本。

    异常: TimeoutError / ConnectionError / RuntimeError
    """
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 2048,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
    except TimeoutError:
        raise
    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            raise TimeoutError(f"Ollama 超时: {e}")
        raise ConnectionError(f"Ollama 不可达: {e}")
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Ollama 响应异常: {e}")


# ---------------------------------------------------------------- D7: 置信度复合公式

def compute_confidence(
    state: DiagnosisState,
    self_confidence: float,
) -> tuple[float, dict[str, float]]:
    """置信度复合公式（plan §六.2）。

    检索 0.35 / 传感器 0.20 / 图谱 0.15 / 自评 0.30
    返回 (confidence, breakdown)
    """
    # 检索覆盖度: evidence 数量 / 期望 5 条
    retrieval = min(len(state.evidence) / 5.0, 1.0)

    # 传感器数据质量
    sensor = 0.0
    if state.sensor_report:
        if state.sensor_report.get("count", 0) > 0:
            sensor = 0.5
            if state.sensor_report.get("trend") != "unknown":
                sensor = 1.0

    # 图谱命中度
    graph = min(len(state.graph_paths) / 3.0, 1.0)

    # LLM 自评
    self_score = max(0.0, min(1.0, self_confidence))

    confidence = (
        0.35 * retrieval + 0.20 * sensor
        + 0.15 * graph + 0.30 * self_score
    )
    return round(confidence, 4), {
        "retrieval": round(retrieval, 4),
        "sensor": round(sensor, 4),
        "graph": round(graph, 4),
        "self": round(self_score, 4),
    }


# ---------------------------------------------------------------- D8: 校准框架

def calibrate_confidence(raw: float, _: Any = None) -> float:
    """置信度校准（D8 框架）。

    当前: 恒等映射（identity calibration）
    后续: 有评测数据后改用 Platt scaling 或温度校准
    目标: ECE ≤ 0.10
    """
    return max(0.0, min(1.0, raw))


def compute_ece(
    predictions: list[tuple[float, bool]],
    n_bins: int = 10,
) -> float:
    """计算 Expected Calibration Error（D8 评测用）。

    predictions: [(confidence, is_correct), ...]
    返回: ECE ∈ [0,1]，越低越好
    """
    if not predictions:
        return 1.0
    bin_size = 1.0 / n_bins
    ece = 0.0
    for i in range(n_bins):
        lo, hi = i * bin_size, (i + 1) * bin_size
        bin_items = [(c, r) for c, r in predictions if lo <= c < hi or (i == n_bins - 1 and c == 1.0)]
        if not bin_items:
            continue
        avg_conf = sum(c for c, _ in bin_items) / len(bin_items)
        avg_acc = sum(1 for _, r in bin_items if r) / len(bin_items)
        ece += abs(avg_conf - avg_acc) * len(bin_items) / len(predictions)
    return round(ece, 4)


# ---------------------------------------------------------------- D6: diagnose 节点

def _determine_risk_level(alarm_severity: str, confidence: float) -> str:
    """风险等级判定。"""
    if confidence < 0.50:
        return "high"
    if confidence < 0.75:
        return "medium"
    if alarm_severity == "high" and confidence < 0.85:
        return "high"
    return "low"


def diagnose(state: DiagnosisState) -> dict[str, Any]:
    """接入 deepseek-r1:7b 推理 + 置信度计算。

    输入: state（alarm + sensor_report + evidence + graph_paths + work_orders）
    输出: {"diagnosis", "root_causes", "suggestions", "confidence",
           "confidence_breakdown", "risk_level"}
    降级: Ollama 不可达 → retry_count++ + errors
    """
    alarm = state.alarm
    if alarm is None:
        return {"errors": [{"node": "diagnose", "code": "E_NO_ALARM",
                            "msg": "缺少告警事件"}]}

    # 调用 LLM
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(state)},
    ]
    try:
        raw_content = _call_ollama(messages, timeout=TIMEOUT_SEC)
    except (TimeoutError, ConnectionError) as exc:
        return {
            "retry_count": state.retry_count + 1,
            "errors": [{"node": "diagnose", "code": "E_LLM_UNREACHABLE",
                        "msg": str(exc)}],
        }
    except RuntimeError as exc:
        return {
            "retry_count": state.retry_count + 1,
            "errors": [{"node": "diagnose", "code": "E_LLM_ERROR",
                        "msg": str(exc)}],
        }

    # 剥离 think + 解析 JSON
    clean = _strip_think(raw_content)
    parsed = _extract_json(clean)

    if parsed is None:
        # JSON 解析失败：用原始文本作为诊断
        return {
            "diagnosis": clean[:500],
            "root_causes": [],
            "suggestions": [],
            "retry_count": state.retry_count + 1,
            "errors": [{"node": "diagnose", "code": "E_JSON_PARSE",
                        "msg": "LLM 输出 JSON 解析失败"}],
        }

    # 提取字段
    diagnosis_text = parsed.get("diagnosis", "")
    # 引用规范化（2026-10-14 修复）：LLM 常把引用写成 `chunk_id=<id>`，而 evidence 的
    # chunk_id 为纯 id —— 不规范化会使 finalize 的引用校验恒判无效（误报 + 幂等键漂移）。
    root_causes = [
        RootCause(
            cause=rc.get("cause", ""),
            citations=[_normalize_cite(c) for c in rc.get("citations", [])],
            confidence_hint=rc.get("confidence_hint", 0.0),
        )
        for rc in parsed.get("root_causes", [])
    ]
    suggestions = [
        Suggestion(
            action=s.get("action", ""),
            citations=[_normalize_cite(c) for c in s.get("citations", [])],
            risk=s.get("risk", "low"),
        )
        for s in parsed.get("suggestions", [])
    ]
    self_conf = float(parsed.get("self_confidence", 0.5))

    # D7: 置信度复合公式
    raw_conf, breakdown = compute_confidence(state, self_conf)

    # D8: 校准
    confidence = calibrate_confidence(raw_conf)

    # risk_level
    risk = _determine_risk_level(alarm.severity, confidence)

    return {
        "diagnosis": diagnosis_text,
        "root_causes": root_causes,
        "suggestions": suggestions,
        "confidence": confidence,
        "confidence_breakdown": breakdown,
        "risk_level": risk,
    }
