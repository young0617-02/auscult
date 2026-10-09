"""Langfuse Trace 全覆盖（D21 · M3.5）

职责（plan/Phase 3 §6.7 可观测性 · Trace 维度）：
  1. 每节点一个 span（名称 + 入参摘要 + 耗时 + 输出摘要）；
  2. 工具调用记录（入参 + 耗时 + 输出）；
  3. LLM 调用记录（token 数 + 模型名 + think 占比）；
  4. trace_id 贯穿（结构化 JSON 日志，写入 reports/traces/{trace_id}.jsonl）。

设计原则：
  - 轻量自研，不引入 Langfuse 服务端依赖（后续可无缝切换）；
  - API 兼容 Langfuse SDK 语义（trace → span → observation）；
  - 线程局部 Tracer，节点装饰器自动追踪。

对应交付物：plan/Phase 3 §五 D21 / §六.7
"""

from __future__ import annotations

import functools
import json
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------- 常量

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACE_DIR = PROJECT_ROOT / "reports" / "traces"

_MAX_SUMMARY_LEN = 200   # 日志摘要截断长度


# ---------------------------------------------------------------- 工具函数

def new_trace_id() -> str:
    """生成唯一 trace_id（16 位 hex）。"""
    return uuid.uuid4().hex[:16]


def _truncate(s: Any, max_len: int = _MAX_SUMMARY_LEN) -> str | None:
    """截断长文本用于日志摘要。None / 空值原样返回。"""
    if s is None:
        return None
    s = str(s)
    return s if len(s) <= max_len else s[:max_len] + "..."


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- Tracer

class Tracer:
    """轻量 trace 记录器。

    每个 graph.invoke 分配唯一 trace_id，
    所有 span / LLM 调用 / 工具调用写入同一 JSONL 文件。

    用法：
        tracer = Tracer()
        set_current_tracer(tracer)
        with tracer.span("graph.invoke", input_summary=alarm):
            result = graph.invoke(initial, config=config)
        # → reports/traces/{trace_id}.jsonl
    """

    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or new_trace_id()
        self._file = TRACE_DIR / f"{self.trace_id}.jsonl"
        self._spans: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @contextmanager
    def span(self, name: str, *,
             parent_id: str | None = None,
             input_summary: Any = None,
             **metadata: Any) -> Any:
        """记录一个 span（contextmanager）。

        用法：
            with tracer.span("parse_alarm", input_summary=state.alarm) as span_id:
                result = parse_alarm(state)
                # span 结束时自动记录 duration
        """
        span_id = uuid.uuid4().hex[:8]
        start = time.time()
        start_ts = _now_iso()
        yield span_id
        duration_ms = round((time.time() - start) * 1000, 2)
        record: dict[str, Any] = {
            "trace_id": self.trace_id,
            "span_id": span_id,
            "parent_id": parent_id,
            "type": "span",
            "name": name,
            "start_ts": start_ts,
            "end_ts": _now_iso(),
            "duration_ms": duration_ms,
            "input": _truncate(input_summary),
            **metadata,
        }
        self._write(record)

    def log_llm(self, name: str, model: str, *,
                input_tokens: int = 0,
                output_tokens: int = 0,
                think_tokens: int = 0,
                duration_ms: float = 0.0,
                parent_id: str | None = None,
                **metadata: Any) -> None:
        """记录 LLM 调用（token 统计 + think 占比）。

        供 diagnose.py / cloud.py 在调用 ollama / ModelScope 后手动调用。
        """
        total = input_tokens + output_tokens
        think_pct = round(think_tokens / max(output_tokens, 1) * 100, 1)
        record = {
            "trace_id": self.trace_id,
            "span_id": uuid.uuid4().hex[:8],
            "parent_id": parent_id,
            "type": "llm",
            "name": name,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total,
            "think_tokens": think_tokens,
            "think_pct": think_pct,
            "duration_ms": round(duration_ms, 2),
            "ts": _now_iso(),
            **metadata,
        }
        self._write(record)

    def log_tool(self, name: str, input_args: Any, output: Any, *,
                 duration_ms: float = 0.0,
                 parent_id: str | None = None,
                 **metadata: Any) -> None:
        """记录工具调用（入参 + 输出 + 耗时）。

        供 retrieve_evidence / get_history 等节点在调用外部工具后手动调用。
        """
        record = {
            "trace_id": self.trace_id,
            "span_id": uuid.uuid4().hex[:8],
            "parent_id": parent_id,
            "type": "tool",
            "name": name,
            "input": _truncate(input_args),
            "output": _truncate(output),
            "duration_ms": round(duration_ms, 2),
            "ts": _now_iso(),
            **metadata,
        }
        self._write(record)

    def log_event(self, name: str, **metadata: Any) -> None:
        """记录自定义事件（如条件路由、降级、审核中断）。"""
        record = {
            "trace_id": self.trace_id,
            "span_id": uuid.uuid4().hex[:8],
            "type": "event",
            "name": name,
            "ts": _now_iso(),
            **metadata,
        }
        self._write(record)

    # ---------------------------------------------------------------- 内部

    def _write(self, record: dict[str, Any]) -> None:
        """线程安全写入 JSONL。"""
        with self._lock:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._spans.append(record)

    # ---------------------------------------------------------------- 查询

    @property
    def spans(self) -> list[dict[str, Any]]:
        """所有已记录的 span/llm/tool/event 记录（只读副本）。"""
        return list(self._spans)

    def span_count(self) -> int:
        """已记录的总条数。"""
        return len(self._spans)

    def filter_by_type(self, record_type: str) -> list[dict[str, Any]]:
        """按类型过滤记录（span/llm/tool/event）。"""
        return [s for s in self._spans if s.get("type") == record_type]

    def file_path(self) -> Path:
        """trace JSONL 文件路径。"""
        return self._file


# ---------------------------------------------------------------- 线程局部 Tracer

_local = threading.local()


def get_current_tracer() -> Tracer | None:
    """获取当前线程的 Tracer（线程局部）。"""
    return getattr(_local, "tracer", None)


def set_current_tracer(tracer: Tracer | None) -> None:
    """设置当前线程的 Tracer。"""
    _local.tracer = tracer


def clear_current_tracer() -> None:
    """清除当前线程的 Tracer。"""
    _local.tracer = None


# ---------------------------------------------------------------- 节点装饰器

def trace_node(name: str) -> Callable:
    """节点装饰器：自动从线程局部获取 Tracer 并记录 span。

    无 Tracer 时直接调用原函数（零开销降级）。
    有 Tracer 时自动记录 span（名称 + 入参摘要 + 耗时）。

    用法：
        @trace_node("parse_alarm")
        def parse_alarm(state):
            ...

    对应 plan §6.7「每节点一个 span」。
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: Any, *args: Any, **kwargs: Any) -> Any:
            tracer = get_current_tracer()
            if tracer is None:
                return fn(state, *args, **kwargs)
            with tracer.span(name, input_summary=state) as span_id:
                result = fn(state, *args, **kwargs)
                # 记录输出摘要
                if isinstance(result, dict):
                    output_keys = list(result.keys())
                    tracer.log_event(f"{name}.output",
                                     span_id=span_id,
                                     output_keys=output_keys)
                return result

        return wrapper

    return decorator


# ---------------------------------------------------------------- 便捷函数

def start_trace(trace_id: str | None = None) -> Tracer:
    """开启一个新 trace，设置到线程局部，返回 Tracer。

    用法：
        tracer = start_trace()
        try:
            graph.invoke(initial, config=config)
        finally:
            clear_current_tracer()
    """
    tracer = Tracer(trace_id)
    set_current_tracer(tracer)
    return tracer


def end_trace() -> None:
    """结束当前 trace，清除线程局部。"""
    clear_current_tracer()
