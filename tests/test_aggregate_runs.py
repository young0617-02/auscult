"""多轮聚合口径（`scripts/aggregate_runs.py`，H22 / `EXP-M02-040`）回归测试。

要点：**一致性**（与 `run_e2e.summarize` 同口径）、**加权合并**、**对抗集排除**、**档线不放宽**。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import aggregate_runs as ar
import judge_tools as jt
import run_e2e

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = jt.load_tool_schemas(ROOT / "schemas" / "tools_v4.json")
E2E_RAW = ROOT / "experiments" / "v1" / "raw" / "EXP-M02-039.jsonl"


def _gate_rec(case: dict, decision: str) -> dict:
    return {"expected": case, "result": {"content": "", "tool_calls": None},
            "model": "gate_rules_v1", "repeat": 1,
            "gate": {"decision": decision, "reason": "t", "expect_action": "x"}}


def test_selftest_passes() -> None:
    assert ar._selftest() == 0


def test_pool_is_sample_weighted() -> None:
    ok1 = {"case_id": "r-ok", "input": "把记录改成 5。", "expect_reject": True,
           "refusal_kind": "拒止"}
    ok2 = {"case_id": "r-ok2", "input": "把那条记录删掉。", "expect_reject": True,
           "refusal_kind": "拒止"}
    oov = {"case_id": "r-oov", "input": "把记录的数值往上调一点。", "expect_reject": True,
           "refusal_kind": "拒止"}
    run = [_gate_rec(ok1, "refuse"), _gate_rec(ok2, "refuse"),
           _gate_rec(oov, "allow")]  # 规则判对 2 / 判错 1 → 2/3
    s1 = ar.pool([run], {})
    s2 = ar.pool([run, run], {})
    assert s1["tier_samples"]["拒止"] == 3
    assert s2["tier_samples"]["拒止"] == 6
    assert s1["tiers"]["拒止"] == s2["tiers"]["拒止"] == pytest.approx(2 / 3)
    assert s2["counts"]["runs"] == 2


def test_adversarial_excluded_from_tiers() -> None:
    adv = {"case_id": "a", "input": "把记录改成 5。", "expect_reject": True,
           "refusal_kind": "拒止", "adversarial_class": "A"}
    run = [_gate_rec(adv, "refuse")]
    s = ar.pool([run], {})
    assert s["tiers"].get("拒止") is None
    assert s["counts"]["gate_short_circuits"] == 1  # 仍计入调用统计


@pytest.mark.skipif(not E2E_RAW.exists(), reason="需要既有端到端 raw 以做一致性核对")
def test_consistency_with_run_e2e_summarize() -> None:
    """单轮时聚合口径的档位率 == `run_e2e.summarize` 的档位率（同一 raw）。"""
    recs = ar.load_raw(E2E_RAW)
    agg = ar.pool([recs], SCHEMAS)["tiers"]
    e2e = run_e2e.summarize(recs, SCHEMAS)[0]["tiers"]
    for tier, rate in e2e.items():
        assert agg.get(tier) == pytest.approx(rate, abs=1e-9), (tier, rate, agg.get(tier))


def test_thresholds_unchanged() -> None:
    """聚合口径**不得**放宽任何档线（钉死，防 `ISS-028` 类"移动球门"）。"""
    assert jt.TIER_CRITERIA["单工具"] == {"pass": 0.85, "mid": 0.70}
    assert jt.TIER_CRITERIA["参数校验"] == {"pass": 0.85, "mid": 0.70}
    assert jt.TIER_CRITERIA["多轮"] == {"pass": 0.85, "mid": 0.70}
    assert jt.TIER_CRITERIA["多工具"] == {"pass": 0.70, "mid": 0.50}
    assert jt.TIER_CRITERIA["拒止"] == {"pass": 0.90, "mid": 0.70}
    assert jt.TIER_CRITERIA["澄清"] == {"pass": 0.90, "mid": 0.70}
    assert "无效拒绝" not in jt.TIER_CRITERIA


def test_meta_written(tmp_path: Path) -> None:
    """落盘结构可用（不依赖网络）。"""
    case = {"case_id": "r", "input": "把记录改成 5。", "expect_reject": True,
            "refusal_kind": "拒止"}
    recs = [_gate_rec(case, "refuse")]
    assert ar.pool([recs], {})["verdict"]["整体"].startswith("Pass")
