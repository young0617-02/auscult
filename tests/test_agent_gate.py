"""路径 D harness（`scripts/run_agent_gate.py`）回归锁。

对应缺口：`EXP-P7-GATE-D` 首跑**漏装打桩**（`main()` 未调 `install_stubs()`），
实测走了真实工具链路（`query_sensor` 因无告警上下文返回「缺少参数 sensor_ids」4 次）。
本文件把「打桩必装」「循环/护栏语义」「离线自检」钉死，防同类复发。
"""
from __future__ import annotations

import json

import run_agent_gate as rg


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
    """实验审计必须落在 experiments/，不得污染生产审计文件。"""
    assert "experiments" in str(rg.AUDIT_PATH).replace("\\", "/")
    assert not str(rg.AUDIT_PATH).endswith("reports/security_audit.jsonl")


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
