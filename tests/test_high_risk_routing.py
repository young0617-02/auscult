"""Must#9「高风险强制审核」的绕过路径回归锁（2026-10-22）。

## 三条绕过路径（核对报告 §一 #9）

| # | 路径 | 现象 |
|---|---|---|
| ① | `high + confidence<0.50` | 走 `degrade` 而非审核 → 报告落库但 `review_status=NULL`，**永远无法补审** |
| ② | `escalate_cloud → finalize` 直连 | 云端回来的结论即使 `risk=high` 也不审核 —— 换后端即绕过 |
| ③ | `auto_approved` 只看 `needs_review` | 该值受 `risk_rules.yml` 的 `always_interrupt_when_high` 控制，改 YAML 即可绕过 |

本文件把三条都锁在**纯函数**上（不跑图、不调 LLM）：
`_route_condition` / `_route_after_cloud` / `should_auto_approve`。
"""

from __future__ import annotations

from app.graph.build import _route_after_cloud, _route_condition
from app.graph.nodes.review import should_auto_approve
from app.graph.state import DiagnosisState


def _state(**kw) -> DiagnosisState:
    base = {"thread_id": "thr-x", "diagnosis": "轴承磨损", "confidence": 0.82, "risk_level": "low"}
    base.update(kw)
    return DiagnosisState(**base)


# ------------------------------------------------ ① 高风险优先于置信度

def test_high_risk_low_confidence_goes_to_review_not_degrade():
    """修复①：high + 0.3 原本 degrade（不审核），现在必须进审核。"""
    assert _route_condition(_state(risk_level="high", confidence=0.30)) == "human_review"


def test_high_risk_medium_confidence_goes_to_review_not_cloud():
    """修复①的副作用（有意为之）：high 不再走云端升级，直接人审。"""
    assert _route_condition(_state(risk_level="high", confidence=0.60)) == "human_review"


def test_medium_low_confidence_still_degrades():
    """非高风险仍按置信度降级 —— 修复不能把降级路径打死。"""
    assert _route_condition(_state(risk_level="medium", confidence=0.30)) == "degrade"


def test_medium_mid_confidence_still_escalates():
    assert _route_condition(_state(risk_level="medium", confidence=0.60)) == "escalate_cloud"


def test_low_confidence_high_confidence_finalizes():
    assert _route_condition(_state(risk_level="low", confidence=0.90)) == "finalize"


def test_refusal_short_circuits_before_review():
    """合规拒答先于 high 判定：拒答没有结论，不该占用审核资源。"""
    st = _state(risk_level="high", confidence=0.0, refusal={"kind": "refusal", "reason": "越界"})
    assert _route_condition(st) == "finalize"


def test_needs_human_goes_to_review():
    st = _state(risk_level="medium", confidence=0.90,
                needs_human=True, human_reason="传感器数据缺失")
    assert _route_condition(st) == "human_review"


# ------------------------------------------------ ② 云端升级后补审

def test_cloud_upgrade_high_risk_requires_review():
    """修复②：云端回来的 high 必须补审（原实现直连 finalize）。"""
    st = _state(risk_level="high", confidence=0.80, escalate_cloud=True)
    assert _route_after_cloud(st) == "human_review"


def test_cloud_upgrade_needs_human_requires_review():
    st = _state(risk_level="medium", confidence=0.80, escalate_cloud=True, needs_human=True)
    assert _route_after_cloud(st) == "human_review"


def test_cloud_upgrade_still_low_confidence_degrades():
    st = _state(risk_level="medium", confidence=0.40, escalate_cloud=True)
    assert _route_after_cloud(st) == "degrade"


def test_cloud_upgrade_ok_finalizes():
    st = _state(risk_level="medium", confidence=0.90, escalate_cloud=True)
    assert _route_after_cloud(st) == "finalize"


def test_cloud_upgrade_refusal_finalizes():
    st = _state(risk_level="high", confidence=0.0, escalate_cloud=True,
                refusal={"kind": "refusal", "reason": "越界"})
    assert _route_after_cloud(st) == "finalize"


# ------------------------------------------------ ③ auto_approved 配置硬化

def test_auto_approve_never_for_high_even_if_rules_say_so():
    """修复③：即便 rules 判 needs_review=False（配置漂移），risk=high 也不自动通过。"""
    risk_eval = {"needs_review": False, "reasons": []}
    assert should_auto_approve(_state(risk_level="high"), risk_eval) is False


def test_auto_approve_never_for_needs_human():
    risk_eval = {"needs_review": False, "reasons": []}
    st = _state(risk_level="medium", needs_human=True, human_reason="拿不准")
    assert should_auto_approve(st, risk_eval) is False


def test_auto_approve_allowed_for_clean_medium():
    risk_eval = {"needs_review": False, "reasons": []}
    assert should_auto_approve(_state(risk_level="medium"), risk_eval) is True


def test_auto_approve_blocked_when_rules_hit():
    risk_eval = {"needs_review": True, "reasons": ["关键词命中: 停机"]}
    assert should_auto_approve(_state(risk_level="medium"), risk_eval) is False
