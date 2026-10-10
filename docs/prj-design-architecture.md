# 云侧工业 IoT 诊断 Agent 系统 · 架构设计文档（Architecture）

> **层级**：项目级长期有效（跨阶段）
> **对应里程碑**：`M6.1`（Phase 6 文档收口 · D2 交付物）
> **状态**：🟢 **活动**
> **最近更新**：2026-10-10
> **上游依据与事实源指针**：系统摘要与口径对齐 → `README.md` §二；设计原始来源 → `plan/工业设备诊断 Agent.md` §四（分层/七模块/三条数据流/存储归属）、§五（接口契约）、§六（关键机制）；命名与文件头规范 → `docs/prj-spec-document-standard.md` §二/§三；模块与路由落地 → `app/`（`app/api/`、`app/graph/`、`app/tools/`、`app/report/`、`app/review/`、`app/router/`、`app/security/`、`app/observability/`）；阶段环境细节 → `docs/p3-handover-p4.md`、`docs/p4-handover-p5.md`、`docs/p5-handover-p6.md`
> **说明**：本文是 `README.md` §二、`plan/工业设备诊断 Agent.md` §四 的**详细展开版**，三处口径必须一致；凡来源查不到或互相矛盾者标 `【待确认】`，不编造数字/端口/事件名/路由/模型名。

---

## 一、定位与范围

> **一句话定位**：一个跑在本地、以告警为入口、会自己查资料并给出**带出处**维修建议的工业设备诊断 Agent —— **数据不出厂，结论可追溯**。

**系统边界**（口径来源 `docs/p0-spec-scope-mvp.md` §一/§二/§三）：

- **做**：告警 → 证据汇聚 → 诊断推理 → 报告生成 → 高风险人工审核 的闭环（Must 链 13 项，逐条见 `docs/p0-spec-scope-mvp.md` §二）；
- **不做（Won't）**：多租户｜模型微调（预留 LoRA 接口）｜复杂 GraphRAG（>2 跳）｜移动端｜真实 Modbus/OPC UA 直连（预留边缘网关转 MQTT 接口）｜**自动执行维修动作（永久安全刚性）**（`docs/p0-spec-scope-mvp.md` §三）；
- **合规边界**：默认自编模拟数据交付并附局限声明；敏感数据本地闭环，云端升级仅传脱敏摘要与结构化参数、**不传证据原文**（`docs/p0-spec-scope-mvp.md` §六）。

---

## 二、分层架构

```
┌──────────────────────────────────────────────────────────────────────┐
│  入口层     Nginx :9763  （反向代理 + WebSocket 透传 + SSL 预留）        │
├──────────────────────────────────────────────────────────────────────┤
│  表现层     Next.js 16 + shadcn/ui + Socket.IO 实时推送                 │
│            页面：登录 / 告警看板 / 诊断对话 / 报告详情+审核 / 知识库 / 图谱 / 审计 │
├──────────────────────────────────────────────────────────────────────┤
│  编排层     LangGraph（StateGraph + Checkpointer）                      │
│            节点：告警解析 → 传感器分析 → 知识检索 → 历史工单 → 诊断推理   │
│                  → [条件路由] → 降级 / 云端升级 / 人工审核 / 定稿        │
│            工具：retrieve_knowledge / query_sensor / query_graph /       │
│                  get_maintenance_history / generate_report               │
├──────────────────────────────────────────────────────────────────────┤
│  推理层     LLM 适配（本地 Ollama）+ 云端脱敏兜底                         │
│            ├─ 本地：qwen2.5:7b（工具调用）/ deepseek-r1:7b（诊断推理）    │
│            └─ 云端兜底：置信度 ∈ [0.50, 0.75) 升级（脱敏 + 每日预算熔断） │
├──────────────────────────────────────────────────────────────────────┤
│  检索层     混合检索：Dense(BGE-M3) + Sparse(BM25) + RRF + reranker      │
│            图谱检索：Neo4j Cypher 多跳（≤2 跳）                          │
├──────────────────────────────────────────────────────────────────────┤
│  数据层     Milvus / Neo4j / TDengine / PostgreSQL 18 / Redis 8          │
├──────────────────────────────────────────────────────────────────────┤
│  接入层     MQTT(Mosquitto) + Sparkplug B 自研解码器 → TDengine           │
│            告警引擎（阈值 + 滑动窗口）→ Redis 去重 → LangGraph 触发       │
└──────────────────────────────────────────────────────────────────────┘
```

**逐层说明**：

| 层 | 职责 | 落地 / 指针 |
|---|---|---|
| 入口层 | 统一入口；`/` → Next.js、`/api` → FastAPI、`/socket.io` → WS 透传；Phase 4+ 引入（`ADR-009`） | `docs/p3-handover-p4.md` §一 D19、`README.md` §4.7 |
| 表现层 | 七类页面、对话式追问、Socket.IO 实时推送 | `client/`（Next.js）；推送由 `app/api/socket.py` 承载 |
| 编排层 | State 管理、节点路由、工具调用、置信度路由；支持 `interrupt`/`resume` | `app/graph/build.py`、`app/graph/state.py`、`app/graph/nodes/*.py`、`app/graph/checkpointer.py` |
| 推理层 | 本地双模型分工；低置信度按策略升级云端（脱敏 + 预算熔断） | `app/router/cloud.py`、`app/router/budget.py`；模型分工见 `ADR-001` |
| 检索层 | Dense 稠密 + Sparse 稀疏并行 → RRF 融合 → reranker Top-5；图谱多跳 | `app/tools/retrieve_knowledge.py`、`app/tools/query_graph.py` |
| 数据层 | 五类存储各司其职（见 §六） | `docker/compose.base.yml`、`docs/prj-ledger-version-lock.md` |
| 接入层 | MQTT/Sparkplug B 接入、时序写入、告警生成、去重后触发 | `app/api/socket.py`（`alarm:new` 桥接）；告警引擎为外部进程 |

> **口径裁定（2026-10-10，用户确认）**：本文件推理层一律**以现状代码口径为准** —— **自研 LLM 适配层**（本地 Ollama 直调 + 云端 OpenAI 兼容端点直调；`app/router/cloud.py`、`app/router/budget.py`）。上游 `plan/工业设备诊断 Agent.md` §4.1 中的「LiteLLM 网关」为**早期设计表述、未落地**（`docs/prj-ledger-version-lock.md` 无该依赖、代码无该引用）。
> **不采用 LiteLLM 的完整原因**由 Phase 6 D5 在 `docs/prj-decision-adr-002-hybrid-deployment.md`（ADR-002）中**详细说明**（本文件不重复，以免两处口径再次分叉）。

---

## 三、七大功能模块

| 模块 | 职责 | 关键产出 | 代码落地位置 |
|---|---|---|---|
| 2.1 IoT 接入与告警 | MQTT/Sparkplug B 接入、时序写入、告警生成、Redis 去重 | 告警事件流 | `app/api/socket.py`（`alarm:new` 轮询桥接）；告警引擎为外部进程（`scripts/`） |
| 2.2 知识库管理 | 解析、Parent-Child 分块、三存储写入、版本管理 | 文档块 / 三元组 / 元数据 | `app/api/routes/knowledge.py`（登记 + 准入审核） |
| 2.3 混合检索 | 查询改写、Dense+BM25 并行、RRF、证据组装、图谱融合 | 证据集（含来源） | `app/tools/retrieve_knowledge.py`、`app/tools/query_graph.py` |
| 2.4 Agent 编排 | State 管理、节点路由、工具调用、置信度路由 | 决策轨迹 | `app/graph/build.py`、`app/graph/state.py`、`app/graph/nodes/*.py`、`app/tools/*.py` |
| 2.5 报告与审核 | 结构化报告、高风险强制审核、降级显式化 | 报告 + 审计 | `app/report/idempotency.py`、`app/review/lifecycle.py`、`app/api/routes/review.py`、`app/api/routes/reports.py` |
| 2.6 前端交互 | 七类页面、对话式追问、实时推送 | 用户界面 | `client/`（Next.js）；推送链路 `app/api/socket.py` |
| 2.7 权限与审计 | RBAC（三角色 + 知识库管理员）、全操作审计、职责分离 | 审计日志 | `app/api/security.py`、`app/api/deps.py`、`app/security/pg_audit.py`、`app/security/rate_limit.py`、`app/security/sanitizer.py`、`db/migrations/0006_audit_logs.sql` |

> 模块边界清晰、依赖单向；上游口径见 `plan/工业设备诊断 Agent.md` §4.2。

---

## 四、三条数据流

**① 离线知识构建流**

```
PDF/工单/规程 → MinerU 解析 → Parent-Child 分块 → 元数据标注
   → ① 写入 Milvus(稠密+稀疏) ② 写入 Neo4j(三元组) ③ 写入 PostgreSQL(元数据/版本)
   → 【Outbox 对账】确认三写一致
```

**② 在线诊断请求流**

```
MQTT 告警 → 去重(Redis 滑动窗口) → LangGraph 触发
   → 告警解析 → 传感器分析(query_sensor) → 知识检索(retrieve_knowledge + query_graph)
   → 历史工单(get_maintenance_history) → 诊断推理(置信度计算)
   → [条件路由：降级 / 云端升级 / 人工审核 / 定稿] → 报告生成(generate_report)
   → [高风险 → interrupt 人工审核] → Socket.IO 推送 → 审计落库
```

**③ 业务数据管理流**

```
登录(RBAC) → 告警/报告/知识库查询 → 审核(通过/驳回+意见) → 知识库更新(版本升版) → 审计
```

> 口径来源 `README.md` §2.3 与 `plan/工业设备诊断 Agent.md` §4.3。

---

## 五、关键机制

### 5.1 五档条件路由（首个命中生效）

> 实现：`app/graph/build.py` `_route_condition`；口径来源 `README.md` §2.4、`plan/工业设备诊断 Agent.md` §5.4。

| 优先级 | 条件 | 目标节点 |
|---|---|---|
| 1 | `retry_count >= 3` | `degrade` |
| 2 | `confidence < 0.50` | `degrade` |
| 3 | `confidence < 0.75` | `escalate_cloud`（云端失败 → `degrade`） |
| 4 | `risk_level == "high"` | `human_review`（`interrupt`） |
| 5 | else | `finalize` |

### 5.2 复合置信度与 0.75 阈值

加权和（各项归一化 0~1，来源 `plan/工业设备诊断 Agent.md` §6.1）：

```
confidence = 0.35 * retrieval_score      # Top-K 检索得分归一化均值
           + 0.20 * sensor_consistency   # 传感器异常与候选故障模式的一致性
           + 0.15 * graph_support        # 图谱是否存在支撑路径（有=1，无=0.3）
           + 0.30 * llm_self_score       # 推理模型自评（经温度缩放校准）
```

- **0.75 阈值依据**：达到可自动生成正式报告所需精确率（≥85%）对应的**校准后阈值**，非拍脑袋；
- **校准**：温度缩放（Temperature Scaling），目标 `ECE ≤ 0.10`（`plan/工业设备诊断 Agent.md` §6.1）；
- **三档阈值语义区分**：0.50（降级线）/ 0.60（强制审核线）/ 0.75（自动生成线），三者为**不同用途的独立阈值**（`docs/p0-spec-scope-mvp.md` §7.1）。

### 5.3 高风险强制审核

| 事项 | 机制 | 落地 |
|---|---|---|
| 强制中断 | 高风险命中 → `interrupt()`，checkpoint 落盘、流程挂起 | `app/graph/nodes/review.py` |
| 恢复 | 审核决策经 `Command(resume=...)` 恢复执行，图外幂等写入报告 | `app/api/routes/review.py`、`app/report/idempotency.py` |
| 职责分离（SoD） | 报告提交者不得自审 | `app/review/lifecycle.py` `validate_submitter` |
| 并发唯一性 | `lock:review:{thread_id}` SETNX + 24h 超时缓冲 | `app/review/lifecycle.py` `ReviewLock` |
| 24h 超时自动降级 | 4h 通知备用审核人；24h 未审 → `resume({action:"timeout"})`，流程不挂起 | `app/review/lifecycle.py` `check_review_timeout` / `auto_timeout_resume` |

### 5.4 跨存储一致性（Outbox + 对账）

- **Outbox 模式**：先写 PostgreSQL（`document.status='pending'`）→ 后台消费写入 Milvus + Neo4j → 全成功置 `indexed`，任一失败入补偿队列（指数退避，≥5 次告警人工介入）；
- **每日对账**：比对 PG / Milvus / Neo4j 的 `doc_id` 集合，输出差异报告；
- **权威源**：**PostgreSQL 为唯一权威源**；Milvus/Neo4j 为可重建索引，Redis 仅承载运行态（`plan/工业设备诊断 Agent.md` §6.3）。
- 表落地：`outbox` / `documents` 见 `db/migrations/0001_init.sql`（`docs/p3-handover-p4.md` §1.5）。

### 5.5 LangGraph Checkpoint（PostgresSaver）

- **采纳方案**：`langgraph-checkpoint-postgres`（候选 B，官方实现），弃用 Redis 第三方 checkpointer（`ISS-005` / B7）；
- 连接与建表：`PostgresSaver.from_conn_string(...)` + `saver.setup()`（幂等），见 `app/graph/checkpointer.py`；
- 表：`checkpoints` / `checkpoint_writes` / `checkpoint_blobs`；
- **写操作移出图内**：`generate_report` 置于审核之后、图外执行 + `idempotency_key` 去重（`ADR-007`）；
- 决策与逐项理由见 `docs/p0-decision-checkpoint.md`（= `ADR-008` 的上游事实源）。

### 5.6 云端脱敏与预算熔断

- **脱敏**：送云端前将 `device_id` 替换为 **`设备#<sha256[:6]>`**（可追溯不可逆），剥离厂区/工艺参数标识，仅保留「故障现象 + 通用知识 + 统计摘要」，**不传证据原文** —— `app/router/cloud.py` `_hash_device_id` / `sanitize_state`；
- **每日预算上限**：**340 次/天**，`budget:cloud:{YYYY-MM-DD}` Redis 按天计数，超限熔断 → `degrade_reason="budget_exceeded"`（`app/router/budget.py`、`app/api/config.py` `CLOUD_BUDGET_LIMIT`，口径 `plan/工业设备诊断 Agent.md` §5.7 / §7.1）；
- **超时**：云端调用 20s 超时，失败 → `degrade_reason="cloud_unavailable"`，保留本地诊断；
- **审计**：每次升级写 `reports/cloud_audit.jsonl`（含脱敏前后 hash + 预算计数）。

### 5.7 降级显式化

低置信度（`confidence < 0.50`）**不自动出正式报告**，显式输出「初步判断，建议人工确认」并标注 `degrade_reason`（`state.degrade_reason`），使降级可被用户与审计识别（`plan/工业设备诊断 Agent.md` §5.4；`README.md` §2.3）。

---

## 六、存储归属（一表定责）

> 口径来源 `README.md` §2.5 与 `plan/工业设备诊断 Agent.md` §4.4（两处口径一致）。

| 数据 | 存储 | 权威源 | 说明 |
|---|---|---|---|
| 传感器时序 | TDengine | ✅ | 原始遥测 |
| 告警事件 | TDengine(生成) + PostgreSQL(状态) | PostgreSQL | 状态流转 |
| 文档块 + 向量 | Milvus | ✅ | 检索主体 |
| 三元组 | Neo4j | ✅ | 图谱 |
| 文档元数据/版本 | PostgreSQL | ✅ | `knowledge_versions` |
| 报告 | PostgreSQL | ✅ | `reports` 表 |
| 工作流状态 | Redis（运行态）/ PostgreSQL（报告态） | **PostgreSQL** | V5 checkpoint |
| 审核 / 审计记录 | PostgreSQL | ✅ | `audit_logs`（append-only 触发器） |
| 会话上下文 | Redis（TTL 24h） | — | 非权威，可重建 |

---

## 七、接口总览

> **实测提取**（2026-10-10，来源为代码 `app/api/routes/*.py`、`app/api/socket.py`、`app/api/main.py`）；未实测确认者不写。

### 7.1 REST 路由（前缀 + 端点）

| 前缀 | 端点 | 方法 | 说明 | 鉴权 |
|---|---|---|---|---|
| `/api/auth` | `/api/auth/login` | POST | 登录，返回 JWT | 公开 |
| | `/api/auth/me` | GET | 当前登录用户 | 已登录 |
| `/api/health` | `/api/health` | GET | 健康检查（存储探测 + 云端预算） | 公开 |
| `/api/alarms` | `/api/alarms` | GET | 告警列表（分页/筛选） | 已登录 |
| `/api/reports` | `/api/reports` | GET | 报告列表（status/risk 筛选） | 已登录 |
| | `/api/reports/{report_id}` | GET | 报告详情 | 已登录 |
| `/api/graph` | `/api/graph/neighbors` | GET | 图谱邻居（可视化；Neo4j 不可达降级） | 已登录 |
| `/api/knowledge/docs` | `/api/knowledge/docs` | GET | 知识库文档列表 | 已登录 |
| | `/api/knowledge/docs` | POST | 文档登记（准入占位） | `kb_admin` |
| | `/api/knowledge/docs/{doc_id}/admission` | POST | 准入审核（一次性决策） | `kb_admin` |
| `/api/diagnose` | `/api/diagnose` | POST | 发起诊断（`alarm_id` 或 `alarm` 二选一） | `engineer`/`reviewer`/`sys_admin` |
| `/api/threads` | `/api/threads/{thread_id}` | GET | 线程状态/进度 | 已登录 |
| | `/api/threads/{thread_id}/ask` | POST | 对话式追问（`chat:ask` 的 REST twin） | `engineer`/`reviewer`/`sys_admin` |
| | `/api/threads/{thread_id}/review` | POST | 审核提交主通道（`approved`/`rejected`） | `reviewer` |
| `/api/reports` | `/api/reports/{report_id}/review` | POST | 审核别名（由报告反查线程，复用同一服务） | `reviewer` |
| `/api/review` | `/api/review/pending` | GET | 审核队列 | `reviewer`/`sys_admin` |
| 根/运维 | `/api` | GET | 根包络（冒烟） | 公开 |
| | `/metrics` | GET | Prometheus 抓取端点（裸 exposition，无包络） | 公开 |

> **前缀合计 10 个**（`/api/auth`、`/api/health`、`/api/alarms`、`/api/reports`、`/api/graph`、`/api/knowledge/docs`、`/api/diagnose`、`/api/threads`、`/api/review`，及根 `/api`+`/metrics`），**端点数合计 18 个**。
> 统一响应包络 `{code, message, data, trace_id}`、错误码映射与限流见 `app/api/errors.py`、`app/api/main.py`、`app/security/rate_limit.py`。

### 7.2 Socket.IO 事件（实测）

| 事件名 | 方向 | 载荷要点 | 代码位置 |
|---|---|---|---|
| `alarm:new` | Server → Client | `{alarm_id, device_id, metric, value, severity, status, ts}`（PG 轮询桥接） | `app/api/socket.py` `_alarm_poller` |
| `diagnosis:progress` | Server → Client | `{thread_id, node, nodes_done, ts}` | `app/api/socket.py` `_emit_runner_event` |
| `diagnosis:done` | Server → Client | `{thread_id, status, report_id, degrade_reason, ts[, error]}`（终态：done/error） | 同上（`diagnosis:error` 亦以本事件 `status="error"` 发出） |
| `review:required` | Server → Client | `{thread_id, payload, ts}` | 同上 |
| `chat:ask` | Client → Server | `{thread_id, question}`（ack 返回 `{code,message,data}`） | `app/api/socket.py` `_chat_ask` |
| `review:submit` | Client → Server | `{thread_id, action, comment}`（仅 `reviewer`） | `app/api/socket.py` `_review_submit` |

> 连接鉴权：`connect` 时 `auth={"token": <JWT>}`，无效即拒连；另有 `connect` / `disconnect` 生命周期钩子（非业务事件）。事件契约冻结口径见 `app/api/socket.py` 文件头（`plan/工业设备诊断 Agent.md` §5.6 为设计稿口径）。

---

## 八、技术选型与版本

> **版本号不在本文件展开**：组件与模型一律以 **`docs/prj-ledger-version-lock.md`**（唯一事实源）为准，禁止裸 tag、禁止写 `latest`。

| 组件 | 版本 | 事实源指针 |
|---|---|---|
| MQTT Broker / 工业协议 | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.1 |
| 时序库 TDengine | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.1 |
| 向量库 Milvus | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.1 |
| 关系库 PostgreSQL | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.1 |
| 缓存 Redis | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.1 |
| 知识图谱 Neo4j | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.1 |
| 本地 LLM（Ollama 双模型） | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2 |
| 嵌入模型 BGE-M3 / reranker | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.1 / §二.2.2 |
| 编排 LangGraph + PG checkpointer | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.2.9 |
| 后端 FastAPI / 前端 Next.js / 实时 Socket.IO | 【见版本锁】 | `docs/prj-ledger-version-lock.md` §二.3 |

> **选型偏离登记（2026-10-10，用户确认；登记与版本一律以 `docs/prj-ledger-version-lock.md` 为准）**：上游 `plan/工业设备诊断 Agent.md` §3.1 选型总表列出的组件，与现行实装对照如下 ——
>
> | 上游选型 | 现行状态 | 依据 |
> |---|---|---|
> | `BGE-reranker-v2-m3`（重排） | ✅ **已选用 & 锁定** | `docs/prj-ledger-version-lock.md` §二.2.2.2、§三 第 13 行 |
> | `RAGAS`（评测） | ✅ **已锁** `ragas==0.4.3` | `docs/prj-ledger-version-lock.md` §二.2.24 第 2 行、`requirements.txt` |
> | `LiteLLM`（LLM 网关） | ❌ **未采用** | 推理层为自研适配层，见 §二 口径裁定；详细原因见 `docs/prj-decision-adr-002-hybrid-deployment.md` |
> | `Langfuse`（可观测） | ❌ **未采用** | 可观测采用 Prometheus + Grafana，见 `monitoring/` |
>
> 本文件不另抄版本清单；上表未列者一律以版本台账为准。

---

## 九、架构决策索引（ADR-001 – ADR-009）

> ADR 文件**已创建（2026-10-10，Phase 6 D5 产出）**。计划原写 `docs/adr/ADR-001..009.md`，按 `docs/prj-spec-document-standard.md` §二 已裁决改为 `docs/prj-decision-adr-00N-<主题>.md`；下表「拟定文件名」列即为实际产出路径。

| ADR | 决策 | 拟定文件名（D5 产出） | 事实源 / 重叠说明 |
|---|---|---|---|
| ADR-001 | 本地双模型分工（`qwen2.5:7b` 工具调用 + `deepseek-r1:7b` 推理） | `docs/prj-decision-adr-001-model-role.md` | **与现存 `docs/p0-decision-model-role.md` 重叠** → D5 改为引用而非重复 |
| ADR-002 | 混合部署形态（本地优先 + 云端脱敏兜底）；**并须详细说明「不采用 LiteLLM 网关」的原因** | `docs/prj-decision-adr-002-hybrid-deployment.md` | 来源 `plan/工业设备诊断 Agent.md` §3.8；**用户裁定 2026-10-10：LiteLLM 未采用的完整原因必须在本 ADR 中详述**（见 §二 口径裁定） |
| ADR-003 | Milvus + 服务端 BM25（jieba analyzer） | `docs/prj-decision-adr-003-milvus-bm25.md` | 来源 `plan/工业设备诊断 Agent.md` §3.2 |
| ADR-004 | 复合置信度公式与 0.75 阈值依据 | `docs/prj-decision-adr-004-confidence.md` | 来源 `plan/工业设备诊断 Agent.md` §6.1 |
| ADR-005 | PostgreSQL 18 为唯一权威业务库（不用 MongoDB） | `docs/prj-decision-adr-005-postgres-authority.md` | 来源 `plan/工业设备诊断 Agent.md` §3.10 |
| ADR-006 | 跨存储一致性（Outbox + 对账，PG 权威源） | `docs/prj-decision-adr-006-cross-store-consistency.md` | 来源 `plan/工业设备诊断 Agent.md` §6.3 |
| ADR-007 | 写操作移出图内 + 幂等键 | `docs/prj-decision-adr-007-write-outside-graph.md` | 来源 `plan/工业设备诊断 Agent.md` §6.4 |
| ADR-008 | checkpoint 存储选型与 `noeviction`/无 TTL | `docs/prj-decision-adr-008-checkpoint-store.md` | **与现存 `docs/p0-decision-checkpoint.md` 重叠** → D5 改为引用而非重复 |
| ADR-009 | Nginx 仅在生产化阶段引入 | `docs/prj-decision-adr-009-nginx-late.md` | 来源 `plan/工业设备诊断 Agent.md` §3.11 |

---

## 十、已知边界与遗留

| 类别 | 指针 |
|---|---|
| 已知缺陷（ISS 台账） | `docs/prj-ledger-known-issues.md` |
| 风险登记册 | `docs/prj-ledger-risk-register.md` |
| Phase 5 → 6 遗留（按优先级 8 项） | `docs/p5-handover-p6.md` §五 |

> 重点遗留（口径来源 `docs/p5-handover-p6.md` §五）：P95 端到端（含生成）未达标（优化路径=流式输出 / `max_tokens` 收紧 / 结构化输出 / 高频缓存）；数据库访问层连接池（`app/api/db.py`）；health 探测阻塞；RPO 定时备份持续化；引用正确率严格口径；ECE 区分度；golden 50 题待扩语料重评。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D2 初版建立（本项目级架构文档首建，作为 `README.md` §二 / `plan/工业设备诊断 Agent.md` §四 的详细展开版） | `docs/prj-design-architecture.md` |