"""LLM 客户端配置（P7 · Agent 化第一步：统一客户端抽象）。

口径：
- **环境变量优先**；默认 **local + agent**（2026-10-21 所有者裁决把诊断形态转默认，
  回退 `AUSCULT_DIAGNOSIS_MODE=deterministic`）——
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
    """诊断段形态：**agent（默认，2026-10-21 所有者裁决）** | deterministic（固定编排）。

    切换依据：`EXP-P7-P1` 74/75 = 98.67%（六档首次全绿）+ 真机 smoke PASS +
    U1-D1/D2 脱敏落地 + ISS-059 轮内重试；**回退方式**：`AUSCULT_DIAGNOSIS_MODE=deterministic`。
    两种形态共用同一套下游契约（diagnosis/root_causes/suggestions/
    confidence/risk_level + 条件路由），切换不影响审核/幂等/降级链路。
    """
    mode = _env_str("AUSCULT_DIAGNOSIS_MODE", "agent").lower()
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


def cloud_timeout() -> float:
    """云端升级（`escalate_cloud` 兜底路径）单次调用超时（秒）。

    修复 ISS-058（2026-10-21）：原 `app/router/cloud.py::CLOUD_TIMEOUT_SEC`
    写死 20s（plan §六.4 口径），而云端实测单轮 **5.5–37s** → 兜底路径在云端
    稍慢时**必然**超时降级，且客户端断连**不等于**服务端停止计费（每次超时
    仍消耗一次云端额度）。现改为**角色化 + env 可调**：
      - `AUSCULT_CLOUD_TIMEOUT_SEC` 显式给出时以其为准（运维应急/压测）；
      - 否则取 `llm_timeout(ROLE_AGENT)`（默认 90s）——升级与 Agent 循环打的是
        同一个云端端点、同一量级延迟，不应存在两套超时预算。
    """
    raw = _env_str("AUSCULT_CLOUD_TIMEOUT_SEC", "")
    if raw:
        try:
            value = float(raw)
        except ValueError as exc:
            raise RuntimeError("AUSCULT_CLOUD_TIMEOUT_SEC 必须为数字") from exc
        if value <= 0:
            raise RuntimeError("AUSCULT_CLOUD_TIMEOUT_SEC 必须为正数")
        return value
    return llm_timeout(ROLE_AGENT)


LLM_TEMPERATURE = float(_env_str("AUSCULT_LLM_TEMPERATURE", "0"))
LLM_MAX_TOKENS = int(_env_str("AUSCULT_LLM_MAX_TOKENS", "2048"))
LLM_NUM_CTX = int(_env_str("AUSCULT_LLM_NUM_CTX", "8192"))


# ---------------------------------------------------------------- 出网脱敏口径（本地部署为准）

_SANITIZE_MODES = ("auto", "on", "off")


def sanitize_outbound() -> bool:
    """Agent 主路是否对出网内容做脱敏（设备号 hash + 工单 result 剥离）。

    **口径（2026-10-21 所有者裁决：合规以本地部署方案为准）**：
    目标形态是「本地模型为主 → 数据不出厂」，此时**不需要**对 Agent 主路脱敏；
    脱敏只在「数据真的出网」时有意义 —— 即 `AUSCULT_LLM_BACKEND=cloud`。
    故默认 `auto`：cloud 后端开、local 后端关，随后端翻转自动切换，无需运维记忆。

    - `auto`（默认）：按 `llm_backend()` 决定（cloud → 开，local → 关）；
    - `on`：强制开（云端测试期复现合规口径 / 需要按上云标准验收时）；
    - `off`：强制关（仅限本地或已获合规豁免的环境）。
    """
    mode = _env_str("AUSCULT_SANITIZE_OUTBOUND", "auto").lower()
    if mode not in _SANITIZE_MODES:
        raise RuntimeError(
            f"AUSCULT_SANITIZE_OUTBOUND 非法: {mode!r}（允许 {_SANITIZE_MODES}）")
    if mode == "on":
        return True
    if mode == "off":
        return False
    return llm_backend() == "cloud"


def cloud_fallback_enabled() -> bool:
    """本地主通道失败（重试耗尽）时，是否升级云端兜底。

    "云端降为兜底"要成立，必须覆盖两种失败语义：
      ① 结论置信度不足（既有 `confidence < 0.75 → escalate_cloud`）；
      ② **本地 LLM 不可达/超时**（`E_LLM_UNREACHABLE` 重试耗尽）—— 此前直接
         degrade，云端完全不介入（2026-10-21 核查发现的架构缺口）。
    `AUSCULT_CLOUD_FALLBACK=0` 可关闭（纯离线开发、或云端额度为零时）。
    后端已是 cloud 时该开关无意义（escalate 会空转跳过，不重复计费）。
    """
    return _env_str("AUSCULT_CLOUD_FALLBACK", "1") not in ("0", "false", "False", "off")


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
        # ISS-058：兜底路径超时（角色化，env AUSCULT_CLOUD_TIMEOUT_SEC 可覆盖）
        "cloud_timeout_sec": cloud_timeout(),
        # 2026-10-21：出网脱敏是否生效（本地形态关闭）+ 本地失败是否云端兜底
        "sanitize_outbound": sanitize_outbound(),
        "cloud_fallback": cloud_fallback_enabled(),
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS,
        "num_ctx": LLM_NUM_CTX,
    }
