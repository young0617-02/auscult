# 云侧工业 IoT 诊断 Agent 系统 — 项目全景总结
> **⚠️ 历史留痕（2026-10-08 文档同步加注，正文结论未改）**：本文所载判定为 **2026-09-28** 时点。文件名已按规范改为 `p0-summary-project-2026-09-28.md`（原 `reports/project-overview.md`）。 全景快照，**已被 `reports/p0-summary-project-2026-09-29.md` 与 10-08 过闸报告取代**，保留备查。 当前口径见 `README.md` §当前状态速览 与 `docs/p0-spec-gate-criteria.md` §六；裁决依据 `reports/p0-gate-m02-verdict-2026-10-08.md`。

> **项目根**：`<REPO>`
> **主场景**：离心泵驱动端轴承振动异常诊断
> **当前阶段**：Phase 0（技术验证与范围锁定，D0 + D1–D10）
> **文档基准日期**：2026-09-28
> **文档性质**：面向团队的项目全景速览（不含新实测，全部数据引自现有报告/文档）
>
> ⚠️ **本文已被覆盖更新**：`reports/p0-summary-project-2026-09-29.md`（2026-09-29）为**最新全景总结**，
> 含 2026-09-29 代码—文档一致性审计的全部修正结果（含 V3 P95 26.2 ms、ParadeDB 端口 5433、
> 裸 tag 已清零、`--selftest` 覆盖实际情况等）。**有冲突时以后者与各原始报告为准。**
> 本文件保留作 2026-09-28 时点的历史快照。

---

## 一、项目概述

**一句话定位**：一个**云侧、本地优先**的工业设备智能诊断 Agent —— 把「时序遥测 + 设备知识 + 图谱关系 + 维修历史」四类证据汇聚给 LLM，自动完成**告警 → 诊断推理 → 证据引用 → 报告生成 → 高风险人工审核**的闭环，主场景锁定在离心泵轴承振动异常。

**核心设计取向**：

| 取向 | 具体表现 |
|---|---|
| 证据驱动 | 每条结论必须带 `EvidenceItem`（chunk_id / doc_id / source / page），**无来源不出结论** |
| 本地优先 | LLM 推理走宿主 Ollama（`127.0.0.1:11434`），容器只承载 DB/存储 |
| 判据前置 | 任一验证项开跑前，Pass / 中间区间 / No-Go 必须先定稿（三条铁律之一） |
| 降级必带代价 | 任何替代方案都要标注对 `Recall@5` 与 `P95` 的影响 |
| 不编造数字 | 未实测项一律写 `【待实测填入】`，禁止"预计/大约"伪装 |
| 可复现 | 组件/模型一律以 digest 锁定；模拟数据固定 seed + `synthetic: true` 标记 |

**阶段定位**：Phase 0 只做「技术验证 + 范围锁定」，产出的结论直接作为 Phase 1（数据接入与知识库构建）的输入基线。

---

## 二、主要功能点（Must 链 13 项）

上游 V5.0 定稿锁定的端到端必须闭环能力（逐字提取，未增减）：

| # | 能力 | 可验收判据 | 依赖验证项 |
|---|---|---|---|
| 1 | **告警产生** | 模拟 Sparkplug B 数据触发阈值告警，产出标准 `AlarmEvent` | V3 |
| 2 | **告警去重** | 5min 内同类告警合并（`dedup:alarm:{device_id}:{metric}`） | V3 |
| 3 | 传感器分析 | `query_sensor` 返回 avg/max/min/p95/trend + `anomaly` 标记 | V3 |
| 4 | 混合检索 | `search_knowledge` 在 50 条评测集上 `Recall@5` ≥ 85% | V2 / V7 |
| 5 | 图谱检索 | `query_graph` 返回 ≥1 条 `GraphPath`（nodes/relations/confidence） | V3 后续 / P1 |
| 6 | 诊断推理 | 输出 `root_causes` + `suggestions` + `confidence` 复合公式 | V1 / V2 |
| 7 | **证据引用强制** | 每条结论带 `EvidenceItem`；无来源不出结论 | V2 / V5 |
| 8 | 报告生成 | 结构化报告落 `reports` 表，状态 ∈ {pending_review, published, degraded} | V5 |
| 9 | **高风险审核** | 高风险命中 → `interrupt()` 强制人工审核，覆盖率 100% | V5 |
| 10 | 业务表落库 | 报告 + 审核记录入 PostgreSQL（唯一权威源） | V5 / P1 |
| 11 | 审计日志 | 全操作追加记录不可篡改（追加表 + 禁改触发器） | V5 / P1 |
| 12 | 降级路径 | 低置信度（<0.50）标注"初步判断，建议人工确认"，不自动出正式报告 | V1 / V5 |
| 13 | 前端展示 | 五类页面可用（告警看板 / 诊断对话 / 报告详情+审核 / 知识库 / 图谱可视化） | P4 |

**明确不做（Won't）**：多租户、模型微调（预留 LoRA 接口）、复杂 GraphRAG 多跳（>2 跳）、移动端、真实 Modbus/OPC UA 直连（预留边缘网关转 MQTT 接口）、**自动执行维修动作（永久安全刚性）**。

**Should/Could**（不计入 Must）：对话式追问、图谱可视化、Prometheus 指标面板 / 多设备扩展、GraphRAG 多跳、模型微调。

---

## 三、技术栈

### 3.1 硬件与运行环境

| 项 | 实测值 |
|---|---|
| OS / 主机 | Windows 10 Pro 25H2（build 26200）/ `<WORKSTATION>` |
| CPU | i7-13650HX，20 逻辑核（6P + 8E） |
| 内存 / GPU | 32 GB / RTX 4060 Laptop 8 GB（8188 MiB，驱动 616.56，CC 8.9） |
| WSL2 配额 | memory=20 GB / processors=10 / swap=8 GB（`.wslconfig` 已核验生效） |
| Docker | 引擎 29.6.2 / Compose v5.3.1 |
| 门禁线 | 峰值 ≤ 24 GB（= 32 GB × 75%，口径 B：宿主总占用） |

### 3.2 组件（8 个 Docker 镜像，均锁 digest）

| 组件 | Tag | 用途 |
|---|---|---|
| `milvusdb/milvus` | `v3.0.0` | **V2 主路线**（向量 + 稀疏 BM25） |
| `quay.io/coreos/etcd` | `v3.5.25` | Milvus 依赖 |
| `minio/minio` | `RELEASE.2024-12-18T13-15-44Z` | Milvus 依赖 |
| `postgres` | `18` | 业务库基线 |
| `paradedb/paradedb` | digest 锁定 | V2 对照路线（pgvector + pg_search 真 BM25），宿主端口 **5433**（原 5927 被 `smart-doc-db` 占用已整改），库 `auscult_v2` |
| `redis` | `8` | V5 checkpoint 候选 A（最终未采用） |
| `tdengine/tsdb` | `3.3.8.0` | V3 时序库（OSS，自研解码器路线） |
| `eclipse-mosquitto` | `2` | V3 MQTT Broker（Sparkplug B 传输层） |
| `neo4j` | `5-community` | 图谱库 |

### 3.3 模型（均经 Ollama 加载，锁 manifest digest）

| 模型 | 大小 | 角色 | 备注 |
|---|---|---|---|
| `qwen2.5:7b` | 4.68 GB | 候选 A（通用指令模型） | 无 `think` 输出；显存占用 5773 MiB |
| `deepseek-r1:7b` | 4.68 GB | 候选 B（推理模型） | **含 `think`，须剥离**；显存 5779 MiB |
| `BGE-M3` | 1.2 GB | V2 向量化（dim=1024，F16） | 经 `/v1/embeddings`，显存 6512 MiB |
| `Qwen/Qwen3.8-27B`（云端） | — | V1 上界校准（非默认部署） | ModelScope OpenAI 兼容端点 |

### 3.4 工具链与依赖

- **运行时**：Python 3.12.8 / Node.js v24.19.0 / Git 2.45.1 / Ollama **0.34.2**（已锁定不升级）
- **Python 关键库**：`pymilvus` 3.0.2、`psycopg` 3.3.6、`jieba` 0.42.1、`paho-mqtt` 2.1.0、`taospy`/`taosrest` 2.8.10、`protobuf` 7.36.2、`grpcio` 1.84.0、`langgraph` 1.2.12、`langgraph-checkpoint-postgres` 3.1.2、`langgraph-checkpoint-redis` 0.5.2（未采用）
- **固定实验参数**：`temperature=0`、`seed=42`、`num_ctx=8192`、`top_p=1.0`、`max_tokens=1024`、`stream=false`

---

## 四、模块划分与目录结构

```
auscult/
├─ plan/          阶段开发计划（Phase 0 D1-D10 / Phase 1）
├─ docs/          15 份治理与规范文档（范围/判据/风险/版本/缺陷/移交…）
├─ reports/       验证报告 v1–v5 + p0-gate-review + daily/D1-status
├─ schemas/       tools_v1.json（5 工具 Schema，FROZEN）
├─ protos/        sparkplug_b.proto + 生成的 PB 类
├─ configs/       decoder_schema_mapping.json / mosquitto.conf / redis.conf / milvus
├─ docker/        compose.base.yml / compose.ingest.yml / Dockerfile.decoder
├─ scripts/       16 个 Python 执行器 + 2 个 PowerShell（其中 10 个带 --selftest，清单见下表）
├─ evals/         golden_set_v1(50) / v1_cases(20) / corpora_v1(100)
├─ experiments/   v1 / v2 / v4b / v5 原始实测数据（raw/，只增不改）
├─ env/           env-baseline-v2 / hardware.json / ports.md / wslconfig.*
└─ prompts/       tool_call_prompt_v1.md / v2.md
```

### 核心脚本（按验证项分组）

| 验证项 | 脚本 | 职责 |
|---|---|---|
| **V1** 工具调用 | `llm_adapter.py` | 统一适配层（Schema 注入 / `think` 剥离 / 静默退化识别） |
| | `judge_tools.py` | 判分器（draft-07 校验 / `time_range` ±10% 等价 / 8 指标汇总） |
| | `run_v1.py` | 批量执行器（多轮历史 / 回灌重试 / 断点续跑 / `--constrain` 约束解码） |
| | `gbnf_grammar.py` | 约束解码 Schema 生成（供 Ollama `format` 字段） |
| | `run_cloud_baseline.py` | 云端上界校准（不作为判据） |
| **V2** 混合检索 | `run_v2.py` | Milvus / pgvector × dense/sparse/hybrid 质量对比 + jieba 抽检 |
| | `v2_pg_build.py` | PG 侧建库灌数（含 ParadeDB ngram BM25 索引） |
| | `v2_synth_corpus.py` / `v2_load_test.py` | 压力档语料合成与延迟/内存实测 |
| **V3** 时序接入 | `spb_simulator.py` | 自建 Sparkplug B 模拟器（`--scenario` 驱动五类边界：`birth`/`new_metric`/`rebirth`/`offline`/`ndeath`） |
| | `self_decoder.py` | 自研 Sparkplug B 解码器（M1–M6，MQTT → Protobuf → TDengine REST） |
| **V4a** 环境 | `collect_env.ps1` / `check_ports.ps1` | 硬件采集 / 12 端口可用性检查 |
| **V5** checkpoint | `run_v5.py` | T5.1–T5.7 七步骤（恢复/幂等/并发/体积/TTL） |

---

## 五、关键实现逻辑

### 5.1 端到端数据流

```
IoT 侧： spb_simulator ──MQTT──> Mosquitto ──> self_decoder ──REST6041──> TDengine
                                                                  └─> st_pump_metrics / st_unmapped_metrics / st_device_status
知识侧： PDF/工单 ──MinerU解析──> Parent-Child 分块 ──> 三存储写入
                                                        ├─ Milvus（稠密 BGE-M3 + 稀疏 BM25/jieba）
                                                        ├─ Neo4j（三元组，准确率 ≥85%）
                                                        └─ PostgreSQL（元数据 + 版本 + 业务表）
Agent 侧：LangGraph 工作流 parse → readonly(read-only 工具) → diagnose → [interrupt 人工审核] → generate_report（图外执行）
```

### 5.2 工具契约（`schemas/tools_v1.json`，v1 已 FROZEN）

5 个工具：`query_sensor`、`search_knowledge`、`query_graph`、`get_maintenance_history`（4 个 read-only，图内）+ `generate_report`（唯一写操作，**移出图外**，必带 `idempotency_key` 防重复）。

> `change_policy`：一经冻结，任何修改必须升版 `tools_v2.json`，否则 V1 全部结论作废。

### 5.3 自研 Sparkplug B 解码器（V3 关键降级项）

因 TDengine 官方 Sparkplug B 连接器仅随 All-in-One/Enterprise，OSS 无 taosX，故**自研消费者**（方案 ≈1.9 人日，在 ≤2 天红线内）：

- 订阅 `spBv1.0/plant1/+/gw-pump-01/#` → Protobuf 解析 → 按 `configs/decoder_schema_mapping.json` 映射写入 TDengine
- M1 proto 工程 / M2 订阅分流 / M3 DBIRTH 建表 / M4 DDATA 写入 / M5 离线 / M6 re-birth 冲突判定
- **四类边界 4/4 实测通过**：建表、新增 metric 旁路（`st_unmapped_metrics` + schema_drift）、re-birth（bdSeq 比对）、离线状态翻转
- 局部写入原则：单个坏 metric 不丢整条报文

### 5.4 检索路线（V2）

| 路线 | 稠密 | 稀疏 | 混合 |
|---|---|---|---|
| **Milvus（主路线）** | 0.90 | **0.92** | **0.91**（RRF） |
| pgvector/ParadeDB 真 BM25（ngram） | 0.90 | 0.90 | 0.91 |

- 判据：Milvus 混合 `Recall@5` 0.91 ≥ pgvector 0.90 → **Pass**；jieba 中文抽检 32/32
- 压力档（10 万块）：Milvus 查询 P95 **5.6 ms** / 1.28 GB；pgvector **170.6 ms** / 0.33 GB
- tsvector 路线对中文 `Recall@5 = 0`，已淘汰

### 5.5 Checkpoint 方案（V5）

- 初选 Redis checkpointer（候选 A）因 **B7 阻塞**（redis-py ↔ redis-stack 连接握手被服务端关闭，**根因非缺 RediSearch**）转向 **PostgreSQL checkpointer（候选 B）**
- PG 路线 T5.1–T5.7 **全 Pass**：字段齐全率 100%、写操作重复落库 **0 次**、双审核人并发仅 **1 份报告**、单 thread 体积 296 KB（有界）
- 可靠性设计：写操作移出图外 + 幂等键 + PG 唯一索引 + SETNX 锁三层兜底

---

## 六、当前进展与门禁结论

### 6.1 里程碑（M0.1–M0.6）

| 里程碑 | 内容 | 判定 |
|---|---|---|
| M0.1 | 约束与基线锁定 | ⚠️ **条件通过**（`.wslconfig` 已核验；T1.9 授权=需降级，不阻塞） |
| M0.2 | V1 完成 | ❌ **未通过（No-Go <70%）**，V1 已挂起 |
| M0.3 | V2 + V3 完成 | ⚠️ **有条件**（V2 Pass；V3 已闭环） |
| M0.4 | V5 完成 | ✅ **达成**（PG 路线全 Pass） |
| M0.5 | V4b + V6 + V7 | ⚠️ **部分达成**（V4b 中间区间；V6/V7 结构 Pass） |
| M0.6 | P0 门禁评审 | ❌ **不予放行**（仅 M0.4 达成） |

### 6.2 验证项逐项判定

| 验证项 | 判定 | 关键数字 |
|---|---|---|
| **V1** LLM 工具调用 | **No-Go** | 约束解码首次 qwen 0.35 / ds 0.45（云端上界 0.60）；重试后 0.95 / 0.90；可解析率 1.00 |
| **V2** 混合检索 | **Pass** | 混合 `Recall@5` 0.91；真 BM25 对标闭环；压力档闭环 |
| **V3** 时序接入 | **条件通过** | 授权需降级（自研解码器 ≈1.9 人日）；四类边界 4/4；`query_sensor` 聚合 P95 **≈26.2 ms**（实测，见 `reports/p0-report-v3-ingest-license.md` / `experiments/v3/raw/EXP-V3-QS.jsonl`） |
| **V4a** 约束采集 | **Pass** | env 三件套 |
| **V4b** 资源实测 | **中间区间** | 宿主峰值 **26.38 GB > 24 GB**（超 9.9% ≤10%）→ 分组启动；容器合计仅 1.38 GB |
| **V5** checkpoint | **Pass** | PG 路线；M0.4 达成 |
| **V6 / V7** 数据 / 评测集 | **结构 Pass** | 模拟数据兜底；单人标注（Kappa 未做） |

---

## 七、已知问题与限制

### 7.1 缺陷清单（ISS-001 – ISS-013）

| 编号 | 组件 | 现象 | 状态 |
|---|---|---|---|
| ISS-001 | LangGraph `has_writes` | 状态判断不可信 | ✅ 可规避（PG 未复现） |
| ISS-002 | 恢复后重复副作用 | 重复报告/落库 | ✅ 可规避（写操作图外 + 幂等键，实测 0 次重复） |
| ISS-003 | Redis TTL/驱逐 | 状态永久丢失 | ✅ 可规避（PG 路线 N/A） |
| ISS-004 | 审核并发 | 双审核人产两份报告 | ✅ 可规避（PG 唯一索引兜底，实测 1 份） |
| ISS-005 | Redis checkpointer | 第三方实现，B7 握手失败 | ✅ **需换方案**（已切 PG checkpointer） |
| ISS-006 | checkpoint 体积 | 无上限增长 | ✅ 可规避（296 KB/thread，有界，建议 N=20 归档） |
| ISS-007 | WSL2 配额 | V4b 结论无效 | ✅ 已修复闭环（2026-09-24） |
| ISS-008 | GPU 直通 | `nvidia-smi` 不可用 | ✅ 已裁决改走宿主 Ollama |
| ISS-009 | Ollama 版本漂移 | 0.34.2 vs 0.34.3 | ✅ 已决锁定 0.34.2 |
| ISS-010 | TDengine 授权 | OSS 无连接器 | ✅ 已定稿（OSS + 自研解码器） |
| ISS-011 | `think` 污染 | 误判为能力不足 | 🔲 待回填（适配层已统一剥离） |
| ISS-012 | 量化档公平性 | Q4 vs Q8 不可比 | 🔲 待 D2–D3 回填 |
| ISS-013 | Ollama 静默退化 | 返回 200 但无 `tool_calls` | 🔲 待回填（`llm_adapter` 已置位 `tool_calls_missing`，判分器记 `格式退化`） |

### 7.2 主要限制与未闭环项

1. **V1（M0.2）已挂起**：三路实测均 No-Go，7B 模型参数精确抽取为结构性硬上限；处置路径收窄（**参数归一化纠错已实测 uplift=0 否决**，见 `experiments/v1/EXP-V1-NORM.md`）：待定（用例/Schema 复审 / 承认 7B 上界）。
2. **V4b 未到 Pass**：需落地"分组启动 + 按需加载"，稳态峰值实测留待 P1。
3. **V3 第二段接入**：授权已定稿，但 M0.3 通过条件（时序决策 + Schema 映射 + `query_sensor` 契约 + 告警路线）尚有缺口；告警路线未实测确认。
4. **数据合规**：版权/隐私书面结论"待外部"，全部质量结论**基于模拟数据**，仅证明"链路可运行、方案可比较"，不等于现场可用性。
5. **版本锁定未齐**：仍有 reranker 模型、EMQX、应用前后端依赖等未锁定。（**裸 tag 已于 2026-09-29 清零**：base / ingest / v2 三个 compose 全部锚定 digest，见 `docs/prj-ledger-version-lock.md` 修订记录。）
6. **标注可信度**：V7 为单人标注，Cohen's Kappa 一致性检验待 P5。
7. **上游矛盾待裁决**：V1 处置步骤数 2 vs 4、M0.1 条件项 3 vs 6、`R-新2/R-新3` 编号冲突、`hardware.json` 主机名/时间不一致等。

---

## 八、后续改进建议

### 8.1 Phase 1 首日待办（按优先级）

| 优先级 | 动作 | 判据 |
|---|---|---|
| **P0-1** | **MinerU 解析 Spike**（R14，P1 最大不确定项）：解析文本型/扫描件/含表格 3 类 PDF | 文本型完整率 ≥95%；三样本均产出结构化 markdown；不通过改用 PyMuPDF + PaddleOCR（+1~2 天） |
| **P0-2** | A1 接入骨架：打通 Mosquitto + TDengine + 自研解码器 | `compose.ingest.yml` 可启动，MQTT 连接打通 |
| **P0-3** | 环境复用：启动 Milvus/Neo4j/PG/Redis | 健康检查通过，版本/digest 与 prj-ledger-version-lock 一致 |
| **P1-1** | PG 迁移：建 `documents/doc_chunks/work_orders/outbox/alerts` 表 | `db/migrations/0001_init.sql` 执行成功 |
| **P1-2** | P0 遗留项认领收口（L-01 – L-10） | 每条更新为「已闭环 / 已转 P1 任务」 |
| **P2-1** | 版权/隐私书面结论推进（R15） | 未闭环则维持模拟数据兜底 |

### 8.2 建议的改进方向

1. **V1 破局（最关键）**：「参数归一化纠错」已量化实测 **uplift=0**（EXP-V1-NORM，2026-09-28）——多数参数值错为**语义选择**（window/aggregation/relation_type…）+ **多工具缺失**，规则化无效，**该路径关闭**；改走「用例与 Tool Schema v2 简化 + 多工具编排评估」优先，其次评估「用例降档」，最后才考虑承认 7B 上界并把工具调用转云端 —— 注意转云端会引入数据出域合规问题，须与 `p1-spec-data-sources.md` 联动。
2. **V4b 落地**：把"分组启动 + 按需加载"清单转为常驻脚本与准入检查（启动前强制 `docker info` 内存断言），并补测分组稳态峰值。
3. **V3 收口**：补实测告警路线（阈值 + 滑动窗口 Z-Score）+ `query_sensor` 契约与 `tools_v1.json` 字段一致性核对。
4. **版本与文档一致性**：补齐待锁定 digest（reranker / EMQX / 前后端锁文件）；~~整改 compose 裸 tag~~（2026-09-29 已清零）；~~统一工具命名~~（已统一为 `search_knowledge`）；`hardware.json` 元数据与 5 条上游矛盾待处理。完整审计结果见 `reports/p0-summary-project-2026-09-29.md` 附录 A。
5. **数据合规前置**：把版权/隐私书面结论作为 P1 首日遗留问题推进，避免 P1 建库返工。
6. **评测集增强**：引入第二标注人做 Cohen's Kappa；补充 V2 分类别（7 类）质量指标；补充检索重测流程（真实语料到位后同集同流程重测）。
7. **工程化沉淀**：把 `--selftest` 纳入 CI；补 `requirements.txt` / `package.json` 锁文件；将 `experiments/**/raw/` 的登记与 `prj-template-experiment-log.md` 打通为自动化台账。

---

## 九、一页速览

| 维度 | 结论 |
|---|---|
| 项目目标 | 云侧工业 IoT 诊断 Agent，主场景离心泵轴承振动异常 |
| 技术栈 | Milvus + TDengine + Neo4j + PostgreSQL + Redis/Mosquitto + Ollama（qwen2.5:7b / deepseek-r1:7b / BGE-M3） |
| 核心链路 | Sparkplug B → MQTT → 自研解码器 → TDengine；LangGraph 工作流 + 5 工具契约 + 强制证据引用 + 高风险人工审核 |
| 当前阶段 | Phase 0 完成，M0.6 **未放行** |
| 唯一达成里程碑 | **M0.4（V5 checkpoint）** |
| 最大风险 | **V1 工具调用 No-Go（7B 上界）** + V4b 内存超限 9.9% |
| 下一步 | 按 `p0-handover-p1.md` 启动 Phase 1，首日做 MinerU Spike |

---

> **数据来源**：`plan/`、`docs/`（15 份）、`reports/`（v1–v5 + p0-gate-review）、`schemas/`、`env/`、`docker/`、`scripts/`、`experiments/`。
> **引用纪律**：本文为导读性汇总，任何结论以其原始文档为准；引用环境/版本须以 `env/env-baseline-v2.md` 与 `docs/prj-ledger-version-lock.md` 为准。

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | 文档同步整理：加「历史留痕」横幅（正文结论一字未改）；文件重命名 → `p0-summary-project-2026-09-28.md` | 头部 / 索引 |
