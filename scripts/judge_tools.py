"""V1 自动判分器（T2.2）

对应交付物：`Phase 0 详细开发计划（D1-D10 可执行版）.md` §三 D2–D3 · T2.2
判据依据：`reports/v1-report.md` §3.3、§四（8 项指标定义逐字来自上游计划）

判分逻辑（四步，顺序不可颠倒）：
  1. **工具名匹配**：`tool_calls[0].name` vs 期望名（指标 1 的定义）；
     多工具用例额外判定指标 `1b_多工具集合覆盖`：`Counter(expected) == Counter(actual)`
     —— 即**多重集精确相等**（顺序不限，但**多给工具即判否**）。
     ⚠️ 该口径严于下方第 3 步的「数组超集可接受」：多工具调用的**工具集合**必须精确一致，
     而单个工具的**数组类参数**允许超集。指标名中的「覆盖」为历史命名，实际语义以本行为准
     （见 `docs/known-issues.md` ISS-016）。
  2. **JSON Schema 校验**：参数是否符合 `schemas/tools_v1.json` v1（指标 2）。
  3. **参数值比对**：`time_range` → **±10% 语义等价**；数组参数 → **超集可接受**
     （actual 覆盖 expected 全部项即可，多给项不判错）；其余标量 → 精确匹配。
  4. **重试计数 + 失败归类**：
     工具名错 / JSON 不可解析 / 参数缺失 / 参数值错 / 该拒绝却调用 / 该调用却拒绝 / 格式退化。

判分口径（2026-09-24 裁决，与本函数 `compare_arguments` 注释一致）：
  - **语义缺省**：仅 schema `required` 键缺失判「参数缺失」；`expected` 中的可选键
    若实际缺失，视为采用默认值，不判错，已存在才比对值。
  - **数组超集**：`category_filter` / `sensor_ids` 等数组按集合覆盖判，多给项可接受。
  -（该口径取代旧的「expected 列出则必显」与「数组精确相等」，详见 v1-report §四/§10.3 扩张）
  - **自由长文本宽松（2026-09-24 第二轮修订）**：`search_knowledge.query` 走语义匹配
    （精确 / 子串 / 关键词 bigram 交叠 / 域概念覆盖，见 `_query_semantic_match`）；
    `generate_report.diagnosis_summary` 仅判「非空文本」（见 `_free_text_ok`，长度下限由
    Schema minLength 保证）；`generate_report.evidence_refs` 只校验**非空且 type 合法**
    （F6 复审 v3；类型覆盖度降为诊断项，不再判错），忽略具体 `ref`（见 `_refs_type_ok`）。
  - **应拒绝不再误判退化**：应拒绝用例（expect_reject）下模型正确不调用任何工具
    （`tool_calls_missing=True`）是**期望行为，不属于「格式退化」**；仅真实请求错误
    （`error`）计入退化（见 `judge_record` 的 `degraded` 计算）。
  - **v2 复审归一化（2026-09-30 裁决，对应 `schemas/tools_v2.json` 与复审 §四）**：
      · D1 `query_sensor.window` 量纲归一比对：`15m`/`15min`/`900s` 等价（`duration_equivalent`）；
      · D2 `query_sensor.aggregation` 超限类别名：`count_over_limit`/`count`/`over_limit`/`exceed_count`
        视为等价（`_aggregation_over_limit_equivalent`）；
      · D3 `time_range` 绝对时间已即时区等价（`parse_iso`→epoch，见 `time_range_equivalent` docstring）；
      · D5 `generate_report` 判分收敛为**意图 + 3 项必填**
        （`device_id`/`diagnosis_summary`/`evidence_refs`），`severity`/`format`/
        `recommended_actions`/`idempotency_key` 不参与正确性比对。

判分纪律（来自报告，违反即结论失真）：
  - 指标 5（首次成功率）与指标 6（重试后成功率）**必须分行报**，禁止只报「成功率」；
  - `tool_calls` 缺失属 **R-V1-3 静默退化**，记为 `格式退化`，**不得**混入「工具名错」；
  - `generate_report.idempotency_key` 由模型自生成，**只校验正则、不比对具体值**；
  - 判据适用对象是**首次成功率**，重试后成功率仅作辅助。

自检：`python scripts/judge_tools.py --selftest`
用法：`python scripts/judge_tools.py --raw experiments/v1/raw/results.jsonl --out experiments/v1/summary.csv`
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import param_normalizer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "tools_v2.json"  # P5 缩描述实测为负结果（EXP-V1-008），已回退至 v2
CASES_PATH = PROJECT_ROOT / "evals" / "v1_cases.jsonl"

# 判据（逐字采用上游计划 §五 / reports/v1-report.md §7.1）
PASS_FIRST_SUCCESS = 0.90
PASS_PARSEABLE = 0.95
MID_LOWER = 0.70

TIME_TOLERANCE = 0.10          # time_range ±10% 语义等价
MAX_RETRY = 3                  # 重试上限（≤3 次内全对记为「重试后成功」）

# 失败归类枚举（与 reports/v1-report.md §3.3 第 5 条一一对应）
FAIL_TOOL_NAME = "工具名错"
FAIL_JSON = "JSON 不可解析"
FAIL_MISSING_PARAM = "参数缺失"
FAIL_PARAM_VALUE = "参数值错"
FAIL_SHOULD_REJECT = "该拒绝却调用"
FAIL_SHOULD_CALL = "该调用却拒绝"
FAIL_DEGRADED = "格式退化"
FAIL_STEP_CHAIN = "多工具步骤链失败"   # D4（P6 拆步）：execution_mode=step_chain 用例的链式失败

# 由模型自生成、只校验格式不比对值的参数
FORMAT_ONLY_PARAMS = {("generate_report", "idempotency_key")}

# v2（2026-09-30 复审）：
#  - OVER_LIMIT_ALIAS：`query_sensor.aggregation` 超限类别名，服务端统一为 count_over_limit
#  - REPORT_VERDICT_KEYS：`generate_report` 参与正确性比对的必填/意图键白名单
OVER_LIMIT_ALIAS = {"count_over_limit", "count", "over_limit", "exceed_count"}
REPORT_VERDICT_KEYS = {"device_id", "diagnosis_summary", "evidence_refs"}
# F6（复审 v3）：evidence_refs 允许的 type 枚举（与 schema 一致）
_REF_TYPES = {"sensor", "knowledge", "graph", "maintenance"}


# ---------------------------------------------------------------- Schema 校验
# 说明：仅实现 Schema v1 实际用到的 draft-07 关键字，避免引入第三方依赖。
# 覆盖：type / enum / const / pattern / minLength / maxLength / minimum / maximum /
#       minItems / maxItems / items / required / properties / additionalProperties

_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def validate(schema: dict[str, Any], value: Any, path: str = "$") -> list[str]:
    """按 JSON Schema 校验单个值，返回错误信息列表（空列表 = 通过）。"""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return errors

    expected_type = schema.get("type")
    if expected_type:
        py_types = _TYPE_MAP.get(expected_type)
        if py_types is None:
            errors.append(f"{path}: 未支持的 schema 类型 {expected_type!r}")
        else:
            ok = isinstance(value, py_types)
            if ok and expected_type in ("integer", "number") and isinstance(value, bool):
                ok = False                      # bool 是 int 的子类，必须排除
            if not ok:
                errors.append(f"{path}: 类型应为 {expected_type}，实际 {type(value).__name__}")
                return errors

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 应为常量 {schema['const']!r}，实际 {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} 不在枚举 {schema['enum']} 内")

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: 长度 {len(value)} 小于 minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: 长度 {len(value)} 大于 maxLength {schema['maxLength']}")
        if "pattern" in schema:
            try:
                if re.search(schema["pattern"], value) is None:
                    errors.append(f"{path}: 不匹配 pattern {schema['pattern']}")
            except re.error as exc:
                errors.append(f"{path}: pattern 非法（{exc}）")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} 小于 minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} 大于 maximum {schema['maximum']}")

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: 元素数 {len(value)} 小于 minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: 元素数 {len(value)} 大于 maxItems {schema['maxItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                errors.extend(validate(item_schema, item, f"{path}[{i}]"))

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: 缺少必填字段 {key}")
        properties = schema.get("properties", {})
        for key, sub in value.items():
            if key in properties:
                errors.extend(validate(properties[key], sub, f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: 出现未定义字段 {key}")
    return errors


def load_tool_schemas(schema_path: Path = SCHEMA_PATH) -> dict[str, dict[str, Any]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return {tool["name"]: tool["parameters"] for tool in schema["tools"]}


# ---------------------------------------------------------------- 时间等价


_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(d|h|m|s)", re.I)
_DURATION_UNIT = {"d": 86400.0, "h": 3600.0, "m": 60.0, "s": 1.0}


def parse_duration(text: str) -> float | None:
    """解析相对时间（如 `24h` / `7d` / `90m` / `1h30m`）为秒数；不可解析返回 None。"""
    if not isinstance(text, str):
        return None
    matches = _DURATION_RE.findall(text)
    if not matches:
        return None
    total = 0.0
    for amount, unit in matches:
        total += float(amount) * _DURATION_UNIT[unit.lower()]
    return total


def parse_iso(text: str) -> float | None:
    """解析 ISO 8601 时间为 epoch 秒；不可解析返回 None。"""
    if not isinstance(text, str):
        return None
    cleaned = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def time_range_equivalent(a: Any, b: Any, tolerance: float = TIME_TOLERANCE) -> bool:
    """判断两个 `time_range` 是否语义等价（±tolerance）。

    规则（判分口径，须与 reports/v1-report.md §3.3 一致）：
      - 两侧都可解析为「窗口长度」时，长度差 ≤ tolerance 即等价
        （如 `{"start": "24h"}` 与 `{"start": "24 小时"}` / `{"start": "1d"}`）；
      - 两侧都是绝对时间时，除窗口长度外还比较起点，起点差 ≤ tolerance × 窗口长度。
    D3（v2 2026-09-30）：绝对时间即时区等价——`parse_iso` 已把任意时区（含 `+08:00`/`Z`/省时区）
    统一归一到 epoch（UTC）再比对，故 `2026-09-16T00:00:00+08:00` 与同刻 `Z`/省时区表示等价，
    仅当**时刻不同**才判「参数值错」；本函数无需再改逻辑。
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False

    def window(spec: dict[str, Any]) -> tuple[float, float] | None:
        """返回 (窗口长度秒, 起点 epoch 秒)；起点缺失时以 0 占位。"""
        start_raw, end_raw = spec.get("start"), spec.get("end")
        start_s = parse_duration(start_raw) if isinstance(start_raw, str) else None
        start_abs = parse_iso(start_raw) if isinstance(start_raw, str) else None
        end_abs = parse_iso(end_raw) if isinstance(end_raw, str) else None

        if start_abs is not None:
            if end_abs is None:
                return None                      # 绝对起点但无终点：无法判定窗口，交回精确比对
            return (end_abs - start_abs, start_abs)
        if start_s is not None:
            return (start_s, 0.0)
        return None

    wa, wb = window(a), window(b)
    if wa is None or wb is None:
        return False
    len_a, start_a = wa
    len_b, start_b = wb
    if len_a <= 0 or len_b <= 0:
        return False
    if abs(len_a - len_b) / max(len_a, len_b) > tolerance:
        return False
    if start_a and start_b:
        if abs(start_a - start_b) > tolerance * max(len_a, len_b):
            return False
    return True


# ---------------------------------------------------------------- 参数比对


def duration_equivalent(a: Any, b: Any, tolerance: float = TIME_TOLERANCE) -> bool:
    """D1 `window`/时长量纲归一等价：把相对时长（`15m`/`15min`/`900s`/`1h`/`60min`…）秒化后比对。

    规则（v2 2026-09-30 复审 §三.2）：仅当**两侧均可解析为秒数**、且秒数差在容限内时判等价
    （同量纲数值相等必然落在此区间）；任一不可解析（如裸数字 `"15"`）返回 False，交回精确比对
    （仍可能判「参数值错」）。
    """
    if not isinstance(a, str) or not isinstance(b, str):
        return a == b
    sa, sb = parse_duration(a), parse_duration(b)
    if sa is None or sb is None:
        return False
    if sa <= 0 or sb <= 0:
        return False
    return abs(sa - sb) <= tolerance * max(sa, sb)


def _aggregation_over_limit_equivalent(a: Any, b: Any) -> bool:
    """D2 `aggregation` 超限类别名等价：当两侧都属于超限类别名表时视为等价。

    仅当期望值、实测值均为超限类语义（`count_over_limit`/`count`/`over_limit`/`exceed_count`）
    才判等价；非超限聚合（avg/max/min/trend/raw）保持精确匹配，不做别名映射（中性归一化，
    见复审风险 R-1）。
    """
    return a in OVER_LIMIT_ALIAS and b in OVER_LIMIT_ALIAS


def _aggregation_canonical(value: Any) -> Any:
    """把 `aggregation` 超限类别名归一为服务端 canonical `count_over_limit`（保持中性）。

    仅当值本身属于超限类别名表时替换；非超限聚合（avg/max/min/trend/raw）原样返回。
    """
    if value in OVER_LIMIT_ALIAS:
        return "count_over_limit"
    return value


def _window_canonical(value: Any) -> Any:
    """把 `window` 量纲等价变体归一为标准枚举成员（保持中性）。

    仅当值可量纲等价于某个标准枚举（`1m`/`5m`/`15m`/`1h`/`1d`）时替换；不可解析或
    与任何标准枚举不等价时原样返回（仍可能被 Schema 校验判非法）。
    """
    if not isinstance(value, str):
        return value
    for candidate in ("1m", "5m", "15m", "1h", "1d"):
        if duration_equivalent(value, candidate):
            return candidate
    return value


def _is_superset(actual: list[Any], expected: list[Any]) -> bool:
    """数组参数比对口径（维度2 · 超集可接受）：actual 覆盖 expected 全部项即可，
    多给项、重复、顺序均不限；元素不可哈希（如对象）时回退精确相等。"""
    try:
        return set(expected).issubset(set(actual))
    except TypeError:
        return actual == expected


def _char_bigrams(text: str) -> set[str]:
    """中文文本 2-gram 化，用于无外部分词依赖的关键词包含判定。"""
    cleaned = re.sub(r"[\s，。、；：！？""''（）【】《》,.;:!?()|-]+", "", text)
    if not cleaned:
        return set()
    if len(cleaned) < 2:
        return {cleaned}
    return {cleaned[i:i + 2] for i in range(len(cleaned) - 1)}


# F4（复审 v3）：`search_knowledge.query` 的**封闭域概念**词表 —— 中文检索串措辞差异大，
# 仅靠 bigram 交叠会把同义改写误杀（如"振动速度有效值 分区边界 报警值 停机值" vs
# "离心泵振动标准限值 mm/s 振动烈度 报警值 危险值"）。把同义说法归并到规范概念，
# 当期望串概念集合被实际串完全覆盖时判为语义近似。
_QUERY_CONCEPTS: dict[str, tuple[str, ...]] = {
    "振动": ("振动", "烈度", "有效值", "vib"),
    "限值": ("报警", "停机", "危险", "分区", "边界", "限值", "阈值", "门限"),
    "温度": ("温度", "温升"),
    "流量": ("流量",),
    "手册": ("手册", "规程", "说明书"),
    "轴承": ("轴承", "滚子", "圆柱滚子", "nu210", "nu "),
    "对中": ("对中", "找正"),
    "图谱": ("图谱", "拓扑", "影响链路", "连接关系"),
}


def _query_concepts(text: str) -> set[str]:
    """把查询串映射为规范概念集合（子串命中即视为该概念出现）。"""
    low = text.lower()
    return {concept for concept, variants in _QUERY_CONCEPTS.items()
            if any(v in low for v in variants)}


def _query_semantic_match(exp: Any, act: Any) -> bool:
    """`search_knowledge.query` 语义匹配：精确 / 子串 / 关键词(bigram) 交叠 / 域概念覆盖。

    检索查询串是自由语义文本，模型措辞可不同，故以「语义包含或关键词交叠」为准，
    不做逐字精确匹配。
      · bigram 交叠率 ≥50%（相对较短一侧）视为语义近似；
      · F4（复审 v3）：期望串的**域概念集合**被实际串完全覆盖时，亦判为语义近似
        （仅覆盖闭集域概念，不放宽到无约束字符串）。
    """
    if not isinstance(exp, str) or not isinstance(act, str):
        return exp == act
    e, a = exp.strip(), act.strip()
    if not e or not a:
        return e == a
    if e == a or e in a or a in e:
        return True
    eb, ab = _char_bigrams(e), _char_bigrams(a)
    if eb and ab and len(eb & ab) / min(len(eb), len(ab)) >= 0.5:
        return True
    ec = _query_concepts(e)
    return bool(ec) and ec.issubset(_query_concepts(a))


def _free_text_ok(exp: Any, act: Any) -> bool:
    """`generate_report.diagnosis_summary` 宽松判定：诊断结论为自由长文本，无法逐字比对；
    模型产出非空结论文本即视为有效（长度下限已由 Schema minLength 保证）。"""
    if not isinstance(exp, str) or not isinstance(act, str):
        return exp == act
    return bool(act.strip())


def _types_of(refs: Any) -> list[str]:
    """提取 evidence_refs 中各条目的 type 字段。"""
    if not isinstance(refs, list):
        return []
    return [r.get("type") for r in refs if isinstance(r, dict) and r.get("type")]


def _refs_type_ok(exp: Any, act: Any) -> bool:
    """`generate_report.evidence_refs` 判定：**对齐 schema 规格「必须至少一条」**。

    F6（复审 v3）：原判据要求覆盖 `expected` 列出的**全部**证据类型，严于
    `schemas/tools_*.json` 的描述（"必须至少一条"）与用例 notes（"至少 1 条"）。
    现改为：`actual` 非空，且每条 `type` 均属允许枚举 `_REF_TYPES`。
    类型**覆盖度**降为诊断项（不再作为判错依据；如需可从 raw 另行统计）。
    """
    if not isinstance(exp, list) or not isinstance(act, list):
        return exp == act
    if not act:
        return False
    return all(isinstance(r, dict) and r.get("type") in _REF_TYPES for r in act)


def compare_arguments(tool_name: str, tool_schema: dict[str, Any] | None,
                      expected: dict[str, Any],
                      actual: dict[str, Any],
                      lenient_defaults: dict[str, list] | None = None) -> tuple[bool, list[str]]:
    """比对期望参数与实测参数，返回 (是否全对, 问题列表)。

    判分口径（2026-09-24 裁决）：
      维度1「语义口径」：仅 schema `required` 键缺失判「参数缺失」；`expected` 列出的
        可选键若实际缺失，视为采用默认值，不判错；已存在才比对值。
      维度2「超集可接受」：数组参数要求 actual 覆盖 expected 全部项（多给项可接受）；
        标量仍精确匹配。`time_range` 走 ±10% 语义等价。
      维度3「合理缺省/默认值豁免（2026-09-28 用例复审引入）」：`lenient_defaults` 为
        用例级声明的 `{参数名: [可接受值]}`。若某参数**显式**给出其中某个值，视为与本例
        期望一致的合理答案（等价"该参数采用默认值"）直接判对。仅对**明确在用例 notes 中
        声明"缺省/默认值可接受"的参数打这个标记，避免误伤必须严格锁定的用例（如 v1-011
        window 严格锁定 15m）。缺省为 None 时行为与旧口径完全一致。
        F5（复审 v3）：该字段同时承载「用例多解」语义——当用例意图对应多个同样合理的
        取值时，把其余合理解列入可接受值（如 v1-018 的 aggregation 允许 max /
        count_over_limit）；同样须在用例 notes 中留痕。
    """  # noqa: D205
    issues: list[str] = []
    required_keys = set((tool_schema or {}).get("required", []))
    for key, exp_value in expected.items():
        if (tool_name, key) in FORMAT_ONLY_PARAMS:
            continue                             # 只校验格式，已由 Schema 校验覆盖
        # D5（v2 2026-09-30 复审 §三.5）：generate_report 判分收敛为意图 + 3 项必填，
        # severity/format/recommended_actions/idempotency_key 不参与正确性比对。
        if tool_name == "generate_report" and key not in REPORT_VERDICT_KEYS:
            continue
        if key not in actual:
            if key in required_keys:
                issues.append(f"参数缺失：{key}")
            continue                             # 可选参数缺省 = 采用默认值，不判错
        act_value = actual[key]
        if key == "time_range":
            if not time_range_equivalent(exp_value, act_value):
                issues.append(f"参数值错：time_range 期望 {exp_value}，实际 {act_value}")
            continue
        # 自由长文本宽松（2026-09-24 第二轮修订）：不走精确匹配
        if (tool_name, key) == ("search_knowledge", "query"):
            if not _query_semantic_match(exp_value, act_value):
                issues.append(f"参数值错：query 期望近似 {exp_value!r}，实际 {act_value!r}")
            continue
        if (tool_name, key) == ("generate_report", "diagnosis_summary"):
            if not _free_text_ok(exp_value, act_value):
                issues.append(f"参数值错：diagnosis_summary 应为非空文本，实际 {act_value!r}")
            continue
        if (tool_name, key) == ("generate_report", "evidence_refs"):
            if not _refs_type_ok(exp_value, act_value):
                issues.append(
                    f"参数值错：evidence_refs 应为非空且 type ∈ {sorted(_REF_TYPES)}"
                    f"，实际 {_types_of(act_value)}")
            continue
        # 用例级「合理缺省/默认值豁免」（2026-09-28）：显式给出声明的可接受默认值 → 判对
        if lenient_defaults and key in lenient_defaults:
            if act_value in lenient_defaults[key]:
                continue
        # D1（v2 2026-09-30 复审 §三.2）：window 量纲归一等价（15m=15min=900s）
        if key == "window":
            if duration_equivalent(exp_value, act_value):
                continue
            issues.append(f"参数值错：window 期望 {exp_value!r}，实际 {act_value!r}")
            continue
        # D2（v2 2026-09-30 复审 §三.3）：aggregation 超限类别名等价（count_over_limit=count 等）
        if key == "aggregation" and _aggregation_over_limit_equivalent(exp_value, act_value):
            continue
        if isinstance(exp_value, list) and isinstance(act_value, list):
            if not _is_superset(act_value, exp_value):
                issues.append(f"参数值错：{key} 期望覆盖 {exp_value}，实际 {act_value}")
            continue
        if exp_value != act_value:
            issues.append(f"参数值错：{key} 期望 {exp_value!r}，实际 {act_value!r}")
    return (not issues), issues


def match_expected_calls(expected_calls: list[dict[str, Any]],
                         actual_calls: list[dict[str, Any]],
                         schemas: dict[str, dict[str, Any]],
                         lenient_defaults: dict[str, list] | None = None) -> tuple[bool, list[str]]:
    """把期望调用逐条与实际调用按工具名配对并比对参数（顺序不限）。"""
    issues: list[str] = []
    remaining = list(actual_calls)
    for exp in expected_calls:
        name = exp["name"]
        hit_index = next((i for i, a in enumerate(remaining) if a.get("name") == name), None)
        if hit_index is None:
            issues.append(f"工具缺失：未调用 {name}")
            continue
        actual = remaining.pop(hit_index)
        if actual.get("arguments") is None:
            issues.append(f"JSON 不可解析：{name} 的 arguments 无法解析")
            continue
        ok, sub_issues = compare_arguments(
            name, schemas.get(name), exp.get("arguments", {}), actual["arguments"],
            lenient_defaults
        )
        if not ok:
            issues.extend(sub_issues)
    return (not issues), issues


def judge_step_chain(expected_steps: list[dict[str, Any]],
                     actual_steps: list[dict[str, Any]],
                     schemas: dict[str, dict[str, Any]],
                     lenient_defaults: dict[str, list] | None = None
                     ) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """D4（P6 拆步）：按**有序步骤链**判定「拆单工具多次调用」。

    与 `match_expected_calls`（单响应内、顺序不限）的区别：
      - **保序**：第 i 个期望步骤只与第 i 个实际步骤比对，不跨步配对；
      - **每步只允许一个工具**：取该步的首个调用参与比对，多余调用记为「步骤不经济」
        （提示信息，不判失败——只针对工具名 + 必填参数齐全，不放宽判据）。

    `actual_steps` 形态：`[{"tool_calls": [{"name":..., "arguments":...}, ...]}, ...]`
    （`run_v1.run_step_chain_group` 逐步落盘）。
    返回 (是否全通过, 失败问题列表, 每步明细)。
    """
    issues: list[str] = []
    step_results: list[dict[str, Any]] = []
    for i, exp in enumerate(expected_steps):
        name = exp["name"]
        step_actual = actual_steps[i] if i < len(actual_steps) else None
        calls = (step_actual or {}).get("tool_calls") or []
        if not calls:
            issues.append(f"步骤链缺第 {i + 1} 步：未调用 {name}")
            step_results.append({"step": i + 1, "expected": name, "actual": None,
                                 "ok": False, "note": "缺步"})
            continue
        first = calls[0]
        actual_name = first.get("name")
        step_issues: list[str] = []
        if actual_name != name:
            step_issues.append(f"步骤 {i + 1} 工具名错：期望 {name}，实际 {actual_name}")
        if first.get("arguments") is None:
            step_issues.append(f"步骤 {i + 1} JSON 不可解析：{name} 的 arguments 无法解析")
        else:
            ok_args, sub = compare_arguments(
                name, schemas.get(name), exp.get("arguments", {}),
                first["arguments"], lenient_defaults)
            if not ok_args:
                step_issues.extend(f"步骤 {i + 1} {s}" for s in sub)
        note = ""
        if len(calls) > 1:
            note = f"该步产出 {len(calls)} 个调用，已取首个（步骤不经济）"
        issues.extend(step_issues)
        step_results.append({"step": i + 1, "expected": name, "actual": actual_name,
                             "ok": not step_issues, "note": note})
    return (not issues), issues, step_results


def judge_record(record: dict[str, Any],
                 schemas: dict[str, dict[str, Any]],
                 normalize: bool = False) -> dict[str, Any]:
    """对一条原始结果判分，返回该条的判定明细。

    normalize=True 时，在**参数比对**前对 actual 参数应用 `param_normalizer` 白名单
    归一化（`--normalize`）。`schema_valid` 与 `first_tool_match` 仍基于**原始**调用计算
    ——格式门槛不被归一化放宽；归一化只作用于 `compare_arguments` 环节，用于量化
    「参数归一化纠错」对结果的真实影响（不改动 experiments/**/raw）。
    """
    case = record["expected"]
    result = record["result"]
    expected_calls = case.get("expected_tool_calls", [])
    expect_reject = bool(case.get("expect_reject"))
    # D4（P6 拆步）：execution_mode=step_chain 时，实际调用来自逐步落盘的 result["steps"]；
    # 展平后仍走同一套 schema_valid 门槛（所有步的调用一并校验）。
    execution_mode = case.get("execution_mode") or "single"
    actual_steps = result.get("steps") or []
    if execution_mode == "step_chain":
        actual_calls = [c for s in actual_steps for c in (s.get("tool_calls") or [])]
    else:
        actual_calls = result.get("tool_calls") or []
    # 应拒绝用例（expect_reject）下，模型正确不产生工具调用（tool_calls_missing=True）是
    # **期望行为**，不视为退化；仅真实请求错误（error）计入退化。
    degraded = result.get("error") is not None or (
        bool(result.get("tool_calls_missing")) and not expect_reject
    )

    first_tool_match = bool(actual_calls) and bool(expected_calls) \
        and actual_calls[0].get("name") == expected_calls[0]["name"]

    # 指标 2：剥离 think 后参数能否通过 JSON Schema 校验
    # 口径：只有「确实产出了工具调用」的条目才算可解析；一条调用都没产出 = 不可解析。
    #       应拒绝用例（expect_reject）本就无参数可校验，由 aggregate 从本指标分母剔除。
    schema_errors: list[str] = []
    for call in actual_calls:
        tool_schema = schemas.get(call.get("name"))
        if tool_schema is None:
            schema_errors.append(f"未知工具 {call.get('name')}")
            continue
        if call.get("arguments") is None:
            schema_errors.append(f"{call.get('name')}: arguments 无法解析为 JSON 对象")
            continue
        # v2（2026-09-30 复审）：schema 校验门槛对 query_sensor 的 window/aggregation 应用
        # 量纲/别名归一（判分逻辑归一，不改 schema 枚举值域），使 D1/D2 变体不因指标2被拦。
        args = call["arguments"]
        if call.get("name") == "query_sensor" and isinstance(args, dict):
            args = dict(args)
            if isinstance(args.get("window"), str):
                args["window"] = _window_canonical(args["window"])
            if isinstance(args.get("aggregation"), str):
                args["aggregation"] = _aggregation_canonical(args["aggregation"])
        schema_errors.extend(
            validate(tool_schema, args, f"$.{call.get('name')}")
        )
    schema_valid = bool(actual_calls) and not schema_errors

    # 拒绝方向的双向判定（指标 4，两个方向分开报）
    should_reject_but_called = expect_reject and bool(actual_calls)
    should_call_but_rejected = (not expect_reject) and not actual_calls

    # 参数比对用 actual：归一化时先对参数应用白名单层，再进入比对业务。
    # schema_valid / first_tool_match 不受影响（见函数 docstring）。
    if normalize:
        cmp_calls = [
            {"name": c.get("name"),
             "arguments": param_normalizer.normalize_arguments(
                 c.get("name"),
                 schemas.get(c.get("name")),
                 c.get("arguments") if isinstance(c.get("arguments"), dict) else None)}
            for c in actual_calls
        ]
    else:
        cmp_calls = actual_calls

    if execution_mode == "step_chain":
        cmp_steps = actual_steps
        if normalize:
            cmp_steps = [
                {"tool_calls": [
                    {"name": c.get("name"),
                     "arguments": param_normalizer.normalize_arguments(
                         c.get("name"), schemas.get(c.get("name")),
                         c.get("arguments") if isinstance(c.get("arguments"), dict) else None)}
                    for c in (s.get("tool_calls") or [])
                ]}
                for s in actual_steps
            ]
        calls_ok, call_issues, step_results = judge_step_chain(
            expected_calls, cmp_steps, schemas, case.get("lenient_param_defaults") or {}
        )
    else:
        step_results = []
        calls_ok, call_issues = match_expected_calls(
            expected_calls, cmp_calls, schemas, case.get("lenient_param_defaults") or {}
        )
    tool_set_match = Counter(c["name"] for c in expected_calls) == \
        Counter(c["name"] for c in actual_calls)

    if expect_reject:
        success = not actual_calls and not degraded
    else:
        success = bool(actual_calls) and calls_ok and not degraded and schema_valid

    # 失败归类（互斥，按优先级取首个）
    failure: str | None = None
    if not success:
        if degraded and not actual_calls:
            failure = FAIL_DEGRADED
        elif should_reject_but_called:
            failure = FAIL_SHOULD_REJECT
        elif should_call_but_rejected:
            failure = FAIL_SHOULD_CALL
        elif any(c.get("arguments") is None for c in actual_calls):
            failure = FAIL_JSON
        elif execution_mode == "step_chain":
            failure = FAIL_STEP_CHAIN
        elif not first_tool_match:
            failure = FAIL_TOOL_NAME
        elif any("参数缺失" in i for i in call_issues):
            failure = FAIL_MISSING_PARAM
        else:
            failure = FAIL_PARAM_VALUE

    return {
        "case_id": case.get("case_id"),
        "case_type": case.get("type"),
        "difficulty": case.get("difficulty"),
        "expect_reject": expect_reject,
        "execution_mode": execution_mode,
        "steps_total": len(expected_calls) if execution_mode == "step_chain" else None,
        "steps_passed": (sum(1 for s in step_results if s["ok"])
                         if execution_mode == "step_chain" else None),
        "first_missing_step": next((s["step"] for s in step_results if not s["ok"]), None)
        if execution_mode == "step_chain" else None,
        "step_chain": ("; ".join(
            f"{s['step']}:{'OK' if s['ok'] else 'FAIL'}={s['actual']}"
            + (f"({s['note']})" if s["note"] else "") for s in step_results)
            if execution_mode == "step_chain" else ""),
        "model": record.get("model"),
        "attempt": record.get("attempt"),
        "repeat": record.get("repeat"),
        "tag": record.get("tag", "main"),
        "cold_start": record.get("cold_start"),
        "first_tool_match": first_tool_match,
        "tool_set_match": tool_set_match,
        "schema_valid": bool(schema_valid),
        "schema_errors": "; ".join(schema_errors),
        "calls_ok": calls_ok,
        "call_issues": "; ".join(call_issues),
        "should_reject_but_called": should_reject_but_called,
        "should_call_but_rejected": should_call_but_rejected,
        "degraded": degraded,
        "success": success,
        "failure": failure,
        "latency_ms": result.get("latency_ms") or 0.0,
        "completion_tokens": result.get("completion_tokens"),
        "think_tokens": result.get("think_tokens"),
        "token_source": result.get("token_source"),
    }


# ---------------------------------------------------------------- 汇总指标


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[idx]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate(judged: list[dict[str, Any]]) -> dict[str, Any]:
    """按模型汇总 8 项指标（首次与重试后分行报）。"""
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in judged:
        by_model[row["model"]].append(row)

    summary: dict[str, Any] = {}
    for model, rows in by_model.items():
        first_attempt = [r for r in rows if r["attempt"] == 1]
        cases_total = len({r["case_id"] for r in rows})

        # 每个 case_id 的「首次是否成功」与「≤3 次内是否成功」
        first_by_case: dict[str, bool] = {}
        retry_by_case: dict[str, bool] = {}
        for r in rows:
            cid = r["case_id"]
            if r["attempt"] == 1:
                first_by_case[cid] = r["success"]
            if r["success"] and r["attempt"] <= MAX_RETRY:
                retry_by_case[cid] = True
        for cid in {r["case_id"] for r in rows}:
            retry_by_case.setdefault(cid, False)

        def ratio(numerator: int, denominator: int) -> float | None:
            return (numerator / denominator) if denominator else None

        cold = [r["latency_ms"] for r in first_attempt if r["cold_start"]]
        warm = [r["latency_ms"] for r in first_attempt if not r["cold_start"]]
        think_tokens = [r["think_tokens"] for r in first_attempt if r["think_tokens"]]
        out_tokens = [r["completion_tokens"] for r in first_attempt if r["completion_tokens"]]
        char_fallback = any(r["token_source"] == "char_fallback" for r in first_attempt)

        summary[model] = {
            "用例数": cases_total,
            "总调用次数": len(rows),
            "1_工具选择准确率": ratio(sum(r["first_tool_match"] for r in first_attempt),
                                      len(first_attempt)),
            "1b_多工具集合覆盖": ratio(
                sum(r["tool_set_match"] for r in first_attempt if r["case_type"] == "多工具"),
                sum(1 for r in first_attempt if r["case_type"] == "多工具")),
            # D4（P6 拆步）：步骤链口径的「步级完整率」= 通过的步数 / 期望总步数。
            # 单响应模式（steps_total=None）下分母为 0 → None，不影响既有指标。
            "1c_多工具步骤链完整率": ratio(
                sum(r.get("steps_passed") or 0 for r in first_attempt
                    if r["case_type"] == "多工具"),
                sum(r.get("steps_total") or 0 for r in first_attempt
                    if r["case_type"] == "多工具")),
            "2_参数JSON可解析率": ratio(sum(r["schema_valid"] for r in first_attempt
                                            if not r["expect_reject"]),
                                        sum(1 for r in first_attempt if not r["expect_reject"])),
            "3_参数值正确率": ratio(sum(r["calls_ok"] for r in first_attempt
                                        if not r["expect_reject"]),
                                    sum(1 for r in first_attempt if not r["expect_reject"])),
            "4a_应拒绝却调用": sum(r["should_reject_but_called"] for r in rows),
            "4b_应调用却拒绝": sum(r["should_call_but_rejected"] for r in rows),
            "5_首次成功率": ratio(sum(first_by_case.values()), len(first_by_case)),
            "6_重试后成功率": ratio(sum(retry_by_case.values()), len(retry_by_case)),
            "7_平均延迟_冷_ms": _mean(cold),
            "7_P95延迟_冷_ms": _p95(cold),
            "7_平均延迟_热_ms": _mean(warm),
            "7_P95延迟_热_ms": _p95(warm),
            "7_输出token均值": _mean([float(t) for t in out_tokens]),
            "7_think_token均值": _mean([float(t) for t in think_tokens]),
            "8_输出冗长度_think占比": (
                _mean([float(t) for t in think_tokens]) /
                _mean([float(t) for t in out_tokens])
                if think_tokens and out_tokens and _mean([float(t) for t in out_tokens])
                else None
            ),
            "think_token口径": "字符近似（provider 未回传 reasoning_tokens）"
            if char_fallback else "usage",
            "失败归类": dict(Counter(r["failure"] for r in rows if r["failure"])),
            "分层_类型": _by_dimension(first_attempt, "case_type"),
            "分层_难度": _by_dimension(first_attempt, "difficulty"),
        }
    return summary


def _by_dimension(rows: list[dict[str, Any]], key: str) -> dict[str, float | None]:
    buckets: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        buckets[r[key]].append(r["success"])
    return {k: (sum(v) / len(v)) for k, v in sorted(buckets.items())}


def judge_verdict(first_success: float | None, parseable: float | None) -> str:
    """按判据给出 Pass / 中间区间 / No-Go（适用对象 = 首次成功率）。

    单线判据（遗留）：`docs/gate-criteria.md` §3.1 保留为整体下界口径，
    分档判定见 `judge_verdict_tiered`（2026-09-28 重校后为权威口径）。
    """
    if first_success is None:
        return "无数据"
    if first_success >= PASS_FIRST_SUCCESS and (parseable or 0) >= PASS_PARSEABLE:
        return "Pass"
    if first_success >= MID_LOWER:
        return "中间区间（70–90%）：须执行约束解码 + few-shot 并记录代价"
    return "No-Go（<70%）：云端工具调用转正"


# ---------------------------------------------------------------- 判据按类型分档（2026-09-28 重校）
# 依据：`docs/gate-criteria.md` §3.1 修订版 + EXP-V1-003 分层实测 + 云端 baseline 实测。
# 口径（分层定位，见 gate-criteria §3.1 与 v1-report §7.3）：
#   - 本地可达成类型（单工具/参数校验/多轮/无效拒绝）沿用高线：本地启动值
#     单工具 0.33–0.39、参数校验 0.50–0.67、多轮 0.22–0.67、无效拒绝 0.33–0.78，
#     经「约束解码 + few-shot」有上扬空间，pass 线沿用原全局 0.85；
#   - 多工具为 7B 结构性硬限（EXP-V1-003 双模型集合覆盖 0.00），单独设低线：
#     低于线下线即触发「架构切分」（交云端或拆单工具多轮），而非整线云端转正。
# 云端 baseline 实测（仅供参考，不作本地判据）：
#   - EXP-V1-002 无约束裸跑：整体首次成功率 0.60；
#   - EXP-V1-005 约束解码：整体首次成功率 0.55、参数可解析率 0.88
#     （约束解码对云端反而降分，见 reports/v1-report.md §7.3）。
TIER_CRITERIA: dict[str, dict[str, float]] = {
    "单工具":   {"pass": 0.85, "mid": 0.70},
    "参数校验": {"pass": 0.85, "mid": 0.70},
    "多轮":     {"pass": 0.85, "mid": 0.70},
    "无效拒绝": {"pass": 0.90, "mid": 0.70},
    "多工具":   {"pass": 0.70, "mid": 0.50},
}
# 各类型 Non-Go 的处置动作（未列出的类型 → 默认「云端工具调用转正」）
TIER_DISPOSITION: dict[str, str] = {
    "多工具": "架构切分（交云端或拆单工具多轮）",
}


def _tier_verdict(rate: float | None, pass_line: float, mid_lower: float) -> str:
    """单类型的分档判定。rate 为 None（该类型无用例）→ 无数据，不参与整体合成。"""
    if rate is None:
        return "无数据"
    if rate >= pass_line:
        return "Pass"
    if rate >= mid_lower:
        return f"中间区间（{mid_lower*100:.0f}–{pass_line*100:.0f}%）：须处置并记录代价"
    return f"No-Go（<{mid_lower*100:.0f}%）"


def judge_verdict_tiered(success_by_type: dict[str, float | None]) -> dict[str, str]:
    """按类型分档判定（2026-09-28 重校的权威判据入口）。

    返回 {各类型档位..., "整体": 裁决}。整体 = 有数据类型的**最差档位**，
    保证 M0.6 门禁仍可判：
      - 任一类型触 No-Go → 整体 No-Go（多工具 No-Go 附「架构切分」处置，见 TIER_DISPOSITION）
      - 否则恰有一类型落中间区间 → 整体中间区间
      - 否则全部过闸 → 整体 Pass
    """
    verdicts: dict[str, str] = {}
    for ctype, lines in TIER_CRITERIA.items():
        verdicts[ctype] = _tier_verdict(
            success_by_type.get(ctype), lines["pass"], lines["mid"])
    order: list[tuple[int, str, str]] = []
    for ctype, verdict in verdicts.items():
        if success_by_type.get(ctype) is None:
            continue
        tag = verdict.split("（")[0]
        order.append(({"Pass": 0, "中间区间": 1, "No-Go": 2}.get(tag, 1), ctype, verdict))
    if not order:
        verdicts["整体"] = "无数据"
        return verdicts
    _rank, worst_type, worst_verdict = max(order, key=lambda x: x[0])
    if worst_verdict.startswith("No-Go"):
        disposition = TIER_DISPOSITION.get(worst_type, "云端工具调用转正")
        verdicts["整体"] = f"No-Go：{worst_type} {worst_verdict} → {disposition}"
    elif worst_verdict.startswith("中间区间"):
        verdicts["整体"] = f"中间区间：{worst_type} {worst_verdict}"
    else:
        verdicts["整体"] = "Pass（全部类型过闸）"
    return verdicts


# ---------------------------------------------------------------- 落盘


def write_summary_csv(summary: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    metric_names: list[str] = []
    for model_summary in summary.values():
        for key in model_summary:
            if key not in metric_names and not key.startswith("分层_"):
                metric_names.append(key)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["指标"] + list(summary.keys()))
        for name in metric_names:
            writer.writerow([name] + [_csv_cell(summary[m].get(name)) for m in summary])
    print(f"[judge] 汇总表已写入 {out_path}")


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def print_summary(summary: dict[str, Any]) -> None:
    for model, metrics in summary.items():
        print("\n" + "=" * 72)
        print(f"模型：{model}（用例 {metrics['用例数']} 条，调用 {metrics['总调用次数']} 次）")
        print("=" * 72)
        for key, value in metrics.items():
            if key.startswith("分层_"):
                continue
            print(f"  {key}: {_csv_cell(value)}")
        tiered = judge_verdict_tiered(metrics["分层_类型"])
        print(f"  → 判据判定（整体，2026-09-28 分档重校）：{tiered['整体']}")
        for ctype in TIER_CRITERIA:
            rate = metrics["分层_类型"].get(ctype)
            print(f"      {ctype}：{tiered[ctype]}（{rate if rate is None else f'{rate:.0%}'}）")
        for dim_key in ("分层_难度",):
            print(f"  {dim_key}: " + ", ".join(
                f"{k}={v:.0%}" if isinstance(v, float) else f"{k}={v}"
                for k, v in metrics[dim_key].items()))


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    failures: list[str] = []
    schemas = load_tool_schemas()

    # 1) Schema 校验：必填缺失 / 枚举错 / 正则错 / 额外字段
    if not validate(schemas["query_sensor"], {"device_id": "PUMP-A-01"}, "$"):
        failures.append("缺少 time_range 必填字段未被识别")
    if not validate(schemas["query_sensor"],
                    {"device_id": "PUMP-A-01", "time_range": {"start": "24h"},
                     "aggregation": "median"}, "$"):
        failures.append("aggregation 非法枚举未被识别")
    if not validate(schemas["query_sensor"],
                    {"device_id": "pump-a-01", "time_range": {"start": "24h"}}, "$"):
        failures.append("device_id 正则不匹配未被识别")
    if not validate(schemas["query_sensor"],
                    {"device_id": "PUMP-A-01", "time_range": {"start": "24h"}, "foo": 1}, "$"):
        failures.append("additionalProperties=false 未被识别")
    if validate(schemas["query_sensor"],
                {"device_id": "PUMP-A-01", "time_range": {"start": "24h"}}, "$"):
        failures.append("合法参数被误判为非法")
    if validate(schemas["generate_report"],
                {"device_id": "PUMP-A-01", "diagnosis_summary": "轴承磨损，建议停机更换",
                 "evidence_refs": [{"type": "sensor", "ref": "PUMP-A-01.vib_x"}],
                 "idempotency_key": "PUMP-A-01-20260923-001"}, "$"):
        failures.append("合法 generate_report 参数被误判为非法")

    # 2) time_range ±10% 等价
    if not time_range_equivalent({"start": "24h"}, {"start": "1d"}):
        failures.append("24h 与 1d 应等价")
    if not time_range_equivalent({"start": "1h"}, {"start": "60m"}):
        failures.append("1h 与 60m 应等价")
    if time_range_equivalent({"start": "24h"}, {"start": "30h"}):
        failures.append("24h 与 30h 不应等价（差 25%）")
    if not time_range_equivalent(
            {"start": "2026-09-16T00:00:00+08:00", "end": "2026-09-23T00:00:00+08:00"},
            {"start": "2026-09-16T00:30:00+08:00", "end": "2026-09-23T00:30:00+08:00"}):
        failures.append("起点偏移 30min / 窗口 7d 应等价")

    # 3) 判分：成功路径
    case_ok = {"case_id": "v1-001", "type": "单工具", "difficulty": "易",
               "expect_reject": False,
               "expected_tool_calls": [{"name": "query_sensor",
                                        "arguments": {"device_id": "PUMP-A-01",
                                                      "time_range": {"start": "24h"}}}]}
    record_ok = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                 "expected": case_ok,
                 "result": {"tool_calls": [{"name": "query_sensor",
                                            "arguments": {"device_id": "PUMP-A-01",
                                                          "time_range": {"start": "1d"}}}],
                            "tool_calls_missing": False, "latency_ms": 10.0}}
    judged = judge_record(record_ok, schemas)
    if not judged["success"]:
        failures.append(f"成功用例被判失败：{judged['failure']} / {judged['call_issues']}")

    # 4) 判分：应拒绝却调用（不得混入「工具名错」）
    case_reject = {"case_id": "v1-016", "type": "无效拒绝", "difficulty": "中",
                   "expect_reject": True, "expected_tool_calls": []}
    record_bad = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                  "expected": case_reject,
                  "result": {"tool_calls": [{"name": "query_sensor", "arguments": {}}],
                             "tool_calls_missing": False, "latency_ms": 10.0}}
    judged_bad = judge_record(record_bad, schemas)
    if judged_bad["failure"] != FAIL_SHOULD_REJECT:
        failures.append(f"应拒绝却调用归类错误：{judged_bad['failure']}")

    # 5) 判分：静默退化必须单列为「格式退化」
    record_degraded = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                       "expected": case_ok,
                       "result": {"tool_calls": [], "tool_calls_missing": True,
                                  "latency_ms": 10.0}}
    judged_deg = judge_record(record_degraded, schemas)
    if judged_deg["failure"] != FAIL_DEGRADED:
        failures.append(f"静默退化归类错误：{judged_deg['failure']}")

    # 6) idempotency_key 只校验格式、不比对具体值
    _report_args = {"device_id": "PUMP-A-01",
                    "diagnosis_summary": "轴承磨损，建议停机更换轴承",
                    "evidence_refs": [{"type": "sensor", "ref": "PUMP-A-01.vib_x"}]}
    case_report = {"case_id": "v1-019", "type": "多轮", "difficulty": "难",
                   "expect_reject": False,
                   "expected_tool_calls": [{"name": "generate_report",
                                            "arguments": {**_report_args,
                                                          "idempotency_key": "AAA-1111"}}]}
    record_report = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                     "expected": case_report,
                     "result": {"tool_calls": [{"name": "generate_report",
                                                "arguments": {**_report_args,
                                                              "idempotency_key": "ZZZ-9999"}}],
                                "tool_calls_missing": False, "latency_ms": 10.0}}
    if not judge_record(record_report, schemas)["success"]:
        failures.append("idempotency_key 被错误地按值比对")

    # 6a) v2 回归：generate_report 非判决键（severity/format/recommended_actions）不参与正确性比对
    _report_sev_exp = {"device_id": "PUMP-A-01",
                       "diagnosis_summary": "轴承磨损，建议停机更换轴承",
                       "evidence_refs": [{"type": "sensor", "ref": "PUMP-A-01.vib_x"}],
                       "severity": "warning"}
    _report_sev_act = {**_report_sev_exp, "severity": "critical"}
    _case_sev = {"case_id": "v1-019", "type": "多轮", "difficulty": "难",
                 "expect_reject": False,
                 "expected_tool_calls": [{"name": "generate_report",
                                          "arguments": _report_sev_exp}]}
    _rec_sev = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                "expected": _case_sev,
                "result": {"tool_calls": [{"name": "generate_report",
                                           "arguments": _report_sev_act}],
                           "tool_calls_missing": False, "latency_ms": 10.0}}
    if not judge_record(_rec_sev, schemas)["success"]:
        failures.append("generate_report 非判决键（severity 不一致）不应判失败（v2 D5）")

    # 6a2) v2 回归：window 量纲归一等价（15m=15min=900s），裸数字"15"仍判错
    if not duration_equivalent("15m", "15min"):
        failures.append("window 15m 与 15min 应量纲等价")
    if not duration_equivalent("15m", "900s"):
        failures.append("window 15m 与 900s 应量纲等价")
    if not duration_equivalent("1h", "60min"):
        failures.append("window 1h 与 60min 应量纲等价")
    if duration_equivalent("15m", "1h"):
        failures.append("window 15m 与 1h 不应等价")
    if duration_equivalent("15m", "15"):
        failures.append("window 不可解析裸数字应判不等价（交回精确比对）")
    _window_exp = {"device_id": "PUMP-A-01", "time_range": {"start": "7d"},
                   "aggregation": "avg", "window": "15m"}
    _window_act_equiv = {**_window_exp, "window": "900s"}
    _window_act_bad = {**_window_exp, "window": "1h"}
    _case_win = {"case_id": "v1-011", "type": "参数校验", "difficulty": "中",
                 "expect_reject": False,
                 "expected_tool_calls": [{"name": "query_sensor",
                                          "arguments": _window_exp}]}
    for _tag, _act in (("等价", _window_act_equiv), ("不等价", _window_act_bad)):
        _rec_win = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                    "expected": _case_win,
                    "result": {"tool_calls": [{"name": "query_sensor", "arguments": _act}],
                               "tool_calls_missing": False, "latency_ms": 10.0}}
        _j = judge_record(_rec_win, schemas)
        if _tag == "等价" and not _j["success"]:
            failures.append(f"window 量纲等价 {_act['window']} 应判成功：{_j['failure']}/{_j['call_issues']}")
        if _tag == "不等价" and _j["success"]:
            failures.append(f"window 不同量纲 {_act['window']} 不应判成功")

    # 6a3) v2 回归：aggregation 超限类别名等价（count_over_limit=count），avg 不误判等价
    if not _aggregation_over_limit_equivalent("count_over_limit", "count"):
        failures.append("aggregation count_over_limit 与 count 应等价")
    if not _aggregation_over_limit_equivalent("over_limit", "exceed_count"):
        failures.append("aggregation over_limit 与 exceed_count 应等价")
    if _aggregation_over_limit_equivalent("count_over_limit", "avg"):
        failures.append("aggregation count_over_limit 与 avg 不应等价")
    if _aggregation_over_limit_equivalent("max", "count"):
        failures.append("aggregation max 与 count 不应等价（超限别名不得污染非超限聚合）")
    _agg_exp = {"device_id": "PUMP-A-01", "sensor_ids": ["PUMP-A-01.vib_x"],
                "time_range": {"start": "30d"}, "aggregation": "count_over_limit"}
    _agg_act = {**_agg_exp, "aggregation": "count"}
    _case_agg = {"case_id": "v1-012", "type": "参数校验", "difficulty": "中",
                 "expect_reject": False,
                 "expected_tool_calls": [{"name": "query_sensor", "arguments": _agg_exp}]}
    _rec_agg = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                "expected": _case_agg,
                "result": {"tool_calls": [{"name": "query_sensor", "arguments": _agg_act}],
                           "tool_calls_missing": False, "latency_ms": 10.0}}
    if not judge_record(_rec_agg, schemas)["success"]:
        failures.append("aggregation count_over_limit 与 count（超限别名）应判成功（v2 D2）")

    # 6b) 必填参数缺失（evidence_refs）必须判为失败，且归类为「参数缺失」
    record_missing = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                      "expected": case_report,
                      "result": {"tool_calls": [{"name": "generate_report",
                                                 "arguments": {"device_id": "PUMP-A-01",
                                                               "diagnosis_summary": "轴承磨损，建议停机更换轴承",
                                                               "idempotency_key": "ZZZ-9999"}}],
                                 "tool_calls_missing": False, "latency_ms": 10.0}}
    judged_missing = judge_record(record_missing, schemas)
    if judged_missing["success"] or judged_missing["schema_valid"]:
        failures.append("generate_report 缺 evidence_refs 未被判失败")

    # 6c) 应拒绝用例正确拒绝（无 tool_calls + tool_calls_missing=True）→ 成功，不得判退化
    record_reject_ok = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                        "expected": case_reject,
                        "result": {"tool_calls": [], "tool_calls_missing": True,
                                   "latency_ms": 10.0}}
    judged_reject_ok = judge_record(record_reject_ok, schemas)
    if not judged_reject_ok["success"] or judged_reject_ok["degraded"]:
        failures.append("应拒绝用例正确拒绝被误判为退化/失败")

    # 6d) query 语义匹配：子串与 bigram 交叠应判等价；语义无关应判错
    if not _query_semantic_match("轴承振动异常", "泵轴承振动异常的原因"):
        failures.append("query 子串语义应判等价")
    if _query_semantic_match("查询轴承振动", "查询冷却液温度"):
        failures.append("query 语义无关不应判等价")

    # 6e) diagnosis_summary 宽松：非空不同文本判等价；空串判错
    if not _free_text_ok("(较长期望摘要……)", "泵轴承磨损加剧，皮带张紧度不足导致径向冲击，建议优先更换 6205 轴承并重新对中。"):
        failures.append("diagnosis_summary 非空不同文本应判等价")
    if _free_text_ok("(期望)", ""):
        failures.append("diagnosis_summary 空串不应判等价")

    # 6f) evidence_refs 对齐规格（F6 复审 v3）：非空且 type ∈ 枚举即判等价
    #     （类型覆盖度降为诊断项）；空列表 / 非法 type 判错
    ref_exp, ref_act_ok, ref_act_empty, ref_act_badtype = (
        [{"type": "sensor", "ref": "PUMP-A-01.vib_x"},
         {"type": "knowledge", "ref": "chunk-7f3a"}],
        [{"type": "sensor", "ref": "PUMP-A-01.vib_x"},
         {"type": "knowledge", "ref": "chunk-0001"}],
        [],
        [{"type": "unknown_type", "ref": "x"}])
    if not _refs_type_ok(ref_exp, ref_act_ok):
        failures.append("evidence_refs ref 不同但类型合法应判等价")
    if not _refs_type_ok(ref_exp, [{"type": "sensor", "ref": "PUMP-A-01.vib_x"}]):
        failures.append("evidence_refs 覆盖不全但类型合法应判等价（F6）")
    if _refs_type_ok(ref_exp, ref_act_empty):
        failures.append("evidence_refs 空列表应判错")
    if _refs_type_ok(ref_exp, ref_act_badtype):
        failures.append("evidence_refs 非法 type 应判错")

    # 6g) --normalize：time_range 单位别名（24小时 vs 24h）应能被归一化判等价；
    #      --normalize 只放宽比对、不放宽 schema_valid（格式门槛保持不变）
    _case_norm = {"case_id": "v1-norm", "type": "单工具", "difficulty": "易",
                  "expect_reject": False,
                  "expected_tool_calls": [{"name": "query_sensor",
                                           "arguments": {"device_id": "PUMP-A-01",
                                                         "time_range": {"start": "24h"}}}]}
    _rec_norm = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                 "expected": _case_norm,
                 "result": {"tool_calls": [{"name": "query_sensor",
                                            "arguments": {"device_id": "PUMP-A-01",
                                                          "time_range": {"start": "24小时"}}}],
                            "tool_calls_missing": False, "latency_ms": 10.0}}
    _j_raw = judge_record(_rec_norm, schemas)              # 不归一化：24小时≠24h → fail
    _j_norm = judge_record(_rec_norm, schemas, normalize=True)  # 归一化：判等价 → success
    if _j_raw["success"]:
        failures.append("未归一化时 24小时/24h 不应被判等价（否则归一化无意义）")
    if not _j_norm["success"]:
        failures.append(f"归一化后 24小时/24h 应判等价：{_j_norm['failure']}/{_j_norm['call_issues']}")
    if not _j_norm["schema_valid"]:
        failures.append("归一化不得放宽 schema_valid（格式门槛保持原始）")

    # 6h) D4（P6 拆步）：步骤链判定——保序、每步单工具、缺步判链失败
    _sc_exp = [{"name": "query_sensor",
                "arguments": {"device_id": "PUMP-A-01", "time_range": {"start": "3d"},
                              "aggregation": "max"}},
               {"name": "search_knowledge",
                "arguments": {"query": "振动标准 报警值", "category_filter": ["振动标准"]}}]
    _case_sc = {"case_id": "v3-007", "type": "多工具", "difficulty": "中",
                "execution_mode": "step_chain", "expect_reject": False,
                "expected_tool_calls": _sc_exp}
    _steps_full = [
        {"tool_calls": [{"name": "query_sensor",
                         "arguments": {"device_id": "PUMP-A-01", "time_range": {"start": "3d"},
                                       "aggregation": "max"}}]},
        {"tool_calls": [{"name": "search_knowledge",
                         "arguments": {"query": "振动标准 报警值",
                                       "category_filter": ["振动标准"]}}]},
    ]
    _steps_missing = _steps_full[:1]                       # 缺第 2 步
    _steps_wrong_order = list(reversed(_steps_full))        # 顺序颠倒
    _steps_extra = [
        {"tool_calls": [_steps_full[0]["tool_calls"][0],
                        {"name": "get_maintenance_history",
                         "arguments": {"device_id": "PUMP-A-01"}}]},
        _steps_full[1],
    ]
    for _tag, _steps, _expect_ok in (
            ("完整", _steps_full, True),
            ("缺步", _steps_missing, False),
            ("顺序颠倒", _steps_wrong_order, False),
            ("单步多调用", _steps_extra, True),
    ):
        _rec_sc = {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                   "expected": _case_sc,
                   "result": {"steps": _steps, "tool_calls_missing": not _steps,
                              "latency_ms": 10.0}}
        _j_sc = judge_record(_rec_sc, schemas)
        if _j_sc["success"] != _expect_ok:
            failures.append(f"步骤链「{_tag}」判定错误：success={_j_sc['success']}"
                            f"（期望 {_expect_ok}）/ {_j_sc['call_issues']}")
        if not _expect_ok and _j_sc["failure"] != FAIL_STEP_CHAIN:
            failures.append(f"步骤链「{_tag}」失败归类应为 {FAIL_STEP_CHAIN}，"
                            f"实际 {_j_sc['failure']}")
    if judge_record({"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                     "expected": _case_sc,
                     "result": {"steps": _steps_full, "tool_calls_missing": False,
                                "latency_ms": 10.0}}, schemas)["steps_passed"] != 2:
        failures.append("步骤链 steps_passed 统计错误（完整链应为 2）")

    # 7) 判据分档（单线遗留口径）
    if judge_verdict(0.95, 0.96) != "Pass":
        failures.append("判据 Pass 分档错误")
    if not judge_verdict(0.85, 0.96).startswith("中间区间"):
        failures.append("判据中间区间分档错误")
    if not judge_verdict(0.50, 0.96).startswith("No-Go"):
        failures.append("判据 No-Go 分档错误")

    # 7b) 判据按类型分档（2026-09-28 重校）
    _t_all_pass = {"单工具": 0.90, "参数校验": 0.88, "多工具": 0.80,
                   "无效拒绝": 0.95, "多轮": 0.90}
    if not judge_verdict_tiered(_t_all_pass)["整体"].startswith("Pass"):
        failures.append("分档全部过闸应判整体 Pass")
    _t_multitool_ng = {"单工具": 0.90, "参数校验": 0.88, "多工具": 0.20,
                       "无效拒绝": 0.95, "多轮": 0.90}
    _overall = judge_verdict_tiered(_t_multitool_ng)["整体"]
    if not _overall.startswith("No-Go") or "架构切分" not in _overall:
        failures.append("多工具 No-Go 应判整体 No-Go 且附架构切分处置")
    _t_mid = {"单工具": 0.75, "参数校验": 0.88, "多工具": 0.80,
              "无效拒绝": 0.95, "多轮": 0.90}
    if not judge_verdict_tiered(_t_mid)["整体"].startswith("中间区间"):
        failures.append("单工具落中间区间应判整体中间区间")
    _t_single_only = {"单工具": 0.50}      # 只有单工具类型有数据
    if not judge_verdict_tiered(_t_single_only)["整体"].startswith("No-Go"):
        failures.append("单工具类型 No-Go 应判整体 No-Go（云端工具调用转正）")

    if failures:
        print("[FAIL] 判分器自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] 判分器自检通过：Schema 校验 / time_range 等价 / 七类失败归类 / 判据分档 / "
          "宽松口径（query语义、summary非空、evidence_refs类型、应拒绝不退化）/ "
          "步骤链 D4（保序、缺步、单步多调用）")
    return 0


# ---------------------------------------------------------------- 入口


def load_records(raw_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V1 自动判分器（T2.2）")
    parser.add_argument("--raw", type=Path, help="原始结果 JSONL（run_v1.py 的 --out）")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH, help="工具 Schema v1")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "experiments/v1/summary.csv",
                        help="汇总表输出路径")
    parser.add_argument("--detail-out", type=Path, default=None,
                        help="逐条判定明细 CSV（可选）")
    parser.add_argument("--normalize", action="store_true",
                        help="参数比对前应用 param_normalizer 白名单归一化（不改 raw）")
    parser.add_argument("--selftest", action="store_true", help="运行判分器自检（不读数据）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.raw:
        parser.error("需要 --raw 指定原始结果 JSONL（或使用 --selftest）")
    if not args.raw.exists():
        parser.error(f"原始结果不存在：{args.raw}")

    schemas = load_tool_schemas(args.schema)
    judged = [judge_record(r, schemas, normalize=args.normalize)
              for r in load_records(args.raw)]
    summary = aggregate(judged)
    print_summary(summary)
    write_summary_csv(summary, args.out)

    if args.detail_out:
        if not judged:
            print(f"[judge] 原始结果为空，跳过逐条明细写入：{args.raw}")
            return 0
        args.detail_out.parent.mkdir(parents=True, exist_ok=True)
        with args.detail_out.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(judged[0].keys()))
            writer.writeheader()
            writer.writerows(judged)
        print(f"[judge] 逐条明细已写入 {args.detail_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
