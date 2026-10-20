"""统一 LLM 客户端（P7 · Agent 化第一步：本地/云端单一出口）。

设计要点：
- **唯一出口**：产品运行态所有 LLM 调用（确定性诊断 / Agent 循环 / 云端兜底）
  都经本模块；原先分散在 nodes/diagnose.py（硬编码本地 Ollama）与
  router/cloud.py（硬编码云端）的两个调用点合并为同一传输实现。
- **OpenAI 兼容 tools 通道**：本地 Ollama 与云端（ModelScope，OpenAI 兼容）
  共用同一套 `tools` + `tool_choice=auto` 请求形态——该形态已在
  scripts/llm_adapter.py（`--transport tools`）双端实测，本客户端逐字沿用其
  载荷结构与 `tool_choice` 纪律（H5/ISS-027/R-V1-9：**禁用 "required"**，
  云端会静默返回空 tool_calls）。
- **异常契约与 nodes/diagnose.py 既有口径一致**：TimeoutError / ConnectionError /
  RuntimeError 三态，供上层走「重试 → 降级」既有路由，不引入新异常类型。
- **可测性**：`opener` 可注入（默认 urllib.request.urlopen），测试零网络。

对应交付物：docs/p7-design-agent-diagnosis-2026-10-19.md §三。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from . import config as cfg

#: tool_choice 唯一可用值（llm_adapter.DEFAULT_TOOL_CHOICE 同口径）
DEFAULT_TOOL_CHOICE = "auto"


@dataclass(slots=True)
class ToolCall:
    """一次工具调用（OpenAI 兼容归一后）。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatResult:
    """单次对话结果。"""

    model: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: float = 0.0
    error: str | None = None

    @property
    def tool_calls_missing(self) -> bool:
        """请求了 tools 但模型未产出调用（R-V1-3「静默退化」探针）。"""
        return not self.tool_calls


class OpenAICompatClient:
    """OpenAI 兼容 /v1/chat/completions 客户端（本地 Ollama 与云端共用）。

    参数:
        endpoint:  完整端点 URL（含 /v1/chat/completions）
        model:     模型名（云端 = env/cloud.json 的 model；本地 = Ollama 模型名）
        api_key:   云端 Bearer；本地为 None
        opener:    HTTP opener（测试注入假实现；默认 urllib.request.urlopen）
    """

    def __init__(self, *, endpoint: str, model: str, api_key: str | None = None,
                 temperature: float | None = None, max_tokens: int | None = None,
                 num_ctx: int | None = None, timeout: float | None = None,
                 role: str = cfg.ROLE_DIAGNOSE,
                 opener: Callable[..., Any] | None = None) -> None:
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.role = role
        self.temperature = cfg.LLM_TEMPERATURE if temperature is None else temperature
        self.max_tokens = cfg.LLM_MAX_TOKENS if max_tokens is None else max_tokens
        self.num_ctx = cfg.LLM_NUM_CTX if num_ctx is None else num_ctx
        self.timeout = cfg.llm_timeout(role) if timeout is None else timeout
        self._opener = opener or urllib.request.urlopen

    # ---------------------------------------------------------------- 请求

    def chat(self, messages: list[dict[str, Any]], *,
             tools: list[dict[str, Any]] | None = None,
             tool_choice: str = DEFAULT_TOOL_CHOICE,
             timeout: float | None = None) -> ChatResult:
        """一次对话。

        Args:
            messages: OpenAI 兼容消息列表（支持 role=tool 的工具结果回灌）
            tools:    OpenAI 兼容 tools 数组；None = 纯文本对话（确定性诊断）
            tool_choice: 仅 "auto"（H5 实测：云端 "required" 静默退化）

        Raises:
            TimeoutError / ConnectionError / RuntimeError（与 diagnose 既有契约一致）
        """
        if tool_choice != DEFAULT_TOOL_CHOICE:
            raise RuntimeError(
                f"tool_choice 仅支持 {DEFAULT_TOOL_CHOICE!r}（H5/ISS-027/R-V1-9）")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
            # Ollama 扩展参数（OpenAI 兼容端点忽略未知字段，非 Ollama 后端亦安全）
            "options": {"num_ctx": self.num_ctx, "temperature": self.temperature},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            self.endpoint, data=body, headers=headers, method="POST")
        try:
            with self._opener(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except TimeoutError:
            raise TimeoutError(f"LLM 调用超时（>{timeout or self.timeout}s）")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"LLM HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            if "timed out" in str(exc).lower():
                raise TimeoutError(f"LLM 调用超时（>{timeout or self.timeout}s）")
            raise ConnectionError(f"LLM 不可达: {exc}") from exc

        return self._parse(raw)

    # ---------------------------------------------------------------- 解析

    def _parse(self, raw: str) -> ChatResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LLM 响应不是合法 JSON: {exc.msg}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM 响应缺少 choices")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        # 云端 thinking 模型可能回传 reasoning_content（与 think 区块同理，
        # 由上层 diagnose._strip_think 统一剥离，此处不处理）
        calls = [_normalize_call(c) for c in (message.get("tool_calls") or [])]
        calls = [c for c in calls if c is not None]
        return ChatResult(model=self.model, content=content, tool_calls=calls)


def _normalize_call(item: Any) -> ToolCall | None:
    """OpenAI tool_calls 元素 → ToolCall。

    兼容 Ollama（arguments 可能已是 dict）与云端（arguments 为 JSON 字符串）。
    """
    if not isinstance(item, dict):
        return None
    fn = item.get("function") or {}
    name = fn.get("name") or item.get("name")
    if not name:
        return None
    raw_args = fn.get("arguments", item.get("arguments"))
    arguments: dict[str, Any] = {}
    if isinstance(raw_args, dict):
        arguments = raw_args
    elif isinstance(raw_args, str) and raw_args.strip():
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            arguments = parsed
        # 不可解析的参数串 → 空 dict，由工具层按「缺必填参数」处理（不静默放过）
    return ToolCall(id=str(item.get("id") or f"call-{name}"), name=str(name),
                    arguments=arguments)


# ---------------------------------------------------------------- 工厂

_clients: dict[tuple[str, str], OpenAICompatClient] = {}


def _load_cloud_settings() -> tuple[str, str, str]:
    """云端端点配置（复用 router/cloud.py 的单一加载器，避免两处口径漂移）。"""
    from ..router.cloud import load_cloud_config        # noqa: PLC0415 防循环导入

    cfgdata = load_cloud_config()
    endpoint = cfgdata.get("endpoint", "")
    model = cfgdata.get("model", "")
    api_key = cfgdata.get("api_key", "")
    missing = [k for k, v in (("endpoint", endpoint), ("model", model),
                              ("api_key", api_key)) if not v]
    if missing:
        raise RuntimeError(f"env/cloud.json 缺必填项: {missing}")
    return endpoint, model, api_key


def get_client(role: str = cfg.ROLE_DIAGNOSE) -> OpenAICompatClient:
    """按角色取客户端（进程内缓存；backend × model 组合各一实例）。

    role=diagnose → 确定性诊断模型；role=agent → Agent 循环模型。
    后端由 AUSCULT_LLM_BACKEND 决定；cloud 缺配置抛 RuntimeError
    （上层按 E_LLM_ERROR 走重试/降级）。
    """
    backend = cfg.llm_backend()
    if backend == "cloud":
        endpoint, model, api_key = _load_cloud_settings()
    else:
        endpoint, model, api_key = cfg.local_ollama_url(), cfg.local_model(role), None

    key = (backend, model)
    client = _clients.get(key)
    if client is None:
        client = OpenAICompatClient(endpoint=endpoint, model=model, api_key=api_key,
                                    role=role)
        _clients[key] = client
    return client


def get_cloud_client() -> OpenAICompatClient:
    """无条件取云端客户端（escalate 兜底路径专用：后端为 local 时也走云端）。"""
    endpoint, model, api_key = _load_cloud_settings()
    key = ("cloud", model)
    client = _clients.get(key)
    if client is None:
        client = OpenAICompatClient(endpoint=endpoint, model=model, api_key=api_key)
        _clients[key] = client
    return client


def reset_client_cache() -> None:
    """清空客户端缓存（测试/配置热切换用）。"""
    _clients.clear()


__all__ = [
    "ChatResult", "DEFAULT_TOOL_CHOICE", "OpenAICompatClient", "ToolCall",
    "get_client", "get_cloud_client", "reset_client_cache",
]
