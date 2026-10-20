"""LLM 客户端配置（P7 · Agent 化第一步：统一客户端抽象）。

口径：
- **环境变量优先，默认值保持既有行为不变**（local + deterministic）——
  离线测试/回归零网络调用（tests/ 全量离线纪律，ISS-030 回归套件前提）。
- 现阶段（2026-10-19 起）测试开发形态（用户三项判决之②，云端临时承载）：

    $env:AUSCULT_LLM_BACKEND="cloud"      # LLM 后端走云端（env/cloud.json）
    $env:AUSCULT_DIAGNOSIS_MODE="agent"   # 诊断段切 Agent 循环（LLM 自主调工具）

- 后期切回本地（换硬件 + qwen3:32b 后，用户判决之①）：

    $env:AUSCULT_LLM_BACKEND="local"
    $env:AUSCULT_LOCAL_MODEL_AGENT="qwen3:32b"      # Agent 循环（工具调用角色）
    $env:AUSCULT_LOCAL_MODEL_DIAGNOSE="qwen3:32b"   # 确定性诊断（原 deepseek-r1:7b 角色）

  此时云端自动降为 escalate 兜底路径（app/router/cloud.py 原语义不变）。

设计依据：docs/p7-design-agent-diagnosis-2026-10-19.md（三项判决记录 + 切换 Runbook）。
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- 角色

#: diagnose 角色 = 确定性诊断（原 nodes/diagnose.py，deepseek-r1:7b）
ROLE_DIAGNOSE = "diagnose"
#: agent 角色 = Agent 循环（工具调用规划 + 诊断，原 qwen2.5:7b 职责）
ROLE_AGENT = "agent"

_BACKENDS = ("local", "cloud")
_MODES = ("deterministic", "agent")


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def llm_backend() -> str:
    """当前 LLM 后端：local（宿主 Ollama，默认）| cloud（env/cloud.json）。

    默认 local = 既有行为不变；测试开发期显式设 cloud。
    """
    backend = _env_str("AUSCULT_LLM_BACKEND", "local").lower()
    if backend not in _BACKENDS:
        raise RuntimeError(
            f"AUSCULT_LLM_BACKEND 非法: {backend!r}（允许 {_BACKENDS}）")
    return backend


def diagnosis_mode() -> str:
    """诊断段形态：deterministic（固定编排，默认）| agent（LLM 自主工具循环）。

    两种形态共用同一套下游契约（diagnosis/root_causes/suggestions/
    confidence/risk_level + 条件路由），切换不影响审核/幂等/降级链路。
    """
    mode = _env_str("AUSCULT_DIAGNOSIS_MODE", "deterministic").lower()
    if mode not in _MODES:
        raise RuntimeError(
            f"AUSCULT_DIAGNOSIS_MODE 非法: {mode!r}（允许 {_MODES}）")
    return mode


def agent_max_steps() -> int:
    """Agent 循环单次诊断的最大工具调用轮数（混合形态方案④：拆单工具多次调用）。

    默认 4 = plan/p0-design-m02-hybrid-form.md 的 max_steps≤4 口径。
    """
    try:
        steps = int(_env_str("AUSCULT_AGENT_MAX_STEPS", "4"))
    except ValueError as exc:
        raise RuntimeError("AUSCULT_AGENT_MAX_STEPS 必须为整数") from exc
    if steps < 1 or steps > 16:
        raise RuntimeError("AUSCULT_AGENT_MAX_STEPS 必须在 1–16 之间")
    return steps


# ---------------------------------------------------------------- 本地后端（宿主 Ollama）

LOCAL_OLLAMA_URL = _env_str(
    "AUSCULT_LOCAL_OLLAMA_URL", "http://127.0.0.1:11434/v1/chat/completions")

#: 各角色默认本地模型（后期统一指向 qwen3:32b；单模型双角色，见 ADR-001 §五 备选重评）
LOCAL_MODEL_DIAGNOSE = _env_str("AUSCULT_LOCAL_MODEL_DIAGNOSE", "deepseek-r1:7b")
LOCAL_MODEL_AGENT = _env_str("AUSCULT_LOCAL_MODEL_AGENT", "qwen2.5:7b")


def local_model(role: str = ROLE_DIAGNOSE) -> str:
    """按角色取本地模型名（函数级读取，测试可 monkeypatch env）。"""
    if role == ROLE_AGENT:
        return _env_str("AUSCULT_LOCAL_MODEL_AGENT", LOCAL_MODEL_AGENT)
    return _env_str("AUSCULT_LOCAL_MODEL_DIAGNOSE", LOCAL_MODEL_DIAGNOSE)


def local_ollama_url() -> str:
    return _env_str("AUSCULT_LOCAL_OLLAMA_URL", LOCAL_OLLAMA_URL)


# ---------------------------------------------------------------- 通用推理参数

def llm_timeout(role: str = ROLE_DIAGNOSE) -> float:
    """单次 LLM 调用超时（秒）。

    - diagnose 角色默认 30（= nodes/diagnose.py 原 TIMEOUT_SEC，本地 deepseek 口径）；
    - agent 角色默认 90——**2026-10-20 云端实跑实测**：云端 Qwen3.8-27B 带
      tools 通道 + 完整工具面 prompt 时单轮 5.5–23s（多工具并行轮更慢），
      30s 预算会误杀正常调用并触发整套重试（成本 ×3）。见设计文档 §六 U2。
    两者均可被 env 覆盖。
    """
    env_name = ("AUSCULT_LLM_TIMEOUT_AGENT_SEC" if role == ROLE_AGENT
                else "AUSCULT_LLM_TIMEOUT_SEC")
    default = 90.0 if role == ROLE_AGENT else 30.0
    try:
        return float(_env_str(env_name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{env_name} 必须为数字") from exc


LLM_TEMPERATURE = float(_env_str("AUSCULT_LLM_TEMPERATURE", "0"))
LLM_MAX_TOKENS = int(_env_str("AUSCULT_LLM_MAX_TOKENS", "2048"))
LLM_NUM_CTX = int(_env_str("AUSCULT_LLM_NUM_CTX", "8192"))


def describe() -> dict:
    """配置快照（健康检查/审计用，不含密钥）。"""
    return {
        "backend": llm_backend(),
        "diagnosis_mode": diagnosis_mode(),
        "agent_max_steps": agent_max_steps(),
        "local_url": local_ollama_url(),
        "local_model_diagnose": local_model(ROLE_DIAGNOSE),
        "local_model_agent": local_model(ROLE_AGENT),
        "timeout_sec": llm_timeout(ROLE_DIAGNOSE),
        "timeout_agent_sec": llm_timeout(ROLE_AGENT),
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
        "num_ctx": LLM_NUM_CTX,
    }
