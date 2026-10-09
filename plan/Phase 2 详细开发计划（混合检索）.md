# Phase 2 详细开发计划（混合检索实现）

> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §六 / §九
> **前一阶段**：Phase 1（数据接入与知识库构建）——须 **M1.4 门禁通过**后启动
> **本阶段定位**：把 Phase 1 建成的"数据底座"变成"**可用、可测、可交付的检索能力**"——实现多路召回 → 融合 → 重排 → 证据组装的完整管线，并把结果封装为 `retrieve_knowledge` 工具，供 Phase 3 Agent 直接调用。
> **执行主体**：单人（"机器并行、人串行"）
> **总工期**：20 个工作日（P2-D1 – P2-D20，占比 20%）
> **制定日期**：2026-09-23

---

## 目录

- [一、阶段目标与出口](#一阶段目标与出口)
- [二、阶段前置（Phase 1 移交物核对）](#二阶段前置phase-1-移交物核对)
- [三、工作分解（WBS）](#三工作分解wbs)
- [四、逐段计划（P2-D1 – P2-D20，按周）](#四逐段计划p2-d1--p2-d20按周)
- [五、关键模块详细设计](#五关键模块详细设计)
- [六、里程碑](#六里程碑)
- [七、验收标准与指标门禁](#七验收标准与指标门禁)
- [八、性能预算与优化手段](#八性能预算与优化手段)
- [九、风险与应对](#九风险与应对)
- [十、交付物与目录](#十交付物与目录)
- [十一、检查清单](#十一检查清单)

---

## 一、阶段目标与出口

### 1.1 阶段目标

> 在**同一评测集（`golden_set_v1.jsonl`）**下，交付一条端到端检索管线：
> **查询改写 → 多路召回（Dense / BM25 / 图谱）→ RRF 融合 → 重排 → 父块回填 → 证据组装**，
> 并达到 **`Recall@5 ≥ 85%`、`MRR ≥ 0.75`、`P95 检索 < 800ms`**，封装为 `retrieve_knowledge` 工具。

### 1.2 阶段出口（M2.4）

| 出口物 | 判据 |
|---|---|
| 检索管线 | 六环节全部实现，可配置开关做消融 |
| 指标 | `Recall@5 ≥85%`、`MRR ≥0.75`、`NDCG@5` 报告值、引用正确率 ≥90% |
| 性能 | `P95 检索 < 800ms`（本地命中路径） |
| 工具化 | `retrieve_knowledge` 契约符合 `schemas/tools_v1.json`，可被 Agent 调用 |
| 消融报告 | 组件贡献度可量化（reranker / BM25 / 图谱 各自增益） |

### 1.3 与前后阶段的关系

```
Phase 1（数据底座）
   └─► Phase 2（本阶段：检索能力）
            ├─► Phase 3 Agent：retrieve_knowledge / query_graph 工具直接可用
            ├─► Phase 5 评测：复用本阶段指标脚本
            └─► 反哺 Phase 1 建库参数（若调优需要）
```

---

## 二、阶段前置（Phase 1 移交物核对）

> **逐项确认以下 Phase 1（M1.4）产出可用；缺失项须先补齐。**

| # | 移交物 | 用途 | 状态 |
|---|---|---|---|
| 1 | Milvus Collection（dense + sparse）与建库参数 | 检索直接复用 | ☐ |
| 2 | `chunks/chunks_v1.jsonl` + 父块映射 | 父块回填 | ☐ |
| 3 | Neo4j 图谱（实体/关系类型） | 图谱召回 | ☐ |
| 4 | `evals/golden_set_v1.jsonl`（50 条） | 指标评测基准 | ☐ |
| 5 | `docs/labeling-spec-v1.md` | 相关性判定口径 | ☐ |
| 6 | `docs/data-dictionary.md` | 字段/元数据口径 | ☐ |
| 7 | `env-baseline-v1.md` + `version-lock.md` | 版本一致性 | ☐ |
| 8 | `reports/v2-report.md` 参数基线表 | 索引/度量/analyzer/RRF k 起点 | ☐ |

> **注意**：本阶段**不重建库**；若需调整索引参数，走 Phase 1 的幂等建库脚本重建（记录新版本号）。

---

## 三、工作分解（WBS）

| 包 | 名称 | 核心内容 | 关键产出 |
|---|---|---|---|
| **W1** | 查询理解与改写 | 语义查询 / 关键词 / 实体三元组改写，含缓存与快速路径 | `scripts/query_rewrite.py` |
| **W2** | 多路召回 | Dense(BGE-M3) + Sparse(BM25/jieba) + Graph(Neo4j ≤2 跳) | `scripts/retrieve_dense.py` 等 |
| **W3** | 融合 | RRF（可加权）+ 去重 + 候选池 | `scripts/fuse_rrf.py` |
| **W4** | 重排 | BGE-reranker-v2-m3，含显存调度 | `scripts/rerank.py` |
| **W5** | 证据组装 | 父块回填、冲突裁定、来源标注 | `scripts/assemble_evidence.py` |
| **W6** | 工具化与硬化 | `retrieve_knowledge` 工具、缓存、超时、降级、指标脚本 | `app/tools/retrieve_knowledge.py` |

### 3.1 依赖关系

```
W1 ─► W2 ─┬─► W3 ─► W4 ─► W5 ─► W6
          └─►（Graph 路并行）
消融评测（W2–W5 各环节开关）贯穿全程
```

---

## 四、逐段计划（P2-D1 – P2-D20，按周）

### 第 1 周（D1–D5）· 基础管线打通

| 天 | 任务 | 产出 |
|---|---|---|
| D1 | W1 查询改写：定义三路改写输出（semantic / keywords / entities）；先实现**规则 + 小模型快速路径**（`qwen2.5:3b` 或规则），LLM 改写作为可选项 | `scripts/query_rewrite.py` |
| D2 | W2 Dense 召回：BGE-M3 编码 + Milvus HNSW（`ef` 可调），`top_k=20` | `scripts/retrieve_dense.py` |
| D3 | W2 Sparse 召回：Milvus 服务端 BM25（jieba），`top_k=20`；验证分词效果 | `scripts/retrieve_sparse.py` |
| D4 | W3 RRF 融合（k=60，基础等权）+ 去重 | `scripts/fuse_rrf.py` |
| D5 | 端到端串联 + **首次指标基线**（无重排、无图谱） | `reports/p2-baseline.md` |

> **出口 M2.1**：管线可跑通，产出首版 `Recall@5` 基线（预期低于目标，作为优化起点）。

### 第 2 周（D6–D10）· 重排 + 图谱 + 回填

| 天 | 任务 | 产出 |
|---|---|---|
| D6 | W4 重排接入：BGE-reranker-v2-m3，候选池 50 → Top-5；**显存调度**（与 7B 错峰） | `scripts/rerank.py` |
| D7 | 重排消融：有/无重排指标对比，确认增益 | `reports/p2-rerank-ablation.md` |
| D8 | W2 Graph 召回：Neo4j Cypher ≤2 跳，路径 Top-5；实体识别 → 图查询 | `scripts/retrieve_graph.py` |
| D9 | W5 图谱融合与**冲突裁定**（文档证据优先，图谱为线索） | `scripts/assemble_evidence.py` |
| D10 | W5 父块回填（子块命中 → 返回父块上下文）+ 来源标注 | `reports/p2-evidence.md` |

> **出口 M2.2**：六环节齐备，消融可量化。

### 第 3 周（D11–D15）· 指标优化达标

| 天 | 任务 | 产出 |
|---|---|---|
| D11 | 调参：HNSW `ef`、候选池大小、RRF `k` 与**加权**（`w_dense` / `w_sparse`） | `configs/retrieval.yml` |
| D12 | 标注口径校准：结合 `labeling-spec-v1.md` 复核评测集判定一致性 | 校准记录 |
| D13 | 错误分析：对未命中样本归类（改写失败/召回缺失/排序错误/标注问题） | `reports/p2-error-analysis.md` |
| D14 | 针对性优化：改写策略、查询扩展、同义词典、BM25 `k1/b` | 迭代记录 |
| D15 | **指标复核**：`Recall@5 ≥85%`、`MRR ≥0.75`、`NDCG@5` | `reports/p2-metrics.md` |

> **出口 M2.3**：指标达标（或进入中间区间并记录处置）。

### 第 4 周（D16–D20）· 性能硬化与工具化

| 天 | 任务 | 产出 |
|---|---|---|
| D16 | 性能剖析：逐环节耗时打点，定位瓶颈 | `reports/p2-perf.md` |
| D17 | 优化：Dense/Sparse 并行、重排批处理、连接复用、结果缓存 | 优化提交 |
| D18 | W6 工具化：`retrieve_knowledge` 实现（入参/返回符合 `tools_v1.json`）+ 超时/错误码/降级 | `app/tools/retrieve_knowledge.py` |
| D19 | 缓存与降级：Redis `cache:retrieve:{hash}`（TTL 10min）；重排不可用时降级为 RRF 结果 | `configs/cache.yml` |
| D20 | 验收与移交：指标 + 性能 + 消融汇总；`handover-p3.md` | **M2.4** |

---

## 五、关键模块详细设计

### 5.1 W1 · 查询改写

| 路 | 输出 | 用途 |
|---|---|---|
| 语义查询 | 规范化自然语言问句 | Dense 检索 |
| 关键词 | 抽出的术语/型号/部件 | BM25 检索 |
| 实体 | 设备/部件/故障模式 | 图谱检索 |

**性能取舍**：LLM 改写单次约 200–500ms，**默认走"规则 + 小模型"快速路径**；LLM 改写仅在低置信或复杂查询时启用，并**缓存改写结果**。

```
rewrite_cache_key = hash(raw_query + device_model)
```

### 5.2 W2 · 多路召回

| 路 | 参数 | 候选数 |
|---|---|---|
| Dense | BGE-M3(1024d)，HNSW `M=16, efConstruction=200`，查询 `ef=64~128`，COSINE | 20 |
| Sparse | Milvus 服务端 BM25，jieba analyzer，`bm25_k1=1.2, bm25_b=0.75` | 20 |
| Graph | Neo4j Cypher，`max_hops=2`，关系类型受控 | 5 路径 |

> **并行执行**：Dense 与 Sparse 并发；Graph 独立通道。

### 5.3 W3 · RRF 融合

```
等权版：  score(d) = Σ_i 1 / (k + rank_i(d))      k = 60
加权版：  score(d) = Σ_i w_i / (k + rank_i(d))
          w_dense + w_sparse = 1（初值 0.6 / 0.4，由评测调优）
```

- 同一 `chunk_id` 去重合并；
- 图谱路径**不进入 RRF 排序**，作为独立证据通道（见 §5.5）。

### 5.4 W4 · 重排与显存调度

| 项 | 设计 |
|---|---|
| 模型 | BGE-reranker-v2-m3 |
| 输入 | RRF Top-50（可调） |
| 输出 | Top-5 |
| 批处理 | batch 8–16，按显存实测调整 |
| **显存约束** | 7B LLM 常驻 GPU 时，reranker **按需加载**；不可三者共存（见 V5.0 §3.9） |
| 调度策略 | 重排前若显存不足 → 走 CPU 重排（延迟上升，记录代价）或短暂让出 GPU |
| 降级 | 重排不可用 → 直接返回 RRF Top-5，并标注 `degraded=true` |

### 5.5 W5 · 证据组装与冲突裁定

```
融合规则：
  文档证据（Milvus 命中）  ── 主证据
  图谱路径（Neo4j 命中）   ── 线索（附在证据集，标注 relation path）

冲突裁定：
  文档与图谱冲突  → 以文档证据为准，图谱标注"待确认线索"
  文档与图谱一致  → graph_support = 1（提升置信度）
  图谱无路径      → graph_support = 0.3（不否决，仅降权）

父块回填：
  命中子块 → 依据 parent_id 取回父块上下文（供 Agent 使用完整段落），
            输出仍以子块为引用粒度（含 page/section）
```

**证据条目结构**（对齐 `tools_v1.json` 的 `EvidenceItem`）：

```json
{
  "chunk_id": "c_00123",
  "doc_id": "d_0042",
  "content": "…父块上下文…",
  "source": "离心泵维护手册_v2.pdf",
  "page": 37,
  "score": 0.83,
  "channel": "dense+sparse",
  "graph_hint": "bearing_wear -CAUSES-> temperature_rise"
}
```

### 5.6 W6 · `retrieve_knowledge` 工具化

```python
# app/tools/retrieve_knowledge.py
class RetrieveKnowledgeInput(BaseModel):
    query: str
    top_k: int = Field(5, ge=1, le=20)
    filters: dict | None = None   # {device_model, doc_type, section}

class RetrieveKnowledgeOutput(BaseModel):
    items: list[EvidenceItem]
    total: int
    elapsed_ms: int
```

**约定**：超时 2s；错误码 `E_TIMEOUT/E_NOT_FOUND/E_INVALID_ARG/E_UPSTREAM`；只对 `E_TIMEOUT/E_UPSTREAM` 重试 ≤3 次（指数退避）；返回统一 `{ok, data|error, elapsed_ms, trace_id}`。

### 5.7 缓存策略

| Key | 内容 | TTL |
|---|---|---|
| `cache:rewrite:{hash}` | 查询改写结果 | 1h |
| `cache:retrieve:{hash}` | 检索结果（含证据） | 10min |
| `cache:embed:{hash}` | 查询向量 | 1h |

> 缓存键须包含 `device_model` 与 `top_k`，避免跨设备污染。

### 5.8 消融评测（贯穿全程）

| 配置 | 目的 |
|---|---|
| Dense only | 基线下界 |
| Dense + Sparse + RRF | BM25 与融合增益 |
| + Reranker | 重排增益 |
| + Graph | 图谱增益 |
| 全量 | 最终指标 |

---

## 六、里程碑

| 里程碑 | 内容 | 时间 | 通过条件 |
|---|---|---|---|
| **M2.1** | 基础管线打通 | D5 | Dense+Sparse+RRF 可跑通，产出 `Recall@5` 基线 |
| **M2.2** | 六环节齐备 | D10 | 重排 + 图谱 + 父块回填完成，消融可量化 |
| **M2.3** | 指标达标 | D15 | `Recall@5 ≥85%`、`MRR ≥0.75`、`NDCG@5` 报告值 |
| **M2.4** | 性能与工具化 | D20 | `P95 < 800ms`；`retrieve_knowledge` 可用；移交 Phase 3 |

---

## 七、验收标准与指标门禁

### 7.1 量化指标

| 指标 | 目标 | 测量 |
|---|---|---|
| `Recall@5` | ≥ 85% | `golden_set_v1.jsonl` |
| `MRR` | ≥ 0.75 | 同上 |
| `NDCG@5` | 报告值 | 同上 |
| 引用正确率 | ≥ 90% | 人工抽检 |
| `P95 检索延迟` | < 800ms | 探针 |
| 缓存命中率 | 报告值 | 统计 |

### 7.2 门禁判定

| 情况 | 处置 |
|---|---|
| `Recall@5 ≥85%` 且 `MRR ≥0.75` 且 `P95 <800ms` | **通过**，进入 Phase 3 |
| `Recall@5` 80–85% | 中间区间：继续调参（改写/权重/候选池）；记录处置与代价；若仍不达标则**显式下调 Phase 5 目标值并标注原因** |
| `P95` 800–1000ms | 中间区间：加大缓存 + 关闭图谱通道/降低候选池；记录延迟-质量权衡 |
| `MRR <0.75` 但 `Recall@5` 达标 | 可接受（排序问题），记录并进入下一阶段 |
| `Recall@5 <80%` | **阻塞**：回到错误分析，不允许带病进入 Phase 3 |

> **纪律**：中间区间 **≠ 通过**，必须写处置动作与指标代价。所有指标基于**模拟数据的初步验证**。

---

## 八、性能预算与优化手段

### 8.1 延迟预算（目标 P95 < 800ms）

| 环节 | 预算 | 备注 |
|---|---|---|
| 查询改写 | ≤ 50ms（缓存/规则） / 200–500ms（LLM） | **默认快速路径** |
| 查询向量化 | 20–50ms | 宿主 GPU |
| Dense 检索 | 10–30ms | HNSW |
| Sparse 检索 | 10–30ms | 服务端 BM25 |
| RRF 融合 | ≤ 5ms | 内存计算 |
| 重排（50→5） | 100–300ms | 批处理 |
| 图谱查询 | 50–150ms | ≤2 跳 |
| 组装/回填 | ≤ 20ms | 缓存父块 |
| **合计** | **~400–700ms** | 满足预算 |

### 8.2 优化手段（按收益排序）

1. **改写走缓存/规则**（最大收益，避免 LLM 每次介入）；
2. **Dense 与 Sparse 并行**；
3. **重排批处理** + 候选池自适应（简单查询 20，复杂 50）；
4. **结果缓存**（重复查询直达）；
5. **HNSW `ef` 权衡**：`ef` 越小越快但召回下降，需在指标与延迟间取平衡点；
6. **图谱通道可开关**：高延迟时降级。

---

## 九、风险与应对

| 编号 | 风险 | 影响 | 应对 | 归属 |
|---|---|---|---|---|
| P2-R1 | 改写引入语义漂移 | 召回变差 | 保留原文通道；A/B 对比改写前后 | W1 |
| P2-R2 | 显存不足致重排不可用 | 质量下降 | 错峰加载 / CPU 降级 / 标注 `degraded` | W4 |
| P2-R3 | 评测集标注口径不一致 | 指标不可信 | 复用 `labeling-spec-v1.md` + 复核一致性 | W3 周 |
| P2-R4 | 图谱召回引入噪声 | 干扰文档排序 | 图谱**不进入 RRF**，只作线索 | W5 |
| P2-R5 | 调参过拟合评测集 | 泛化差 | 留出 10 条 hold-out 验证 | D11–D15 |
| P2-R6 | 延迟超标 | 影响 Phase 3 端到端 | 按 §8.2 逐项优化；必要时下调候选池 | D16–D17 |
| P2-R7 | BM25 中文分词不佳 | 稀疏路收益≈0 | 复用 Phase 0 结论；必要时换分词器/加同义词 | D3 |
| P2-R8 | 缓存污染（跨设备） | 结果错配 | 缓存键含 `device_model` + `top_k` | D19 |

---

## 十、交付物与目录

### 10.1 目录增量

```
project/
├─ app/tools/
│  └─ retrieve_knowledge.py        # ★ 工具实现
├─ configs/
│  └─ retrieval.yml                # 索引/度量/权重/RRF k/缓存
├─ scripts/
│  ├─ query_rewrite.py
│  ├─ retrieve_dense.py
│  ├─ retrieve_sparse.py
│  ├─ retrieve_graph.py
│  ├─ fuse_rrf.py
│  ├─ rerank.py
│  ├─ assemble_evidence.py
│  └─ eval_retrieval.py            # 指标评测 + 消融
└─ reports/
   ├─ p2-baseline.md
   ├─ p2-rerank-ablation.md
   ├─ p2-evidence.md
   ├─ p2-error-analysis.md
   ├─ p2-metrics.md
   ├─ p2-perf.md
   └─ P2-summary.md
```

### 10.2 交付物清单

| 类别 | 交付物 |
|---|---|
| 管线 | 六环节脚本 + `retrieval.yml` 参数 |
| 指标 | 指标报告 + 消融报告 + 错误分析 |
| 性能 | 逐环节耗时报告 + 优化记录 |
| 工具 | `retrieve_knowledge` 实现（契约符合 `tools_v1.json`） |
| 移交 | `docs/handover-p3.md` |

---

## 十一、检查清单

### 通用规则
- [ ] 指标评测使用 `golden_set_v1.jsonl`，口径与 `labeling-spec-v1.md` 一致
- [ ] 每次调参记录到 `retrieval.yml` 版本，可回滚
- [ ] 保留 hold-out 10 条，禁止用于调参
- [ ] 所有延迟测量区分冷/热启动

### 第 1 周（M2.1）
- [ ] 三路改写输出可用
- [ ] Dense / Sparse 各自可召回
- [ ] RRF 可融合去重
- [ ] 产出 `Recall@5` 基线

### 第 2 周（M2.2）
- [ ] 重排接入并完成消融
- [ ] 图谱召回 + 冲突裁定
- [ ] 父块回填与来源标注

### 第 3 周（M2.3）
- [ ] `Recall@5 ≥85%`、`MRR ≥0.75`
- [ ] 错误分析完成
- [ ] hold-out 验证通过

### 第 4 周（M2.4）
- [ ] `P95 <800ms`
- [ ] `retrieve_knowledge` 契约符合 `tools_v1.json`
- [ ] 缓存与降级策略生效
- [ ] `handover-p3.md` 齐备

---

## 附：Phase 2 → Phase 3 移交要点

| 移交项 | 用途 |
|---|---|
| `retrieve_knowledge` 工具（含契约与降级） | Agent 检索节点直接调用 |
| `retrieve_graph` / 图谱融合规则 | Agent 图谱节点 |
| 图谱通道的 `graph_support` 取值规则 | 置信度计算（V5.0 §6.1） |
| 缓存与超时策略 | Agent 可靠性设计 |
| 指标脚本 `eval_retrieval.py` | Phase 5 复用 |
| `retrieval.yml` 参数基线 | Agent 调参参考 |
