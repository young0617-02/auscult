# 云侧工业 IoT 诊断 Agent 系统 · 最终执行方案（V5.0 定稿）

> **文档定位**：本项目**唯一有效**的方案文档。整合并**取代**以下文档的口径冲突：
> `云侧工业 IoT 诊断 Agent 方案分析报告.md`、`Phase 0 方案验证与完善.md`、`Phase 0 方案完善与执行计划.md`、`Phase 0 完整执行方案.md`（以上保留为评审记录，不再作为执行依据）。
> **本版新增（选型论证并入）**：LLM 选型维度体系（§3.7）、部署形态选型（§3.8）、本地 CUDA 资源使用（§3.9）、数据库选型 MongoDB vs PostgreSQL（§3.10）、入口网关 Nginx（§3.11）——形成"设计 + 论证"完整闭环。
> **事实基线**：`本机配置.md`（image-1/2/3 实测截图）+ 官方文档核实结论。
> **定稿日期**：2026-09-21
> **执行主体**：单人（"机器并行、人串行"），除标注"外部依赖"外。
> **总工期基准**：Phase 0 = 10 个工作日（D1–D10），其余阶段见 §九。

---

## 目录

- [零、本次定稿解决的三类问题](#零本次定稿解决的三类问题)
- [一、项目定位与目标](#一项目定位与目标)
- [二、本机环境基线（实测）](#二本机环境基线实测)
- [三、技术选型与版本锁定](#三技术选型与版本锁定)
- [四、系统架构设计](#四系统架构设计)
- [五、接口契约（开发就绪）](#五接口契约开发就绪)
- [六、关键机制设计](#六关键机制设计)
- [七、安全设计（四道防线）](#七安全设计四道防线)
- [八、风险登记册](#八风险登记册)
- [九、实施路线图与里程碑](#九实施路线图与里程碑)
- [十、MVP 范围与停止条件](#十mvp-范围与停止条件)
- [十一、验收指标与门禁判据](#十一验收指标与门禁判据)
- [十二、附录](#十二附录)

---

## 零、本次定稿解决的三类问题

评审与下游文档共指出 **12 项待裁决问题（Q1–Q12）+ 10 项遗漏风险（R-M1–R-M10）**。本定稿依据本机实测配置与官方文档核实，逐条收敛：

| 类别 | 问题 | 定稿处理 | 位置 |
|---|---|---|---|
| **事实冲突** | Milvus 版本（3.0 vs ≥2.5） | 锁定 **v3.0.0**（本机已拉取镜像 + 官方 v3.0.x 能力核实） | §三 |
| **事实冲突** | BM25 实现路径（服务端/客户端） | 锁定 **服务端 `FunctionType.BM25`**（自动生成稀疏向量） | §三、§五 |
| **事实冲突** | 本地 LLM 定位错配（R1 做工具调用） | 锁定 **双模型分工**：`qwen2.5:7b` 工具调用 + `deepseek-r1:7b` 诊断推理 | §三、§六 |
| **事实冲突** | PG16/Redis7/R1-7B 与实际不符 | 锁定 **PostgreSQL 18 / Redis 8 / Ollama 双 7B 模型** | §三 |
| **确定性冲突** | Sparkplug B 连接器"已提供" | 降格为 **待验证假设**（本机 D-1 首步确认社区版授权） | §三、§九 |
| **结构性缺失** | 硬件约束与降级映射 | 补齐 **实测硬件表 + 内存档判定 + 降级映射（含指标代价）** | §二、§三 |
| **结构性缺失** | 接口契约（工具/State/REST/Redis） | 补齐 **完整入出 Schema + 类型化 State + 事件契约 + key 规范** | §五 |
| **结构性缺失** | 置信度 0.75 无来源 | 补齐 **复合置信度公式 + 校准方法（温度缩放 + ECE）** | §六 |
| **结构性缺失** | 跨存储一致性无补偿 | 补齐 **Outbox 模式 + 对账脚本 + 权威源定义** | §六 |
| **结构性缺失** | 审核生命周期缺失 | 补齐 **超时/死锁/并发/幂等/eviction 全套策略** | §六 |
| **结构性缺失** | 无 MVP 分层与停止条件 | 补齐 **Must/Should/Could/Won't + 可判定停止条件** | §十 |
| **口径冲突** | 三套工期并存 | 统一为 **Phase 0 十天 + 后续阶段相对占比** | §九 |
| **选型论证** | LLM 选型缺维度体系 | 补齐 **八维权重 + 候选评分矩阵** | §3.7 |
| **选型论证** | 部署形态未论证 | 锁定 **混合架构、本地优先** | §3.8 |
| **选型论证** | CUDA 用途未说明 | 明确 **推理刚需 / 微调可选 / 训练不可行** | §3.9 |
| **选型论证** | 未对比 MongoDB/PG | 锁定 **PostgreSQL 18，不引入 MongoDB** | §3.10 |
| **选型论证** | 入口网关未定 | **Phase 4+ 引入 Nginx**（反代 + WS + SSL） | §3.11 |

---

## 一、项目定位与目标

### 1.1 背景：三重结构性矛盾

1. **知识获取效率低**：设备手册 / 维修工单 / 专家经验分散，故障定位以"小时"计。
2. **数据安全约束刚性**：设备参数、工艺曲线不可上传公有云，通用 LLM 无法直接使用。
3. **通用模型幻觉风险高**：错误维修建议可导致设备二次损坏或安全事故。

**可行性对冲**：工业 IoT 基础设施（MQTT/Sparkplug B、TDengine、Milvus v3.0、Neo4j）+ 本地开源模型（Ollama 7B）+ 本地算力（RTX 4060 8GB）已同时具备，条件成熟。

### 1.2 核心目标

> 以**设备告警为触发入口**，通过 **LangGraph 编排**多源证据（传感器时序 / 设备手册 / 历史工单 / 知识图谱），经**本地/云端混合推理**，输出**带引用来源、置信度与安全提示的结构化维修建议**——**辅助诊断而非自动决策**。

### 1.3 差异化定位

| 定位 | 说明 |
|---|---|
| **Agent 驱动而非检索驱动** | 以告警事件为入口，Agent 自主决定工具序列，区别于"问答式 RAG" |
| **多源证据融合** | 四类证据源互补：图谱给"关系路径"，文档给"语义细节"，时序给"事实判据"，工单给"经验模式" |
| **安全边界明确** | 工具白名单 + 确定性策略约束 + 高风险强制人工审核 + 不提供"一键执行" |
| **本地优先、云为兜底** | 敏感数据不出本地；仅在低置信度时按策略升级云端 |

### 1.4 主演示场景（锁定）

> **离心泵驱动端轴承振动异常**：传感器振动 RMS / 温度 / 电流告警 → Agent 检索手册与历史工单 → 图谱推理故障链（轴承磨损 → 润滑不足 → 温度升高）→ 输出"检查润滑 / 更换轴承"结构化建议 → 高风险（涉及停机）强制人工审核。

### 1.5 电梯演讲（一句话卖点）

> **"一个跑在本地、以告警为入口、会自己查资料并给出带出处维修建议的工业诊断 Agent——数据不出厂，结论可追溯。"**

---

## 二、本机环境基线（实测）

> 来源：`本机配置.md` image-1/2/3 实测截图。**本表为"环境基线文档 v1"主体，所有验证报告须引用本表版本号。**

### 2.1 硬件参数表（实测）

| 维度 | 实测值 | 说明 |
|---|---|---|
| 操作系统 | Windows 11（内核 10.0.26200.7171） | 容器需 WSL2 + Docker Desktop |
| CPU | 13th Gen Intel Core i7-13650HX @ 2.60 GHz | 14 核 20 线程（6P+8E），**CPU 档充足** |
| 物理内存 | **32.0 GB**（4800 MT/s DDR5） | 判定所属内存档 |
| GPU | **NVIDIA GeForce RTX 4060 Laptop GPU** | **显存 8 GB（关键瓶颈）** |
| 磁盘 | 954 GB，已用 357 GB → **可用 ~597 GB** | 满足 50–100GB 镜像/权重需求，余量充裕 |
| 容器环境 | Docker Desktop（Personal）运行中 | 当前占用 4.12 GB 内存 |

### 2.2 资源档判定（按"峰值 ≤ 物理内存 × 75%"判据）

| 判据 | 计算 | 结论 |
|---|---|---|
| 内存准入线 | 32 GB × 75% = **24 GB** | 内存侧属 **≥24GB 高档**，Milvus Standalone 可承载 |
| GPU 显存准入线 | 8 GB，需容纳 7B 模型 + 嵌入 + 重排 | **显存侧属"紧档"，三者不可常驻共存** |

> **结论**：内存为高档、**显存为瓶颈**。采用"**7B 模型常驻 GPU + BGE-M3/reranker 分时调度（不常驻）**"策略；若实测冲突，则嵌入/重排降级到 CPU（见 §3.5 降级映射）。

### 2.3 已装组件清单（实测，避免重复拉取）

| 类别 | 组件 | 实测版本 / ID | 状态 |
|---|---|---|---|
| 向量库 | `milvusdb/milvus` | **v3.0.0**（49371c30af46, 3.93 GB） | ✅ 已拉取 |
| 元数据 | `quay.io/coreos/etcd` | v3.5.25 | ✅ 已拉取 |
| 对象存 | `minio/minio` | RELEASE.2024-12-18T13-15-... | ✅ 已拉取 |
| 关系库 | `postgres` | **18** | ✅ 已拉取 |
| 缓存 | `redis` | **8** | ✅ 已拉取 |
| 其他 | `mysql` / `mongodb-atlas-local` | 8.4 / 8.0 | ✅（本项目暂不用） |
| 本地 LLM | Ollama（**宿主机运行**） | `qwen2.5:7b`（845dbda0ea48, 4.7GB）/ `deepseek-r1:7b`（755ced02ce7b, 4.7GB） | ✅ 已就位 |
| 加速运行时 | CUDA / PyTorch | `D:\py312-torch`（Python 3.12 + torch + CUDA） | ✅ 本地 |
| 嵌入模型 | 本地模型仓 | `D:\modelscope\hub\models`（BGE-M3 等） | ✅ 本地 |

### 2.4 待拉取 / 待安装清单

| 组件 | 用途 | 建议版本 | 备注 |
|---|---|---|---|
| `neo4j` | 知识图谱 | Community 5.x | `query_graph` 数据源 |
| `tdengine`（含 taosX） | 时序库 | **3.3.6 LTS** | SparkplugB 接入，授权待验证 |
| MQTT Broker | 数据接入 | **Mosquitto 2.x**（默认）/ EMQX 5.x（备选） | 见 §3.3 裁决 |
| FastAPI / Next.js 运行栈 | 后端/前端 | — | 开发期 |

### 2.5 WSL2 / Docker Desktop 配置基线（**D1 必做**）

Windows 下 Docker Desktop 默认仅分配宿主内存的 50%（约 16 GB），**不足以承载全组件**。须在 `%UserProfile%\.wslconfig` 提升上限：

```ini
[wsl2]
memory=20GB          # 32GB 宿主分配 20GB 给 WSL2（留 12GB 给 Windows + Ollama）
processors=10
swap=8GB
localhostForwarding=true

[experimental]
autoMemoryReclaim=gradual
```

**GPU 直通**：若在容器内跑嵌入/重排，需 Docker Desktop 开启 WSL2 GPU 支持（默认已启用 `--gpus all`）。**本项目推荐嵌入/重排走宿主机 Python（`D:\py312-torch`）**，规避容器 GPU 直通复杂度。

### 2.6 端口规划（冲突检查 + 重映射）

| 端口 | 组件 | 本机占用风险 | 规划 |
|---|---|---|---|
| 19530 | Milvus gRPC | 低 | 保持 |
| 9091 | Milvus metrics | 低 | 保持 |
| 7474 / 7687 | Neo4j HTTP / Bolt | 低 | 保持 |
| 6030 / 6041 | TDengine | 低 | 保持 |
| 5432 | PostgreSQL | **中** | 冲突时→5433 |
| 6379 | Redis | 低 | 保持 |
| 11434 | Ollama（宿主） | — | 保持 |
| 1883 | MQTT | 低 | 保持 |
| 8000 | FastAPI | 低 | 保持 |
| 3000 | Next.js | **中** | 冲突时→3001 |

---

## 三、技术选型与版本锁定

### 3.1 锁定总表（**全文唯一版本口径**）

| 层级 | 选型 | **锁定版本** | 依据 |
|---|---|---|---|
| 数据接入 | MQTT Broker | **Mosquitto 2.x**（默认）| 轻量；EMQX 为备选（见 §3.3） |
| 工业协议 | MQTT + Sparkplug B | TDengine taosX 解码 | 授权待验证 |
| 时序库 | TDengine | **3.3.6 LTS** | SparkplugB 面向 3.x |
| 文档解析 | MinerU | 最新稳定版 | P1 首日 Spike 验证 |
| 嵌入模型 | BGE-M3 | 本地 `D:\modelscope\hub\models` | 中文工业语料 |
| 向量库 | **Milvus Standalone** | **v3.0.0**（镜像 digest 待补） | 本机已拉取 + §3.2 |
| 重排序 | BGE-reranker-v2-m3 | 锁定快照 | 标准选择 |
| 知识图谱 | Neo4j Community | 5.x | Cypher 成熟 |
| 编排 | LangGraph | 锁定版本 | interrupt/resume 刚需 |
| 本地 LLM | **Ollama 双模型** | `qwen2.5:7b`（工具调用）+ `deepseek-r1:7b`（诊断推理）| 本机已就位 + §3.4 |
| LLM 网关 | LiteLLM | 锁定版本 | 多云 fallback |
| 业务库 | **PostgreSQL 18** | 18（本机镜像） | 权威状态源 |
| 缓存/会话 | **Redis 8** | 8（本机镜像），`maxmemory-policy=noeviction` | 运行态 Checkpoint |
| 后端 | FastAPI | 锁定版本 | — |
| 前端 | Next.js + Tailwind + shadcn/ui | 锁定版本 | — |
| 实时通信 | Socket.IO（python-socketio + ASGI） | 锁定版本 | 需 Compose 体现适配层 |
| 图谱可视化 | react-force-graph | 锁定版本 | — |
| 评测 | RAGAS + 自建问答集 | 锁定版本 | — |
| 可观测 | Langfuse + Prometheus/Grafana | 锁定版本 | 补齐指标/日志/告警 |
| 部署 | Docker Compose | — | 单机方案 |

> **口径纪律**：任何位置出现与上表不同的版本号，以本表为准；`镜像 digest（待填）` 字段在 Phase 0 D9 版本锁定清单中补齐。

### 3.2 Milvus v3.0.0 与 BM25 路径（**已核实，不再是假设**）

**核实结论**（Milvus v3.0.x 官方/镜像文档）：

- v3.0.x 提供 **BM25 Function**，属**服务端"本地文本函数"**，在 Milvus 内部运行，**无需模型推理或外部集成**；
- **稀疏向量由服务端自动生成**：写入时原始文本经 Analyzer 分词 → 计算 TF/DF/平均长度 → 生成稀疏嵌入并维护倒排列表；查询时同一 Analyzer 处理，保证分词一致；
- 文本字段须 `enable_analyzer=True`；稀疏字段 `SPARSE_FLOAT_VECTOR`；Function 用 `FunctionType.BM25`；
- 索引：`index_type="SPARSE_INVERTED_INDEX"`、`metric_type="BM25"`，参数 `bm25_k1=1.2`、`bm25_b=0.75`；
- 插入/查询**只传原始文本**，**不传稀疏向量**；
- **中文分词**：默认 `standard` 分析器对中文近乎无效，**必须**配置自定义分析器的 `jieba` tokenizer。

> **裁决**：选用**服务端 `FunctionType.BM25`**（而非客户端 `BM25EmbeddingFunction`）。理由：声明式、服务端一致性更好、新增语料自动更新统计、P1 建库工程量最小。**中文 analyzer 为 V2 成败关键**，须做分词结果人工抽检。

### 3.3 MQTT Broker 裁决

| 方案 | 优点 | 缺点 | 裁决 |
|---|---|---|---|
| **Mosquitto 2.x** | 极轻（~10MB 内存），部署简单 | 无内置 Sparkplug B 感知 | **默认采用**（配合 taosX 解码） |
| EMQX 5.x | Sparkplug B 生态插件成熟 | 显著更重（数百 MB~GB 级内存） | **备选**（Mosquitto 不满足时启用，须重算内存预算）|

> 选择 Mosquitto 的前提是 **taosX 侧能独立完成 Sparkplug B 解码**（§3.6 首步验证）；若必须依赖 EMQX 插件，则切换到 EMQX 并触发 V4b 内存重测。

### 3.4 本地 LLM 双模型分工（**核心裁决**）

| 事实 | 依据 |
|---|---|
| `qwen2.5:7b` **原生支持 Function Calling / 工具调用** | Qwen2.5 系列训练含 function calling；Ollama 模板含 tools |
| `deepseek-r1:7b`（蒸馏版）**不支持结构化工具调用** | 蒸馏模型最大短板；会输出 ` thinking` 长链 |
| 本地显存 8GB，两模型不可同时常驻 | §2.2 |

**分工结论**：

| 角色 | 模型 | 理由 |
|---|---|---|
| **工具调用 / 结构化决策** | `qwen2.5:7b` | 原生 FC，JSON 可解析率高 |
| **诊断推理 / 根因分析** | `deepseek-r1:7b` | 长链推理强，但**仅做文本推理、不产生工具调用** |
| **云端兜底** | LiteLLM 转发（1 个云端模型） | 低置信度升级 + 上界校准 |

> 若 V1 实测 `qwen2.5:7b` 首次成功率 ≥90%，则工具调用定于本地；70–90% 则叠加约束解码 + few-shot；<70% 触发"本地推理 + 云端工具调用"降级。
> 本地模型因显存限制**按需切换**（Ollama `keep_alive` 控制），避免与嵌入/重排争显存。

### 3.5 降级映射表（**含指标代价，任何降级不得默认沿用原指标**）

| 触发条件 | 向量库 | 图谱 | 时序 | LLM 驻留 | 对指标的影响 |
|---|---|---|---|---|---|
| 全组件峰值 ≤ 24GB 且显存调度可行 | Milvus Standalone v3.0.0 | Neo4j | TDengine | 7B 常驻 GPU | 原指标不变 |
| 峰值 24–28GB（超限 ≤10%） | Milvus Standalone | Neo4j | TDengine | 7B GPU + 嵌入/重排 CPU 或分时 | `P95 检索 < 800ms` 需实测复核 |
| 峰值 > 28GB（严重超限） | **Milvus Lite** 或 pgvector | PostgreSQL 关系表 / NetworkX | TDengine | 本地仅诊断推理，工具调用走云端 | `Recall@5 ≥ 85%` **须重测**；`P95` 可能放宽 |
| GPU 显存不足（<8GB 可用） | 不变 | 不变 | 不变 | 7B 转 CPU 推理（QLoRA 级量化） | 端到端延迟显著上升，`P95 < 3s` 大概率不达标 |

### 3.6 TDengine Sparkplug B 接入形态（**待验证假设**）

**核实结论**：TDengine 通过 **`taosX`（接入引擎）+ `taosExplorer`（Web 管理界面）** 提供 SparkplugB **零代码接入**：

- 支持消息类型：`NBIRTH/NDEATH/NDATA/NCMD/DBIRTH/DDEATH/DDATA/DCMD/STATE`；
- Payload 为 **Protobuf**，检索时转 JSON；
- 支持模板化超级表创建、字段拆分、过滤、异常策略（归档/丢弃/报错/缓存）；
- 文档面向 **3.x（3.3.6 LTS / 3.4.x）**。

> ⚠️ **授权边界未确认**：官方文档未标注"社区版可用 / 需 License"。**Phase 0 D1 首步必须确认社区版（OSS）是否包含 SparkplugB 接入**。
> **降级路径**（若为商业功能）：三种备选，按成本排序 —— ① EMQX 插件转 JSON 后桥接 taosX；② 自研 Protobuf 消费者（Python，+2 天工期）；③ MQTT JSON 直写 TDengine（放弃 Sparkplug B 编码优势）。

### 3.7 LLM 选型维度体系与评分（深化论证）

**八维权重**（按本项目紧要程度排序）：

| # | 维度 | 判据 | 权重 |
|---|---|---|---|
| D1 | **工具调用 / 结构化输出能力** | 是否原生 Function Calling、JSON Schema 约束 | ⭐⭐⭐⭐⭐（Agent 命脉） |
| D2 | **数据合规与部署形态** | 能否完全本地运行 | ⭐⭐⭐⭐⭐（刚性） |
| D3 | **硬件匹配度** | 量化后能否装入 8GB 显存 | ⭐⭐⭐⭐⭐ |
| D4 | 推理质量 | 中文/工业语料/长链推理正确率 | ⭐⭐⭐⭐ |
| D5 | 推理速度 | TTFT、吞吐、`think` token 占比 | ⭐⭐⭐⭐（`P95 < 3s` 预算） |
| D6 | 成本（TCO） | 硬件折旧 + 电费 + 云 token | ⭐⭐⭐ |
| D7 | 生态与工具链 | Ollama/LiteLLM、OpenAI 兼容、版本稳定 | ⭐⭐⭐ |
| D8 | 上下文长度 | 单次可用上下文 | ⭐⭐（**RAG 分块后可弱化**） |

> **关键洞察**：D8 权重最低。本项目用 RAG 把长文档切块，**无需依赖超长上下文**；显存预算应花在"能力与速度"上，而非"堆上下文"。

**候选评分矩阵**：

| 候选 | 工具调用 | 可本地(8GB) | 推理质量 | 速度 | 结论 |
|---|---|---|---|---|---|
| **`qwen2.5:7b`** | ✅ 原生 FC | ✅ Q4 4.7GB | 中上 | 快（无长 `think`） | **选为工具调用/决策模型** |
| **`deepseek-r1:7b`（蒸馏）** | ❌ 不支持结构化 FC | ✅ Q4 4.7GB | 高（长链推理） | 慢（大量 `think`） | **选为诊断推理模型（不产工具调用）** |
| `qwen2.5:14b` | ✅ | ❌ Q4≈9GB 装不下 | 高 | 慢 | 淘汰（硬件不允许） |
| `qwen2.5:3b` | ✅ | ✅ 极轻 | 中 | 很快 | 备选（仅意图分类/查询改写） |
| 云端大模型（闭源） | ✅ 强 | ❌ 需联网 | 最高 | 受网络 | **仅兜底与上界校准** |

**结论**：见 §3.4 分工表（`qwen2.5:7b` 工具调用 + `deepseek-r1:7b` 诊断推理 + 云端兜底）。

### 3.8 部署形态选型（纯本地 / 纯云端 / 混合）

| 维度 | 纯本地 | 纯云端 | **混合（推荐）** |
|---|---|---|---|
| 数据安全 | ✅ 零外泄 | ❌ 数据出域 | ✅ 本地为主，云端仅脱敏摘要 |
| 能力上限 | ⚠️ 7B 封顶 | ✅ 最强 | ✅ 本地 7B + 云端兜底 |
| 成本结构 | 一次性硬件 | 按 token 线性增长 | 硬件 + 少量云端 |
| 延迟 | ✅ 稳定（无网络） | ❌ 受网络抖动（+1–3s） | ⚠️ 主流路径本地快，升级路径慢 |
| 可用性 | ✅ 断网可用 | ❌ 断网即停 | ✅ 云端故障可降级 |
| 并发 | ❌ 单机受限 | ✅ 弹性 | ⚠️ 本地受限，峰值可溢出云端 |
| 运维复杂度 | 中 | 低 | 中高（两套） |
| 适用场景 | 敏感数据、离线现场、演示 | 非敏感、追求极致质量、突发高并发 | **敏感 + 需兜底质量** |

> **结论**：**混合架构、本地优先**。理由：① 合规刚性（纯云端直接被否）；② 已具备本地算力（RTX 4060 + Ollama 双模型）；③ 本地 7B 有边界（需云端"最后保险"）；④ 断网仍可完整跑通主流程。
> **路由与脱敏**：策略见 §5.4 与 §6.1；**送云端前必须剥离设备编号、工艺参数、厂区信息**，只保留"故障现象 + 通用知识"；云端超预算触发 `budget:cloud:{day}` 熔断。

> **术语澄清**：项目名中的"**云侧**"指**相对设备侧的"平台侧"层级**（区别于边缘网关），**不等于"必须部署在公有云"**——"云侧架构 + 本地化部署"并不矛盾。

### 3.9 本地 CUDA 资源使用（训练 / 微调 / 推理）

> **结论**：CUDA **会被实际使用且是刚需——但主要用于「推理」，而非「训练」**。

| 阶段 | 是否用 CUDA | 本机（RTX 4060 8GB）可行性 | 说明 |
|---|---|---|---|
| 推理（7B LLM） | ✅ **核心刚需** | ✅ 可行 | Ollama 默认 CUDA 加速，7B Q4 权重 ~4.5GB |
| 推理（嵌入 BGE-M3） | ✅ 使用 | ✅ 可行 | 稠密向量编码，~1–2GB |
| 推理（reranker） | ✅ 使用 | ⚠️ 需分时 | 与 7B 同时驻留可能超显存 |
| 微调（LoRA / QLoRA） | ⚠️ 可选 | ⚠️ 勉强 | QLoRA 7B 需 ~8–10GB，需梯度检查点 + 小 batch |
| 全参数训练 | ❌ 不可行 | ❌ 不可行 | 7B 全参需 60GB+ 显存 |
| 格式转换 / 量化 | ✅ 使用 | ✅ 可行 | GGUF 量化、LoRA 合并 |

**显存预算分配（8 GB，关键约束）**：

| 用途 | 占用 |
|---|---|
| 7B Q4 权重（常驻） | ~4.5 GB |
| KV Cache（8K ctx） | ~1.0–1.5 GB |
| 运行时开销 | ~0.5 GB |
| **剩余可用** | **~1.5–2.0 GB（仅够嵌入或重排之一）** |

**调度纪律**：LLM 常驻 GPU（`keep_alive` 保活）；BGE-M3 / reranker **按需加载或降级 CPU**（`D:\py312-torch` 支持 CPU）；**严禁三者同时驻留**，否则 OOM 或显存换页致延迟飙升。

**环境要点**：宿主机 Ollama 直调 CUDA（无需容器）；嵌入/重排**推荐走宿主 Python** 规避容器 GPU 直通；`nvidia-smi` 校验驱动/CUDA 与 PyTorch 版本匹配。

**微调纪律**：不做全参数训练；优先 **Prompt + RAG + few-shot**；若确需领域适配，Phase 4+ 以 **QLoRA** 实验或借云 GPU，产物归入 **Won't → 预留接口**（§10.3）。

### 3.10 数据库选型（MongoDB vs PostgreSQL）

**六维度对比**：

| 维度 | **MongoDB** | **PostgreSQL** |
|---|---|---|
| 数据模型 | 文档型（BSON），Schema-less，嵌套自然 | 关系型 + **JSONB**，强 Schema |
| 事务 | 4.0+ 多文档 ACID，4.2+ 分布式事务，**开销较大** | **原生 ACID**，成熟稳定 |
| 查询能力 | 聚合管道强；**跨集合 JOIN 弱** | **SQL 强大**：JOIN / 窗口函数 / CTE |
| 索引 | 灵活（复合/文本/地理） | 丰富（B-tree/GIN/GiST/BRIN/pgvector） |
| 扩展性 | **原生水平分片** | 垂直为主，水平需 Citus |
| 一致性 | 可调（默认偏最终一致） | **强一致**（ACID） |
| 生态 | Atlas 成熟 | **生态最大**（JSONB/pgvector/PostGIS） |
| 运维成本 | 分片复杂，内存敏感 | 工具成熟，资料丰富 |

**本项目需求画像**：业务库承载 **报告 / 审核 / 审计 / 用户权限**，核心诉求为 **强事务 + 强一致 + 复杂关联查询 + 审计不可篡改**——恰好全落在 MongoDB 的**弱项**上（时序→TDengine、向量→Milvus、图谱→Neo4j、运行态→Redis 均已他属）。

> **结论**：**采用 PostgreSQL 18 作为唯一权威业务库；不引入 MongoDB。**
> 理由：① 强 ACID 支撑报告状态机与审核流转；② 多表 JOIN 远比聚合管道自然；③ 审计可用**追加表 + 禁改触发器**落地；④ 灵活字段用 **JSONB + GIN** 即可，无需为"灵活"多养一个库；⑤ 本机已 pull `postgres:18`，零额外成本。

**JSONB 替代示例**：

```sql
CREATE TABLE reports (
    report_id  UUID PRIMARY KEY,
    thread_id  UUID NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low','medium','high')),
    status     TEXT NOT NULL,
    confidence NUMERIC(4,3),
    payload    JSONB,                        -- 灵活字段（建议/引用/证据）
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_reports_payload ON reports USING GIN (payload);
```

**MongoDB 更合适的边界**（本项目均不成立）：大规模半结构化日志/遥测原始存储（已交 TDengine）、Schema 频繁变更（业务模型稳定）、跨分片水平扩展（单机小数据量）、文档嵌套为主无需关联（本项目强关联）。

### 3.11 入口网关选型（Nginx）

> **结论**：**Phase 0–3 不引入；Phase 4+ 引入**（生产化/统一入口阶段）。纯内网演示可用 **Caddy** 或直接暴露端口替代。

| 职责 | 说明 | 需要度 |
|---|---|---|
| **反向代理** | 统一入口 → FastAPI(:8000) / Next.js(:3000) | ⭐⭐⭐⭐⭐ |
| **WebSocket 代理** | Socket.IO 需透传 `Upgrade`/`Connection` 头，**否则实时推送失效** | ⭐⭐⭐⭐⭐ |
| **SSL/TLS 终止** | 提供 HTTPS（内网可自签） | ⭐⭐⭐ |
| 静态资源服务 | Next.js 静态产物缓存 + gzip/brotli | ⭐⭐⭐ |
| 限流/防刷 | 保护诊断接口与云端配额 | ⭐⭐⭐ |
| 负载均衡 | 多后端实例（`upstream`） | ⭐（当前单实例） |
| 安全响应头 | HSTS / CSP / X-Frame-Options | ⭐⭐ |

**架构位置**：

```
客户端 ──HTTPS──► Nginx(:443)
                    ├── /           ──► Next.js (:3000)  静态 + SSR
                    ├── /api/       ──► FastAPI (:8000)  REST
                    └── /socket.io/ ──► FastAPI (:8000)  WebSocket 升级
```

**分期建议**：

| 阶段 | 是否用 Nginx | 入口形态 |
|---|---|---|
| Phase 0–3（开发验证） | ❌ 不用 | 直接 `localhost:8000` / `:3000` |
| Phase 4（前端集成） | ⚠️ 可选 | Next.js rewrite 代理 API |
| Phase 5+（演示/生产化） | ✅ 引入 | Nginx 统一入口 + HTTPS + WS |

---

## 四、系统架构设计

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  入口层  Nginx（Phase 4+）：反向代理 + WebSocket 透传 + SSL    │
├─────────────────────────────────────────────────────────────┤
│  表现层  Next.js + shadcn/ui + Socket.IO 实时推送             │
│  页面：告警看板 / 诊断对话 / 报告详情+审核 / 知识库 / 图谱可视化  │
├─────────────────────────────────────────────────────────────┤
│  编排层  LangGraph（StateGraph + Checkpointer）              │
│  节点：告警解析 → 传感器分析 → 知识检索 → 诊断推理 → 报告生成 → 人工审核 │
│  工具：retrieve_knowledge / query_sensor / query_graph /     │
│        get_maintenance_history / generate_report             │
├─────────────────────────────────────────────────────────────┤
│  推理层  LiteLLM 网关                                        │
│  ├─ 本地：qwen2.5:7b（工具调用） / deepseek-r1:7b（诊断推理） │
│  └─ 云端兜底（置信度路由触发）                                │
├─────────────────────────────────────────────────────────────┤
│  检索层  混合检索：Dense(BGE-M3) + Sparse(BM25) + RRF + reranker │
│  图谱检索：Neo4j Cypher 多跳                                 │
├─────────────────────────────────────────────────────────────┤
│  数据层  Milvus v3.0.0 / Neo4j / TDengine / PostgreSQL 18 / Redis 8 │
├─────────────────────────────────────────────────────────────┤
│  接入层  MQTT(Mosquitto) + Sparkplug B(taosX) → TDengine     │
│         告警引擎（阈值 + 滑动窗口）→ 去重 → LangGraph 触发     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 七大功能模块（边界清晰、依赖单向）

| 模块 | 职责 | 关键产出 |
|---|---|---|
| 2.1 IoT 接入与告警 | MQTT/Sparkplug B 接入、时序写入、告警生成、Redis 去重 | 告警事件流 |
| 2.2 知识库管理 | MinerU 解析、Parent-Child 分块、三存储写入、版本管理 | 文档块 / 三元组 / 元数据 |
| 2.3 混合检索 | 查询改写、Dense+BM25 并行、RRF、reranker Top-5、图谱融合 | 证据集（含来源） |
| 2.4 Agent 编排 | State 管理、节点路由、工具调用、置信度路由 | 决策轨迹 |
| 2.5 报告与审核 | 结构化报告、高风险强制审核、降级显式化 | 报告 + 审计 |
| 2.6 前端交互 | 五类页面、对话式追问、实时推送 | 用户界面 |
| 2.7 权限与审计 | RBAC（三角色 + 知识库管理员）、全操作审计、职责分离 | 审计日志 |

### 4.3 三条数据流

**① 离线知识构建流**

```
PDF/工单/规程 → MinerU 解析 → Parent-Child 分块 → 元数据标注
   → ①写入 Milvus(稠密+稀疏) ②写入 Neo4j(三元组) ③写入 PostgreSQL(元数据/版本)
   → 【Outbox 对账】确认三写一致
```

**② 在线诊断请求流**

```
MQTT 告警 → 去重(Redis 滑动窗口) → LangGraph 触发
   → 告警解析 → 传感器分析(query_sensor) → 知识检索(retrieve_knowledge+query_graph)
   → 历史工单(get_maintenance_history) → 诊断推理(置信度计算)
   → [置信度<0.75 → 云端升级 / 重检索] → 报告生成(generate_report)
   → [高风险 → interrupt 人工审核] → Socket.IO 推送 → 审计落库
```

**③ 业务数据管理流**

```
登录(RBAC) → 告警/报告/知识库查询 → 审核(通过/驳回+意见) → 知识库更新(版本升版) → 审计
```

### 4.4 数据存储归属表（一表定责）

| 数据 | 存储 | 权威源 | 说明 |
|---|---|---|---|
| 传感器时序 | TDengine | ✅ | 原始遥测 |
| 告警事件 | TDengine(生成) + PostgreSQL(状态) | PostgreSQL | 状态流转 |
| 文档块 + 向量 | Milvus | ✅ | 检索主体 |
| 三元组 | Neo4j | ✅ | 图谱 |
| 文档元数据/版本 | PostgreSQL | ✅ | `knowledge_versions` |
| 报告 | PostgreSQL | ✅ | `reports` 表 |
| **工作流状态** | Redis（运行态）/ PostgreSQL（报告态） | **PostgreSQL** | 见 §6.4 |
| 审核记录 | PostgreSQL | ✅ | `audit_logs` |
| 会话上下文 | Redis（TTL 24h） | — | 非权威，可重建 |

---

## 五、接口契约（开发就绪）

### 5.1 五个工具的完整契约（Pydantic ↔ JSON Schema v1）

> **D1 冻结，改动即升版。** 所有工具入参/返回均定义完整；只读工具在图内执行，**写操作 `generate_report` 置于审核之后/图外**（见 §6.4）。

#### ① `retrieve_knowledge`

```python
class RetrieveKnowledgeInput(BaseModel):
    query: str = Field(..., description="查询文本（已改写）")
    top_k: int = Field(5, ge=1, le=20)
    filters: dict | None = Field(None, description="{device_model, doc_type, section}")

class EvidenceItem(BaseModel):
    chunk_id: str
    doc_id: str
    content: str
    source: str          # 文件路径/标题
    page: int | None
    score: float         # 归一化 0~1

class RetrieveKnowledgeOutput(BaseModel):
    items: list[EvidenceItem]
    total: int
    elapsed_ms: int
```

#### ② `query_sensor`

```python
class QuerySensorInput(BaseModel):
    device_id: str
    metric: str                       # e.g. "vibration_rms"
    time_range: tuple[datetime, datetime]
    agg: Literal["avg","max","min","p95","trend"] = "avg"

class QuerySensorOutput(BaseModel):
    points: list[dict]                # {ts, value}
    stats: dict                       # {avg, max, min, p95, slope}
    anomaly: bool                     # 是否触发异常判据
    baseline_window: dict | None      # 冷启动基线
```

#### ③ `query_graph`

```python
class QueryGraphInput(BaseModel):
    entity: str                       # e.g. "bearing_wear"
    relation_types: list[str] | None  # e.g. ["CAUSES","PART_OF","MITIGATED_BY"]
    max_hops: int = Field(2, ge=1, le=3)

class GraphPath(BaseModel):
    nodes: list[str]
    relations: list[str]
    confidence: float

class QueryGraphOutput(BaseModel):
    paths: list[GraphPath]
    entities: list[dict]
```

#### ④ `get_maintenance_history`

```python
class MaintenanceHistoryInput(BaseModel):
    device_id: str | None = None
    fault_keyword: str | None = None
    limit: int = Field(10, ge=1, le=50)

class WorkOrder(BaseModel):
    order_id: str
    device_id: str
    fault: str
    action: str
    result: str
    created_at: datetime

class MaintenanceHistoryOutput(BaseModel):
    orders: list[WorkOrder]
```

#### ⑤ `generate_report`（**写操作，位于审核之后/图外**）

```python
class GenerateReportInput(BaseModel):
    thread_id: str
    diagnosis: str
    root_causes: list[str]
    suggestions: list[str]
    citations: list[EvidenceItem]
    confidence: float
    risk_level: Literal["low","medium","high"]
    idempotency_key: str              # hash(thread_id + evidence_ids)，防重复报告

class GenerateReportOutput(BaseModel):
    report_id: str
    status: Literal["pending_review","published","degraded"]
    created_at: datetime
```

### 5.2 通用约定（错误码 / 超时 / 幂等 / 重试）

| 约定 | 规则 |
|---|---|
| **超时** | `retrieve_knowledge` 2s / `query_sensor` 3s / `query_graph` 3s / `get_maintenance_history` 2s / `generate_report` 5s |
| **错误码** | `E_TIMEOUT`/`E_NOT_FOUND`/`E_INVALID_ARG`/`E_UPSTREAM`/`E_CONFLICT`/`E_PERMISSION` |
| **重试** | 仅对 `E_TIMEOUT`/`E_UPSTREAM` 重试，最多 3 次，指数退避（0.5s/1s/2s）；`E_INVALID_ARG` 不重试 |
| **幂等** | 只读工具天然幂等；`generate_report` 以 `idempotency_key` 去重（PG 唯一索引） |
| **返回包裹** | 统一 `{ok, data|error, elapsed_ms, trace_id}` |

### 5.3 LangGraph State（**类型化 Pydantic**）

```python
class DiagnosisState(BaseModel):
    # 输入
    alarm: AlarmEvent
    thread_id: str
    # 运行态
    sensor_report: QuerySensorOutput | None = None
    evidence: list[EvidenceItem] = []
    graph_paths: list[GraphPath] = []
    work_orders: list[WorkOrder] = []
    diagnosis: str | None = None
    root_causes: list[str] = []
    suggestions: list[str] = []
    confidence: float = 0.0
    confidence_breakdown: dict = {}
    risk_level: Literal["low","medium","high"] = "low"
    # 控制
    retry_count: int = 0
    escalate_cloud: bool = False
    degrade_reason: str | None = None
    human_review: dict | None = None
    # 产出
    report_id: str | None = None
    errors: list[dict] = []
```

### 5.4 条件路由判定（**明确的 if-else 优先级顺序**）

```
按顺序判定（首个命中即生效）：
1. if 局部重试次数 ≥ 3 且仍失败      → 输出降级报告(degraded)，人工确认
2. elif confidence < 0.50            → 降级：输出"初步判断，建议人工确认"，不自动出正式报告
3. elif confidence < 0.75            → 触发云端升级(escalate_cloud)；云端失败则按 2 处理
4. elif risk_level == "high"         → interrupt() 强制人工审核
5. else                              → 直接生成报告
```

### 5.5 REST 接口契约

| 方法 | 路径 | 说明 | 鉴权 |
|---|---|---|---|
| POST | `/api/auth/login` | 登录，返回 JWT | 公开 |
| GET | `/api/alarms?status=&page=&size=` | 告警列表（分页） | 三角色 |
| GET | `/api/reports/{id}` | 报告详情 | 三角色 |
| POST | `/api/reports/{id}/review` | 审核（`{action: approve\|reject, comment}`） | 审核角色 |
| POST | `/api/diagnose` | 手动发起诊断（对话式追问） | 工程师 |
| GET | `/api/knowledge/docs?page=` | 知识库文档列表 | 三角色 |
| POST | `/api/knowledge/docs` | 文档上传（准入审核） | 知识库管理员 |
| GET | `/api/graph/neighbors?entity=` | 图谱邻居（可视化） | 三角色 |
| GET | `/api/health` | 健康检查 | 公开 |

**统一响应**：`{code, message, data, trace_id}`；**统一错误码**同 §5.2。

### 5.6 Socket.IO 事件契约

| 事件名 | 方向 | 载荷 |
|---|---|---|
| `alarm:new` | Server→Client | `{alarm_id, device_id, metric, value, ts, severity}` |
| `diagnosis:progress` | Server→Client | `{thread_id, node, status, elapsed_ms}` |
| `diagnosis:done` | Server→Client | `{thread_id, report_id, confidence, risk_level}` |
| `review:required` | Server→Client | `{thread_id, report_preview, risk_level}` |
| `review:submit` | Client→Server | `{thread_id, action, comment}` |
| `chat:ask` | Client→Server | `{thread_id, question}` |

### 5.7 Redis Key 规范与 TTL

| Key 模式 | 用途 | TTL | `maxmemory-policy` |
|---|---|---|---|
| `ckpt:{thread_id}:*` | LangGraph checkpoint | **不设 TTL** | **noeviction** |
| `sess:{user_id}` | 会话上下文 | 24h | 可驱逐 |
| `dedup:alarm:{device_id}:{metric}` | 告警去重滑动窗口 | 5min | 可驱逐 |
| `cache:retrieve:{hash}` | 检索结果缓存 | 10min | 可驱逐 |
| `lock:review:{thread_id}` | 审核并发锁（SETNX） | 30s | — |
| `budget:cloud:{day}` | 云端预算计数 | 至当日 24:00 | — |

> **强约束**：checkpoint 类 key **禁止设 TTL**、**禁止 LRU/LFU 驱逐**（否则内存压力下静默丢状态）。实例级 `maxmemory-policy=noeviction`，并设内存上限告警。

---

## 六、关键机制设计

### 6.1 置信度机制（把 0.75 从"魔法数字"变为"可解释阈值"）

**复合置信度**（加权和，各项归一化到 0~1）：

```
confidence = 0.35 * retrieval_score      # Top-K 检索得分归一化均值
           + 0.20 * sensor_consistency   # 传感器异常与候选故障模式的一致性
           + 0.15 * graph_support         # 图谱是否存在支撑路径（有=1，无=0.3）
           + 0.30 * llm_self_score        # 推理模型自评（经温度缩放校准）
```

**校准方法**：

1. 在 50 条评测集上标注"正确/错误"，构造校准集；
2. 对 `llm_self_score` 施加**温度缩放**（Temperature Scaling）校准；
3. 计算 **ECE（Expected Calibration Error）**，目标 `ECE ≤ 0.10`；
4. 0.75 阈值依据："达到可自动生成正式报告所需精确率（≥85%）对应的校准后阈值"，而非拍脑袋。

**路由接入**：见 §5.4 优先级。

### 6.2 混合检索算法（含图谱融合规则）

```
Query → 查询改写(qwen2.5:7b)
  ├─ Dense: BGE-M3 → Milvus HNSW，Top-20
  ├─ Sparse: Milvus BM25 Function（jieba analyzer），Top-20
  └─ Graph: Neo4j Cypher ≤2 跳，路径 Top-5
        ↓
   RRF 融合（k=60）：doc_score = Σ 1/(k + rank_i)
        ↓
   BGE-reranker-v2-m3 重排 → Top-5
        ↓
   证据集（文档块 + 图谱路径，各自带来源）
```

**融合冲突裁定**：
- 文档证据与图谱路径**冲突**时 → **以文档证据为准**（文档有原文出处，可追溯），图谱路径标注为"待确认线索"；
- 二者**一致** → `graph_support = 1`，提升置信度；
- 图谱无路径 → `graph_support = 0.3`（不直接否决，仅降权）。

### 6.3 跨存储一致性（**补齐的功能性缺陷**）

采用 **Outbox + 对账** 双机制：

```
① 写入 PostgreSQL(document, status='pending')
② 后台 Worker 消费 → 写入 Milvus(向量) + Neo4j(三元组)
③ 全部成功 → document.status='indexed'；任一失败 → status='failed' + 入补偿队列
④ 补偿队列：指数退避重试，≥5 次 → 告警人工介入
⑤ 每日对账脚本：比对 PG / Milvus / Neo4j 的 doc_id 集合，输出差异报告
```

**权威源定义**：**PostgreSQL 为唯一权威源**；Milvus/Neo4j 为可重建索引。Redis 仅承载运行态。

### 6.4 工作流可靠性与审核生命周期

| 场景 | 策略 |
|---|---|
| **Checkpoint 存储** | 默认 Redis（第三方实现），**D6 复现已知缺陷后决策**：若存在阻塞缺陷 → 切 PostgreSQL checkpointer |
| **写操作位置** | `generate_report` **移出图内**，置于 `interrupt()` 审核之后；审核通过后由图外写库 |
| **幂等** | 写操作携带 `idempotency_key`，PG 唯一索引去重 |
| **审核超时** | 4h 未审 → 通知**备用审核人**；24h 未审 → 自动降级为"待人工确认"状态，流程不挂起 |
| **并发 resume** | `lock:review:{thread_id}` SETNX 锁，防双审核人产生重复报告 |
| **Redis 配置** | `maxmemory-policy=noeviction` + 不设 TTL + 内存上限告警 |
| **体积治理** | 审核完成即归档 checkpoint；按 thread 保留上限；监控 key 数 |
| **多实例** | P0 结论默认**单实例**；若需多实例，须先验证 checkpoint 并发安全 |

### 6.5 告警引擎（补齐的黑盒输入）

| 环节 | 设计 |
|---|---|
| 生成位置 | **应用层轮询**（初期）/ 流式计算（中期升级） |
| 阈值告警 | `振动RMS > N` / `温度 > N` 等确定性阈值 |
| 统计异常 | 滑动窗口 Z-Score（主）+ Isolation Forest（辅，需 ≥7 天基线） |
| 冷启动基线 | 设备首周运行数据建立基线；无基线时仅用阈值规则 |
| 去重 | Redis 滑动窗口 `dedup:alarm:{device}:{metric}`，5min 内同类告警合并 |
| 输出 | 标准 `AlarmEvent`，作为 LangGraph `DiagnosisState.alarm` 输入 |

---

## 七、安全设计（四道防线）

| 防线 | 措施 |
|---|---|
| **① 数据接入层** | 敏感数据本地闭环，不出厂；云端升级仅传脱敏摘要（可选开关） |
| **② Agent 层** | 工具**白名单**；高风险判定**不依赖 LLM**（确定性规则）；输入净化防 Prompt 注入 |
| **③ 报告层** | **引用强制**（无来源不出结论）；降级显式化（明确标注"初步判断"）；不提供"一键执行" |
| **④ 审核层** | 高风险关键词命中 → `interrupt()` 强制人工；职责分离（禁止提交者自审） |

### 7.1 补充安全措施（评审遗漏项）

| 编号 | 风险 | 措施 |
|---|---|---|
| R-M2 | Prompt 注入 | 输入净化 + 工具白名单 + 高风险判定用确定性规则 + 系统提示隔离 |
| R-M3 | 知识库投毒 | 文档**准入审核** + 来源可信度分级 + 版本留痕可回滚 |
| R-M4 | 密钥/成本失控 | 云端 API 密钥托管（环境变量/密钥管理）+ 速率限制 + **预算熔断**（`budget:cloud:{day}`） |
| — | 审计不可篡改 | PostgreSQL 采用**追加专用表 + 触发器禁止 UPDATE/DELETE**（或只读分区/外部 WORM） |

### 7.2 RBAC（含职责分离）

| 角色 | 权限 | 约束 |
|---|---|---|
| 工程师 | 查告警/报告、发起诊断、编辑知识库草稿 | **不能**自行审核自己的报告 |
| 审核员 | 审核报告、审批知识库 | 不能修改原始证据 |
| **知识库管理员**（新增） | 文档准入审核、版本发布 | 独立于工程与审核 |
| 系统管理员 | 用户/权限管理 | 不可查看敏感原始数据 |

---

## 八、风险登记册

> **统一字段**：风险 / 概率 / 影响 / 触发条件 / 应对 / 归属阶段 / 剩余风险。以下为 v1。

### 8.1 原有风险（补齐字段）

| 编号 | 风险 | 概率 | 影响 | 触发条件 | 应对 | 阶段 |
|---|---|---|---|---|---|---|
| R1 | 阶段定位不裁决 | 低 | 高 | — | 本定稿已完成（替代大纲 P0） | 已完成 |
| R6 | 中文分词器无效 | 中 | 高 | BM25 收益≈0 | 强制 jieba analyzer + 分词人工抽检 | 阶段四 |
| R8 | 连接器为商业授权 | **中** | 高 | 社区版无 SparkplugB | 首步确认；不通过即启降级（§3.6） | 阶段五 |
| R9 | Broker 选型改变内存预算 | 低 | 中 | 被迫用 EMQX | 按最重方案重算内存 | 阶段五 |
| R11 | checkpoint TTL/驱逐丢状态 | 中 | 高 | Redis 驱逐 | 不设 TTL + `noeviction` + 超时降级 | 阶段四/五 |
| R12 | 恢复后重复副作用 | 中 | 高 | 恢复重放 | 写操作移出图内 + 幂等键 | 阶段四/五 |
| R16 | 工期超载 | 中 | 中 | 单人排程过密 | 10 工作日 + "机器并行、人串行" | 阶段二/五 |

### 8.2 新增风险（评审遗漏，R-M 系列）

| 编号 | 风险 | 概率 | 影响 | 应对 | 阶段 |
|---|---|---|---|---|---|
| R-M1 | 多存储一致性（静默缺数据） | 中 | 高 | Outbox + 对账脚本（§6.3） | 阶段三/五 |
| R-M2 | Prompt 注入 | 中 | 高 | §7.1 | 阶段四 |
| R-M3 | 知识库投毒 | 低 | 高 | 准入审核 + 来源分级 | 阶段四 |
| R-M4 | 密钥/成本失控 | 中 | 中 | 密钥托管 + 限流 + 预算熔断 | 阶段四 |
| R-M5 | 审核生命周期（超时/死锁/并发） | 中 | 高 | §6.4 | 阶段四/五 |
| R-M6 | 中文分词器失效 | 中 | 高 | 同 R6 | 阶段四 |
| R-M7 | Windows/WSL2 平台约束 | 低 | 高 | `.wslconfig` + GPU 直通 + 端口重映射（§2.5/2.6） | 阶段一/三 |
| R-M8 | 评测集可信度 | 中 | 中 | 标注规范 + 双人标注 + Cohen's Kappa + 局限声明 | 阶段四 |
| R-M9 | 硬件资源不足 | 低 | 高 | 峰值 ≤ 75% 判据 + 降级映射表（§3.5） | 阶段三/六 |
| R-M10 | 开源依赖版本漂移 | 中 | 中 | 精确锁定 + 镜像 digest + 升级评估机制 | 阶段六 |

### 8.3 外部依赖（唯一不可控项）

| 外部依赖 | 说明 | 兜底 |
|---|---|---|
| 数据版权/隐私 | 手册版权、工单隐私 | **默认自编模拟数据**（主路线，非兜底） |
| TDengine 连接器授权 | 社区版 SparkplugB 可用性 | §3.6 降级路径 |
| 云端 API 可用性/成本 | 升级路径 | 离线降级：输出"初步判断，建议人工确认" |

---

## 九、实施路线图与里程碑

### 9.1 阶段总览（口径统一）

| 阶段 | 名称 | 相对占比 | 说明 |
|---|---|---|---|
| **Phase 0** | 技术验证与范围锁定 | 10 工作日（D1–D10） | 见 §9.2，本方案**替代**大纲 P0 |
| Phase 1 | 数据接入与知识库构建 | 10% | MinerU 解析、建库、三元组抽取 |
| Phase 2 | 混合检索实现 | 20% | 参数基线落地、检索指标达标 |
| Phase 3 | Agent 工作流实现 | 25% | LangGraph 编排、工具集成、置信度路由 |
| Phase 4 | 前端与集成 | 20% | 五页面、实时推送、审核界面 |
| Phase 5 | 评测与硬化 | 15% | RAGAS、Kappa、可观测性、备份恢复 |
| Phase 6 | 收敛与交付 | 10% | 文档、演示、停止条件核对 |

> 绝对工期以 Phase 0 的 10 天为标定单位；后续阶段按占比折算，**不设"无限期"**。

### 9.2 Phase 0 六阶段执行（D1–D10）

| 阶段 | 时间 | 核心任务 | 出口 |
|---|---|---|---|
| 一 决策冻结 | D0（0.5d） | 5 项开放问题闭环（本定稿已完成 Q1–Q5） | 定位/拆分/硬件参数表 |
| 二 方案修订 | D0–D1 | 固化为规范文本（本定稿即为成果） | 执行版方案 v2 |
| 三 基线建立 | D1 | 环境基线 + Schema v1 冻结 + 数据盘点 + 实验登记 | **M0.1** |
| 四 判据补全 | D1–D2 | 每项验证补齐 Pass/中间/No-Go | 门禁判据表定稿 |
| 五 主验证执行 | D2–D8 | V1/V2/V3/V5/V7/V4b 实测 | M0.2–M0.4 |
| 六 仲裁与门禁 | D8–D10 | 联合仲裁 + 版本锁定 + 门禁评审 | **M0.6** |

### 9.3 Phase 0 日级排期（自洽版）

| 天 | 主线任务 | 并行任务（低资源） | 当日出口 |
|---|---|---|---|
| **D1** | V4a 约束采集 + `.wslconfig` + 端口检查；**TDengine SparkplugB 授权首步确认** | V6 数据盘点；**工具 Schema v1 冻结** | 环境基线、数据来源清单、Schema v1、授权结论 |
| **D2–D3** | **V1**（独占 GPU）：2 模型 × 20 用例 × 3 次 + 云端 baseline | V7 评测集构建（标注，不占 GPU） | V1 报告 + 分工决策表 + Prompt v1 + 评测集 v1 |
| **D4–D5** | **V2 Step1+Step2**（纯 CPU）：版本/中文 analyzer/质量对比/压力档 | V3 Step1（Broker 选型 + 连接器） | 版本+analyzer 结论、参数基线表、检索对比结论 |
| **D5** | V2 Step3 决策 | V3 Step2/3（Schema 映射 + `query_sensor` 契约 + 告警链路） | 检索路线决策、时序接入决策 |
| **D6–D7** | **V5 Step1+Step2**：重启恢复 + 缺陷复现 + 幂等 + 并发 resume | V6 Step2 MVP 范围（文档） | checkpoint 报告、Redis 模板、checkpoint 决策 |
| **D8** | **V4b 全组件实测**：全组件运行态压测 | 联合决策仲裁 | 资源实测表、分组策略、替代清单 |
| **D9** | 版本锁定清单 + 风险登记册 v1 | 电梯演讲 + 停止条件 | 锁定清单、风险册、范围文档 |
| **D10** | **M0.6 门禁评审** | P1 移交物整理 | P0 报告合集 + P1 移交清单 |

### 9.4 验证项依赖（DAG 硬约束）

```
V4a（D1，一切前置）
  ├─► V1（工具调用）── 独占 GPU ──► 分工决策 ──► V5、P1、P2、P3
  ├─► V2（混合检索）── 纯 CPU ◄── 强依赖 ── V7（评测集）
  ├─► V3（时序接入）── 与 V1 并行
  └─► V5（checkpoint）── 低资源并行（确定性规则触发 interrupt，解耦 V1）

V4b（D8）◄── 强依赖 V2/V3 容器就绪 + V1 模型就绪
```

**不可违反顺序**：① 阶段一/三先于阶段五；② **V7 先于 V2 Step2**；③ **V4b 在 V2/V3 之后**；④ 判据先于对应 V 项。

### 9.5 里程碑

| 里程碑 | 内容 | 时间 | 通过条件 |
|---|---|---|---|
| M0.1 | 约束与基线锁定 | D1 | 环境基线、Schema v1、数据来源清单齐备 |
| M0.2 | V1 完成 | D3 | 分工决策表 + 指标数据（含云端基线） |
| M0.3 | V2 + V3 完成 | D5 | 检索路线、时序接入方案、告警路线确定 |
| M0.4 | V5 完成 | D7 | checkpoint 方案确定，已知缺陷均有应对 |
| M0.5 | V4b + V6 + V7 完成 | D9 | 资源实测、MVP 范围、评测集、版本锁定 |
| M0.6 | **P0 门禁评审** | D10 | §十一 判据全部通过 |

---

## 十、MVP 范围与停止条件

### 10.1 Must（必须闭环，端到端可演示）

| # | 能力 | 验收方式 |
|---|---|---|
| 1 | **告警产生** | 模拟 Sparkplug B 数据触发阈值告警 |
| 2 | **告警去重** | 5min 内同类告警合并为 1 条 |
| 3 | 传感器分析 | `query_sensor` 返回统计 + 异常标记 |
| 4 | 混合检索 | `retrieve_knowledge` Recall@5 ≥ 85% |
| 5 | 图谱检索 | `query_graph` 返回 ≥1 条支撑路径 |
| 6 | 诊断推理 | 输出根因 + 建议 + 置信度 |
| 7 | **证据引用强制** | 每条结论均有来源，无来源不出结论 |
| 8 | 报告生成 | 结构化报告落库 |
| 9 | **高风险审核** | 高风险命中 → 强制人工审核 |
| 10 | **业务表落库** | 报告 + 审核记录入 PostgreSQL |
| 11 | **审计日志** | 全操作追加记录，不可篡改 |
| 12 | **降级路径** | 低置信度显式标注"初步判断" |
| 13 | 前端展示 | 五类页面可用 |

### 10.2 Should / Could

| 级别 | 内容 |
|---|---|
| Should | 对话式追问、图谱可视化、Prometheus 指标面板 |
| Could | 多设备类型扩展、GraphRAG 多跳、模型微调 |

### 10.3 Won't（明确边界，区分"不做"与"预留接口"）

| 项 | 说明 |
|---|---|
| 多租户 | **不做** |
| 模型微调 | **不做**（预留 LoRA 接入点） |
| 复杂 GraphRAG 多跳 | **不做**（当前 ≤2 跳） |
| 移动端 | **不做** |
| 真实 Modbus/OPC UA 直连 | **不做**（预留"边缘网关转 MQTT"接口） |
| 自动执行维修动作 | **不做**（安全边界，永久 Won't） |

### 10.4 停止条件（**可判定**）

> 当且仅当以下三条**同时满足**，停止扩展范围，转入交付：
> 1. **Must 链 13 项端到端可演示**（一次完整跑通告警→报告→审核）；
> 2. **≥3 项量化指标达标**：`Recall@5 ≥ 85%` + `P95 检索 < 800ms` + 工具调用首次成功率 ≥ 90%；
> 3. **版本锁定清单 + 风险登记册定稿**。

---

## 十一、验收指标与门禁判据

### 11.1 量化指标

| 指标 | 目标 | 测量方式 |
|---|---|---|
| `Recall@5` | ≥ 85% | 50 条评测集 |
| `MRR` | ≥ 0.75 | 同上 |
| `NDCG@5` | 报告值 | 同上 |
| 引用正确率 | ≥ 90% | 人工抽检 |
| 幻觉率 | ≤ 10% | 人工 3 级评分 |
| `P95 检索延迟` | < 800ms | 探针 |
| `P95 端到端` | < 3s（本地命中路径口径） | 探针；云端升级路径单独统计 |
| 工具调用首次成功率 | ≥ 90% | V1 用例 |
| 审核覆盖率（高风险） | 100% | 审计日志 |
| 去重有效率 | 报告值 | 告警统计 |
| 置信度 ECE | ≤ 0.10 | 校准集 |

> **口径声明**：`P95 端到端 < 3s` 仅统计**本地命中路径**；云端升级路径单独统计并注明。所有指标基于**模拟数据的初步验证**，须显式声明局限。

### 11.2 Go / No-Go 门禁判据

| 验证项 | Pass | 中间区间处置 | No-Go → 备选 |
|---|---|---|---|
| **V1** | 首次成功率 ≥90% 且参数可解析率 ≥95% | 70–90%：约束解码 + few-shot 复测；仍不达标→"本地推理 + 云端工具调用" | 两模型均 <70% → 云端工具调用转正 |
| **V2** | 支持 jieba 中文 analyzer + 原生 BM25；Recall@5 不低于对照 | 质量接近→按内存约束决策 | BM25 需大量自研 → 切轻量路线 |
| **V3** | 连接器社区版可用且 Schema 映射正确 | 需自研解码器但 ≤2 天 → 有条件通过 | 商业授权/工程量不可控 → MQTT JSON 或自研消费者 |
| **V4** | 全组件峰值 ≤ 24GB（32×75%）且 GPU 可直通 | 超限 ≤10% → 分组启动 | 严重超限 → 启用 §3.5 降级并调整 MVP |
| **V5** | 重启状态完整、payload 正确、无重复副作用、无 TTL 丢状态 | 非阻塞缺陷 → 记录规避清单后采用 | 阻塞缺陷 → 切 PostgreSQL checkpointer |
| **V6/V7** | 数据合法可用、评测集可执行、Must 链完整可验收 | 需自编 → 模拟数据交付并标注局限 | 评测集不可执行 → 指标无法验证，需重做 |

> **纪律**：中间区间 **≠ 通过**，必须记录**具体处置动作与指标代价**。

---

## 十二、附录

### 12.1 Milvus v3.0.0 Collection 建表参考（含中文 analyzer）

```python
from pymilvus import MilvusClient, DataType, Function, FunctionType

schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
schema.add_field("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True)
schema.add_field("doc_id",   DataType.VARCHAR, max_length=64)
schema.add_field("parent_id",DataType.VARCHAR, max_length=64)   # Parent-Child
schema.add_field("content",  DataType.VARCHAR, max_length=4096, enable_analyzer=True,
                 analyzer_params={"tokenizer": "jieba"})          # ★ 中文分词
schema.add_field("dense",    DataType.FLOAT_VECTOR, dim=1024)     # BGE-M3
schema.add_field("sparse",   DataType.SPARSE_FLOAT_VECTOR)        # 服务端 BM25 输出

# ★ 服务端 BM25 Function：原始文本 → 稀疏向量，自动维护 DF/IDF
schema.add_function(Function(
    name="bm25_fn",
    input_field_names=["content"],
    output_field_names=["sparse"],
    function_type=FunctionType.BM25,
))

index_params = MilvusClient.prepare_index_params()
index_params.add_index("dense",  index_type="HNSW", metric_type="COSINE",
                       params={"M": 16, "efConstruction": 200})
index_params.add_index("sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25",
                       params={"inverted_index_algo": "DAAT_MAXSCORE",
                               "bm25_k1": 1.2, "bm25_b": 0.75})
```

### 12.2 实验登记模板（所有验证报告强制使用）

| 字段 | 示例 |
|---|---|
| 实验 ID / 日期 | V1-20260922-01 |
| 模型 digest | `qwen2.5:7b@845dbda0ea48` |
| 推理引擎版本 | `ollama --version` |
| `num_ctx` / `temperature` / seed | 8192 / 0.2 / 42 |
| Prompt 版本 | `tool_call_prompt_v1` |
| 镜像 digest | `milvusdb/milvus@sha256:...` |
| 代码 commit | `abc1234` |
| 环境基线版本 | `env-baseline-v1` |

### 12.3 Docker Compose 编排要点

- 所有服务加 `healthcheck` + `depends_on: condition: service_healthy`；
- 各服务设 `mem_limit` / `cpus`（防单服务拖垮整机）；
- Milvus 依赖 etcd + MinIO（本机已就绪）；
- `redis` 命令：`redis-server --maxmemory 1gb --maxmemory-policy noeviction --appendonly yes`；
- 端口冲突项（5432→5433、3000→3001）在 Compose 中重映射并统一记录；
- 数据卷：Milvus/MinIO/PG/Neo4j/TDengine 均挂载命名卷，纳入备份策略；
- **入口网关**：Phase 4+ 增加 `nginx`（或 `caddy`）服务，统一入口 + WebSocket 透传 + HTTPS（见 §3.11）。

### 12.4 备份与恢复策略

| 对象 | 方式 | 频率 |
|---|---|---|
| PostgreSQL（权威源） | `pg_dump` / WAL 归档 | 每日全量 |
| Milvus / Neo4j 卷 | 卷快照 | 每周 |
| Neo4j | `neo4j-admin dump` | 每周 |
| 原始文档语料 | 冷备 | 变更即备 |

### 12.5 可观测性

| 维度 | 工具 |
|---|---|
| Trace | Langfuse |
| 指标 | Prometheus + Grafana（含 checkpoint key 数、云端预算、各存储一致性差异） |
| 日志 | 结构化日志聚合 |
| 告警 | Redis 内存、GPU 显存、对账差异、审核超时 |

### 12.6 依赖清单（锁定后补 digest）

```
# Python（开发期，精确锁定）
pymilvus==<锁定>
langgraph==<锁定>
langchain-core==<锁定>
fastapi / uvicorn / python-socketio / sqlalchemy / psycopg[binary]
neo4j / taospy / redis / pydantic / ragas / langfuse
# 前端
next / react / tailwindcss / socket.io-client / react-force-graph
# 基础设施镜像
milvusdb/milvus:v3.0.0
quay.io/coreos/etcd:v3.5.25
minio/minio:RELEASE.2024-12-18T13-15-...
postgres:18
redis:8
neo4j:5.x
tdengine/tdengine:3.3.6.0
eclipse-mosquitto:2
nginx:alpine          # Phase 4+ 入口网关（见 §3.11）
```

---

## 附：本定稿 vs 旧文档 冲突消解速查

| 议题 | 旧文档（冲突） | **本定稿（唯一口径）** |
|---|---|---|
| 阶段定义 | V4.0"不设周期" / 大纲 P0 / Phase0 P0 并存 | **本方案替代大纲 P0**；工期 = 10 工作日 + 阶段占比 |
| 本地 LLM | 仅 `deepseek-r1:7b` 承担工具调用 | **`qwen2.5:7b` 工具调用 + `deepseek-r1:7b` 诊断推理** 双模型 |
| Milvus 版本 | 3.0.0 vs ≥2.5 | **v3.0.0**（本机镜像） |
| BM25 路径 | 服务端/客户端混用 | **服务端 `FunctionType.BM25`** + jieba analyzer |
| PostgreSQL | 16 | **18**（本机镜像） |
| Redis | 7 | **8**（本机镜像）+ `noeviction` |
| Sparkplug B | "TDengine 已提供" | **待验证假设**（taosX 社区版授权待确认） |
| 硬件判据 | 物理内存容量 | **峰值 ≤ 物理内存 × 75%（即 24GB）** |
| 置信度 0.75 | 无来源 | **复合公式 + 温度缩放 + ECE ≤ 0.10** |
| 一致性 | 仅 PG↔Redis | **Outbox + 每日对账（PG 为权威源）** |
| MVP/停止条件 | 无 | **Must 13 项 + 三条可判定停止条件** |
| 部署形态 | 未明确 | **混合架构、本地优先**（云端仅脱敏兜底） |
| CUDA 用途 | 未说明 | **推理刚需 / 微调可选 / 训练不可行** |
| 数据库 | 仅提 PG16（且本机有 MongoDB） | **PostgreSQL 18 权威库；不引入 MongoDB** |
| 入口网关 | 未提及 | **Phase 4+ 引入 Nginx**（反代 + WebSocket 透传 + SSL） |
| 版本治理 | V4.0 自称最终却已被修订 | **本文件为唯一有效版本（V5.0 定稿）** |

---

> **一句话总结**：本方案在**本机实测配置（32GB/RTX4060 8GB/954GB）**约束下，完成了**版本收敛、模型分工、置信度定义、接口契约化、一致性补偿、审核生命周期、MVP 与停止条件**七项"收敛型"补齐。技术设计已就绪，可直接进入 Phase 0 D1 执行。
