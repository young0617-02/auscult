"""D18 自测：审核生命周期（4h 通知 / 24h 超时 / 并发锁 / 职责分离）

验证项：
  1. ReviewLock.acquire 获取成功
  2. ReviewLock.acquire 互斥（不同 reviewer → False）
  3. ReviewLock.acquire 可重入（同一 reviewer → True）
  4. ReviewLock.release 释放成功
  5. ReviewLock.release 非持有者释放 → False
  6. check_review_timeout 未超时 → "none"
  7. check_review_timeout 4h → "notify_backup"
  8. check_review_timeout 24h → "timeout"
  9. notify_backup_reviewer 写审计日志
  10. validate_submitter 同一人 → False，不同人 → True
  11. auto_timeout_resume 图内超时降级

用法：
  .venv\\Scripts\\python.exe scripts\\test_d18_lifecycle.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.review import lifecycle  # noqa: E402
from app.review.lifecycle import (  # noqa: E402
    ReviewLock,
    auto_timeout_resume,
    check_review_timeout,
    notify_backup_reviewer,
    validate_submitter,
)


# ---------------------------------------------------------------- 测试

def test_lock_acquire() -> None:
    """1. 获取锁成功。"""
    lock = ReviewLock()
    ok = lock.acquire("d18-test-1", "rev-001")
    assert ok, "应获取锁成功"
    assert lock.holder("d18-test-1") == "rev-001"
    lock.release("d18-test-1", "rev-001")
    print("[PASS] 获取锁")


def test_lock_mutex() -> None:
    """2. 互斥：不同 reviewer → False。"""
    lock = ReviewLock()
    lock.acquire("d18-test-2", "rev-A")
    ok = lock.acquire("d18-test-2", "rev-B")
    assert ok is False, "不同 reviewer 应获取失败"
    assert lock.holder("d18-test-2") == "rev-A"
    lock.release("d18-test-2", "rev-A")
    print("[PASS] 互斥锁")


def test_lock_reentrant() -> None:
    """3. 可重入：同一 reviewer → True。"""
    lock = ReviewLock()
    lock.acquire("d18-test-3", "rev-X")
    ok = lock.acquire("d18-test-3", "rev-X")
    assert ok, "同一 reviewer 应可重入"
    lock.release("d18-test-3", "rev-X")
    print("[PASS] 可重入")


def test_lock_release() -> None:
    """4. 释放成功。"""
    lock = ReviewLock()
    lock.acquire("d18-test-4", "rev-R")
    ok = lock.release("d18-test-4", "rev-R")
    assert ok, "应释放成功"
    assert lock.holder("d18-test-4") is None
    print("[PASS] 释放锁")


def test_lock_release_wrong_owner() -> None:
    """5. 非持有者释放 → False。"""
    lock = ReviewLock()
    lock.acquire("d18-test-5", "rev-owner")
    ok = lock.release("d18-test-5", "rev-intruder")
    assert ok is False, "非持有者不应释放"
    assert lock.holder("d18-test-5") == "rev-owner"
    lock.release("d18-test-5", "rev-owner")
    print("[PASS] 非持有者释放失败")


def test_timeout_none() -> None:
    """6. 未超时 → none。"""
    now = time.time()
    assert check_review_timeout(now) == "none"
    assert check_review_timeout(now - 60) == "none"
    print("[PASS] 未超时")


def test_timeout_notify() -> None:
    """7. 4h → notify_backup。"""
    four_hours_ago = time.time() - 4.5 * 3600
    assert check_review_timeout(four_hours_ago) == "notify_backup"
    print("[PASS] 4h → 通知")


def test_timeout_24h() -> None:
    """8. 24h → timeout。"""
    one_day_ago = time.time() - 25 * 3600
    assert check_review_timeout(one_day_ago) == "timeout"
    print("[PASS] 24h → 超时")


def test_notify_backup() -> None:
    """9. 通知备用审核人写审计。"""
    audit_path = PROJECT_ROOT / "reports" / "review_audit.jsonl"
    count_before = 0
    if audit_path.exists():
        count_before = sum(1 for _ in audit_path.open(encoding="utf-8"))
    notify_backup_reviewer("d18-notify", {
        "risk_level": "high", "diagnosis": "需停机检查", "confidence": 0.80,
    })
    count_after = sum(1 for _ in audit_path.open(encoding="utf-8"))
    assert count_after > count_before, "审计记录应增加"
    print("[PASS] 通知备用审核人")


def test_validate_submitter() -> None:
    """10. 职责分离。"""
    assert validate_submitter("user-001", "user-001") is False, "同一人应禁止"
    assert validate_submitter("user-001", "user-002") is True, "不同人应允许"
    assert validate_submitter("user-001", "") is True, "无提交者应放行"
    print("[PASS] 职责分离")


def test_auto_timeout_resume() -> None:
    """11. 图内 auto_timeout_resume 超时降级。"""
    from langgraph.checkpoint.memory import InMemorySaver
    from app.graph import build as build_mod
    from app.graph.build import build_graph
    from app.graph.state import RootCause, Suggestion

    def _mock_diagnose(state):
        return {"diagnosis": "需立即停机检查", "confidence": 0.80,
                "risk_level": "high",
                "root_causes": [RootCause(cause="轴承磨损",
                                           citations=["c_001"])],
                "suggestions": [Suggestion(action="紧急停机",
                                           citations=["c_001"], risk="high")]}

    def _mock_analyze_sensor(state):
        return {"sensor_report": {"count": 50, "avg": 6.8, "max": 7.5,
                                  "trend": "up", "exceed_duration_ms": 12000}}

    def _mock_retrieve_evidence(state):
        from app.graph.state import EvidenceItem
        return {"evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损",
                                           score=0.9)]}

    def _mock_get_history(state):
        return {"work_orders": []}

    config = {"configurable": {"thread_id": "d18-auto"}}
    initial = {
        "alarm": {"alarm_id": "smoke-1", "device_id": "PUMP-A-01",
                  "metric": "vib_rms", "value": 7.1, "ts": 0},
        "thread_id": "d18-auto",
    }
    # 2026-10-22：本用例断言的是审核/幂等/trace/指标等**与形态无关**的语义，而打桩只覆盖
    # deterministic 链的 `diagnose`；默认 agent 形态会绕过 mock 去调真 LLM（慢且不确定）。
    # 故显式固定形态（agent 形态的等价验证见 tests/test_agent_diagnosis.py）。
    with patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
         patch.dict("os.environ", {"AUSCULT_DIAGNOSIS_MODE": "deterministic"}), \
         patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
         patch.object(build_mod, "get_history", _mock_get_history), \
         patch.object(build_mod, "diagnose", _mock_diagnose):
        graph = build_graph(InMemorySaver())
        graph.invoke(initial, config=config)
        # 确认挂起在 human_review
        st = graph.get_state(config)
        assert st.next and "human_review" in st.next
        # auto_timeout_resume 应自动降级
        result = auto_timeout_resume(graph, config, "d18-auto")
    assert result is not None, "auto_timeout_resume 应返回结果"
    assert result.get("report_id", "").startswith("RPT-")
    assert result.get("degrade_reason") == "review_timeout"
    assert result["human_review"]["status"] == "timeout"
    print(f"[PASS] auto_timeout_resume（report={result['report_id']}）")


def main() -> int:
    tests = [
        ("获取锁", test_lock_acquire),
        ("互斥锁", test_lock_mutex),
        ("可重入", test_lock_reentrant),
        ("释放锁", test_lock_release),
        ("非持有者释放", test_lock_release_wrong_owner),
        ("未超时", test_timeout_none),
        ("4h 通知", test_timeout_notify),
        ("24h 超时", test_timeout_24h),
        ("通知备用审核人", test_notify_backup),
        ("职责分离", test_validate_submitter),
        ("auto_timeout_resume", test_auto_timeout_resume),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    print(f"\n{'=' * 50}")
    print(f"D18 自测结果：{len(tests) - failures}/{len(tests)} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
