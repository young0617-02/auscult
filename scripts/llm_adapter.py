"""LLM 统一适配层（V1 · T2.3）

对应交付物：`Phase 0 详细开发计划（D1-D10 可执行版）.md` §三 D2–D3 · T2.3
判据依据：`reports/v1-report.md` §3.4

职责（单一入口，两个模型走同一条路径）：
  1. 从 `schemas/tools_v1.json` **程序化注入**工具定义，禁止手抄（防止提示词与 Schema 漂移）；
  2. 从提示词文件（默认 `prompts/tool_call_prompt_v1.md`，可用构造参数/`--prompt` 覆盖）
     抽取 System Prompt 与**该文件中的全部** few-shot 示例（v1 = 3 条，v2 = 8 条，条数由文件决定）；
  3. 走 **OpenAI 兼容 `/v1/chat/completions`** 发起请求；
  4. **统一剥离 `think`**（唯一剥离点，防止两模型口径不一致，对应 R-V1-1）；
  5. **显式标记 `tool_calls` 缺失**：置位 `AdapterResult.tool_calls_missing = True` 并落盘，
     判分器据此记为「格式退化」（应对 Ollama 静默退化，对应 R-V1-3）。
     `ToolCallsMissingError` 供调用方按需 `raise`；**默认路径不抛异常**，以免单条失败中断整批实验。
     此类失败必须单独计数，不得静默记为「工具名错」。

设计约束：
  - 仅用标准库（`urllib`），不引入第三方 HTTP 依赖，保证在裸 Python 3.12 下可运行；
  - 实验固定参数写死为默认值，并在运行开始打印，防止静默漂移（见 prompt v1 §三）。

自检：`python scripts/llm_adapter.py --selftest`
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 路径与常量

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "tools_v1.json"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "tool_call_prompt_v1.md"

# ★ 实验固定值（prompt v1 §三 写死；任何改动必须升 prompt 版本并新开 experiment_id）
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 42
DEFAULT_NUM_CTX = 8192
DEFAULT_TOP_P = 1.0
DEFAULT_MAX_TOKENS = 1024
DEFAULT_STREAM = False

DEFAULT_ENDPOINT = "http://127.0.0.1:11434/v1/chat/completions"

# ★ 工具调用通道的 tool_choice（H5 / ISS-027 / R-V1-9）：
#   "auto" = 唯一可用值。允许模型自行决定是否调用工具（含"应拒绝"用例的正常拒绝行为）。
# ⚠️ 实测（2026-10-05，ModelScope Qwen/Qwen3.8-27B，3 条用例）：
#   `tool_choice="required"` **不被支持** —— HTTP 200 但**正文与 tool_calls 均为空**
#   （3/3 复现），即静默降级而非报错。**故不得使用 "required"**：
#   其一它会伪装成"格式退化"污染指标；其二若被支持还会强制调用、破坏"应拒绝"判据。
#   保留本常量以便 H5 重测时固定口径（`run_v1 --transport tools` 一律用 "auto"）。
DEFAULT_TOOL_CHOICE = "auto"

# 剥离 think 区块的三种形态（标签字面量在此以转义形式书写，避免被上游文本管线改写）：
#   ① 成对标签：think 开标记 + 闭标记（或 thinking 标签对）
#   ② DeepSeek-R1 特殊 token：开标记 + end-of-thinking 特殊 token
#   ③ 未闭合：max_tokens 打满导致闭标记缺失，此时从开标记一直剥到结尾
_T_OPEN = "<" + "think" + ">"
_T_CLOSE = "<" + "/" + "think" + ">"
_T_OPEN_LONG = "<" + "thinking" + ">"
_T_CLOSE_LONG = "<" + "/" + "thinking" + ">"
R1_END_TOKEN = "<｜end▁of▁thinking｜>"

THINK_BLOCK_RE = re.compile(
    "(" + _T_OPEN + "|" + _T_OPEN_LONG + ")(.*?)(?:" + _T_CLOSE + "|" + _T_CLOSE_LONG + "|"
    + re.escape(R1_END_TOKEN) + ")",
    re.S,
)
UNCLOSED_THINK_RE = re.compile("(" + _T_OPEN + "|" + _T_OPEN_LONG + ")(.*)$", re.S)


class ToolCallsMissingError(RuntimeError):
    """Ollama 静默退化：HTTP 200 但响应里既没有 tool_calls、也没有可解析的工具调用文本。

    对应 R-V1-3。此类失败必须记为「格式退化」（`judge_tools.FAIL_DEGRADED`），
    **不得**记为「工具选择错误」。

    注意：本适配层默认**只置位** `AdapterResult.tool_calls_missing`，不主动抛出；
    调用方若需要"缺失即中断"的语义，自行 `raise ToolCallsMissingError(...)`。
    """


# ---------------------------------------------------------------- 数据结构


@dataclass
class ToolCall:
    """一次工具调用。`arguments` 为解析后的 dict；解析失败时为 None。"""

    name: str
    arguments: dict[str, Any] | None
    raw_arguments: str
    arguments_parse_error: str | None = None


@dataclass
class AdapterResult:
    """一次请求的完整结果，字段即原始落盘（raw JSONL）的骨架。"""

    model: str
    content_raw: str                      # 未剥离 think 的正文
    content_clean: str                    # 已剥离 think 的正文
    think_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_calls_missing: bool = False      # True = 触发 R-V1-3 静默退化
    latency_ms: float = 0.0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    think_tokens: int | None = None
    token_source: str = "usage"           # usage | char_fallback | none
    finish_reason: str | None = None
    http_status: int | None = None
    error: str | None = None

    def to_raw(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "content_raw": self.content_raw,
            "content_clean": self.content_clean,
            "think_text": self.think_text,
            "tool_calls": [
                {
                    "name": c.name,
                    "arguments": c.arguments,
                    "raw_arguments": c.raw_arguments,
                    "arguments_parse_error": c.arguments_parse_error,
                }
                for c in self.tool_calls
            ],
            "tool_calls_missing": self.tool_calls_missing,
            "latency_ms": round(self.latency_ms, 3),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "think_tokens": self.think_tokens,
            "token_source": self.token_source,
            "finish_reason": self.finish_reason,
            "http_status": self.http_status,
            "error": self.error,
        }


# ---------------------------------------------------------------- 提示词装配

_FENCE_RE = re.compile(r"```(?:text|json)?\n(.*?)```", re.S)
_TOOL_CALL_MARKER_RE = re.compile(r"^\((tool_call(?:\s+\d+)?)\)\s*$", re.I)
_JSON_DECODER = json.JSONDecoder()


def load_tools(schema_path: Path = SCHEMA_PATH) -> list[dict[str, Any]]:
    """读取 Schema v1 并转换为 OpenAI 兼容的 `tools` 数组。"""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    tools: list[dict[str, Any]] = []
    for tool in schema["tools"]:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
        )
    return tools


def tools_json_for_prompt(schema_path: Path = SCHEMA_PATH) -> str:
    """序列化 `tools[]` 供 `{{TOOLS_JSON_SCHEMA}}` 注入（不做任何人工删改）。"""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return json.dumps(schema["tools"], ensure_ascii=False, indent=2)


def load_system_prompt(prompt_path: Path = PROMPT_PATH, schema_path: Path = SCHEMA_PATH) -> str:
    """抽取 prompt v1 §一 的 System Prompt 正文并注入工具定义。"""
    text = prompt_path.read_text(encoding="utf-8")
    m = re.search(r"##\s*一、System Prompt.*?```text\n(.*?)```", text, re.S)
    if not m:
        raise ValueError(f"未能在 {prompt_path} 中定位 System Prompt 代码块")
    system = m.group(1).strip()
    if "{{TOOLS_JSON_SCHEMA}}" not in system:
        raise ValueError("System Prompt 中缺少 {{TOOLS_JSON_SCHEMA}} 占位符")
    return system.replace("{{TOOLS_JSON_SCHEMA}}", tools_json_for_prompt(schema_path))


def _extract_json_objects(blob: str) -> list[dict[str, Any]]:
    """从一段文本中依次抽取所有顶层 JSON 对象（容忍对象之间夹带说明文字）。"""
    objects: list[dict[str, Any]] = []
    idx = 0
    while idx < len(blob):
        start = blob.find("{", idx)
        if start < 0:
            break
        try:
            obj, end = _JSON_DECODER.raw_decode(blob[start:])
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        idx = start + end
    return objects


def load_fewshot(prompt_path: Path = PROMPT_PATH) -> list[dict[str, str]]:
    """抽取 prompt v1 §二 的 3 条 few-shot，转为 user/assistant 消息对。

    assistant 侧若含工具调用，统一序列化为 JSON 数组字符串
    （单次调用也包成数组，保证判分侧只需支持一种形态）。
    """
    text = prompt_path.read_text(encoding="utf-8")
    section = re.search(r"##\s*二、Few-shot.*?(?=\n##\s*三、)", text, re.S)
    if not section:
        raise ValueError(f"未能在 {prompt_path} 中定位 Few-shot 章节")

    messages: list[dict[str, str]] = []
    for block in re.findall(r"###\s*示例.*?```\n(.*?)```", section.group(0), re.S):
        user_part = re.search(r"user:\s*(.*?)(?=\n\s*assistant:)", block, re.S)
        asst_part = re.search(r"assistant:\s*(.*)", block, re.S)
        if not user_part or not asst_part:
            continue
        user_text = user_part.group(1).strip()

        rest = "\n".join(
            line for line in asst_part.group(1).splitlines()
            if not _TOOL_CALL_MARKER_RE.match(line.strip())
        ).strip()
        calls = _extract_json_objects(rest)
        asst_text = json.dumps(calls, ensure_ascii=False) if calls else rest

        messages.append({"role": "user", "content": user_text})
        messages.append({"role": "assistant", "content": asst_text})
    return messages


def build_messages(
    user_input: str,
    history: list[dict[str, str]] | None = None,
    fewshot: bool = True,
    system_prompt: str | None = None,
    prompt_path: Path | None = None,
) -> list[dict[str, str]]:
    """装配完整 messages：system → few-shot → 多轮上下文 → 本轮输入。

    ★`prompt_path` 决定 **few-shot 的来源文件**（未显式传 `system_prompt` 时也决定 system 来源）。
    历史缺陷：此前 `load_fewshot()` 恒用默认 `PROMPT_PATH`（v1），导致 `--prompt` 指向 v2/step
    时，**system 用了新提示词、few-shot 却仍是 v1 的 3 条**——「few-shot 3→8 扩容」实际未生效。
    现由调用方传入实际提示词路径，保证 system 与 few-shot 同源。
    """
    source = prompt_path or PROMPT_PATH
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt or load_system_prompt(source)}
    ]
    if fewshot:
        messages.extend(load_fewshot(source))
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    return messages


# ---------------------------------------------------------------- think 剥离


def strip_think(text: str) -> tuple[str, str]:
    """剥离 think 区块，返回 (干净正文, think 原文)。

    ★ 顺序不可颠倒：必须先剥离再判 JSON，否则思维链里的 JSON 会被误判为工具调用（R-V1-1）。
    """
    if not text:
        return "", ""
    thinks: list[str] = []

    def _keep(m: re.Match[str]) -> str:
        thinks.append(m.group(2))
        return ""

    clean = THINK_BLOCK_RE.sub(_keep, text)
    m = UNCLOSED_THINK_RE.search(clean)          # 截断的 think（max_tokens 打满）
    if m:
        thinks.append(m.group(2))
        clean = clean[: m.start()]
    return clean.strip(), "\n".join(t.strip() for t in thinks).strip()


def _estimate_tokens(text: str) -> int:
    """字符数近似 token 数（仅在 provider 未回传 token 用量时作为兜底口径）。"""
    return len(text)


def parse_tool_calls(message: dict[str, Any], clean_text: str) -> list[ToolCall]:
    """解析 tool_calls；若标准字段缺失，退化为从正文 JSON 中还原（并显式标记来源）。"""
    calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        fn = raw.get("function") or {}
        raw_args = fn.get("arguments") or ""
        parsed, err = _parse_arguments(raw_args)
        calls.append(ToolCall(name=fn.get("name") or "", arguments=parsed,
                              raw_arguments=raw_args, arguments_parse_error=err))
    if calls:
        return calls

    # 退化路径：部分实现把调用写在正文里。此路径必须在指标中单列，不得与标准路径混算。
    for obj in _extract_json_objects(clean_text):
        if "name" in obj and "arguments" in obj:
            args = obj["arguments"]
            calls.append(ToolCall(name=str(obj["name"]),
                                  arguments=args if isinstance(args, dict) else None,
                                  raw_arguments=json.dumps(args, ensure_ascii=False),
                                  arguments_parse_error=None if isinstance(args, dict)
                                  else "arguments 不是 JSON 对象"))
    return calls


def _parse_arguments(raw_args: Any) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(raw_args, dict):
        return raw_args, None
    if not isinstance(raw_args, str) or not raw_args.strip():
        return None, "arguments 为空"
    try:
        parsed = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        return None, f"arguments 不是合法 JSON：{exc.msg}"
    if not isinstance(parsed, dict):
        return None, "arguments 不是 JSON 对象"
    return parsed, None


# ---------------------------------------------------------------- 适配器主体


class LLMAdapter:
    """两模型共用的唯一入口。"""

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        temperature: float = DEFAULT_TEMPERATURE,
        seed: int = DEFAULT_SEED,
        num_ctx: int = DEFAULT_NUM_CTX,
        top_p: float = DEFAULT_TOP_P,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout_s: float = 300.0,
        api_key: str | None = None,
        schema_path: Path = SCHEMA_PATH,
        prompt_path: Path = PROMPT_PATH,
        grammar: dict | str | None = None,
        structured_output: bool = False,
        tool_choice: str = DEFAULT_TOOL_CHOICE,
    ) -> None:
        self.endpoint = endpoint
        self.temperature = temperature
        self.seed = seed
        self.num_ctx = num_ctx
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s
        self.api_key = api_key
        self.schema_path = schema_path
        self.prompt_path = prompt_path
        self.grammar = grammar                       # 约束解码 JSON Schema（由 gbnf_grammar 生成）
        self.structured_output = structured_output   # 云端约束解码走 OpenAI response_format json_schema
        self.tool_choice = tool_choice               # tools 通道的 tool_choice（H5：云端可用 required）
        self.tools = load_tools(schema_path)
        self.system_prompt = load_system_prompt(prompt_path, schema_path)

    def describe(self) -> str:
        """打印实验固定参数，防止静默漂移。"""
        return (
            f"adapter   : {self.endpoint}\n"
            f"temperature={self.temperature} seed={self.seed} num_ctx={self.num_ctx} "
            f"top_p={self.top_p} max_tokens={self.max_tokens} stream={DEFAULT_STREAM}\n"
            f"tools     : {len(self.tools)} 个（来自 {self.schema_path.name}，程序化注入）\n"
            f"prompt    : {self.prompt_path}\n"
            f"constrain : {'云端约束解码（response_format=json_schema<' +
                            self.schema_path.name + '>）'
                           if (self.grammar and self.structured_output)
                           else ('Ollama 原生约束解码（/api/chat format=<' +
                                 self.schema_path.name + '>）'
                                 if self.grammar else '关闭（OpenAI 兼容 tools 引导）')}\n"
            f"transport : tools + tool_choice={self.tool_choice}"
        )

    def chat(self, messages: list[dict[str, str]], model: str,
             use_tools: bool = True) -> AdapterResult:
        """发起一次请求并返回结构化结果。

        三种模式（互斥）：
          - 约束解码 + 结构化输出（云端 response_format json_schema）→ `_chat_openai_structured`
          - 约束解码 + Ollama 原生 `/api/chat` + `format` → `_chat_native`
          - 默认 → OpenAI 兼容 `/v1/chat/completions` + tools 引导
        """
        if self.grammar and self.structured_output:
            return self._chat_openai_structured(messages, model)
        if self.grammar:
            return self._chat_native(messages, model)
        return self._chat_openai(messages, model, use_tools)

    def _chat_openai(self, messages: list[dict[str, str]], model: str,
                     use_tools: bool = True) -> AdapterResult:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "stream": DEFAULT_STREAM,
            "seed": self.seed,
            # Ollama 扩展参数（OpenAI 兼容端点会忽略未知字段，非 Ollama 后端亦安全）
            "options": {"num_ctx": self.num_ctx, "seed": self.seed, "temperature": self.temperature},
        }
        if use_tools:
            payload["tools"] = self.tools
            payload["tool_choice"] = self.tool_choice

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return AdapterResult(model=model, content_raw="", content_clean="", think_text="",
                                 latency_ms=(time.perf_counter() - started) * 1000,
                                 http_status=exc.code, error=f"HTTP {exc.code}: {detail[:500]}")
        except Exception as exc:                                  # noqa: BLE001 - 网络层兜底
            return AdapterResult(model=model, content_raw="", content_clean="", think_text="",
                                 latency_ms=(time.perf_counter() - started) * 1000,
                                 error=f"{type(exc).__name__}: {exc}")

        latency_ms = (time.perf_counter() - started) * 1000
        return self._parse_response(model, raw, latency_ms, status)

    def _parse_response(self, model: str, raw: str, latency_ms: float,
                        status: int) -> AdapterResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return AdapterResult(model=model, content_raw=raw, content_clean="", think_text="",
                                 latency_ms=latency_ms, http_status=status,
                                 error=f"响应不是合法 JSON：{exc.msg}")

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content_raw = message.get("content") or ""
        # Ollama/云端对 thinking 模型可能单独回传 thinking 字段（云端 Qwen3 为 reasoning_content），
        # 与正文 think 区块合并统计
        thinking_field = message.get("thinking") or message.get("reasoning_content") or ""

        content_clean, think_text = strip_think(content_raw)
        if thinking_field:
            think_text = (think_text + "\n" + thinking_field).strip()

        calls = parse_tool_calls(message, content_clean)
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        completion_tokens = usage.get("completion_tokens")
        think_tokens = details.get("reasoning_tokens")

        if think_tokens is None and think_text:
            think_tokens = _estimate_tokens(think_text)
            token_source = "char_fallback"
        elif completion_tokens is not None:
            token_source = "usage"
        else:
            token_source = "none"

        return AdapterResult(
            model=model,
            content_raw=content_raw,
            content_clean=content_clean,
            think_text=think_text,
            tool_calls=calls,
            tool_calls_missing=not calls,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=completion_tokens,
            think_tokens=think_tokens,
            token_source=token_source,
            finish_reason=choice.get("finish_reason"),
            http_status=status,
        )

    def _normalize_structured_calls(self, content_clean: str) -> list[ToolCall]:
        """解析云端 structured_output 的正文为工具调用列表。

        兼容三种形态：正文为 `[{name, arguments}, ...]` 数组、
        `{"tool_calls": [...]}` 对象包装（部分实现把严格 JSON 包成对象），
        或**裸单对象** `{name, arguments}`（单次调用时云端可能直接返回对象，
        见复审 v3 的 F1；此前未识别会误判为「格式退化」）。
        解析失败或无对象时返回空列表（→ 视为静默退化）。
        """
        calls: list[ToolCall] = []
        if not content_clean.strip():
            return calls
        try:
            data = json.loads(content_clean)
        except json.JSONDecodeError:
            return calls
        if isinstance(data, dict):
            if isinstance(data.get("tool_calls"), list):
                data = data["tool_calls"]
            elif data.get("name") is not None:
                data = [data]              # F1：裸单对象 → 视为单元素调用数组
        if not isinstance(data, list):
            return calls
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if name is None:
                continue
            args = item.get("arguments")
            parsed, err = _parse_arguments(args)
            raw_args = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
            calls.append(ToolCall(name=str(name), arguments=parsed,
                                  raw_arguments=raw_args, arguments_parse_error=err))
        return calls

    def _chat_openai_structured(self, messages: list[dict[str, str]], model: str) -> AdapterResult:
        """走 OpenAI 兼容 `/v1/chat/completions` + `response_format: json_schema` 做云端约束解码。

        `self.grammar` 是 `gbnf_grammar.generate_grammar` 产出的工具调用数组 JSON Schema，
        直接作为结构化输出 schema（各分支 name 用 const 锁定、arguments 完整、全部
        additionalProperties=false，满足 strict 前提）。不给 `tools` 字段，由 schema 强制
        输出合法 JSON 工具调用数组；正文经 `_normalize_structured_calls` 还原为调用。
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "stream": DEFAULT_STREAM,
            "seed": self.seed,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "tool_call_array",
                    "strict": True,
                    "schema": self.grammar,
                },
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return AdapterResult(model=model, content_raw="", content_clean="", think_text="",
                                 latency_ms=(time.perf_counter() - started) * 1000,
                                 http_status=exc.code, error=f"HTTP {exc.code}: {detail[:500]}")
        except Exception as exc:                                  # noqa: BLE001 - 网络层兜底
            return AdapterResult(model=model, content_raw="", content_clean="", think_text="",
                                 latency_ms=(time.perf_counter() - started) * 1000,
                                 error=f"{type(exc).__name__}: {exc}")

        latency_ms = (time.perf_counter() - started) * 1000
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return AdapterResult(model=model, content_raw=raw, content_clean="", think_text="",
                                 latency_ms=latency_ms, http_status=status,
                                 error=f"响应不是合法 JSON：{exc.msg}")

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content_raw = message.get("content") or ""
        thinking_field = message.get("thinking") or message.get("reasoning_content") or ""
        content_clean, think_text = strip_think(content_raw)
        if thinking_field:
            think_text = (think_text + "\n" + thinking_field).strip()

        calls = self._normalize_structured_calls(content_clean)
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        completion_tokens = usage.get("completion_tokens")
        think_tokens = details.get("reasoning_tokens")
        token_source = "usage"
        if think_tokens is None and think_text:
            think_tokens = _estimate_tokens(think_text)
            token_source = "char_fallback"
        elif completion_tokens is None:
            token_source = "none"

        return AdapterResult(
            model=model,
            content_raw=content_raw,
            content_clean=content_clean,
            think_text=think_text,
            tool_calls=calls,
            tool_calls_missing=not calls,
            latency_ms=latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=completion_tokens,
            think_tokens=think_tokens,
            token_source=token_source,
            finish_reason=choice.get("finish_reason"),
            http_status=status,
        )

    def _chat_native(self, messages: list[dict[str, str]], model: str) -> AdapterResult:
        """走 Ollama 原生 `/api/chat`，用 `format=<约束 schema>` 做结构化输出。

        原生接口返回单条 `message.content`，无 `choices[]`；结构化工具调用由 schema 保证为
        JSON 数组，故从正文还原（复用 parse_tool_calls 的内容兜底路径）。
        """
        base = re.sub(r"/v1/chat/completions$", "", self.endpoint) or self.endpoint
        native = base + "/api/chat"
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": self.grammar,      # 约束解码 JSON Schema（结构化输出）
            "options": {
                "num_ctx": self.num_ctx,
                "seed": self.seed,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": self.max_tokens,
            },
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(native, data=body, headers=headers, method="POST")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return AdapterResult(model=model, content_raw="", content_clean="", think_text="",
                                 latency_ms=(time.perf_counter() - started) * 1000,
                                 http_status=exc.code, error=f"HTTP {exc.code}: {detail[:500]}")
        except Exception as exc:                                  # noqa: BLE001 - 网络层兜底
            return AdapterResult(model=model, content_raw="", content_clean="", think_text="",
                                 latency_ms=(time.perf_counter() - started) * 1000,
                                 error=f"{type(exc).__name__}: {exc}")

        latency_ms = (time.perf_counter() - started) * 1000
        return self._parse_native_response(model, raw, latency_ms, status)

    def _parse_native_response(self, model: str, raw: str, latency_ms: float,
                               status: int) -> AdapterResult:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return AdapterResult(model=model, content_raw=raw, content_clean="", think_text="",
                                 latency_ms=latency_ms, http_status=status,
                                 error=f"响应不是合法 JSON：{exc.msg}")

        message = data.get("message") or {}
        content_raw = message.get("content") or ""
        thinking_field = message.get("thinking") or ""

        content_clean, think_text = strip_think(content_raw)
        if thinking_field:
            think_text = (think_text + "\n" + thinking_field).strip()

        # grammar 保证输出是 JSON 数组，从正文内容兜底还原工具调用
        calls = parse_tool_calls({"content": content_clean, "tool_calls": None}, content_clean)
        prompt_tokens = data.get("prompt_eval_count")
        completion_tokens = data.get("eval_count")
        think_tokens = data.get("eval_count_reasoning")

        if think_tokens is None and think_text:
            think_tokens = _estimate_tokens(think_text)
            token_source = "char_fallback"
        elif completion_tokens is not None:
            token_source = "usage"
        else:
            token_source = "none"

        return AdapterResult(
            model=model,
            content_raw=content_raw,
            content_clean=content_clean,
            think_text=think_text,
            tool_calls=calls,
            tool_calls_missing=not calls,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            think_tokens=think_tokens,
            token_source=token_source,
            finish_reason=data.get("done_reason") or ("done" if data.get("done") else None),
            http_status=status,
        )

    # -- 对外便捷方法 -------------------------------------------------------

    def call_case(self, model: str, user_input: str,
                  history: list[dict[str, str]] | None = None,
                  fewshot: bool = True) -> AdapterResult:
        """按用例发起一次调用；`history` 用于多轮用例（`context` 字段）。"""
        messages = build_messages(user_input, history=history, fewshot=fewshot,
                                  system_prompt=self.system_prompt)
        return self.chat(messages, model=model)


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    """不依赖模型与网络的装配自检（判据：Schema 注入与 few-shot 抽取必须成功）。"""
    failures: list[str] = []

    tools = load_tools()
    if len(tools) != 5:
        failures.append(f"工具数应为 5，实际 {len(tools)}")
    if {t["function"]["name"] for t in tools} != {
        "query_sensor", "search_knowledge", "query_graph",
        "get_maintenance_history", "generate_report",
    }:
        failures.append("工具名集合与 Schema v1 不一致")

    system = load_system_prompt()
    if "{{TOOLS_JSON_SCHEMA}}" in system or '"query_sensor"' not in system:
        failures.append("System Prompt 注入失败")

    fewshot = load_fewshot()
    if len(fewshot) != 6:
        failures.append(f"few-shot 应为 3 组共 6 条消息，实际 {len(fewshot)}")
    else:
        if fewshot[0]["role"] != "user" or fewshot[1]["role"] != "assistant":
            failures.append("few-shot 角色顺序错误")
        calls = json.loads(fewshot[1]["content"])
        if calls[0]["name"] != "query_sensor":
            failures.append("few-shot 示例 1 的工具名抽取错误")
        calls2 = json.loads(fewshot[3]["content"])
        if len(calls2) != 2:
            failures.append(f"few-shot 示例 2 应含 2 次调用，实际 {len(calls2)}")
        if fewshot[5]["content"].startswith("["):
            failures.append("few-shot 示例 3 应无工具调用（纯文本回复）")

    # ★防缺陷回归：build_messages 的 few-shot 来源必须随 prompt_path 变化。
    # 历史缺陷：load_fewshot() 恒用默认 PROMPT_PATH（v1），导致 --prompt 指向 v2/step 时
    # few-shot 仍为 v1 的 3 条（system 是新提示词、few-shot 是旧的，二者不同源）。
    _v1_msgs = build_messages("x", fewshot=True, system_prompt="s",
                              prompt_path=PROJECT_ROOT / "prompts" / "tool_call_prompt_v1.md")
    _v2_msgs = build_messages("x", fewshot=True, system_prompt="s",
                              prompt_path=PROJECT_ROOT / "prompts" / "tool_call_prompt_v2.md")
    if len(_v2_msgs) <= len(_v1_msgs):
        failures.append("build_messages 的 few-shot 未随 prompt_path 变化（v2 应多于 v1）")

    # think 剥离：先剥离再判 JSON；三种形态（成对标签 / R1 特殊 token / 未闭合）都要覆盖
    r1_case = _T_OPEN + '调用 query_sensor{}{"a":1}' + R1_END_TOKEN + "真正的回复"
    clean, think = strip_think(r1_case)
    if "query_sensor" in clean or "真正的回复" not in clean or think == "":
        failures.append("R1 特殊 token 形态的 think 剥离失败")

    pair_case = _T_OPEN_LONG + "内部推理" + _T_CLOSE_LONG + "对外回复"
    clean2, think2 = strip_think(pair_case)
    if "内部推理" in clean2 or "对外回复" not in clean2 or think2 != "内部推理":
        failures.append("成对标签形态的 think 剥离失败")

    unclosed_case = _T_OPEN + "被 max_tokens 截断的推理"
    clean3, _ = strip_think(unclosed_case)
    if clean3 != "":
        failures.append("未闭合 think 未被剥离")

    # tool_calls 缺失必须可被识别（R-V1-3）
    adapter = LLMAdapter()
    result = adapter._parse_response(
        "mock", json.dumps({"choices": [{"message": {"content": "抱歉，我无法调用工具。"}}]}), 1.0, 200
    )
    if not result.tool_calls_missing:
        failures.append("静默退化未被识别")

    # 云端 structured_output 归一：数组形态与 {"tool_calls":[...]} 包装形态都应还原
    _norm = LLMAdapter()
    _array_form = '[{"name": "query_sensor", "arguments": {"device_id": "PUMP-A-01", "time_range": {"start": "24h"}}}]'
    _calls_arr = _norm._normalize_structured_calls(_array_form)
    if len(_calls_arr) != 1 or _calls_arr[0].name != "query_sensor":
        failures.append("structured_output 数组形态归一失败")
    if _calls_arr[0].arguments is None \
            or _calls_arr[0].arguments.get("device_id") != "PUMP-A-01":
        failures.append("structured_output 数组形态 arguments 解析失败")
    _wrapped_form = '{"tool_calls": ' + _array_form + '}'
    _calls_wrap = _norm._normalize_structured_calls(_wrapped_form)
    if len(_calls_wrap) != 1 or _calls_wrap[0].name != "query_sensor":
        failures.append("structured_output 对象包装形态归一失败")
    # F1（复审 v3）：裸单对象形态 {name, arguments} 亦须还原
    _bare_form = '{"name": "query_sensor", "arguments": {"device_id": "PUMP-A-01", "time_range": {"start": "24h"}}}'
    _calls_bare = _norm._normalize_structured_calls(_bare_form)
    if len(_calls_bare) != 1 or _calls_bare[0].name != "query_sensor":
        failures.append("structured_output 裸单对象形态归一失败（F1）")
    if _norm._normalize_structured_calls("抱歉无法调用"):
        failures.append("structured_output 非 JSON 正文不应还原出调用")

    print(adapter.describe())
    if failures:
        print("\n[FAIL] 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("\n[OK] 自检通过：Schema 注入 / few-shot 抽取 / think 剥离 / 静默退化识别"
          " / 云端结构化输出归一")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM 统一适配层（V1 · T2.3）")
    parser.add_argument("--selftest", action="store_true", help="运行装配自检（不联网）")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
