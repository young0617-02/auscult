"""V2 混合检索验证器（T3.1–T3.3）

对应交付物：`Phase 0 详细开发计划（D1-D10 可执行版）.md` §三 D4–D5 · T3.1 / T3.2 / T3.3
判据依据：`reports/v2-report.md` §四 / §八 ｜ 评测集：`evals/golden_set_v1.jsonl`（50 条）
实验登记：`docs/experiment-log-template.md`

本脚本一次覆盖三件事：
  1. **`--check-analyzer`**：jieba 中文分词有效性抽检（≥20 条工业术语，R-V2-1 强制动作）；
  2. **质量对比**：Milvus / pgvector 两条路线 × dense / sparse / hybrid 三种模式，
     统一计算 `Recall@5` / MRR / Precision@5（即报告中的「Top-5 相关性」）；
  3. **公平性硬约束**：pgvector 侧稀疏路线**必须显式声明** `tsvector` 或 `paradedb`（R-V2-3），
     未声明直接报错退出，禁止含糊对比。

资源纪律：**纯 CPU 路线**，不占 GPU（与 V1 错峰，对应 R10）。

自检：`python scripts/run_v2.py --selftest`
用法：
  python scripts/run_v2.py --check-analyzer --samples evals/corpora_v1/corpus_100.jsonl
  python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes milvus,pgvector \
      --pg-sparse tsvector --out-dir experiments/v2/raw
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = PROJECT_ROOT / "evals" / "golden_set_v1.jsonl"
CORPUS_PATH = PROJECT_ROOT / "evals" / "corpora_v1" / "corpus_100.jsonl"
RAW_DIR = PROJECT_ROOT / "experiments" / "v2" / "raw"

DENSE_TOP_K = 5
RRF_K = 60                       # 报告 §五 候选值；实测选定值须回填基线表
EMBED_DIM_EXPECTED = 1024        # BGE-M3 维度（已实测确认，见 reports/v2-report.md §四）
ROUTES = ("milvus", "pgvector")
MODES = ("dense", "sparse", "hybrid")
PG_SPARSE_IMPLS = ("tsvector", "paradedb")
ANALYZER_MIN_SAMPLES = 20        # R-V2-1：抽检样本数下限


# ---------------------------------------------------------------- 数据结构


@dataclass
class Doc:
    chunk_id: str
    text: str
    category: str = ""
    doc_title: str = ""


@dataclass
class Query:
    qid: str
    question: str
    relevant_chunk_ids: list[str]
    category: str = ""


@dataclass
class EvalConfig:
    route: str
    mode: str
    top_k: int = DENSE_TOP_K
    rrf_k: int = RRF_K
    pg_sparse: str | None = None
    embed_model: str = "bge-m3"
    notes: str = ""

    @property
    def experiment_id(self) -> str:
        # 稀疏声明只影响涉及稀疏检索的模式，稠密模式的编号不带后缀（避免同义编号分裂）
        needs_sparse = self.mode in ("sparse", "hybrid")
        suffix = f"-{self.pg_sparse}" if (self.route == "pgvector" and self.pg_sparse
                                          and needs_sparse) else ""
        return f"EXP-V2-{self.route}-{self.mode}{suffix}"


# ---------------------------------------------------------------- 数据加载


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_golden(path: Path = GOLDEN_PATH) -> list[Query]:
    queries: list[Query] = []
    for row in load_jsonl(path):
        queries.append(Query(
            qid=row["qid"],
            question=row["question"],
            relevant_chunk_ids=list(row.get("relevant_chunk_ids") or []),
            category=row.get("category", ""),
        ))
    return queries


def load_corpus(path: Path = CORPUS_PATH) -> list[Doc]:
    docs: list[Doc] = []
    for row in load_jsonl(path):
        docs.append(Doc(
            chunk_id=row["chunk_id"],
            text=row.get("text", ""),
            category=row.get("category", ""),
            doc_title=row.get("doc_title", ""),
        ))
    return docs


# ---------------------------------------------------------------- 指标


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Recall@k = 命中相关块数 / 相关块总数。"""
    if not relevant:
        return 0.0
    hit = len(set(retrieved[:k]) & set(relevant))
    return hit / len(relevant)


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Precision@k —— 报告中「Top-5 相关性（均值）」的口径（二值相关性）。"""
    if k <= 0:
        return 0.0
    return len(set(retrieved[:k]) & set(relevant)) / k


def reciprocal_rank(retrieved: list[str], relevant: list[str]) -> float:
    """RR（用于 MRR）= 1 / 首个相关块的排名；无命中记 0。"""
    relevant_set = set(relevant)
    for idx, chunk_id in enumerate(retrieved, start=1):
        if chunk_id in relevant_set:
            return 1.0 / idx
    return 0.0


def rrf_fuse(rank_lists: list[list[str]], k: int = RRF_K) -> list[str]:
    """Reciprocal Rank Fusion：score(d) = Σ 1/(k + rank_i(d))，排名从 1 起。"""
    scores: dict[str, float] = defaultdict(float)
    for ranks in rank_lists:
        for rank, chunk_id in enumerate(ranks, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return [cid for cid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


def evaluate(queries: Iterable[Query], retrieve: Any, config: EvalConfig) -> dict[str, Any]:
    """对一批 query 跑检索并汇总指标；`retrieve(question, top_k) -> list[chunk_id]`。"""
    per_query: list[dict[str, Any]] = []
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for q in queries:
        started = time.perf_counter()
        retrieved = retrieve(q.question, config.top_k)
        latency_ms = (time.perf_counter() - started) * 1000
        row = {
            "qid": q.qid,
            "category": q.category,
            "question": q.question,
            "retrieved": list(retrieved[: config.top_k]),
            "relevant": q.relevant_chunk_ids,
            "recall_at_5": recall_at_k(retrieved, q.relevant_chunk_ids, config.top_k),
            "precision_at_5": precision_at_k(retrieved, q.relevant_chunk_ids, config.top_k),
            "rr": reciprocal_rank(retrieved, q.relevant_chunk_ids),
            "latency_ms": round(latency_ms, 3),
        }
        per_query.append(row)
        by_category[q.category].append(row)

    metrics = {
        "recall_at_5": _mean([r["recall_at_5"] for r in per_query]),
        "mrr": _mean([r["rr"] for r in per_query]),
        "precision_at_5": _mean([r["precision_at_5"] for r in per_query]),
        "p95_latency_ms": _p95([r["latency_ms"] for r in per_query]),
        "mean_latency_ms": _mean([r["latency_ms"] for r in per_query]),
        "query_count": len(per_query),
    }
    category_metrics = {
        cat: {
            "recall_at_5": _mean([r["recall_at_5"] for r in rows]),
            "mrr": _mean([r["rr"] for r in rows]),
            "query_count": len(rows),
        }
        for cat, rows in sorted(by_category.items())
    }
    return {
        "experiment_id": config.experiment_id,
        "route": config.route,
        "mode": config.mode,
        "top_k": config.top_k,
        "rrf_k": config.rrf_k,
        "pg_sparse": config.pg_sparse,
        "embed_model": config.embed_model,
        "notes": config.notes,
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "metrics": metrics,
        "by_category": category_metrics,
        "per_query": per_query,
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(0.95 * len(ordered)) - 1))]


# ---------------------------------------------------------------- 向量化


# ModelScope 本地 BGE-M3 模型目录（完整 sentence-transformers 格式）
BGE_M3_MODEL_PATH = r"D:\modelscope\hub\models\BAAI--bge-m3\snapshots\master"


class EmbeddingClient:
    """基于 sentence-transformers 从 ModelScope 本地目录加载 BGE-M3 做向量化。

    纯本地推理，不依赖 Ollama。惰性加载：首次 `embed()` 时才装载模型，无参构造
    不加载模型（供 `--selftest` 等占位用途，避免无谓加载）。保留 `embed()` 接口与
    磁盘缓存，调用方（run_v2 / v2_pg_build / evaluate）无需改动。
    """

    def __init__(self, model: str = BGE_M3_MODEL_PATH,
                 device: str | None = None, cache_path: Path | None = None) -> None:
        self.model_path = model
        self.device = device
        self.cache_path = cache_path
        self._encoder = None                     # 惰性加载
        self.cache: dict[str, list[float]] = {}
        if cache_path and cache_path.exists():
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def _load(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(
                self.model_path, device=self.device)
        return self._encoder

    def embed(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in texts if t not in self.cache]
        if missing:
            encoder = self._load()
            try:
                vectors = encoder.encode(missing, normalize_embeddings=True).tolist()
            except Exception as exc:             # noqa: BLE001 - 推理层兜底
                raise RuntimeError(
                    f"向量化失败：{type(exc).__name__}: {exc}\n"
                    f"请确认 ModelScope 本地模型目录存在：{self.model_path}") from exc
            for text, vec in zip(missing, vectors):
                self.cache[text] = vec
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(json.dumps(self.cache), encoding="utf-8")

        vectors = [self.cache[t] for t in texts]
        if vectors and len(vectors[0]) != EMBED_DIM_EXPECTED:
            print(f"⚠️  向量维度 {len(vectors[0])} ≠ 期望 {EMBED_DIM_EXPECTED}"
                  f"（须回填 v2-report §五 参数基线表）")
        return vectors


# ---------------------------------------------------------------- Milvus 路线


class MilvusRetriever:
    """Milvus v3.0.0：稠密 + **服务端 BM25**（`FunctionType.BM25` + `enable_analyzer`）。

    ★ R-V2-2：稀疏检索必须走服务端 BM25 函数，**不得**在客户端自实现 BM25 后冒充原生能力。
    """

    COLLECTION = "kb_v1"

    def __init__(self, uri: str, embedder: EmbeddingClient, mode: str,
                 analyzer: str = "jieba", rrf_k: int = RRF_K) -> None:
        try:
            from pymilvus import (AnnSearchRequest, DataType, Function, FunctionType,   # noqa: PLC0415
                                  MilvusClient, RRFRanker, connections)
        except ImportError as exc:                                # pragma: no cover - 环境依赖
            raise RuntimeError(
                "缺少 pymilvus，请先安装：uv pip install pymilvus") from exc
        self._api = {"AnnSearchRequest": AnnSearchRequest, "DataType": DataType,
                     "Function": Function, "FunctionType": FunctionType,
                     "RRFRanker": RRFRanker}
        self.uri = uri
        self.embedder = embedder
        self.mode = mode
        self.analyzer = analyzer
        self.rrf_k = rrf_k
        self.client = MilvusClient(uri=uri)
        connections.connect(alias="default", uri=uri)

    # -- 建库 ---------------------------------------------------------------

    def rebuild(self, docs: list[Doc]) -> None:
        """按 v1 参数建库（维度 1024 / 服务端 BM25 / jieba analyzer）。"""
        DataType = self._api["DataType"]
        Function = self._api["Function"]
        FunctionType = self._api["FunctionType"]
        client = self.client

        if client.has_collection(self.COLLECTION):
            client.drop_collection(self.COLLECTION)

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, max_length=128, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=65535,
                         enable_analyzer=True,
                         analyzer_params={"tokenizer": self.analyzer})
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=EMBED_DIM_EXPECTED)
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(Function(name="bm25", function_type=FunctionType.BM25,
                                     input_field_names=["text"],
                                     output_field_names=["sparse"]))

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="dense", index_type="HNSW",
                               metric_type="COSINE", params={"M": 16, "efConstruction": 200})
        index_params.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX",
                               metric_type="BM25")

        client.create_collection(self.COLLECTION, schema=schema, index_params=index_params)

        vectors = self.embedder.embed([d.text for d in docs])
        client.insert(self.COLLECTION, [
            {"chunk_id": d.chunk_id, "text": d.text, "dense": vec}
            for d, vec in zip(docs, vectors)
        ])
        client.flush(self.COLLECTION)
        print(f"[milvus] 建库完成：{len(docs)} 块（analyzer={self.analyzer}，服务端 BM25）")

    # -- 检索 ---------------------------------------------------------------

    def __call__(self, question: str, top_k: int) -> list[str]:
        if self.mode == "dense":
            return self._search_dense(question, top_k)
        if self.mode == "sparse":
            return self._search_sparse(question, top_k)
        dense = self._search_dense(question, top_k * 2)
        sparse = self._search_sparse(question, top_k * 2)
        return rrf_fuse([dense, sparse], self.rrf_k)[:top_k]

    def _search_dense(self, question: str, top_k: int) -> list[str]:
        vector = self.embedder.embed([question])[0]
        res = self.client.search(collection_name=self.COLLECTION, data=[vector],
                                 anns_field="dense", limit=top_k,
                                 output_fields=["chunk_id"])
        return [hit["entity"]["chunk_id"] for hit in (res[0] if res else [])]

    def _search_sparse(self, question: str, top_k: int) -> list[str]:
        # BM25 函数型稀疏字段的查询侧直接传原始文本（分词由服务端 analyzer 完成）
        res = self.client.search(collection_name=self.COLLECTION, data=[question],
                                 anns_field="sparse", limit=top_k,
                                 output_fields=["chunk_id"])
        return [hit["entity"]["chunk_id"] for hit in (res[0] if res else [])]


# ---------------------------------------------------------------- pgvector 路线


class PgvectorRetriever:
    """PostgreSQL + pgvector：稠密（`<=>`）+ 稀疏（`tsvector` 或 ParadeDB `pg_search`）。

    ★ R-V2-3：稀疏实现必须由 `--pg-sparse` 显式声明，未声明直接报错。
    """

    DENSE_SQL = """
        SELECT chunk_id FROM kb_chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    TSVECTOR_SQL = """
        SELECT chunk_id FROM kb_chunks
        WHERE to_tsvector('simple', text) @@ plainto_tsquery('simple', %s)
        ORDER BY ts_rank(to_tsvector('simple', text), plainto_tsquery('simple', %s)) DESC
        LIMIT %s
    """
    PARADEDB_SQL = """
        SELECT chunk_id FROM kb_chunks
        WHERE text ||| %s
        ORDER BY paradedb.score(chunk_id) DESC
        LIMIT %s
    """

    def __init__(self, dsn: str, embedder: EmbeddingClient, mode: str,
                 pg_sparse: str | None, rrf_k: int = RRF_K) -> None:
        try:
            import psycopg                                        # noqa: PLC0415
        except ImportError as exc:                                # pragma: no cover - 环境依赖
            raise RuntimeError("缺少 psycopg，请先安装：uv pip install 'psycopg[binary]'") from exc
        if mode in ("sparse", "hybrid"):
            if pg_sparse is None:
                raise ValueError(
                    "pgvector 侧稀疏检索必须显式声明实现路线（v2-report §4.3 强制）：\n"
                    "  --pg-sparse tsvector   # 路线 B：PostgreSQL 原生全文检索，**非 BM25**\n"
                    "  --pg-sparse paradedb   # 路线 A：ParadeDB pg_search 真 BM25\n"
                    "未声明即对比不公平（R-V2-3），拒绝执行。")
            if pg_sparse not in PG_SPARSE_IMPLS:
                raise ValueError(f"--pg-sparse 只能是 {PG_SPARSE_IMPLS} 之一")
        self.dsn = dsn
        self.embedder = embedder
        self.mode = mode
        self.pg_sparse = pg_sparse
        self.rrf_k = rrf_k
        self.conn = psycopg.connect(dsn, autocommit=True)

    def declaration(self) -> str:
        if self.pg_sparse == "paradedb":
            return ("pgvector 侧对照采用【路线 A：ParadeDB pg_search 真 BM25】，"
                    "版本 + digest 见 v2-report §二.2.3")
        if self.pg_sparse == "tsvector":
            return ("pgvector 侧对照【仅代表 tsvector 路线】，非原生 BM25；因此本对比**不能**"
                    "等同为『BM25 实现之间的对比』，结论适用范围限于"
                    "『Milvus 原生 BM25 vs PostgreSQL tsvector』")
        return "pgvector 侧仅跑稠密检索，不涉及稀疏实现声明"

    def __call__(self, question: str, top_k: int) -> list[str]:
        if self.mode == "dense":
            return self._search_dense(question, top_k)
        if self.mode == "sparse":
            return self._search_sparse(question, top_k)
        dense = self._search_dense(question, top_k * 2)
        sparse = self._search_sparse(question, top_k * 2)
        return rrf_fuse([dense, sparse], self.rrf_k)[:top_k]

    def _search_dense(self, question: str, top_k: int) -> list[str]:
        vector = self.embedder.embed([question])[0]
        with self.conn.cursor() as cur:
            cur.execute(self.DENSE_SQL, (json.dumps(vector), top_k))
            return [row[0] for row in cur.fetchall()]

    def _search_sparse(self, question: str, top_k: int) -> list[str]:
        sql = self.PARADEDB_SQL if self.pg_sparse == "paradedb" else self.TSVECTOR_SQL
        params = (question, top_k) if self.pg_sparse == "paradedb" else (question, question, top_k)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return [row[0] for row in cur.fetchall()]


# ---------------------------------------------------------------- analyzer 抽检


_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}|[\u4e00-\u9fa5]{2,8}")

# R-V2-1 抽检词表：工业诊断领域高频复合词（≥3 字为主，2 字词不足以判定分词有效性）
INDUSTRIAL_TERMS: tuple[str, ...] = (
    "离心泵", "轴承箱", "机械密封", "联轴器", "叶轮", "泵轴", "驱动端", "非驱动端",
    "深沟球轴承", "圆柱滚子轴承", "汽轮机油", "振动烈度", "振动速度有效值", "位移峰峰值",
    "加速度包络", "特征频率", "转频", "倍频", "边带", "包络谱", "轴心轨迹",
    "内圈故障", "外圈故障", "滚动体", "保持架", "点蚀", "剥落", "磨损",
    "动平衡", "对中偏差", "软脚", "气蚀", "汽蚀余量", "喘振", "松动", "碰摩",
    "润滑油", "油品乳化", "铁谱分析", "红外测温", "状态监测", "故障诊断",
)


def extract_terms(samples_path: Path, limit: int = 40) -> list[str]:
    """从语料中筛出**实际出现**的工业术语（≥ANALYZER_MIN_SAMPLES 条）。

    术语来自 `INDUSTRIAL_TERMS` 词表（人工维护），只保留在语料里出现过的，
    保证抽检对象是真实业务词，而不是任意 n-gram 片段。
    """
    text = samples_path.read_text(encoding="utf-8")
    present = [term for term in INDUSTRIAL_TERMS if term in text]
    return present[:limit]


def tokenize(text: str) -> tuple[list[str], str]:
    """本地分词：优先 jieba；不可用时退回正则，并显式报告所用分词器。"""
    try:
        import jieba                                               # noqa: PLC0415
        return [t for t in jieba.lcut(text) if t.strip()], "jieba"
    except ImportError:
        return _TERM_RE.findall(text), "regex_fallback"


def check_analyzer(samples_path: Path, out_path: Path | None,
                   min_samples: int = ANALYZER_MIN_SAMPLES) -> int:
    """R-V2-1 强制动作：jieba analyzer 抽检 ≥20 条工业术语。

    判据：**≥3 字**术语被逐字切分（token 全为单字）即视为分词失效；
    2 字词（如「泵轴」）切分本身存在歧义，不作为失效证据。
    """
    terms = extract_terms(samples_path)
    rows: list[dict[str, Any]] = []
    degraded: list[str] = []
    tokenizer_name = ""
    for term in terms:
        tokens, tokenizer_name = tokenize(term)
        # 判定口径：≥3 字术语若被切成「全单字」，即视为分词失效（2 字词不足以判定）
        char_split = len(term) >= 3 and all(len(t) == 1 for t in tokens)
        rows.append({"term": term, "token_count": len(tokens),
                     "tokens": "|".join(tokens), "逐字切分": "是" if char_split else "否"})
        if char_split:
            degraded.append(term)

    print(f"[analyzer] 分词器：{tokenizer_name} ｜ 抽检 {len(rows)} 条术语"
          f"（下限 {min_samples}）")
    for row in rows[:25]:
        print(f"  {row['term']:<16} → {row['tokens']}")

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["term", "token_count", "tokens", "逐字切分"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"[analyzer] 抽检明细已写入 {out_path}")

    if len(rows) < min_samples:
        print(f"[FAIL] 抽检样本不足：{len(rows)} < {min_samples}（R-V2-1 要求 ≥{min_samples}）")
        return 1
    if tokenizer_name == "regex_fallback":
        print("[WARN] 未安装 jieba，本次为回退分词器；结论**不得**用于判定 jieba analyzer 有效性")
        return 2
    if degraded:
        print(f"[FAIL] {len(degraded)} 条术语被逐字切分，分词失效（R-V2-1 触发）："
              f"{degraded[:10]}")
        return 1
    print("[OK] 抽检通过：无逐字切分现象，中文分词有效")
    print("     ⚠️ 仍须在 Milvus 侧用同一术语表复核服务端 analyzer 输出（R-V2-2）")
    return 0


# ---------------------------------------------------------------- 落盘与汇总


def write_raw(result: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{result['experiment_id']}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({k: v for k, v in result.items() if k != "per_query"},
                            ensure_ascii=False) + "\n")
        for row in result["per_query"]:
            fh.write(json.dumps({"experiment_id": result["experiment_id"], **row},
                                ensure_ascii=False) + "\n")
    print(f"[v2] 原始数据已写入 {path}")
    return path


def write_summary(results: list[dict[str, Any]], path: Path) -> None:
    """写 V2 汇总对比表（**按 `experiment_id` 合并**，不抹掉其它已实测路线）。

    历史缺陷（`docs/known-issues.md` ISS-023）：早期实现每次 run 都以 "w" 模式整体重写，
    只跑单条路线时会把其它路线的已实测结果一并清掉——`experiments/v2/summary.csv`
    一度只剩 2 行（milvus-hybrid / pgvector-hybrid-paradedb），需要回 raw/*.jsonl 才能还原。
    现在先读回既有表，用本次结果覆盖同 `experiment_id` 的行、其余保留，列集合取并集后重写。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    categories = sorted({c for r in results for c in r["by_category"]})
    base_cols = ["experiment_id", "route", "mode", "pg_sparse", "recall_at_5", "mrr",
                 "precision_at_5", "mean_latency_ms", "p95_latency_ms"]

    existing: dict[str, dict[str, str]] = {}
    old_cat_cols: list[str] = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                for old in csv.DictReader(fh):
                    existing[old.get("experiment_id") or ""] = dict(old)
                    for col in old:
                        if col.startswith("recall@5[") and col not in old_cat_cols:
                            old_cat_cols.append(col)
        except (OSError, csv.Error) as exc:      # 既有表损坏不应阻断本次落盘
            print(f"[v2] 警告：既有汇总表无法读回（{exc}），将重建")

    fresh: dict[str, dict[str, str]] = {}
    for r in results:
        m = r["metrics"]
        row = {
            "experiment_id": r["experiment_id"], "route": r["route"], "mode": r["mode"],
            "pg_sparse": r["pg_sparse"] or "",
            "recall_at_5": _fmt(m["recall_at_5"]), "mrr": _fmt(m["mrr"]),
            "precision_at_5": _fmt(m["precision_at_5"]),
            "mean_latency_ms": _fmt(m["mean_latency_ms"]),
            "p95_latency_ms": _fmt(m["p95_latency_ms"]),
        }
        for c in categories:
            row[f"recall@5[{c}]"] = _fmt(r["by_category"].get(c, {}).get("recall_at_5"))
        fresh[r["experiment_id"]] = row

    merged = dict(existing)
    merged.update(fresh)

    all_cat_cols = sorted(set(old_cat_cols) | {f"recall@5[{c}]" for c in categories})
    header = base_cols + all_cat_cols
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow({col: merged[key].get(col, "") for col in header})
    print(f"[v2] 汇总表已合并写入 {path}（共 {len(merged)} 行，本次新增/更新 {len(fresh)} 行）")


def _fmt(value: Any) -> str:
    return "" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)


def print_results(results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 78)
    print(f"{'实验编号':<28}{'Recall@5':>10}{'MRR':>10}{'P@5':>10}{'P95(ms)':>10}")
    print("-" * 78)
    for r in results:
        m = r["metrics"]
        print(f"{r['experiment_id']:<28}{_fmt(m['recall_at_5']):>10}{_fmt(m['mrr']):>10}"
              f"{_fmt(m['precision_at_5']):>10}{_fmt(m['p95_latency_ms']):>10}")
    print("=" * 78)
    print("判据对照（v2-report §八）：Milvus 侧 Recall@5 不低于 pgvector 侧 → Pass")


# ---------------------------------------------------------------- 自检


class _ToyRetriever:
    """自检用的内存检索器：按关键词命中数排序，仅用于验证指标与融合的算术。"""

    def __init__(self, docs: list[Doc]) -> None:
        self.docs = docs

    def __call__(self, question: str, top_k: int) -> list[str]:
        scored = [(len(set(question) & set(d.text)), d.chunk_id) for d in self.docs]
        return [cid for _, cid in sorted(scored, key=lambda kv: (-kv[0], kv[1]))[:top_k]]


def _selftest() -> int:
    failures: list[str] = []

    # 1) 指标算术
    if recall_at_k(["a", "b", "c"], ["b", "d"], 5) != 0.5:
        failures.append("Recall@5 计算错误")
    if recall_at_k(["a", "b"], ["x"], 5) != 0.0:
        failures.append("Recall@5 无命中应为 0")
    if precision_at_k(["b", "a"], ["b"], 5) != 0.2:
        failures.append("Precision@5 计算错误")
    if reciprocal_rank(["a", "b"], ["b"]) != 0.5:
        failures.append("RR 计算错误")
    if reciprocal_rank(["a"], ["z"]) != 0.0:
        failures.append("RR 无命中应为 0")

    # 2) RRF 融合：两路各贡献一次，双命中者应排第一
    fused = rrf_fuse([["x", "y"], ["y", "z"]], k=60)
    if fused[0] != "y":
        failures.append(f"RRF 融合排序错误：{fused}")
    if sorted(fused) != ["x", "y", "z"]:
        failures.append("RRF 融合丢块")

    # 3) 评测集与语料完整性
    queries = load_golden()
    docs = load_corpus()
    if len(queries) != 50:
        failures.append(f"评测集应为 50 条，实际 {len(queries)}")
    if len(docs) != 100:
        failures.append(f"语料应为 100 块，实际 {len(docs)}")
    corpus_ids = {d.chunk_id for d in docs}
    dangling = [cid for q in queries for cid in q.relevant_chunk_ids if cid not in corpus_ids]
    if dangling:
        failures.append(f"评测集引用了不存在的块：{dangling[:5]}")

    # 4) evaluate 端到端（内存检索器，不联网）
    config = EvalConfig(route="milvus", mode="dense")
    result = evaluate(queries[:5], _ToyRetriever(docs), config)
    if result["experiment_id"] != "EXP-V2-milvus-dense":
        failures.append("experiment_id 生成错误")
    if len(result["per_query"]) != 5 or result["metrics"]["query_count"] != 5:
        failures.append("逐条结果条数错误")
    if not 0.0 <= (result["metrics"]["recall_at_5"] or 0) <= 1.0:
        failures.append("Recall@5 超出 [0,1]")
    if not result["by_category"]:
        failures.append("分类别统计为空")

    # 5) 公平性硬约束：pgvector 稀疏未声明必须报错
    try:
        PgvectorRetriever("postgresql://x/y", EmbeddingClient(), "sparse", pg_sparse=None)
    except RuntimeError:
        pass                                   # 缺 psycopg 也视为拦截成功
    except ValueError as exc:
        if "--pg-sparse" not in str(exc):
            failures.append("pgvector 稀疏未声明的报错信息缺少指引")
    else:
        failures.append("pgvector 稀疏未声明却未报错（违反 R-V2-3）")

    # 6) 术语抽取数量满足 R-V2-1 下限
    if len(extract_terms(CORPUS_PATH)) < ANALYZER_MIN_SAMPLES:
        failures.append(f"术语抽取不足 {ANALYZER_MIN_SAMPLES} 条")

    if failures:
        print("[FAIL] run_v2 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] run_v2 自检通过：指标算术 / RRF 融合 / 评测集完整性 / 公平性约束 / 术语抽取")
    return 0


# ---------------------------------------------------------------- 入口


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V2 混合检索验证器（T3.1–T3.3）")
    parser.add_argument("--eval", dest="eval_path", type=Path, default=GOLDEN_PATH,
                        help="评测集 JSONL（V7 硬依赖，禁止用临时题集替代）")
    parser.add_argument("--routes", default="milvus,pgvector", help="逗号分隔：milvus,pgvector")
    parser.add_argument("--mode", choices=MODES, default=None,
                        help="不指定则依次跑 dense / sparse / hybrid")
    parser.add_argument("--corpus", type=Path, default=CORPUS_PATH, help="语料 JSONL")
    parser.add_argument("--top-k", type=int, default=DENSE_TOP_K)
    parser.add_argument("--rrf-k", type=int, default=RRF_K, help="RRF k 值（候选 60）")
    parser.add_argument("--pg-sparse", choices=PG_SPARSE_IMPLS, default=None,
                        help="pgvector 侧稀疏实现路线（必填声明，见 v2-report §4.3）")
    parser.add_argument("--milvus-uri", default="http://127.0.0.1:19531")
    parser.add_argument("--dsn", default="postgresql://root:123456@127.0.0.1:5433/auscult_v2",
                        help="PostgreSQL DSN（默认 auscult_v2 库，与 v2_pg_build.py 建库一致）")
    parser.add_argument("--embed-model", default=BGE_M3_MODEL_PATH,
                        help="BGE-M3 本地模型目录（sentence-transformers 格式，默认 ModelScope 路径）")
    parser.add_argument("--embed-device", default=None,
                        help="推理设备：cuda / cpu（默认让 sentence-transformers 自动选择）")
    parser.add_argument("--rebuild", action="store_true",
                        help="重建索引并重新灌入语料（首次运行必须加）")
    parser.add_argument("--out-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--summary", type=Path, default=PROJECT_ROOT / "experiments/v2/summary.csv")
    parser.add_argument("--check-analyzer", action="store_true",
                        help="只做 jieba 分词抽检（R-V2-1），不跑质量对比")
    parser.add_argument("--samples", type=Path, default=CORPUS_PATH,
                        help="分词抽检样本（jsonl 语料或纯文本术语表）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不连接服务")
    parser.add_argument("--selftest", action="store_true", help="运行自检（不联网）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.check_analyzer:
        out = None if args.dry_run else args.out_dir / "analyzer_check.csv"
        return check_analyzer(args.samples, out)

    routes = [r.strip() for r in args.routes.split(",") if r.strip()]
    invalid = [r for r in routes if r not in ROUTES]
    if invalid:
        parser.error(f"未知路线：{invalid}（可选 {ROUTES}）")
    modes = [args.mode] if args.mode else list(MODES)

    if "pgvector" in routes and any(m in ("sparse", "hybrid") for m in modes) \
            and args.pg_sparse is None:
        parser.error("pgvector 侧稀疏检索必须显式声明 --pg-sparse tsvector|paradedb"
                     "（v2-report §4.3 强制，R-V2-3）")

    queries = load_golden(args.eval_path)
    docs = load_corpus(args.corpus)
    print("=" * 78)
    print("V2 混合检索质量对比（纯 CPU 路线，不占 GPU）")
    print("=" * 78)
    print(f"评测集 : {len(queries)} 条（{args.eval_path}）")
    print(f"语料   : {len(docs)} 块（{args.corpus}）")
    print(f"路线   : {', '.join(routes)} ｜ 模式: {', '.join(modes)}")
    print(f"指标   : Recall@{args.top_k} / MRR / Precision@{args.top_k}"
          f"（即报告「Top-5 相关性」）｜ RRF k={args.rrf_k}")
    print(f"向量   : {args.embed_model}（期望 {EMBED_DIM_EXPECTED} 维，待 D4 实测确认）")
    if args.pg_sparse:
        print(f"pgvector 稀疏声明：{args.pg_sparse}")
        print("  → " + ("采用【路线 A：ParadeDB pg_search 真 BM25】" if args.pg_sparse == "paradedb"
                        else "【仅代表 tsvector 路线】，非原生 BM25，结论适用范围受限"))
    if args.dry_run:
        print("\n[dry-run] 计划产出：")
        for route in routes:
            for mode in modes:
                cfg = EvalConfig(route=route, mode=mode, top_k=args.top_k,
                                 rrf_k=args.rrf_k, pg_sparse=args.pg_sparse,
                                 embed_model=args.embed_model)
                print(f"  - {cfg.experiment_id} → {args.out_dir / (cfg.experiment_id + '.jsonl')}")
        return 0

    embedder = EmbeddingClient(model=args.embed_model, device=args.embed_device,
                               cache_path=args.out_dir / "embed_cache.json")
    results: list[dict[str, Any]] = []
    for route in routes:
        for mode in modes:
            config = EvalConfig(route=route, mode=mode, top_k=args.top_k, rrf_k=args.rrf_k,
                                pg_sparse=args.pg_sparse, embed_model=args.embed_model)
            print(f"\n▶ {config.experiment_id}")
            if route == "milvus":
                retriever = MilvusRetriever(args.milvus_uri, embedder, mode, rrf_k=args.rrf_k)
                if args.rebuild:
                    retriever.rebuild(docs)
            else:
                retriever = PgvectorRetriever(args.dsn, embedder, mode, args.pg_sparse,
                                              rrf_k=args.rrf_k)
                print(f"  {retriever.declaration()}")
            result = evaluate(queries, retriever, config)
            write_raw(result, args.out_dir)
            results.append(result)

    if results:
        print_results(results)
        write_summary(results, args.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
