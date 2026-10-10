# Phase 3 → Phase 4 移交清单

| 项 | 值 |
|---|---|
| 移交方 | Phase 3（Agent 工作流实现） |
| 接收方 | Phase 4（前端与集成） |
| 移交日期 | 2026-10-09 |
| 前置条件 | M3.5 ✅ 达成（Trace/指标齐备；e2e 通过） |

---

## 一、移交物核对

### 1.1 Agent 工作流（可直接调用）

| 组件 | 入口 | 说明 |
|---|---|---|
| LangGraph Agent | `app.graph.build.build_graph(checkpointer)` | 9 节点 + 条件路由（五档优先级） |
| PG Checkpointer | `app.graph.checkpointer.build_checkpointer()` | contextmanager，PG 5433 |
| 图执行 | `graph.invoke(initial, config)` / `graph.invoke(Command(resume=...), config)` | 支持 interrupt/resume |
| 图外报告写入 | `app.report.idempotency.generate_report(state_dict)` | 幂等写入 PG reports 表 |
| 审核恢复 | `app.review.lifecycle.auto_timeout_resume(graph, config, thread_id)` | 24h 超时自动降级 |

### 1.2 条件路由（五档优先级，首个命中生效）

| 优先级 | 条件 | 目标节点 |
|---|---|---|
| 1 | retry_count >= 3 | degrade |
| 2 | confidence < 0.50 | degrade |
| 3 | confidence < 0.75 | escalate_cloud |
| 4 | risk_level == "high" | human_review (interrupt) |
| 5 | else | finalize |

### 1.3 可观测（前端可直接消费）

| 模块 | API | 输出 |
|---|---|---|
| Trace | `app.observability.tracing.Tracer` | `reports/traces/{trace_id}.jsonl` |
| 指标 | `app.observability.metrics.MetricsCollector.snapshot()` | `reports/metrics/{date}.jsonl` |
| 安全审计 | `app.security.sanitizer.log_security_event()` | `reports/security_audit.jsonl` |
| 审核审计 | `app.review.lifecycle._audit()` | `reports/review_audit.jsonl` |
| 云端审计 | `app.router.cloud.write_audit()` | `reports/cloud_audit.jsonl` |

### 1.4 安全

| 模块 | API | 说明 |
|---|---|---|
| 输入净化 | `sanitize_input(text)` / `sanitize_state_inputs(state)` | 4 类注入模式检测+中和 |
| 工具白名单 | `validate_tool_call(tool)` / `validate_tool_args(tool, args)` | 5 个合法工具 |
| 审计 | `log_security_event()` / `audit_injection_attempt()` / `audit_tool_call()` | 安全事件落库 |

### 1.5 数据库

| 表 | 用途 | 迁移文件 |
|---|---|---|
| checkpoints | LangGraph checkpoint | PostgresSaver.setup() |
| checkpoint_writes | checkpoint 写入 | 同上 |
| checkpoint_blobs | checkpoint blob | 同上 |
| reports | 诊断报告（幂等） | 0003_reports.sql |
| alerts | 告警事件 | 0001_init.sql |
| work_orders | 工单 | 0001_init.sql |
| documents / doc_chunks | 知识库 | 0001_init.sql |
| outbox | 一致性 | 0001_init.sql |

### 1.6 配置

| 文件 | 用途 |
|---|---|
| `configs/risk_rules.yml` | 高风险关键词(24) + 操作类型(15) + 审核策略 |
| `configs/redis.conf` | noeviction + AOF + requirepass |
| `env/cloud.json` | 云端模型(Qwen3.8-27B) + 预算上限(340/天) |

---

## 二、Phase 4 对接要点

### 2.1 前端调用 Agent

```python
# 构建 + 执行
with build_checkpointer() as saver:
    graph = build_graph(saver)
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial, config=config)
    # 如挂起在 human_review → 等待前端 resume
    # result["report_id"] 可直接使用（finalize 已生成）
    # 图外幂等写入：
    write_result = generate_report(result)
```

### 2.2 审核界面

- 挂起检测：`graph.get_state(config).next == ("human_review",)`
- resume 提交：`graph.invoke(Command(resume={"action": "approved"|"rejected", "comment": ..., "reviewer_id": ...}), config=config)`
- 并发锁：`ReviewLock().acquire(thread_id, reviewer_id)` / `.release(thread_id, reviewer_id)`
- 职责分离：`validate_submitter(reviewer_id, submitter_id)`

### 2.3 可观测仪表盘

- Trace 文件：`reports/traces/{trace_id}.jsonl`（每行一个 span/llm/tool/event）
- 指标快照：`MetricsCollector().snapshot()` → JSON 可直接渲染图表
- 安全审计：`reports/security_audit.jsonl`

### 2.4 报告查询

```python
from app.report.idempotency import get_report, report_exists
report = get_report("RPT-xxxxxxxxxxxxxxxx")
```

---

## 三、遗留转 P4 / P1

| 项 | 归属 | 说明 |
|---|---|---|
| Trace 接入各节点 | P4 D1-D5 | 各节点加 @trace_node 装饰器 + log_llm/log_tool |
| 指标采集接入 | P4 D1-D5 | 路由/审核/置信度事件 → MetricsCollector |
| 安全净化接入图 | P4 D1-D5 | diagnose/cloud prompt 前调用 sanitize_input |
| ISS-D20-1 反序列化警告 | P1 | 注册 allowed_msgpack_modules |
| ISS-D20-2 测试残留 | P1 | D19 改用 uuid thread_id |
| Langfuse 服务端 | P4+ | 当前轻量自研，后续可切 Langfuse SDK |
| degrade 节点完善 | P4 | 当前仅传 degrade_reason，可扩展降级策略 |

---

## 四、环境要求

| 组件 | 端口 | 容器 |
|---|---|---|
| PostgreSQL 18.6 | 5433 | auscult-v2-pg |
| Redis 8 | 6379 | auscult-redis |
| Ollama | 11434 | 宿主进程 |
| Milvus | 19531 | auscult-v2-milvus |
| Neo4j | 7687 | auscult-neo4j |
| Nginx（Phase 4 新增） | 9763 | 待 Phase 4 部署 |

---

## 五、测试命令

```powershell
# Phase 3 全量回归（106 项）
.venv\Scripts\python.exe scripts\test_d14_escalate_cloud.py
.venv\Scripts\python.exe scripts\test_d15_budget.py
.venv\Scripts\python.exe scripts\test_d16_review.py
.venv\Scripts\python.exe scripts\test_d17_resume.py
.venv\Scripts\python.exe scripts\test_d18_lifecycle.py
.venv\Scripts\python.exe scripts\test_d19_idempotency.py
.venv\Scripts\python.exe scripts\test_d20_reliability.py
.venv\Scripts\python.exe scripts\test_d21_tracing.py
.venv\Scripts\python.exe scripts\test_d22_metrics.py
.venv\Scripts\python.exe tests\e2e\test_e2e_scenarios.py
.venv\Scripts\python.exe scripts\test_d24_security.py
```

前置：PG（5433）、Redis（6379）、Ollama（11434）运行中。

---

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-09 | v1 | Phase 3→4 移交清单，M3.5 达成 |
