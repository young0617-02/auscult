"""D20 可靠性测试：杀进程恢复 / 重复 resume / Redis 驱逐防护

对应 plan/Phase 3 §8.2 E7/E8/E9 + §6.5 Checkpoint 策略
M3.4 出口：重启恢复 + 无重复副作用 + 并发安全

三组共 12 项：
  A. 杀进程恢复（4 项）—— PG Checkpointer 持久化 + 新实例恢复
     A1. PG checkpoint 持久化：invoke 到 human_review 挂起 → PG 有记录
     A2. 新实例恢复：新 with 块 + 新 graph → get_state 挂起在 human_review
     A3. 状态完整：恢复 state 含 diagnosis/root_causes/suggestions/evidence
     A4. resume + 幂等报告：恢复后 resume(approved) → finalize → generate_report 仅 1 份

  B. 重复 resume / 并发安全（4 项）
     B1. ReviewLock 互斥：A 获锁，B 失败
     B2. 重复 resume 无副作用：已终结流程再 resume 不产生新报告
     B3. generate_report 幂等：重复调用 is_new=False
     B4. PG reports 无重复：相同 idempotency_key 仅 1 条

  C. Redis 驱逐防护 noeviction（4 项）
     C1. maxmemory-policy == noeviction（运行时 CONFIG GET）
     C2. appendonly == yes（AOF 持久化，保障重启恢复）
     C3. 无 TTL key 持久：写入无 TTL key → 确认存在（noeviction 不淘汰）
     C4. 有 TTL key 持久：lock:review:* key 存在 + TTL 未被 maxmemory 重置

用法：
  .venv\\Scripts\\python.exe scripts\\test_d20_reliability.py
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.state import (  # noqa: E402
    AlarmEvent,
    DiagnosisState,
    EvidenceItem,
    RootCause,
    Suggestion,
)


# ---------------------------------------------------------------- 辅助

def _mock_analyze_sensor(state):
    return {"sensor_report": {"count": 50, "avg": 6.8, "max": 7.5,
                              "trend": "up", "exceed_duration_ms": 12000}}


def _mock_retrieve_evidence(state):
    return {"evidence": [EvidenceItem(chunk_id="c_001", text="轴承磨损",
                                      score=0.9)]}


def _mock_get_history(state):
    return {"work_orders": []}


def _mock_diagnose(state):
    return {"diagnosis": "需立即停机检查轴承",
            "confidence": 0.80, "risk_level": "high",
            "root_causes": [RootCause(cause="轴承磨损",
                                       citations=["c_001"])],
            "suggestions": [Suggestion(action="紧急停机",
                                       citations=["c_001"], risk="high")]}


def _make_initial(thread_id: str) -> dict:
    return {
        "alarm": {"alarm_id": "d20-1", "device_id": "PUMP-A-01",
                  "metric": "vib_rms", "value": 7.1, "ts": 0},
        "thread_id": thread_id,
    }


def _build_and_invoke_to_interrupt(thread_id: str):
    """用 PG Checkpointer invoke 到 human_review 挂起，返回 (graph, config)。"""
    from app.graph import build as build_mod
    from app.graph.build import build_graph
    from app.graph.checkpointer import build_checkpointer

    config = {"configurable": {"thread_id": thread_id}}
    initial = _make_initial(thread_id)

    ctx = build_checkpointer()
    saver = ctx.__enter__()
    try:
        # 2026-10-22：本用例断言的是审核/幂等/trace/指标等**与形态无关**的语义，而打桩只覆盖
        # deterministic 链的 `diagnose`；默认 agent 形态会绕过 mock 去调真 LLM（慢且不确定）。
        # 故显式固定形态（agent 形态的等价验证见 tests/test_agent_diagnosis.py）。
        with patch.object(build_mod, "analyze_sensor", _mock_analyze_sensor), \
             patch.dict("os.environ", {"AUSCULT_DIAGNOSIS_MODE": "deterministic"}), \
             patch.object(build_mod, "retrieve_evidence", _mock_retrieve_evidence), \
             patch.object(build_mod, "get_history", _mock_get_history), \
             patch.object(build_mod, "diagnose", _mock_diagnose):
            graph = build_graph(saver)
            graph.invoke(initial, config=config)
        return graph, config, ctx
    except Exception:
        ctx.__exit__(None, None, None)
        raise


# =================================================================
# A. 杀进程恢复
# =================================================================

def test_a1_pg_checkpoint_persisted() -> None:
    """A1. PG checkpoint 持久化：挂起后 PG 有 checkpoint 记录。"""
    import psycopg

    thread_id = f"d20-a1-{uuid.uuid4().hex[:8]}"
    graph, config, ctx = _build_and_invoke_to_interrupt(thread_id)
    try:
        # 确认挂起
        st = graph.get_state(config)
        assert st.next and "human_review" in st.next, \
            f"应挂起在 human_review（next={st.next}）"

        # 查 PG checkpoint 表（DSN 随 API_PG_URL 走，避免绕开集成测试隔离）
        from app.api.config import POSTGRES_URL  # noqa: PLC0415

        conn = psycopg.connect(POSTGRES_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM checkpoints WHERE thread_id = %s",
                    (thread_id,))
                count = cur.fetchone()[0]
        finally:
            conn.close()
        assert count > 0, f"PG 应有 checkpoint 记录（thread={thread_id}）"
        print(f"[PASS] A1 PG checkpoint 持久化（{count} 条记录）")
    finally:
        ctx.__exit__(None, None, None)


def test_a2_new_instance_recover() -> None:
    """A2. 新实例恢复：新 with 块 + 新 graph → get_state 挂起在 human_review。"""
    from app.graph.checkpointer import build_checkpointer
    from app.graph.build import build_graph

    thread_id = f"d20-a2-{uuid.uuid4().hex[:8]}"
    # 第一次：invoke 到挂起
    graph1, config, ctx1 = _build_and_invoke_to_interrupt(thread_id)
    ctx1.__exit__(None, None, None)  # 关闭连接，模拟进程退出

    # 第二次：新连接、新 graph 实例（模拟重启）
    ctx2 = build_checkpointer()
    saver2 = ctx2.__enter__()
    try:
        graph2 = build_graph(saver2)
        st = graph2.get_state(config)
        assert st.next and "human_review" in st.next, \
            f"重启后应恢复到 human_review 挂起（next={st.next}）"
        print(f"[PASS] A2 新实例恢复（next={st.next}）")
    finally:
        ctx2.__exit__(None, None, None)


def test_a3_state_complete() -> None:
    """A3. 状态完整：恢复 state 含 diagnosis/root_causes/suggestions/evidence。"""
    from app.graph.checkpointer import build_checkpointer
    from app.graph.build import build_graph

    thread_id = f"d20-a3-{uuid.uuid4().hex[:8]}"
    graph1, config, ctx1 = _build_and_invoke_to_interrupt(thread_id)
    ctx1.__exit__(None, None, None)

    ctx2 = build_checkpointer()
    saver2 = ctx2.__enter__()
    try:
        graph2 = build_graph(saver2)
        st = graph2.get_state(config)
        vals = st.values
        assert vals.get("diagnosis") == "需立即停机检查轴承", \
            f"diagnosis 应恢复: {vals.get('diagnosis')}"
        assert len(vals.get("root_causes", [])) >= 1, "root_causes 不应为空"
        assert vals.get("root_causes")[0].cause == "轴承磨损"
        assert len(vals.get("suggestions", [])) >= 1, "suggestions 不应为空"
        assert vals.get("risk_level") == "high"
        assert len(vals.get("evidence", [])) >= 1, "evidence 不应为空"
        print("[PASS] A3 状态完整（diagnosis/root_causes/suggestions/evidence 均在）")
    finally:
        ctx2.__exit__(None, None, None)


def test_a4_resume_and_idempotent_report() -> None:
    """A4. 恢复后 resume(approved) → finalize → generate_report 仅 1 份。"""
    from langgraph.types import Command
    from app.graph.checkpointer import build_checkpointer
    from app.graph.build import build_graph
    from app.report.idempotency import generate_report, report_exists

    thread_id = f"d20-a4-{uuid.uuid4().hex[:8]}"
    graph1, config, ctx1 = _build_and_invoke_to_interrupt(thread_id)
    ctx1.__exit__(None, None, None)

    # 恢复 + resume
    ctx2 = build_checkpointer()
    saver2 = ctx2.__enter__()
    try:
        graph2 = build_graph(saver2)
        st = graph2.get_state(config)
        assert st.next and "human_review" in st.next

        resume = {"action": "approved", "comment": "审核通过",
                  "reviewer_id": "rev-d20-a4"}
        result = graph2.invoke(Command(resume=resume), config=config)
    finally:
        ctx2.__exit__(None, None, None)

    assert result.get("report_id", "").startswith("RPT-"), \
        f"应生成 report_id: {result.get('report_id')}"
    assert result["human_review"]["status"] == "approved"

    # 图外幂等写入
    write1 = generate_report(result)
    assert write1["is_new"] is True, "首次写入应为新建"
    write2 = generate_report(result)
    assert write2["is_new"] is False, "重复写入应返回既有"
    assert write1["report_id"] == write2["report_id"], "幂等应返回相同 report_id"
    assert report_exists(write1["idempotency_key"])
    print(f"[PASS] A4 resume + 幂等报告（{write1['report_id']}，"
          f"重复 is_new=False）")


# =================================================================
# B. 重复 resume / 并发安全
# =================================================================

def test_b1_review_lock_mutex() -> None:
    """B1. ReviewLock 互斥：A 获锁成功，B 失败。"""
    from app.review.lifecycle import ReviewLock

    thread_id = f"d20-b1-{uuid.uuid4().hex[:8]}"
    lock = ReviewLock()
    try:
        ok_a = lock.acquire(thread_id, "rev-A")
        assert ok_a, "A 应获锁成功"
        ok_b = lock.acquire(thread_id, "rev-B")
        assert ok_b is False, "B 应获锁失败（互斥）"
        assert lock.holder(thread_id) == "rev-A", "持有者应为 A"
        print("[PASS] B1 ReviewLock 互斥（A 成功，B 失败）")
    finally:
        lock.release(thread_id, "rev-A")


def test_b2_repeat_resume_no_side_effect() -> None:
    """B2. 重复 resume 无副作用：已终结流程再 resume 不产生新报告。"""
    from langgraph.types import Command
    from app.graph.checkpointer import build_checkpointer
    from app.graph.build import build_graph

    thread_id = f"d20-b2-{uuid.uuid4().hex[:8]}"
    graph, config, ctx = _build_and_invoke_to_interrupt(thread_id)
    try:
        # 第一次 resume
        resume1 = {"action": "approved", "comment": "同意",
                   "reviewer_id": "rev-b2-1"}
        result1 = graph.invoke(Command(resume=resume1), config=config)
        rid1 = result1.get("report_id", "")
        assert rid1.startswith("RPT-"), "第一次 resume 应出报告"

        # 流程已终结
        st_end = graph.get_state(config)
        assert not st_end.next, f"流程应已终结（next={st_end.next}）"

        # 第二次 resume（已终结，不应产生新副作用）
        resume2 = {"action": "approved", "comment": "再同意",
                   "reviewer_id": "rev-b2-2"}
        result2 = graph.invoke(Command(resume=resume2), config=config)
        rid2 = result2.get("report_id", "")
        assert rid2 == rid1, \
            f"重复 resume 不应产生新 report_id: {rid1} vs {rid2}"
        print(f"[PASS] B2 重复 resume 无副作用（{rid1} == {rid2}）")
    finally:
        ctx.__exit__(None, None, None)


def test_b3_generate_report_idempotent() -> None:
    """B3. generate_report 幂等：重复调用 is_new=False。"""
    from app.report.idempotency import generate_report

    state = {
        "thread_id": f"d20-b3-{uuid.uuid4().hex[:8]}",
        "risk_level": "low",
        "confidence": 0.85,
        "diagnosis": "正常",
        "root_causes": [RootCause(cause="x", citations=["c_001", "c_002"])],
        "suggestions": [Suggestion(action="检查", citations=["c_001"])],
        "escalate_cloud": False,
        "human_review": None,
        "degrade_reason": None,
        "errors": [],
    }
    first = generate_report(state)
    second = generate_report(state)
    assert first["report_id"] == second["report_id"], "幂等应返回相同 report_id"
    assert first["is_new"] is True, "首次应新建"
    assert second["is_new"] is False, "重复应 is_new=False"
    print(f"[PASS] B3 generate_report 幂等（{second['report_id']}）")


def test_b4_no_duplicate_reports() -> None:
    """B4. PG reports 无重复：相同 idempotency_key 仅 1 条。"""
    import psycopg
    from app.report.idempotency import generate_report

    thread_id = f"d20-b4-{uuid.uuid4().hex[:8]}"
    state = {
        "thread_id": thread_id,
        "risk_level": "medium",
        "confidence": 0.70,
        "diagnosis": "需关注",
        "root_causes": [RootCause(cause="磨损", citations=["c_010"])],
        "suggestions": [Suggestion(action="润滑", citations=["c_010"])],
        "escalate_cloud": False,
        "human_review": None,
        "degrade_reason": None,
        "errors": [],
    }
    # 连续调用三次
    generate_report(state)
    generate_report(state)
    result3 = generate_report(state)

    from app.api.config import POSTGRES_URL  # noqa: PLC0415

    conn = psycopg.connect(POSTGRES_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM reports WHERE idempotency_key = %s",
                (result3["idempotency_key"],))
            count = cur.fetchone()[0]
    finally:
        conn.close()
    assert count == 1, f"PG reports 应仅 1 条（实际 {count}）"
    print(f"[PASS] B4 PG 无重复报告（{result3['report_id']}，count={count}）")


# =================================================================
# C. Redis 驱逐防护 noeviction
# =================================================================

def _get_redis_client():
    """惰性 Redis 连接。"""
    import redis
    return redis.from_url(
        "redis://:auscult-dev-redis@127.0.0.1:6379/0",
        decode_responses=True, socket_timeout=2)


def test_c1_maxmemory_policy_noeviction() -> None:
    """C1. 运行时 maxmemory-policy == noeviction。"""
    client = _get_redis_client()
    config = client.config_get("maxmemory-policy")
    policy = config.get("maxmemory-policy", "")
    assert policy == "noeviction", \
        f"maxmemory-policy 应为 noeviction（实际 {policy}）"
    print(f"[PASS] C1 maxmemory-policy == noeviction（{policy}）")


def test_c2_appendonly_yes() -> None:
    """C2. AOF 持久化开启（appendonly == yes）。"""
    client = _get_redis_client()
    config = client.config_get("appendonly")
    aof = config.get("appendonly", "")
    assert aof == "yes", f"appendonly 应为 yes（实际 {aof}）"
    print(f"[PASS] C2 appendonly == yes（AOF 持久化开启）")


def test_c3_no_ttl_key_persists() -> None:
    """C3. 无 TTL key 持久：noeviction 下不被淘汰。"""
    client = _get_redis_client()
    key = "d20:c3:nottl"
    client.delete(key)
    client.set(key, "persistent_value")  # 无 TTL
    # 确认 key 存在
    assert client.get(key) == "persistent_value"
    assert client.ttl(key) == -1, "无 TTL key 的 TTL 应为 -1（永不过期）"
    # noeviction 语义：内存满时写入报错，不会淘汰此 key
    # 验证 key 仍存在（未被淘汰）
    assert client.get(key) == "persistent_value"
    client.delete(key)
    print("[PASS] C3 无 TTL key 持久（noeviction 不淘汰）")


def test_c4_ttl_key_not_evicted() -> None:
    """C4. 有 TTL key（lock:review:* 模式）不被 maxmemory 淘汰。

    noeviction 保证：内存满时写入报错，而非淘汰已有 key。
    lock:review:* key 的 TTL 由业务设置（25h），不会被 maxmemory 重置或删除。
    """
    client = _get_redis_client()
    key = "lock:review:d20-c4-test"
    client.delete(key)
    # 模拟审核锁写入（SETNX + EXPIRE 25h）
    ok = client.set(key, "rev-c4", nx=True, ex=900)
    assert ok, "应写入成功"
    ttl_before = client.ttl(key)
    assert 0 < ttl_before <= 900, f"TTL 应在 (0, 900]（实际 {ttl_before}）"
    # noeviction 下，key 不会被 maxmemory 淘汰
    # 验证 key 仍在、TTL 未被重置
    assert client.get(key) == "rev-c4"
    ttl_after = client.ttl(key)
    assert abs(ttl_before - ttl_after) <= 2, \
        f"TTL 不应被 maxmemory 重置（before={ttl_before}, after={ttl_after}）"
    client.delete(key)
    print(f"[PASS] C4 有 TTL key 不被淘汰（TTL {ttl_before}→{ttl_after}）")


# =================================================================
# 主入口
# =================================================================

def main() -> int:
    tests = [
        # A. 杀进程恢复
        ("A1 PG checkpoint 持久化", test_a1_pg_checkpoint_persisted),
        ("A2 新实例恢复", test_a2_new_instance_recover),
        ("A3 状态完整", test_a3_state_complete),
        ("A4 resume + 幂等报告", test_a4_resume_and_idempotent_report),
        # B. 重复 resume / 并发安全
        ("B1 ReviewLock 互斥", test_b1_review_lock_mutex),
        ("B2 重复 resume 无副作用", test_b2_repeat_resume_no_side_effect),
        ("B3 generate_report 幂等", test_b3_generate_report_idempotent),
        ("B4 PG reports 无重复", test_b4_no_duplicate_reports),
        # C. Redis 驱逐防护
        ("C1 maxmemory-policy=noeviction", test_c1_maxmemory_policy_noeviction),
        ("C2 appendonly=yes", test_c2_appendonly_yes),
        ("C3 无 TTL key 持久", test_c3_no_ttl_key_persists),
        ("C4 有 TTL key 不被淘汰", test_c4_ttl_key_not_evicted),
    ]
    failures = 0
    for name, test_fn in tests:
        try:
            test_fn()
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            failures += 1
    total = len(tests)
    print(f"\n{'=' * 50}")
    print(f"D20 可靠性测试结果：{total - failures}/{total} PASS"
          + (f"，{failures} 项失败" if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
