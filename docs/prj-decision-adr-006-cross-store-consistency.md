# ADR-006：跨存储一致性 —— Outbox + 对账（PostgreSQL 唯一权威源）

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：Outbox + 对账机制于 `plan/工业设备诊断 Agent.md` §6.3 定稿（2026-09-21，V5.0 定稿，为补齐"跨存储一致性无补偿"的结构性缺失；对应风险 R-M1）；工程实装与锁版为 P1（2026-10-08~09，`docs/prj-ledger-version-lock.md` §二.2.13）。

## 二、背景（Context）

- 离线知识构建流需**三写一致**：PostgreSQL（元数据/版本）+ Milvus（向量）+ Neo4j（三元组）；任一存储静默缺数据都会造成检索证据缺失且难排查（`plan/工业设备诊断 Agent.md` §4.3 数据流①、§8.2 R-M1"多存储一致性（静默缺数据）"）。
- 跨库无分布式事务，必须有**可补偿、可对账**的最终一致机制（同上 §6.3）。

## 三、决策（Decision）

**采用 Outbox + 每日对账双机制；PostgreSQL 为唯一权威源。**

### 3.1 Outbox 五步流程（出处：`plan/工业设备诊断 Agent.md` §6.3）

```
① 写入 PostgreSQL（document, status='pending'）
② 后台 Worker 消费 → 写入 Milvus（向量）+ Neo4j（三元组）
③ 全部成功 → document.status='indexed'；任一失败 → status='failed' + 入补偿队列
④ 补偿队列：指数退避重试，≥5 次 → 告警人工介入
⑤ 每日对账脚本：比对 PG / Milvus / Neo4j 的 doc_id 集合，输出差异报告
```

### 3.2 权威源定义（同上 §6.3）

| 存储 | 角色 |
|---|---|
| **PostgreSQL** | **唯一权威源**（元数据/状态） |
| Milvus / Neo4j | 可重建索引（以 PG 为准重建） |
| Redis | 仅承载运行态，非权威 |

### 3.3 落地现状

| 组件 | 落地 | 出处 |
|---|---|---|
| 表 | `outbox`（11 列，含 1 部分索引）/ `documents`（11 列，被 `doc_chunks` 显式外键引用）随 `db/migrations/0001_init.sql` 建立 | `docs/prj-spec-data-dictionary.md` §二（表 1/表 6） |
| 写入侧 | `scripts/load_meta.py`：与三表**同事务幂等补写** outbox（无唯一约束，故"先查后插"判重，重复导入不重复插）；每 chunk 两条 outbox（`target=milvus, op=upsert` / `target=neo4j, op=verify`） | `scripts/load_meta.py` 文件头与 `write_outbox_idempotent`/`build_outbox_rows` |
| 消费/对账 | `scripts/outbox_worker.py`（消费）、`scripts/reconcile.py`（对账）；P1 判据 =「失败注入下对账零差异、补偿队列可自愈」 | `scripts/load_meta.py` 文件头（§5.9 / 出口 §1.2 口径）；`docs/prj-ledger-version-lock.md` §二.2.13（P1 B4–B6/D9 图谱与一致性链路锁版） |

## 四、备选方案与放弃理由（Options & Rejected）

| 备选 | 放弃理由 | 出处 |
|---|---|---|
| 仅靠每日对账、不做 Outbox | 对账只能"发现"差异，无逐条补偿通道；失败注入下无法自愈，R-M1"静默缺数据"风险未被覆盖 | `plan/工业设备诊断 Agent.md` §8.2 R-M1（应对 = Outbox + 对账脚本，二者配套） |
| 同时直写三库（双写/多写，无 Outbox） | 跨库无事务，部分失败即产生不一致且无重放依据；Outbox 以"先落权威源 + 事务内登记意图"消除该窗口 | `plan/工业设备诊断 Agent.md` §6.3 流程设计（① 必须先落 PG） |
| 以 Milvus/Neo4j 为权威源 | 二者为**可重建索引**，不具备状态/版本语义；权威源定为 PG | 同上 §6.3 权威源定义 |

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | 最终一致可补偿（指数退避 + ≥5 次人工介入兜底）；权威源唯一， Milvus/Neo4j 可随时以 PG 重建；对账差异报告可审计 |
| ⚠️ 负面 | 写入路径多一跳（先 PG 后异步消费），知识构建非即时可见；补偿 ≥5 次需人工介入，存在滞留窗口 |
| 📎 已知边界 | 对账为每日快照口径，非实时强一致；outbox 表无唯一约束，判重依赖应用层"先查后插"（`scripts/load_meta.py`，重复导入防护已实现但非 DB 级保证） |

## 六、事实源

- `plan/工业设备诊断 Agent.md` §4.3、§6.3、§8.2（R-M1）
- `docs/prj-spec-data-dictionary.md` §二
- `docs/prj-ledger-version-lock.md` §二.2.13
- `scripts/load_meta.py`、`scripts/outbox_worker.py`、`scripts/reconcile.py`
- `db/migrations/0001_init.sql`

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版 | 本文件 |
