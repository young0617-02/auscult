# ADR-008：Checkpoint 存储选型（PostgreSQL PostgresSaver）与 noeviction / 无 TTL 纪律

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：checkpoint 方案裁决实为 **P0 产物**（M0.4 / V5 验证项，2026-09-24 实测定稿），决策载体 `docs/p0-decision-checkpoint.md`。本 ADR 为 Phase 6 D5 的 ADR 化登记：**引用而不重复**——候选对比、Redis 配置逐项理由、降级触发 B1–B7、体积治理、多实例决策一律见上游文件。

## 二、背景（Context）

- 诊断流程跨 `interrupt()` 人工审核、可能**跨天**；进程/容器重启后必须**状态不丢、恢复后不重复干活、不因"过期/内存不足"静默丢审核中状态**（`docs/p0-decision-checkpoint.md` §一 四条保证）。
- LangGraph 官方 checkpointer 有 PostgreSQL / SQLite 实现，社区另有 Redis 第三方实现（候选 A 默认），须实测裁决。

## 三、决策（Decision）

**采纳候选 B：PostgreSQL checkpointer（`langgraph-checkpoint-postgres`，LangGraph 官方实现），弃用候选 A（Redis 第三方 checkpointer）。**

| 项 | 指针（详见上游，此处不重复） |
|---|---|
| 三候选对比表（实现来源 / 完整性 / 幂等 / 并发 / 体积 / 运维）与对比结论 | `docs/p0-decision-checkpoint.md` §二、§2.1 |
| 候选 A 弃用根因 **B7**（redis-py↔redis-stack 连接握手被服务端关闭，非"缺 RediSearch"） | 同上 §2.1 降级行 |
| Redis 配置定稿与逐项理由（`appendonly yes` / `maxmemory 1gb` / **`noeviction`** / **不设 TTL** / `appendfsync everysec`；候选 A 留档 `configs/redis.conf`） | 同上 §三 |
| 降级触发标准 B1–B7 与执行清单 | 同上 §五 |
| 体积治理与多实例决策（审核完成即归档、保留上限 N=20、默认单实例） | 同上 §七、§八 |

### 3.1 noeviction / 无 TTL 纪律的现状口径

| 层面 | 口径 | 出处 |
|---|---|---|
| PG 路线（采纳） | checkpoint 落 PG 表（`checkpoints` / `checkpoint_writes` / `checkpoint_blobs`），**天然无驱逐/无 TTL 语义**，实测无丢状态（B5） | `docs/p0-decision-checkpoint.md` §6.1 T5.7；`app/graph/checkpointer.py` |
| Redis 层（运行态） | 实例级 `maxmemory-policy=noeviction` + checkpoint 类 key 不设 TTL 的纪律随候选 A 决策一并成文（§三 逐项理由与 §3.3 Key 规范）；PG 路线下 Redis 仅承载运行态（`sess:`/`dedup:`/`cache:`/`lock:review:`/`budget:cloud:`，各自 TTL 见 Key 规范表） | `docs/p0-decision-checkpoint.md` §三、§3.3；`plan/工业设备诊断 Agent.md` §5.7 |

### 3.2 落地与 V5 实测口径（补引）

| 项 | 实测值 | 出处 |
|---|---|---|
| 代码落地 | `PostgresSaver.from_conn_string(...)` + `saver.setup()`（幂等建表）；依赖 `langgraph-checkpoint-postgres==3.1.2`（候选 A `langgraph-checkpoint-redis==0.5.2` 已锁未采用，仅留复现 B7 与审计） | `app/graph/checkpointer.py`；`requirements.txt`；`docs/prj-ledger-version-lock.md` §二.2.9 |
| 重启恢复完整性 | 五字段齐全率 **100%**，payload 无差异（EXP-V5-003） | `docs/p0-decision-checkpoint.md` §6.1/§6.2 |
| 重复副作用 | **重复落库 0 次**（EXP-V5-004，幂等键拦住；详见 `docs/prj-decision-adr-007-write-outside-graph.md`） | 同上 |
| 单 thread 体积 | **296KB/thread**（4 表 29/55/29/10 行），有界可归档，上限基线 ≤1MB/thread（EXP-V5-006） | 同上 §6.2；`reports/p0-report-v5-checkpoint.md` |

## 四、备选方案与放弃理由（Options & Rejected）

| 备选 | 放弃理由 | 出处 |
|---|---|---|
| 候选 A：Redis checkpointer（第三方实现） | **B7 阻塞**：redis-py↔redis-stack 握手被服务端关闭，属"无法规避的兼容性缺陷"；且并发安全未经验证 | `docs/p0-decision-checkpoint.md` §二 对比表、§2.1、§五 B7 |
| 候选 C：文件/本地 SQLite checkpointer（官方） | **不支持多实例**（单文件锁）；仅极简单机场景备选 | 同上 §二 候选 C 列 |

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | 官方实现可持续维护；PG 行刀天然支持多实例；与"PG 唯一权威源"（`docs/prj-decision-adr-005-postgres-authority.md`）同栈，备份链路统一（P5 备份演练 RTO 3.1s） |
| ⚠️ 负面 | checkpoint 写入增加 PG 负载（实测总 DB ≈8.66MB，可接受）；磁盘路线慢于内存（本地单线程秒级、无感知阻塞）；PG 表管理/清理策略需运维 |
| 📎 已知边界 | 默认**单实例**（P0 结论）：若 Phase 1+ 需多实例，须先验证 checkpoint 并发安全（`docs/p0-decision-checkpoint.md` §八）；`ISS-015`（Redis 容器形态无鉴权暴露面）登记在案，P1 起改 `requirepass`（同上 §三 网络段风险） |

## 六、事实源

- `docs/p0-decision-checkpoint.md`（上游决策载体：§二/§2.1、§三/§3.3、§五、§六、§七、§八）
- `plan/工业设备诊断 Agent.md` §5.7、§6.4、§8.1（R11）
- `app/graph/checkpointer.py`；`requirements.txt`
- `docs/prj-ledger-version-lock.md` §二.2.9
- `reports/p0-report-v5-checkpoint.md`
- `docs/p5-handover-p6.md` §一 M5.3（备份演练）

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版（ADR 化登记，引用 `docs/p0-decision-checkpoint.md` 不重复；补 V5 实测口径指针） | 本文件 |
