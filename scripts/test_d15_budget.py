"""D15 自测：预算熔断 + 离线降级 + 条件边全量接入

验证项：
  1. BudgetGuard.check() 未超限 → ok=True（Redis 在线）
  2. BudgetGuard.increment() 计数 +1
  3. 预算超限熔断 → ok=False（mock Redis count ≥ limit）
  4. Redis 不可达 → ok=True（不阻塞，fallback）
  5. check_budget() 兼容接口返回 bool
  6. budget_status() 返回完整状态 dict
  7. CloudRouter 预算熔断 → degrade_reason="budget_exceeded"
  8. 条件边全量：5 分支路由（degrade×2 / escalate_cloud / human_review / finalize）

用法：
  .venv\\Scripts\\python.exe scripts\\test_d15_budget.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import AlarmEvent, DiagnosisState  # noqa: E402
from app.router import budget as budget_mod  # noqa: E402
from app.router.budget import BudgetGuard, budget_status, check_budget  # noqa: E402
from app.router import cloud  # noqa: E402
from app.router.cloud import CloudRouter  # noqa: E402
from app.graph.build import _route_condition  # noqa: E402


# ---------------------------------------------------------------- 辅助

def _make_state(*, confidence=0.6, retry_count=0, risk_level="medium") -> DiagnosisState:
    return DiagnosisState(
        alarm=AlarmEvent(alarm_id="a1", device_id="PUMP-A",
                         metric="vib_rms", value=7.1, ts=0),
        thread_id="d15-test",
        confidence=confidence,
        retry_count=retry_count,
        risk_level=risk_level,
    )


# ---------------------------------------------------------------- 测试

def test_budget_under_limit() -> None:
    """1. 未超限 → ok=True。"""
    guard = BudgetGuard()
    ok, count, limit, reason = guard.check()
    assert ok is True, f"应允许调用（reason={reason}）"
    assert limit > 0, "limit 应 > 0"
    assert reason == "ok" or "redis_unreachable" in reason
    print(f"[PASS] 预算未超限（count={count}/{limit}）")


def test_budget_increment() -> None:
    """2. increment 计数 +1。"""
    guard = BudgetGuard()
    _, before, _, _ = guard.check()
    new_count = guard.increment()
    assert new_count >= 0, "increment 应返回非负数（-1 = Redis 不可达）"
    if new_count > 0:
        assert new_count == before + 1, \
            f"计数应 +1（before={before}, after={new_count}）"
    print(f"[PASS] increment 计数（before={before}, after={new_count}）")


def test_budget_exceeded() -> None:
    """3. 预算超限熔断 → ok=False（mock）。"""
    guard = BudgetGuard()
    limit = budget_mod._get_limit()
    with patch.object(budget_mod, "_get_client") as mock_client_fn:
        mock_client = mock_client_fn.return_value
        mock_client.get.return_value = str(limit + 10)
        ok, count, limit_val, reason = guard.check()
    assert ok is False, "超限应熔断"
    assert count == limit + 10
    assert "budget_exceeded" in reason
    print(f"[PASS] 预算超限熔断（{count}/{limit_val}）")


def test_redis_unreachable() -> None:
    """4. Redis 不可达 → ok=True（不阻塞）。"""
    guard = BudgetGuard()
    with patch.object(budget_mod, "_get_client",
                      side_effect=ConnectionError("redis down")):
        ok, count, limit, reason = guard.check()
    assert ok is True, "Redis 不可达时不应阻塞"
    assert "redis_unreachable" in reason
    print(f"[PASS] Redis 不可达 → 不阻塞（reason={reason}）")


def test_check_budget_compat() -> None:
    """5. check_budget() 兼容接口返回 bool。"""
    result = check_budget()
    assert isinstance(result, bool)
    print(f"[PASS] check_budget() 兼容接口（={result}）")


def test_budget_status() -> None:
    """6. budget_status() 返回完整状态 dict。"""
    status = budget_status()
    assert "ok" in status and "count" in status
    assert "limit" in status and "reason" in status
    print(f"[PASS] budget_status()（ok={status['ok']}, count={status['count']})")


def test_cloud_budget_exceeded_degrade() -> None:
    """7. CloudRouter 预算熔断 → degrade_reason="budget_exceeded"。"""
    state = _make_state()
    router = CloudRouter()
    with patch.object(budget_mod, "_get_client") as mock_client_fn:
        mock_client = mock_client_fn.return_value
        mock_client.get.return_value = "999999"
        result = router.escalate(state)
    assert result.get("degrade_reason") == "budget_exceeded"
    assert result.get("escalate_cloud") is True
    assert result["errors"][0]["code"] == "E_BUDGET_EXCEEDED"
    print("[PASS] CloudRouter 预算熔断 → degrade")


def test_route_condition_all_branches() -> None:
    """8. 条件边全量：5 分支路由。

    1. retry_count >= 3 → degrade
    2. confidence < 0.50 → degrade
    3. confidence ∈ [0.50, 0.75) → escalate_cloud
    4. risk_level == "high" → human_review
    5. else → finalize
    """
    # 1. retry >= 3 → degrade
    s = _make_state(confidence=0.9, retry_count=3, risk_level="low")
    assert _route_condition(s) == "degrade", "retry≥3 应路由到 degrade"

    # 2. conf < 0.50 → degrade
    s = _make_state(confidence=0.30, retry_count=0, risk_level="low")
    assert _route_condition(s) == "degrade", "conf<0.50 应路由到 degrade"

    # 3. conf ∈ [0.50, 0.75) → escalate_cloud
    s = _make_state(confidence=0.60, retry_count=0, risk_level="medium")
    assert _route_condition(s) == "escalate_cloud", "conf∈[0.50,0.75) 应路由到 escalate_cloud"

    # 3b. 边界 conf=0.50 → escalate_cloud（0.50 不 < 0.50）
    s = _make_state(confidence=0.50, retry_count=0, risk_level="medium")
    assert _route_condition(s) == "escalate_cloud", "conf=0.50 应路由到 escalate_cloud"

    # 3c. 边界 conf=0.749 → escalate_cloud
    s = _make_state(confidence=0.749, retry_count=0, risk_level="medium")
    assert _route_condition(s) == "escalate_cloud", "conf=0.749 应路由到 escalate_cloud"

    # 4. risk=high（conf >= 0.75）→ human_review
    s = _make_state(confidence=0.80, retry_count=0, risk_level="high")
    assert _route_condition(s) == "human_review", "risk=high 应路由到 human_review"

    # 5. else → finalize
    s = _make_state(confidence=0.85, retry_count=0, risk_level="low")
    assert _route_condition(s) == "finalize", "else 应路由到 finalize"

    # 优先级验证：retry≥3 优先于 conf（即使 conf 也很低）
    s = _make_state(confidence=0.30, retry_count=3, risk_level="low")
    assert _route_condition(s) == "degrade", "retry≥3 应优先于 conf<0.50"

    # 优先级验证：conf<0.50 优先于 risk=high
    s = _make_state(confidence=0.40, retry_count=0, risk_level="high")
    assert _route_condition(s) == "degrade", "conf<0.50 应优先于 risk=high"

    print("[PASS] 条件边全量（5 分支 + 优先级验证）")


def main() -> int:
    tests = [
        ("预算未超限", test_budget_under_limit),
        ("increment 计数", test_budget_increment),
        ("预算超限熔断", test_budget_exceeded),
        ("Redis 不可达 fallback", test_redis_unreachable),
        ("check_budget() 兼容", test_check_budget_compat),
        ("budget_status()", test_budget_status),
        ("CloudRouter 预算熔断", test_cloud_budget_exceeded_degrade),
        ("条件边全量 5 分支", test_route_condition_all_branches),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D15 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
