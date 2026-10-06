"""V2 pgvector 对照路线建库 / 灌数脚本（D4，压力档改造）。

`run_v2.py` 的 PgvectorRetriever 只检索、不建库（仅 Milvus 有 `--rebuild`）。
本脚本补齐 pgvector 对照侧的 `kb_chunks` 表 + `vector`/`pg_search` 扩展，
并按 `--ingest-mode` 灌入语料：

  - `dense`（默认）：embedding 填 BGE-M3 向量（维度 1024，复用 run_v2 嵌入客户端）；
  - `sparse`（压力档）：embedding 填 `NULL`（隔离 dense embedding，避免长时调用 bge-m3），
    仅建 BM25 稀疏索引。

表结构需与 `run_v2.py` PgvectorRetriever 约定一致：
  kb_chunks(chunk_id text PRIMARY KEY, text text, embedding vector(1024))
稀疏检索用 `--pg-sparse paradedb`（R-V2-3 显式声明，走 `|||` 真 BM25）。

★ 压力档已按 K-V2-1 正解追加 `kb_bm25` 索引（`USING bm25` + ngram tokenizer），
  与 `experiments/v2/raw/bm25_init.sql` 保持一致（该 SQL 幂等可重建）。
  ⚠️ 本脚本 `DROP TABLE kb_chunks`，会连同 bm25 索引一并重建；压测后需恢复 EXP-V2-BM25
  环境时执行 `bm25_init.sql` 即可。

用法（在本仓库 `.venv` 下）：
  python scripts/v2_pg_build.py --dsn postgresql://root:123456@127.0.0.1:5433/auscult_v2 --corpus experiments/v2/raw/corpora_v2/corpus_10000.jsonl --ingest-mode sparse
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_v2 import BGE_M3_MODEL_PATH, EMBED_DIM_EXPECTED, EmbeddingClient, load_corpus  # noqa: E402

DEFAULT_DSN = "postgresql://root:123456@127.0.0.1:5433/auscult_v2"

# K-V2-1 正解 BM25 索引（ngram tokenizer，幂等；与 experiments/v2/raw/bm25_init.sql 一致）
BM25_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS kb_bm25 ON kb_chunks USING bm25 (chunk_id, text) "
    "WITH (key_field='chunk_id', "
    "text_fields='{\"text\":{\"type\":\"text\",\"tokenizer\":"
    "{\"type\":\"ngram\",\"min_gram\":2,\"max_gram\":3,\"prefix_only\":false}}}')"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="V2 pgvector/ParadeDB 对照侧建库+灌数")
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="PostgreSQL 连接串")
    parser.add_argument("--corpus", type=Path, default=None, help="语料 jsonl")
    parser.add_argument("--ingest-mode", choices=("dense", "sparse"), default="dense",
                        help="dense=灌 BGE-M3 向量（默认）；sparse=压力档，embedding 填 NULL")
    parser.add_argument("--embed-model",
                        default=BGE_M3_MODEL_PATH,
                        help="BGE-M3 本地模型目录（sentence-transformers 格式，默认 ModelScope 路径）")
    parser.add_argument("--embed-device", default=None,
                        help="推理设备：cuda / cpu（默认让 sentence-transformers 自动选择）")
    parser.add_argument("--batch", type=int, default=16, help="批次嵌入大小")
    args = parser.parse_args()

    import psycopg  # noqa: PLC0415（本地依赖，延迟导入保持入口轻量）

    corpus_path = args.corpus or PROJECT_ROOT / "evals" / "corpora_v1" / "corpus_100.jsonl"
    docs = load_corpus(corpus_path)
    print(f"语料：{len(docs)} 段（{corpus_path}）｜灌数模式：{args.ingest_mode}")

    embedder = EmbeddingClient(model=args.embed_model, device=args.embed_device) \
        if args.ingest_mode == "dense" else None

    with psycopg.connect(args.dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
            cur.execute("DROP TABLE IF EXISTS kb_chunks")
            cur.execute(
                f"CREATE TABLE kb_chunks (chunk_id text PRIMARY KEY, "
                f"text text, embedding vector({EMBED_DIM_EXPECTED}))"
            )
            cur.execute(BM25_INDEX_SQL)
            print("扩展 vector + 表 kb_chunks 已创建，并追加 kb_bm25 真 BM25 索引（K-V2-1）")

            n = 0
            if args.ingest_mode == "sparse":
                insert_sql = (
                    "INSERT INTO kb_chunks (chunk_id, text, embedding) VALUES (%s, %s, NULL)"
                )
                cur.executemany(
                    insert_sql,
                    [(d.chunk_id, d.text) for d in docs],
                )
                n = len(docs)
                print(f"  已灌入 {n}/{len(docs)}（sparse，embedding=NULL）")
            else:
                insert_sql = (
                    "INSERT INTO kb_chunks (chunk_id, text, embedding) "
                    "VALUES (%s, %s, %s::vector)"
                )
                for i in range(0, len(docs), args.batch):
                    batch = docs[i:i + args.batch]
                    vectors = embedder.embed([d.text for d in batch])  # type: ignore[union-attr]
                    rows = [(d.chunk_id, d.text, repr(v)) for d, v in zip(batch, vectors)]
                    cur.executemany(insert_sql, rows)
                    n += len(rows)
                    print(f"  已灌入 {n}/{len(docs)}")

        # 维度/行数/索引核验
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), max(vector_dims(embedding)) FROM kb_chunks")
            cnt, dim = cur.fetchone()
            cur.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename='kb_chunks'"
                " AND indexname='kb_bm25'"
            )
            has_bm25 = cur.fetchone() is not None

    print(f"完成：表 kb_chunks 共 {cnt} 行；实测维度 = {dim if dim else 'NULL(压力档 sparse)'}"
          + ("" if (dim is None or dim == EMBED_DIM_EXPECTED) else
             f" ⚠️ ≠ 期望 {EMBED_DIM_EXPECTED}（须回填 v2-report §五）"))
    print(f"kb_bm25 索引存在：{'✅' if has_bm25 else '❌ 缺失'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())