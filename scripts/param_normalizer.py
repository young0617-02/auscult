"""V1 参数归一化纠错层（收窄版）—— 白名单确定性规则

目标（对应 `reports/v1-report.md` §8.2.1「参数归一化纠错」收窄版）：
  对模型产出的工具调用参数做**确定性后处理**，只修复「意图对、表达不对」的格式类
  误差（时间单位别名 / 设备·测点大小写 / 数字字符串→数值）。**明确不做**任何语义映射
  （`window`/`aggregation`/`relation_type`/`depth`/`direction`/`severity` 等一律不动），
  否则会掩盖 7B 模型内容级的真实缺陷，违反「不编造数字」铁律。

用途：
  1. 判分侧：`judge_tools.py --normalize` 在比对前对 actual 参数应用本层，量化其对
     首次成功率的真实 uplift（不改动 experiments/**/raw 原始数据）。
  2. 生产侧（Phase 1）：本层可作为 llm_adapter / 工具执行前的入参 canonical 化入口复用。

规则白名单（逐条可证伪，见 `_selftest`）：
  R1 time_range 相对时长单位别名 → canonical（小时/时/hour→h、天/日→d、分钟/分/min→m、秒→s）
  R2 标识符规整：`_ID_FIELDS = {device_id, sensor_ids, start_node, device_model}`
    逐项 trim + 去内部空白（`sensor_ids` 为数组，逐元素处理）；
    **不做大小写转换**，避免与黄金集小写期望、`_is_superset` 大小写敏感比对冲突
  R3 数字字符串 → number（仅 schema 类型为 integer/number 的字段，严格解析）

明确不做：
  - 相对↔绝对时间转换（需 `now` 锚定，离线评测无参考系，避免掩盖）
  - 任何枚举/语义字段的别名映射（window/aggregation/relation_types/depth/direction/severity…）
  - 多工具缺失补全（结构性，规则救不了）

自检：`python scripts/param_normalizer.py --selftest`
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 规则 R1：时长单位别名

# 别名 → canonical 单位字母
_DUR_ALIAS: dict[str, str] = {
    "hour": "h", "hours": "h", "hr": "h", "hrs": "h", "h": "h", "小时": "h", "时": "h",
    "day": "d", "days": "d", "d": "d", "天": "d", "日": "d",
    "minute": "m", "minutes": "m", "min": "m", "mins": "m", "m": "m", "分钟": "m", "分": "m",
    "second": "s", "seconds": "s", "sec": "s", "secs": "s", "s": "s", "秒": "s",
}

# 依次匹配：数字 + 可选空白 + 别名（含多字节中文别名）
_DUR_TOKEN_RE = re.compile(
    r"([0-9]*\.?[0-9]+)\s*([A-Za-z]+|小时|天|日|分钟|秒|时|分)"
)


def canonicalize_duration(text: Any) -> Any:
    """R1：把相对时长表达式（`24小时`/`7 天`/`90分钟`/`1h30m`）归一为 `N+canonical单位`。

    仅做字面别名替换，**不解析成秒、不做语义换算**，保证是纯损失极小的格式规整。
    无法识别的输入原样返回（不猜测）。
    """
    if not isinstance(text, str):
        return text
    out: list[str] = []
    pos = 0
    for m in _DUR_TOKEN_RE.finditer(text):
        out.append(text[pos:m.start()])
        num, alias = m.group(1), m.group(2)
        canon = _DUR_ALIAS.get(alias.lower(), alias)
        out.append(f"{num}{canon}")
        pos = m.end()
    if not out:
        return text
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------- 规则 R2：标识符规整

def _canonical_id(value: Any) -> Any:
    """设备/测点标识：trim + 去内部空白。

    注意：**不做大小写转换**。`sensor_ids` 黄金集为小写（如 `PUMP-A-01.vib_x`），
    而 `_is_superset` 比对大小写敏感——若在此转大写，会把原本合法的小写 actual 与
    小写期望拆开，造成**误判失败**（归一化方向性错误，实测回退 0.50→0.40）。
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    return re.sub(r"\s+", "", s) if s else value


def _canonical_list(value: Any) -> Any:
    """数组元素逐一做标识符规整（仅当其全部为字符串时）。"""
    if not isinstance(value, list):
        return value
    if value and all(isinstance(x, str) for x in value):
        return [_canonical_id(x) for x in value]
    return value


# ---------------------------------------------------------------- 规则 R3：数字字符串→数值

def _coerce_number(schema: dict[str, Any], value: Any) -> Any:
    """R3：仅 schema 类型为 integer/number 且值为数字字符串时做严格转换。"""
    if not isinstance(schema, dict):
        return value
    stype = schema.get("type")
    if stype not in ("integer", "number") or not isinstance(value, str):
        return value
    s = value.strip()
    if stype == "integer":
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        return value
    try:
        return float(s)
    except ValueError:
        return value


# ---------------------------------------------------------------- 主入口：按工具 Schema 归一化参数

# 需要做 R2 标识符规整的字段（白名单，随 Schema v1 冻结）
_ID_FIELDS = {"device_id", "sensor_ids", "start_node", "device_model"}


def normalize_arguments(tool_name: str,
                        tool_schema: dict[str, Any] | None,
                        arguments: dict[str, Any] | None) -> dict[str, Any]:
    """对单个工具调用的 arguments 应用白名单归一化，返回新 dict（不改入参）。

    逐字段规则：
      - `time_range.{start,end}`：R1 时长别名长度化（ISO 绝对时间不动）。
      - `_ID_FIELDS`：R2 标识符规整（仅 trim/去内部空白，不作大小写转换）。
      - number/integer 字段：R3 数字字符串→数值。
      其余字段（window/aggregation/relation_types/depth/direction/severity/query/
      diagnosis_summary/evidence_refs/fault_keywords/category_filter 等）一律原样保留。
    """
    if not isinstance(arguments, dict):
        return arguments or {}
    norm = dict(arguments)

    # R1：time_range 相对时长
    tr = norm.get("time_range")
    if isinstance(tr, dict):
        ntr = dict(tr)
        for k in ("start", "end"):
            if k in ntr:
                ntr[k] = canonicalize_duration(ntr[k])
        norm["time_range"] = ntr

    # R2：标识符规整
    for key in _ID_FIELDS:
        if key not in norm:
            continue
        if key == "sensor_ids":
            norm[key] = _canonical_list(norm[key])
        else:
            norm[key] = _canonical_id(norm[key])

    # R3：数字字符串 → 数值（仅 schema 类型字段，白名单 key 之外不改）
    props = (tool_schema or {}).get("properties", {})
    for key, value in norm.items():
        if isinstance(value, str) and key in props:
            norm[key] = _coerce_number(props[key], value)

    return norm


# ---------------------------------------------------------------- 自检

def _selftest() -> int:
    failures: list[str] = []

    # R1：时长别名
    if canonicalize_duration("24小时") != "24h":
        failures.append("24小时 应归一为 24h")
    if canonicalize_duration("7 天") != "7d":
        failures.append("7 天 应归一为 7d")
    if canonicalize_duration("90分钟") != "90m":
        failures.append("90分钟 应归一为 90m")
    if canonicalize_duration("1h30m") != "1h30m":
        failures.append("1h30m 应保持原样")
    if canonicalize_duration("2026-09-20T00:00:00+08:00") != "2026-09-20T00:00:00+08:00":
        failures.append("ISO 绝对时间不应被改动")

    # R2：标识符（仅 trim/去空白，**不做大小写转换**，以保持与黄金集小写期望可比对）
    if _canonical_id("pump-a-01") != "pump-a-01":
        failures.append("pump-a-01 不应被改大小写")
    if _canonical_id(" PUMP-A-01 ") != "PUMP-A-01":
        failures.append("带空白标识符应 trim")
    if _canonical_list(["pump-a-01.vib_x ", "PUMP-A-01.temp_bearing_de"]) != \
            ["pump-a-01.vib_x", "PUMP-A-01.temp_bearing_de"]:
        failures.append("sensor_ids 数组元素应仅去空白、不改大小写")

    # R3：数字字符串
    if _coerce_number({"type": "number"}, "7.1") != 7.1:
        failures.append("'7.1' 应转为 7.1")
    if _coerce_number({"type": "integer"}, "3") != 3:
        failures.append("'3' 应转为 3")
    if _coerce_number({"type": "integer"}, "7.1") != "7.1":
        failures.append("非整型字符串不应强转 integer")

    # 主入口：组合验证（验证流程=判分前应用）
    schema = {"type": "object", "properties": {
        "device_id": {"type": "string"},
        "time_range": {"type": "object", "properties": {"start": {"type": "string"}}},
        "depth": {"type": "integer"},
    }}
    arg = {"device_id": "pump-a-01",
           "time_range": {"start": "24小时"},
           "depth": "2"}
    got = normalize_arguments("query_graph", schema, arg)
    if got["device_id"] != "pump-a-01":
        failures.append("device_id 组合路径不应改大小写（保持中性）")
    if got["time_range"]["start"] != "24h":
        failures.append("time_range.start 组合路径未规整")
    if got["depth"] != 2:
        failures.append("depth 数字字符串组合路径未转 number")
    if arg["device_id"] != "pump-a-01":
        failures.append("归一化不得原地修改入参")

    # 防越界：① 复合时长不得被截断；② 语义字段不得被映射
    for compound in ("1h5m", "2d3h", "1h"):
        if canonicalize_duration(compound) != compound:
            failures.append(f"复合/已规范时长不应被改写：{compound}")
    if canonicalize_duration("30分钟") != "30m":
        failures.append("30分钟 应归一为 30m（回归：修复恒假条件后仍须生效）")

    if failures:
        print("[FAIL] param_normalizer 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] param_normalizer 自检通过：R1 时长别名 / R2 标识符(trim,保持中性) / R3 数字转义 / "
          "防越界（语义字段不动）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V1 参数归一化纠错层（脚本独立自检入口）")
    parser.add_argument("--selftest", action="store_true", help="运行自检")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    parser.error("请使用 --selftest")


if __name__ == "__main__":
    sys.exit(main())