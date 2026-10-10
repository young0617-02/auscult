# API 文档（REST + Socket.IO）

> **层级**：项目级长期有效（跨阶段）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D4 交付物）
> **状态**：🟢 **活动**
> **最近更新**：2026-10-10
> **口径基准**：`docs/prj-design-architecture.md` §七（接口总览，D2 定稿）—— 本文档是其**详细展开版**，端点/方法/鉴权口径必须与之一致
> **事实源**：全部字段、状态码、payload 均为**离线静态实测**（2026-10-10），来源代码：`app/api/main.py`、`app/api/routes/*.py`（8 文件）、`app/api/socket.py`、`app/api/deps.py`、`app/api/security.py`、`app/api/errors.py`、`app/api/runner.py`、`app/api/config.py`、`app/api/db.py`、`app/security/rate_limit.py`、`app/graph/state.py`、`app/report/idempotency.py`、`app/graph/nodes/review.py`；凡代码查不到者标 `【待确认】`，不编造

---

## 一、总则

### 1.1 Base URL 与启动

| 项 | 值 | 出处 |
|---|---|---|
| 直连后端 | `http://127.0.0.1:8000` | `app/api/main.py` 文件头（uvicorn 启动命令） |
| API 路径前缀 | `/api`（各路由 router prefix） | `app/api/routes/*.py` |
| Nginx 单入口 | `http://127.0.0.1:9763`（`/`→Next.js:3000、`/api`→FastAPI:8000、`/socket.io` WS 透传） | `docs/p4-handover-p5.md` §一 D19 |
| ASGI 入口 | `app.api.main:socket_app`（FastAPI + Socket.IO ASGIApp 合体，REST 场景亦须用它） | `app/api/main.py` L112-113 |
| Prometheus 抓取 | `GET /metrics`（**不在 `/api` 前缀下**，裸 exposition 格式，无统一包络） | `app/api/main.py` L72-75 |

### 1.2 鉴权方式（代码实测）

| 项 | 实测值 | 出处 |
|---|---|---|
| 传输方式 | `Authorization: Bearer <JWT>` 请求头 | `app/api/deps.py` `get_current_user` |
| 签名算法 | HS256 | `app/api/security.py`、`app/api/config.py` `JWT_ALGORITHM` |
| JWT payload | `{sub: user_id, username, role, iat, exp}`（不塞敏感字段） | `app/api/security.py` `create_access_token` |
| 有效期 | 480 分钟（8h，一个班次）；环境变量 `JWT_EXPIRE_MINUTES` 可覆盖 | `app/api/config.py` `JWT_EXPIRE_MINUTES` |
| 密码存储 | bcrypt（rounds=12，**72 字节上限在登录入口校验**，超限 422，不静默截断） | `app/api/security.py`、`app/api/routes/auth.py` |
| 密钥注入 | `JWT_SECRET` 环境变量；开发默认值仅限本机（启动打 warning 不中断） | `app/api/config.py`、`app/api/main.py` L46-49 |
| RBAC 四角色 | `engineer` / `reviewer` / `kb_admin` / `sys_admin`（PG CHECK 约束，见 `docs/prj-spec-data-dictionary.md` §二.8） | `db/migrations/0004_users.sql` |
| 后端依赖 | `get_current_user`（登录态解析 + `is_active` 复核）、`require_roles(*roles)`（角色门控工厂） | `app/api/deps.py` |
| 职责分离（SoD） | 诊断发起人不得自审（`validate_submitter` 后端强制，非前端体验优化） | `app/review/lifecycle.py`、`app/api/runner.py` `submit_review` |
| 防账号枚举 | 登录失败统一 401 文案「用户名或密码错误」，不区分用户不存在/密码错误 | `app/api/routes/auth.py` L30-32 |

### 1.3 统一响应包络

成功与失败均为同一包络 `{code, message, data, trace_id}`（`app/api/errors.py`）：

```json
// 成功：code 为数值 0
{"code": 0, "message": "ok", "data": { ... }, "trace_id": "a1b2c3d4e5f60718"}
// 失败：code 为错误码字符串（见 §四）
{"code": "E_NOT_FOUND", "message": "报告 RPT-xxx 不存在", "data": null, "trace_id": "a1b2c3d4e5f60718"}
```

- `trace_id`：每请求由中间件生成（uuid4 hex 前 16 位），同时写入 **`X-Trace-Id` 响应头**，用于审计关联（`app/api/main.py` L52-69）；
- **例外**：`GET /metrics` 返回裸 Prometheus exposition（`text/plain`），不走包络；
- 兜底 500 不向客户端透出内部细节，仅凭 trace_id 服务端反查（`app/api/main.py` L88-92）。

### 1.4 分页约定

告警 / 报告 / 知识库文档三类列表接口共用同一分页参数与响应结构（各路由文件 Query 定义实测）：

| 参数 | 类型 | 约束 | 默认 | 说明 |
|---|---|---|---|---|
| `page` | int | ≥1 | 1 | 页码，从 1 起 |
| `size` | int | 1..100 | 20 | 每页条数 |

响应 `data` 结构：`{"items": [...], "total": <int>, "page": <int>, "size": <int>}`，排序均为时间倒序（`alerts.ts DESC` / `reports.created_at DESC` / `documents.created_at DESC`）。

### 1.5 限流（P5-W4/D13）

| 项 | 实测值 | 出处 |
|---|---|---|
| 适用端点 | 仅 `POST /api/diagnose`（云端升级入口，高成本） | `app/security/rate_limit.py` `DEFAULT_RULES` |
| 算法 | Redis Lua 原子令牌桶（按客户端 IP 分桶） | 同上 |
| 参数 | 容量 10、回填 10/分（≈6s/令牌）；环境变量 `AUSCULT_RATE_LIMIT="capacity:refill_per_sec"` 可覆盖 | 同上 |
| 触发响应 | `429 E_RATE_LIMITED` + `Retry-After` 响应头（仍带统一包络与 trace_id） | 同上、`app/api/main.py` L57-59 |
| 降级 | Redis 不可达 → **fail-open 放行** + 审计记录 `rate_limit_redis_unreachable` | 同上 |

---

## 二、REST 端点详表

> 共 **18 个端点 / 10 个前缀**（与 `docs/prj-design-architecture.md` §7.1 一致）。所有成功响应 HTTP 状态码均为 200（FastAPI 默认，无 201/204）；失败状态码见 §四。

### 2.1 认证 `/api/auth`

#### POST `/api/auth/login` —— 登录

| 项 | 值 |
|---|---|
| 权限 | 公开 |
| 请求体（`LoginIn`） | 见下表 |
| 成功响应 `data` | `{"access_token": "<JWT>", "token_type": "bearer", "user": {"user_id", "username", "display_name", "role"}}` |
| 失败状态码 | 401（用户名或密码错误 / 账号已停用）、422（参数校验失败或密码 >72 字节） |

请求体字段（`app/api/routes/auth.py`）：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `username` | str | ✅ | 1..64 字符 | 用户名 |
| `password` | str | ✅ | min_length=1；UTF-8 编码 ≤72 字节 | 密码（bcrypt 上限硬校验） |

#### GET `/api/auth/me` —— 当前登录用户

| 项 | 值 |
|---|---|
| 权限 | 已登录（`get_current_user`） |
| 请求体 | 无 |
| 成功响应 `data` | `{"user_id", "username", "display_name", "role"}`（均 str） |
| 失败状态码 | 401（未携带 / 无效 / 过期 token / 账号停用） |

> 用途：RBAC 校验锚点，e2e 用其验证 401/403（路由文件 docstring 实测）。

### 2.2 健康检查 `/api/health`

#### GET `/api/health` —— 存储探测 + 云端预算

| 项 | 值 |
|---|---|
| 权限 | 公开 |
| 请求体 | 无 |
| 失败状态码 | 无（**health 永不 500**：全部探测 1s 超时、异常降级为 down） |

响应 `data` 字段（`app/api/routes/health.py` 实测）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `pg` | `{"status": "up"/"down", "latency_ms": float/null}` | **真实查询探测**（`SELECT 1`，验证鉴权与库可用），非仅 TCP |
| `milvus` / `neo4j` / `tdengine` / `redis` | 同上结构 | TCP 连通性探测（探测端口来自 `app/api/config.py`：milvus 19531 / neo4j 7687 / tdengine 6041 / redis 6379，环境变量可覆盖） |
| `cloud_budget` | `{"used": int/null, "limit": int}` | 读 Redis `budget:cloud:{YYYY-MM-DD}` 当日计数；Redis 不可达时 `used=null`；`limit` 来自 `CLOUD_BUDGET_LIMIT`（默认 340，`env/cloud.json` 的 `budget_daily_limit` 可覆盖） |

> 探测目标主机/端口默认值与容器端口基线的对应关系见 `app/api/config.py`（v2 栈 milvus 端口 19531，基线 19530 被占）。

### 2.3 告警 `/api/alarms`

#### GET `/api/alarms` —— 告警列表（分页/筛选）

| 项 | 值 |
|---|---|
| 权限 | 已登录（任意角色；工程师/审核员均为告警消费方） |
| 查询参数 | `page`、`size`（§1.4）＋ `status`（≤20 字符，按状态筛选）、`severity`（≤20 字符）、`device_id`（≤100 字符），均可选，多条件 AND |
| 成功响应 `data.items[]` 行 | `{"alarm_id", "device_id", "metric", "value", "severity", "status", "ts"}`（ts 为 TIMESTAMPTZ，FastAPI 序列化为 ISO 字符串） |
| 排序 | `ts DESC` |
| 失败状态码 | 401；502（PG 不可达，`db.py` 统一转 `E_UPSTREAM`） |

> `status` 取值词表（`open/acked/closed`）与 `severity` 取值词表（`info/warning/critical`）目前仅写在 Query 参数 description 中，**库层无 CHECK 约束**；落库方当前只写 `status='open'`（见 `scripts/alarm_engine.py`），acked/closed 的流转路径【待确认，已登记 `ISS-039`（Q6 登记不修）】。severity 枚举详册见 `docs/prj-spec-data-dictionary.md` §四。

### 2.4 诊断报告 `/api/reports`

#### GET `/api/reports` —— 报告列表（status/risk 筛选）

| 项 | 值 |
|---|---|
| 权限 | 已登录 |
| 查询参数 | `page`、`size`（§1.4）＋ `status`、`risk`（均可选） |
| `status` 合法值 | `pending` / `approved` / `rejected` / `timeout` / `auto_approved`（非法值 → 422） |
| `risk` 合法值 | `low` / `medium` / `high`（非法值 → 422） |
| `pending` 语义 | `review_status IS NULL`（待审核，含 high 风险刚生成未走完审核的）——`_STATUS_MAP` 实测 |
| 成功响应 `data.items[]` 行 | `{"report_id", "thread_id", "risk_level", "confidence", "review_status", "degrade_reason", "created_at", "diagnosis"}`（`diagnosis` 取 `payload->>'diagnosis'` 摘要） |
| 排序 | `created_at DESC` |
| 失败状态码 | 401、422（status/risk 非法）、502 |

#### GET `/api/reports/{report_id}` —— 报告详情

| 项 | 值 |
|---|---|
| 权限 | 已登录 |
| 成功响应 `data` | `{"report_id", "idempotency_key", "thread_id", "payload", "risk_level", "confidence", "review_status", "degrade_reason", "created_at"}`（复用 `app/report/idempotency.py` `get_report`；`payload` 为完整 JSONB 快照，结构见 §2.4.3） |
| 失败状态码 | 401、404（报告不存在）、502 |

**2.4.3 `payload` JSONB 快照结构**（`app/report/idempotency.py` `state_to_payload` 实测，P5-Q8 已含 evidence 原文持久化与置信度四分量）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `diagnosis` | str/null | 诊断结论 |
| `root_causes` | `[{cause, citations[], confidence_hint}]` | 根因（带引用） |
| `suggestions` | `[{action, citations[], risk}]` | 建议（risk: low/medium/high） |
| `confidence` | float | 复合置信度 |
| `confidence_breakdown` | `{<str>: float}` | 置信度四分量（retrieval/sensor/graph/self），支撑报告详情分解面板 |
| `evidence` | `[{chunk_id, text, score, source_type, routes[]}]` | **证据原文持久化**（P5 机制）；source_type: knowledge/sensor/graph/maintenance |
| `risk_level` | str | low/medium/high |
| `escalate_cloud` | bool | 是否云端升级 |
| `human_review` | dict/null | 审核结果（`{status, reviewer_id, comment, ...}`，见 `app/graph/nodes/review.py`） |
| `degrade_reason` | str/null | 降级原因 |
| `errors` | list | 图执行错误留痕 |

### 2.5 图谱 `/api/graph`

#### GET `/api/graph/neighbors` —— 图谱邻居查询（可视化）

| 项 | 值 |
|---|---|
| 权限 | 已登录 |
| 查询参数 | `entity`（**必填**，1..64 字符，起始实体按 `Entity.name` 精确匹配）、`hops`（1..2，默认 2） |
| 成功响应 `data` | `{"entity", "hops", "degraded", "reason", "latency_ms", "nodes": [{"id", "entity_id", "name", "type"}], "edges": [{"source", "target", "relation", "chunk_ids", "confidence", "source_count"}]}` |
| 节点 `id` | Neo4j `elementId`（react-force-graph 直用） |
| 边数上限 | 400（单次查询 UI 渲染保护，`_EDGE_LIMIT` 实测） |
| 关系白名单 | `configs/triple_schema.json` `neo4j_relation_map` 的 11 种受控关系（Cypher 内插前经转义防注入） |
| 失败状态码 | 401、404（实体不存在 → `E_NOT_FOUND`）、422 |
| **降级语义** | Neo4j 不可达 → **200 + `degraded=true`**（附 `reason`），不作 502 打断监盘（路由文件 docstring 口径实测） |

### 2.6 知识库 `/api/knowledge/docs`

#### GET `/api/knowledge/docs` —— 文档列表

| 项 | 值 |
|---|---|
| 权限 | 已登录 |
| 查询参数 | `page`、`size`（§1.4）＋ `status`（pending/indexed/failed，非法 → 422）、`doc_type`（manual/work_order/procedure，非法 → 422） |
| 成功响应 `data.items[]` 行 | `{"doc_id", "title", "source", "doc_type", "device_model", "status", "admission_status", "created_at"}` |
| 排序 | `created_at DESC` |
| 失败状态码 | 401、422、502 |

#### POST `/api/knowledge/docs` —— 文档登记（上传占位）

| 项 | 值 |
|---|---|
| 权限 | **仅 `kb_admin`**（`require_roles("kb_admin")`） |
| 语义 | 本步只做「元数据登记 + `knowledge_versions` 留痕（action=create, actor=当前用户）」，status 置 `pending`；解析/分块/向量化由流水线任务推进（Phase 4 计划 §4.6 口径） |
| 成功响应 `data` | `{"doc_id": "<uuid>", "status": "pending", "note": "..."}` |
| 失败状态码 | 401、403（非 kb_admin）、422、502 |
| 事务性 | `documents` 插入与 `knowledge_versions` 留痕**同一事务**（两写同事务实测） |

请求体字段（`DocCreate`）：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `title` | str | ✅ | 1..200 字符 | 文档标题 |
| `doc_type` | str | ✅ | manual/work_order/procedure（代码二次校验，非法 → 422） | 文档类型 |
| `source` | str | ✅ | 1..100 字符 | 来源（如 供应商手册/工单系统） |
| `device_model` | str/null | ❌ | ≤100 字符 | 适用设备型号 |
| `content` | str/null | ❌ | ≤200,000 字符 | 可选正文文本；**仅用于计算 checksum（sha256），暂不分块**（未传时 checksum=sha256(title:doc_id)） |

#### POST `/api/knowledge/docs/{doc_id}/admission` —— 准入审核（一次性决策）

| 项 | 值 |
|---|---|
| 权限 | **仅 `kb_admin`** |
| 语义 | 防知识库投毒（R-M3，V5.0 §7.1）：pending → approved/rejected **一次性决策**，已决策再提交 → 409；双写同事务（`documents.admission_*` 三列 + `knowledge_versions` 留痕 action=`admission_approve`/`admission_reject`，version=max+1） |
| 成功响应 `data` | `{"doc_id", "admission_status": "approved"/"rejected", "admitted_by", "comment"}` |
| 失败状态码 | 401、403、404（文档不存在）、409（已决策）、422（action 非法 / doc_id 非法 UUID）、502 |

请求体字段（`AdmissionRequest`）：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `action` | str | ✅ | `approve` / `reject` | 准入决策 |
| `comment` | str | ❌ | ≤2000 字符，默认 `""` | 审核意见 |

### 2.7 诊断 `/api/diagnose` 与线程 `/api/threads`

#### POST `/api/diagnose` —— 发起诊断

| 项 | 值 |
|---|---|
| 权限 | `engineer` / `reviewer` / `sys_admin`（`_LAUNCH_ROLES` 实测） |
| 限流 | 是（§1.5，唯一限流端点） |
| 语义 | `alarm_id`（从 alerts 表取）与 `alarm`（内联对象）**二选一**（两者同给/同缺 → 422）；告警字段先过注入净化（`sanitize_state_inputs`），命中即审计 |
| 成功响应 `data` | `{"thread_id": "thr-<20位hex>", "status": "running", "note": "诊断已后台启动，进度经 GET /api/threads/{id} 或 Socket.IO diagnosis:progress 获取"}` |
| 失败状态码 | 401、403、404（alarm_id 不存在）、422、429（限流）、502 |

请求体字段（`DiagnoseRequest`）：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `alarm_id` | str/null | 二选一 | ≤64 字符 | 从 `alerts` 表按主键取告警 |
| `alarm` | dict/null | 二选一 | 须能构造 `AlarmEvent`（校验失败 → 422） | 内联告警对象 `{device_id, metric, value, ...}`；`device_id` 与 `metric` 为空 → 422 |

> 内联 `alarm` 对象以 `app/graph/state.py` `AlarmEvent` 为准：`{alarm_id="", device_id, metric, value:float=0.0, baseline:null, severity:"high"/"medium"/"low"（默认 medium）, ts:int(epoch ms)=0, rule_id:null, dedup_count:0}`。注意：内联告警 severity 走规则引擎词表（high/medium/low），与 `alerts` 表落库词表（info/warning/critical，经 `_SEV_PG_MAP` 映射）是**两套并存口径**（详见 `docs/prj-spec-data-dictionary.md` §四.1）。

#### GET `/api/threads/{thread_id}` —— 线程状态/进度

| 项 | 值 |
|---|---|
| 权限 | 已登录（任意角色） |
| 语义 | 内存注册表优先；服务重启后从 checkpointer 推断（回退分支返回部分字段为 null，`app/api/runner.py` `thread_status` 实测） |
| 成功响应 `data` | `{"thread_id", "status", "submitter", "alarm", "nodes_done": [], "report_id", "review_payload", "degrade_reason", "qa_log": [], "error", "started_at", "finished_at"}` |
| `status` 枚举 | `running` / `waiting_review` / `done` / `error`（`ThreadRecord` 实测） |
| `qa_log[]` 行 | `{"question", "answer", "citations", "user", "model", "ts"}`（chat:ask 追问留痕） |
| `review_payload` | interrupt 载荷（结构见 §三.3.4） |
| 失败状态码 | 401、404（线程不存在，含重启后 checkpointer 亦无线程）、422、502（状态存储不可用） |

#### POST `/api/threads/{thread_id}/ask` —— 对话式追问（REST twin）

| 项 | 值 |
|---|---|
| 权限 | `engineer` / `reviewer` / `sys_admin` |
| 语义 | 与 Socket.IO `chat:ask` 复用同一服务（`runner.ask_question`）；复用 thread 上下文不新建 thread；追问文本过注入检测；仅线程 `done`/`waiting_review` 态可追问（否则 409） |
| 成功响应 `data` | `{"answer": str(≤2000), "citations": [chunk_id]}`（本地 LLM 回答，无可用依据时 citations 为空数组并明确说明） |
| 失败状态码 | 401、403、404、409（诊断未完成）、422、502（推理/状态存储不可用）、500 |

请求体字段（`AskRequest`）：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `question` | str | ✅ | 1..2000 字符 | 追问内容 |

#### POST `/api/threads/{thread_id}/review` —— 审核提交主通道

| 项 | 值 |
|---|---|
| 权限 | **仅 `reviewer`** |
| 流程 | 等待态校验（非 waiting_review → 409）→ SoD（发起人不得自审 → 403）→ `ReviewLock` 并发锁（锁被他人持有 → 409）→ `Command(resume)` 恢复执行 → 图外幂等写入 → 释放锁（`runner.submit_review` 实测） |
| 成功响应 `data` | `{"status": "done", "report_id", "degrade_reason", "human_review"}` |
| 失败状态码 | 401、403、404（线程不存在或服务已重启）、409（非等待态 / 锁被占用）、422、500 |

请求体字段（`ReviewRequest`）：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `action` | str | ✅ | `approved` / `rejected`（**timeout 仅系统 watcher 触发**，`_REVIEW_ACTIONS` 实测） | 审核决策 |
| `comment` | str | ❌ | ≤2000 字符，默认 `""` | 审核意见（UI §6.3 驳回必填意见，通过亦建议留痕） |

#### POST `/api/reports/{report_id}/review` —— 审核别名（契约补丁）

| 项 | 值 |
|---|---|
| 权限 | **仅 `reviewer`** |
| 语义 | 由报告反查线程后**复用同一审核服务**；报告行在审核完成后才由 finalize 幂等写入，故本别名仅对「已存在报告且对应线程仍处等待态」可用，否则 409（路由 docstring 实测） |
| 请求体 | 与 §2.7 审核主通道相同（`ReviewRequest`） |
| 成功响应 `data` | 同上 |
| 失败状态码 | 401、403、404（报告不存在）、409（对应诊断不在等待审核状态）、422、500 |

### 2.8 审核队列 `/api/review`

#### GET `/api/review/pending` —— 审核队列

| 项 | 值 |
|---|---|
| 权限 | `reviewer` / `sys_admin` |
| 语义 | 进程注册表内 `waiting_review` 线程；**服务重启后队列清空**，以 `review:required` 事件回放为准（路由 docstring 口径实测） |
| 成功响应 `data` | `{"items": [{"thread_id", "submitter", "alarm", "review_payload", "waiting_since", "notified_4h"}], "total": <int>}` |
| `notified_4h` | bool：4h 备用审核人通知是否已触发（生命周期 watcher） |
| 失败状态码 | 401、403 |

### 2.9 根与运维（公开）

| 端点 | 方法 | 说明 | 响应 |
|---|---|---|---|
| `/api` | GET | 根包络（冒烟） | `data = {"service": "auscult-diagnosis-api", "version": "0.1.0"}` |
| `/metrics` | GET | Prometheus 抓取端点（`include_in_schema=False`） | 裸 exposition 格式，**无统一包络**；`/metrics` 自身不计入 HTTP 指标 |

---

## 三、Socket.IO 事件

### 3.1 连接方式与命名空间

| 项 | 实测值 | 出处 |
|---|---|---|
| 路径 | `/socket.io`（由 ASGIApp 接管，与 FastAPI 同端口 8000；Nginx 场景经 9763 WS 透传） | `app/api/main.py`、`docs/p4-handover-p5.md` D19 |
| 命名空间 | 默认 `/`（服务端未注册自定义 namespace） | `app/api/socket.py` |
| 连接鉴权 | `connect` 时 `auth={"token": <JWT>}`，无效（token 非法 / 用户不存在 / 已停用）即 `ConnectionRefusedError` 拒连 | `app/api/socket.py` `_connect` |
| 会话保持 | sid → 用户映射（`_sessions`），断开即清除 | 同上 |
| 跨域 | 环境变量 `SOCKETIO_ORIGINS` 白名单；**dev 默认 `*`**（本地 Next :3000 / Nginx 同源 9763），生产必须白名单 | 同上 L33-34 |
| 后台桥接 | `alarm:new` 轮询桥接（2s 间隔）与 runner 事件桥接，随 FastAPI lifespan 启动 | `app/api/main.py` `lifespan` |

### 3.2 事件总表（6 个业务事件）

| 事件名 | 方向 | 触发时机 | 代码位置 |
|---|---|---|---|
| `alarm:new` | S→C | 后台每 2s 轮询 PG `alerts` 表（游标推进，启动时不回放历史；单批 ≤100 条逐条 emit） | `app/api/socket.py` `_alarm_poller` |
| `diagnosis:progress` | S→C | LangGraph 逐节点推进（`graph.stream(stream_mode="updates")`） | 同上 `_emit_runner_event` ← `runner` 事件总线 |
| `diagnosis:done` | S→C | 诊断终态（**done 与 error 均以本事件发出**，以 `status` 字段区分；runner 的 `diagnosis:error` 事件在 socket 层转译为 `diagnosis:done` + `status="error"`） | 同上 |
| `review:required` | S→C | 高风险命中 → `interrupt()` 挂起，审核 payload 推送 | 同上 |
| `chat:ask` | C→S | 对话式追问（ack 回调返回统一包络） | 同上 `_chat_ask` |
| `review:submit` | C→S | 审核提交（与 REST `/api/threads/{id}/review` 同一服务） | 同上 `_review_submit` |

> 另有 `connect` / `disconnect` 两个生命周期钩子（非业务事件）。

### 3.3 各事件 payload 结构（emit/on 调用处实测）

**3.3.1 `alarm:new`（S→C）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `alarm_id` | str | 告警 ID（`{rule_id}:{device_id}:{metric}:{alert_start_ms}`） |
| `device_id` | str | 设备 ID |
| `metric` | str | 测点名 |
| `value` | float/null | 告警值（显式转 float；socketio 默认 JSON 序列化器不支持 Decimal，混入会被 emit 静默丢弃——代码注释实测） |
| `severity` | str | `info` / `warning` / `critical`（PG 落库词表） |
| `status` | str | `open`（当前唯一写入值） |
| `ts` | int/null | **epoch 毫秒**（显式 `int(ts.timestamp()*1000)` 转换，规避 datetime 序列化问题） |

**3.3.2 `diagnosis:progress`（S→C）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `thread_id` | str | 诊断线程 ID |
| `node` | str | 当前完成节点名 |
| `nodes_done` | list[str] | 已完成节点列表（累计） |
| `ts` | float | **epoch 秒**（`time.time()`；与 `alarm:new` 的毫秒口径不同，实测差异如实记录） |

**3.3.3 `diagnosis:done`（S→C）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `thread_id` | str | 诊断线程 ID |
| `status` | str | `done` / `error`（终态二值） |
| `report_id` | str/null | 报告 ID（`RPT-<16位hex>`） |
| `degrade_reason` | str/null | 降级原因（如 `review_rejected` / `review_timeout` / `budget_exceeded` / `cloud_unavailable`） |
| `ts` | float | epoch 秒 |
| `error` | str（可选） | 仅 `status="error"` 时附带 |

**3.3.4 `review:required`（S→C）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `thread_id` | str | 诊断线程 ID |
| `payload` | dict/null | interrupt 载荷，由 `app/graph/nodes/review.py` `_build_review_payload` 构造：`{thread_id, review_status:"pending", risk_level, diagnosis, root_causes[{cause,citations}], suggestions[{action,risk,citations}], evidence_count, confidence, risk_eval{needs_review,keywords_hit,operations_hit,reasons}, question, resume_hint}` |
| `ts` | float | epoch 秒 |

**3.3.5 `chat:ask`（C→S，ack 回调）**

| 请求字段 | 类型 | 必填 | 校验（ack 失败码实测） |
|---|---|---|---|
| `thread_id` | str | ✅ | 缺失 → ack `{code:"E_INVALID_ARG"}` |
| `question` | str | ✅ | 非空且 ≤2000 字符，超长 → `E_INVALID_ARG` |

| ack 返回 | 结构 |
|---|---|
| 成功 | `{"code": 0, "message": "ok", "data": {"answer": str, "citations": [chunk_id]}}` |
| 失败 | `{"code": <错误码>, "message": <人话消息>}`（未登录 `E_UNAUTHORIZED` / 线程不存在 `E_NOT_FOUND` / 未完成 `E_CONFLICT` / 推理不可用 `E_UPSTREAM` 等） |

**3.3.6 `review:submit`（C→S，ack 回调）**

| 请求字段 | 类型 | 必填 | 校验（实测） |
|---|---|---|---|
| `thread_id` | str | ✅ | 缺失 → `E_INVALID_ARG` |
| `action` | str | ✅ | 仅 `approved` / `rejected`（timeout 仅系统触发） |
| `comment` | str | ❌ | 截断至 2000 字符 |

| ack 返回 | 结构 |
|---|---|
| 成功 | `{"code": 0, "message": "ok", "data": {"status": "done", "report_id", "degrade_reason", "human_review"}}` |
| 失败 | 同 REST 审核主通道错误码；**socket 通道独立做 `reviewer` 角色校验**（非 reviewer → `E_PERMISSION`），SoD/并发锁语义与 REST 完全一致 |

### 3.4 时序图

```
告警 → 诊断 → 审核 全链路（Socket.IO 视角）：

 外部告警引擎        客户端                 服务端 Socket.IO            runner/图引擎
     │                │                        │                        │
     │ 落库 alerts     │                        │                        │
     │───────────────▶│ 2s 轮询桥接             │                        │
     │                │◀─── alarm:new ─────────│                        │
     │                │                        │                        │
     │                │── POST /api/diagnose ─▶│ (REST, 限流+RBAC)      │
     │                │◀─ {thread_id,running} ─│── start_diagnosis ────▶│
     │                │                        │                        │ 逐节点 stream
     │                │◀ diagnosis:progress ───│◀── 事件总线 subscribe ──│
     │                │◀ diagnosis:progress ───│                        │
     │                │                        │                  [高风险]
     │                │◀ review:required ──────│◀── interrupt payload ──│
     │                │                        │                        │ (挂起)
     │                │── POST /threads/{id}/review ─▶│ (REST 主通道)   │
     │                │   或 review:submit ───▶│ (socket 通道)          │
     │                │                        │── submit_review ──────▶│ SoD→锁→resume
     │                │◀ diagnosis:done ───────│◀── done 事件 ──────────│ 图外幂等写报告
     │                │                        │                        │
     │                │── chat:ask / POST ask ▶│── ask_question ───────▶│ checkpointer 取上下文
     │                │◀─ ack {answer,citations} │                      │ 本地 LLM 带引用回答
```

---

## 四、错误码汇总

错误码 → HTTP 状态码唯一映射处：`app/api/errors.py` `ERROR_STATUS`（实测全表）：

| 错误码 | HTTP | 语义 | 典型触发点 |
|---|---|---|---|
| `E_UNAUTHORIZED` | 401 | 未登录 / 会话失效 / 凭证无效或过期 / 账号停用 | `deps.get_current_user`、`auth.login`、socket `_connect` 拒连 |
| `E_PERMISSION` | 403 | 已登录但角色不符（RBAC）/ 职责分离拦截（发起人自审） | `deps.require_roles`、`runner.submit_review` |
| `E_NOT_FOUND` | 404 | 资源不存在（报告 / 告警 / 诊断线程 / 图谱实体） | 各路由 404 分支 |
| `E_CONFLICT` | 409 | 状态已变更（并发审核锁 / 幂等冲突 / 准入已决策 / 诊断未完成不能追问） | `runner.submit_review`、`knowledge.admit_doc`、`runner.ask_question` |
| `E_INVALID_ARG` | 422 | 请求参数校验失败（Pydantic / 业务校验 / bcrypt 72 字节上限） | `RequestValidationError` 统一转本码（data 含 errors 明细，最多 10 条） |
| `E_RATE_LIMITED` | 429 | 限流触发（令牌桶，仅 POST /api/diagnose）；响应附 `Retry-After` 头 | `app/security/rate_limit.py` |
| `E_INTERNAL` | 500 | 未分类服务端错误（兜底，不透出内部细节，trace_id 反查） | `main.fallback_handler` |
| `E_UPSTREAM` | 502 | 上游依赖不可用（PG / checkpointer / 本地推理） | `db.get_conn`、`runner.thread_status`、`ask_question` |
| `E_TIMEOUT` | 504 | 上游超时（已登记映射；当前代码路径未见主动抛出点【待确认，已登记 `ISS-038`（Q6 登记不修）】） | `errors.ERROR_STATUS` |

> `ApiError` 构造器强制错误码必须在 `ERROR_STATUS` 登记（未登记直接 ValueError），保证上表完备（`app/api/errors.py` 实测）。

---

## 五、与数据字典的对应关系

本节仅作指针，字段定义不在此重复，权威口径见 `docs/prj-spec-data-dictionary.md`：

| API 载荷 | 数据字典落点 |
|---|---|
| `GET /api/alarms` 列表行 / `alarm:new` payload | §二.5 `alerts` 表 7 列 |
| `GET /api/reports` 列表行 / 详情 / `diagnosis:done` 的 `report_id` | §二.7 `reports` 表 9 列（payload JSONB 快照结构见本文档 §2.4.3） |
| `GET /api/knowledge/docs` 列表行 / 文档登记 / 准入审核 | §二.1 `documents` 表 11 列（0001 建 8 列 + 0005 加 3 列准入）、§二.3 `knowledge_versions` 留痕 |
| `POST /api/knowledge/docs` checksum | §二.1 `documents.checksum`（sha256） |
| `GET /api/auth/*` / JWT payload `role` | §二.8 `users` 表（RBAC CHECK 约束四角色） |
| `alarm:new` 轮询源、`POST /api/diagnose` 的 `alarm_id` 反查 | §二.5 `alerts` 表 |
| `X-Trace-Id` 响应头 / 包络 `trace_id` | §二.9 `audit_logs.trace_id`（VARCHAR(32)）与 P5 审计双轨机制 |
| Socket.IO `chat:ask` 追问留痕 `qa_log` | 非持久化（内存注册表），重启即失【待确认：无落库路径，已登记 `ISS-041`（Q6 登记不修）】 |
| 图谱邻居查询节点/关系 | §三.3 Neo4j `Entity` 标签与 11 种受控关系 |

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D4 初版建立：`docs/prj-design-architecture.md` §七接口总览的详细展开版；全部字段/状态码/payload 离线静态实测自代码，与 D2 口径逐项核对一致 | `docs/prj-spec-api.md` |
