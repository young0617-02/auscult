"""Redis 缓存 key 规范与 TTL 口径（P7 · 缓存层）。

命名空间：``auscult:cache:v1:{layer}:{token}:{hash}``

设计口径：
  - **版本前缀进 key**：schema 变更（如 llm key 增加字段）直接换 ``v1→v2``
    前缀整体失效，不做原地迁移——与 schemas/ 冻结区「修改须升版」同构；
  - **失效 = 换 key**：模型 digest / prompt 版本 / 知识版本等一切影响输出的
    输入都进 hash，输入变则 key 变，旧 key 靠 TTL 自然过期，无原地失效逻辑；
  - **hash 输入 canonical JSON**（sort_keys）：同语义输入同 key，与 dict
    键序无关。

对应交付物：docs/p7-design-redis-cache-layer-2026-10-16.md §三
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.api.config import (
    CACHE_TTL_EMBEDDING,
    CACHE_TTL_LLM,
    CACHE_TTL_RETRIEVAL,
    CACHE_TTL_STATE,
    CACHE_TTL_VALUES,
)

NS = "auscult:cache:v1"


def _h(payload: Any) -> str:
    """canonical JSON → sha256 前 32 hex（碰撞面足够，key 更短）。"""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:32]


# ---------------------------------------------------------------- 各层 key

def embedding_key(model_token: str, text: str) -> str:
    """BGE-M3 纯函数缓存：model_token = 模型路径 + size + mtime（换模型即失效）。"""
    return f"{NS}:emb:{model_token}:{_h(text)}"


def retrieval_key(version_token: str, *, mode: str, top_k: int,
                  use_rerank: bool, cache_key: str) -> str:
    """检索结果缓存：version_token = knowledge_versions.max(id)（升版即失效）。

    cache_key 由调用方给的归一化检索语义（如 device_id|metric），
    不得含告警数值等每次不同的字段（否则命中率趋零）。
    """
    return f"{NS}:retr:{version_token}:{_h({'mode': mode, 'top_k': top_k,
                                            'use_rerank': use_rerank,
                                            'q': cache_key})}"


def state_key(thread_id: str) -> str:
    """thread_status 只读缓存（PG 前 read-through）。"""
    return f"{NS}:state:{thread_id}"


def values_key(thread_id: str) -> str:
    """线程 state values 只读缓存（ask 追问注入用）。"""
    return f"{NS}:values:{thread_id}"


def llm_key(model: str, messages: list[dict[str, Any]]) -> str:
    """LLM 响应缓存：model + 完整 messages（temperature=0 路径专用）。"""
    return f"{NS}:llm:{_h({'model': model, 'messages': messages})}"


def trigger_guard_key(alarm_id: str) -> str:
    """告警自动触发快速去重（SETNX；权威标记在 PG alerts.diagnosed_thread_id）。"""
    return f"{NS}:trig:{alarm_id}"


# ---------------------------------------------------------------- TTL 口径

TTL_STATE = CACHE_TTL_STATE          # 线程状态/上下文（对齐 README §2.5 会话 24h 口径）
TTL_VALUES = CACHE_TTL_VALUES        # state values（证据冻结后不变）
TTL_RETRIEVAL = CACHE_TTL_RETRIEVAL  # 检索结果（知识升版换 key 后旧 key 自然过期）
TTL_EMBEDDING = CACHE_TTL_EMBEDDING  # embedding（纯函数，仅模型变更失效）
TTL_LLM = CACHE_TTL_LLM              # LLM 响应（prompt/模型/输入变即失效）
TTL_TRIGGER_GUARD = 7 * 24 * 3600    # 触发去重护栏（与 budget 审计窗口对齐）
