# ADR-007：写操作移出图内 + 幂等键

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：写操作位置与幂等设计于 `plan/工业设备诊断 Agent.md` §6.4 定稿（2026-09-21，V5.0 定稿；对应风险 R12"恢复后重复副作用"），详细论证与实测载体为 `docs/p0-decision-checkpoint.md` §四（P0 · M0.4，2026-09-24）。本 ADR 与 ADR-008（checkpoint 存储）同源不同面：本 ADR 聚焦**写操作位置与幂等**，存储选型见 `docs/prj-decision-adr-008-checkpoint-store.md`。

## 二、背景（Context）

- 诊断流程是**长流程 + 人工审核**图：`interrupt()` 挂起等人审核、可能跨天；期间进程可被杀、容器可重启，恢复时 LangGraph 可能**重放节点**（`plan/工业设备诊断 Agent.md` §6.4；`docs/p0-decision-checkpoint.md` §一）。
- **只读工具重跑无害**（天然幂等，最多再查一次）；**写操作重跑有副作用**（重复生成报告、重复落库、重复通知）——两者必须区别处置（`docs/p0-decision-checkpoint.md` §4.1）。

## 三、决策（Decision）

| # | 决策项 | 定稿口径 |
|---|---|---|
| 1 | 图内只保留只读工具 | `query_sensor` / `search_knowledge`（`retrieve_knowledge`）/ `query_graph` / `get_maintenance_history`——只读、天然幂等，可安全享受断点续跑 |
| 2 | **写操作移出图内** | `generate_report` 置于 `interrupt()` 审核**之后**，由图外（API 层）显式调用一次：调用点唯一、可控、可单测 |
| 3 | 写携带幂等键 | `idempotency_key = sha256(thread_id + report_type + content_digest + schema_version)`，PostgreSQL 唯一索引去重 |

### 3.1 幂等键设计要点（出处：`docs/p0-decision-checkpoint.md` §4.3，不重复展开）

- `thread_id` 天然唯一；`report_type` 区分同 thread 多类报告；`content_digest` 保证同内容不重复落库；`schema_version` 使 Schema 升版视为新报告（仅用 `thread_id` 或仅用内容 hash 均会误判）。
- 写入方式 `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING id`：有返回 = 首次；无返回 = 重复（**直接复用同一 `report_id`，不报错**，上游无感知）。
- **幂等范围**仅覆盖报告生成与落库；通知发送、外部推送等外部副作用须另行幂等。

### 3.2 执行时序（出处：`docs/p0-decision-checkpoint.md` §4.2）

```
[图内] 告警解析 → 只读工具（可安全重放）→ 诊断推理 → interrupt()（高风险强制审核，checkpoint 落盘）
（人工审核：通过 / 驳回，经 Command(resume=...) 恢复）
[图外] generate_report（携带 idempotency_key，PG 唯一索引去重）→ 审核记录落库 + 审计追加
```

### 3.3 落地与实测

| 项 | 内容 | 出处 |
|---|---|---|
| 代码落地 | `app/report/idempotency.py`（幂等键）；审核提交主通道 `app/api/routes/review.py`（resume 后图外写）；SoD 与并发锁 `app/review/lifecycle.py` | `docs/prj-design-architecture.md` §5.3 |
| V5 实测 | **重复落库 0 次**（幂等键拦住，B3=True）、只读工具重放 2 次（设计允许）；双审核人多 resume **仅产 1 份报告** | `docs/p0-decision-checkpoint.md` §6.1（EXP-V5-004 / EXP-V5-003-T）、§6.2；`reports/p0-report-v5-checkpoint.md` |

## 四、备选方案与放弃理由（Options & Rejected）

| 备选 | 放弃理由 | 出处 |
|---|---|---|
| 写操作留在图内 + 幂等键 | 图内节点重跑次数与时机由 framework 控制、**应用不可掌控**；checkpoint 恢复可能重放多个节点，幂等键全靠应用层每次正确构造，出错概率高 | `docs/p0-decision-checkpoint.md` §4.4 方案对比表 |
| 写操作移出图内但**无幂等键** | 依赖"图外只调一次"，但网络重试、进程重启后重放仍可能重复 → 幂等键不能省 | 同上（判"勉强可行"，不采纳为定稿） |
| 写操作留图内、仅靠 checkpoint 幂等 | 同备选 1，且重复副作用触发 R12（概率中 / 影响高）风险登记在案 | `plan/工业设备诊断 Agent.md` §8.1 R12（应对 = 写操作移出图内 + 幂等键） |

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | 恢复/重放零重复副作用（实测 0 次）；写路径唯一、可单测；报告 Schema 升版不与旧报告混淆 |
| ⚠️ 负面 | 报告生成从图内能力降为图外编排，图自身不再"一图到底"；外部副作用（通知/推送）仍需各自的幂等方案 |
| 📎 已知边界 | 幂等范围不含通知/外部推送（`docs/p0-decision-checkpoint.md` §4.3 幂等范围行）；幂等判重为 PG 唯一索引应用层语义，键构造正确性依赖调用方（`app/report/idempotency.py`） |

## 六、事实源

- `plan/工业设备诊断 Agent.md` §5.1、§6.4、§8.1（R12）
- `docs/p0-decision-checkpoint.md` §一、§四（§4.1–§4.4）、§六
- `docs/prj-design-architecture.md` §5.3、§5.5
- `app/report/idempotency.py`、`app/api/routes/review.py`、`app/review/lifecycle.py`
- `reports/p0-report-v5-checkpoint.md`

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版 | 本文件 |
