# Phase 2 → Phase 3 移交清单（Handover P3）v1

> **里程碑**：M2.4（Phase 2 收尾 · 性能与工具化）
> **上游依据**：`plan/Phase 2 详细开发计划（混合检索）.md` §一–§七；`docs/p0-spec-gate-criteria.md` §1.2
> **台账**：`docs/prj-ledger-version-lock.md` §二.2.14–2.20
> **版本**：v1 ｜ **制定日期**：2026-10-09 ｜ **状态**：定稿

---

## 一、移交目的与使用方式

### 1.1 目的

本清单是 **Phase 2（混合检索）→ Phase 3（Agent 编排）** 的唯一移交凭据，回答三件事：

1. **P2 交出了什么**（可直接复用的资产，见 §二）；
2. **P3 第一天先做什么**（按优先级排序，见 §三）；
3. **哪些问题没闭环**（自动成为 P3 遗留问题，见 §四）。

### 1.2 使用方式

| 项 | 说明 |
|---|---|
| **可直接作为 P3 的输入基线** | `retrieve_knowledge` 工具可直接注入 Agent 工具列表 |
| **不重复劳动** | 检索管线 W1–W5 全部就绪，P3 只需编排调用 |
| **未闭环项自动成为 P3 遗留问题** | golden 50 题评测、Redis 缓存等 |
| **引用纪律** | 版本/依赖一律引用 `docs/prj-ledger-version-lock.md` §二.2.14–2.20 |

---

## 二、P2 已交付资产清单

### 2.1 检索管线（W1–W5）

| 组件 | 文件 | 台账 | 状态 |
|---|---|---|---|
| W1 查询改写 | `scripts/query_rewrite.py` | §二.2.14 | ✅ 规则+LLM 双路径 |
| W2 多路召回 | `scripts/retrieve_{dense,sparse,graph}.py` + `retrieval.py` + `retrieval_base.py` | §二.2.15 | ✅ Dense+Sparse 并行，Graph 独立通道 |
| W3 RRF 融合 | `scripts/fuse_rrf.py` | §二.2.16 | ✅ k=60, weights{0.6,0.4} |
| W4 重排 | `scripts/rerank.py` + `scripts/probe_reranker.py` | §二.2.17 | ✅ BGE-reranker-v2-m3（GPU 可用；D7 消融后默认跳过） |
| W5 证据组装 | `scripts/assemble_evidence.py` + `chunks/parents_v1.jsonl` | §二.2.17 | ✅ 父块回填 + 图谱冲突裁定 |

### 2.2 工具化（W6–W7）

| 组件 | 文件 | 台账 | 状态 |
|---|---|---|---|
| W6 retrieve_knowledge | `scripts/retrieve_knowledge.py` | §二.2.18 | ✅ `RetrievalService` 常驻单例，`to_openai_tool()/with_tools()` 附加注册 |
| W7 工具链接入 R-2/R-3 | `schemas/tools_p2_retrieve.json` + `evals/v2_retrieve_cases.jsonl` + `scripts/run_v2_tools.py` | §二.2.19 | ✅ 云端 Qwen/Qwen3.8-27B 16/16 Pass（单工具 100% ≥85%） |

### 2.3 指标与消融

| 组件 | 文件 | 台账 | 状态 |
|---|---|---|---|
| M2.3 配套评测集 | `evals/m2_acc_set.jsonl` + `scripts/eval_m2.py` | §二.2.20 | ✅ 12 题，Recall=1.0/MRR=0.7569/NDCG=1.0/P95=86ms |
| D7 重排消融 | `scripts/d7_ablation.py` + `experiments/p2/d7/` | §二.2.20 | ✅ rerank 净负（ΔMRR=-0.0417），RRF-only 最优 |
| D11 延迟闭合 | `experiments/p2/m2/meta-m2.json` | §二.2.20 | ✅ CPU 7037ms → GPU 353ms → RRF-only 86ms |
| 配置 | `configs/retrieval.yml` | §二.2.15–16 | ✅ rrf{k:60, top_k:5, weights{0.6,0.4}} |

### 2.4 报告

| 报告 | 路径 |
|---|---|
| W1 查询改写 | `reports/p2-d1-w1-query-rewrite.md` |
| W2 多路召回 | `reports/p2-d1-w2-recall.md` |
| W3 RRF 融合 | `reports/p2-d1-w3-rrf.md` |
| W4-W5 重排+证据 | `reports/p2-d2-w4-w5-rerank-evidence.md` |
| W6 工具化 | `reports/p2-d3-w6-retrieve-knowledge.md` |
| W7 工具链接入 | `reports/p2-d3-w7-retrieve-tools.md` |
| M2.3 指标 | `reports/p2-d3-m2-metrics.md` |

---

## 三、P3 第一天先做什么

按优先级排序：

1. **接入 `retrieve_knowledge` 工具**：`from retrieve_knowledge import RetrievalService, with_tools` → 注入 Agent 工具列表。推荐配置 `device="cuda", use_rerank=False`（D7 最优）。
2. **Agent 编排**：按 V5 方案 §六，用云端 LLM（Qwen/Qwen3.8-27B）编排 R-1~R-5 角色，`retrieve_knowledge` 作为 R-2/R-3 的检索后端。
3. **多工具链路**：V1 5 工具 Schema（`schemas/tools_v2.json`）+ Phase 2 单工具（`schemas/tools_p2_retrieve.json`）合并为 Phase 3 完整工具集。
4. **端到端冒烟**：一条完整问题 → Agent 规划 → 工具调用 → 证据返回 → 诊断报告。

---

## 四、未闭环项（自动成为 P3 遗留）

| # | 项 | 根因 | 处置建议 |
|---|---|---|---|
| 1 | **golden 50 题评测** | golden_set_v1 引用 7 类逻辑文档与真实合成语料（19 文档/36 子块/3147 token）内容脱节 | 扩语料后重评；当前用 12 题配套集作 M2.3 替代 |
| 2 | **Redis 缓存** | plan D19 计划项，Phase 2 未实现 | P3 按需实现 `cache:retrieve:{hash}` TTL 10min |
| 3 | **引用正确率 ≥90%** | 需人工抽检 | P3 端到端冒烟后抽检 |
| 4 | **rerank 重评** | D7 确认当前小语料下 rerank 净负，默认走 RRF-only | 语料扩大后重评 rerank 增益 |
| 5 | **GPU 环境依赖** | `D:\py312-torch` 独立 venv，补装了 transformers/jieba/pymilvus/neo4j | P3 若用 GPU embedder/reranker，需复用该环境 |

---

## 五、M2.4 里程碑判定

| 通过条件 | 实测 | 判定 |
|---|---|---|
| P95 < 800ms | 86.1ms（RRF-only, cuda embedder） | ✅ |
| retrieve_knowledge 可用 | W6-W7 完成，16/16 工具链 Pass | ✅ |
| 移交 Phase 3 | 本清单 | ✅ |

**M2.4 达成。Phase 2 四项里程碑（M2.1–M2.4）全部达成。**

> **约束**：M2.3/M2.4 指标基于 12 题配套评测集（非 golden 50 题）。golden 待扩语料后重评。切勿据此宣称 Phase 2 在 golden 全量上达标。
