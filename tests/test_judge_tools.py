"""judge_tools 回归测试：覆盖历史上真实修复过的判据口径缺陷。

对应缺陷：D1（window 量纲等价）、D2（aggregation 超限别名）、F4（语义覆盖）、
        F6（引用类型）、`--detail-out` 空结果 IndexError、判据分档边界（2026-09-28 重校）。
"""
import json
from pathlib import Path

import pytest

import judge_tools as jt

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "tools_v4.json"
SCHEMAS = jt.load_tool_schemas(SCHEMA)


def _qs():   # query_sensor 的 schema 片段
    return SCHEMAS["query_sensor"]


# ---------------------------------------------------------------- 必填 / 可选 口径
def test_optional_missing_is_not_an_error():
    """判据维度1：**可选**参数缺省 = 采用默认值，不判错。"""
    ok, issues = jt.compare_arguments(
        "query_sensor", _qs(),
        expected={"device_id": "PUMP-A-01", "sensor_ids": ["PUMP-A-01.vib_x"]},
        actual={"device_id": "PUMP-A-01"})
    assert ok and issues == []


def test_required_missing_is_an_error():
    """**必填**参数缺失须报「参数缺失」。"""
    ok, issues = jt.compare_arguments(
        "query_sensor", _qs(),
        expected={"device_id": "PUMP-A-01", "time_range": {"start": "24h"}},
        actual={"time_range": {"start": "24h"}})
    assert not ok and any("参数缺失：device_id" in i for i in issues)


# ---------------------------------------------------------------- 维度3：lenient 豁免 / 多解
def test_lenient_default_waiver():
    """lenient_param_defaults：显式给出声明的可接受默认值 → 判对（2026-09-28 引入）。"""
    args = dict(expected={"window": "1h", "device_id": "PUMP-A-01"},
                actual={"window": "5m", "device_id": "PUMP-A-01"})
    assert not jt.compare_arguments("query_sensor", _qs(), **args)[0]
    assert jt.compare_arguments("query_sensor", _qs(),
                                lenient_defaults={"window": ["5m"]}, **args)[0]


def test_lenient_multi_solution():
    """F5：lenient 同时承载「用例多解」语义（如 v1-007 的 aggregation 多解）。"""
    args = dict(expected={"aggregation": "max"}, actual={"aggregation": "trend"})
    assert not jt.compare_arguments("query_sensor", _qs(), **args)[0]
    assert jt.compare_arguments("query_sensor", _qs(),
                                lenient_defaults={"aggregation": ["trend", "avg"]}, **args)[0]


# ---------------------------------------------------------------- D1 / D2：等价口径
@pytest.mark.parametrize("exp,act", [("15m", "900s"), ("15m", "15min"), ("1h", "60m"), ("5m", "5m")])
def test_window_duration_equivalence(exp, act):
    """D1：window 量纲归一等价（15m = 15min = 900s）。"""
    assert jt.duration_equivalent(exp, act)
    ok, issues = jt.compare_arguments("query_sensor", _qs(),
                                      expected={"window": exp}, actual={"window": act})
    assert ok, issues


def test_window_non_equivalent_still_fails():
    """量纲等价不得误伤：1h ≠ 15m。"""
    ok, issues = jt.compare_arguments("query_sensor", _qs(),
                                      expected={"window": "1h"}, actual={"window": "15m"})
    assert not ok and any("window" in i for i in issues)


@pytest.mark.parametrize("act", ["count", "over_limit", "exceed_count", "count_over_limit"])
def test_aggregation_over_limit_alias(act):
    """D2：count_over_limit 的语义别名视为等价。"""
    ok, issues = jt.compare_arguments("query_sensor", _qs(),
                                      expected={"aggregation": "count_over_limit"},
                                      actual={"aggregation": act})
    assert ok, issues


@pytest.mark.parametrize("act", ["avg", "max", "trend", "raw"])
def test_aggregation_non_alias_fails(act):
    """非超限聚合不得被别名规则放行。"""
    ok, _ = jt.compare_arguments("query_sensor", _qs(),
                                 expected={"aggregation": "count_over_limit"},
                                 actual={"aggregation": act})
    assert not ok


# ---------------------------------------------------------------- ISS-031：非字符串不得令判据崩溃
@pytest.mark.parametrize("bad", [
    {"type": "count_over_limit", "limit": 500},   # 实测 qwen2.5:7b 的真实返回形态
    {"value": "avg"},
    ["avg"],
    5,
    True,
    None,
])
def test_aggregation_non_string_does_not_crash(bad):
    """ISS-031 回归：模型把枚举包成对象/数组时，判据须判「参数值错」，**不得抛 TypeError**。

    原实现 `b in OVER_LIMIT_ALIAS` 对 dict/list 抛 `unhashable type`，导致判分器整体崩溃
    （该缺陷未被 `--selftest` 或既有测试覆盖，由 H9 实跑暴露）。
    """
    ok, issues = jt.compare_arguments("query_sensor", _qs(),
                                      expected={"aggregation": "count_over_limit"},
                                      actual={"aggregation": bad})
    assert ok is False and issues, f"actual={bad!r} 应判参数值错"
    assert jt._aggregation_over_limit_equivalent("count_over_limit", bad) is False
    assert jt._aggregation_over_limit_equivalent(bad, "count_over_limit") is False
    assert jt._aggregation_canonical(bad) == bad, "非字符串须原样返回，不得崩溃或篡改"


@pytest.mark.parametrize("value,expect", [
    ("count", "count_over_limit"), ("over_limit", "count_over_limit"),
    ("exceed_count", "count_over_limit"), ("count_over_limit", "count_over_limit"),
    ("avg", "avg"), ("trend", "trend"),
])
def test_aggregation_canonical_string_behaviour_unchanged(value, expect):
    """ISS-031 修复的边界：**字符串输入的归一行径必须与修复前完全一致**（零口径变更）。"""
    assert jt._aggregation_canonical(value) == expect
    assert jt._aggregation_over_limit_equivalent("count_over_limit", value) is (expect == "count_over_limit")


def test_aggregation_string_behaviour_fully_preserved():
    """对全部枚举值，等价判定结果须与「纯字符串语义」一致（证明修复未改动既有判据）。"""
    for a in ["avg", "max", "min", "trend", "raw", "count_over_limit", "count"]:
        for b in ["avg", "max", "min", "trend", "raw", "count_over_limit", "count"]:
            expected = (a in jt.OVER_LIMIT_ALIAS) and (b in jt.OVER_LIMIT_ALIAS)
            assert jt._aggregation_over_limit_equivalent(a, b) is expected, (a, b)


# ---------------------------------------------------------------- 维度2：超集 / time_range
def test_array_superset_accepted():
    """数组参数走超集口径（多给项可接受，少给即失败）。"""
    assert jt.compare_arguments("query_sensor", _qs(),
                                expected={"sensor_ids": ["PUMP-A-01.vib_x"]},
                                actual={"sensor_ids": ["PUMP-A-01.vib_x", "PUMP-A-01.vib_y"]})[0]
    ok, issues = jt.compare_arguments("query_sensor", _qs(),
                                      expected={"sensor_ids": ["PUMP-A-01.vib_x"]},
                                      actual={"sensor_ids": ["PUMP-A-01.vib_y"]})
    assert not ok and any("sensor_ids" in i for i in issues)


def test_time_range_relative_tolerance():
    """time_range 相对时长走 ±10% 语义等价。"""
    assert jt.compare_arguments("query_sensor", _qs(),
                                expected={"time_range": {"start": "24h"}},
                                actual={"time_range": {"start": "23h"}})[0]
    assert not jt.compare_arguments("query_sensor", _qs(),
                                    expected={"time_range": {"start": "24h"}},
                                    actual={"time_range": {"start": "12h"}})[0]


def test_time_range_absolute_iso_timezone_equivalence():
    """D3：绝对 ISO8601 时间**即刻等价** —— 同一时刻的不同时区表示不判错。

    注意：绝对时间须给出 `start` 与 `end` 两端（仅给绝对 `start` 时无法判定窗口长度，
    判据会交回精确比对，见 `time_range_equivalent` 的 `window()` 注释）。
    """
    assert jt.compare_arguments(
        "query_sensor", _qs(),
        expected={"time_range": {"start": "2026-09-16T00:00:00+08:00",
                                 "end": "2026-09-23T00:00:00+08:00"}},
        actual={"time_range": {"start": "2026-09-15T16:00:00Z",
                               "end": "2026-09-22T16:00:00Z"}})[0]


def test_time_range_absolute_different_instant_fails():
    """时刻真不同时须判错（不得因"都是绝对时间"就放行）。"""
    assert not jt.compare_arguments(
        "query_sensor", _qs(),
        expected={"time_range": {"start": "2026-09-16T00:00:00+08:00",
                                 "end": "2026-09-23T00:00:00+08:00"}},
        actual={"time_range": {"start": "2026-09-10T00:00:00+08:00",
                               "end": "2026-09-17T00:00:00+08:00"}})[0]


# ---------------------------------------------------------------- F4 / F6
def test_query_semantic_match_identical_and_unrelated():
    """F4：query 走语义近似；相同文本必过，无关文本必拒。"""
    q = "离心泵轴承振动速度有效值 报警值 停机值 分区边界"
    assert jt._query_semantic_match(q, q)
    assert not jt._query_semantic_match(q, "今天天气不错适合出门散步")


def test_refs_type_ok_requires_valid_ref():
    """F6：evidence_refs 须非空且每条 type ∈ 合法枚举；类型**覆盖度**不再作为判错依据。"""
    exp = [{"type": "sensor", "ref": "PUMP-A-01.vib_x"},
           {"type": "knowledge", "ref": "chunk-1"}]
    # 至少一条、且类型合法 → 通过（不再要求覆盖 expected 的全部类型）
    assert jt._refs_type_ok(exp, [{"type": "sensor", "ref": "whatever"}])
    assert not jt._refs_type_ok(exp, [])
    assert not jt._refs_type_ok(exp, [{"type": "bogus", "ref": "x"}])
    assert not jt._refs_type_ok(exp, [{"ref": "no-type"}])


# ---------------------------------------------------------------- 多工具配对
def test_match_expected_calls_missing_tool():
    """多工具：缺任一工具须报「工具缺失」。"""
    expected = [{"name": "query_sensor", "arguments": {"device_id": "PUMP-A-01"}},
                {"name": "search_knowledge", "arguments": {"query": "标准"}}]
    actual = [{"name": "query_sensor", "arguments": {"device_id": "PUMP-A-01"}}]
    ok, issues = jt.match_expected_calls(expected, actual, SCHEMAS)
    assert not ok and any("工具缺失" in i and "search_knowledge" in i for i in issues)


# ---------------------------------------------------------------- 分档边界（2026-09-28 重校）
@pytest.mark.parametrize("rate,label", [
    (0.70, "Pass"), (0.69, "中间区间"), (0.50, "中间区间"), (0.49, "No-Go"),
])
def test_multi_tool_tier_boundary(rate, label):
    """多工具档 pass=0.70 / mid=0.50（7B 结构性硬限单独设低线）。"""
    v = jt.judge_verdict_tiered({"多工具": rate})["多工具"]
    assert v.startswith(label), v


@pytest.mark.parametrize("tier", ["拒止", "澄清"])
@pytest.mark.parametrize("rate,label", [
    (0.90, "Pass"), (0.89, "中间区间"), (0.70, "中间区间"), (0.69, "No-Go"),
])
def test_reject_tier_boundary(tier, rate, label):
    """`ISS-036` 拆档后，`拒止` / `澄清` 两档各自沿用原高线 pass=0.90。"""
    v = jt.judge_verdict_tiered({tier: rate})[tier]
    assert v.startswith(label), v


def test_legacy_reject_tier_is_gone():
    """「无效拒绝」档应已被拆为 拒止 / 澄清（防回退）。"""
    assert "无效拒绝" not in jt.TIER_CRITERIA
    assert {"拒止", "澄清"} <= set(jt.TIER_CRITERIA)


def test_clarify_failure_cannot_be_masked_by_refuse_pass():
    """拆档的关键语义：拒止 100% 但澄清 No-Go 时，整体必须是 No-Go（不得被平均掩盖）。"""
    tiers = {"单工具": 1.0, "参数校验": 1.0, "多轮": 1.0, "多工具": 1.0,
             "拒止": 1.0, "澄清": 0.0}
    assert jt.judge_verdict_tiered(tiers)["整体"].startswith("No-Go")


def test_refusal_kind_explicit_then_notes_fallback():
    """考点细分：优先显式字段；缺省由 `notes` 推断（兼容 2026-10-06 前的 raw）。"""
    assert jt.refusal_kind_of({"expect_reject": True, "refusal_kind": "澄清"}) == ("澄清", "explicit")
    assert jt.refusal_kind_of({"expect_reject": True, "refusal_kind": "拒止"}) == ("拒止", "explicit")
    assert jt.refusal_kind_of(
        {"expect_reject": True, "notes": "考察信息不足时的澄清行为"}) == ("澄清", "notes_infer")
    assert jt.refusal_kind_of(
        {"expect_reject": True, "notes": "正确行为是明确拒绝并说明权限边界"}) == ("拒止", "notes_infer")
    assert jt.refusal_kind_of({"expect_reject": False, "notes": "澄清"}) == (None, "n/a")


def test_tier_verdict_no_data_ignored():
    """无该类型用例 → 「无数据」，不得被当作 0% 参与合成。"""
    assert jt.judge_verdict_tiered({"多工具": None})["多工具"] == "无数据"


# ---------------------------------------------------------------- 空结果保护（原 IndexError）
def test_empty_raw_with_detail_out_does_not_crash(tmp_path):
    """回归：`--detail-out` 遇空结果原会 IndexError，现须安全返回 0。"""
    raw = tmp_path / "empty.jsonl"
    raw.write_text("", encoding="utf-8")
    out = tmp_path / "summary.csv"
    detail = tmp_path / "detail.csv"
    rc = jt.main(["--raw", str(raw), "--schema", str(SCHEMA),
                  "--out", str(out), "--detail-out", str(detail)])
    assert rc == 0
    assert not detail.exists(), "空结果不应产出明细文件"


def test_judge_record_and_aggregate_on_minimal_record():
    """judge_record 对最小合法记录须产出稳定结构（防字段漂移）。"""
    rec = {
        "expected": {"case_id": "t-001", "type": "单工具", "expect_reject": False,
                     "expected_tool_calls": [{"name": "query_sensor", "arguments": {
                         "device_id": "PUMP-A-01",
                         "time_range": {"start": "24h"}}}]},
        "result": {"content_clean": "", "tool_calls": [
            {"name": "query_sensor", "arguments": {
                "device_id": "PUMP-A-01",
                "time_range": {"start": "24h"}}}]},
        "model": "m", "repeat": 1, "attempt": 1,
    }
    j = jt.judge_record(rec, SCHEMAS)
    assert j["case_id"] == "t-001" and j["success"] is True
    agg = jt.aggregate([j])
    inner = next(v for v in agg.values() if isinstance(v, dict))
    assert inner["用例数"] == 1 and inner["5_首次成功率"] == 1.0
