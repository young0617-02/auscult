"""BGE-M3 embedding 缓存代理（P7 · 缓存层 emb 分层）。

定位：embedding 是**纯函数**（同模型同文本 → 同向量），缓存零一致性风险，
     唯一失效维度是模型变更——故 key 进 model_token（路径 + size + mtime）。

为什么包代理而不改 run_v2.EmbeddingClient：
  - EmbeddingClient 是 V2 基线资产，众多脚本共用；缓存是 P7 增量关注点，
    按「附加式注册、不改既有契约」原则（同 retrieve_knowledge.with_tools 思路）
    以代理形态外挂；
  - 代理接口与 EmbeddingClient.embed(list[str]) -> list[vector] 完全一致，
     可透明替换。

降级：app.cache 导入失败 / Redis 不可达 → 全量透传（代理退化为直通）。
     注意：本模块被 scripts/ 独立运行时调用，故自带项目根 path 引导
     （与 app/tools/retrieve_knowledge.py 的 sys.path 转发同模式）。

自检：python scripts/embedding_cache.py --selftest
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _model_token(model_path: str | Path) -> str:
    """模型身份令牌：路径 + size + mtime（换模型/换文件即失效）。"""
    p = Path(model_path)
    try:
        st = p.stat()
        return f"{p.name}:{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return f"{p.name}:nostat"


class CachedEmbedder:
    """embed() 结果 Redis 缓存代理（fail-open：任何异常退化为直通）。"""

    def __init__(self, inner: Any, model_token: str) -> None:
        self._inner = inner
        self._token = model_token
        self.hits = 0
        self.misses = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            from app.cache import cache_get_embedding, cache_set_embedding  # noqa: PLC0415
        except Exception:                                         # noqa: BLE001 - 导入失败直通
            return self._inner.embed(texts)

        vectors: list[list[float] | None] = [None] * len(texts)
        miss_idx: list[int] = []
        miss_texts: list[str] = []
        for i, t in enumerate(texts):
            hit = cache_get_embedding(self._token, t)
            if hit is not None:
                vectors[i] = hit
                self.hits += 1
            else:
                miss_idx.append(i)
                miss_texts.append(t)

        if miss_texts:
            fresh = self._inner.embed(miss_texts)
            for i, vec in zip(miss_idx, fresh):
                vectors[i] = vec
                self.misses += 1
                try:
                    cache_set_embedding(self._token, texts[i], vec)
                except Exception:                                 # noqa: BLE001 - 写失败不影响结果
                    pass
        # miss 已由 inner 回填，vectors 与 texts 等长同序；None 仅当 inner
        # 返回数不足（契约违反），交由上游按与直通 EmbeddingClient 相同的方式失败
        return vectors


def wrap_embedder(inner: Any, model_path: str | Path) -> Any:
    """工厂：inner 为 None 时原样返回（调用方负责惰性加载顺序）。"""
    if inner is None:
        return None
    return CachedEmbedder(inner, _model_token(model_path))


def _selftest() -> int:
    """离线自检：直通语义 + 顺序保持 + 计数（不连 Redis 也可过）。"""
    fail = 0

    class _Fake:
        def embed(self, texts):
            return [[float(len(t)), 1.0] for t in texts]

    fake = _Fake()
    proxy = CachedEmbedder(fake, "tok:1:2")
    # Redis 不可达时 cache_get 返回 None → 全 miss → 直通且顺序保持
    out = proxy.embed(["a", "bb", "ccc"])
    if out != [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]]:
        print(f"[FAIL] 直通语义/顺序错误: {out}")
        fail += 1
    if proxy.misses != 3 or proxy.hits != 0:
        print(f"[FAIL] 计数错误: hits={proxy.hits} misses={proxy.misses}")
        fail += 1
    # 空输入
    if proxy.embed([]) != []:
        print("[FAIL] 空输入未短路")
        fail += 1
    # wrap_embedder(None) → None
    if wrap_embedder(None, "x") is not None:
        print("[FAIL] wrap_embedder(None) 应返回 None")
        fail += 1
    print(f"[{'OK' if fail == 0 else 'FAIL'}] embedding_cache selftest：失败 {fail} 项")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="BGE-M3 embedding 缓存代理")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
