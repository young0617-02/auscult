-- K-V2-1 闭环：ngram + prefix_only 真 BM25
DROP TABLE IF EXISTS tmp_bm25_test;
CREATE TABLE tmp_bm25_test (chunk_id text PRIMARY KEY, text text);
INSERT INTO tmp_bm25_test VALUES
  ('c1', '离心泵轴承振动异常诊断 振动速度有效值 报警值'),
  ('c2', '泵轴承温度过高原因分析'),
  ('c3', '离心泵最小流量 径向力 温升影响');

CREATE INDEX tmp_bm25_idx
  ON tmp_bm25_test
  USING bm25 (chunk_id, text)
  WITH (
    key_field = 'chunk_id',
    text_fields = '{"text": {"type": "text", "tokenizer": {"type": "ngram", "min_gram": 2, "max_gram": 3, "prefix_only": false}}}'
  );

INSERT INTO tmp_bm25_test VALUES ('c4', '泵轴承游隙变化 振动频谱特征');
INSERT INTO tmp_bm25_test VALUES ('c5', '离心泵最小流量 径向力');
SELECT chunk_id, text FROM tmp_bm25_test ORDER BY chunk_id;

SELECT chunk_id, paradedb.score(chunk_id)::numeric(6,4) AS score
FROM tmp_bm25_test WHERE text @@@ '离心泵'
ORDER BY paradedb.score(chunk_id) DESC LIMIT 5;