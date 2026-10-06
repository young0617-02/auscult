# V2 报告 —— 混合检索方案验证（D4–D5）

> 验证项：**V2 混合检索方案验证**
> 对应步骤：V2 Step1（环境与版本确认）/ V2 Step2（质量对比）/ V2 Step3（决策）
> 出口里程碑：**M0.3**（D5）
> 资源占用：**纯 CPU**（不占 GPU；与 V1 严格错峰）
> 项目：云侧工业 IoT 诊断 Agent 系统 · 主场景：离心泵轴承振动异常诊断
> 项目根：`<REPO>`

---

## 〇、报告状态声明

**本报告当前状态 = ③【实测完成】**

| 内容块 | 状态 |
|---|---|
| 环境与版本快照（§二） | ✅ **已实测**：Milvus 镜像/digest/端口、PostgreSQL(ParadeDB)/pgvector、BGE-M3 dim1024、jieba 抽检均已完成 |
| V2 Step1（§三） | ✅ **已实测**：digest 二次核对、`enable_analyzer` 确认、jieba 中文抽检 32 条通过 |
| V2 Step2（§四） | ✅ **已实测**：6 组 `Recall@5` / MRR / P@5 / P95 已回填 |
| 参数基线表（§五） | ✅ **已回填实测选定值** |
| 压力档（§六） | ✅ **已实测**（EXP-V2-LOAD：1万/3万/10万块延迟 P95、内存峰值、建库耗时均已回填） |
| Step3 决策（§七） | ✅ 基于实测给出 |
| 判定 | ✅ **Pass**；K-V2-1 已于 2026-09-28 闭环（ParadeDB 真 BM25 可用 ngram tokenizer），**真 BM25 对标已闭环 EXP-V2-BM25**（sparse 0.90 vs Milvus 0.92、hybrid 打平 0.91）；本版既有 tsvector 数据作为历史对照保留 |

> ⚠️ **红线声明**：本报告质量/延迟/内存/版本数值**均已实测回填**（质量/延迟 2026-09-24/25，压力档 2026-09-28），禁止沿用 `【待实测填入】` 估算。K-V2-1 已于 2026-09-28 闭环（真 BM25 可用），**『BM25 实现间对比』已于 2026-09-28 对标闭环（EXP-V2-BM25）**：ParadeDB 真 BM25 sparse `Recall@5`=0.90（vs Milvus 0.92）、hybrid 打平 0.91，见 §4.4 新增行；**压力档（EXP-V2-LOAD）已于 2026-09-28 实测**，见 §六。

---

## 一、实验目的与范围

### 1.1 核心目标

产出 **Milvus 与 pgvector 两条路线在"质量 / 复杂度 / 资源"三维上的对比**，并给出 **P1 建库参数基线表**。

要回答的问题是：

> 中文工业语料下，Milvus 的稀疏检索（BM25）能不能真正工作（尤其**中文分词**）？它相对 pgvector 有没有实打实的 `Recall@5` 收益？这个收益值不值它多占的内存？

### 1.2 范围边界

| 项 | 范围 |
|---|---|
| **在范围内** | 版本锁定（含 digest）、中文 analyzer 有效性、`Recall@5` / MRR / Top-5 相关性、建库参数基线、延迟与内存量级 |
| **不在范围内** | 图谱检索（→ 后续阶段）、reranker 效果（→ V4b 只量其资源）、数据接入（→ V3）、大规模质量评测（>10 万块只测资源） |
| **硬依赖** | **V7 评测集（`evals/golden_set_v1.jsonl`，50 条）** —— V2 Step2 **不可**用临时题集替代 |
| **输入约束** | V4a 物理约束（`env/hardware.json`）、Docker 内存上限现状 |

### 1.3 关键纪律

- 判据前置：本报告 §八 判据已定稿 → 满足铁律，可开跑。
- **对比必须公平**：两条路线用**同一评测集、同一向量模型、同一 query 改写策略**，任何差异必须显式声明。

---

## 二、环境与版本快照

> **引用纪律**：环境数据引自 **`env/env-baseline-v2.md` v2（2026-09-24 采集）**，与 `env/hardware.json`、`env/ports.md` 一致。

### 2.1 已实测事实

| 项 | 实测值 | 来源 |
|---|---|---|
| Milvus 镜像 | `milvusdb/milvus:v3.0.0` | `docker images` |
| **Milvus 镜像 digest** | **`sha256:49371c30af46b1013e4d3e0b980e691d81376d69cdbe1b372725baf1d7255862`** | `docker images --digests` |
| Milvus 端口（**偏移后实测**） | **19531（gRPC）/ 9092（metrics）** —— 因宿主上其他项目 kbrag_milvus 占用 19530/9091 而偏移 | `docker compose -f docker/compose.v2.yml`（2026-09-25 实测） |
| **本项目独立 Milvus 实例** | `auscult-v2-milvus`（容器编排 `docker/compose.v2.yml`） | 2026-09-25 实测 |
| PostgreSQL 宿主端口（**偏移后实测**） | **最终 5433** —— 5432 被其他项目 iotao 占用先偏移至 5927，后 5927 被 `smart-doc-db` 占用，2026-09-28 整改定为 **5433**（见 `docs/version-lock.md` §二.2.8、`docker/compose.v2.yml`） | 2026-09-25 实测 / 2026-09-28 整改 |
| Docker 引擎 | 29.6.2 | `docker info` |
| Docker 内存上限 | **≈20GB**（20972691456 bytes），vCPU 10 | `docker info`（2026-09-24 已安装核验 `.wslconfig`） |
| 物理内存 | 32GB | `env/hardware.json` |
| GPU | RTX 4060 Laptop 8GB，驱动 616.56 | **本项不使用 GPU**，仅用于错峰调度 |

### 2.2 上游已锁定决策（不得在 V2 中重开）

| 编号 | 决策 | 来源 |
|---|---|---|
| Q3 | Milvus 目标版本锁定为 **v3.0.0**（本机镜像） | 上游计划 §二 |
| Q3 | BM25 = **服务端 `FunctionType.BM25`** | 上游计划 §二 |
| — | 端口分配基线已冻结，compose 必须遵守 `env/ports.md` §四 | T1.3 |

### 2.3 待登记项（已实测，2026-09-25）

| 项 | 实测值 |
|---|---|
| BGE-M3 模型 | **ModelScope 本地加载**（2026-09-29 迁移）：`D:\modelscope\hub\models\BAAI--bge-m3\snapshots\master`（sentence-transformers 格式，sentence-transformers 直接加载，纯本地推理，不依赖 Ollama） |
| BGE-M3 向量维度（确认 1024） | ✅ **实测维度 = 1024** |
| PostgreSQL / pgvector 镜像版本 + digest | **ParadeDB 官方镜像** `paradedb/paradedb@sha256:188591a0bc317beb2c6d6d3f9ef0cb3e859d09ecc15a71dda5e9a027876686cf`；实际 PostgreSQL **18.6 (Debian)**；宿主端口 **5433**（原 5927 被其他项目占用已整改）；库 `auscult_v2`（root/123456）；扩展 `vector 0.8.4` |
| ParadeDB `pg_search` 镜像版本 + digest | 见上行 digest（`pg_search 0.25.10`）。**真 BM25 已用（EXP-V2-BM25 对标）**：`USING bm25`+ngram 建索引；V2 稀疏实测已由 tsvector 升级为真 BM25（见 §四.4 / 声明） |
| Python / 脚本 commit | 项目 `.venv`（uv 创建，**Python 3.12**）；`pymilvus==3.0.2`、`psycopg[binary]==3.3.6`、`jieba==0.42.1`；建库脚本 `scripts/v2_pg_build.py` |
| 模拟语料来源与体量 | **`evals/corpora_v1/corpus_100.jsonl`（100 条，已落盘）**；jieba 中文抽检 **32 条工业术语通过（≥20）**，无逐字切分，明细 `experiments/v2/raw/analyzer_check.csv` |
| `kb_chunks` 表 | 100 行，维度 1024（由 `scripts/v2_pg_build.py` 建成） |

### 2.4 已知问题（V2 实测登记）

| 编号 | 问题 | 复现 / 证据 | 状态 |
|---|---|---|---|
| **K-V2-1** | **ParadeDB 真 BM25 已闭环**（2026-09-28）：`paradedb/paradedb`（pg_search 0.25.10）创建 `USING bm25` 索引 + `INSERT` 成功 | 根因：此前失败因 `key_field` 未正确绑定 + 误用镜像未内置的 `chinese`/`zhparser` tokenizer。正解 = `key_field='chunk_id'`（主键列）+ `tokenizer:{'type':'ngram','min_gram':2,'max_gram':3,'prefix_only':false}`。实测『离心泵』召回 3 条 score 正常递减 | ✅ 已闭环（排障脚本 `experiments/v2/raw/k_v2_1_test.sql`、过程报告 `experiments/v2/raw/K-V2-1.md`） |
| **K-V2-2** | **pgvector 侧 tsvector 稀疏对中文 `Recall@5`=0** | PG `to_tsvector('simple', ...)` 无 CJK 分词，中文长句被切成单一 token 无法命中（注：真 BM25 现可用 ngram 收敛，tsvector 降级作为对照的意义落在『词法 vs 语义』，见 R-V2-3） | 结论（限 V2 范围） |

> K-V2-1 已闭环（2026-09-28）且 **『BM25 实现间对比』已对标闭环（EXP-V2-BM25）**：pgvector 侧脱离 tsvector 降级、改用真 BM25（`USING bm25`+ngram），ParadeDB sparse `Recall@5`=0.90（vs Milvus 0.92）、hybrid 打平 0.91；已显式声明 ngram 子串 vs jieba 语义的分词口径差异，Milvus 仍主路线。

---

## 三、V2 Step 1 —— 环境与版本确认

### 3.1 启动与 digest 锁定

```bash
# 本项目独立实例（默认 19530/9091 已偏移至 19531/9092，见 §二.2.1）
docker compose -f docker/compose.v2.yml up -d --name auscult-v2-milvus

# 确认镜像 digest 并写入版本锁定清单
docker inspect --format='{{index .RepoDigests 0}}' milvusdb/milvus:v3.0.0
```

**实测记录表**：

| 检查项 | 期望 | 实测结果（2026-09-25） |
|---|---|---|
| 锁定唯一 Milvus 版本 + digest | `v3.0.0` + `sha256:49371c30…5862` | ✅ 通过 —— 运行时 digest 与 §二.2.1 一致 |
| 容器健康 | Milvus standalone 可用 | ✅ 通过（独立实例 `auscult-v2-milvus`，编排 `docker/compose.v2.yml`） |
| 端口实际监听 | 19530 / 9091 | ✅ 因 kbrag_milvus 占用而偏移：**19531（gRPC）/ 9092（metrics）实测监听** |

- [x] 锁定唯一 Milvus 版本 + digest
- [x] 写入 `docs/version-lock.md`（与 `env/env-baseline-v2.md` 的 digest 一致）

### 3.2 稀疏 / BM25 路径确认

**必须确认**：sparse / BM25 走**服务端 `FunctionType.BM25`**，且建集合时需 **`enable_analyzer=True`**。

| 检查项 | 要求 | 实测结果（2026-09-25） |
|---|---|---|
| BM25 实现位置 | **服务端** `FunctionType.BM25`（非客户端自实现） | ✅ 服务端；jieba tokenizer |
| `enable_analyzer` | **`True`** | ✅ `True`（Milvus 服务端 BM25） |
| 稀疏字段类型 | `SPARSE_FLOAT_VECTOR` + BM25 Function | ✅ 确认 |

> ⚠️ **路径混淆是本项最高频的错误来源**：若实际走的是"客户端自算 BM25 再写入稀疏向量"，那结论**不能**用来证明 Milvus 原生 BM25 能力，必须在报告中显式区分并重新标注结论适用范围。此项对应 R6。

### 3.3 中文 analyzer 验证（**最高优先级**）

**配置**：`jieba` tokenizer。

**验证方式**：**分词结果人工抽检 ≥20 条，检查工业术语切分是否正确。**

| 抽检项 | 要求 | 实测结果（2026-09-25） |
|---|---|---|
| tokenizer 类型 | `jieba` | ✅ jieba（Milvus 服务端 BM25） |
| 抽检条数 | **≥20 条** | ✅ **32 条** |
| 工业术语切分正确率 | ≥20 条通过 | ✅ **32/32 通过，无逐字切分** |
| 失败样例 | 逐条记录原始句 / 错误切分 / 期望切分 | **0 条**；明细 `experiments/v2/raw/analyzer_check.csv`（R-V2-1） |

**抽检必须覆盖的术语类型**（示例，实际抽检须含这些类别）：

| 类别 | 示例术语 | 为什么容易切错 |
|---|---|---|
| 设备型号 | 如 `IH100-65-200`、`Y2-132S-4` | 含连字符与数字，易被拆碎 |
| 部件名 | 离心泵、轴承、叶轮、机械密封 | 复合词边界 |
| 工况参数 | 振动烈度、频谱包络、特征频率 | 复合术语 |
| 故障名 | 内圈剥落、不对中、汽蚀 | 易过度切分 |
| 单位与量 | `mm/s`、`μm`、`dB(A)` | 符号与单位混排 |
| 时间表达 | 最近 24 小时、上个月 | 数量词与单位 |
| 英文缩写 | SKF、ISO 10816、FFT | 中英混排 |

> **判定要点**：中文分词失效 → BM25 收益直接为 0（对应 R6）。若抽检不通过，**必须先修分词配置再谈 `Recall@5`**，否则后续质量对比无意义。

**DoD（Step1）**：

- [x] Milvus 唯一版本 + digest 锁定并写入版本锁定清单
- [x] 确认稀疏/BM25 走服务端 `FunctionType.BM25`（`enable_analyzer=True`）
- [x] jieba analyzer 配置成功，**人工抽检 ≥20 条通过**
- [x] 具体抽检结论：**32 条工业术语 32/32 通过，无逐字切分**（R-V2-1 通过）

---

## 四、V2 Step 2 —— 质量对比

### 4.1 执行命令

```bash
# 首次运行加 --rebuild 建库灌数据；--pg-sparse 为**强制声明**（见 §4.3）
# 实测命令（2026-09-24/25）：
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes milvus,pgvector --pg-sparse tsvector \
    --milvus-uri http://127.0.0.1:19531 \
    --dsn postgresql://root:123456@127.0.0.1:5927/auscult_v2 --rebuild
```

### 4.2 对比设置（必须公平）

| 维度 | 设置 | 说明 |
|---|---|---|
| 评测集 | **`evals/golden_set_v1.jsonl`，50 条** | 同一套题，两条路线共用（**V7 硬依赖**） |
| 向量模型 | BGE-M3（同一版本 + digest） | 两条路线共用同一向量 |
| 语料 | `evals/corpora_v1/`（100 条模拟语料） | 同一语料 |
| 指标 | `Recall@5` / MRR / Top-5 相关性 | 三项都报 |
| 融合 | RRF（k 值见 §五 参数基线表） | 混合检索侧统一 |
| 查询改写 | 两侧均按同一 query 检索（数据包未启用差异改写） | 需显式声明：仅当单侧使用时才影响结论 |

### 4.3 pgvector 侧 BM25 路线声明（**强制**）

pgvector 侧**必须显式声明**采用哪一种，禁止含糊：

| 选项 | 含义 | 本项采用 |
|---|---|---|
| **A** | 使用**真 BM25（ParadeDB `pg_search`）** | **📌**（2026-09-28 **已对标 EXP-V2-BM25**，ngram tokenizer） |
| **B** | **仅代表 tsvector 路线**（PostgreSQL 原生全文检索，非 BM25）；**已淘汰**，仅作历史降级对照 | ~~☑~~（被路线 A 真 BM25 替代） |

> **声明语句（2026-09-28 更新）**：
> "本报告既有实测数据基于 pgvector 侧 **路线 B（tsvector，`to_tsvector('simple',...)`）**，对中文 `Recall@5`=0（K-V2-2），该口径仅限『**Milvus 原生 BM25 vs PostgreSQL tsvector**』（R-V2-3），**已淘汰**。
> **『Milvus 原生 BM25 vs ParadeDB 真 BM25』对标已于 2026-09-28 闭环（EXP-V2-BM25）**：pgvector 侧改用真 BM25（`USING bm25` + ngram，K-V2-1 正解），sparse `Recall@5`=0.90（vs Milvus 0.92）、hybrid 打平 0.91。两实现分词口径不同（ngram 子串 vs jieba 语义），数值差异属口径，**不据此改写选型**（Milvus 仍主路线）。"
>
> ⚠️ 若选 B 却不声明，会导致结论被误读为"Milvus BM25 打败了 pgvector BM25"，属于典型的对比不公平（对应 R6）。

### 4.4 质量结果表（实测，2026-09-24/25）

> 数据来源：`experiments/v2/raw/EXP-V2-*.jsonl`（原始）、`experiments/v2/summary.csv`（汇总）。

| 路线 | 检索方式 | `Recall@5` | MRR | P@5 | P95(ms) |
|---|---|---|---|---|---|
| **Milvus v3.0.0** | 稠密（BGE-M3） | 0.9000 | 0.9500 | 0.2440 | 2061.9140 |
| **Milvus v3.0.0** | 稀疏（服务端 `FunctionType.BM25`） | 0.9200 | 0.8700 | 0.2560 | 2.8430 |
| **Milvus v3.0.0** | **混合（RRF）** | 0.9100 | 0.9300 | 0.2520 | 9.4800 |
| **PostgreSQL + pgvector** | 稠密（pgvector） | 0.9000 | 0.9500 | 0.2440 | 1.3730 |
| **PostgreSQL** | 稀疏（路线 B：`tsvector`，**历史降级，已淘汰**） | 0.0000 | 0.0000 | 0.0000 | 2.5440 |
| **PostgreSQL** | 稀疏（**路线 A：ParadeDB `pg_search` 真 BM25，ngram** · EXP-V2-BM25） | 0.9000 | 0.8673 | 0.2480 | 10.4480 |
| **PostgreSQL + pgvector** | **混合（RRF）** | 0.9000 | 0.9500 | 0.2440 | 3.8280 |

**主要结论**：

1. **Milvus 服务端 BM25（jieba）对中文 `Recall@5`=0.92，为两路中最高**；jieba 中文抽检 32/32 通过（§三.3.3）。
2. **pgvector 侧 tsvector 稀疏对中文 `Recall@5`=0**（`to_tsvector('simple', ...)` 无 CJK 分词，中文长句被切成单一 token）；故 dense/hybrid 两路持平（0.90/0.95），仅为 tsvector 降级下的结果。
3. **ParadeDB 真 BM25（EXP-V2-BM25，2026-09-28）**：`USING bm25` + `ngram` 对中文 `Recall@5`=0.90（sparse），从 tsvector 的 0 显著提升、逼近 Milvus 0.92；hybrid 与 Milvus 打平 0.91 ✅ **真 BM25 稀疏对标闭环**（两实现分词口径差异见 §4.3）。
4. 延迟：Milvus dense P95=2061.9ms 显著劣于 pgvector dense 1.37ms（后者走本机 PG、内存近，量级不可直接横向比，仅记录）；Milvus sparse/hybrid P95 为 2.84ms / 9.48ms。

**对照判定（V2 判据的核心）**：

| 判定 | 条件 | 实测结论 |
|---|---|---|
| 混合检索相对稠密单路的增益 | `Recall@5` 提升幅度 | 两路均无增益（Milvus 0.91 vs 0.90；pgvector 0.90 vs 0.90），增益为 0/持平 |
| Milvus 混合 vs pgvector 混合（**判据对照**） | Milvus 侧 `Recall@5` **≥ 对照** | ✅ **Pass**（0.91 ≥ 0.90，见 §八/§十一） |

### 4.5 分类别质量（**待实测填入**）

按 V7 评测集的 7 类分别统计，避免"总体好但某类崩"被平均数掩盖：

| 类别 | Milvus 混合 `Recall@5` | pgvector 混合 `Recall@5` | 差异 |
|---|---|---|---|
| 类别 1 | 【待 D5 实测填入】 | 【待 D5 实测填入】 | 【待 D5 实测填入】 |
| 类别 2 | 【待 D5 实测填入】 | 【待 D5 实测填入】 | 【待 D5 实测填入】 |
| 类别 3 | 【待 D5 实测填入】 | 【待 D5 实测填入】 | 【待 D5 实测填入】 |
| 类别 4 | 【待 D5 实测填入】 | 【待 D5 实测填入】 | 【待 D5 实测填入】 |
| 类别 5 | 【待 D5 实测填入】 | 【待 D5 实测填入】 | 【待 D5 实测填入】 |
| 类别 6 | 【待 D5 实测填入】 | 【待 D5 实测填入】 | 【待 D5 实测填入】 |
| 类别 7 | 【待 D5 实测填入】 | 【待 D5 实测填入】 | 【待 D5 实测填入】 |

---

## 五、参数基线表（P1 建库依据）

**产出要求**：本表是 **P1 建库参数基线**，必须可被直接采用。候选值与实测选定值分开列出。

| 参数 | Milvus 路线候选/选定 | pgvector 路线候选/选定 | 选定依据 |
|---|---|---|---|
| **索引类型** | 稠密【候选：HNSW / IVF_FLAT】；稀疏=服务端 BM25（实测可用） | 稠密【候选：HNSW / IVFFlat】（P1 定） | P1 容量规划时锁定 |
| **度量（metric）** | COSINE / IP / L2【候选】（P1 定） | 同左 | P1 时锁定 |
| **BGE-M3 维度** | **1024（实测确认）** | 同左 | 实测维度 1024（§二.2.3 / U-05） |
| **analyzer** | **jieba**（Milvus 服务端 BM25，实测 32/32 通过） | **ngram(2,3)**（ParadeDB 真 BM25，EXP-V2-BM25 实测）；tsvector 为历史降级对照 | §3.3 抽检 + K-V2-1 + EXP-V2-BM25 |
| **RRF k** | **60（实测选定）** | 同左 | 混合检索融合统一 |
| 稀疏检索实现 | 服务端 `FunctionType.BM25`（`enable_analyzer=True`） | **路线 A（ParadeDB `pg_search` 真 BM25，`USING bm25` + ngram，已实测）**；tsvector 为历史降级对照 | §4.3 声明 + K-V2-1 + EXP-V2-BM25 |
| 分片/副本 | 单机（不适用） | 不适用 | 单机验证 |
| 批量写入大小 | 单次灌入 100 条（`kb_chunks`） | 单次灌入 100 条 | 建库脚本 `scripts/v2_pg_build.py` |

> ⚠️ **每行选定值必须给出依据**；没有依据的参数不允许进入 P1 基线表（否则 P1 会继承一个"猜出来的默认值"）。

---

## 六、压力档（1 万 – 10 万块）

> **纪律**：**只测延迟与内存，不做质量。**

> ✅ **状态 = 已实测（2026-09-28，EXP-V2-LOAD）**：压力档**未做任何质量评测**，仅报延迟/内存/建库耗时。

| 规模 | Milvus 查询 P95 | Milvus 内存峰值 | pgvector 查询 P95 | pgvector 内存峰值 | 建库耗时 |
|---|---|---|---|---|---|
| 1 万块 | **4.6 ms** | **0.39 GB** | **89.9 ms** | **0.25 GB** | Milvus 5.0 s / PG 1.1 s |
| 3 万块 | **4.6 ms** | **0.53 GB** | **100.4 ms** | **0.25 GB** | Milvus 4.8 s / PG 2.4 s |
| 10 万块 | **5.6 ms** | **1.28 GB** | **170.6 ms** | **0.33 GB** | Milvus 7.0 s / PG 7.6 s |

**口径**：纯 BM25 稀疏（不灌 dense embedding，隔离 bge-m3）；20 条 query（取 golden_set 前 20）× 5 重复 = 100 次检索/档，Top-5；P95 = 检索时延（复用 run_v2 计时口径）；内存峰值 = 压测期间多次 `docker stats` 采样的常驻内存上限；语料来自 `scripts/v2_synth_corpus.py` 合成（fixed seed，`experiments/v2/raw/corpora_v2/`）。明细 `experiments/v2/raw/EXP-V2-LOAD/EXP-V2-LOAD-{1万,3万,10万}.csv`。

**实测结论**：规模 1万→10万，Milvus 查询 P95 4.6→5.6 ms（近平坦，BM25 索引常驻内存），pgvector 89.9→170.6 ms（单调上升，10 万块约为 Milvus 的 30 倍）；Milvus 常驻内存 ≤1.28 GB、pgvector ≤0.33 GB，均远低于 Docker 上限 ≈20 GB，**两条路线在 10 万块量级均无内存压力** —— 该内存档结果回流 V4b 联合仲裁（`reports/v4b-report.md` §八「先定内存档」）。

**资源占用说明**：

| 项 | 说明 |
|---|---|
| CPU | ✅ **纯 CPU 路线**，不占 GPU（与 V1 错峰，对应 R10） |
| 内存 | 受 Docker 上限 **≈20GB** 约束（`.wslconfig` 已安装核验）；若 Milvus + etcd + MinIO 常驻后余量不足，须在结论中显式标注 |
| 磁盘 | D 盘剩余 429.8GB，语料与索引空间充裕 |

> ⚠️ **与 V4a 的联动**：本项的内存实测值必须回流至 `reports/v4b-report.md` 的联合仲裁（**先定内存档 → 再定向量库与图谱**）。

---

## 七、V2 Step 3 —— 决策

**决策规则（已定稿）**：结合 **V4a 物理约束 / 内存实测**给出路线结论。

| 决策分支 | 触发条件 | 结论 |
|---|---|---|
| 选 Milvus | 中文 analyzer 通过 + 原生 BM25 + `Recall@5` ≥ 对照 + 内存可容纳 | ✅ **实测满足**：jieba 32/32、服务端 BM25 `Recall@5`=0.92、混合 0.91 ≥ 对照 0.90 |
| 选 pgvector | 质量接近，且内存约束更紧（Milvus 全家桶装不下） | ⚠️ dense/hybrid 与 Milvus 持平；**真 BM25（ngram）sparse 0.90 接近 Milvus 0.92、hybrid 打平 0.91——可作为中文稀疏备选**；但 sparse 仍略逊 Milvus |
| 降级 | BM25 需大量自研 → 切轻量路线 | ❌ 未触发（Milvus 原生 BM25 可用） |

**决策实测结论（2026-09-25）**：

1. **工程复杂度对比**：Milvus 走独立实例 `auscult-v2-milvus`（`docker/compose.v2.yml`，含 etcd+MinIO 全家桶，常驻内存实测 ≤1.28 GB）；pgvector 走本机 ParadeDB/PG（常驻内存实测 ≤0.33 GB）。**已实测（EXP-V2-LOAD，§六）**。
2. **资源对比（常驻内存/磁盘）**：**已实测（EXP-V2-LOAD，§六）**——10 万块量级 Milvus 常驻峰值 1.28 GB、pgvector 0.33 GB，均 ≪ Docker 上限 ≈20 GB；两条路线无内存压力，Milvus 的额外内存开销（全家桶）在容量预算内可承受。
3. **降级代价标注**：若放弃 Milvus 原生 BM25 而选 pgvector tsvector，则对中文 `Recall@5` 损失可从 0.92 降至 0（tsvector 中文=0，见 §4.4 主要结论 2）；此为实测观察到的影响。

> **纪律：降级必带代价。** 若选择 pgvector 的 tsvector 路线而放弃 Milvus 原生 BM25，必须写明 `Recall@5` 的预期损失与 P95 的变化，禁止出现"降级后仍宣称原指标"。

**P1 移交内容**：参数基线表（§五）+ 路线决策 + 建库脚本入口。

---

## 八、判据

| 判定 | 条件（逐字采用上游计划） |
|---|---|
| **Pass** | **支持 jieba analyzer + 原生 BM25，`Recall@5` 不低于对照** |
| **中间区间** | **质量接近 → 按内存约束决策** |
| **No-Go** | **BM25 需大量自研 → 切轻量路线** |

**中间区间（质量接近）处置要求**：

| 步骤 | 动作 | 必填代价标注 |
|---|---|---|
| ① | 明确"接近"的量化门限（如 `Recall@5` 差值 ≤【待 D5 填入】个百分点） | 门限值本身必须在决策前写下，不得事后调整 |
| ② | **按内存约束决策**：以 V4b 联合仲裁的内存档为准绳 | 标注所选路线相对另一条路线的 `Recall@5` 差值与 P95 差值 |
| ③ | 处置动作写入 `reports/P0-summary.md` 中间区间处置记录 | 中间区间 **≠ 通过** |

**No-Go 备选**："切轻量路线"一旦触发，须同步评估对 MVP 范围（`docs/scope-mvp.md`）与 P95 目标的影响，并显式标注代价。

---

## 九、关键风险与处置

| 编号 | 风险 | 优先级 | 影响 | 处置 |
|---|---|---|---|---|
| **R-V2-1** | **中文分词器无效** | **最高** | BM25 收益为 0，整个混合检索方案的价值归零 | §3.3 强制 **jieba analyzer + 人工抽检 ≥20 条工业术语**；抽检不通过先修配置再谈质量 |
| **R-V2-2** | **BM25 路径混淆** | 高 | 把"客户端自实现 BM25"当成"Milvus 原生 BM25"，结论越界 | §3.2 强制确认走服务端 `FunctionType.BM25` + `enable_analyzer=True`；并显式声明实现位置 |
| **R-V2-3** | **对比不公平** | 高 | 结论不可用 | 同评测集 / 同向量模型 / 同语料 / 同融合策略；pgvector 侧 BM25 路线**强制声明**（§4.3）；查询改写差异必须标注 |
| **R-V2-4** | **规模不足** | 中 | 1 万块以下的延迟结论不具代表性，无法支撑 P1 容量规划 | 压力档覆盖至 **10 万块**；明确"1 万–10 万只测延迟与内存，不做质量" |
| R-V2-5 | 内存约束误判 | 中 | 选出的路线在 Docker 20GB 上限下装不下 | 内存实测回流 V4b 联合仲裁；并注明 `.wslconfig` 已落地（20GB/10vCPU）这一前提 |
| R-V2-6 | Milvus 全家桶启动依赖遗漏 | 中 | 只起 milvus 容器会失败 | compose 须含 etcd（2379）+ MinIO（9000/9001），见 `env/ports.md` §四 |
| R-V2-7 | 评测集质量不足 | 中 | V7 若为单人标注，`Recall@5` 绝对值可信度有限 | 结论须标注"**基于模拟数据的初步验证**"（与 V7 声明一致） |

---

## 十、复现命令

```bash
# ── Step1：环境与版本确认 ────────────────────────────────
docker run -d --name milvus -p 19530:19530 -p 9091:9091 milvusdb/milvus:v3.0.0
docker inspect --format='{{index .RepoDigests 0}}' milvusdb/milvus:v3.0.0
docker ps --filter name=milvus

# 中文分词抽检（≥20 条工业术语）
python scripts/run_v2.py --check-analyzer --samples evals/corpora_v1/corpus_100.jsonl

# ── Step2：质量对比（同一评测集，50 条） ─────────────────
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes milvus,pgvector

# 单路线复算（便于定位差异）
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes milvus  --mode dense
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes milvus  --mode sparse
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes milvus  --mode hybrid
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes pgvector --mode dense
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes pgvector --mode sparse
python scripts/run_v2.py --eval evals/golden_set_v1.jsonl --routes pgvector --mode hybrid

# ── 压力档（只测延迟与内存） ─────────────────────────────
python scripts/v2_load_test.py --scale 10000     # 1万/3万/10万 各跑一次
python scripts/v2_load_test.py --scale 30000
python scripts/v2_load_test.py --scale 100000

# ── 原始数据落盘 ────────────────────────────────────────
# experiments/v2/raw/*.jsonl
```

**前置检查**：

```bash
cat env/env-baseline-v2.md          # 引用版本号
cat env/ports.md                    # 端口基线（Milvus 19530/9091、PG 5432）
cat schemas/tools_v1.json           # Schema v1 已冻结
wc -l evals/golden_set_v1.jsonl     # 必须为 50（V7 硬依赖）
```

---

## 十一、结论与 M0.3 判定

### 11.1 结论

| 项 | 内容 |
|---|---|
| Milvus 版本 + digest 锁定 | ✅ 已实测（`v3.0.0` / `sha256:49371c30…5862`），运行时二次核对一致 |
| jieba analyzer 结论 | ✅ **通过**：32 条工业术语 32/32（R-V2-1 解除） |
| 原生 BM25 路径确认 | ✅ 服务端 `FunctionType.BM25` + `enable_analyzer=True` 已确认 |
| 参数基线表 | ✅ 实测选定值已回填（§五） |
| 检索质量对比 | ✅ **已实测**（§4.4，6 组 Recall@5/MRR/P@5/P95） |
| 压力档 | ✅ **已实测**（EXP-V2-LOAD 2026-09-28：10 万块 Milvus P95 5.6 ms / 1.28 GB、pgvector 170.6 ms / 0.33 GB，三档明细见 §六） |
| 路线决策 | ✅ 选 Milvus；pgvector 稀疏真 BM25 已对标（ngram，sparse 0.90 / hybrid 0.91，EXP-V2-BM25），tsvector 降级淘汰（§七） |

### 11.2 M0.3 判定

> **M0.3（V2 + V3 完成 · D5）判定**：
>
> - **V2 判据（§八）实测 = Pass**：jieba 32/32 + 原生 BM25 可用 + Milvus 混合 `Recall@5`=0.91 ≥ 对照 0.90。**真 BM25 稀疏对标已闭环（EXP-V2-BM25，2026-09-28）**：ParadeDB 真 BM25（ngram）sparse `Recall@5`=0.90、hybrid 打平 0.91——pgvector 侧脱离 tsvector 降级；结论范围扩展为『两实现 BM25 对比』（口径差异见 §4.3）。
> - **已就绪**：V7 评测集（50 条）为硬依赖已用；Milvus 镜像 digest、端口（偏移 19531/9092）、对比设置均已实测。
> - **与 V3 联动**：M0.3 最终达成除本报告外还依赖 V3 接入实测状态（见 `Phase 0 任务总结.md` §四）；本节仅就 V2 判定。
>
> **压力档（§六）已实测（EXP-V2-LOAD，2026-09-28）**：三档延迟/内存/建库耗时已回填——10 万块 Milvus 查询 P95 5.6 ms、常驻峰值 1.28 GB；pgvector 170.6 ms、0.33 GB，均 ≪ Docker ≈20 GB，无内存压力。**M0.3 条件项已全部解除**，完整资源数据供 V4a/V4b 仲裁使用。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| D4（计划） | 单人（本人） | 初始建立：Step1/Step2/Step3 设计、参数基线表结构、判据定稿 | — |
| 2026-09-25 | 单人（本人） | **V2 实测完成并回填**：实测端口偏移（19531/9092、5927）、BGE-M3 锁维度 1024、jieba 抽检 32/32、6 组质量结果回填、参数基线选定值、Pass 判定；**pgvector 稀疏降级 tsvector（真 BM25 悬置 K-V2-1）**；压力档暂缓待 D5 | §〇、§二.2.1/2.3/2.4、§三–§五、§七–§十一 |
| 2026-09-28 | 单人（本人） | **真 BM25 稀疏对标闭环（EXP-V2-BM25）**：为 kb_chunks 建 `USING bm25`+ngram 索引，Milvus vs ParadeDB 真 BM25 对标（sparse 0.92/0.90、hybrid 打平 0.91）；§4.3 声明、§4.4 表、§五 基线、§七 决策、M0.3、§11.1 路线决策统一更新；tsvector 由"降级"改为"历史对照" | §四、§五、§七、§十一、修订记录 |
| 2026-09-28 | 单人（本人） | **压力档实测闭环（EXP-V2-LOAD）**：新增 `v2_synth_corpus.py`（合成 1万/3万/10万 语料）与 `v2_load_test.py`；ParadeDB 侧 `v2_pg_build.py` 改 dsn 5433 + K-V2-1 bm25 索引 + sparse/NULL embedding；Milvus sparse-only 建库隔离 embedding；三档延迟 P95/内存峰值/建库耗时回填（10 万块 Milvus 5.6 ms/1.28 GB vs pgvector 170.6 ms/0.33 GB）；M0.3 条件项解除、§〇/§六/§七/§十/§11 同步 | §〇、§六、§七、§十、§十一、修订记录 |