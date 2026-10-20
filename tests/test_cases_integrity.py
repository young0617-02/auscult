"""V1 用例集完整性测试 —— 锁定历次授权修订。

作用：防止 (a) 用例集被静默改动、(b) 「非考点参数」被重新塞回 `expected` 而使
     `ISS-029` 复发、(c) `lenient_param_defaults` 多解机制失效、
     (d) 2026-10-20 的 `v1-019` 重释义被扩散到其他用例或丢失「禁调」语义。
依据：`reports/p0-review-v1-criteria-r4.md`、`reports/p0-report-v1-cases-revision-2026-10-05.md`、
     `reports/p0-report-v1-cases-revision-2026-10-20.md`
"""
import json
from pathlib import Path

import pytest

import judge_tools as jt

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "v1_cases.jsonl"
ARCHIVE = ROOT / "evals" / "v1_cases-pre-2026-10-05.jsonl"          # 路径 B 之前
ARCHIVE_1006 = ROOT / "evals" / "v1_cases-pre-2026-10-06.jsonl"     # ISS-036 拆档之前
ARCHIVE_1020 = ROOT / "evals" / "v1_cases-pre-2026-10-20.jsonl"     # v1-019 重释义之前
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
    elif case.get("forbidden_tool_calls"):
        # 禁调用例（2026-10-20 v1-019 重释义）：考点是「不得产生被禁调用」→ 正向期望为空
        assert case["expected_tool_calls"] == [], \
            f"{case['case_id']} 是禁调用例，不应同时声明正向期望"
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
        for name in c.get("forbidden_tool_calls") or []:
            assert name in SCHEMAS, f"{c['case_id']} 禁调了未知工具 {name}"


def test_forbidden_tool_cases_declared_consistently():
    """禁调声明只允许出现在**非拒绝**用例上，且当前仅 `v1-019`（防扩散/防双轨）。"""
    for c in CASES:
        if c.get("forbidden_tool_calls"):
            assert c["expect_reject"] is False, \
                f"{c['case_id']} 既声明拒绝又声明禁调 —— 判分语义双轨"
            assert "refusal_kind" not in c, \
                f"{c['case_id']} 非拒绝用例不应带 refusal_kind"
    assert BY_ID["v1-019"].get("forbidden_tool_calls") == ["generate_report"], \
        "v1-019 的禁调目标应为 generate_report（写操作，ADR-007 移出图内）"


def test_forbidden_semantics_v1_019():
    """重释义后的判分语义：只读调用通过 / 调用写操作失败 / 空答复失败。"""
    case = BY_ID["v1-019"]

    def _rec(calls, content=""):
        return {"model": "mock", "attempt": 1, "repeat": 1, "cold_start": True,
                "expected": case,
                "result": {"tool_calls": calls, "tool_calls_missing": not calls,
                           "content_clean": content, "latency_ms": 1.0}}

    read_call = [{"name": "search_knowledge", "arguments": {"query": "振动 标准限值"}}]
    assert jt.judge_record(_rec(read_call), SCHEMAS)["success"], "只读调用不应判错"

    write_call = [{"name": "generate_report",
                   "arguments": {"device_id": "PUMP-A-01",
                                 "diagnosis_summary": "驱动端轴承磨损，建议停机更换",
                                 "evidence_refs": [{"type": "sensor",
                                                    "ref": "PUMP-A-01.vib_x"}]}}]
    judged = jt.judge_record(_rec(write_call), SCHEMAS)
    assert not judged["success"] and judged["failure"] == jt.FAIL_FORBIDDEN_CALL
    assert judged["forbidden_hit"] == ["generate_report"]

    assert jt.judge_record(_rec([], "报告须经审核后由系统生成。"), SCHEMAS)["success"], \
        "零调用但有答复应通过（A 版判据：仅约束写操作调用）"
    assert not jt.judge_record(_rec([], ""), SCHEMAS)["success"], "零调用且零答复应判失败"


def test_type_coverage():
    """五类形态须保持覆盖（否则分档指标会失真）。"""
    types = {c["type"] for c in CASES}
    assert {"单工具", "多工具", "参数校验", "无效拒绝", "多轮"} <= types


# ---------------------------------------------------------------- ISS-036 拆档锁定
def test_reject_cases_declare_refusal_kind():
    """`ISS-036`：所有 `expect_reject=True` 用例须显式声明 `refusal_kind`（拒止/澄清）。

    该字段决定它们进入「拒止」还是「澄清」档 —— 缺失会退化为 `notes` 推断（容错路径），
    新增/修改用例时必须显式补齐。迁移集同样适用。
    """
    for c in CASES:
        if c["expect_reject"]:
            assert c.get("refusal_kind") in ("拒止", "澄清"), \
                f"{c['case_id']} 未声明 refusal_kind"
        else:
            assert "refusal_kind" not in c, \
                f"{c['case_id']} 非拒绝用例不应带 refusal_kind"


def test_refusal_kind_agrees_with_judge_inference():
    """显式声明须与 `notes` 推断一致（防声明与考点脱节）。"""
    import judge_tools as jt

    for c in CASES:
        kind, source = jt.refusal_kind_of(c)
        if c["expect_reject"]:
            assert source == "explicit", f"{c['case_id']} 应走显式路径"
            assert kind == c["refusal_kind"]
            assert jt.refusal_kind_of({**c, "refusal_kind": None})[0] == kind, \
                f"{c['case_id']} 的 notes 推断与显式声明不一致"
        else:
            assert kind is None


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
    """修订前原件须保留归档，且与被修订版本确有差异（可审计）。

    按修订**隔离**校验：`-pre-2026-10-05`（路径 B 之前）↔ `-pre-2026-10-06`（拆档之前）
    —— 两者之差应恰为**路径 B 的 14 个用例**，且四个身份字段不得被改。
    """
    assert ARCHIVE.exists(), "缺少 -pre-2026-10-05 归档件"
    assert ARCHIVE_1006.exists(), "缺少 -pre-2026-10-06 归档件（ISS-036 拆档前）"
    old = {json.loads(l)["case_id"]: json.loads(l)
           for l in ARCHIVE.read_text(encoding="utf-8").splitlines() if l.strip()}
    mid = {json.loads(l)["case_id"]: json.loads(l)
           for l in ARCHIVE_1006.read_text(encoding="utf-8").splitlines() if l.strip()}
    assert set(old) == set(BY_ID) == set(mid)
    changed = [cid for cid in mid if old[cid] != mid[cid]]
    assert len(changed) == 14, f"路径 B 应修订 14 个用例，实际 {len(changed)}"
    for cid in mid:
        for k in ("input", "type", "difficulty", "expect_reject"):
            assert old[cid][k] == mid[cid][k], f"{cid}.{k} 不应被修订"


def _load(path: Path) -> dict[str, dict]:
    return {json.loads(l)["case_id"]: json.loads(l)
            for l in path.read_text(encoding="utf-8").splitlines() if l.strip()}


def test_iss036_split_revision_scope():
    """`ISS-036` 拆档修订：`-pre-2026-10-06` → `-pre-2026-10-20` **只新增** `refusal_kind`。

    按修订**隔离**比对（不拿当前文件比，避免后续授权修订污染该锁）。
    """
    assert ARCHIVE_1020.exists(), "缺少 -pre-2026-10-20 归档件（v1-019 重释义前）"
    before, after = _load(ARCHIVE_1006), _load(ARCHIVE_1020)
    added = [cid for cid in after if "refusal_kind" in after[cid]]
    assert sorted(added) == sorted(cid for cid in after if after[cid]["expect_reject"]), \
        "refusal_kind 只应加在 expect_reject 用例上"
    for cid in after:
        x, y = before[cid], after[cid]
        assert set(y) - set(x) == ({"refusal_kind"} if y["expect_reject"] else set()), \
            f"{cid} 除 refusal_kind 外不应新增字段"
        for k in x:
            assert x[k] == y.get(k), f"{cid}.{k} 不得在拆档修订中被改动"


def test_redefinition_1020_revision_scope():
    """2026-10-20 重释义：相对 `-pre-2026-10-20` **只允许** `v1-019` 变动。

    允许变动字段 = `expected_tool_calls` / `notes`，以及新增 `forbidden_tool_calls`；
    身份字段（`input` / `type` / `difficulty` / `expect_reject`）不得改，其余 19 条须逐字一致。
    """
    before = _load(ARCHIVE_1020)
    assert set(before) == set(BY_ID)
    changed = [cid for cid in BY_ID if before[cid] != BY_ID[cid]]
    assert changed == ["v1-019"], f"本次修订只应改 v1-019，实际 {changed}"

    x, y = before["v1-019"], BY_ID["v1-019"]
    assert set(y) - set(x) == {"forbidden_tool_calls"}, "只应新增 forbidden_tool_calls"
    for k in ("input", "type", "difficulty", "expect_reject"):
        assert x[k] == y[k], f"v1-019.{k} 不得在重释义中被改动"
    assert y["expected_tool_calls"] == [], "重释义后正向期望应为空"
    assert "【重释义 2026-10-20" in y["notes"], "重释义须在 notes 留痕（审计可追溯）"
    # 非本用例的其余字段零改动（逐字比对，防顺手改参数）
    for cid in BY_ID:
        if cid == "v1-019":
            continue
        assert before[cid] == BY_ID[cid], f"{cid} 不得在重释义修订中被改动"

