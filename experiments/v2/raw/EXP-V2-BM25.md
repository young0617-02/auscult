# EXP-V2-BM25 —— Milvus 原生 BM25（jieba）vs ParadeDB 真 BM25（ngram）对标

> **编号**：EXP-V2-BM25
> **日期**：2026-09-28
> **目的**：补齐 **M0.3** 真 BM25 稀疏对标（`K-V2-1` 遗留 P1 专项）
> **状态**：✅ 已完成
> **关联**：`reports/v2-report.md` §四.3 / §四.4 / §五 / §七 · `experiments/v2/raw/K-V2-1.md`
> **评测集**：`evals/golden_set_v1.jsonl`（50 条）· 语料 `evals/corpora_v1/corpus_100.jsonl`（100 块）
> **环境**：Milvus v3.0.0（服务端 `FunctionType.BM25` + jieba）+ ParadeDB `pg_search` 0.25.10（ngram）· PG 容器 `auscult-v2-pg` :5433，库 `auscult_v2`
> **初始化**：`experiments/v2/raw/bm25_init.sql`（`CREATE INDEX ... USING bm25`，`key_field='chunk_id'` + `tokenizer:{type:'ngram',min_gram:2,max_gram:3,prefix_only:false}`）

---

## 一、方法

1. 用 K-V2-1 正解为 `kb_chunks` 建真 BM25 索引（已灌入 100 块 corpus，主键 `chunk_id`）。
2. 冒烟：`WHERE text ||| '离心泵'` 返回 2 块、score 递减（`|||` 算子与 ngram 索引兼容，无需改 `PARADEDB_SQL`）。
3. `run_v2.py --routes milvus,pgvector --pg-sparse paradedb --mode sparse,hybrid`（同一批 50 query，`--dsn` 显式指向 `auscult_v2` 库）。

## 二、结果

| 实验 | `Recall@5` | MRR | P@5 | P95(ms) |
|---|---|---|---|---|
| **EXP-V2-milvus-sparse** | **0.9200** | 0.8700 | 0.2560 | 4.5180 |
| EXP-V2-pgvector-sparse-paradedb | 0.9000 | 0.8673 | 0.2480 | 10.4480 |
| EXP-V2-milvus-hybrid | 0.9100 | 0.9300 | 0.2520 | 110.0240 |
| EXP-V2-pgvector-hybrid-paradedb | 0.9100 | 0.9367 | 0.2480 | 10.8570 |

### 分类别（pgvector-sparse-paradedb，`Recall@5`）

| 类别 | `Recall@5` | query 数 |
|---|---|---|
| 设备手册 | 0.8571 | 7 |
| 维护规程 | 0.8571 | 7 |
| 故障诊断 | 0.9375 | 8 |
| 振动标准 | 1.0000 | 8 |
| 安全规范 | 1.0000 | 6 |
| 历史工单 | 0.7143 | 7 |
| 传感器与测量 | 0.9286 | 7 |

## 三、结论

1. **ParadeDB 真 BM25（ngram）对中文 `Recall@5`=0.90**，相较 tsvector（**=0**，K-V2-2）**显著提升**，已逼近 Milvus（0.92）。
2. **sparse 直接对比**：Milvus 0.92 **≥** pgvector 0.90 → 判据 **Pass**（Milvus 原生 BM25 仍为最优）。
3. **hybrid 打平**：0.91 = 0.91（pgvector MRR 0.9367 略高，但 Recall@5 相同）。
4. **口径声明（R-V2-3）**：ngram(2,3) 做**子串召回**（覆盖面好、含子串噪声），jieba 做**语义分词**；两实现数值差异**属分词口径所致，不据此改写既有选型**（Milvus 仍主路线，见 v2-report §七）。

## 四、M0.3 判定

> **真 BM25 稀疏对标闭环**：『Milvus 原生 BM25 vs ParadeDB 真 BM25』已实测，结论范围从「仅 Milvus BM25 vs tsvector」扩大为「含两实现 BM25 对比」。
> Milvus 主路线地位不变（sparse 0.92 ≥ 0.90）；pgvector 真 BM25 可作为中文稀疏备选（0 提升至 0.90）。

## 五、遗留 / 后续

- [x] P0 交付：两 BM25 实现的 **10 万块压力档**（延迟/内存）**已实测**（`EXP-V2-LOAD`，2026-09-28，`experiments/v2/raw/EXP-V2-LOAD/`）：M0.3 条件项全解除——10 万块 Milvus 查询 P95 5.6 ms/常驻峰值 1.28 GB vs pgvector 170.6 ms/0.33 GB，均 ≪ Docker ≈20 GB（`v2-report` §六）。
- [ ] 双 BM25 的工程运维面完整对比（常驻内存/磁盘）待 P1。

---
## 复现

```powershell
# 2）建立 bm25 索引（幂等）
Get-Content experiments\v2\raw\bm25_init.sql -Raw | docker exec -i auscult-v2-pg psql -U root -d auscult_v2

# 3）跑对标（venv）
.venv\Scripts\python.exe scripts/run_v2.py --eval evals\golden_set_v1.jsonl `
  --routes milvus,pgvector --pg-sparse paradedb --mode sparse,hybrid `
  --dsn "postgresql://root:123456@127.0.0.1:5433/auscult_v2" `
  --milvus-uri "http://127.0.0.1:19531" --out-dir experiments\v2\raw\EXP-V2-BM25
```

> ⚠️ 注意：`run_v2.py` 默认 `--dsn` 库名为 `postgres`，而 `kb_chunks` 建在 **`auscult_v2`** 库——须显式 `--dsn` 指向 `auscult_v2`，否则连不到表。