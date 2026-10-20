"""P7 Redis 缓存层回归测试（全离线：Redis 不可达即验证 fail-open 降级路径）。

对应缺口：缓存层引入后的三类风险——
  1. key 漂移（同语义不同 key → 命中率归零；不同语义同 key → 串味）；
  2. 降级路径失效（Redis 挂了没按 miss/放行处理 → 阻断主业务）；
  3. 序列化错位（pydantic/datetime 未归一化 → 脏值或异常外抛）。

运行：.venv\\Scripts\\python.exe -m pytest tests/test_cache_layer.py -q
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.cache import RedisCache
from app.cache.client import (
    cache_get_llm,
    cache_set_llm,
)
from app.cache.keys import (
    embedding_key,
    llm_key,
    retrieval_key,
    state_key,
    trigger_guard_key,
    values_key,
)
from app.graph.state import AlarmEvent
from embedding_cache import CachedEmbedder

# 端口 1：本机必然拒绝连接（连接立即失败，不拖慢测试）
_UNREACHABLE = "redis://127.0.0.1:1/0"


# ---------------------------------------------------------------- key 规范

def test_embedding_key_model_token_isolated():
    """换模型（token 变）必须换 key——否则旧模型向量串味。"""
    a = embedding_key("bge:v1:100", "离心泵振动")
    b = embedding_key("bge:v2:100", "离心泵振动")
    assert a != b
    assert embedding_key("bge:v1:100", "离心泵振动") == a      # 确定性


def test_retrieval_key_all_dimensions():
    """版本/模式/top_k/rerank/语义 五维任一变化都必须换 key。"""
    base = dict(version_token="42", mode="rules", top_k=5,
                use_rerank=False, cache_key="PUMP-A-01|vib_rms")
    k = retrieval_key(**base)
    assert retrieval_key(**{**base, "version_token": "43"}) != k     # 知识升版
    assert retrieval_key(**{**base, "mode": "llm"}) != k
    assert retrieval_key(**{**base, "top_k": 10}) != k
    assert retrieval_key(**{**base, "use_rerank": True}) != k
    assert retrieval_key(**{**base, "cache_key": "PUMP-B-02|vib_rms"}) != k
    assert retrieval_key(**base) == k                                # 确定性


def test_llm_key_model_and_messages():
    """model 或 messages 任一变化 → 换 key。"""
    msgs = [{"role": "user", "content": "hi"}]
    k = llm_key("deepseek-r1:7b", msgs)
    assert llm_key("qwen2.5:7b", msgs) != k
    assert llm_key("deepseek-r1:7b", msgs + [{"role": "assistant",
                                              "content": "hello"}]) != k
    assert llm_key("deepseek-r1:7b", msgs) == k


def test_thread_keys_isolated():
    assert state_key("thr-a") != state_key("thr-b")
    assert state_key("thr-a") != values_key("thr-a")
    assert trigger_guard_key("alarm-1") != trigger_guard_key("alarm-2")


# ---------------------------------------------------------------- fail-open 降级

def test_unreachable_redis_read_is_miss():
    """Redis 不可达 → 读必须按 miss（None），不得抛异常阻断调用方。"""
    c = RedisCache(_UNREACHABLE, enabled=True)
    assert c.get_json("auscult:cache:v1:state:x") is None


def test_unreachable_redis_write_is_noop():
    """Redis 不可达 → 写必须静默失败（False）。"""
    c = RedisCache(_UNREACHABLE, enabled=True)
    assert c.set_json("k", {"a": 1}, ttl=60) is False


def test_unreachable_redis_setnx_fails_open():
    """set_nx 不可达 → 放行（True）——自动触发护栏不得因 Redis 故障阻断业务。"""
    c = RedisCache(_UNREACHABLE, enabled=True)
    assert c.set_nx("k", "v", ttl=60) is True


def test_disabled_cache_short_circuits():
    """CACHE_ENABLED=0 → 全短路（不建连接、不落审计）。"""
    c = RedisCache(_UNREACHABLE, enabled=False)
    assert c.get_json("k") is None
    assert c.set_json("k", 1, 60) is False
    assert c.set_nx("k", "v", 60) is True
    c.delete("k")          # 不抛即过


def test_module_level_helpers_with_unreachable_default(monkeypatch):
    """便捷函数层（ diagnose/runner 实际调用面）同样 fail-open。"""
    monkeypatch.setattr("app.cache.client._cache",
                        RedisCache(_UNREACHABLE, enabled=True))
    assert cache_get_llm("m", [{"role": "user", "content": "x"}]) is None
    assert cache_set_llm("m", [{"role": "user", "content": "x"}], "y") is False


# ---------------------------------------------------------------- 序列化

def test_jsonable_pydantic_and_datetime():
    """state values 含 pydantic/datetime → 归一化为 JSON 安全结构。"""
    alarm = AlarmEvent(alarm_id="a1", device_id="PUMP-A-01", metric="vib_rms",
                       value=4.7, severity="high", ts=0)
    out = RedisCache.jsonable({
        "alarm": alarm,
        "when": dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.timezone.utc),
        "items": [alarm, {"k": (1, 2)}],
        "none": None,
    })
    assert out["alarm"]["device_id"] == "PUMP-A-01"
    assert out["when"].startswith("2026-10-16T12:00:00")
    assert out["items"][0]["metric"] == "vib_rms"
    assert out["items"][1]["k"] == [1, 2]        # tuple → list
    assert out["none"] is None
    # 归一化结果必须可 JSON 化（落缓存的前置条件）
    import json
    json.dumps(out, ensure_ascii=False)


# ---------------------------------------------------------------- embedding 代理

class _FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[float(len(t)), 0.5] for t in texts]


def test_cached_embedder_passthrough_when_redis_down(monkeypatch):
    """Redis 不可达 → 全 miss → 直通 inner，且顺序/计数正确。"""
    monkeypatch.setattr("app.cache.client._cache",
                        RedisCache(_UNREACHABLE, enabled=True))
    fake = _FakeEmbedder()
    proxy = CachedEmbedder(fake, "tok:1:2")
    out = proxy.embed(["a", "bb", "ccc"])
    assert out == [[1.0, 0.5], [2.0, 0.5], [3.0, 0.5]]   # 与 inner 直通一致
    assert proxy.misses == 3 and proxy.hits == 0
    assert fake.calls == 1                                 # miss 合并为一次批量调用


def test_cached_embedder_empty_short_circuit():
    proxy = CachedEmbedder(_FakeEmbedder(), "tok")
    assert proxy.embed([]) == []
