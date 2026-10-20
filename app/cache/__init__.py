"""P7 Redis 缓存层（非权威、可重建、fail-open）。

分层（docs/p7-design-redis-cache-layer-2026-10-16.md）：
  emb     BGE-M3 embedding 纯函数缓存（模型 token 进 key）
  retr    检索结果缓存（knowledge_versions 版本令牌进 key）
  state   thread_status read-through（PG 前；TTL 24h）
  values  state values read-through（ask 追问注入；TTL 24h）
  llm     LLM 响应缓存（model + messages 进 key；temperature=0 路径）
  trig    告警自动触发 SETNX 快速去重（权威标记在 PG）

公开 API 即 client.py 的 cache_* 便捷函数；key 规范见 keys.py。
"""

from app.cache.client import (                                 # noqa: F401
    RedisCache,
    cache_get_embedding,
    cache_get_llm,
    cache_get_retrieval,
    cache_get_state,
    cache_get_values,
    cache_guard_trigger,
    cache_invalidate_thread,
    cache_set_embedding,
    cache_set_llm,
    cache_set_retrieval,
    cache_set_state,
    cache_set_values,
    get_cache,
)
