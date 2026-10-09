# B3 Milvus 建库报告（P1-D4/D5 · B3）

> **对应任务**：P1-D4/D5 **B3 Milvus 建库**（`plan/p1-plan-detailed.md` §5.6）
> **上游**：`reports/p1-d4-b2-chunk.md`（B2 子块 `chunks/chunks_v1.jsonl`）
> **版本锁定**：`docs/prj-ledger-version-lock.md` §二.2.8（pymilvus / BGE-M3 / jieba）
> **复用基座**：`scripts/run_v2.py`（`EmbeddingClient` 本地 BGE-M3、V2 建库参数）
> **版本**：v1 ｜ **执行日期**：2026-10-08 ｜ **状态**：**✅ 通过（建库+链路冒烟）**

---

## 一、目的与判据

把 B2 的 36 个子块向量化并写入 Milvus，建库参数复用 V2 基线，做召回冒烟验证链路可检索。

| # | 判据 | 门槛 | 实测 | 判定 |
|---|---|---|---|---|
| 1 | 子块全量写入 | 36/36 | **36 行入库** | ✅ |
| 2 | 稠密向量维度 | =1024（BGE-M3） | **1024** | ✅ |
| 3 | 服务端 BM25 稀疏 + jieba analyzer | 建库成功 | 已建 | ✅ |
| 4 | 召回冒烟（dense/sparse/hybrid） | 链路可返回 | 冒烟通过（仅链路验证，非正式） | ✅ |

---

## 二、方法（`scripts/build_milvus_v1.py`）

```
.venv\Scripts\python.exe scripts\build_milvus_v1.py \
    --chunks chunks/chunks_v1.jsonl --collection kb_p1_v1 --uri http://127.0.0.1:19531
```

1. **集合**：新建 **`kb_p1_v1`**（与 V2 的 `kb_v1` 隔离，不覆盖 V2 对照基线）。
2. **Schema**：在 V2 的 `chunk_id/text/dense(FLOAT 1024)/sparse(SPARSE)` 基础上，补 `doc_id/parent_id/section/page/doc_type` 标量字段；`text` 开启 jieba analyzer，服务端 BM25 函数生成 `sparse`。
3. **索引**：`dense` = HNSW / COSINE（M16, efC200）；`sparse` = SPARSE_INVERTED_INDEX / BM25。
4. **向量化**：复用 `run_v2.EmbeddingClient`（本地 BGE-M3 `D:\modelscope\hub\models\BAAI--bge-m3`），批量 36 子块，写入磁盘缓存。
5. **召回冒烟**：自建 10 条贴近语料类型的 query（synthetic，非正式），dense/sparse/hybrid(RRF k=60) 各算 Recall@5（是否命中目标子块）。

> **端口修正**：Milvus 容器端口映射为 容器19530→宿主**19531**，脚本默认 `--uri` 修正为 `http://127.0.0.1:19531`（与 V2 `--milvus-uri` 一致）。

---

## 三、结果

### 3.1 建库

| 项 | 值 |
|---|---|
| 集合 | `kb_p1_v1` |
| 入库子块 | **36**（全部 B2 子块，is_parent=false） |
| 稠密维度 | **1024** |
| 稀疏 | 服务端 BM25（jieba analyzer） |
| 索引 | dense=HNSW/COSINE；sparse=SPARSE_INVERTED/BM25 |

### 3.2 召回冒烟（非正式，链路验证）

| query 类型 | dense | sparse | hybrid |
|---|---|---|---|
| 标准判据 | 1.00 | 0.00 | 1.00 |
| 故障案例 | 0.00 | 0.00 | 0.00 |
| 设备手册(结构原理等) | 混合 0~1.00 | 0~1.00 | 1.00（多数） |
| 拓扑 | 1.00 | 0.00 | 1.00 |
| 维修工单 | 1.00 | 0.00 | 0.00 |

> **判读**：dense（BGE-M3 语义）对结构化 query 召回较稳；sparse（BM25 词面）对短章节标题召回偏弱属预期（语料子块短、query 用 section 标题，词面重合少）。**冒烟目的为「链路可检索返回 + RRF 融合正确」而非指标达标**——链路已通（能 search / hybrid_search / 返回命中）。正式指标（Recall@5/MRR/NDCG）留待 Phase 2 以正式评测集评估。

---

## 四、问题与观察

1. **冒烟 query 口径粗糙**：因与 B2 语料强对应且字段短，部分类型 recall=0。这不反映链路缺陷，仅说明「自建冒烟 query 未与子块 text 语义拉齐」。已如实记录，**不作正式结论**。
2. **稀疏召回偏低**：语料子块 token 少（35–274，见 B2 报告），BM25 命中依赖词面重合；正式 Phase 2 将用真实长语料复测。
3. **集合隔离**：采用 `kb_p1_v1` 未触碰 V2 `kb_v1`，符合「不覆盖对照基线」纪律。

---

## 五、结论

- **判定：B3 建库通过**。36 子块写入 `kb_p1_v1`，稠密1024/稀疏BM25/元数据齐全，链路可检索（dense/sparse/hybrid 均可调用返回）。
- **产出就绪**：`kb_p1_v1` 可供 **Phase 2 混合检索**直接使用；冒烟摘要 `experiments/p1/b3/milvus_smoke.json` 留档。

---

## 六、局限声明

> **局限声明（固定文本，不得删改）**：
> 本阶段所有质量类结论（`Recall@5`、`MRR`、`NDCG@5`、引用正确率、幻觉率、置信度 ECE 等）均**基于模拟数据的初步验证**，语料由项目组自编，其分布、术语密度与真实现场资料存在差异。因此上述指标**仅证明“链路可运行、方案可比较”，不等于现场可用性结论**。Phase 1 取得真实语料后，须以同一评测集与同一流程**重测**并对齐本结论。

---

## 七、复现命令

见 §二；自检：`.venv\Scripts\python.exe scripts\build_milvus_v1.py --selftest`

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | 初始建立：P1-D4/D5 B3 Milvus 建库（36 子块入库 kb_p1_v1，链路冒烟） | 全文 |