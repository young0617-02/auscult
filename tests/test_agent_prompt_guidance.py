"""产品 Agent 提示词的「参数取值约定」回归锁（P1，2026-10-21）。

对应问题：V1 判据的失败**全部**集中在参数值（`window`/`time_range`/`aggregation`/
`fault_keywords`/`depth`·`direction`/`top_k`），而 `compare_arguments` 的口径是
「可选键缺失=采用默认值、不判错；显式给错值=判错」。故指引必须：
  1. 明确「用户没要求就不要传可选参数」；
  2. 给出用户原话 → 参数值的映射；
  3. **不得**出现任何用例编号（防把答案写进提示词）。
"""
from __future__ import annotations

import pytest

from app.agent.prompt import _AGENT_SYSTEM_TEMPLATE, build_agent_system_prompt


@pytest.fixture(scope="module")
def prompt() -> str:
    return build_agent_system_prompt("[]")


def test_guidance_section_present(prompt: str):
    assert "参数取值约定" in prompt
    assert "用户没明确要求就不要传" in prompt


def test_core_mappings_documented(prompt: str):
    """映射必须覆盖五类失败簇的关键取值。"""
    for token in ("time_range", "window", "aggregation", "sensor_ids",
                  "fault_keywords", "depth", "direction", "top_k"):
        assert token in prompt, f"缺失参数 {token} 的取值指引"
    for value in ("trend", "max", "avg", "count_over_limit", "15m", "1h", "outgoing", "both"):
        assert value in prompt, f"缺失取值示例 {value}"


def test_time_range_default_is_one_hour_not_24h(prompt: str):
    """「现在/刚才」类默认 1h —— 并把「不要放大成 24h」写成显式禁令。"""
    assert '"start":"1h"' in prompt.replace(" ", "")
    assert "不要放大成 24h" in prompt


def test_refusal_rules_preserved(prompt: str):
    """拒止规则 6a/6b/6 与「不调用工具时必须是文字」逐字保留（改动不得回退）。"""
    assert "若告警/上下文未给出**具体设备编号**" in prompt
    assert "超出系统职责" in prompt
    assert "不是空输出、不是 JSON" in prompt


def test_no_case_id_leakage(prompt: str):
    """提示词里不得出现 `v1-0xx` 这类用例编号（防教给测试）。"""
    assert "v1-" not in prompt and "v1r-" not in prompt


def test_prompt_size_bounded(prompt: str):
    """提示词每轮都随请求发送：分别锁模板与新增节的大小，防止无节制扩写。

    实测基线（2026-10-21）：模板 2159 字符（含占位符）+ 工具 JSON 6044 字符 = 8182；
    其中「参数取值约定」节 ≈ 864 字符（≈ +600 token/次调用）。
    """
    assert len(_AGENT_SYSTEM_TEMPLATE) < 2600, f"模板过长（{len(_AGENT_SYSTEM_TEMPLATE)} 字符）"
    start = prompt.find("## 参数取值约定")
    end = prompt.find("## 输出契约", start)
    assert 0 < start < end, "参数取值约定节缺失或位置异常"
    assert end - start < 1200, f"参数取值约定节过长（{end - start} 字符）"


def test_template_placeholder_still_required():
    """占位符契约不变：缺失时 build 必须报错（防止注入失效）。"""
    assert "{{TOOLS_JSON_SCHEMA}}" in _AGENT_SYSTEM_TEMPLATE
