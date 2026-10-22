"""路径 D harness（`scripts/run_agent_gate.py`）回归锁。

对应缺口：`EXP-P7-GATE-D` 首跑**漏装打桩**（`main()` 未调 `install_stubs()`），
实测走了真实工具链路（`query_sensor` 因无告警上下文返回「缺少参数 sensor_ids」4 次）。
本文件把「打桩必装」「循环/护栏语义」「离线自检」钉死，防同类复发。
"""
from __future__ import annotations

import json

import pytest

import run_agent_gate as rg


@pytest.fixture(autouse=True)
def _isolate_executors():
    """隔离 `install_stubs()` 的全局副作用（2026-10-22 发现）。

    `rg.install_stubs()` 实现是 `tr._EXECUTORS.update(STUBS)` —— **直接改写模块级
    执行体字典、无回滚**。本文件有两个用例会真的安装打桩（覆盖率 + `--selftest`），
    泄漏后同进程后续测试的 `execute_tool()` 全部走 STUB（实测：让
    `test_device_id_migration` 的工具调用静默返回固定结果）。此处按用例快照/恢复。
    """
    snapshot = dict(rg.tr._EXECUTORS)
    try:
        yield
    finally:
        rg.tr._EXECUTORS.clear()
        rg.tr._EXECUTORS.update(snapshot)


def test_install_stubs_covers_every_product_tool():
    """打桩必须覆盖产品工具面的**每一个**工具，否则会静默退回真实执行体。"""
    rg.install_stubs()
    for name in rg.tr.STUBS_EXPECTED if hasattr(rg.tr, "STUBS_EXPECTED") else rg.STUBS:
        assert rg.tr._EXECUTORS[name] is rg.STUBS[name], f"{name} 未安装打桩"


def test_default_run_installs_stubs(monkeypatch, tmp_path):
    """默认路径（不带 `--no-stub`）必须先安装打桩 —— 首跑事故的直接回归。"""
    called: list[str] = []

    def _spy() -> None:
        called.append("stub")

    monkeypatch.setattr(rg, "install_stubs", _spy)
    monkeypatch.setattr(rg, "load_cases", lambda paths: [])
    out = tmp_path / "noop.jsonl"          # 落临时目录，避免污染 experiments/
    rc = rg.main(["--cases", "evals/v1_cases.jsonl", "--out", str(out), "--quiet"])
    assert rc == 0 and called == ["stub"]


def test_messages_for_keeps_context_then_input():
    """用例驱动口径：system → 历史（按序）→ 本轮输入；不得把期望值塞进消息。"""
    case = {"context": [{"role": "user", "content": "u1"},
                        {"role": "assistant", "content": "a1"}],
            "input": "u2"}
    msgs = rg.messages_for(case, "SYS")
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[-1]["content"] == "u2"


def test_selftest_passes_offline():
    """自检覆盖：工具面 4 只读 / 循环 2 次调用 / 写护栏拦截 / 强制收口 / 审计重定向。"""
    assert rg.main(["--selftest"]) == 0


def test_audit_redirected_out_of_reports():
    """实验审计不得污染**生产审计文件**。

    2026-10-22：断言意图而非字面目录 —— 默认路径在 `experiments/v1/raw/`，
    但 pytest 根 conftest 会用 `AUSCULT_AGENT_GATE_AUDIT_PATH` 把它重定向到临时目录
    （回归不能把已跟踪的实验产物写长）。判据统一为"不在 reports/ 生产审计路径上"。
    """
    path = str(rg.AUDIT_PATH).replace("\\", "/")
    assert "/reports/" not in path, f"gate 审计不得落生产 reports/：{path}"
    # 且 `main()` 必须跑完即还原全局（否则会污染同进程内其它审计调用方）
    rg.main(["--selftest"])
    assert str(rg.sanitizer.AUDIT_LOG_PATH).replace("\\", "/") != path, \
        "main() 退出后未还原 sanitizer.AUDIT_LOG_PATH"


def test_infer_alarm_covers_real_cases_without_leaking_expected():
    """v2-① 告警前置：有设备编号的用例必须注入告警（含「编号只在上下文里」的多轮用例）。"""
    cases = rg.load_cases(["evals/v1_cases.jsonl"])
    by_id = {c["case_id"]: c for c in cases}
    # 设备编号只出现在历史上下文里 → 仍应抽出
    al = rg.infer_alarm(by_id["v1-019"])
    assert al is not None and al.device_id == "PUMP-A-01"
    # 注入的告警不得携带期望值（只补事实）
    got = json.dumps(al.model_dump(), ensure_ascii=False)
    for call in by_id["v1-019"]["expected_tool_calls"]:
        assert json.dumps(call["arguments"], ensure_ascii=False) not in got
    # 判据只看「文本里出现的设备编号」：文本无编号 → 不注入（保持 v1 行为）
    for c in cases:
        text = " ".join(str(t.get("content") or "") for t in (c.get("context") or []))
        text += " " + str(c.get("input") or "")
        if rg._DEVICE_RE.search(text):
            assert rg.infer_alarm(c) is not None, f"{c['case_id']} 文本有编号却未注入告警"
        else:
            assert rg.infer_alarm(c) is None, f"{c['case_id']} 文本无编号却注入了告警"


def test_answer_mode_is_reported_but_not_judged(tmp_path):
    """v2-② 收口形态：自然语言收口只单列，不影响 judge 成败（不进六档）。"""
    import judge_tools as jt

    case = {"case_id": "t-002", "type": "参数校验", "difficulty": "中", "expect_reject": False,
            "input": "4.5 mm/s 是哪个标准规定的？",
            "expected_tool_calls": [{"name": "search_knowledge",
                                     "arguments": {"query": "振动 4.5 标准"}}]}
    rec = {"model": "fake", "attempt": 1, "repeat": 1, "cold_start": True, "tag": "t",
           "harness": rg.HARNESS, "expected": case,
           "result": {"tool_calls": [{"name": "search_knowledge",
                                      "arguments": {"query": "振动 4.5 标准"}}],
                      "tool_calls_missing": False,
                      "content_clean": "| 4.5 ~ 11.2 | 注意 |",   # 表格收口
                      "answer_mode": "natural_language",
                      "json_parse_ok": False, "latency_ms": 1.0, "error": None}}
    schemas = jt.load_tool_schemas(rg.DEFAULT_SCHEMA)
    assert jt.judge_record(rec, schemas)["success"], "收口形态不得影响判分"
    assert rg.answer_mode_of(False, "| 表格 |") == "natural_language"
    assert rg.answer_mode_of(False, "   ") == "none"


def test_judged_record_shape_is_aggregatable(tmp_path):
    """D 的 raw 记录必须能被 `aggregate_runs.tier_and_ok` 直接消费。"""
    import aggregate_runs as ar
    import judge_tools as jt

    call = {"name": "query_sensor",
            "arguments": {"device_id": "PUMP-A-01", "time_range": {"start": "1h"}}}
    case = {"case_id": "t-001", "type": "单工具", "difficulty": "中", "expect_reject": False,
            "input": "查一下 PUMP-A-01 振动", "expected_tool_calls": [call]}
    rec = {"model": "fake", "attempt": 1, "repeat": 1, "cold_start": True, "tag": "t",
           "harness": rg.HARNESS, "expected": case,
           "result": {"tool_calls": [call], "tool_calls_missing": False,
                      "content_clean": "{}", "latency_ms": 1.0, "error": None}}
    schemas = jt.load_tool_schemas(rg.DEFAULT_SCHEMA)
    path = tmp_path / "raw.jsonl"
    path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    tier, ok = ar.tier_and_ok(ar.load_raw(path)[0], schemas)
    assert tier == "单工具" and ok is True
