# Phase 3 验收汇总（D25 · M3.5）

| 项 | 值 |
|---|---|
| 阶段 | Phase 3：Agent 工作流实现 |
| 工期 | 25 天（D1–D25） |
| 执行日期 | 2026-10-09 |
| 判定 | **M3.5 ✅ 达成**（Trace/指标齐备；e2e 通过；移交 Phase 4） |

---

## 一、里程碑达成

| 里程碑 | 内容 | 出口条件 | 判定 |
|---|---|---|---|
| M3.1 | 图骨架与只读链路 | 四只读节点串联冒烟通过 | ✅ |
| M3.2 | 诊断与报告 | 结构化结论 + 报告落库（幂等） | ✅ |
| M3.3 | 置信度与混合推理 | 路由与熔断生效 | ✅ |
| M3.4 | 审核与可靠性 | 重启恢复 + 无重复副作用 + 并发安全 | ✅ |
| **M3.5** | **可观测与验收** | **Trace/指标齐备；e2e 通过；移交 Phase 4** | **✅** |

---

## 二、交付物清单

### 2.1 核心代码

| 模块 | 文件 | 职责 |
|---|---|---|
| 图骨架 | `app/graph/build.py` | StateGraph 组装 + 条件路由（五档优先级） |
| 状态类型 | `app/graph/state.py` | DiagnosisState + 6 子类型 |
| Checkpointer | `app/graph/checkpointer.py` | PG Checkpointer 工厂（contextmanager） |
| parse_alarm | `app/graph/nodes/parse_alarm.py` | 确定性规则解析告警 |
| analyze_sensor | `app/graph/nodes/analyze_sensor.py` | 传感器数据分析 |
| retrieve_evidence | `app/graph/nodes/retrieve_evidence.py` | 知识检索 + 图谱推理 |
| get_history | `app/graph/nodes/get_history.py` | 历史工单查询 |
| diagnose | `app/graph/nodes/diagnose.py` | deepseek-r1:7b + 置信度公式 + ECE 校准 |
| finalize | `app/graph/nodes/finalize.py` | 证据校验 + 幂等键 + report_id 生成 |
| degrade | `app/graph/build.py` | 降级节点（degrade_reason 传递） |
| escalate_cloud | `app/graph/nodes/escalate_cloud.py` | 云端升级节点 |
| human_review | `app/graph/nodes/review.py` | 确定性规则 + interrupt + 审核状态机 |
| 云端路由 | `app/router/cloud.py` | 脱敏 + 调用 + 审计 + 预算 |
| 预算熔断 | `app/router/budget.py` | Redis 按天计数 + 熔断 + 降级 |
| 审核生命周期 | `app/review/lifecycle.py` | 并发锁 + 4h 通知 + 24h 超时 + 职责分离 |
| 幂等写入 | `app/report/idempotency.py` | 图外幂等写入 PG reports 表 |
| Trace | `app/observability/tracing.py` | Langfuse Trace 全覆盖（span + LLM + 工具） |
| 指标 | `app/observability/metrics.py` | 节点 P95 + 置信度分布 + 升降级率 + 审核覆盖率 |
| 安全 | `app/security/sanitizer.py` | Prompt 注入防御 + 工具白名单 + 审计落库 |

### 2.2 配置

| 文件 | 用途 |
|---|---|
| `configs/risk_rules.yml` | 24 高风险关键词 + 15 操作类型 + 审核策略 |
| `configs/redis.conf` | noeviction + AOF + requirepass |
| `env/cloud.json` | 云端模型 + 预算上限 |
| `db/migrations/0003_reports.sql` | reports 表 + 幂等唯一索引 |

### 2.3 测试

| 脚本 | 覆盖 | 结果 |
|---|---|---|
| `scripts/test_d14_escalate_cloud.py` | 脱敏/超时/降级/审计 | 8/8 PASS |
| `scripts/test_d15_budget.py` | 预算熔断/条件边全量 | 8/8 PASS |
| `scripts/test_d16_review.py` | 规则判定/审核节点 | 8/8 PASS |
| `scripts/test_d17_resume.py` | 审核状态机/resume | 11/11 PASS |
| `scripts/test_d18_lifecycle.py` | 并发锁/超时/职责分离 | 11/11 PASS |
| `scripts/test_d19_idempotency.py` | 幂等键/图外写入 | 9/9 PASS |
| `scripts/test_d20_reliability.py` | 杀进程恢复/重复 resume/noeviction | 12/12 PASS |
| `scripts/test_d21_tracing.py` | Trace/span/LLM/工具/嵌套 | 10/10 PASS |
| `scripts/test_d22_metrics.py` | P95/分布/比率/快照/聚合 | 11/11 PASS |
| `tests/e2e/test_e2e_scenarios.py` | E1–E6 端到端场景 | 7/7 PASS |
| `scripts/test_d24_security.py` | 注入检测/白名单/审计 | 11/11 PASS |
| **总计** | | **106/106 PASS** |

### 2.4 报告

| 文件 | 内容 |
|---|---|
| `reports/p3-reliability.md` | D20 可靠性测试报告 |
| `reports/p3-summary.md` | 本文件（Phase 3 验收汇总） |
| `docs/handover-p4.md` | Phase 3→4 移交清单 |

---

## 三、端到端场景覆盖（plan §8.2）

| 场景 | 描述 | 测试脚本 | 结果 |
|---|---|---|---|
| E1 | 主场景：离心泵轴承振动（中风险） | D23 test_e2e | ✅ |
| E2 | 高风险（涉及停机）→ interrupt + resume | D23 test_e2e | ✅ |
| E3 | 低置信度（<0.5）→ 降级 | D23 test_e2e | ✅ |
| E4 | 中置信度 + 云端可用 → 升级成功 | D23 test_e2e | ✅ |
| E5 | 中置信度 + 云端不可用 → 离线降级 | D23 test_e2e | ✅ |
| E6 | 工具超时 → 重试 ≥3 → 降级 | D23 test_e2e | ✅ |
| E7 | 服务重启于审核中 → 状态完整 | D20 reliability | ✅ |
| E8 | 双审核人并发 resume → 1 份报告 | D20 reliability | ✅ |
| E9 | 审核超时 → 4h 通知 / 24h 降级 | D18 lifecycle | ✅ |
| E10 | Prompt 注入 → 被净化拦截 | D24 security | ✅ |

---

## 四、M3.5 出口判定

| 出口条件 | 对应交付 | 判定 |
|---|---|---|
| Trace 齐备 | D21 `tracing.py`（span + LLM + 工具 + 嵌套） | ✅ 10/10 PASS |
| 指标齐备 | D22 `metrics.py`（P95 + 分布 + 比率 + 快照） | ✅ 11/11 PASS |
| e2e 通过 | D23 E1–E6 + D20 E7–E9 + D24 E10 | ✅ 10/10 场景 |
| 安全加固 | D24 `security/sanitizer.py` | ✅ 11/11 PASS |
| 移交 Phase 4 | `docs/handover-p4.md` | ✅ |

**M3.5 ✅ 达成。**

---

## 五、已知问题（转 P1）

| ID | 问题 | 影响 | 处置 |
|---|---|---|---|
| ISS-D20-1 | PG checkpoint 反序列化 Pydantic 类型警告 | 非阻塞（功能正常） | P1 注册 `allowed_msgpack_modules` |
| ISS-D20-2 | D19 测试用固定 thread_id 导致残留 | 测试可重复性 | P1 改用 uuid thread_id |

---

## 六、Phase 3 技术栈

| 组件 | 版本 | 用途 |
|---|---|---|
| LangGraph | 1.2.12 | StateGraph + Checkpointer |
| langgraph-checkpoint-postgres | 3.1.2 | PG 持久化 |
| PostgreSQL 18.6 | ParadeDB | checkpoint + reports |
| Redis 8 | noeviction + AOF | 预算 + 审核锁 |
| Ollama deepseek-r1:7b | Q4_K_M | 本地诊断 |
| ModelScope Qwen3.8-27B | 云端 | 云端升级 |
| Python | 3.12 | 运行时 |

---

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-09 | v1 | Phase 3 验收汇总，M3.5 达成，106/106 PASS |
