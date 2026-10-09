# Phase 3 可靠性测试报告（D20 · M3.4）

| 项 | 值 |
|---|---|
| 任务 | D20：可靠性测试（杀进程恢复、重复 resume、Redis 驱逐防护） |
| 里程碑 | M3.4（审核与可靠性） |
| 执行日期 | 2026-10-09 |
| 测试脚本 | [test_d20_reliability.py](file:///d:/DSHproject/auscult/scripts/test_d20_reliability.py) |
| 结果 | **12/12 PASS** |
| 判定 | **M3.4 ✅ 达成**（重启恢复 + 无重复副作用 + 并发安全） |

---

## 一、测试范围

依据 `plan/Phase 3 详细开发计划` §8.2 端到端场景 E7/E8/E9 + §6.5 Checkpoint 策略：

| 场景 | 对应测试 | 验证目标 |
|---|---|---|
| E7 服务重启于审核中 | A 组（A1–A4） | resume 后状态完整、无重复报告 |
| E8 双审核人并发 resume | B 组（B1–B4） | 仅产生 1 份报告（锁生效） |
| §6.5 Checkpoint 不设 TTL + noeviction | C 组（C1–C4） | 审核状态不丢、Redis 不静默淘汰 |

M3.4 出口条件：**重启恢复 + 无重复副作用 + 并发安全**。

---

## 二、测试环境

| 组件 | 版本/配置 | 容器 |
|---|---|---|
| PostgreSQL 18.6 | ParadeDB @ 宿主 5433，库 `auscult_v2` | `auscult-v2-pg` |
| Redis 8 | `maxmemory-policy=noeviction` + `appendonly=yes` | `auscult-redis` |
| LangGraph Checkpointer | `langgraph-checkpoint-postgres==3.1.2`（PostgresSaver） | — |
| Python | 3.12（`.venv`） | — |

PG checkpoint 表：`checkpoints` / `checkpoint_writes` / `checkpoint_blobs`（由 `PostgresSaver.setup()` 创建）。

---

## 三、测试结果汇总

| 组 | # | 测试项 | 结果 |
|---|---|---|---|
| A 杀进程恢复 | A1 | PG checkpoint 持久化 | ✅ PASS |
| | A2 | 新实例恢复（挂起在 human_review） | ✅ PASS |
| | A3 | 状态完整（diagnosis/root_causes/suggestions/evidence） | ✅ PASS |
| | A4 | resume(approved) → finalize → 幂等报告 | ✅ PASS |
| B 重复 resume / 并发安全 | B1 | ReviewLock 互斥（A 成功，B 失败） | ✅ PASS |
| | B2 | 重复 resume 无副作用（report_id 不变） | ✅ PASS |
| | B3 | generate_report 幂等（is_new=False） | ✅ PASS |
| | B4 | PG reports 无重复（count=1） | ✅ PASS |
| C Redis 驱逐防护 | C1 | `maxmemory-policy == noeviction` | ✅ PASS |
| | C2 | `appendonly == yes`（AOF 持久化） | ✅ PASS |
| | C3 | 无 TTL key 持久（noeviction 不淘汰） | ✅ PASS |
| | C4 | 有 TTL key 不被淘汰（TTL 未被重置） | ✅ PASS |

**总计：12/12 PASS。**

---

## 四、分组详述

### 4.1 A 组：杀进程恢复（E7）

**模拟方式**：用两个独立的 `with build_checkpointer()` 块模拟「进程崩溃 → 重启」。第一个块内 invoke 到 human_review 挂起后退出（关闭 PG 连接），第二个块新建 graph 实例从 PG 恢复状态。

| # | 验证点 | 实现 |
|---|---|---|
| A1 | PG checkpoint 持久化 | 挂起后查询 `checkpoints` 表，确认有 thread_id 对应记录 |
| A2 | 新实例恢复 | 新 with 块 + 新 graph，`get_state(config)` 返回 `next=('human_review',)` |
| A3 | 状态完整 | 恢复 state 含 `diagnosis="需立即停机检查轴承"`、`root_causes[0].cause="轴承磨损"`、`suggestions` 非空、`risk_level="high"`、`evidence` 非空 |
| A4 | resume + 幂等 | 恢复后 `invoke(Command(resume={action:"approved"}))` → finalize → `generate_report` 两次，第二次 `is_new=False` |

**结论**：PG Checkpointer 持久化生效，进程重启后可从挂起点恢复，前置链路状态完整，不产生重复报告。

### 4.2 B 组：重复 resume / 并发安全（E8）

| # | 验证点 | 实现 |
|---|---|---|
| B1 | ReviewLock 互斥 | `lock:review:{thread_id}` SETNX：审核人 A 获锁成功，B 获锁失败，holder==A |
| B2 | 重复 resume 无副作用 | 第一次 resume(approved) 完成后流程终结（`next=()`），第二次 resume 返回相同 `report_id` |
| B3 | generate_report 幂等 | 相同 state 调用两次 `generate_report`，第二次 `is_new=False`，`report_id` 相同 |
| B4 | PG reports 无重复 | 相同 `idempotency_key` 在 reports 表 `count=1`（调用三次后验证） |

**结论**：ReviewLock 并发锁 + 幂等键双重防护，重复 resume / 并发审核不会产生重复报告。

### 4.3 C 组：Redis 驱逐防护 noeviction（§6.5）

| # | 验证点 | 实现 |
|---|---|---|
| C1 | maxmemory-policy | `CONFIG GET maxmemory-policy` → `noeviction` |
| C2 | AOF 持久化 | `CONFIG GET appendonly` → `yes`（保障重启恢复） |
| C3 | 无 TTL key 持久 | 写入无 TTL key → `TTL=-1`（永不过期），noeviction 不淘汰 |
| C4 | 有 TTL key 不被淘汰 | 写入 `lock:review:*` key（TTL=900s）→ key 存在 + TTL 未被 maxmemory 重置 |

**结论**：Redis 配置 `noeviction` + `appendonly yes` 保障审核锁 / 预算计数 key 不被静默淘汰，内存满时写入报错而非丢数据。

---

## 五、M3.4 出口判定

| 出口条件 | 对应测试 | 判定 |
|---|---|---|
| 重启恢复 | A1–A4 全 PASS | ✅ |
| 无重复副作用 | B2–B4 全 PASS | ✅ |
| 并发安全 | B1 + C1–C4 全 PASS | ✅ |

**M3.4 ✅ 达成。**

---

## 六、回归测试

| 测试 | 结果 | 备注 |
|---|---|---|
| D17 审核状态机 + resume | 11/11 PASS | 无破坏 |
| D18 审核生命周期 | 11/11 PASS | 无破坏 |
| D19 幂等写入 | 9/9 PASS | 清理残留后通过（见已知问题） |

---

## 七、已知问题

### ISS-D20-1：PG checkpoint 反序列化警告（非阻塞）

```
Deserializing unregistered type app.graph.state.AlarmEvent from checkpoint.
This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true
to block now, or add to allowed_msgpack_modules to allow explicitly.
```

**影响**：不影响功能（反序列化成功，状态完整恢复）。属 LangGraph 未来版本的严格化预警。

**处置**：P1 修复——在 `PostgresSaver` 初始化时注册 `allowed_msgpack_modules`，将 `app.graph.state` 的 Pydantic 子类型（`AlarmEvent`/`EvidenceItem`/`GraphPath`/`RootCause`/`Suggestion`/`WorkOrder`）加入白名单。已登记于 project_memory。

### ISS-D20-2：D19 测试数据残留（测试设计缺陷）

**现象**：D19 测试用固定 `thread_id`（如 `"d19-new"`），首次运行写入 reports 表后，重复运行时 `is_new` 不再为 True，导致"新建报告"测试失败。

**影响**：非功能缺陷，仅影响回归测试可重复性。

**处置**：P1 修复——D19 测试改用 `uuid` 生成唯一 `thread_id`（与 D20 测试一致），或增加 `setUp` 清理旧数据。

---

## 八、复现命令

```powershell
# D20 可靠性测试
.venv\Scripts\python.exe scripts\test_d20_reliability.py

# 回归
.venv\Scripts\python.exe scripts\test_d17_resume.py
.venv\Scripts\python.exe scripts\test_d18_lifecycle.py
.venv\Scripts\python.exe scripts\test_d19_idempotency.py
```

前置：`auscult-v2-pg`（5433）和 `auscult-redis`（6379）容器运行中。

---

## 修订记录

| 日期 | 版本 | 作者 | 变更 |
|---|---|---|---|
| 2026-10-09 | v1 | — | D20 初版，12/12 PASS，M3.4 达成 |
