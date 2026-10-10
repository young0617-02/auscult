# 数据字典（存储全景 + PostgreSQL 表详册 + 非关系存储键结构）

> **层级**：项目级长期有效（跨阶段）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D4 交付物）
> **状态**：🟢 **活动**
> **最近更新**：2026-10-10
> **口径基准**：存储归属总表指向 `docs/prj-design-architecture.md` §六（D2 定稿），本文不重复裁定；接口字段对应关系见 `docs/prj-spec-api.md` §五
> **事实源**：全部表/列/类型/约束/索引/触发器为**离线静态实测**（2026-10-10），来源：`db/migrations/0001_init.sql`、`0003_reports.sql`、`0004_users.sql`、`0005_knowledge_admission.sql`、`0006_audit_logs.sql`（**逐文件读取；无 0002，编号跳过属仓库现状**，见 `docs/prj-spec-deployment.md`）；非关系存储键结构来源代码：`app/router/budget.py`、`app/review/lifecycle.py`、`app/security/rate_limit.py`、`app/security/pg_audit.py`、`scripts/alarm_engine.py`、`scripts/build_milvus_v1.py`、`scripts/retrieval_base.py`、`scripts/outbox_worker.py`、`scripts/reconcile.py`、`configs/triple_schema.json`、`configs/alarm_rules.yml`、`docs/prj-spec-schema-mapping.md`；凡代码/迁移查不到者标 `【待确认】`，不编造

---

## 一、存储归属总表（指针）

> 权威口径见 `docs/prj-design-architecture.md` §六「存储归属（一表定责）」，此处**不重复**。一句话摘要：**PostgreSQL 为唯一权威源**；TDengine（时序）/ Milvus（向量）/ Neo4j（图谱）各管一类可重建或专项数据；Redis 仅承载运行态（可重建、非权威）。

| 数据 | 存储 | 权威源判定 |
|---|---|---|
| 传感器时序 | TDengine | ✅ TDengine |
| 告警事件 | TDengine（生成）+ PostgreSQL（状态） | **PostgreSQL** |
| 文档块 + 向量 | Milvus | ✅ Milvus |
| 三元组 | Neo4j | ✅ Neo4j |
| 文档元数据/版本 | PostgreSQL（`documents`/`knowledge_versions`） | ✅ PostgreSQL |
| 报告 | PostgreSQL（`reports`） | ✅ PostgreSQL |
| 工作流状态 | Redis（运行态）/ PostgreSQL（报告态，checkpointer 落 PG） | **PostgreSQL** |
| 审核/审计记录 | PostgreSQL（`audit_logs`，append-only 触发器） | ✅ PostgreSQL |
| 会话上下文 | Redis（TTL 24h） | —（非权威，可重建；**代码未实测到写入路径，见 §三.1【待确认，已登记 `ISS-040`】**） |

> LangGraph checkpointer 三表（`checkpoints`/`checkpoint_writes`/`checkpoint_blobs`）由 `PostgresSaver.setup()` 框架自动建表（`app/graph/checkpointer.py`），**不在 migrations 管辖内**，列结构由 `langgraph-checkpoint-postgres` 定义，本字典不展开。

---

## 二、PostgreSQL 表详册（按迁移顺序 0001 → 0006）

> 目标实例：PG 18 @ 宿主 5433，库 `auscult_v2`；全部迁移幂等（`IF NOT EXISTS`）。共 **9 张业务表、74 列、13 个索引（含 1 唯一索引 + 2 部分索引）、1 个显式外键、3 个防篡改触发器**。

### 2.1 `documents` —— 文档主表（0001 建 + 0005 扩）

**用途**：语料/工单等知识文档的元数据、索引状态与准入审核状态；`status` 由 outbox worker 在写入 Milvus/Neo4j 成功后置 `indexed`（0001 头注释实测）。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `doc_id` | UUID | PRIMARY KEY | 文档 ID（登记接口由服务端生成 uuid4） |
| `title` | TEXT | NOT NULL | 标题（1..200 字符，应用层约束） |
| `source` | TEXT | NOT NULL | 来源（如 供应商手册/工单系统） |
| `doc_type` | TEXT | NOT NULL | 枚举：`manual` / `work_order` / `procedure`（应用层校验，无库层 CHECK） |
| `device_model` | TEXT | 可空 | 适用设备型号 |
| `checksum` | TEXT | NOT NULL | 内容 sha256（未传正文时 = sha256(title:doc_id)） |
| `status` | TEXT | NOT NULL DEFAULT `'pending'` | 枚举：`pending` / `indexed` / `failed` |
| `created_at` | TIMESTAMPTZ | DEFAULT `now()` | 登记时间 |
| `admission_status` | TEXT | NOT NULL DEFAULT `'pending'`（0005） | 准入状态：`pending` / `approved` / `rejected`；**pending 时流水线不得索引，rejected 永不索引（保留行供审计）** |
| `admitted_by` | TEXT | 可空（0005） | 准入决策人（用户名） |
| `admitted_at` | TIMESTAMPTZ | 可空（0005） | 准入决策时间 |

**索引**：

| 索引名 | 定义 | 说明 |
|---|---|---|
| `idx_documents_admission` | `(admission_status) WHERE admission_status = 'pending'` | **部分索引**：准入待审队列查询（kb_admin 待审列表，0005） |

### 2.2 `doc_chunks` —— 分块表（0001）

**用途**：Parent-Child 分块落库；父块（章节级）与子块（段落级）同表，靠 `parent_id` 关联，**父块 `parent_id` 为 NULL**；仅子块入 Milvus，父块由子块 `parent_id` 回填（`scripts/build_milvus_v1.py` 实测）。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `chunk_id` | VARCHAR(64) | PRIMARY KEY | 块 ID |
| `doc_id` | UUID | NOT NULL，**FOREIGN KEY → `documents(doc_id)`**（全库唯一显式外键） | 所属文档 |
| `parent_id` | VARCHAR(64) | 可空 | 父块 ID；NULL 即父块自身 |
| `content` | TEXT | NOT NULL | 块正文 |
| `section` | TEXT | 可空 | 章节 |
| `page` | INT | 可空 | 页码 |
| `token_count` | INT | 可空 | token 数 |
| `created_at` | TIMESTAMPTZ | DEFAULT `now()` | 创建时间 |

**索引**：`idx_doc_chunks_doc_id (doc_id)`、`idx_doc_chunks_parent_id (parent_id)`

### 2.3 `knowledge_versions` —— 知识版本表（0001）

**用途**：文档变更审计，每次操作记一条，供追溯与对账；权威源对账（PG/Milvus/Neo4j doc_id 集合比对）依赖 PG 为准（架构文档 §5.4）。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 自增主键 |
| `doc_id` | UUID | NOT NULL | 所属文档（无外键约束，逻辑关联 documents） |
| `version` | INT | NOT NULL | 版本号（准入留痕取 `MAX(version)+1`） |
| `action` | TEXT | NOT NULL | 迁移注释词表 `create`/`update`/`delete`；**代码实际写入**：`create`、`admission_approve`、`admission_reject`（`app/api/routes/knowledge.py` 实测，无库层 CHECK，实际词表大于注释词表） |
| `actor` | TEXT | NOT NULL | 操作者（用户名） |
| `created_at` | TIMESTAMPTZ | DEFAULT `now()` | 操作时间 |

**索引**：`idx_kv_doc_id (doc_id)`

### 2.4 `work_orders` —— 工单表（0001）

**用途**：历史维修工单，供诊断链 `get_maintenance_history` 工具检索（`app/graph/state.py` `WorkOrder` 注释对齐）。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `order_id` | TEXT | PRIMARY KEY | 工单号 |
| `device_id` | TEXT | NOT NULL | 设备 ID |
| `fault` | TEXT | NOT NULL | 故障描述 |
| `action` | TEXT | NOT NULL | 处置动作 |
| `result` | TEXT | 可空 | 处置结果 |
| `created_at` | TIMESTAMPTZ | NOT NULL | 工单时间（无默认值，入库方必须显式提供） |

**索引**：`idx_work_orders_device_id (device_id)`

### 2.5 `alerts` —— 告警状态表（0001）

**用途**：告警事件落盘与状态流转（架构文档 §六：TDengine 生成、PG 管状态）；Socket.IO `alarm:new` 的轮询源（`app/api/socket.py` `_fetch_new_alarms` 实测 SELECT 本表 7 列）；`POST /api/diagnose` 按 `alarm_id` 反查的数据源。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `alarm_id` | TEXT | PRIMARY KEY | 告警 ID，幂等格式 `{rule_id}:{device_id}:{metric}:{alert_start_ms}`（`scripts/alarm_engine.py` 实测；重跑 ON CONFLICT upsert 不重复） |
| `device_id` | TEXT | NOT NULL | 设备 ID |
| `metric` | TEXT | NOT NULL | 测点名 |
| `value` | NUMERIC | 可空 | 告警值 |
| `severity` | TEXT | NOT NULL | 落库词表：`info` / `warning` / `critical`（告警引擎规则词表 high/medium/low 经 `_SEV_PG_MAP` 映射写入，详见 §四.1；无库层 CHECK） |
| `status` | TEXT | NOT NULL DEFAULT `'open'` | 告警状态；**当前唯一写入值 `open`**（告警引擎固定写 'open'）；`acked`/`closed` 流转路径【待确认，已登记 `ISS-039`】 |
| `ts` | TIMESTAMPTZ | NOT NULL | 告警时间 |

**索引**：`idx_alerts_device_ts (device_id, ts DESC)`

**与 Redis 去重配合**：`dedup:alarm:{device_id}:{metric}`（TTL 5min）仅作短期去重缓存，PG 为落盘真相（0001 头注释 + `alarm_engine.py` 实测）。

### 2.6 `outbox` —— Outbox 一致性表（0001）

**用途**：跨存储一致性（Outbox 模式，架构文档 §5.4）：写 PG 成功即写 outbox（milvus/neo4j 各一条），worker 消费后置 done；失败指数退避重试，≥5 次告警人工介入。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 自增主键 |
| `entity_type` | TEXT | NOT NULL | 枚举：`document` / `chunk` |
| `entity_id` | TEXT | NOT NULL | 实体 ID |
| `op` | TEXT | NOT NULL | 枚举：`upsert` / `delete` |
| `target` | TEXT | NOT NULL | 枚举：`milvus` / `neo4j` |
| `payload` | JSONB | 可空 | 写入载荷 |
| `status` | TEXT | NOT NULL DEFAULT `'pending'` | 枚举：`pending` / `done` / `failed` |
| `retry_count` | INT | NOT NULL DEFAULT 0 | 重试计数 |
| `last_error` | TEXT | 可空 | 最近错误 |
| `created_at` | TIMESTAMPTZ | DEFAULT `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | DEFAULT `now()` | 更新时间 |

**索引**：`idx_outbox_pending (target, created_at) WHERE status = 'pending'`（**部分索引**：消费走「取 pending」路径，降低扫描面）

### 2.7 `reports` —— 诊断报告表（0003）

**用途**：图外幂等写入的诊断报告（`app/report/idempotency.py`；finalize 仅生成 report_id，API 层写 PG）。P5-Q8 后 payload 含 evidence 原文与置信度四分量（payload 结构详见 `docs/prj-spec-api.md` §2.4.3）。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `report_id` | VARCHAR(20) | PRIMARY KEY | 格式 `RPT-<sha256[:16]>` |
| `idempotency_key` | VARCHAR(16) | NOT NULL | 幂等键 = sha256(`thread_id:sorted_citations:risk_level`)[:16] |
| `thread_id` | VARCHAR(255) | NOT NULL | 诊断线程 ID（`thr-<20位hex>`） |
| `payload` | JSONB | NOT NULL | 诊断结果快照（diagnosis/root_causes/suggestions/confidence/**confidence_breakdown 四分量**/**evidence 原文**/risk_level/escalate_cloud/human_review/degrade_reason/errors） |
| `risk_level` | VARCHAR(10) | NOT NULL | 枚举：`low` / `medium` / `high`（应用层校验，无库层 CHECK） |
| `confidence` | FLOAT | 可空 | 复合置信度 |
| `review_status` | VARCHAR(20) | 可空 | 枚举：`approved` / `rejected` / `timeout` / `auto_approved` / **NULL（=待审核 pending）**（应用层 `_STATUS_MAP` 实测，无库层 CHECK） |
| `degrade_reason` | TEXT | 可空 | 降级原因（`review_rejected` / `review_timeout` / `budget_exceeded` / `cloud_unavailable`） |
| `created_at` | TIMESTAMPTZ | DEFAULT `now()` | 写入时间 |

**索引**：

| 索引名 | 定义 | 说明 |
|---|---|---|
| `idx_reports_idempotency` | UNIQUE `(idempotency_key)` | **唯一索引**：幂等保障——相同 thread+引用集+风险等级 → 相同 report_id，重复写入返回既有行 |
| `idx_reports_thread` | `(thread_id)` | 按 thread 反查报告 |

### 2.8 `users` —— 用户表（0004）

**用途**：RBAC 四角色用户与登录凭证；SoD（工程师不可自审）由应用层 `validate_submitter` 后端强制。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `user_id` | UUID | PRIMARY KEY DEFAULT `gen_random_uuid()` | 用户 ID（JWT `sub`） |
| `username` | VARCHAR(64) | NOT NULL **UNIQUE** | 用户名（登录主键） |
| `password_hash` | TEXT | NOT NULL | bcrypt 哈希（<72 字节，应用层校验；不依赖 pgcrypto，种子由 `scripts/seed_users.py` 应用层生成） |
| `display_name` | TEXT | NOT NULL | 显示名 |
| `role` | VARCHAR(32) | NOT NULL，**CHECK (role IN ('engineer','reviewer','kb_admin','sys_admin'))** | 角色（全库唯一 CHECK 约束枚举） |
| `is_active` | BOOLEAN | NOT NULL DEFAULT TRUE | 停用开关（登录与每次鉴权复核） |
| `created_at` | TIMESTAMPTZ | DEFAULT `now()` | 创建时间 |
| `updated_at` | TIMESTAMPTZ | DEFAULT `now()` | 更新时间 |

**索引**：`idx_users_username (username)`（UNIQUE 约束本身另建隐式唯一索引）

### 2.9 `audit_logs` —— 审计日志表 + 防篡改触发器（0006 · P5-W4/D12 机制，单列说明）

**用途**：全操作审计的 PG 权威层（与进程本地 JSONL 审计**双轨**：JSONL 延续既有消费方、PG 集中可查询且防篡改——`app/security/pg_audit.py` 文件头实测口径）。写入入口 `append_audit()`；**PG 写入失败不阻断业务**（返回 False + warning，与 budget「Redis 不可达不阻塞」同哲学）。

| 列名 | 类型 | 约束/默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 自增主键 |
| `ts` | TIMESTAMPTZ | NOT NULL DEFAULT `now()` | 事件时间 |
| `trace_id` | VARCHAR(32) | 可空 | 请求追踪 ID（与 API 包络/X-Trace-Id 头同源，超长截断 32） |
| `event` | VARCHAR(64) | NOT NULL | 事件名（实测写入例：`prompt_injection_attempt`、`tool_call`、`rate_limit_exceeded`、`rate_limit_redis_unreachable`、`review_submit` 等；超长截断 64） |
| `severity` | VARCHAR(16) | NOT NULL DEFAULT `'info'` | 枚举：`info` / `warning` / `critical`（`append_audit` 签名实测） |
| `thread_id` | VARCHAR(64) | 可空 | 关联诊断会话（超长截断 64） |
| `actor` | VARCHAR(64) | 可空 | 操作者（用户名或 system，超长截断 64） |
| `detail` | JSONB | NOT NULL DEFAULT `'{}'::jsonb` | 结构化明细（注入命中 pattern、限流桶、预算计数等） |

**索引**：`idx_audit_logs_ts (ts DESC)`、`idx_audit_logs_event (event)`、`idx_audit_logs_thread_id (thread_id)`

**⭐ 防篡改触发器（append-only，P5 机制，M5.3 八项安全回归实测全拒）**：

| 触发器名 | 时机/粒度 | 行为 |
|---|---|---|
| `trg_audit_logs_no_update` | BEFORE UPDATE / FOR EACH ROW | 拒绝，抛 `ERRCODE 42501` |
| `trg_audit_logs_no_delete` | BEFORE DELETE / FOR EACH ROW | 拒绝，抛 `ERRCODE 42501` |
| `trg_audit_logs_no_truncate` | BEFORE TRUNCATE / FOR EACH STATEMENT | 拒绝，抛 `ERRCODE 42501` |

- 三个触发器共用函数 `audit_logs_block_mutation()`（plpgsql）：`RAISE EXCEPTION ... USING ERRCODE = '42501'`，报错文案含 `TG_OP` 与 `TG_NAME`（0006 实测）；
- **设计纪律**：保留策略**不在库层开 DELETE 后门**，超期归档由运维侧处理；JSONL 侧轮转策略为 P6 遗留（`docs/p5-handover-p6.md` §五.8，量级极低暂不阻塞）；
- 依赖该表的 P5 机制闭环：注入审计（`sanitizer.audit_injection_attempt`）、限流审计（`rate_limit.py`）、工具白名单双轨审计（M5.3 结论见 `docs/p5-handover-p6.md` §一 M5.3 行）。

### 2.10 表汇总速查

| # | 表名 | 建立迁移 | 列数 | 主键 | 显式外键 | 索引数 | 触发器 |
|---|---|---|---|---|---|---|---|
| 1 | `documents` | 0001（+0005 扩 3 列） | 11 | `doc_id` | 被引用 | 1（部分） | — |
| 2 | `doc_chunks` | 0001 | 8 | `chunk_id` | → documents | 2 | — |
| 3 | `knowledge_versions` | 0001 | 6 | `id` | — | 1 | — |
| 4 | `work_orders` | 0001 | 6 | `order_id` | — | 1 | — |
| 5 | `alerts` | 0001 | 7 | `alarm_id` | — | 1 | — |
| 6 | `outbox` | 0001 | 11 | `id` | — | 1（部分） | — |
| 7 | `reports` | 0003 | 9 | `report_id` | — | 2（含唯一） | — |
| 8 | `users` | 0004 | 8 | `user_id` | — | 1（+UNIQUE 隐式） | — |
| 9 | `audit_logs` | 0006 | 8 | `id` | — | 3 | 3（防篡改） |
| — | **合计** | 0001/0003/0004/0005/0006（**无 0002**） | **74** | 9 | 1 | 13 | 3 |

---

## 三、非关系存储键结构

### 3.1 Redis（运行态，非权威，可重建）

| Key 模式 | 值结构 | TTL | 用途 / 语义 | 代码出处 |
|---|---|---|---|---|
| `budget:cloud:{YYYY-MM-DD}` | 整数（当日云端调用次数） | 7 天（`EXPIRY_SECONDS=7*24*3600`，审计窗口 + 次日归零兜底；INCR 首次置过期） | 云端预算按天计数，超限熔断 → `degrade_reason="budget_exceeded"`；`/api/health` 同 key 读取展示 | `app/router/budget.py`、`app/api/routes/health.py` |
| `lock:review:{thread_id}` | 字符串 = `reviewer_id` | 25h（24h 超时 + 1h 缓冲；SETNX 获取） | 审核并发锁，防双审核人重复出报告；释放用 Lua 校验 value 防误释放；同 reviewer 可重入；**Redis 不可达 fail-open（降级无锁 + 审计）** | `app/review/lifecycle.py` `ReviewLock` |
| `dedup:alarm:{device_id}:{metric}` | 整数（合并计数 dedup_count） | 5min（`configs/alarm_rules.yml` `dedup.ttl_sec` 默认 300；INCR 首次置过期） | 告警滑动窗口去重：5min 内同类告警合并，不重复触发；可驱逐（但实例 `noeviction` 下实际靠 TTL 自回收——`docs/p0-decision-checkpoint.md` 副作用声明） | `scripts/alarm_engine.py`、`configs/alarm_rules.yml` |
| `ratelimit:diagnose:{client_ip}` | Hash：`tokens`（剩余令牌）/`ts`（纳秒时间戳） | `ceil(capacity/refill)*2+60` 秒（兜底过期） | 令牌桶限流（仅 POST /api/diagnose），Lua 原子扣减；Redis 不可达 fail-open | `app/security/rate_limit.py` |
| 会话上下文（`sess:` 类，TTL 24h） | 【待确认，已登记 `ISS-040`】 | 24h（设计口径） | 架构文档 §六 与 `docs/p0-decision-checkpoint.md` 均登记此 key，但 **`app/` 与 `scripts/` 代码中未找到任何 `sess:` 写入路径**（全库检索无命中）——设计登记、未见落地实现 | 检索实证：`docs/prj-design-architecture.md` §六 vs 代码无命中 |

> Redis 连接串口径：`redis://:auscult-dev-redis@127.0.0.1:6379/0`（budget/lifecycle/rate_limit 三处同源实测；API health 探测用 `REDIS_HOST/REDIS_PORT` 无密码连接）。checkpointer 相关 Redis 键不存在（V5 已裁决 PG checkpointer，`docs/p0-decision-checkpoint.md`）。

### 3.2 Neo4j（三元组图谱，可重建索引）

| 项 | 实测值 | 出处 |
|---|---|---|
| 节点标签 | `Entity`（单一标签；属性 `id` / `name` / `type`；前端节点 id 用 Neo4j `elementId`） | `app/api/routes/graph.py` Cypher 实测（`MATCH (n:Entity {name: ...})`） |
| 实体类型词表（`type` 属性取值） | 设备 / 测点 / 部件 / 故障 / 参数 / 标准值 / 处置 / 部位（8 种） | `configs/triple_schema.json` `entity_types` |
| 关系类型白名单（11 种） | `MONITORS`（监测）/ `INSTALLED_ON`（安装于）/ `CONNECTS`（连接）/ `DRIVES`（驱动）/ `COMPOSES`（构成）/ `CAUSES`（导致）/ `CHARACTERIZES`（表征）/ `EXCEEDS`（超限）/ `THRESHOLDS`（阈值）/ `HANDLED_BY`（处置为）/ `LOCATED_AT`（位于） | `configs/triple_schema.json` `neo4j_relation_map`（graph.py 与 query_graph 工具共用） |
| 关系属性 | `source_chunk_ids`（来源子块 id 列表）、`confidence`（抽取置信度 0~1）、`source_count` | `app/api/routes/graph.py` 读取实测 |
| 三元组抽取约束 | head/tail 禁止编造，`source_chunk_id` 必须等于随语料给出的 chunk_id（strict json_schema 约束解码） | `configs/triple_schema.json` schema 段 |

### 3.3 Milvus（向量检索主体，可重建索引）

| 项 | 实测值 | 出处 |
|---|---|---|
| 主链路 collection | **`kb_p1_v1`**（retrieval_base / build_milvus_v1 / outbox_worker / reconcile / retrieve_dense / retrieve_sparse 全部同源） | `scripts/retrieval_base.py` L26 等实测 |
| 对照实验 collection | `kb_v1`（仅 `scripts/run_v2.py` V2 对照基线用，与主链路隔离） | `scripts/run_v2.py` L293 |
| 字段 schema | `chunk_id` VARCHAR(64) **主键**；`text` VARCHAR(65535)（**jieba analyzer**，服务端 BM25）；`dense` FLOAT_VECTOR(dim=**1024**, BGE-M3)；`sparse` SPARSE_FLOAT_VECTOR；标量：`doc_id` / `parent_id` / `section` / `doc_type` VARCHAR(128)、`page` INT64；BM25 Function：text→sparse | `scripts/build_milvus_v1.py` `build_schema` 实测 |
| 索引 | `dense`：HNSW / COSINE / M=16 / efConstruction=200；`sparse`：SPARSE_INVERTED_INDEX / BM25 | 同上 |
| 入库范围 | **仅子块**（`is_parent=False`）；父块不落 Milvus，由子块 `parent_id` 回填 | `scripts/build_milvus_v1.py` `load_chunks` |
| 检索方式 | dense / sparse / hybrid(RRF, k=60) 三路（P0-V2 基座）；运行链路 Dense+BM25 并行 → RRF → reranker Top-5 | `build_milvus_v1.py` 头注释 + 架构文档 §二 检索层 |

### 3.4 TDengine（传感器时序，权威源）

> 逐列定义与边界行为以 `docs/prj-spec-schema-mapping.md`（§四 超级表设计、§4.4 可执行 SQL）为权威，此处摘录键结构；告警引擎按 `iot.st_pump_metrics` 查询实测（`scripts/alarm_engine.py` `poll_series`）。

| 项 | 实测值 |
|---|---|
| 数据库 | `iot`（KEEP 365 / DURATION 10 / PRECISION 'ms' / WAL_LEVEL 1） |
| 超级表 | `st_pump_metrics`：普通列 `ts` TIMESTAMP、`vib_rms`/`vib_peak`/`vib_kurtosis`/`bearing_temp`/`motor_current`/`pump_speed` DOUBLE、`quality_ok` BOOL；TAG 列 `group_id` NCHAR(32)、`edge_node_id` NCHAR(64)、`device_id` NCHAR(64)、`device_type` NCHAR(32) |
| 子表命名 | `d_<group_id>_<device_id>`（如 `d_plant1_PUMP-A`，DBIRTH 自动建表） |
| 旁路表 | `st_unmapped_metrics`（未登记 metric 不丢数，附 `schema_drift` 告警） |
| 状态表 | `st_device_status`（online / birth_seq / last_seq / reason；NDEATH/DDEATH/rebirth 写入） |
| 消费契约 | `query_sensor` 只读 `st_pump_metrics`，只返回原始统计，异常标记由应用层规则判定（禁止插补） |

---

## 四、枚举与状态机（代码实测）

### 4.1 告警严重度 severity —— **两套词表并存（有意设计，非矛盾）**

| 词表 | 取值 | 使用位置 |
|---|---|---|
| 规则引擎词表 | `high` / `medium` / `low` | `AlarmEvent`（`app/graph/state.py`，默认 medium）、`configs/alarm_rules.yml`、诊断链内部 |
| PG/契约词表 | `info` / `warning` / `critical` | `alerts` 表落库（`_SEV_PG_MAP` 映射）、REST `/api/alarms` 筛选与响应、Socket.IO `alarm:new` |

映射（`scripts/alarm_engine.py` L43 实测）：`high→critical`、`medium→warning`、`low→info`。

> **实测注意**：`POST /api/diagnose` 内联 `alarm` 对象走 `AlarmEvent` 校验（规则词表 high/medium/low），**不经 `_SEV_PG_MAP`**；仅告警引擎落库路径做映射。词表口径差异已如实记录。

### 4.2 告警状态（alerts.status）

`open`（默认值，告警引擎唯一写入值）→ `acked` / `closed`（仅见于 `/api/alarms` 筛选参数 description；**无库层 CHECK、无状态机流转代码**，流转路径【待确认，已登记 `ISS-039`】）。

### 4.3 报告风险与审核状态

| 字段 | 枚举/状态机 | 出处 |
|---|---|---|
| `reports.risk_level` | `low` / `medium` / `high`（报告列表接口应用层白名单 `_RISKS`） | `app/api/routes/reports.py` |
| `reports.review_status` | NULL（=pending 待审核）→ `approved` / `rejected` / `timeout` / `auto_approved`；筛选词表 `_STATUS_MAP` 实测，pending 映射 `review_status IS NULL` | 同上 |
| 审核动作 action | API/Socket 层仅 `approved` / `rejected`；`timeout` 仅系统 watcher 触发（`_REVIEW_ACTIONS` 注释实测） | `app/api/routes/review.py`、`app/api/socket.py` |

**审核状态机**（`app/graph/nodes/review.py` 实测）：`pending` → `approved`（正常通过）｜`rejected`（`degrade_reason="review_rejected"`，仍输出报告带降级标记）｜`timeout`（`degrade_reason="review_timeout"`，24h watcher 触发）；确定性规则判定无命中 → `auto_approved`（不挂起）。生命周期：挂起 4h → 通知备用审核人（`notified_4h`）；24h → 自动 timeout 降级（`app/api/runner.py` watcher 实测）。

### 4.4 知识文档状态

| 字段 | 枚举 | 出处 |
|---|---|---|
| `documents.status`（索引状态） | `pending` / `indexed` / `failed` | 迁移默认值 + `knowledge.py` `_DOC_STATUS` |
| `documents.doc_type` | `manual` / `work_order` / `procedure` | `knowledge.py` `_DOC_TYPES` |
| `documents.admission_status`（准入状态机） | `pending`（上传默认态，流水线不得索引）→ `approved`（准入通过，流水线可索引）｜`rejected`（永不索引，保留行供审计）；**一次性决策**，重复提交 409 | `db/migrations/0005` 语义注释 + `knowledge.admit_doc` 实测 |
| `knowledge_versions.action` | 注释词表 create/update/delete；**代码实际写入** create / admission_approve / admission_reject | §二.3 已述 |

### 4.5 诊断线程状态机

`running` → `waiting_review`（高风险 interrupt 挂起）→（resume 后）→ `done`｜`error`；追问仅允许 `done` / `waiting_review` 态（409 否则）。（`app/api/runner.py` `ThreadRecord` / `ask_question` 实测）

### 4.6 outbox 状态机

`pending` →（worker 消费成功）`done`｜（失败退避重试，retry_count 累加，≥5 次告警人工介入）`failed`。（0001 注释 + 架构文档 §5.4）

### 4.7 降级原因 degrade_reason 取值（代码实测）

`review_rejected`（审核驳回）｜`review_timeout`（24h 超时）｜`budget_exceeded`（云端预算熔断）｜`cloud_unavailable`（云端 20s 超时/不可用）。（`app/graph/nodes/review.py`、架构文档 §5.6、`app/api/config.py` 注释）

### 4.8 审计严重度

`info` / `warning` / `critical`（`app/security/pg_audit.py` `append_audit` 签名默认 info）。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D4 初版建立：PG 9 表 74 列逐列实测自 5 个迁移文件（无 0002，编号跳过属仓库现状）；audit_logs 防篡改触发器单列说明；Redis/Neo4j/Milvus/TDengine 键结构自代码与配置实测；枚举与状态机自代码实测 | `docs/prj-spec-data-dictionary.md` |
