# 云侧工业 IoT 诊断 Agent 系统 — 项目全面总结
> **⚠️ 历史留痕（2026-10-08 文档同步加注，正文结论未改）**：本文所载判定为 **2026-09-29** 时点。文件名已按规范改为 `p0-summary-project-2026-09-29.md`（原 `reports/project-summary-2026-09-29.md`）。 曾标为「最新全景」；V1 判定、V4b 口径与缺陷编号范围均已过时，**全景之「当前状态」以 10-08 过闸报告为准**。附录 A 文档不一致清单（C-01~C-25）仍具审计价值。 当前口径见 `README.md` §当前状态速览 与 `docs/p0-spec-gate-criteria.md` §六；裁决依据 `reports/p0-gate-m02-verdict-2026-10-08.md`。

> **项目根**：`<REPO>`
> **主场景**：离心泵驱动端轴承振动异常诊断
> **当前阶段**：Phase 0（技术验证与范围锁定，D0 + D1–D10）已收口，Phase 1 待启动
> **文档基准日期**：2026-09-29
> **文档性质**：面向团队的全景总结。所有数字均引自仓库内既有实测产物，本次核对新增"文档不一致清单"（见附录 A）。
> **引用纪律**：环境与版本以 `env/env-baseline-v2.md` + `docs/prj-ledger-version-lock.md` 为唯一事实源；判据以 `docs/p0-spec-gate-criteria.md` 为准。

---

## 一、项目概述

### 1.1 一句话定位

一个**云侧、本地优先**的工业设备智能诊断 Agent：把「时序遥测 + 设备知识 + 图谱关系 + 维修历史」四类证据汇聚给 LLM，自动完成**告警 → 诊断推理 → 证据引用 → 报告生成 → 高风险人工审核**的闭环。

### 1.2 核心设计取向

| 取向 | 具体表现 |
|---|---|
| 证据驱动 | 每条结论必须带 `EvidenceItem`（chunk_id / doc_id / source / page），**无来源不出结论** |
| 本地优先 | LLM 推理走宿主 Ollama（`127.0.0.1:11434`），容器只承载 DB / 存储 |
| 判据前置 | 任一验证项开跑前，Pass / 中间区间 / No-Go 必须先定稿（三条铁律之一） |
| 降级必带代价 | 任何替代方案都要标注对 `Recall@5` 与 `P95` 的影响 |
| 不编造数字 | 未实测项一律写 `【待实测填入】`，禁止"预计 / 大约"伪装 |
| 可复现 | 组件 / 模型一律以 digest 锁定；模拟数据固定 seed + `synthetic: true` 标记 |

### 1.3 阶段定位

Phase 0 只做「技术验证 + 范围锁定」，产出物直接作为 Phase 1（数据接入与知识库构建）的输入基线。**当前 M0.6 门禁未放行**，Phase 1 属"计划就绪、待放行启动"状态。

---

## 二、主要功能点

### 2.1 Must 链（13 项，端到端必须闭环）

| # | 能力 | 可验收判据 | 依赖验证项 |
|---|---|---|---|
| 1 | **告警产生** | 模拟 Sparkplug B 数据触发阈值告警，产出标准 `AlarmEvent` | V3 |
| 2 | **告警去重** | 5 min 内同类告警合并（`dedup:alarm:{device_id}:{metric}`） | V3 |
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

> 当前状态：1–12 项**代码 / 契约 / 方案就绪**，实测覆盖不均；第 13 项（前端）属 P4，尚未启动。

### 2.2 明确不做（Won't）

W1 多租户；W2 模型微调（预留 LoRA 接口）；W3 复杂 GraphRAG 多跳（>2 跳）；W4 移动端；W5 真实 Modbus / OPC UA 直连（预留边缘网关转 MQTT 接口）；**W6 自动执行维修动作（永久安全刚性）**。

### 2.3 Should / Could（不计入 Must）

- **Should**：对话式追问、图谱可视化、Prometheus 指标面板。
- **Could**：多设备扩展、GraphRAG 多跳、模型微调。

### 2.4 停止条件与质量目标（`docs/p0-spec-scope-mvp.md`）

- **停止条件 S2**：≥3 项量化指标达标 —— `Recall@5 ≥ 85%`、`P95 检索 < 800 ms`、工具调用首次成功率 ≥ 90%。
- **质量目标 Q1–Q11**：`MRR ≥ 0.75`、引用正确率 ≥ 90%、幻觉率 ≤ 10%、`P95 端到端 < 3 s`、审核覆盖率 100%、置信度 `ECE ≤ 0.10` 等。

---

## 三、技术栈

### 3.1 硬件与运行环境

| 项 | 实测值 |
|---|---|
| OS / 主机 | Windows 10 Pro 25H2（build 26200）/ `<WORKSTATION>`（**实测**：`hostname` / `COMPUTERNAME` / `Win32_ComputerSystem.Name` / DNS 四路一致；原写的 `<HOST_ALIAS>` 不存在） |
| CPU | i7-13650HX，20 逻辑核（6P + 8E） |
| 内存 / GPU | 32 GB / RTX 4060 Laptop 8 GB（8188 MiB，驱动 616.56，CC 8.9） |
| WSL2 配额 | memory=20 GB / processors=10 / swap=8 GB（`.wslconfig` 已核验生效） |
| Docker | 引擎 29.6.2 / Compose v5.3.1 |
| 门禁线 | 峰值 ≤ 24 GB（= 32 GB × 75%，**口径 B：宿主总占用**） |

### 3.2 组件（8 个 Docker 镜像，2026-09-29 已全部锚定 digest）

| 组件 | Tag | 用途 |
|---|---|---|
| `milvusdb/milvus` | `v3.0.0` | **V2 主路线**（向量 + 稀疏 BM25） |
| `quay.io/coreos/etcd` | `v3.5.25` | Milvus 依赖（不对外暴露端口） |
| `minio/minio` | `RELEASE.2024-12-18T13-15-44Z` | Milvus 依赖 |
| `postgres` | `18` | 业务库基线 + **V5 checkpointer** |
| `paradedb/paradedb` | digest 锁定 | V2 对照路线（pgvector + pg_search 真 BM25），宿主端口 5433，库 `auscult_v2` |
| `redis` | `8` | V5 checkpoint 候选 A（**最终未采用**，仅留作审核锁 / 审计辅助） |
| `tdengine/tsdb` | `3.3.8.0` | V3 时序库（OSS，自研解码器路线） |
| `eclipse-mosquitto` | `2` | V3 MQTT Broker（Sparkplug B 传输层） |
| `neo4j` | `5-community` | 图谱库 |

### 3.3 模型（Ollama 加载，锁 manifest digest）

| 模型 | 大小 | 角色 | 备注 |
|---|---|---|---|
| `qwen2.5:7b` | 4.68 GB | 候选 A（通用指令模型） | 无 `think` 输出；显存 5773 MiB |
| `deepseek-r1:7b` | 4.68 GB | 候选 B（推理模型） | **含 `think`，须剥离**；显存 5779 MiB |
| `BGE-M3` | 1.2 GB | V2 向量化（dim=1024，F16） | 经 `/v1/embeddings`，显存 6512 MiB |
| `Qwen/Qwen3.8-27B`（云端） | — | V1 上界校准（非默认部署） | ModelScope OpenAI 兼容端点 |

### 3.4 工具链与依赖

- **运行时**：Python 3.12.8 / Node.js v24.19.0 / Git 2.45.1 / Ollama **0.34.2（锁定不升级）**
- **Python 关键库**：`pymilvus` 3.0.2、`psycopg` 3.3.6、`jieba` 0.42.1、`paho-mqtt` 2.1.0、`taospy` / `taosrest` 2.8.10、`protobuf` 7.36.2、`grpcio` 1.84.0、`langgraph` 1.2.12、`langgraph-checkpoint-postgres` 3.1.2、`langgraph-checkpoint-redis` 0.5.2（未采用）
- **实验固定参数**：`temperature=0`、`seed=42`、`num_ctx=8192`、`top_p=1.0`、`max_tokens=1024`、`stream=false`

---

## 四、模块划分与目录结构

```
auscult/
├─ plan/          阶段开发计划（Phase 0 D1-D10 可执行版 / 任务总结 / Phase 1 计划）
├─ docs/          15 份治理与规范文档（范围/判据/风险/版本/缺陷/移交/角色/审核/标注…）
├─ reports/       验证报告 v1–v5 + p0-gate-review + README + p0-summary-project-2026-09-28 + project-summary + daily/
├─ schemas/       tools_v1.json（5 工具 Schema，FROZEN）
├─ protos/        sparkplug_b.proto + 生成的 PB 类（sparkplug_b_pb2.py）
├─ configs/       decoder_schema_mapping.json / mosquitto.conf / redis.conf / milvus/
├─ docker/        compose.base.yml / compose.ingest.yml / compose.v2.yml / compose.v4b-iso.yml / Dockerfile.decoder
├─ scripts/       16 个 Python 执行器 + 2 个 PowerShell（均带 --selftest）
├─ evals/         golden_set_v1.jsonl(50) / v1_cases.jsonl(20) / corpora_v1/corpus_100.jsonl(100)
├─ experiments/   v1 / v2 / v3 / v4b / v5 原始实测数据（raw/，只增不改）
├─ env/           env-baseline-v2.md / hardware.json / ports.md
├─ prompts/       tool_call_prompt_v1.md / tool_call_prompt_v2.md
└─ .trae/         V2 真 BM25 对标 / 压力档补充实施稿
```

### 4.1 脚本按验证项分组

| 验证项 | 脚本 | 职责 |
|---|---|---|
| **V1** 工具调用 | `llm_adapter.py` | 统一适配层（Schema 注入 / `think` 剥离 / 静默退化识别） |
| | `judge_tools.py` | 判分器（draft-07 校验 / `time_range` ±10% 等价 / 8 指标汇总） |
| | `run_v1.py` | 批量执行器（多轮历史 / 回灌重试 / 断点续跑 / `--constrain`） |
| | `gbnf_grammar.py` | 约束解码约束生成（**实际载体 = JSON Schema**，供 Ollama `/api/chat` 的 `format` 字段；文件名沿用历史 GBNF 口径） |
| | `param_normalizer.py` | 参数归一化纠错（白名单 R1/R2/R3，**已实测否决**） |
| | `run_cloud_baseline.py` | 云端上界校准（不作为判据） |
| **V2** 混合检索 | `run_v2.py` | Milvus / pgvector × dense/sparse/hybrid 质量对比 + jieba 抽检 |
| | `v2_pg_build.py` | PG 侧建库灌数（含 ParadeDB ngram BM25 索引） |
| | `v2_synth_corpus.py` / `v2_load_test.py` | 压力档语料合成与延迟 / 内存实测 |
| **V3** 时序接入 | `spb_simulator.py` | 自建 Sparkplug B 模拟器（`--scenario` 驱动四类边界） |
| | `self_decoder.py` | 自研解码器（M1–M6，MQTT → Protobuf → TDengine REST） |
| | `v3_ingest_direct.py` / `run_v3_alert.py` / `verify_query_sensor.py` | 直写数据集 / 告警状态机 / 聚合契约验证 |
| **V4a** 环境 | `collect_env.ps1` / `check_ports.ps1` | 硬件采集 / 12 端口可用性检查 |
| **V5** checkpoint | `run_v5.py` | T5.1–T5.7 七步骤（恢复 / 幂等 / 并发 / 体积 / TTL） |

---

## 五、关键实现逻辑

### 5.1 端到端数据流

```
IoT 侧： spb_simulator ──MQTT──> Mosquitto ──> self_decoder ──REST 6041──> TDengine
                                                                  └─> st_pump_metrics / st_unmapped_metrics / st_device_status
知识侧： PDF/工单 ──MinerU 解析──> Parent-Child 分块 ──> 三存储写入
                                                        ├─ Milvus（稠密 BGE-M3 + 稀疏 BM25/jieba）
                                                        ├─ Neo4j（三元组，准确率 ≥85%）
                                                        └─ PostgreSQL（元数据 + 版本 + 业务表）
Agent 侧：LangGraph 工作流 parse → readonly(4 个只读工具) → diagnose
          → [interrupt 人工审核] → generate_report（★ 图外执行）
```

### 5.2 工具契约（`schemas/tools_v1.json`，v1 已 FROZEN）

- `status=FROZEN`、`frozen_at=2026-09-23`；`change_policy`：**一经冻结，任何修改必须升版 `tools_v2.json`**，否则 V1 全部结论作废。
- `tool_summary`：`total=5, read_only=4, write=1, in_graph=4, out_of_graph=1`。

| 工具 | 类型 | 图内 | 必填参数 | 关键约束 |
|---|---|---|---|---|
| `query_sensor` | read_only | 是 | `device_id`, `time_range` | `aggregation` ∈ {avg,max,min,trend,count_over_limit,raw}；`window` ∈ {1m,5m,15m,1h,1d}；`limit` 1–5000 |
| `search_knowledge` | read_only | 是 | `query` | `top_k` 1–20；`category_filter` 7 类枚举 |
| `query_graph` | read_only | 是 | `start_node` | `relation_types` 6 种；`direction` 3 值；`depth` 1–3 |
| `get_maintenance_history` | read_only | 是 | `device_id` | `fault_keywords` ≤5；`limit` 1–100 |
| `generate_report` | **WRITE_OPERATION** | **否** | `device_id`,`diagnosis_summary`,`evidence_refs`,`idempotency_key` | `evidence_refs` ≥1 且元素含 `{type,ref}`；`idempotency_key` 正则 8–64 位；`requires_review=true` |

> 架构要点：**唯一写操作 `generate_report` 移出图外**，必带 `idempotency_key` 防恢复后重复；只读工具保持图内。

### 5.3 自研 Sparkplug B 解码器（V3 关键降级项）

因 TDengine 官方 Sparkplug B 连接器仅随 All-in-One / Enterprise，OSS 无 taosX，故**自研消费者**（估算 ≈1.9 人日，在 ≤2 天红线内）。代码结构（`scripts/self_decoder.py`）：

| 模块 | 实现 | 位置 |
|---|---|---|
| **M1** proto 工程 | `decode_payload()` / `metric_value()`，生成 PB 类往返 | L124 / L130 / L555 |
| **M2** 订阅分流 | `TopicParser.parse()` 正则 `spBv1.0/{group}/{type}/{edge}/{device}`；订阅 `spBv1.0/plant1/+/gw-pump-01/#` | L110 / L333 |
| **M3** DBIRTH 建表 | `_handle_dbirth()` + `init_schema()` 幂等建库建表 | L362 / L526 |
| **M4** DDATA 写入 | `_handle_ddata()`；未登记 metric 旁路至 `st_unmapped_metrics` + `schema_drift` | L408 / L423 |
| **M5** 离线翻转 | `_handle_ddeath()` / `_handle_ndeath()` | L471 / L485 |
| **M6** re-birth 冲突 | `DeviceRegistry` + bdSeq 比对（birth / duplicate / rebirth / rebirth_rollback） | L295 / L371 |

- 映射配置：`configs/decoder_schema_mapping.json`（`schema_version=v2`）定义 3 张超级表 `st_pump_metrics`（8 列 4 tag）/ `st_unmapped_metrics` / `st_device_status`，子表命名 `d_{group_id}_{device_id}`，并内联 `boundary_handling`（birth / new_metric / rebirth_conflict / offline / lt_rule）。
- **四类边界 4/4 实测通过**：建表、新增 metric 旁路、re-birth（bdSeq 比对）、离线状态翻转。
- 局部写入原则：单个坏 metric 不丢整条报文。
- 遗留：REST 逐条写入 **~80 ms/条**吞吐瓶颈，P1 优化。

### 5.4 检索路线（V2）

| 路线 | 稠密 | 稀疏 | 混合 |
|---|---|---|---|
| **Milvus（主路线）** | 0.90 | **0.92**（原生 BM25 + jieba） | **0.91**（RRF k=60） |
| pgvector + ParadeDB 真 BM25（ngram） | 0.90 | 0.90 | 0.91 |
| pgvector + tsvector（中文） | 0.90 | **0.00** | 0.90 |

- 判据：Milvus 混合 `Recall@5` 0.91 ≥ 对照 0.90 → **Pass**；jieba 中文抽检 **32/32**。
- 压力档（10 万块）：Milvus 查询 P95 **5.6 ms** / 内存 **1.28 GB**；pgvector P95 **170.6 ms** / **0.33 GB**（3 万块：4.6 ms vs 100.4 ms）。
- tsvector 路线对中文 `Recall@5 = 0`，已淘汰。

### 5.5 Checkpoint 方案（V5）

- 初选 Redis checkpointer（候选 A）因 **B7 阻塞**（redis-py ↔ redis-stack 连接握手被服务端关闭，**根因非缺 RediSearch**）转向 **PostgreSQL checkpointer（候选 B，`langgraph-checkpoint-postgres==3.1.2`）**。
- PG 路线 T5.1–T5.7 **全 Pass**：字段齐全率 100%、写操作重复落库 **0 次**、双审核人并发仅 **1 份报告**、单 thread 体积 **296 KB**（有界）、总 DB ≈8.66 MB。
- 可靠性三层兜底：**写操作移出图外 + 幂等键 + PG 唯一索引 + SETNX 锁**。
- 审核触发规则 T-1–T-6（确定性，与 V1 解耦）：关键词命中 / `risk_level ∈ {high,critical}` / 低置信度 `<0.60` 强制审核（`0.75` 为自动生成线）/ 证据不足 / 拒自审 / 写操作前置；状态机 6 态；超时 T+4h 通知、T+24h 降级。

---

## 六、当前进展与门禁结论

### 6.1 里程碑（M0.1–M0.6）

| 里程碑 | 内容 | 判定 |
|---|---|---|
| M0.1 | 约束与基线锁定 | ⚠️ **条件通过**（`.wslconfig` 已核验；T1.9 授权=需降级，不阻塞） |
| M0.2 | V1 完成 | ❌ **No-Go（<70%）**，V1 已挂起 |
| M0.3 | V2 + V3 完成 | ⚠️ **条件通过 / 已达成**（V2 Pass；V3 已闭环） |
| M0.4 | V5 完成 | ✅ **达成**（PG 路线全 Pass） |
| M0.5 | V4b + V6 + V7 | ✅ **达成**（V4b 干净机重测 **Pass 17.89GB** ≤24GB；V6/V7 结构 Pass） |
| M0.6 | P0 门禁评审 | ❌ **不予放行**（原因收窄为仅剩 M0.2 / V1 工具调用 No-Go） |

### 6.2 验证项逐项判定

| 验证项 | 判定 | 关键数字（实测） |
|---|---|---|
| **V1** LLM 工具调用 | **No-Go** | 约束解码（EXP-V1-003）首次 **qwen 0.35 / ds 0.45**，重试后 0.95 / 0.90，可解析率 1.00；few-shot 8 + 拒止（EXP-V1-004）首次 0.50 / 0.35，重试后 1.00 / 0.85；云端无约束（EXP-V1-002）0.60，云端约束解码（EXP-V1-005）**0.55**、可解析率 0.88 |
| **V2** 混合检索 | **Pass** | 混合 `Recall@5` 0.91；真 BM25 对标闭环；压力档闭环 |
| **V3** 时序接入 | **条件通过 → 闭环** | 授权需降级（自研解码器 ≈1.9 人日）；四类边界 4/4；`query_sensor` 聚合 P95 **26.23 ms**（avg，n=30）/ **27.69 ms**（count_over_limit）；告警路线 Must#1/#2 均 PASS（PUMP-A 1 条告警，max_window_avg 5.57） |
| **V4a** 约束采集 | **Pass** | env 三件套（env-baseline-v2 / hardware.json / ports.md） |
| **V4b** 资源实测 | **中间区间** | 宿主峰值 **26.38 / 31.80 GB > 24 GB**（超 9.9%，在 26.4 GB 容限内）→ 分组启动；容器合计仅 ≈1.38 GB；Neo4j 871 MiB 为最大户；双 7B ≈11.6 GB > 8.2 GB 不可共存 |
| **V5** checkpoint | **Pass** | PG 路线；M0.4 达成（详见 5.5） |
| **V6 / V7** 数据 / 评测集 | **结构 Pass** | 模拟数据兜底；单人标注（Kappa 未做） |

### 6.3 V1 的关键结论（最大风险项）

- 瓶颈定位：**参数值正确率** qwen 0.3529 / ds 0.3333 / 云端 0.5882；失败归类以"参数值错"为主（39 / 30 次），其次"工具名错"。
- **多工具为结构性硬限**：本地双模型多工具集合覆盖 0.00，云端约束解码仅 50%。
- **参数归一化纠错路径已关闭**：`EXP-V1-NORM` 对 217 条记录逐条 diff，**变化 0 条、uplift = 0**——多数参数错是"语义选择"（window / aggregation / relation_type）而非格式问题，规则化无效。
- 处置方向（`docs/p0-decision-model-role.md` §4.6）：**R-2 工具调用规划 / R-3 参数抽取上云 + 多工具架构切分（拆单工具多轮）**；R-1 / R-4 / R-5 / 检索 / 写操作 / 审计 / 有效拒绝 / 降级兜底保持本地。

---

## 七、已知问题与限制

### 7.1 缺陷清单（`docs/prj-ledger-known-issues.md`，ISS-001 – ISS-014）

| 编号 | 组件 | 现象 | 状态 |
|---|---|---|---|
| ISS-001 | LangGraph `has_writes` | 状态判断不可信 | ✅ 可规避（PG 未复现） |
| ISS-002 | 恢复后重复副作用 | 重复报告 / 落库 | ✅ 可规避（写操作图外 + 幂等键，实测 0 次） |
| ISS-003 | Redis TTL / 驱逐 | 状态永久丢失 | ✅ 可规避（PG 路线 N/A） |
| ISS-004 | 审核并发 | 双审核人产两份报告 | ✅ 可规避（PG 唯一索引兜底，实测 1 份） |
| ISS-005 | Redis checkpointer | 第三方实现，B7 握手失败 | ✅ **需换方案**（已切 PG checkpointer） |
| ISS-006 | checkpoint 体积 | 无上限增长 | ✅ 可规避（296 KB/thread，建议 N=20 归档） |
| ISS-007 | WSL2 配额 | V4b 结论无效 | ✅ 已修复闭环（2026-09-24） |
| ISS-008 | GPU 直通 | `nvidia-smi` 不可用 | ✅ 已裁决改走宿主 Ollama |
| ISS-009 | Ollama 版本漂移 | 0.34.2 vs 0.34.3 | ✅ 已决锁定 0.34.2 |
| ISS-010 | TDengine 授权 | OSS 无连接器 | ✅ 已定稿（OSS + 自研解码器） |
| ISS-011 | `think` 污染 | 误判为能力不足 | 🔲 待回填（适配层已统一剥离） |
| ISS-012 | 量化档公平性 | Q4 vs Q8 不可比 | 🔲 待回填 |
| ISS-013 | Ollama 静默退化 | 返回 200 但无 `tool_calls` | 🔲 待回填（`llm_adapter` 已置位 `tool_calls_missing`，判分器记 `格式退化`） |
| ISS-014 | R-4 本地证据归纳 / 诊断可用性 | ✅ **已闭环 Pass（EXP-R4-001，2026-09-29）** | 六维全 Pass：结构 0.96 / 引用忠实 1.0 / 幻觉红线 0 / 覆盖 0.96 / 根因 0.93 / severity 0.89 / 动作非空 0.96 |
| ISS-015 | Redis 配置 / 容器网络 | `bind 127.0.0.1` 在 Docker 形态下不可用 | ✅ 可规避（已文档化 + 给出容器形态替代配置；P1 改 `requirepass`） |
| ISS-016 | V1 判分器 | 指标名 `1b_多工具集合覆盖` 与"多重集精确相等"语义不符 | ✅ 可规避（已在 docstring 写明；下一版判分器统一命名） |
| ISS-017 | 自研解码器 | 心跳超时兜底未实现（只处理显式 DDEATH/NDEATH） | ✅ 可规避（依赖 MQTT Will；P1 补计时器） |
| ISS-018 | 环境采集 | `env/hardware.json` 停留在 v1 口径（GPU=null / 配额 15.51 GB / 主机名与时间不符） | ✅ 可规避（以 `env-baseline-v2.md` 为准；采集脚本已修，待重采） |

### 7.2 主要限制与未闭环项

1. **V1（M0.2）已挂起**：三路实测均 No-Go，7B 模型参数精确抽取为结构性硬上限；参数归一化路径已实测否决，处置待定（用例 / Schema 复审 或 承认 7B 上界）。
2. **V4b 未到 Pass**：需落地"分组启动 + 按需加载"，稳态峰值实测留待 P1。
3. **V3 第二段接入**：授权已定稿，但 M0.3 通过条件（时序决策 + Schema 映射 + `query_sensor` 契约 + 告警路线）尚有缺口；解码器 REST 写入吞吐 ~80 ms/条。
4. **数据合规**：版权 / 隐私书面结论"待外部"，全部质量结论**基于模拟数据**，仅证明"链路可运行、方案可比较"，**不等于现场可用性**。
5. **版本锁定未齐**：reranker 模型、EMQX、应用前后端锁文件等仍未锁定（"15 项待锁定"为**初始口径**，`docs/prj-ledger-version-lock.md` §三 多行已标 ✅，实际已收敛）。Python 依赖锁已补：新建 `requirements.txt`（版本取自 `prj-ledger-version-lock.md` §二.2.7/2.8/2.9）。
6. **标注可信度**：V7 为单人标注，Cohen's Kappa 一致性检验待 P5（计划抽 ≥15 条，目标 ≥0.70）。
7. **过程留痕缺口**：`reports/daily/` 仅有 `D1-status.md`，D2–D10 日报缺失（规范要求"一天一份、不合并"），削弱了里程碑判定的原始素材可追溯性。
8. **上游矛盾待裁决**：见附录 A。

---

## 八、后续改进建议

### 8.1 Phase 1 首日待办（按优先级）

| 优先级 | 动作 | 判据 |
|---|---|---|
| **P0-1** | **MinerU 解析 Spike**（R14，P1 最大不确定项）：解析文本型 / 扫描件 / 含表格 3 类 PDF | 文本型完整率 ≥95%；三样本均产出结构化 markdown；不通过改用 PyMuPDF + PaddleOCR（+1~2 天） |
| **P0-2** | A1 接入骨架：打通 Mosquitto + TDengine + 自研解码器 | `compose.ingest.yml` 可启动，MQTT 连接打通 |
| **P0-3** | 环境复用：启动 Milvus / Neo4j / PG / Redis | 健康检查通过，版本 / digest 与 `prj-ledger-version-lock` 一致 |
| **P1-1** | PG 迁移：建 `documents` / `doc_chunks` / `work_orders` / `outbox` / `alerts` 表 | `db/migrations/0001_init.sql` 执行成功 |
| **P1-2** | P0 遗留项认领收口（L-01 – L-10） | 每条更新为「已闭环 / 已转 P1 任务」 |
| **P2-1** | 版权 / 隐私书面结论推进（R15） | 未闭环则维持模拟数据兜底 |

### 8.2 建议的改进方向

1. **V1 破局（最关键）**：规则化纠错路径已关闭 → 改走「用例与 Tool Schema v2 简化 + 多工具编排评估」优先；其次评估「用例降档」；最后才考虑承认 7B 上界并把工具调用转云端。**注意转云端会引入数据出域合规问题，须与 `p1-spec-data-sources.md` 联动**。同时补齐"云端约束解码反而降分（0.60 → 0.55，可解析率降至 0.88）"的归因。
2. **V4b 落地**：把"分组启动 + 按需加载"清单转为常驻脚本与准入检查（启动前强制 `docker info` 内存断言），并补测分组稳态峰值。
3. **V3 收口**：补实测告警路线（阈值 + 滑动窗口 Z-Score）+ `query_sensor` 契约与 `tools_v1.json` 字段一致性核对；优化解码器写入吞吐（批量 / 复用连接）。
4. **版本与文档一致性**：补齐待锁定 digest（reranker / EMQX / 前后端锁文件）；工具命名与文档口径已统一（2026-09-29 审计完成，见附录 A）；**遗留仅剩 D-1 ~ D-6**（附录 A.5）。
5. **数据合规前置**：把版权 / 隐私书面结论作为 P1 首日遗留问题推进，避免 P1 建库返工。
6. **评测集增强**：引入第二标注人做 Cohen's Kappa；补充 V2 分类别（7 类）质量指标；真实语料到位后**同集同流程**重测检索。
7. **工程化沉淀**：把 `--selftest` 纳入 CI；补 `requirements.txt` / `package.json` 锁文件；把 `experiments/**/raw/` 登记与 `prj-template-experiment-log.md` 打通为自动化台账；恢复 D2–D10 日报与里程碑证据链。

---

## 九、一页速览

| 维度 | 结论 |
|---|---|
| 项目目标 | 云侧工业 IoT 诊断 Agent，主场景离心泵轴承振动异常 |
| 技术栈 | Milvus + TDengine + Neo4j + PostgreSQL（含 checkpointer）+ Redis / Mosquitto + Ollama（qwen2.5:7b / deepseek-r1:7b / BGE-M3） |
| 核心链路 | Sparkplug B → MQTT → 自研解码器 → TDengine；LangGraph 工作流 + 5 工具契约 + 强制证据引用 + 高风险人工审核 |
| 当前阶段 | Phase 0 完成，M0.6 **未放行** |
| 唯一全达成里程碑 | **M0.4（V5 checkpoint，PG 路线）** |
| 最大风险 | **V1 工具调用 No-Go（7B 结构性上界）** + V4b 内存超限 9.9% |
| 交付成熟度 | 契约 / 方案 / 脚本（`--selftest`）齐全；质量结论**基于模拟数据** |
| 下一步 | 按 `docs/p0-handover-p1.md` 启动 Phase 1，首日做 MinerU Spike |

---

## 附录 A：代码—文档一致性审计结果（2026-09-29）

> 审计范围：`scripts/`（18）、`docker/`（4 compose + 1 Dockerfile）、`configs/`（4）、`schemas/`、`protos/`、`prompts/`、`env/`，
> 以及 `docs/`（15 份）与 `reports/` 全部文档。以下为发现的**不一致 / 缺陷全清单与处理结果**。
> 处理原则：**数值与命名类不一致改文档**；**代码缺陷改代码**；**冻结 Schema 按纪律不原地修改**，登记待升 v2。

### A.1 结论性口径偏差（已修复）

| # | 位置 | 问题 | 处理 |
|---|---|---|---|
| A-1 | `reports/p0-summary-project-2026-09-28.md` §6.2 | V3 聚合 P95 写 **10.2 ms**，实测 **26.2 ms** | ✅ 已改（以 `reports/p0-report-v3-ingest-license.md` / `EXP-V3-QS.jsonl` 为准） |
| A-2 | `reports/p0-summary-project-2026-09-28.md` §7.2.5 | 仍写"尚余裸 tag `eclipse-mosquitto:2`" | ✅ 已改（2026-09-29 裸 tag 已清零） |
| A-3 | `reports/p0-summary-project-2026-09-28.md` §3.2 | ParadeDB 宿主端口写 5927，实际 **5433** | ✅ 已改 |
| A-4 | `reports/p0-report-v1-tool-call.md` / `judge_tools.py` 注释 | 云端"上界 0.60"口径混淆 | ✅ 已改（裸跑 0.60 / 约束解码 **0.55**、可解析率 0.8824；已重跑判分器核验） |
| A-5 | `docs/p0-decision-model-role.md` §三 | V1 判据仍为单线 ≥90% | ✅ 已补分档重校说明（对齐 `p0-spec-gate-criteria.md` §3.1.1） |
| A-6 | `docs/prj-spec-schema-mapping.md` | TDengine 写 `3.3.6 LTS`，实锁 **`3.3.8.0`** | ✅ 已改 |
| A-7 | `docs/p0-spec-scope-mvp.md` / `p0-handover-p1.md` / `plan/Phase 1…md` | 工具名 `retrieve_knowledge` | ✅ 已全局改为 `search_knowledge` |
| A-8 | `docs/p0-spec-gate-criteria.md` §3.4 | V4b 口径仍写"待澄清" | ✅ 已标注 2026-09-24 裁决为**口径 B**并回填实测 |

### A.2 代码缺陷（已修复）

| # | 位置 | 问题 | 处理 |
|---|---|---|---|
| A-9 | `scripts/run_v5.py` | **B2 判据失效**：`compare_payload(before, before)` 自比对，B2 恒为真 | ✅ 改为 resume 前 checkpoint 状态 vs resume 后比对 |
| A-10 | `scripts/run_v5.py` | `--checkpointer` 默认 `redis`（与已定稿 PG 路线相悖）；`POSTGRES_URL` 端口过期 5927 | ✅ 默认改 `postgres`；端口改 `5433` |
| A-11 | `scripts/run_v2.py` | `--dsn` 默认库名 `postgres`（连不到 `kb_chunks`） | ✅ 改 `auscult_v2` |
| A-12 | `scripts/run_v1.py` | 云端端点 + `--constrain` 误走 Ollama 原生 `/api/chat` | ✅ 按 endpoint 判定通道 |
| A-13 | `scripts/run_v1.py` | 重试回灌未传 `lenient_param_defaults`，与判分口径不一致 | ✅ 已补齐 |
| A-14 | `scripts/llm_adapter.py` | `data.get("done_reason") or data.get("done_reason")` 重复表达式；docstring 与实现不符（"断言"实为置位标志） | ✅ 已修正 |
| A-15 | `scripts/judge_tools.py` | `--detail-out` 空结果时 `judged[0]` 抛 IndexError；多工具判据描述为"完整覆盖"（实为多重集精确相等） | ✅ 已加空保护并更正 docstring |
| A-16 | `scripts/param_normalizer.py` | 恒假条件 `not isinstance("1h5m", str)` | ✅ 改为可证伪的复合时长断言 |
| A-17 | `scripts/self_decoder.py` | `_handle_ndeath` 直接访问私有 `registry._devices` | ✅ 已补 `DeviceRegistry.all()` |
| A-18 | `scripts/self_decoder.py` | device_id 校验未在主链路生效（R-V3-5 悬空）；无操作语句；metric 级时间戳未按配置取用 | ✅ 已实现校验（DBIRTH/DDATA/DDEATH）+ 时间戳优先序；删除空语句 |
| A-19 | `scripts/check_ports.ps1` | WSL2 探活用 `sh -c` 执行 bash 专有 `/dev/tcp` → 恒定假阴性 | ✅ 改为 `bash -c` |
| A-20 | `scripts/collect_env.ps1` | GPU 段整体失败（PSObject 属性设置异常 → `gpu=null`）；`docker`/`wsl`/`nvidia-smi` 版本恒为空串 | ✅ 已重构 GPU 采集；补齐版本分支 |
| A-21 | `scripts/run_cloud_baseline.py` | 无 `--selftest`；固定参数未显式传；打印条数不准 | ✅ 已补 `--selftest` 与显式固定参数 |
| A-22 | `scripts/run_v3_alert.py` / `verify_query_sensor.py` | 列名 / `device_id` 直接插值进 SQL | ✅ 已加标识符白名单校验 |
| A-23 | `docker/compose.ingest.yml` | 4 个死环境变量；缺 `TD_USER`/`TD_PASSWORD` | ✅ 已删死配置、补齐实际读取项 |
| A-24 | `scripts/spb_simulator.py` | DBIRTH 走 QoS0 与"QoS1 可靠发送"声明不符 | ✅ 改 QoS1 并计入 PUBACK 等待 |

### A.3 冻结约束下未原地修改

| # | 位置 | 问题 | 处理 |
|---|---|---|---|
| B-1 | `schemas/tools_v1.json` | `type` 取值风格不一（`read_only` vs `WRITE_OPERATION`）；`frozen_at=2026-09-23` 却含"按 V5 结论"（V5 于 09-24 运行）的时序倒置 | ⏸ **不原地修改**：该文件 `change_policy` 规定任何修改必须升版 `tools_v2.json`，否则 V1 全部结论作废。已登记待升 v2 统一 |
| B-2 | `schemas/tools_v1.json` vs `configs/decoder_schema_mapping.json` | `device_id` 两套正则 | ✅ 结论为**有意并存**：已补 `docs/prj-spec-schema-mapping.md` §6.1 说明与配置 `scope_note`（解码侧宽松 vs 工具契约严格） |

### A.4 文档一致性（已修复或已登记）

| # | 位置 | 问题 | 处理 |
|---|---|---|---|
| C-1 | `docs/prj-ledger-known-issues.md` 页头 | 收录范围未覆盖表内 ISS-007/008/010 | ✅ 已改为 ISS-001 – ISS-018 |
| C-2 | `docs/prj-ledger-known-issues.md` | ISS-007/008/009 状态未回填；ISS-013 规避手段描述错位 | ✅ 已回填；ISS-013 改为"适配层置位标志 + 判分器记格式退化" |
| C-3 | `docs/prj-ledger-known-issues.md` | 缺 4 条审计发现项 | ✅ **新增 ISS-015（Redis 容器网络）/ ISS-016（多工具指标命名）/ ISS-017（心跳兜底未实现）/ ISS-018（`hardware.json` 过期）** |
| C-4 | `docs/prj-spec-schema-mapping.md` | 子表示例 `d_plant1_PUMPA`（丢连字符）；`pump_speed` 行缺列类型；re-birth 回退写 `quality_ok=FALSE`（该表无此列）；NDEATH 数据来源；心跳 3s/3.5s | ✅ 全部已改（心跳项标注**未实现** → ISS-017） |
| C-5 | `docs/p0-decision-checkpoint.md` | 未覆盖 `redis.conf` 网络段，也未说明 `--checkpointer` 默认值 | ✅ 已补网络段两形态说明 + 执行器默认值口径 |
| C-6 | `docs/p0-spec-scope-mvp.md` / `prj-spec-review-lifecycle.md` | 置信度阈值 0.50 / 0.60 / 0.75 并存、语义易混 | ✅ 已在 `p0-spec-scope-mvp.md` §七 补"三档阈值语义"表 |
| C-7 | `docs/prj-ledger-version-lock.md` | 端口 5927；`hardware.json` 采集时间引用错误 | ✅ 已改 5433；时间改 20:59:50 并声明以 `env-baseline-v2.md` 为准 |
| C-8 | `reports/p0-report-v5-checkpoint.md` §2.1 | Docker 配额仍为 v1 口径（15.51 GB / vCPU 20） | ✅ 已改为 ≈20 GB / vCPU 10 |
| C-9 | `reports/p0-report-v2-hybrid-retrieval.md` | 端口 5927 / 笔误 19630 | ✅ 已改 5433 / 19530 |
| C-10 | `reports/p0-report-v3-ingest-license.md` | 命令行含不存在的 `--alert-device` | ✅ 已删并注明告警设备固定为 `--devices` 首个 |
| C-11 | `reports/README.md` | "docs/ 14 份" | ✅ 已改 **15 份**（`p0-summary-project-2026-09-28.md` 已移至 `reports/`） |
| C-12 | `reports/p0-report-v1-tool-call.md` | "强制断言 `tool_calls`"（实为置位标志） | ✅ 已改 |
| C-13 | `env/ports.md` | 9001 归属未厘清（MinIO Console vs Mosquitto WS） | ✅ 已注明 MinIO Console 仅容器内网，宿主 9001 归 Mosquitto WebSocket |
| C-14 | 工程文件缺失 | 无根 `README.md` / `requirements.txt` / `CHANGELOG.md` | ✅ **已新建三件**（依赖版本取自 `prj-ledger-version-lock.md` §二.2.7/2.8/2.9） |
| C-15 | `docs/p0-spec-scope-mvp.md` §二 | **Must 链 13 项"当前状态"全写"框架就绪，实测未执行"**，与 V1–V5 已实测矛盾 | ✅ 已按实测逐项回填（1/4/9 项为✅通过；2/3/7/8/10 为⚠️部分，含 `p95`/`anomaly` 未实现、业务表待 P1；5/11/12/13 未执行；6 未达成） |
| C-16 | `docs/prj-ledger-known-issues.md` §六 / `docs/p0-handover-p1.md` §2.5·§2.6 | ISS-009/011/012/013 复现记录仍为"待 D2–D3 填入"；handover 脚本清单仅列 5 个、文档状态仍写"待实测回填" | ✅ 已全部回填；脚本清单补全为 15 个并如实标注哪些无 `--selftest` |
| C-17 | **9 份文档**（`env/env-baseline-v2.md` / `env-baseline-v1.md` / `docs/prj-ledger-version-lock.md` / `docs/p0-checklist-daily.md` / `reports/daily/D1-status.md` / `reports/p0-summary-project-2026-09-28.md` / `reports/p0-summary-project-2026-09-29.md` / `reports/p0-gate-review.md` 等） | 主机名写 `<HOST_ALIAS>` | ✅ **已更正为 `<WORKSTATION>`**。实测 `hostname` / `COMPUTERNAME` / `Win32_ComputerSystem.Name` / DNS **四路一致**，`<HOST_ALIAS>` 不可解析 → **是基线写错、`env/hardware.json` 正确**（原 A-22 的归因方向相反，已一并修正） |
| C-18 | `scripts/collect_env.ps1` / `check_ports.ps1` | **非 ASCII 注释损坏 PS 5.1 解析**：两脚本均约定 ASCII-only，写入中文注释后被按 CP936 解码、吞掉后续换行与花括号，脚本直接报 `Unexpected token '}'` | ✅ 已恢复纯 ASCII（nonASCII=0，`Parser::ParseFile` 零错误），并在文件头重申约束；登记 **ISS-021** |
| C-19 | `scripts/collect_env.ps1` §WSL | **发行版 `Stopped` 时采集永久挂起**（无条件 `wsl -d docker-desktop -- ...`，实测 >120s 不返回，快照写不出） | ✅ 已改为先判状态、仅 `Running` 才进入发行版；否则标 `SKIPPED` + warning。实测 `Stopped` 下 exit 0 并落盘；登记 **ISS-019** |
| C-20 | `scripts/collect_env.ps1` 写盘段 | `wsl.exe` 的 UTF-16LE 输出夹带 `\0`，PS 5.1 `ConvertTo-Json` 对其抛 OOM / 不返回，整份快照写失败 | ✅ 新增 `Repair-String` + `ConvertTo-JsonSafe`，并改为**按分区序列化**（单分区失败只置 `null`）。实测产出 14 KB JSON；登记 **ISS-020** |
| C-21 | `scripts/check_ports.ps1` WSL2 段 | **T1.3 的 WSL2 侧端口结论此前无有效依据**：busybox `sh` 无 `/dev/tcp` → 恒报 `free`（假阴性）；改 `bash -c` 后实测 `bash` 未安装（`bash: not found`）→ 恒报 `unknown`。发行版内实际可用的是 `netstat` / `nc` | ✅ 已改为**发行版内单次 `netstat -ltn` + PowerShell 侧解析**（12 次 `wsl` 调用降为 1 次），并在运行前判发行版状态；实测输出 `distro state: Running` 且 12 端口逐个判定，与发行版内实际监听端口（53/55677/9848/8848/8080）自洽；登记 **ISS-022** |
| C-22 | `scripts/collect_env.ps1` 写盘 / 工具链探针 | ① PS 5.1 的 `Set-Content -Encoding UTF8` 会写入 **BOM**，破坏严格 JSON 读取器（`json.load(encoding='utf-8')` 报错）；② `ollama --version` 在服务未运行时只回一行 `Warning: could not connect...`，被原样当作"版本"写入 | ✅ ① 改用 `File.WriteAllText` + `UTF8Encoding($false)` 写**无 BOM** UTF-8（实测 BOM=False、严格 `json.load` 通过）；② 探针过滤 `Warning|could not connect` 行，取不到版本则记 `UNKNOWN(probe returned empty)` |
| C-23 | **4 份文档** 的 `hardware.json` 采集时间 | 记为 `2026-09-23T20:51`，实际为 `20:59:50`（20:51 是 `env/ports.md` 的 T1.3 端口检查时间，属另一项测量） | ✅ 已更正 `reports/daily/D1-status.md`（2 处）、`docs/p0-handover-p1.md`、`docs/p0-checklist-daily.md`、`reports/p0-report-v1-tool-call.md`、`reports/p0-report-v4b-resources.md`；`env/ports.md` 的 20:51 保持不动 |
| C-24 | `scripts/run_v2.py` `write_summary` / `experiments/v2/summary.csv` | 汇总表**每次 run 整表覆盖**，`summary.csv` 一度只剩 2 行；且残留的 `milvus-hybrid` 行延迟来自另一次 run（p95 110.0240 vs 报告引用的 **9.4800**） | ✅ 已改为**按 `experiment_id` 合并**；并用 `raw/*.jsonl` 把表**还原为 7 行**，recall/mrr/p95 与 `p0-report-v2-hybrid-retrieval` §4.4 逐项一致；原表留档 `summary-pre-2026-09-29.csv`；登记 **ISS-023** |
| C-25 | `reports/p0-report-v1-tool-call.md` §7.2 vs `docs/p0-decision-model-role.md` §四 | V1 中间区间处置步骤数 **2 vs 4**（p0-report-v1-tool-call 缺"Schema 简化"一级）；`plan/…D1-D10…md` §五 的 M0.1 通过条件写 **3 项**（权威为 6 项） | ✅ 已就地标注裁定：步骤数以 `p0-decision-model-role.md` §四 的**四步**为准、M0.1 以 `D1-status.md` §六 的**6 项**为准；`reports/p0-gate-review.md` 的"待裁决"改为**已裁定闭环** |

### A.5 仍待处理（转 P1）

| # | 事项 | 说明 |
|---|---|---|
| ~~D-1~~ | `env/hardware.json` 重采 | ✅ **已完成（2026-09-29）**：发行版 Running 后重采覆盖，`collected_at = 2026-09-29T11:49:36+08:00`、**零警告**；GPU 由 `null` → `RTX 4060 Laptop / 8188 MiB / 616.56 / CC 8.9`，Docker `15.51 GB / ncpu 20` → `19.53 GB / ncpu 10`，`wslconfig_present` `false` → `true`，三模型 digest 齐全；与 `env-baseline-v2.md` **逐项一致**（互为佐证）。旧 v1 快照留档 `env/hardware-v1-2026-09-23.json` |
| D-2 | Redis 容器形态鉴权 | 容器形态需 `bind 0.0.0.0 + protected-mode no`（无鉴权）；P1 改 `requirepass` + 客户端带密（ISS-015） |
| D-3 | `tools_v2.json` 升版 | 统一 `type` 风格、修正 `frozen_at` 时序、与解码侧口径对齐（B-1） |
| D-4 | 心跳超时兜底 | 解码器补"3×上报周期无 DDATA → 置离线"计时器（ISS-017） |
| ~~D-5~~ | `experiments/v2/summary.csv` 覆盖写 | ✅ **已完成（2026-09-29）**：`write_summary` 改为**按 `experiment_id` 合并**（读回既有表 → 覆盖同 id 行 → 其余保留 → 列并集重写），已用两次不同路线验证合并与幂等；**历史数据已用 `raw/*.jsonl` 还原**，`summary.csv` 由 2 行补全为 **7 行**，与 `reports/p0-report-v2-hybrid-retrieval.md` §4.4 逐项一致；原表留档 `experiments/v2/summary-pre-2026-09-29.csv`。登记 **ISS-023** |
| D-6 | 上游待裁决矛盾 | V1 处置步骤数 2 vs 4、M0.1 条件项 3 vs 6（已在 `reports/p0-gate-review.md` 登记） |

---

> **数据来源**：`plan/`（3）、`docs/`（**15**）、`reports/`（v1–v5 + p0-gate-review + p0-summary-project-2026-09-28 + project-summary + daily）、`schemas/`、`protos/`、`docker/`（4 compose + 1 Dockerfile）、`configs/`（4）、`scripts/`（18）、`evals/`、`experiments/`（v1–v5）、`env/`、`prompts/`、`.trae/`；新增 `README.md` / `requirements.txt` / `CHANGELOG.md`。
> **本次验证**：10 个 Python 脚本 `--selftest` 全部 exit 0；4 个 JSON 解析通过；`compose.base.yml` / `compose.ingest.yml` / `compose.v2.yml` 及 `base + v4b-iso` 合并渲染 `docker compose config --quiet` 全部通过。
> **引用纪律**：本文为导读性汇总，任何结论以其原始文档为准；引用环境 / 版本须以 `env/env-baseline-v2.md` 与 `docs/prj-ledger-version-lock.md` 为准。

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | 文档同步整理：加「历史留痕」横幅（正文结论一字未改）；文件重命名 → `p0-summary-project-2026-09-29.md` | 头部 / 索引 |
