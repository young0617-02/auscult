-- =============================================================
-- bm25_init.sql —— V2 真 BM25 对标初始化
-- 目的：为 kb_chunks 建 ParadeDB pg_search 真 BM25 索引（ngram tokenizer）
-- 对应：K-V2-1 正解（experiments/v2/raw/K-V2-1.md §三）+ EXP-V2-BM25
-- 幂等：IF NOT EXISTS，可重复执行
-- 执行（PowerShell 规避双引号转义）：
--   Get-Content experiments\v2\raw\bm25_init.sql -Raw | docker exec -i auscult-v2-pg psql -U root -d auscult_v2
-- =============================================================

CREATE INDEX IF NOT EXISTS kb_bm25
  ON kb_chunks
  USING bm25 (chunk_id, text)
  WITH (
    key_field = 'chunk_id',
    text_fields = '{"text": {"type": "text", "tokenizer": {"type": "ngram", "min_gram": 2, "max_gram": 3, "prefix_only": false}}}'
  );