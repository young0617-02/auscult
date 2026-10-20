"""云端 Agent 形态实跑冒烟（P7 · docs/p7-design-agent-diagnosis-2026-10-19.md）

链路：真实 PG checkpointer + 真实工具（TDengine / Milvus+Neo4j / PG）+ 真实云端 LLM
（Qwen/Qwen3.8-27B，env/cloud.json）——验证 Agent 循环在生产依赖下的端到端行为：
告警 → LLM 自主调只读工具取证 → 诊断 JSON → 置信度/风险 → [高风险挂起] → 审核 resume
→ finalize 定稿（report_id）。

用法：
    python scripts/smoke_agent_cloud.py                      # 完整链路（含审核 resume）
    python scripts/smoke_agent_cloud.py --no-resume          # 只跑到挂起/终态
    python scripts/smoke_agent_cloud.py --device-id PUMP-A --value 7.1 --baseline 4.5
    python scripts/smoke_agent_cloud.py --selftest           # 离线自检（mock，零网络零云端）

前置：交付栈 up（PG/Milvus/Neo4j/TDengine/Redis  healthy）；TDengine 已灌样本数据
（README §五；注意 ISS-050：解码器须 QoS 1 订阅，否则 broker 丢消息）；
env/cloud.json 就位。脚本自设 AUSCULT_DIAGNOSIS_MODE=agent / AUSCULT_LLM_BACKEND=cloud。

预算：完整链路 ≈ 3–6 次云端调用（含超时重试时更多），计入 budget:cloud:{date}。

2026-10-20 首跑实测（见 CHANGELOG）：诊断→挂起→审核→RPT 全链路 156–226s
（云端单轮 5.5–37s，U2 基线据此重定）；曾出现 1 次 >90s 超时→自循环重试→成功
（ISS-048 重试分支首次实战）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 脚本自设形态（不影响进程外默认值）
os.environ.setdefault("AUSCULT_DIAGNOSIS_MODE", "agent")
os.environ.setdefault("AUSCULT_LLM_BACKEND", "cloud")


def _run_live(device_id: str, value: float, baseline: float,
              severity: str, metric: str, do_resume: bool) -> int:
    from app.graph.build import build_graph
    from app.graph.checkpointer import build_checkpointer
    from app.graph.state import AlarmEvent

    alarm = AlarmEvent(
        alarm_id=f"smoke-agent-{int(time.time())}",
        device_id=device_id, metric=metric, value=value, baseline=baseline,
        severity=severity, ts=int(time.time() * 1000),
    )
    thread_id = f"thr-smoke-agent-{int(time.time())}"

    t0 = time.time()
    with build_checkpointer() as saver:
        graph = build_graph(saver)
        config = {"configurable": {"thread_id": thread_id}}
        graph.invoke({"thread_id": thread_id, "alarm": alarm.model_dump()}, config)
        snap = graph.get_state(config)
        next_nodes = tuple(snap.next or ())
        resumed = False
        if do_resume and "human_review" in next_nodes:
            from langgraph.types import Command
            graph.invoke(Command(resume={"action": "approved",
                                         "comment": "冒烟审核通过",
                                         "reviewer_id": "smoke-reviewer"}), config)
            resumed = True
            snap = graph.get_state(config)
        values = dict(snap.values or {})

    summary = {
        "thread_id": thread_id,
        "elapsed_s": round(time.time() - t0, 1),
        "next_before_resume": list(next_nodes),
        "resumed": resumed,
        "diagnosis": (values.get("diagnosis") or "")[:500],
        "confidence": values.get("confidence"),
        "risk_level": values.get("risk_level"),
        "report_id": values.get("report_id"),
        "degrade_reason": values.get("degrade_reason"),
        "evidence_n": len(values.get("evidence") or []),
        "sensor_count": (values.get("sensor_report") or {}).get("count"),
        "work_orders_n": len(values.get("work_orders") or []),
        "graph_paths_n": len(values.get("graph_paths") or []),
        "agent_steps": values.get("agent_steps"),
        "errors": values.get("errors"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))

    ok = bool(values.get("report_id")) if resumed else True
    verdict = "PASS" if ok and not (values.get("errors") or []) else "CHECK"
    print(f"[smoke] verdict={verdict}（resumed={resumed}）")
    return 0 if verdict == "PASS" else 1


def _selftest() -> int:
    """离线自检：mock 客户端 + 打桩工具，验证循环契约（零网络零云端）。"""
    from app.graph.nodes import agent_diagnose as ad
    from app.graph.state import AlarmEvent, DiagnosisState
    from app.llm.client import ChatResult, ToolCall

    final_json = json.dumps({
        "diagnosis": "自检：轴承磨损导致振动超标",
        "root_causes": [{"cause": "轴承磨损", "citations": ["c_001"],
                         "confidence_hint": 0.8}],
        "suggestions": [{"action": "检查润滑", "citations": ["c_001"], "risk": "low"}],
        "self_confidence": 0.75,
    }, ensure_ascii=False)

    class _Client:
        def __init__(self):
            self.turn = 0

        def chat(self, messages, *, tools=None, tool_choice="auto", timeout=None):
            self.turn += 1
            if self.turn == 1:
                assert tools, "首轮应带工具面"
                return ChatResult(model="mock", tool_calls=[
                    ToolCall(id="c1", name="search_knowledge",
                             arguments={"query": "振动限值"})])
            assert any(m.get("role") == "tool" for m in messages), "二轮应含工具回灌"
            return ChatResult(model="mock", content=final_json)

    orig_client, orig_exec = ad.get_client, ad.execute_tool
    try:
        ad.get_client = lambda role: _Client()
        ad.execute_tool = lambda name, args, *, alarm=None, thread_id=None: {
            "ok": True, "result": {"degraded": False,
                                   "items": [{"chunk_id": "c_001", "score": 0.9,
                                              "text": "限值"}]}}
        out = ad.agent_diagnose(DiagnosisState(
            thread_id="selftest", alarm=AlarmEvent(device_id="PUMP-A", metric="vib_rms")))
    finally:
        ad.get_client, ad.execute_tool = orig_client, orig_exec

    failures = []
    if out.get("diagnosis") != "自检：轴承磨损导致振动超标":
        failures.append("diagnosis 不符")
    if not out.get("root_causes") or out["root_causes"][0].citations != ["c_001"]:
        failures.append("root_causes/citations 不符")
    if not (0 < out.get("confidence", 0) < 1):
        failures.append("confidence 异常")
    if len(out.get("agent_steps") or []) != 1:
        failures.append("agent_steps 应为 1 条")
    if out.get("errors"):
        failures.append(f"不应有 errors: {out['errors']}")

    if failures:
        print("[smoke] selftest FAILED:", failures)
        return 1
    print("[smoke] selftest PASS（mock 客户端 + 打桩工具，循环契约完整）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="云端 Agent 形态实跑冒烟（P7）")
    ap.add_argument("--device-id", default="PUMP-A")
    ap.add_argument("--metric", default="vib_rms")
    ap.add_argument("--value", type=float, default=7.1)
    ap.add_argument("--baseline", type=float, default=4.5)
    ap.add_argument("--severity", default="high")
    ap.add_argument("--no-resume", action="store_true", help="不自动审核 resume")
    ap.add_argument("--selftest", action="store_true", help="离线自检（零网络）")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    return _run_live(args.device_id, args.value, args.baseline, args.severity,
                     args.metric, do_resume=not args.no_resume)


if __name__ == "__main__":
    sys.exit(main())
