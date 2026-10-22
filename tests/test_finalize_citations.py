"""Must#7「证据引用强制」的负路径回归锁（2026-10-22 补齐）。

## 为什么有这个文件

`finalize` 自 2026-10-14 起对**无效**引用（`E_INVALID_CITATION`）硬阻断，但 `citations=[]`
时循环直接跳过 —— 于是"无来源不出结论"只对"给了错的引用"成立，对"不给引用"不成立。
2026-10-22 跑 S1 主场景实测坐实：报告 `citations=None` 仍定稿（`RPT-dfbf857be97f625e`）。

本文件锁住修复后的四条边界：

| 场景 | 期望 |
|---|---|
| 正常路径 + 有引用 | 产出 `report_id` |
| 正常路径 + **零引用** | **阻断**（`E_NO_CITATION`，不产 `report_id`） |
| 正常路径 + 引用不存在 | 阻断（`E_INVALID_CITATION`） |
| 降级 / 拒答 + 零引用 | **放行**（其产出本就不是正式结论，且已带降级披露） |

> 降级放行不是妥协：`build.py` 的 `degrade` 分支此前就断言「仍产出 `RPT-*`」（e2e E3/E5/E6），
> 若无条件拦截会把"降级路径可用"一并打死。
"""

from __future__ import annotations

from app.graph.nodes.finalize import finalize
from app.graph.state import DiagnosisState, EvidenceItem, RootCause, Suggestion


def _state(**kw) -> DiagnosisState:
    base = {
        "thread_id": "thr-test",
        "diagnosis": "轴承磨损导致振动超标",
        "confidence": 0.82,
        "risk_level": "low",
    }
    base.update(kw)
    return DiagnosisState(**base)


def _codes(result: dict) -> list[str]:
    return [e["code"] for e in result.get("errors", [])]


# ------------------------------------------------ 正常路径

def test_citations_present_produces_report():
    r = finalize(_state(
        evidence=[EvidenceItem(chunk_id="c1")],
        root_causes=[RootCause(cause="轴承磨损", citations=["c1"])],
        suggestions=[Suggestion(action="更换轴承", citations=["c1"])],
    ))
    assert r["report_id"].startswith("RPT-")
    assert "E_NO_CITATION" not in _codes(r)


def test_zero_citations_blocks_report():
    """正常路径零引用 → 不给 report_id（本次修复的核心）。"""
    r = finalize(_state(
        evidence=[EvidenceItem(chunk_id="c1")],
        root_causes=[RootCause(cause="轴承磨损", citations=[])],
        suggestions=[Suggestion(action="更换轴承", citations=[])],
    ))
    assert r["report_id"] is None
    assert r["blocked"] is True
    assert r["degrade_reason"] == "invalid_citation_blocked"
    assert "E_NO_CITATION" in _codes(r)


def test_no_root_causes_at_all_blocks(monkeypatch):
    """连根因都没给（空列表）也算零引用。"""
    r = finalize(_state(root_causes=[], suggestions=[]))
    assert r["report_id"] is None
    assert "E_NO_CITATION" in _codes(r)


def test_invalid_citation_still_blocks():
    r = finalize(_state(
        evidence=[EvidenceItem(chunk_id="c1")],
        root_causes=[RootCause(cause="X", citations=["c1", "NOT_EXIST"])],
    ))
    assert r["report_id"] is None
    assert "E_INVALID_CITATION" in _codes(r)


def test_chunk_id_prefix_is_normalized():
    """`chunk_id=c1` 与 `c1` 同口径，不应误判无效。"""
    r = finalize(_state(
        evidence=[EvidenceItem(chunk_id="c1")],
        root_causes=[RootCause(cause="X", citations=["chunk_id=c1"])],
    ))
    assert r["report_id"].startswith("RPT-")


# ------------------------------------------------ 降级 / 拒答例外

def test_degraded_path_allows_zero_citations():
    """降级路径（degrade_reason 非空）允许无引用 —— 否则 E3/E5/E6「降级仍出报告」会被打死。"""
    r = finalize(_state(degrade_reason="低置信度（0.31 < 0.50）", confidence=0.31,
                        root_causes=[], suggestions=[]))
    assert r["report_id"].startswith("RPT-")
    assert "E_NO_CITATION" not in _codes(r)


def test_refusal_path_allows_zero_citations():
    """合规拒答（refusal）同样允许无引用：产出是"无法作答"而不是结论。"""
    r = finalize(_state(refusal={"kind": "refusal", "reason": "越界请求"},
                        confidence=0.0, risk_level="low",
                        root_causes=[], suggestions=[]))
    assert r["report_id"].startswith("RPT-")
    assert "E_NO_CITATION" not in _codes(r)


# ------------------------------------------------ 传播契约

def test_blocked_carries_warnings_too():
    """阻断时 warnings 一并带出（前端/审核要能看到"为什么没出报告"）。"""
    r = finalize(_state(diagnosis=None, root_causes=[], suggestions=[]))
    codes = _codes(r)
    assert "E_NO_CITATION" in codes
    assert "W_NO_DIAGNOSIS" in codes
