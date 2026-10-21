"""本地后端冒烟：Agent 循环 × 本地 Ollama 连通性验证（P7 · 2026-10-21）。

**用途**：切回本地（`AUSCULT_LLM_BACKEND=local`）前后确认「链路是通的」——
即：本地模型能响应、tools 通道可用、工具能真实执行、收口结果能进诊断契约。
**不判质量**：7B 承担不了 Agent 协议的部分（工具调用/JSON 收口不稳定）属模型
能力问题（`ISS-060`），按所有者口径「先用 7B 验证连通性，质量待换硬件 + qwen3:32b」。

与 `scripts/smoke_agent_cloud.py` 的分工：
- cloud 版 = 完整端到端（真实 PG checkpointer + 审核 resume + 报告落库，耗云端额度）；
- 本地版 = 单节点连通性（只跑 `agent_diagnose`，零云端、零落库、秒级）。

用法：
    .venv\\Scripts\\python.exe scripts/smoke_agent_local.py
    .venv\\Scripts\\python.exe scripts/smoke_agent_local.py --model qwen3:32b
    .venv\\Scripts\\python.exe scripts/smoke_agent_local.py --device PUMP-A --steps 2

退出码：0 = LLM 可达（无论结论质量）；1 = 不可达/配置错误。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.graph.nodes import agent_diagnose as ad           # noqa: E402
from app.graph.state import AlarmEvent, DiagnosisState    # noqa: E402
from app.llm import config as llm_config                  # noqa: E402

#: 视为「链路不通」的错误码（其余如 E_JSON_PARSE 属模型能力问题，不影响连通性判定）
_FATAL_CODES = ("E_LLM_UNREACHABLE", "E_LLM_ERROR", "E_LLM_CONFIG")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地后端 Agent 连通性冒烟")
    parser.add_argument("--model", default="", help="覆盖 AUSCULT_LOCAL_MODEL_AGENT")
    parser.add_argument("--device", default="PUMP-A", help="告警设备编号（数据层口径）")
    parser.add_argument("--steps", type=int, default=2, help="max_steps（默认 2，够验通路）")
    args = parser.parse_args(argv)

    os.environ["AUSCULT_LLM_BACKEND"] = "local"
    os.environ["AUSCULT_AGENT_MAX_STEPS"] = str(max(1, min(args.steps, 16)))
    if args.model:
        os.environ["AUSCULT_LOCAL_MODEL_AGENT"] = args.model
    # 检索走 CPU 兜底：冒烟只验通路，不占显存、不因 CUDA 环境差异失败
    os.environ.setdefault("AUSCULT_RETRIEVAL_DEVICE", "cpu")

    print(f"backend={llm_config.llm_backend()} "
          f"model={llm_config.local_model(llm_config.ROLE_AGENT)} "
          f"sanitize_outbound={llm_config.sanitize_outbound()} "
          f"cloud_fallback={llm_config.cloud_fallback_enabled()} "
          f"url={llm_config.local_ollama_url()}")

    state = DiagnosisState(
        thread_id="thr-local-smoke",
        alarm=AlarmEvent(alarm_id="a-local-smoke", device_id=args.device,
                         metric="vib_rms", value=7.1, baseline=4.5,
                         severity="high", ts=0),
    )
    out = ad.agent_diagnose(state)

    codes = [e.get("code") for e in out.get("errors", [])]
    tools = [s.get("tool") for s in out.get("agent_steps", [])]
    print("errors =", json.dumps(out.get("errors", []), ensure_ascii=False)[:400])
    print("retry_count =", out.get("retry_count", 0))
    print("refusal =", out.get("refusal"))
    print("confidence =", out.get("confidence"))
    print("diagnosis =", (out.get("diagnosis") or "")[:160].replace("\n", " "))
    print("steps =", tools)

    reachable = not any(c in _FATAL_CODES for c in codes)
    # 工具是否被真实调用单独提示（7B 可能零工具直接收口 —— 连通但能力不足）
    print(f"\n[{'PASS' if reachable else 'FAIL'}] "
          f"{'LLM 可达' if reachable else 'LLM 不可达'}；"
          f"工具调用 {len([t for t in tools if t])} 次")
    return 0 if reachable else 1


if __name__ == "__main__":
    raise SystemExit(main())
