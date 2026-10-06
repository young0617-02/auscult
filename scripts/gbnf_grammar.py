"""约束解码 Schema 生成器（V1 步骤① · JSON Schema 结构化输出）

★ 命名说明：文件名与函数名沿用早期「GBNF」口径（见 `docs/role-decision.md` §四 步骤①），
   但实际载体是 **JSON Schema**，不是 GBNF 字符串（原因见下方「载体说明」）。
   本文件不产出、不消费任何 GBNF 文本。

对应交付物：`docs/role-decision.md` §四 步骤①「约束解码（载体=JSON Schema）」
输入：`schemas/tools_v1.json`（FROZEN）
输出：一个 JSON Schema dict，供 Ollama 原生 `/api/chat` 的 `format` 字段使用。

★ 载体说明：Ollama 0.34.2 拒绝原始 GBNF 字符串（报 `expected "json" or a valid JSON Schema object`），
   但完整支持 JSON Schema 结构化输出（已实测：基本对象 / `oneOf` / 数组 + `oneOf` 均被接受，
   且正确收敛到分支与 required 字段）。故本生成器产出 JSON Schema dict，约束力不低于手写 GBNF。

产出形态：
  { "type": "array", "items": { "oneOf": [ <5 个工具对象 schema> ] } }
每工具节点：
  { "type": "object",
    "properties": { "name": {"const": "<toolname>"},
                     "arguments": <该工具参数对象 schema> },
    "required": ["name", "arguments"], "additionalProperties": false }

实现要点（保证 llama.cpp JSON Schema→GBNF 转换正确）：
  - 所有对象节点递归置 `additionalProperties=false`（llama.cpp/NFA 转换要求，
    防死循环），嵌套对象（time_range / evidence_refs.item）原本未声明也强制补上；
  - `name` 用 `const` 锁定到精确工具名；`arguments` 复用 tools_v1 参数 schema
    （含 required / enum / 嵌套对象 / 数组），不对 source 对象做原地修改；
  - expect_reject 用例不施加本 schema（应不调用任何工具），由调用方按用例选择 grammar=None。
  - 已知忽略：`pattern` 关键词 llama.cpp 不转换，不影响「结构合法 + required 必现」这一核心目标。

自检：`python scripts/gbnf_grammar.py --selftest`
预览：`python scripts/gbnf_grammar.py --print`（把生成 schema 打到终端，供人工核对）
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "tools_v1.json"


def _ensure_strict(schema: dict[str, Any]) -> dict[str, Any]:
    """递归把对象节点补上 `additionalProperties:false`，并向下遍历数组 items / 嵌套属性。

    llama.cpp 将 JSON Schema 编译为 GBNF 时要求对象封闭键集合，否则可能产生 NFA 死循环；
    本项目所有对象语义本就是封闭键集合，故统一强制关闭未知键。
    """
    t = schema.get("type")
    if t == "object":
        schema.setdefault("additionalProperties", False)
        for value in (schema.get("properties") or {}).values():
            if isinstance(value, dict):
                _ensure_strict(value)
    elif t == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            _ensure_strict(items)
    return schema


def _tool_node(tool: dict[str, Any]) -> dict[str, Any]:
    """单个工具 → oneOf 分支节点：name 用 const 锁定，arguments 复用参数 schema。"""
    name = tool["name"]
    args = copy.deepcopy(tool["parameters"])
    _ensure_strict(args)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": {"const": name},
            "arguments": args,
        },
        "required": ["name", "arguments"],
    }


def build_tool_call_array_grammar(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """生成顶层约束 schema：一个 JSON 数组，元素为 5 个工具之一的合法对象。"""
    nodes = [_tool_node(t) for t in tools]
    return {"type": "array", "items": {"oneOf": nodes}}


def generate_grammar(schema_path: Path = SCHEMA_PATH) -> dict[str, Any]:
    """读取 tools_v1.json 并生成工具调用数组的 JSON Schema。"""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return build_tool_call_array_grammar(schema["tools"])


def _find_node(node: dict[str, Any], name: str) -> dict[str, Any] | None:
    """在 oneOf 节点列表里按工具名查找分支（自检用）。"""
    for sub in node.get("items", {}).get("oneOf", []):
        if sub.get("properties", {}).get("name", {}).get("const") == name:
            return sub
    return None


def _selftest() -> int:
    failures: list[str] = []
    grammar = generate_grammar()

    if not isinstance(grammar, dict) or grammar.get("type") != "array":
        failures.append("顶层 schema 应为 type=array")
    items = grammar.get("items") or {}
    one_of = items.get("oneOf") or []
    if len(one_of) != 5:
        failures.append(f"oneOf 分支数应为 5，实际 {len(one_of)}")

    # 每个工具：name const 精确 + arguments 完整 + required 完整
    for name in ["query_sensor", "search_knowledge", "query_graph",
                 "get_maintenance_history", "generate_report"]:
        node = _find_node(grammar, name)
        if node is None:
            failures.append(f"缺少工具分支 {name}")
            continue
        if node.get("properties", {}).get("name", {}).get("const") != name:
            failures.append(f"{name} 的 name 未用 const 精确锁定")
        if "arguments" not in node.get("properties", {}):
            failures.append(f"{name} 缺少 arguments")
        if sorted(node.get("required", [])) != ["arguments", "name"]:
            failures.append(f"{name} 的 required 应为 [name, arguments]")

    # 所有对象节点必须 additionalProperties=false（含嵌套 time_range / evidence_refs.item）
    for sub in one_of:
        _walk_ap(sub, failures)

    if failures:
        print("[FAIL] gbnf_grammar 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] gbnf_grammar 自检通过：5 工具分支 + name 锁定 + 全局 additionalProperties=false")
    return 0


def _walk_ap(schema: dict[str, Any], failures: list[str]) -> None:
    """断言当前 schema 子树所有对象节点一律 additionalProperties=false。"""
    t = schema.get("type")
    if t == "object":
        if schema.get("additionalProperties") is not False:
            failures.append(f"对象节点未闭合 additionalProperties=false：{schema.get('properties', {}).keys()}")
        for value in (schema.get("properties") or {}).values():
            if isinstance(value, dict):
                _walk_ap(value, failures)
    elif t == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            _walk_ap(items, failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="约束解码 Schema 生成器（V1 步骤① · JSON Schema 结构化输出）")
    parser.add_argument("--selftest", action="store_true", help="运行自检（不联网）")
    parser.add_argument("--print", action="store_true", help="把生成 schema 打印到终端")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH, help="tools_v1.json 路径")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.print:
        print(json.dumps(generate_grammar(args.schema), ensure_ascii=False, indent=2))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())