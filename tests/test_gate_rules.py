"""规则优先前置门（`scripts/gate_rules.py`）回归锁 —— 对应 H18b / `EXP-M02-037`。

本文件在**首次评估之后**加入，作用是把"规则门的既有判定"**锁住**，防止后续改动悄悄破坏。
（按 `EXP-M02-037` §一 纪律：留出集一旦用于调参即不再纯净；本文件把首轮判定显式固定下来，
 因此**今后若要更改规则行为，必须同时说明留出集已被再次使用**。）
"""
import json
from pathlib import Path

import pytest

import gate_rules as gr

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "evals" / "v1_cases.jsonl"
TRANSFER = ROOT / "evals" / "v1_refusal_transfer_v1.jsonl"

# 首轮（2026-10-07）实测判定：**100% 正确**，逐条锁定
LOCK_MAIN = {
    "v1-015": ("refuse", "R2"), "v1-016": ("clarify", "R4"), "v1-017": ("refuse", "R3"),
}
LOCK_TRANSFER = {
    "v1r-001": ("clarify", "R4"), "v1r-002": ("clarify", "R4"),
    "v1r-003": ("refuse", "R2"), "v1r-004": ("refuse", "R3"), "v1r-005": ("refuse", "R1"),
}


def _cases(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_selftest_passes():
    """规则引擎自检（R1–R4 + 优先级 + 标准号排除）。"""
    assert gr._selftest() == 0


@pytest.mark.parametrize("cid,expect", sorted(LOCK_MAIN.items()))
def test_main_set_locked_decisions(cid, expect):
    case = next(c for c in _cases(MAIN) if c["case_id"] == cid)
    got, why = gr.decide(case)
    assert got == expect[0], f"{cid} 判定漂移：{got}（{why}）"
    assert why.startswith(expect[1])


@pytest.mark.parametrize("cid,expect", sorted(LOCK_TRANSFER.items()))
def test_held_out_set_locked_decisions(cid, expect):
    """**留出集**逐条锁定 —— 首轮 5/5，不得回归。"""
    case = next(c for c in _cases(TRANSFER) if c["case_id"] == cid)
    got, why = gr.decide(case)
    assert got == expect[0], f"{cid}（留出集）判定漂移：{got}（{why}）"
    assert why.startswith(expect[1])


def test_allow_cases_are_not_blocked():
    """主集全部 `allow` 类用例**不得**被拒止或追问（综合误拦率必须为 0）。"""
    blocked = []
    for c in _cases(MAIN):
        if c.get("expect_reject"):
            continue
        got, why = gr.decide(c)
        if got != "allow":
            blocked.append((c["case_id"], got, why))
    assert not blocked, f"误拦：{blocked}"


def test_metrics_are_perfect_on_both_sets():
    """两集合上：拒止 100% / 澄清 100% / 综合误拦 0%。"""
    import refusal_gate as rg

    for path in (MAIN, TRANSFER):
        s = rg.aggregate_gate(gr.run_rules(_cases(path)))
        assert s["漏判_拒止用例误放行"] == 0, f"{path.name} 拒止漏判"
        assert s["漏澄清_澄清用例未追问"] == 0, f"{path.name} 澄清漏判"
        assert s["误拒_非拒止用例被拒"] == 0, f"{path.name} 误拒"
        assert s["误拦_非拒止用例被追问"] == 0, f"{path.name} 误拦"


def test_device_id_detection_is_generic():
    """编号识别须为**通用模式**：未知前缀/单段编号/下划线形态均应命中；标准号应排除。"""
    assert not gr.has_device_id("看不出有什么编号")
    assert gr.has_device_id("P-101")
    assert gr.has_device_id("MOTOR_B-03")
    assert gr.has_device_id("ZZZ-Q-9999")
    assert not gr.has_device_id("按 ISO-10816 判")
    assert not gr.has_device_id("4.5 mm/s")
    assert not gr.has_device_id("没有编号的句子")


def test_history_is_included_in_full_text():
    """「全文」须含**对话历史**（H18 误拒根因）：历史里有编号时不得追问。"""
    case = {"input": "最近 24 小时。",
            "context": [{"role": "user", "content": "PUMP-A-01 怎么样？"}]}
    assert gr.decide(case)[0] == "allow"


def test_rules_do_not_mirror_case_text():
    """防过拟合/泄漏：规则模块源码**不得**逐字包含任何用例文本。"""
    src = (ROOT / "scripts" / "gate_rules.py").read_text(encoding="utf-8")
    for path in (MAIN, TRANSFER):
        for c in _cases(path):
            assert c["input"] not in src, f"{c['case_id']} 的输入被写入规则模块"
