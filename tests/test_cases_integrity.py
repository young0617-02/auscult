"""V1 用例集完整性测试 —— 锁定「路径 B」修订（`ISS-029` / `R-V1-11`）。

作用：防止 (a) 用例集被静默改动、(b) 「非考点参数」被重新塞回 `expected` 而使
     `ISS-029` 复发、(c) `lenient_param_defaults` 多解机制失效。
依据：`reports/v1-review-v4.md`、`reports/v1-cases-revision-2026-10-05.md`
"""
import json
from pathlib import Path

import pytest

import judge_tools as jt

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "v1_cases.jsonl"
ARCHIVE = ROOT / "evals" / "v1_cases-pre-2026-10-05.jsonl"
SCHEMA = ROOT / "schemas" / "tools_v4.json"

CASES = [json.loads(l) for l in CASES_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
BY_ID = {c["case_id"]: c for c in CASES}
SCHEMAS = jt.load_tool_schemas(SCHEMA)

REQUIRED_KEYS = {"case_id", "type", "difficulty", "input", "expected_tool_calls",
                 "expect_reject", "notes"}


# ---------------------------------------------------------------- 结构与规模
def test_case_count_and_unique_ids():
    assert len(CASES) == 20
    assert len(BY_ID) == 20, "case_id 不得重复"


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_case_required_keys_present(case):
    assert REQUIRED_KEYS <= set(case), f"{case['case_id']} 缺字段"
    assert case["input"].strip(), f"{case['case_id']} 输入为空"
    if case["expect_reject"]:
        # 「无效拒绝」用例的正确行为是**不调用工具** → 期望调用列表必须为空
        assert case["expected_tool_calls"] == [], f"{case['case_id']} 是拒绝用例，不应有期望调用"
    else:
        assert case["expected_tool_calls"], f"{case['case_id']} 无期望调用"


def test_reject_cases_are_declared_consistently():
    """`expect_reject` 与 `type` 须一致（防改用例时漏改其一）。"""
    for c in CASES:
        if c["type"] == "无效拒绝":
            assert c["expect_reject"] is True, f"{c['case_id']} 类型为无效拒绝却未标 expect_reject"
        else:
            assert c["expect_reject"] is False, f"{c['case_id']} 非拒绝用例却标了 expect_reject"


def test_every_expected_tool_exists_in_schema():
    """期望工具名必须都存在于 schema，防止改用例时写错工具名而永不匹配。"""
    for c in CASES:
        for call in c["expected_tool_calls"]:
            assert call["name"] in SCHEMAS, f"{c['case_id']} 引用了未知工具 {call['name']}"


def test_type_coverage():
    """五类形态须保持覆盖（否则分档指标会失真）。"""
    types = {c["type"] for c in CASES}
    assert {"单工具", "多工具", "参数校验", "无效拒绝", "多轮"} <= types


# ---------------------------------------------------------------- 路径 B 锁定：非考点参数不得回流
REMOVED = {
    "v1-002": [("search_knowledge", "top_k")],
    "v1-005": [("query_sensor", "window")],
    "v1-008": [("query_sensor", "window")],
    "v1-011": [("query_sensor", "aggregation")],
    "v1-013": [("query_sensor", "aggregation")],
}


@pytest.mark.parametrize("cid", sorted(REMOVED))
def test_non_kaodian_params_not_reintroduced(cid):
    """ISS-029 防复发：已移出比对的非考点参数**不得**再出现在 expected 中。

    若确需恢复为考点，必须先补 `notes` 声明并走授权流程 —— 届时本测试须一并更新。
    """
    for tool, key in REMOVED[cid]:
        calls = [c for c in BY_ID[cid]["expected_tool_calls"] if c["name"] == tool]
        assert calls, f"{cid} 缺少工具 {tool}"
        assert key not in (calls[0].get("arguments") or {}), \
            f"{cid} 的非考点参数 {tool}.{key} 又回到 expected 了（ISS-029 复发）"


def test_non_kaodian_params_documented_in_notes():
    """每处移出都必须在 notes 留痕（审计可追溯）。"""
    for cid in REMOVED:
        assert "【路径B 2026-10-05】" in BY_ID[cid]["notes"], f"{cid} 缺少修订留痕"


# ---------------------------------------------------------------- 多解机制（lenient）仍生效
def test_multi_solution_lenient_effective_v1_007():
    """v1-007：aggregation 属多解，trend / avg 须被判对（max 仍为期望值）。"""
    case = BY_ID["v1-007"]
    call = next(c for c in case["expected_tool_calls"] if c["name"] == "query_sensor")
    lenient = case["lenient_param_defaults"]
    assert set(lenient["aggregation"]) == {"trend", "avg"}
    for alt in ("trend", "avg", "max"):
        assert jt.compare_arguments("query_sensor", SCHEMAS["query_sensor"],
                                    expected=call["arguments"], actual=call["arguments"],
                                    )[0]
        ok, issues = jt.compare_arguments(
            "query_sensor", SCHEMAS["query_sensor"],
            expected={"aggregation": call["arguments"]["aggregation"]},
            actual={"aggregation": alt}, lenient_defaults=lenient)
        assert ok, f"aggregation={alt} 应被判对，实际 {issues}"


def test_multi_solution_lenient_effective_v1_010():
    """v1-010：aggregation 多解，trend 须被判对。"""
    case = BY_ID["v1-010"]
    call = next(c for c in case["expected_tool_calls"] if c["name"] == "query_sensor")
    ok, issues = jt.compare_arguments(
        "query_sensor", SCHEMAS["query_sensor"],
        expected={"aggregation": call["arguments"]["aggregation"]},
        actual={"aggregation": "trend"},
        lenient_defaults=case["lenient_param_defaults"])
    assert ok, issues


def test_non_solution_value_still_fails():
    """多解不得变成"任意值都行"：非合理解仍须判错。"""
    case = BY_ID["v1-010"]
    call = next(c for c in case["expected_tool_calls"] if c["name"] == "query_sensor")
    ok, _ = jt.compare_arguments(
        "query_sensor", SCHEMAS["query_sensor"],
        expected={"aggregation": call["arguments"]["aggregation"]},
        actual={"aggregation": "raw"},
        lenient_defaults=case["lenient_param_defaults"])
    assert not ok


# ---------------------------------------------------------------- 归档可追溯
def test_pre_revision_archive_exists_and_differs():
    """修订前原件须保留归档，且与被修订版本确有差异（可审计）。"""
    assert ARCHIVE.exists(), "缺少 -pre-2026-10-05 归档件"
    old = {json.loads(l)["case_id"]: json.loads(l)
           for l in ARCHIVE.read_text(encoding="utf-8").splitlines() if l.strip()}
    assert set(old) == set(BY_ID)
    changed = [cid for cid in BY_ID if old[cid] != BY_ID[cid]]
    assert len(changed) == 14, f"归档件应与 14 个被修订用例不同，实际 {len(changed)}"
    for cid in BY_ID:
        for k in ("input", "type", "difficulty", "expect_reject"):
            assert old[cid][k] == BY_ID[cid][k], f"{cid}.{k} 不应被修订"
