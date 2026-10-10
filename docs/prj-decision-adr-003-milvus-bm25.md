# ADR-003：Milvus + 服务端 BM25（jieba analyzer），检索融合默认 RRF-only

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：Milvus/BM25 路径于 `plan/工业设备诊断 Agent.md` §3.2 定稿（2026-09-21，V5.0 定稿，"已核实，不再是假设"）；RRF-only 裁决为 P2 D7 消融实测产物（2026-10-09 前后，登记于 `docs/prj-ledger-version-lock.md` §二.2.20）。

## 二、背景（Context）

- 混合检索需要 Sparse（BM25）与 Dense（BGE-M3）互补：BM25 提供精确词面匹配，Dense 提供语义召回（`plan/工业设备诊断 Agent.md` §6.2）。
- BM25 有服务端（Milvus Function）与客户端（`BM25EmbeddingFunction`）两条实现路径，须裁决（同上 §零"事实冲突"行）。
- **中文分词是成败关键**：Milvus 默认 `standard` 分析器对中文近乎无效，必须配置 `jieba` tokenizer（同上 §3.2；风险 R6/R-M6"中文分词器无效/失效"）。

## 三、决策（Decision）

| # | 决策项 | 定稿口径 | 出处 |
|---|---|---|---|
| 1 | 向量库 | **Milvus Standalone**（版本/镜像 digest 见 `docs/prj-ledger-version-lock.md` §二.2.1，不抄写） | `plan/工业设备诊断 Agent.md` §3.1/§3.2 |
| 2 | BM25 实现路径 | **服务端 `FunctionType.BM25`**：属 Milvus 内部"本地文本函数"，无需模型推理或外部集成；**稀疏向量由服务端自动生成**（写入时 Analyzer 分词 → TF/DF/平均长度 → 稀疏嵌入 + 倒排；查询同一 Analyzer 保证分词一致） | `plan/工业设备诊断 Agent.md` §3.2 核实结论 |
| 3 | 字段与索引 | 文本字段 `enable_analyzer=True`；稀疏字段 `SPARSE_FLOAT_VECTOR`；索引 `SPARSE_INVERTED_INDEX` + `metric_type="BM25"`，参数 `bm25_k1=1.2`、`bm25_b=0.75`；插入/查询**只传原始文本** | 同上 §3.2 |
| 4 | 中文分词 | 自定义分析器配 **`jieba` tokenizer**（依赖 `jieba==0.42.1` 已锁，见 `docs/prj-ledger-version-lock.md` §二.2.8）；须做分词结果人工抽检 | 同上 §3.2；`requirements.txt` |
| 5 | 融合 | Dense + Sparse 并行召回 → **RRF 融合（k=60）**；融合参数集中 `configs/retrieval.yml`（weights：dense 0.6 / sparse 0.4） | 同上 §6.2；`docs/prj-ledger-version-lock.md` §二.2.16 |

### 3.1 补充裁决：检索融合默认 RRF-only（rerank 降为可选增强）

| 项 | 口径 | 出处 |
|---|---|---|
| 消融实测 | D7 消融（`scripts/d7_ablation.py`，12 题配套评测集）：rerank **ΔMRR = −0.0417（净负效果）**——2 题帮助、2 题伤害；根因 = 当前语料极小（36 子块），RRF 双路信号已足够排序，rerank 引入噪声 | `docs/prj-ledger-version-lock.md` §二.2.20 裁定口径段 |
| 指标变化 | RRF-only 使 **MRR 0.7153 → 0.7569**（≥0.75 过线）；**P95 = 86.1ms**（较 GPU rerank 353.2ms 再降 76%），RRF-only 与 GPU rerank 双双 <800ms 达标 | 同上 |
| 定稿 | **默认走 RRF-only**；reranker（`BAAI--bge-reranker-v2-m3`，已选用并锁定）保留为可选增强（`RetrievalService` `use_rerank` 开关），GPU 环境保留供语料扩大后重评 | 同上；`docs/prj-ledger-version-lock.md` §二.2.2.2 |
| 口径说明 | 架构文档 §二 检索层写"RRF + reranker"为**能力组成口径**；运行默认 RRF-only（`use_rerank` 可开）。P5 终值：Recall@5 = 1.0、MRR = 0.7986、P95 检索 = 159.4ms（`docs/p5-handover-p6.md` §二） | 本 ADR（综合出处） |

## 四、备选方案与放弃理由（Options & Rejected）

| 备选 | 放弃理由 | 出处 |
|---|---|---|
| 客户端 `BM25EmbeddingFunction` | 服务端 BM25 声明式、服务端一致性更好、新增语料自动更新统计、P1 建库工程量最小 | `plan/工业设备诊断 Agent.md` §3.2 裁决 |
| 纯 Dense 单路检索 | 实测同表**稠密单路 P95 = 2061.9ms 超线**（混合 RRF 9.48ms 达标）——混合路线是达标前提 | `docs/p0-spec-scope-mvp.md` §七 Q6 行 |
| rerank 默认开启 | D7 消融 ΔMRR = −0.0417 净负（小语料引噪），且延迟高 4 倍以上 | `docs/prj-ledger-version-lock.md` §二.2.20 |

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | BM25 零模型推理成本、服务端自动维护统计；中文 jieba 分词可控；RRF-only 延迟极低（P95 86.1ms）且 MRR 达标 |
| ⚠️ 负面 | rerank 在当前小语料为净负，能力闲置（保留开关待语料扩大重评）；golden 50 题与真实语料内容脱节，全部指标待扩语料重评（`docs/p5-handover-p6.md` §五） |
| 📎 已知边界 | M2.3 指标基于 12 题配套评测集（非 golden 50 题），勿混淆口径（`docs/prj-ledger-version-lock.md` §二.2.20 黄金集约束）；D7 结论的适用前提是"小语料"，语料扩充后须重评 rerank |

## 六、事实源

- `plan/工业设备诊断 Agent.md` §3.2、§6.2、§8.1（R6）
- `docs/prj-ledger-version-lock.md` §二.2.1、§二.2.2.2、§二.2.8、§二.2.16、§二.2.20
- `docs/p0-spec-scope-mvp.md` §七（Q1/Q2/Q6）
- `docs/p5-handover-p6.md` §二
- `requirements.txt`（`jieba==0.42.1`）
- `reports/p2-d3-m2-metrics.md`（M2.3 检索质量与 D7/D11 实测）

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版 | 本文件 |
