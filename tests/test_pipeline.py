"""流水线侧回归测试：param_normalizer（R1–R3）、run_v5（B2 判据失效）、run_v1（多轮上下文）。

对应缺陷：B2（`compare_payload(before, before)` 自比对 → 判据恒真）、
        `param_normalizer` R2 白名单与说明对齐、恒假条件清理。
"""
from pathlib import Path

import pytest

import param_normalizer as pn
import run_v1
import run_v5

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "tools_v4.json"


# ---------------------------------------------------------------- param_normalizer R1–R3
def test_r1_time_range_duration_canonicalized():
    """R1：相对时长别名须长度化（ISO 绝对时间不得被改）。"""
    out = pn.normalize_arguments("query_sensor", None,
                                 {"time_range": {"start": "24 小时", "end": "7天"}})
    assert out["time_range"]["start"] not in ("24 小时",), out
    iso = "2026-09-16T00:00:00+08:00"
    out2 = pn.normalize_arguments("query_sensor", None,
                                  {"time_range": {"start": iso, "end": iso}})
    assert out2["time_range"]["start"] == iso, "绝对 ISO 时间不应被改写"


def test_r2_id_fields_trim_only():
    """R2：标识符只做 trim / 去内部空白，**不作大小写转换**。"""
    out = pn.normalize_arguments("query_sensor", None,
                                 {"device_id": "  PUMP-A-01  ",
                                  "sensor_ids": [" PUMP-A-01.vib_x "]})
    assert out["device_id"] == "PUMP-A-01"
    assert out["sensor_ids"] == ["PUMP-A-01.vib_x"]
    # 大小写必须保持原样（不得被规整成 pump-a-01）
    out2 = pn.normalize_arguments("query_sensor", None, {"device_id": "Pump-A-01"})
    assert out2["device_id"] == "Pump-A-01"


def test_r3_numeric_strings_coerced_when_schema_says_number():
    """R3：schema 声明为 number/integer 时，数字字符串须转数值。"""
    schema = {"properties": {"top_k": {"type": "integer"},
                             "depth": {"type": "integer"}}}
    out = pn.normalize_arguments("search_knowledge", schema, {"top_k": "5", "depth": "2"})
    assert out["top_k"] == 5 and out["depth"] == 2


def test_non_whitelisted_fields_preserved_verbatim():
    """白名单之外的字段一律原样保留（不得被"顺手"归一化）。"""
    args = {"window": "15m", "aggregation": "count_over_limit", "direction": "outgoing",
            "fault_keywords": ["轴承"], "query": "  离心泵 振动  "}
    out = pn.normalize_arguments("search_knowledge", None, dict(args))
    for k, v in args.items():
        assert out[k] == v, f"{k} 不应被改写"


def test_normalize_arguments_does_not_mutate_input():
    """归一化须返回新 dict，不得改写入参。"""
    src = {"device_id": "  PUMP-A-01  ", "time_range": {"start": "24 小时"}}
    snapshot = {"device_id": src["device_id"], "time_range": dict(src["time_range"])}
    pn.normalize_arguments("query_sensor", None, src)
    assert src == snapshot


def test_normalize_arguments_handles_none():
    assert pn.normalize_arguments("query_sensor", None, None) == {}


# ---------------------------------------------------------------- B2：恢复前后 payload 比对
def test_compare_payload_detects_difference():
    """B2 回归核心：**不同**的快照必须报出差异（原缺陷传入 before,before 致判据恒真）。"""
    before = {"alarm": "A1", "evidence": ["e1"], "risk_level": "高",
              "root_cause": "轴承磨损", "confidence": 0.8}
    after = dict(before, risk_level="中")
    diffs = run_v5.compare_payload(before, after)
    assert any("risk_level" in d for d in diffs), diffs


def test_compare_payload_identical_is_empty():
    payload = {"alarm": "A1", "evidence": ["e1"], "risk_level": "高",
               "root_cause": "轴承磨损", "confidence": 0.8}
    assert run_v5.compare_payload(payload, dict(payload)) == []


def test_compare_payload_flags_missing_field():
    """字段缺失须被报出，不得静默通过。"""
    before = {"alarm": "A1"}
    after = {"alarm": "A1", "evidence": []}
    diffs = run_v5.compare_payload(before, after)
    assert diffs and all("字段缺失" in d for d in diffs)


def test_idempotency_key_is_deterministic_and_sensitive():
    """幂等键：同输入同键、内容变则键变（ISS-002 规避手段的基础）。"""
    a = run_v5.idempotency_key("t-1", "诊断", "内容")
    assert a == run_v5.idempotency_key("t-1", "诊断", "内容")
    assert a != run_v5.idempotency_key("t-1", "诊断", "内容2")


def test_blocking_defects_mapping():
    """阻塞缺陷映射：False 即未通过。"""
    assert run_v5.blocking_defects({c: True for c in run_v5.BLOCKING_CHECKS}) == []
    first = next(iter(run_v5.BLOCKING_CHECKS))
    assert run_v5.blocking_defects({first: False}) == [first]


def test_needs_review_keyword_detection():
    """人工审核触发词（REVIEW_KEYWORDS）须能命中；无关键词则命中审核流程。"""
    for kw in run_v5.REVIEW_KEYWORDS:
        assert run_v5.needs_review(f"该设备结论：{kw}") is True, kw
    assert run_v5.needs_review("一切正常，无需处理") is False


# ---------------------------------------------------------------- run_v1：多轮上下文装配
def test_history_of_converts_context_turns():
    """多轮用例的 context 须转成 [{role, content}]，并滤掉非法角色/空内容。"""
    case = {"context": [{"role": "user", "content": "第一轮"},
                        {"role": "assistant", "content": "回答一"},
                        {"role": "system", "content": "系统提示应被滤掉"},
                        {"role": "user", "content": ""}]}
    h = run_v1.history_of(case)
    assert h == [{"role": "user", "content": "第一轮"},
                 {"role": "assistant", "content": "回答一"}]


def test_history_of_returns_none_without_context():
    assert run_v1.history_of({}) is None
    assert run_v1.history_of({"context": []}) is None


def test_file_sha256_matches_hashlib(tmp_path):
    """ISS-034：输入指纹须等于 hashlib.sha256，且缺失文件返回 None（不抛错）。"""
    import hashlib

    f = tmp_path / "x.md"
    f.write_bytes("中文内容\n第二行\n".encode())
    assert run_v1.file_sha256(f) == hashlib.sha256(f.read_bytes()).hexdigest()
    assert run_v1.file_sha256(tmp_path / "missing.md") is None
    assert run_v1.file_sha256(None) is None


def test_meta_records_input_fingerprints():
    """ISS-034 回归：meta 必须落盘输入指纹，且**当时那一版输入可从仓库内找回**。

    动机：`prompt_version` 等字段只记**路径**。`ISS-033` 命名事故中同名路径的内容被替换 →
    事后无法自证实验输入。指纹的价值在于：**输入正当演进后，仍能定位到实验当时用的那一版。**

    因此断言不是"等于当前文件"，而是"等于**当前文件或任一归档副本**"
    （用例集/提示词会随授权修订演进，归档件 `*-pre-*.jsonl` 即为其历史版本）。
    """
    import hashlib
    import json

    meta_path = ROOT / "experiments" / "v1" / "raw" / "EXP-M02-023.meta.json"
    if not meta_path.exists():
        pytest.skip("缺少带指纹的 meta 样本（EXP-M02-023）")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fp = meta.get("input_sha256")
    assert isinstance(fp, dict), "meta 缺少 input_sha256 字段"
    assert set(fp) == {"prompt", "prompt_step", "cases", "schema"}
    for key, rel in (("prompt", meta["prompt_version"]),
                     ("cases", meta["cases"]),
                     ("schema", "schemas/%s.json" % meta["schema_version"])):
        target = (ROOT / str(rel).replace("\\", "/")).resolve()
        candidates = [target] + sorted(target.parent.glob(target.stem + "-pre-*.jsonl"))
        digests = {hashlib.sha256(p.read_bytes()).hexdigest() for p in candidates if p.exists()}
        assert fp[key] in digests, (
            f"{key} 指纹在仓库内找不到对应版本：{rel}\n"
            f"  记录={fp[key]}\n  候选={sorted(digests)}")


def test_done_groups_resume_logic(tmp_path):
    """resume：已完成的 (case, model, repeat) 组须被识别，避免重复调用。"""
    raw = tmp_path / "r.jsonl"
    rec = {"expected": {"case_id": "v1-001"}, "model": "m", "repeat": 1}
    raw.write_text("\n".join([__import__("json").dumps(rec),
                              __import__("json").dumps(dict(rec, repeat=2))]) + "\n",
                   encoding="utf-8")
    done = run_v1.done_groups(raw)
    assert ("v1-001", "m", 1) in done and ("v1-001", "m", 2) in done
    assert ("v1-001", "m", 3) not in done
