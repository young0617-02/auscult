"""parse_alarm 节点（D2）

确定性规则解析：从初始 state 接收告警事件，规范化为 AlarmEvent。
从 configs/alarm_rules.yml 匹配规则，补全 baseline/rule_id/severity。

对应交付物：plan/Phase 3 §三.2 / §五 D2
超时预算：100ms（确定性，无 IO）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..state import AlarmEvent, DiagnosisState

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = PROJECT_ROOT / "configs" / "alarm_rules.yml"

_rules_cache: dict | None = None


def _load_rules() -> dict:
    """惰性加载 alarm_rules.yml（进程内缓存）。"""
    global _rules_cache
    if _rules_cache is None:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            _rules_cache = yaml.safe_load(f)
    return _rules_cache


def _match_rule(metric: str, rules: dict) -> dict | None:
    """按 metric 匹配告警规则。"""
    for rule in rules.get("rules", []):
        if rule.get("metric") == metric:
            return rule
    return None


def parse_alarm(state: DiagnosisState) -> dict[str, Any]:
    """确定性规则解析 + AlarmEvent 规范化。

    输入：state.alarm（dict | AlarmEvent | None）
    输出：{"alarm": AlarmEvent} 或 {"errors": [...]}

    规范化逻辑：
      1. dict → AlarmEvent（Pydantic 校验）
      2. 从 alarm_rules.yml 匹配 metric → 补全 baseline/rule_id/severity
      3. 校验 device_id 非空
    """
    alarm = state.alarm

    if alarm is None:
        return {"errors": [{"node": "parse_alarm", "code": "E_NO_ALARM",
                            "msg": "输入缺少告警事件"}]}

    # Pydantic 已将 dict 自动转为 AlarmEvent（DiagnosisState.alarm: AlarmEvent | None）
    if not isinstance(alarm, AlarmEvent):
        return {"errors": [{"node": "parse_alarm", "code": "E_BAD_TYPE",
                            "msg": f"alarm 类型异常: {type(alarm).__name__}"}]}

    if not alarm.device_id:
        return {"errors": [{"node": "parse_alarm", "code": "E_NO_DEVICE",
                            "msg": "告警事件缺少 device_id"}]}

    # 从 alarm_rules.yml 补全缺失字段（默认值视为"未设置"）
    rules = _load_rules()
    rule = _match_rule(alarm.metric, rules)

    updates: dict[str, Any] = {}
    if rule:
        if alarm.baseline is None and rule.get("threshold") is not None:
            updates["baseline"] = rule["threshold"]
        if not alarm.rule_id and rule.get("rule_id"):
            updates["rule_id"] = rule["rule_id"]
        # severity="medium" 是默认值，若规则有更高 severity 则补全
        if alarm.severity == "medium" and rule.get("severity"):
            updates["severity"] = rule["severity"]

    if updates:
        alarm = alarm.model_copy(update=updates)

    return {"alarm": alarm}
