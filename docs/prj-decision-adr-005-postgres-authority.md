# ADR-005：PostgreSQL 18 为唯一权威业务库（不引入 MongoDB）

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：数据库选型于 `plan/工业设备诊断 Agent.md` §3.10 定稿（2026-09-21，V5.0 定稿）；本 ADR 补充 9 表 74 列落库现状指针。

## 二、背景（Context）

- 业务库需承载**报告 / 审核 / 审计 / 用户权限**，核心诉求 = **强事务 + 强一致 + 复杂关联查询 + 审计不可篡改**（`plan/工业设备诊断 Agent.md` §3.10 需求画像）。
- 专业化数据已各有归属：时序 → TDengine、向量 → Milvus、图谱 → Neo4j、运行态 → Redis，业务库不重复承担（同上）。
- MongoDB 与 PostgreSQL 须做一次明确对比裁决，避免"为灵活多养一个库"。

## 三、决策（Decision）

**采用 PostgreSQL 18 作为唯一权威业务库；不引入 MongoDB。** 版本/镜像 digest 以 `docs/prj-ledger-version-lock.md` §二.2.1 为准（不抄写）。

五条定稿理由（出处：`plan/工业设备诊断 Agent.md` §3.10 结论）：

| # | 理由 |
|---|---|
| 1 | 强 ACID 支撑报告状态机与审核流转 |
| 2 | 多表 JOIN 远比聚合管道自然 |
| 3 | 审计可用**追加表 + 禁改触发器**落地 |
| 4 | 灵活字段用 **JSONB + GIN** 即可（如 `reports.payload`） |
| 5 | 本机已 pull `postgres:18`，零额外成本 |

### 3.1 落库现状指针（9 表 74 列）

| 项 | 现状 | 出处 |
|---|---|---|
| 表规模 | **9 张业务表、74 列、13 个索引（含 1 唯一 + 2 部分索引）、1 个显式外键、3 个防篡改触发器**；迁移 0001/0003/0004/0005/0006（无 0002，编号跳过属仓库现状） | `docs/prj-spec-data-dictionary.md` §二（2026-10-10 D4 实测自迁移文件） |
| 审计不可篡改 | `audit_logs` append-only 触发器（UPDATE/DELETE/TRUNCATE 全拒），P5 安全回归实测通过 | `docs/p5-handover-p6.md` §一 M5.3；`db/migrations/0006_audit_logs.sql` |
| 实例与库 | PG 18 @ 宿主 5433，库 `auscult_v2`；连接串与 checkpointer 同源（`API_PG_URL`/`LANGGRAPH_PG_URL`） | `docs/prj-spec-data-dictionary.md` §二；`app/api/config.py` |
| 迁移纪律 | 全部迁移幂等（`IF NOT EXISTS`） | `docs/prj-spec-data-dictionary.md` §二 |

## 四、备选方案与放弃理由（Options & Rejected）

| 备选 | 放弃理由 | 出处 |
|---|---|---|
| **MongoDB 作业务库** | 六维对比：事务开销较大（4.0+ 多文档 ACID）、跨集合 JOIN 弱、默认偏最终一致——强事务/强关联/强一致/审计不可篡改恰全落其弱项；"MongoDB 更合适的边界"四条（大规模半结构化日志、Schema 频繁变更、跨分片水平扩展、嵌套为主无关联）**本项目均不成立** | `plan/工业设备诊断 Agent.md` §3.10 六维对比表与边界段 |
| pgvector 替代 Milvus（顺带裁决） | 仅作"峰值 > 28GB 严重超限"时的**降级路径**保留（Milvus Lite 或 pgvector），非主选；主路线混合检索已实测达标 | `plan/工业设备诊断 Agent.md` §3.5 降级映射表 |

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | 单一权威源支撑 Outbox 对账（ADR-006）、checkpoint 落库（ADR-008）、报告幂等（ADR-007）；审计防篡改有 DB 级保证；JSONB 覆盖灵活字段，避免多养一个文档库 |
| ⚠️ 负面 | 水平扩展能力弱于 MongoDB（垂直为主，水平需 Citus）——单机小数据量场景下不成立，但规模增长后需重评 |
| 📎 已知边界 | 数据库访问层 `psycopg_pool` 连接池替换每请求短连接为 P6 遗留（压测 0.01% 瞬时建连失败触发预留升级条件）（`docs/p5-handover-p6.md` §五 F-2）；RPO 持续达成依赖每日定时备份（同上 §五 第 4 条，`reports/p5-backup.md`） |

## 六、事实源

- `plan/工业设备诊断 Agent.md` §3.5、§3.10
- `docs/prj-spec-data-dictionary.md` §二
- `docs/prj-ledger-version-lock.md` §二.2.1
- `docs/p5-handover-p6.md` §一、§五
- `app/api/config.py`；`db/migrations/0001_init.sql`、`0003_reports.sql`、`0004_users.sql`、`0005_knowledge_admission.sql`、`0006_audit_logs.sql`

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版 | 本文件 |
