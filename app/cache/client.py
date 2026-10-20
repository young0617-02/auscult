"""Redis 缓存客户端（P7 · 非权威只读缓存层）。

定位（docs/p7-design-redis-cache-layer-2026-10-16.md）：
  - **非权威、可重建**：权威数据一律 PG；缓存丢失/过期/未命中的最坏后果
    = 回源重算，不影响正确性；
  - **fail-open**：Redis 不可达/超时/写失败 → 读按 miss、写按跳过、
    set_nx 按放行——与 rate_limit.py / budget.py「Redis 不可达不阻塞」
    的降级哲学一致，每次错误落审计（severity=warning）；
  - **DB 隔离**：缓存用 db 1；限流/预算/审核锁/告警去重等协调原语保持
    db 0——两类 key 生命周期与语义不同，不混居（缓存可整库 flush，
    协调原语不可）；
  - **体积闸门**：超过 CACHE_MAX_VALUE_BYTES 的 value 不落缓存。
    noeviction + maxmemory 1gb 下，大 payload 挤满内存会连带 db 0 的
    预算/锁写入失败（OOM command not allowed），故主动限流。

降级审计：复用 security.sanitizer.log_security_event（JSONL + PG 双写）。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.api.config import (
    CACHE_ENABLED,
    CACHE_MAX_VALUE_BYTES,
    CACHE_REDIS_URL,
)
from app.cache.keys import (
    TTL_EMBEDDING,
    TTL_LLM,
    TTL_RETRIEVAL,
    TTL_STATE,
    TTL_TRIGGER_GUARD,
    TTL_VALUES,
    embedding_key,
    llm_key,
    retrieval_key,
    state_key,
    trigger_guard_key,
    values_key,
)
from app.observability import prom_metrics as pm

logger = logging.getLogger("auscult.cache")


class RedisCache:
    """进程内单例的缓存客户端（惰性连接；所有公开方法 fail-open）。"""

    def __init__(self, url: str = CACHE_REDIS_URL, *, enabled: bool = CACHE_ENABLED):
        self.url = url
        self.enabled = enabled
        self._client = None

    # ---------------------------------------------------------------- 连接

    def _conn(self):
        """惰性 Redis 连接（失败抛异常，由各方法捕获降级）。"""
        if self._client is None:
            import redis                                          # noqa: PLC0415
            self._client = redis.from_url(self.url, decode_responses=True,
                                          socket_timeout=2,
                                          socket_connect_timeout=2)
        return self._client

    def _audit_error(self, op: str, exc: Exception) -> None:
        """缓存错误审计（降级不阻断；与预算/限流口径一致）。"""
        try:
            from app.security.sanitizer import log_security_event    # noqa: PLC0415
            log_security_event("redis_cache_error", severity="warning",
                               detail={"op": op,
                                       "error": type(exc).__name__})
        except Exception:                                         # noqa: BLE001
            pass

    # ---------------------------------------------------------------- 基础读写

    def get_json(self, key: str) -> Any | None:
        """读缓存；未命中/禁用/异常 → None（调用方按 miss 处理）。"""
        if not self.enabled:
            return None
        try:
            raw = self._conn().get(key)
        except Exception as exc:                                  # noqa: BLE001
            self._audit_error("get", exc)
            pm.inc_cache("get", "error")
            return None
        if raw is None:
            pm.inc_cache("get", "miss")
            return None
        try:
            pm.inc_cache("get", "hit")
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            # 脏值（手工写入/版本漂移）：按 miss 处理并记录
            self._audit_error("decode", exc)
            pm.inc_cache("get", "miss")
            return None

    def set_json(self, key: str, value: Any, ttl: int) -> bool:
        """写缓存（带 TTL）；禁用/超体积/异常 → False（调用方无需关心）。"""
        if not self.enabled:
            return False
        try:
            payload = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            pm.inc_cache("set", "skip")     # 不可 JSON 化（如含未归一化对象）
            return False
        if len(payload.encode("utf-8")) > CACHE_MAX_VALUE_BYTES:
            pm.inc_cache("set", "skip")     # 体积闸门：防挤爆 maxmemory 牵连 db 0
            return False
        try:
            self._conn().set(key, payload, ex=ttl)
            pm.inc_cache("set", "ok")
            return True
        except Exception as exc:                                  # noqa: BLE001
            self._audit_error("set", exc)
            pm.inc_cache("set", "error")
            return False

    def delete(self, *keys: str) -> None:
        """失效删除（幂等）；异常静默（TTL 是最终兜底）。"""
        keys = [k for k in keys if k]
        if not self.enabled or not keys:
            return
        try:
            self._conn().delete(*keys)
            pm.inc_cache("del", "ok")
        except Exception as exc:                                  # noqa: BLE001
            self._audit_error("del", exc)
            pm.inc_cache("del", "error")

    def set_nx(self, key: str, value: str, ttl: int) -> bool:
        """SETNX 护栏（自动触发去重用）；Redis 不可达 → True（放行，不阻断业务）。"""
        if not self.enabled:
            return True
        try:
            ok = bool(self._conn().set(key, value, nx=True, ex=ttl))
            pm.inc_cache("set_nx", "ok" if ok else "blocked")
            return ok
        except Exception as exc:                                  # noqa: BLE001
            self._audit_error("set_nx", exc)
            pm.inc_cache("set_nx", "error")
            return True                                           # fail-open

    # ---------------------------------------------------------------- 序列化辅助

    @staticmethod
    def jsonable(obj: Any) -> Any:
        """递归归一化为 JSON 安全结构（pydantic model_dump / datetime isoformat）。

        用于 state values 等含 pydantic 对象的 payload 落缓存前的转换。
        """
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if hasattr(obj, "model_dump"):                            # pydantic v2
            return RedisCache.jsonable(obj.model_dump())
        if hasattr(obj, "isoformat"):                             # datetime
            return obj.isoformat()
        if isinstance(obj, dict):
            return {str(k): RedisCache.jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [RedisCache.jsonable(v) for v in obj]
        return str(obj)                                           # 兜底：不猜语义


# ---------------------------------------------------------------- 进程单例

_cache: RedisCache | None = None


def get_cache() -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache


# ---------------------------------------------------------------- 分层便捷函数

def cache_get_embedding(model_token: str, text: str) -> list[float] | None:
    hit = get_cache().get_json(embedding_key(model_token, text))
    return hit if isinstance(hit, list) else None


def cache_set_embedding(model_token: str, text: str,
                        vector: list[float]) -> bool:
    return get_cache().set_json(embedding_key(model_token, text),
                                vector, TTL_EMBEDDING)


def cache_get_retrieval(version_token: str, *, mode: str, top_k: int,
                        use_rerank: bool, cache_key: str) -> dict | None:
    hit = get_cache().get_json(
        retrieval_key(version_token, mode=mode, top_k=top_k,
                      use_rerank=use_rerank, cache_key=cache_key))
    return hit if isinstance(hit, dict) else None


def cache_set_retrieval(version_token: str, *, mode: str, top_k: int,
                        use_rerank: bool, cache_key: str,
                        payload: dict) -> bool:
    return get_cache().set_json(
        retrieval_key(version_token, mode=mode, top_k=top_k,
                      use_rerank=use_rerank, cache_key=cache_key),
        payload, TTL_RETRIEVAL)


def cache_get_state(thread_id: str) -> dict | None:
    hit = get_cache().get_json(state_key(thread_id))
    return hit if isinstance(hit, dict) else None


def cache_set_state(thread_id: str, payload: dict) -> bool:
    return get_cache().set_json(state_key(thread_id), payload, TTL_STATE)


def cache_get_values(thread_id: str) -> dict | None:
    hit = get_cache().get_json(values_key(thread_id))
    return hit if isinstance(hit, dict) else None


def cache_set_values(thread_id: str, values: dict) -> bool:
    return get_cache().set_json(values_key(thread_id),
                                RedisCache.jsonable(values), TTL_VALUES)


def cache_invalidate_thread(thread_id: str) -> None:
    """线程状态变更（追问追加 / 审核恢复）→ 失效两层缓存。"""
    get_cache().delete(state_key(thread_id), values_key(thread_id))


def cache_get_llm(model: str, messages: list[dict]) -> str | None:
    hit = get_cache().get_json(llm_key(model, messages))
    return hit if isinstance(hit, str) else None


def cache_set_llm(model: str, messages: list[dict], content: str) -> bool:
    return get_cache().set_json(llm_key(model, messages), content, TTL_LLM)


def cache_guard_trigger(alarm_id: str) -> bool:
    """自动触发快速去重；True = 获得触发许可（未触发过或 Redis 不可达）。"""
    return get_cache().set_nx(trigger_guard_key(alarm_id),
                              str(time.time()), TTL_TRIGGER_GUARD)
