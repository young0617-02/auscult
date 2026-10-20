# 云侧工业 IoT 诊断 Agent 系统（auscult）

> **一句话定位**：一个跑在本地、以告警为入口、会自己查资料并给出**带出处**维修建议的工业设备诊断 Agent —— **数据不出厂，结论可追溯**。
> **主场景**：离心泵驱动端轴承振动异常诊断
> **当前阶段**：**Phase 0–6 全部完成** —— `M0.6` 门禁 2026-10-08 放行、`M5.4` 2026-10-10 达成、**`M6.4` 正式收口 2026-10-10**（停止条件三条满足、交付包已封版）；此后**只维护、不扩范围**（后续路线见 `docs/p6-gate-closure-2026-10-10.md` §六）
> **唯一事实源**：环境 → `env/env-baseline-v2.md` ｜ 版本与镜像 digest → `docs/prj-ledger-version-lock.md` ｜ 文档命名 → `docs/prj-spec-document-standard.md` ｜ **阶段状态与收口凭据 → `docs/p6-gate-closure-2026-10-10.md`**

## 一、这是什么

把「**时序遥测 + 设备知识 + 图谱关系 + 维修历史**」四类证据汇聚给 LLM，自动完成
**告警 → 诊断推理 → 证据引用 → 报告生成 → 高风险人工审核** 的闭环。

**核心设计取向**（详见 `docs/p0-spec-scope-mvp.md`）：

- **证据驱动**：每条结论必须带 `EvidenceItem`，**无来源不出结论**；
- **本地优先**：LLM 推理走宿主 Ollama（`127.0.0.1:11434`），容器只承载 DB / 存储；
- **判据前置**：任何验证项开跑前，Pass / 中间区间 / No-Go 必须先定稿；
- **降级必带代价**：替代方案必须标注对 `Recall@5` 与 `P95` 的影响；
- **不编造数字**：未实测项写 `【待实测填入】`；
- **可复现**：组件 / 模型一律 digest 锁定，模拟数据固定 seed + `synthetic: true`。

## 二、系统架构

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│  入口层  Nginx :9763（反向代理 + WebSocket 透传 + SSL 预留）   │
├─────────────────────────────────────────────────────────────┤
│  表现层  Next.js 16 + shadcn/ui + Socket.IO 实时推送          │
│  页面：登录 / 告警看板 / 诊断对话 / 报告详情+审核 / 知识库 / 图谱 / 审计 │
├─────────────────────────────────────────────────────────────┤
│  编排层  LangGraph（StateGraph + Checkpointer）              │
│  节点：告警解析 → 传感器分析 → 知识检索 → 诊断推理 → 报告生成 → 人工审核 │
│  工具：retrieve_knowledge / query_sensor / query_graph /      │
│        get_maintenance_history / generate_report             │
├─────────────────────────────────────────────────────────────┤
│  推理层  LLM 适配层（本地 Ollama + 云端脱敏兜底）              │
│  ├─ 本地：qwen2.5:7b（工具调用） / deepseek-r1:7b（诊断推理）  │
│  └─ 云端兜底：置信度 ∈ [0.50, 0.75) 时升级（脱敏 + 预算 340/天）│
├─────────────────────────────────────────────────────────────┤
│  检索层  混合检索：Dense(BGE-M3) + Sparse(BM25) + RRF         │
│  图谱检索：Neo4j Cypher 多跳（≤2 跳）                         │
├─────────────────────────────────────────────────────────────┤
│  数据层  Milvus v3.0.0 / Neo4j 5 / TDengine 3.3 / PG 18 / Redis 8 │
├─────────────────────────────────────────────────────────────┤
│  接入层  MQTT(Mosquitto) + Sparkplug B 自研解码器 → TDengine   │
│         告警引擎（阈值 + 滑动窗口）→ 去重 → LangGraph 触发      │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 七大功能模块（边界清晰、依赖单向）

| 模块 | 职责 | 关键产出 |
|---|---|---|
| 2.1 IoT 接入与告警 | MQTT/Sparkplug B 接入、时序写入、告警生成、Redis 去重 | 告警事件流 |
| 2.2 知识库管理 | MinerU 解析、Parent-Child 分块、三存储写入、版本管理 | 文档块 / 三元组 / 元数据 |
| 2.3 混合检索 | 查询改写、Dense+BM25 并行、RRF、证据组装、图谱融合 | 证据集（含来源） |
| 2.4 Agent 编排 | State 管理、节点路由、工具调用、置信度路由 | 决策轨迹 |
| 2.5 报告与审核 | 结构化报告、高风险强制审核、降级显式化 | 报告 + 审计 |
| 2.6 前端交互 | 七类页面、对话式追问、实时推送 | 用户界面 |
| 2.7 权限与审计 | RBAC（三角色 + 知识库管理员）、全操作审计、职责分离 | 审计日志 |

### 2.3 三条数据流

**① 离线知识构建流**

```
PDF/工单/规程 → MinerU 解析 → Parent-Child 分块 → 元数据标注
   → ①写入 Milvus(稠密+稀疏) ②写入 Neo4j(三元组) ③写入 PostgreSQL(元数据/版本)
   → 【Outbox 对账】确认三写一致
```

**② 在线诊断请求流**

```
MQTT 告警 → 去重(Redis 滑动窗口) → LangGraph 触发
   （P7：自动触发默认关闭——AUSCULT_AUTO_TRIGGER=1 启用后由 app/api/auto_trigger.py
     轮询 alerts 表发起；未启用时经人工 POST /api/diagnose）
   → 告警解析 → 传感器分析(query_sensor) → 知识检索(retrieve_knowledge+query_graph)
   → 历史工单(get_maintenance_history) → 诊断推理(置信度计算)
   → [置信度<0.75 → 云端升级 / 重检索] → 报告生成(generate_report)
   → [高风险 → interrupt 人工审核] → Socket.IO 推送 → 审计落库
```

**③ 业务数据管理流**

```
登录(RBAC) → 告警/报告/知识库查询 → 审核(通过/驳回+意见) → 知识库更新(版本升版) → 审计
```

### 2.4 条件路由（五档优先级，首个命中生效）

| 优先级 | 条件 | 目标节点 |
|---|---|---|
| 1 | `retry_count >= 3` | degrade |
| 2 | `confidence < 0.50` | degrade |
| 3 | `confidence < 0.75` | escalate_cloud |
| 4 | `risk_level == "high"` | human_review（interrupt） |
| 5 | else | finalize |

### 2.5 数据存储归属（一表定责）

| 数据 | 存储 | 权威源 | 说明 |
|---|---|---|---|
| 传感器时序 | TDengine | ✅ | 原始遥测 |
| 告警事件 | TDengine(生成) + PostgreSQL(状态) | PostgreSQL | 状态流转 |
| 文档块 + 向量 | Milvus | ✅ | 检索主体 |
| 三元组 | Neo4j | ✅ | 图谱 |
| 文档元数据/版本 | PostgreSQL | ✅ | `knowledge_versions` |
| 报告 | PostgreSQL | ✅ | `reports` 表 |
| 工作流状态 | PostgreSQL（checkpointer，唯一权威） | **PostgreSQL** | V5 checkpoint；P7 起 Redis db 1 只读缓存为非权威加速层（`docs/p7-design-redis-cache-layer-2026-10-16.md`） |
| 审核 / 审计记录 | PostgreSQL | ✅ | `audit_logs`（append-only 触发器） |
| 会话上下文 | Redis（TTL 24h，db 1 只读缓存）+ PG（权威） | — | 非权威，可重建；P7 落地（原口径为漂移声明，代码实现在 2026-10-16 补齐） |

## 三、阶段状态与验收指标

### 3.1 阶段状态

| 阶段 | 内容 | 里程碑 | 状态 |
|---|---|---|---|
| Phase 0 | 技术验证与范围锁定 | `M0.1`–`M0.6` | ✅ 全达成（`M0.6` 2026-10-08 放行） |
| Phase 1 | 数据接入与知识库构建 | — | ✅ 已完成 |
| Phase 2 | 混合检索 | `M2.1`–`M2.4` | ✅ 全达成（`P95` 86.1 ms） |
| Phase 3 | Agent 工作流实现 | `M3.1`–`M3.5` | ✅ 全达成 |
| Phase 4 | 前端与集成 | `M4.1`–`M4.4` | ✅ 全达成（Playwright E2E 9/9） |
| Phase 5 | 评测与硬化 | `M5.1`–`M5.4` | ✅ 全达成（停止条件三条满足） |
| **Phase 6** | **收敛与交付** | `M6.1`–`M6.4` | ✅ **全达成（`M6.4` 2026-10-10 收口）** |

### 3.2 Phase 5 全量指标终值（Phase 6 收口输入）

| 指标 | 目标 | 终值 | 判定 |
|---|---|---|---|
| `Recall@5` | ≥85% | **1.0** | ✅ |
| `MRR` | ≥0.75 | **0.7986** | ✅ |
| 引用正确率 | ≥90% | 0.9861（`context_precision` 代理口径） | ✅* |
| 幻觉率 | ≤10% | **0.0%** | ✅ |
| 工具调用首次成功率 | ≥90% | **1.0**（12/12） | ✅ |
| `P95` 检索 | <800 ms | **159.4 ms**（检索 API 口径 86 ms） | ✅ |
| `P95` 端到端（含生成） | <3 s | 9,248.8 ms（`P50` 1,539.6 ms 达标） | ❌ 瓶颈=生成输出长度，优化路径见 `docs/p5-handover-p6.md` §五 |
| 置信度 `ECE` | ≤0.10 | 0.0（零方差，巧合性校准，已声明） | ✅* |
| 高风险审核覆盖率 | 100% | **100%**（纯规则强制 `always_interrupt_when_high`） | ✅ |
| Cohen's Kappa | ≥0.7 | **0.8344** | ✅ |
| 资源峰值 | ≤24 GB | **20.73 GB**（压测窗口含监控栈 + TDengine） | ✅ |

> 权威来源：`docs/p5-handover-p6.md` §一/§二、`reports/p5-eval.md`、`reports/p5-perf.md`、`docs/prj-ledger-version-lock.md`。
> **总声明**：以上为**模拟数据**下的本地验证初步结论，非生产级评测；golden 50 题待扩语料后重评。

## 四、快速开始

### 4.1 前置条件

| 项 | 要求 |
|---|---|
| OS | Windows 10/11 + WSL2（`.wslconfig`：内存 20 GB / 10 vCPU / swap 8 GB，见 `env/wslconfig.proposed`） |
| Python | **3.12**（仓库根 `.python-version` 锚定）+ `uv` |
| Node.js | 24.x + `pnpm` 11.x（`client/package.json` `packageManager` 锚定） |
| Ollama | 0.34.2（宿主进程，`127.0.0.1:11434`；模型 `qwen2.5:7b` + `deepseek-r1:7b`） |
| Docker | Docker Desktop ≥29.6（Compose v5.3.1） |

### 4.2 安装依赖

```powershell
uv venv --python 3.12                     # 建 .venv；解释器锚定 = 仓库根 .python-version（3.12）
uv pip install -r requirements.txt        # 安装/补齐依赖
# ⛔ 勿直接 uv pip sync requirements.txt —— sync 不解析传递依赖，会移除大量包
#     （须先用 uv pip compile 生成 lock，Phase 6 D6/D7 方案 C 处理）
# 之后一律用 .venv\Scripts\python.exe 运行（其即 uv venv 产物，与 uv run python 等价）
```

### 4.3 启动基础设施

```powershell
# 基础组件：Milvus / PostgreSQL / Redis / Neo4j（端口纪律见 env/ports.md）
docker compose -f docker/compose.base.yml up -d
# 时序两件套（可选，仅 V3 链路需要；与 compose.base.yml 端口冲突，不得同时启动）
docker compose -f docker/compose.ingest.yml up -d
```

### 4.4 初始化数据库

```powershell
# PG（auscult_v2 @127.0.0.1:5433，root/123456）按序号执行迁移
# db/migrations/：0001_init / 0003_reports / 0004_users / 0005_knowledge_admission / 0006_audit_logs
# RBAC 种子账号（eng_dev / rev_dev / kb_dev / sys_dev）
.venv\Scripts\python.exe scripts/seed_users.py
```

> ✅ 一键初始化脚本（幂等）已落地为 `deploy/init.ps1`（见 §五）；本节手动迁移路径保留，用于排障与分步核对。

### 4.5 启动后端

```powershell
# REST + Socket.IO（同一 ASGI 应用；/socket.io 由 ASGIApp 接管）
.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000
#   · 健康检查 http://127.0.0.1:8000/api/health
#   · Prometheus 抓取端点 http://127.0.0.1:8000/metrics
#   · 需经 Nginx 容器回源时将 --host 改为 0.0.0.0
```

> **P7 诊断 Agent 化（2026-10-19，可选开关，默认关闭=既有确定性形态）**：
> 统一 LLM 客户端 `app/llm/`（本地 Ollama / 云端双传输）+ Agent 循环 `app/graph/nodes/agent_diagnose.py`
> （LLM 自主调只读工具取证，`max_steps` 封顶，写操作护栏，失败走既有重试/降级路由）。
> 测试开发期云端承载：`$env:AUSCULT_DIAGNOSIS_MODE="agent"; $env:AUSCULT_LLM_BACKEND="cloud"`；
> 后期回本地（换硬件 + qwen3:32b）：`AUSCULT_LLM_BACKEND=local` + `AUSCULT_LOCAL_MODEL_AGENT/DIAGNOSE=qwen3:32b`。
> 设计与切换 Runbook、判据闸门、未决项 U1–U4：`docs/p7-design-agent-diagnosis-2026-10-19.md`。
> **判据闸门结论（2026-10-20 实测，请勿误读为"Agent 已上线"）**：三版实测，**当前对外只引用路径 C 版** ——
> `EXP-P7-GATE`（5 工具面）：多轮 77.8% 中间区间；`EXP-P7-GATE2`（同面 + 禁调口径）：多轮 66.7% **No-Go**
> （根因 = 判据工具面含写操作，登记 **`ISS-052`**，两版均**不得**再对外引用）；
> **`EXP-P7-GATE3`（路径 C：只读 4 工具面 = 产品口径）**：首成 **67/75 = 89.33%**，参数校验 100% /
> 多轮 100% / 拒止 100% / 澄清 100% 四档 Pass，单工具 83.3%、多工具 58.3% 为中间区间，
> **无一档 No-Go → 整体中间区间，按纪律仍不切默认**（`AUSCULT_DIAGNOSIS_MODE` 默认 `deterministic`）。
> 三版**不可横向比较**（被测工具面不同）；**路径 D 首版已跑**（`EXP-P7-GATE-D`：产品 Agent 本体 +
> 多轮循环）：首成 **62/75 = 82.67%**，四档工具类中间区间、无一档 No-Go，13 个失败全是参数值错 ——
> 但该版含三项口径偏离（打桩漏装 / `max_steps=2` / 预算超 5 次）且暴露**收口契约与问答型用例错配**，
> **故仍不作切默认凭据**（详见该实验 §3.4/§3.5）。下一步 = 修 harness + `max_steps=4` 重跑
> （`docs/p7-design-gate-product-agent-2026-10-20.md` §七之二）；U2 已判决「异步诊断 + 实时进度」
> （`docs/p7-decision-async-diagnosis-2026-10-20.md`）。

### 4.6 启动前端

```powershell
cd client
pnpm install
pnpm dev          # http://localhost:3000
```

### 4.7 Nginx 单入口（可选）

```powershell
docker compose -f docker/compose.nginx.yml up -d      # http://127.0.0.1:9763
# 反代：/ → Next.js:3000 ｜ /api → FastAPI:8000 ｜ /socket.io → WS 透传
```

### 4.8 离线自检与回归

```powershell
# 自检（不联网、不需容器）：scripts/ 下 36 个脚本含 --selftest，全部应 exit 0
.venv\Scripts\python.exe scripts/llm_adapter.py --selftest
.venv\Scripts\python.exe scripts/gate_rules.py --selftest
# 全量回归（离线、秒级；防「已修复缺陷复发」，见 docs/prj-ledger-known-issues.md）
.venv\Scripts\python.exe -m pytest tests/ -q
```

## 五、一键启动（交付包，Phase 6 D6–D7 已落地）

> ✅ **已落地（2026-10-10，`M6.2` 达成）**：实测 8 容器 up、7 个基建 healthy、`deploy/smoke.ps1` **6/6 PASS**。

```powershell
deploy\up.ps1        # 一键启动：compose 全服务（healthcheck + 依赖顺序 + 资源限额）+ 等待健康
                    #   注：2026-10-14 起默认含 TDengine profile（诊断主场景 analyze_sensor 依赖时序数据）
deploy\init.ps1      # 一键初始化：迁表 / 建库 / 建图谱 / 导入语料与演示数据（幂等）
deploy\smoke.ps1     # 一键冒烟：健康检查 + Playwright E2E（F1–F11 子集）
deploy\down.ps1      # 一键停止（可选 -v 清卷）
```

- 编排：`deploy/docker-compose.yml`（含 `.env.example`、镜像 **digest** 清单，禁止裸 tag）；
- 版本：沿用 `docs/prj-ledger-version-lock.md`（不另建重复文件）；
- 判据：**干净环境**（全新 clone + 空数据卷 + 仅按交付文档操作）一键启动并冒烟通过（`M6.2`）—— **已达成**；

### 时序样本数据（TDengine，`init.ps1` 之后的独立步骤）

`init.ps1` 只建 **schema**（`iot` 库 + 超级表），**不灌样本数据** —— 时序数据走生产形态的真实链路（MQTT → 自研 Sparkplug B 解码器 → TDengine），需单独执行：

```powershell
# 1) 常驻解码器（本地直跑，订阅 Mosquitto -> 写 TDengine REST 6041；另开一个终端）
.venv\Scripts\python.exe scripts\self_decoder.py --prj-spec-schema-mapping configs\decoder_schema_mapping.json --mqtt-host 127.0.0.1 --td-host 127.0.0.1
# 2) 批量造数（3 设备 x 1h x 1Hz，PUMP-A 注入异常段；固定 seed 可复现）
.venv\Scripts\python.exe scripts\gen_sparkplug.py
```

- 实测（2026-10-14）：**10800 行**落库（3600 x 3 设备），PUMP-A `vib_rms` 峰值 **4.855 mm/s**（越 ISO 10816 C 区上界 4.5，**2 个** 5min 超限窗口），PUMP-B/C 正常态 ~1.30 mm/s；
- 验证：`scripts\verify_query_sensor.py`（3 设备 x 13 窗口 exit 0、`P95~24.2ms`，`ISS-047` 修复后复跑通过）；
- 复灌 = 重跑上面两步（DBIRTH 建表幂等、DDATA 按 ts 主键去重）；不需要时关闭解码器终端即可，已落库数据不受影响。
- ⚠️ **落库不满自查（ISS-050，2026-10-20）**：单轮灌数 10804 报文应全部落库（`select count(*) from iot.st_pump_metrics` 增量核对）。若增量明显偏小（历史缺陷：QoS 0 订阅下 broker 对慢订阅者不排队、静默丢消息），确认解码器为 **QoS 1 订阅**（`scripts/self_decoder.py` 已修）且 `configs/mosquitto.conf` 的 `max_queued_messages=20000` 已生效（改后需 `docker restart auscult-mosquitto`）；解码器落库速率上限 ≈48 行/s（逐行 REST 写），批量 INSERT 优化列 P1。

## 六、目录导航

```
auscult/
├─ README.md            本文件（项目入口）
├─ CHANGELOG.md         变更日志（以验证项 / 里程碑为粒度）
├─ requirements.txt     Python 依赖锁（版本唯一来源 docs/prj-ledger-version-lock.md）
├─ .python-version      解释器锚定（3.12）
├─ app/                 后端 FastAPI 应用（api / graph / tools / report / review / router / security / observability / cache[P7] / llm[P7] / agent[P7]）
├─ client/              前端 Next.js 16 + shadcn/ui + Socket.IO（app/(auth)login、app/(main){alarms,diagnosis,reports,knowledge,graph,audit}）
├─ db/migrations/       PostgreSQL 迁移（0001 / 0003 / 0004 / 0005 / 0006 / 0007[P7 自动触发]）
├─ deploy/              ★ 交付包：docker-compose.yml + up/init/smoke/down.ps1 + .env.example + images.digest.md
├─ demo/                ★ 演示：scenario.md（主场景 S1 + 备用 S2–S4）/ data/alarms.json / recording/rehearsal-log.md
├─ docker/              compose.base / compose.ingest / compose.v2 / compose.nginx / compose.monitoring / compose.v4b-iso + Dockerfile.decoder
├─ monitoring/          Prometheus + Grafana（临时件：压测期启动、测后销毁）
├─ configs/             alarm_rules / risk_rules / retrieval / logging / mosquitto / redis / decoder_schema_mapping / triple_schema
├─ scripts/             86 个 Python 执行器（39 含 --selftest，P7 增 embedding_cache / smoke_agent_cloud 云端 Agent 实跑冒烟）+ 2 个 PowerShell 运维脚本
├─ tests/               回归测试（pytest；含 tests/e2e/ 的免 Playwright 场景级 E2E）
├─ schemas/             tools_v1(FROZEN) … tools_v5 + tools_p2_retrieve（**当前基线 = tools_v4**）
├─ prompts/             工具调用 / 拒止 / R-4 提示词（v4 为当前最优候选；v2 含泄漏禁用）
├─ evals/               用例集：golden_set_v1(50) / v1_cases(20) / v2_cases / v3_cases / r4_cases / 对抗集 / 迁移集 / m2_acc_set
├─ experiments/         1/2/3/4b/5/r4 原始实测数据（`raw/` 只增不改）+ EXP-*.md 实验登记
├─ docs/                治理与规范（判据 / 台账 / 版本锁 / 范围 / 移交 / 决策 / 模板 / 命名规范 / 命名映射表）
│                 ★ Phase 6 D1–D5 收口新增：prj-design-architecture（架构）/ prj-spec-{deployment,operations}（部署运维）
│                            / prj-spec-{api,data-dictionary}（API 与数据字典）/ prj-decision-adr-001..009（架构决策记录）
│                 ★ Phase 6 D10 收口新增：p6-gate-closure-2026-10-10.md（**阶段状态唯一凭据**）
│                 ★ 2026-10-15 新增：prj-design-requirements-main-flow.md（**需求主流程**，跨阶段全景）
│                 ★ 2026-10-16 新增：prj-guide-user-manual.md（**用户操作手册**，实跑验证 + 截图）
│                            / p7-design-redis-cache-layer-2026-10-16.md（P7：Redis 缓存层 + 告警自动触发）
│                 └─ images/manual/   用户手册截图资产（01-login … 08b-audit，2026-10-16 实跑采集）
├─ plan/                阶段计划（Phase 0–6）与设计
├─ reports/             实测报告 / 审计 / 裁决 / 总结 + reports/daily/
├─ env/                 环境基线 v2（+v1 留档）/ hardware.json / ports.md / cloud.json（含 key，已 gitignore）
├─ archive/             非项目技术产物归档（personal/，见 archive/README.md）
├─ blobs/ chunks/ parsed/   P1 知识库中间产物（MinerU 解析 / 分块）
├─ backups/             PG / Neo4j / Milvus 冷备产物（不入 git）
└─ logs/                运行日志
```

> **命名规则与旧名→新名映射的唯一入口** = `docs/prj-spec-document-standard.md`；
> 索引与逐项状态见 `reports/README.md` §一。
> **不可改写区**（文档整理不得触碰）：`prompts/`、`schemas/`、`evals/`、`configs/`、`docker/`、`protos/`、`experiments/**/raw/`、`env/cloud.json`。

## 七、常用入口

| 目的 | 命令 |
|---|---|
| 回归测试（改代码后必跑） | `.venv\Scripts\python.exe -m pytest tests/ -q` |
| **一键启动全栈**（交付包） | `deploy\up.ps1`（compose 全服务 + 等待 healthy） |
| **一键初始化**（幂等） | `deploy\init.ps1`（迁表 / 建库 / 建图谱 / 导入语料与演示数据） |
| **一键冒烟**（`M6.2` 判据） | `deploy\smoke.ps1` |
| 一键停止 | `deploy\down.ps1`（可选 `-v` 清卷） |
| 后端 API + Socket.IO | `.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000` |
| 前端开发服务器 | `cd client; pnpm dev` |
| V1 工具调用评测 | `.venv\Scripts\python.exe scripts/run_v1.py --constrain --tag constrained-decoding ...` |
| V1 判分 | `.venv\Scripts\python.exe scripts/judge_tools.py --raw experiments/v1/raw/EXP-V1-003.jsonl --out experiments/v1/summary-EXP-V1-003.csv` |
| 云端上界校准 | `.venv\Scripts\python.exe scripts/run_cloud_baseline.py --constrain` |
| V2 混合检索对比 | `.venv\Scripts\python.exe scripts/run_v2.py --routes milvus,pgvector --dsn postgresql://root:123456@127.0.0.1:5433/auscult_v2` |
| V5 checkpoint 验证 | `.venv\Scripts\python.exe scripts/run_v5.py --step t5.3 --resume <thread_id> --checkpointer postgres` |
| R-4 证据归纳执行 / 判分 | `.venv\Scripts\python.exe scripts/run_r4.py` ／ `scripts/judge_r4.py --raw experiments/r4/raw/EXP-R4-001.jsonl --out experiments/r4/summary-EXP-R4-001.csv` |
| **M0.2 权威入口**：端到端（规则门 → 云端工具调用） | `.venv\Scripts\python.exe scripts/run_e2e.py --cases evals/v1_cases.jsonl --cases evals/v1_refusal_transfer_v1.jsonl --repeat 3 --out <raw.jsonl>` |
| 同日多轮聚合裁决（§3.1.3） | `.venv\Scripts\python.exe scripts/aggregate_runs.py --raw R1.jsonl --raw R2.jsonl --raw R3.jsonl` |
| 纯规则前置门（零 LLM 调用） | `.venv\Scripts\python.exe scripts/gate_rules.py --selftest`（由 `run_e2e.py` 内置调用） |
| 本地 7B 前置门（R-1 原方案） | `.venv\Scripts\python.exe scripts/refusal_gate.py --models qwen2.5:7b --cases evals/v1_cases.jsonl --repeat 3 --out experiments/v1/raw/EXP-M02-026.jsonl` |
| V3 时序链路（模拟器为验证工具，不进 compose） | `.venv\Scripts\python.exe scripts/spb_simulator.py --scenario birth,new_metric,rebirth,offline` → `scripts/run_v3_alert.py --threshold 4.5 --window-min 5 --must-windows 3` |
| 压测（Locust） | `.venv\Scripts\python.exe -m locust -f scripts/locustfile.py --host http://127.0.0.1:8000 --headless -u 10 -r 5 --run-time 3m` |

## 八、迭代纪律（改动前必读）

1. **Schema 冻结**：`schemas/tools_v1.json` 的 `change_policy` 要求任何修改必须升版，否则 V1 全部结论作废；同时同步 `docs/prj-ledger-version-lock.md`。
2. **组件 / 模型**：只写 digest，**禁止裸 tag 与 `latest`**；变更即升版并重登 digest。
3. **实验登记**：按 `docs/prj-template-experiment-log.md` 记录 `experiment_id` / digest / seed / prompt 版本 / commit；原始数据落 `experiments/**/raw/`（**只增不改**）。
4. **已知缺陷**：改动前先查 `docs/prj-ledger-known-issues.md` 与 `docs/prj-ledger-risk-register.md`。
5. **变更记录**：见 `CHANGELOG.md`。
6. **文档命名**：新增/改名文档按 `docs/prj-spec-document-standard.md`（`<阶段>-<类型>-<主题>[-<日期>]`，全小写 ASCII kebab），并同步登记 `reports/README.md` §一 与本文件目录结构。
7. **依赖口径**：`requirements.txt` 为声明集，`uv pip install -r` 为唯一安装入口；**禁止直接 `uv pip sync`**。
8. **收口后纪律（2026-10-10 起）**：`M6.4` 已达成，仓库进入**维护期** —— **只修缺陷与文档口径，不新增功能范围**；任何扩范围动作须先另立阶段计划并经判据前置，不得直接改本阶段的 Must 链或停止条件。

## 九、明确不做（Won't）

多租户｜模型微调（预留 LoRA 接口）｜复杂 GraphRAG 多跳（>2 跳）｜移动端｜
真实 Modbus / OPC UA 直连（预留边缘网关转 MQTT 接口）｜
**自动执行维修动作（永久安全刚性）**。

---

> **文档事实源索引**：环境基线 `env/env-baseline-v2.md` ｜ 版本与 digest `docs/prj-ledger-version-lock.md` ｜
> 已知缺陷 `docs/prj-ledger-known-issues.md` ｜ 风险 `docs/prj-ledger-risk-register.md` ｜ 命名规范 `docs/prj-spec-document-standard.md` ｜
> **阶段状态与收口凭据 `docs/p6-gate-closure-2026-10-10.md`** ｜ 报告索引 `reports/README.md` ｜ 变更记录 `CHANGELOG.md` ｜ **用户操作手册 `docs/prj-guide-user-manual.md`**。