# Phase 1 详细开发计划（数据接入与知识库构建）

> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §九
> **前一阶段**：Phase 0（技术验证与范围锁定）——须 **M0.6 门禁通过**后启动
> **本阶段定位**：把 Phase 0 的"验证结论"变为"可运行的数据底座"——打通 **IoT 数据接入**与**离线知识库构建**两条链路，为 Phase 2（混合检索）与 Phase 3（Agent 工作流）提供数据与接口基线。
> **执行主体**：单人（"机器并行、人串行"）
> **总工期**：10 个工作日（P1-D1 – P1-D10）
> **制定日期**：2026-09-21

---

## 目录

- [一、阶段目标与出口](#一阶段目标与出口)
- [二、阶段前置（Phase 0 移交物核对）](#二阶段前置phase-0-移交物核对)
- [三、工作分解（WBS）](#三工作分解wbs)
- [四、逐日计划（P1-D1 – P1-D10）](#四逐日计划p1-d1--p1-d10)
- [五、关键模块详细设计](#五关键模块详细设计)
- [六、里程碑](#六里程碑)
- [七、验收标准与质量门槛](#七验收标准与质量门槛)
- [八、风险与应对](#八风险与应对)
- [九、交付物清单与目录](#九交付物清单与目录)
- [十、每日检查清单](#十每日检查清单)

---

## 一、阶段目标与出口

### 1.1 阶段目标

> 建成一个**可运行的"数据底座"**：
> ① **接入侧**：模拟 Sparkplug B 遥测 → MQTT → TDengine，并产生/去重告警；
> ② **知识侧**：PDF/工单 → MinerU 解析 → Parent-Child 分块 → **三存储写入**（Milvus 稠密+稀疏 / Neo4j 三元组 / PostgreSQL 元数据与版本）；
> ③ **一致性**：以 Outbox + 对账保证三写不静默丢数据。

### 1.2 阶段出口（M1.4）

| 出口物 | 判据 |
|---|---|
| IoT 接入链路 | 模拟数据 → TDengine 落库 → 告警产生 → Redis 去重，**端到端可复现** |
| 知识库 | 语料完成解析/分块/建库，**可检索到预期文档块** |
| 三元组 | 抽取准确率 **≥85%**（100 条人工评估）后全量入库 |
| 一致性 | 失败注入测试下 **对账零差异**；补偿队列可自愈 |
| 移交物 | 数据字典 + 接口基线 + 建库参数 → 供 Phase 2 直接使用 |

### 1.3 与前后阶段的关系

```
Phase 0（验证/锁定）
   └─► Phase 1（本阶段：数据底座）
            ├─► Phase 2 混合检索（复用建库参数与语料）
            ├─► Phase 3 Agent 工作流（复用 query_sensor 契约、告警入口）
            └─► Phase 4 前端（复用业务表结构）
```

---

## 二、阶段前置（Phase 0 移交物核对）

> **启动本阶段前，逐项确认以下 Phase 0（M0.6）产出可用；缺失项须先补齐，否则会返工。**

| # | 移交物 | 用途 | 状态 |
|---|---|---|---|
| 1 | `schemas/tools_v1.json` | 工具契约基线（本阶段实现 `query_sensor`） | ☐ |
| 2 | `env/env-baseline-v1.md` | 环境基线（所有实验引用） | ☐ |
| 3 | `docs/version-lock.md` | 组件版本 + digest（建库/接入须一致） | ☐ |
| 4 | `docs/schema-mapping.md` | Sparkplug topic/metric → 超级表/列 | ☐ |
| 5 | `reports/v3-auth.md` | TDengine 连接器授权结论（决定接入形态） | ☐ |
| 6 | **V2 结论：Milvus 版本 + analyzer + 建库参数基线** | 建库直接复用，不重做 | ☐ |
| 7 | `docs/known-issues.md` | checkpoint/一致性规避清单 | ☐ |
| 8 | `evals/golden_set_v1.jsonl` | 建库后召回抽检 | ☐ |
| 9 | `docs/scope-mvp.md` | Must 链范围（本阶段只做 Must 相关） | ☐ |
| 10 | `docs/handover-p1.md` | Phase 0 → Phase 1 移交清单 | ☐ |

> **降级预案**：若 V3 判定连接器为商业授权，本阶段接入形态改用 `reports/v3-auth.md` 指定的降级路径（自研 Protobuf 消费者或 MQTT JSON 直写），工期 +2 天并顺延里程碑。

---

## 三、工作分解（WBS）

### 3.1 两条主线

| 主线 | 工作包 | 目标 |
|---|---|---|
| **A · IoT 数据接入与告警** | A1 接入器 · A2 时序 Schema · A3 告警引擎 · A4 端到端联调 | 告警事件流可用 |
| **B · 知识库构建** | B1 解析 · B2 分块 · B3 Milvus 建库 · B4 三元组 · B5 PG 元数据/版本 · B6 一致性 | 三存储可检索且一致 |

### 3.2 工作包一览

| 包 | 任务 | 产出物 |
|---|---|---|
| **A1** | MQTT Broker + Sparkplug B 接入器（taosX 或降级路径） | `docker/compose.ingest.yml`、接入配置 |
| **A2** | 时序 Schema（超级表/子表/列）+ 模拟数据生成器 | `configs/tdengine/`、`scripts/gen_sparkplug.py` |
| **A3** | 告警引擎（阈值 + 滑动窗口 Z-Score）+ Redis 去重 | `scripts/alarm_engine.py`、`configs/alarm_rules.yml` |
| **A4** | 端到端联调（模拟→落库→告警→去重） | `reports/p1-ingest.md` |
| **B1** | MinerU 解析（**首日 Spike** → 全量） | `scripts/parse_docs.py`、`parsed/` |
| **B2** | Parent-Child 分块 + 元数据标注 | `scripts/chunk_docs.py`、`chunks_v1.jsonl` |
| **B3** | Milvus 建库（Dense BGE-M3 + Sparse BM25/jieba） | `scripts/build_milvus.py` |
| **B4** | 三元组抽取（人工评估 ≥85%）→ Neo4j 入库 | `scripts/extract_triples.py`、`configs/neo4j/` |
| **B5** | PostgreSQL 元数据与版本表 | `db/migrations/`、`work_orders` 导入脚本 |
| **B6** | Outbox + 补偿队列 + 对账脚本 | `scripts/outbox_worker.py`、`scripts/reconcile.py` |

### 3.3 依赖关系

```
A1 ─► A2 ─► A3 ─► A4
B1 ─► B2 ─┬─► B3 ──┐
          ├─► B4 ──┼─► B6 ─► 验收
          └─► B5 ──┘
B1（首日 Spike）为关键路径起点；A 与 B 两条主线可机器并行
```

---

## 四、逐日计划（P1-D1 – P1-D10）

### D1 · 首日 Spike + 骨架搭建

> **关键**：**MinerU 解析质量是 Phase 1 最大不确定性**，必须首日验证，不通过立即影响后续工期。

| 任务 | 步骤 | 产出 |
|---|---|---|
| B1-Spike | 用 MinerU 解析 **3 类样本**：① 文本型 PDF ② 扫描件 PDF ③ 含表格 PDF；检查文本完整率/表格还原/图片处理 | `reports/p1-mineru-spike.md` |
| A1 骨架 | 起 Mosquitto + TDengine + taosX（或降级路径），打通 MQTT 连接 | `docker/compose.ingest.yml` |
| 环境复用 | 复用 Phase 0 `env-baseline-v1.md`；启动 Milvus/Neo4j/PG/Redis | 运行中 |
| PG 迁移 | 建立 `documents/doc_chunks/knowledge_versions/work_orders/outbox/alerts` 表 | `db/migrations/0001_init.sql` |

**MinerU Spike 判据**：文本型 PDF 文本完整率 ≥95%；扫描件 OCR 可读；三样本均能产出结构化 markdown。
**不通过应对**：改用替代解析（PyMuPDF + PaddleOCR 组合）并评估 +1~2 天工期。

### D2–D3 · IoT 接入与告警（主线 A）

| 天 | 任务 | 产出 |
|---|---|---|
| D2 | A2 时序 Schema 落地（超级表/子表/列，复用 Phase 0 `schema-mapping.md`）；编写 Sparkplug B 模拟数据生成器（振动/温度/电流，含 NBIRTH/DBIRTH/NDATA） | `configs/tdengine/`、`scripts/gen_sparkplug.py` |
| D3 | A3 告警引擎（阈值规则 + 滑动窗口 Z-Score）+ Redis 去重（`dedup:alarm:{device}:{metric}`，5min）；A4 端到端联调 | `scripts/alarm_engine.py`、`configs/alarm_rules.yml` |

**A4 联调验收**：模拟数据 → TDengine 可查 → 阈值告警产生 → 5min 内同类告警合并为 1 条 → 标准 `AlarmEvent` 落盘。
**出口：M1.1**

### D3–D5 · 解析与分块（主线 B 前半）

| 天 | 任务 | 产出 |
|---|---|---|
| D3–D4 | B1 全量解析（按 `data-sources-v1.md` 清单） | `parsed/*.md` + `parsed/*.json` |
| D4 | B2 Parent-Child 分块：父块（章节级）→ 子块（段落级）；元数据（来源/型号/章节/页码/父块 ID） | `scripts/chunk_docs.py`、`chunks_v1.jsonl` |
| D5 | B3 Milvus 建库：Dense(BGE-M3) + Sparse(BM25/jieba)，参数**直接复用 V2 参数基线表** | `scripts/build_milvus.py` |

**分块抽检**：随机抽 20 个块，人工检查"语义完整性 + 父块关联正确"。
**出口：M1.2**

### D5–D8 · 三元组与 Neo4j（主线 B 中段）

| 天 | 任务 | 产出 |
|---|---|---|
| D5–D6 | B4 三元组抽取（LLM + Schema 约束）；**先抽 100 条做人工评估** | `scripts/extract_triples.py`、`reports/p1-triples-eval.md` |
| D7 | **质量门槛判定**：准确率 ≥85% 才全量；否则调 Prompt/词典重试 | 评估结论 |
| D7–D8 | 全量抽导入 Neo4j（约束 + 关系类型） | `configs/neo4j/constraints.cypher` |
| D7–D8 | B5 工单/文档元数据入 PostgreSQL + 版本表 | `scripts/load_meta.py` |

**关系类型**（与诊断链对齐）：`CAUSES` / `PART_OF` / `MITIGATED_BY` / `HAS_SYMPTOM` / `LOCATED_AT` / `REQUIRES`。
**出口：M1.3**

### D8–D9 · 一致性机制（B6）

| 任务 | 说明 | 产出 |
|---|---|---|
| Outbox 模式 | 写 PG(`status=pending`) → Worker 写 Milvus/Neo4j → 全成功置 `indexed`；失败入补偿队列 | `scripts/outbox_worker.py`、`db/migrations/0002_outbox.sql` |
| 补偿队列 | 指数退避重试，≥5 次告警人工介入 | 同上 |
| 对账脚本 | 每日比对 PG / Milvus / Neo4j 的 `chunk_id` 集合，输出差异 | `scripts/reconcile.py` |
| **失败注入测试** | 人为中断 Milvus 写入，验证补偿与对账能发现并修复 | `reports/p1-consistency.md` |

### D9–D10 · 质量验收与移交

| 任务 | 内容 | 产出 |
|---|---|---|
| 召回抽检 | 用 `golden_set_v1.jsonl` 抽 10 条，验证能检索到预期块 | `reports/p1-recall-smoke.md` |
| 数据字典 | 表结构、字段、枚举、Milvus Collection/Neo4j 标签说明 | `docs/data-dictionary.md` |
| 接口基线 | `query_sensor` 实现 + `search_knowledge` 数据侧就绪 | `docs/p1-interfaces.md` |
| 移交 Phase 2 | 建库参数、语料、评测集挂载说明 | `docs/handover-p2.md` |
| 门禁评审 | 逐项过 §七 判据 | **M1.4** |

---

## 五、关键模块详细设计

### 5.1 A1 · MQTT + Sparkplug B 接入

| 项 | 设计 |
|---|---|
| Broker | Mosquitto 2.x（默认）；若 Phase 0 判定需 EMQX 则切换 |
| 解码 | taosX SparkplugB 零代码接入；降级路径见 `reports/v3-auth.md` |
| 主题 | `spBv1.0/{group}/{message_type}/{edge_node}/{device}` |
| 消息类型 | `NBIRTH/DBIRTH/NDATA/NDEATH/DDATA/DCMD/STATE` |
| 目标 | 写入 TDengine 超级表（按设备型号） |

### 5.2 A2 · TDengine 时序 Schema（示例）

```sql
-- 超级表：按设备型号建模
CREATE STABLE IF NOT EXISTS telemetry (
    ts          TIMESTAMP,
    vibration   FLOAT,
    temperature FLOAT,
    current     FLOAT
) TAGS (
    device_id   NCHAR(64),
    device_model NCHAR(32),
    workshop    NCHAR(32)
);

-- 子表随 DBIRTH 自动/脚本创建
CREATE TABLE IF NOT EXISTS d_pump_001 USING telemetry
    TAGS ('pump_001', 'centrifugal_pump_A', 'line_3');
```

### 5.3 A3 · 告警引擎与去重

```
规则：
  阈值告警：vibration > 4.5 mm/s  → severity=high
            temperature > 85°C    → severity=high
            current > 额定 * 1.15 → severity=medium
  统计异常：滑动窗口(30min) Z-Score > 3 → severity=medium
            （需 ≥7 天基线；无基线时仅用阈值规则）

去重：
  key = dedup:alarm:{device_id}:{metric}
  TTL = 5min（Redis 滑动窗口），同 key 命中则合并计数不重复触发

输出（AlarmEvent）：
  {alarm_id, device_id, metric, value, baseline, severity, ts, rule_id, dedup_count}
```

### 5.4 B1 · MinerU 解析

| 步骤 | 说明 |
|---|---|
| 输入 | `data-sources-v1.md` 清单中的 PDF/工单 |
| 引擎 | MinerU（VLM + OCR 双引擎，覆盖扫描版） |
| 输出 | 结构化 markdown + 版面 JSON（含标题层级、表格、图片引用） |
| 质量校验 | 文本完整率、表格还原、页眉页脚剔除；抽样人工比对 |
| 失败处理 | 单文件失败重试 2 次；批量失败率 >5% 触发替代解析评估 |

### 5.5 B2 · Parent-Child 分块与元数据

| 项 | 设计 |
|---|---|
| 父块 | 章节级（按标题层级切分），保留完整上下文 |
| 子块 | 段落级（~256–512 token），用于向量检索 |
| 元数据 | `source / doc_type / device_model / section / page / parent_id / version` |
| 检索增强 | 命中子块后回填父块上下文（供 Agent 使用完整段落） |

### 5.6 B3 · Milvus 建库（复用 V2 参数基线）

```python
# 与 V5.0 §12.1 一致；参数取自 Phase 0 的 V2 参数基线表
schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)
schema.add_field("doc_id",   DataType.VARCHAR, max_length=64)
schema.add_field("parent_id",DataType.VARCHAR, max_length=64)
schema.add_field("content",  DataType.VARCHAR, max_length=4096,
                 enable_analyzer=True, analyzer_params={"tokenizer": "jieba"})
schema.add_field("dense",    DataType.FLOAT_VECTOR, dim=1024)   # BGE-M3
schema.add_field("sparse",   DataType.SPARSE_FLOAT_VECTOR)      # 服务端 BM25
schema.add_function(Function(name="bm25_fn", input_field_names=["content"],
                             output_field_names=["sparse"],
                             function_type=FunctionType.BM25))
# 索引：dense=HNSW/COSINE；sparse=SPARSE_INVERTED_INDEX/BM25
```

> 建库完成后用 `golden_set_v1.jsonl` 抽 10 条做**召回冒烟**（非正式指标，正式在 Phase 2）。

### 5.7 B4 · 三元组抽取与质量门槛

| 项 | 设计 |
|---|---|
| 抽取模型 | 按 Phase 0 `role-decision.md` 选定（优先 `qwen2.5:7b` + Schema 约束） |
| 约束 | 实体/关系类型受控词表；输出 JSON Schema 校验 |
| **门槛** | **先抽 100 条人工评估，准确率 ≥85% 方可全量** |
| 低置信处置 | 低置信三元组进"待人工确认"队列，不直接入图 |
| 图谱 Schema | 实体 `:Entity{id,name,type}`；关系按受控类型；`graph_support` 用于置信度 |
| 导入 | `LOAD CSV` 或 `MERGE` 语句批量写入 Neo4j |

```cypher
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name);
```

### 5.8 B5 · PostgreSQL 业务表（DDL 摘要）

```sql
-- 文档主表
CREATE TABLE documents (
    doc_id     UUID PRIMARY KEY,
    title      TEXT NOT NULL,
    source     TEXT NOT NULL,
    doc_type   TEXT NOT NULL,             -- manual|work_order|procedure
    device_model TEXT,
    checksum   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending',  -- pending|indexed|failed
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 分块
CREATE TABLE doc_chunks (
    chunk_id   VARCHAR(64) PRIMARY KEY,
    doc_id     UUID NOT NULL REFERENCES documents(doc_id),
    parent_id  VARCHAR(64),
    content    TEXT NOT NULL,
    section    TEXT,
    page       INT,
    token_count INT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 知识版本
CREATE TABLE knowledge_versions (
    id BIGSERIAL PRIMARY KEY,
    doc_id UUID NOT NULL,
    version INT NOT NULL,
    action TEXT NOT NULL,                 -- create|update|delete
    actor  TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 工单
CREATE TABLE work_orders (
    order_id   TEXT PRIMARY KEY,
    device_id  TEXT NOT NULL,
    fault      TEXT NOT NULL,
    action     TEXT NOT NULL,
    result     TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

-- 告警状态
CREATE TABLE alerts (
    alarm_id  TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    metric    TEXT NOT NULL,
    value     NUMERIC,
    severity  TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'open',
    ts        TIMESTAMPTZ NOT NULL
);
```

### 5.9 B6 · Outbox 一致性

```sql
CREATE TABLE outbox (
    id          BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,          -- document|chunk
    entity_id   TEXT NOT NULL,
    op          TEXT NOT NULL,          -- upsert|delete
    target      TEXT NOT NULL,          -- milvus|neo4j
    payload     JSONB,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|done|failed
    retry_count INT NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

```
流程：
  ① 写 PG(document, status='pending') + 写 outbox(milvus, neo4j 两条)
  ② outbox_worker 消费 → 写 Milvus/Neo4j
  ③ 全部 done → document.status='indexed'
  ④ 失败 → status='failed'，指数退避重试；≥5 次 → 告警人工介入
  ⑤ reconcile.py 每日比对 chunk_id 集合，输出差异报告
```

**权威源**：**PostgreSQL 为唯一权威源**，Milvus/Neo4j 为可重建索引。

---

## 六、里程碑

| 里程碑 | 内容 | 时间 | 通过条件 |
|---|---|---|---|
| **M1.1** | 接入链路打通 | P1-D3 | 模拟数据 → TDengine → 告警产生 → 去重，端到端可复现 |
| **M1.2** | 解析与建库完成 | P1-D5 | 语料解析/分块完成，Milvus 可检索到预期块 |
| **M1.3** | 三元组与图谱 | P1-D8 | 抽取准确率 ≥85%，Neo4j 可查关系路径 |
| **M1.4** | 一致性与移交 | P1-D10 | 失败注入下对账零差异；数据字典/接口基线齐备 |

---

## 七、验收标准与质量门槛

### 7.1 量化门槛

| 项 | 门槛 | 测量方式 |
|---|---|---|
| MinerU 文本完整率（文本型 PDF） | ≥ 95% | 抽样人工比对 |
| 解析批量失败率 | ≤ 5% | 统计 |
| 分块语义完整性 | 抽检 20 块全通过 | 人工抽检 |
| **三元组抽取准确率** | **≥ 85%** | 100 条人工评估 |
| 时序落库一致性 | 100% 无丢失 | 生成 N 条 vs 查询 N 条 |
| 告警去重有效率 | 5min 内同类合并为 1 条 | 统计 |
| **对账差异（失败注入后）** | **0** | `reconcile.py` |
| 召回冒烟（10 条抽样） | 命中预期块 | `golden_set_v1.jsonl` |

### 7.2 门禁判定

| 情况 | 处置 |
|---|---|
| 全部达标 | **M1.4 通过**，进入 Phase 2 |
| 三元组 70–85% | 调整 Prompt/词典/Analyzer 复测；仍不达标则**限制图谱用途**（仅作线索，不作主证据）并记录代价 |
| MinerU 失败率 >5% | 启用替代解析方案，工期 +1~2 天 |
| 对账存在差异 | **阻塞**：必须先修复（属功能性缺陷） |
| 连接器授权不可用 | 按 `v3-auth.md` 降级路径执行，工期 +2 天 |

---

## 八、风险与应对

| 编号 | 风险 | 影响 | 应对 | 归属 |
|---|---|---|---|---|
| P1-R1 | MinerU 解析质量不达标 | 关键路径起点受阻 | D1 首日 Spike；备选 PyMuPDF+PaddleOCR | D1 |
| P1-R2 | 设备侧协议不可直连 | 接入路线作废 | 复用 Phase 0 授权结论；必要时自研 Protobuf 消费者 | D2–D3 |
| P1-R3 | 三元组准确率 <85% | 图谱污染诊断 | 100 条前置评估 + 受控词表 + 低置信隔离 | D5–D7 |
| P1-R4 | 中文分词不佳 | BM25 检索失效 | 复用 Phase 0 jieba 验证结论；建库后冒烟 | D5 |
| P1-R5 | 跨存储三写不一致 | 静默缺数据 | Outbox + 补偿 + 对账 + 失败注入测试 | D8–D9 |
| P1-R6 | 显存/内存争抢 | 建库与推理互拖 | 建库阶段错峰：嵌入走宿主 CPU/GPU、暂停 LLM 常驻 | 全程 |
| P1-R7 | 语料版权/隐私 | 无法使用真实数据 | 默认自编模拟数据兜底（Phase 0 已定） | D1 |
| P1-R8 | 数据量增长导致 Milvus 内存峰值 | 超 24GB 判据 | 分批导入 + 监控峰值；必要时调 `cache.memoryLimit` | D5 |
| P1-R9 | Redis 驱逐 checkpoint | 后续 Phase 3 审核受损 | 建库期即固定 `noeviction` | D1 |

---

## 九、交付物清单与目录

### 9.1 目录增量

```
project/
├─ db/migrations/
│  ├─ 0001_init.sql
│  └─ 0002_outbox.sql
├─ configs/
│  ├─ tdengine/            # 超级表/子表定义
│  ├─ alarm_rules.yml      # 告警规则
│  └─ neo4j/constraints.cypher
├─ scripts/
│  ├─ gen_sparkplug.py     # 模拟数据生成
│  ├─ alarm_engine.py      # 告警 + 去重
│  ├─ parse_docs.py        # MinerU 解析
│  ├─ chunk_docs.py        # Parent-Child 分块
│  ├─ build_milvus.py      # 建库
│  ├─ extract_triples.py   # 三元组抽取
│  ├─ load_meta.py         # 元数据/工单入库
│  ├─ outbox_worker.py     # 一致性
│  └─ reconcile.py         # 对账
├─ parsed/                 # 解析产物
├─ chunks/chunks_v1.jsonl  # 分块结果
├─ reports/
│  ├─ p1-mineru-spike.md
│  ├─ p1-ingest.md
│  ├─ p1-triples-eval.md
│  ├─ p1-consistency.md
│  ├─ p1-recall-smoke.md
│  └─ P1-summary.md
└─ docs/
   ├─ data-dictionary.md
   ├─ p1-interfaces.md
   └─ handover-p2.md
```

### 9.2 交付物清单

| 类别 | 交付物 |
|---|---|
| 接入 | `compose.ingest.yml`、时序 Schema、告警规则、端到端联调报告 |
| 解析 | 解析脚本、`parsed/` 产物、MinerU Spike 报告 |
| 分块 | 分块脚本、`chunks_v1.jsonl`、抽检记录 |
| 建库 | Milvus 建库脚本与参数、Neo4j 约束与数据、PG 迁移与元数据 |
| 一致性 | Outbox Worker、对账脚本、失败注入报告 |
| 移交 | 数据字典、接口基线、`handover-p2.md` |

---

## 十、每日检查清单

### 通用规则

- [ ] 复用 `env-baseline-v1.md` 与 `version-lock.md` 的版本/digest
- [ ] 建库参数**直接复用 Phase 0 V2 基线表**，不重新调参
- [ ] 所有脚本可重复执行（幂等），支持断点续跑
- [ ] 关键中间数据落盘可追溯

### D1
- [ ] MinerU Spike 三样本结论（文本/扫描/表格）
- [ ] PG 迁移 `0001_init.sql` 执行成功
- [ ] MQTT + TDengine 连通

### D2–D3（M1.1）
- [ ] 模拟数据可写入 TDengine 并查询
- [ ] 阈值告警触发 + 5min 去重生效
- [ ] `AlarmEvent` 结构符合契约

### D4–D5（M1.2）
- [ ] 全量解析完成，失败率 ≤5%
- [ ] 分块元数据齐全，抽检 20 块通过
- [ ] Milvus 建库完成，冒烟可检索

### D6–D8（M1.3）
- [ ] 100 条三元组评估准确率 ≥85%
- [ ] Neo4j 约束建立，关系路径可查
- [ ] 工单/文档元数据入库 + 版本表可用

### D8–D9
- [ ] Outbox 全流程跑通
- [ ] 失败注入下补偿 + 对账零差异

### D10（M1.4）
- [ ] 召回冒烟通过
- [ ] 数据字典 + 接口基线 + `handover-p2.md` 齐备
- [ ] 逐项过 §七 判据，判定是否进入 Phase 2

---

## 附：Phase 1 → Phase 2 移交要点

| 移交项 | 用途 |
|---|---|
| Milvus 建库参数与 Collection Schema | Phase 2 直接做检索优化 |
| `chunks_v1.jsonl` + 父块映射 | 语境回填 |
| Neo4j 图谱与关系类型 | `query_graph` 工具实现 |
| `query_sensor` 实现 + 时序 Schema | Agent 工具集成 |
| 告警事件流 | Agent 触发入口 |
| `golden_set_v1.jsonl` 挂载 | 正式检索指标评测 |
| `reconcile.py` | 持续数据质量保障 |
