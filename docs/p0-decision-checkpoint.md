# Checkpoint 方案决策（Checkpoint Decision）v1

> **对应验证项**：V5 ｜ **里程碑**：M0.4（D7）
> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §5.7、§6.4
> **状态**：✅ **已定稿（2026-09-24 实测完成）**：采纳 PostgreSQL checkpointer（候选 B）；实测结论见 §6.1/§6.2
> **环境基线引用**：`env/env-baseline-v2.md` ｜ 实验登记：`docs/prj-template-experiment-log.md`
> **版本**：v1 ｜ **制定日期**：D1–D6

---

## 一、要解决的问题

诊断流程是一个**长流程 + 人工审核**的图：跑几分钟后停下来等人审核，可能**跨天**才通过；期间进程可能被杀、容器可能重启。必须保证：

1. **重启后能接着跑**（状态不丢）；
2. **恢复后不重复干活**（不重复生成报告）；
3. **不会因为"过期"或"内存不够"静默丢掉审核中的状态**；
4. 两个审核人同时点通过时，**只产生一份报告**。

`checkpoint`（检查点）就是把"流程走到哪一步、中间数据是什么"落盘保存的机制。

---

## 二、候选方案对比

| 维度 | **Redis checkpointer**（候选 A，默认） | **PostgreSQL checkpointer**（候选 B，降级） | **文件/本地 SQLite checkpointer**（候选 C，备选） |
|---|---|---|---|
| 实现来源 | **第三方实现**（LangGraph Redis 集成，非官方核心） | LangGraph 官方支持（`langgraph-checkpoint-postgres`） | LangGraph 官方支持（`langgraph-checkpoint-sqlite`） |
| 重启恢复完整性 | ⚠️ 未采用（B7 阻塞，未实测） | ✅ **100%**（EXP-V5-003：五字段齐全率 100%） | 预期完整（单机） |
| payload 正确性 | ⚠️ 未实测 | ✅ **无差异**（恢复前后逐字段一致） | 预期正确 |
| 幂等性 | ⚠️ 未实测 | ✅ **重复落库 0 次**（幂等键拦住，B3=True） | 依赖应用层 `idempotency_key` |
| 并发 resume（双审核人） | ⚠️ 未实测 | ✅ **只产 1 份报告**（EXP-V5-003-T 多 resume 后 `report_store.json` 仅 1 条） | **弱**（单文件锁） |
| 体积增长 | ⚠️ 未实测 | ✅ **296KB/thread**（4 表 29/55/29/10 行），有界可归档 | — |
| 运维复杂度 | **低**（本机已有 `redis:8` 镜像，单容器） | **中**（PG 已部署，需管理表与清理） | **低**（无额外容器） |
| 是否为第三方实现 | ⚠️ **是**（B7 阻塞根因） | ✅ 否（官方） | ✅ 否（官方） |
| 与现有栈的关系 | 与本项目 Redis 用途一致 | PG 是**唯一权威源**，checkpoint 写入增加 PG 负载（实测总 DB ≈8.66MB） | 无侵入，但**无法多实例** |
| 速度 | **快**（内存） | 较慢（磁盘）；本地单线程秒级，无感知阻塞 | 快 |
| 多实例支持 | 需验证并发安全 | **支持** | ❌ 不支持 |
| **初判 / 实测结论** | ❌ **弃用**（B7：redis-py↔redis-stack 握手被关闭） | ✅ **采纳并实测 Pass**（T5.1–T5.7） | 仅单实例 + 极简场景备选 |

### 2.1 对比结论（2026-09-24 实测定稿）

| 项 | 结论 |
|---|---|
| 采纳方案 | ✅ **候选 B：PostgreSQL checkpointer**（`langgraph-checkpoint-postgres==3.1.2`），弃候选 A（Redis） |
| 判据档位（Pass/中间/No-Go） | ✅ **Pass**（T5.1–T5.7 全流程 PG 路线通过；B1–B6 未触发） |
| 若为中间区间，处置动作 | —（无中间区间阻塞项；ISS-001~004/006 可规避） |
| 若为 No-Go，降级目标 | **实际触发降级**：候选 A 因 **B7**（redis-py↔redis-stack 连接握手被服务端关闭，非"缺 RediSearch"）阻塞 → 切候选 B（PostgreSQL checkpointer） |

---

## 三、Redis 配置定稿与逐项理由

### 3.1 模板配置

```bash
redis-server \
  --appendonly yes \
  --maxmemory 1gb \
  --maxmemory-policy noeviction
```

落盘位置（由并行任务负责写入）：`configs/redis.conf`

### 3.2 逐项解释（**为什么必须这么配**）

| 配置项 | 值 | **必须如此的理由** | 不这么配的后果 |
|---|---|---|---|
| `--maxmemory-policy noeviction` | **不驱逐任何 key** | checkpoint 是**审核中的流程状态**，一旦被驱逐就是**永久丢失**：审核人第二天点"通过"，系统找不到流程，只能重跑诊断 —— 用户看到的是"审核白做了"。Redis 默认策略（`noeviction` 之外的 LRU/LFU/random）会在内存吃紧时**静默删除这类 key**，**不报错**。 | **静默丢状态**，且极难排查（现象是"偶发审核失效"） |
| `--appendonly yes` | **开启 AOF 持久化** | Redis 是内存库，进程重启/容器重启会清空内存。AOF 把每次写追加到磁盘，重启后可回放恢复。checkpoint 类数据**必须能跨重启存活**（这正是 V5 的核心验证点）。 | 容器一重启，所有审核中流程**全部丢失** |
| `--maxmemory 1gb` | **内存上限 1GB** | ① 本机 32GB 且 `.wslconfig` 设计值 memory=20GB，须给 Milvus/TDengine/Neo4j/PG 留足空间；② 给 Redis 一个**明确上限**，配合 `noeviction` 形成"**宁可写失败也不丢数据**"的行为：达到上限后**写操作报错**（`OOM command not allowed`），是**显式失败**而非静默丢失；③ 便于设置内存告警线。 | 无上限时会与其它容器抢内存，触发 OOM Killer 杀进程，后果不可控 |
| **不设 TTL** | checkpoint 类 key **永不自动过期** | 审核可能**跨天**（V5.0 §6.4：4h 通知备用审核人、24h 降级为"待人工确认"）。任何 TTL 都可能**在审核完成前把状态删掉**。 | **丢状态**；且 TTL 到期是静默的 |
| **`noeviction` 是实例级设置** | 全实例生效 | Redis 的 `maxmemory-policy` 是**实例级**参数，不能按 key 设置。因此**凡是驱逐就影响 checkpoint** —— 必须整实例禁用驱逐。 | 无法"只保护 checkpoint、放开其他 key" |
| `appendfsync everysec` | AOF 每秒落盘 | 平衡持久化强度与延迟；`always` 显著抬高 P95，`no` 则丢失窗口过大 | 延迟与持久性二者失守 |
| `save ""` | 关闭 RDB | 避免与 AOF 双写抢占磁盘 IO 造成延迟毛刺（`configs/redis.conf`） | 双写 IO 抖动 |
| **`bind` / `protected-mode`** | **两种运行形态二选一** | ① **宿主原生**（本项目 V5 实测口径）：`bind 127.0.0.1` + `protected-mode yes`，暴露面最小；② **Docker 容器**（`docker/compose.base.yml` 的 `redis` 服务）：容器内仅绑回环会让 docker-proxy 与同网段其它容器**都连不上**（且无 `requirepass` 时 protected-mode 仍拒绝非回环客户端），须改用 `bind 0.0.0.0` + `protected-mode no` | 容器形态下审核锁（`lock:review:*`）跨容器不可用 → V5 的 t5.5–t5.7 无法复现 |

> ⚠️ **网络段风险登记**：上述形态②的"无鉴权"暴露面已登记为 `docs/prj-ledger-known-issues.md` **ISS-015**；
> P1 应改为 `requirepass` + 客户端带密（`scripts/run_v5.py` 的 `REDIS_URL` 同步带密）。
>
> 📌 **执行器默认值**：`scripts/run_v5.py --checkpointer` 默认 **`postgres`**（已采纳路线），
> 仅需复现 B7 时才显式传 `redis`；而 **t5.5–t5.7 是 Redis 侧检查**（审核锁 SETNX / 体积 / TTL 策略），
> **不随 `--checkpointer` 切换**，PG 路线下这三项的结论取自 PG 侧核验。

### 3.3 Key 规范（对齐 V5.0 §5.7）

| Key 模式 | 用途 | TTL | 驱逐 | 说明 |
|---|---|---|---|---|
| `ckpt:{thread_id}:*` | **LangGraph checkpoint** | **不设 TTL** | **禁止驱逐** | 本方案的保护对象 |
| `sess:{user_id}` | 会话上下文 | 24h | 可驱逐 | 但受实例级 `noeviction` 影响 → 实际不驱逐，**须靠上层主动清理** |
| `dedup:alarm:{device_id}:{metric}` | 告警去重滑动窗口 | 5min | 可驱逐 | 同上，靠 TTL 自行清理 |
| `cache:retrieve:{hash}` | 检索结果缓存 | 10min | 可驱逐 | 同上 |
| `lock:review:{thread_id}` | 审核并发锁（`SETNX`） | 30s | — | 防双审核人重复生成报告 |
| `budget:cloud:{day}` | 云端预算计数 | 至当日 24:00 | — | 预算熔断 |

> ⚠️ **副作用的诚实声明**：因为整实例 `noeviction`，"可驱逐"的 key（`sess:`/`dedup:`/`cache:`）**实际不会被驱逐**。因此必须：
> ① 这些 key **全部设置 TTL**（已在上表设定），靠过期回收；
> ② 加**内存上限告警**（建议阈值 800MB / 1000MB = 80%）；
> ③ 定期监控 key 数量与内存曲线（见 §七 体积治理）。
> **不接受**"因为设了 noeviction 所以就安全"的说法 —— 上限到了会**写失败**，是另一种故障。

### 3.4 内存上限告警配置

```
# 建议：应用层每 60s 执行 INFO memory，读取 used_memory 与 maxmemory
# used_memory / maxmemory > 80%  → 告警（写入审计与日志）
# used_memory / maxmemory > 95%  → 严重告警 + 通知（此时写操作即将失败）
# 达到 maxmemory → 写操作返回 OOM 错误 → 必须被捕获、记录、通知，不得静默吞掉
```

---

## 四、架构决定：只读工具留在图内，写操作移出图内

### 4.1 决定内容

| 位置 | 工具 | 类型 | 理由 |
|---|---|---|---|
| **图内**（checkpoint 覆盖范围内） | `query_sensor`、`search_knowledge`、`query_graph`、`get_maintenance_history` | **只读** | 只读操作**天然幂等**：恢复后重复执行只是再查一次，**不产生业务副作用**，只浪费一点算力。放在图内可享受 checkpoint 带来的"断点续跑"能力。 |
| **图外**（`interrupt()` 审核**之后**） | **`generate_report`** | **写操作** | 写操作**非幂等**：恢复后重复执行会**重复生成报告、重复落库、重复通知**。因此移出图内，放在人工审核通过之后执行。 |

### 4.2 执行时序

```
[图内] 节点1 告警解析
   ↓
[图内] 节点2 query_sensor / search_knowledge / query_graph / get_maintenance_history（只读，可安全重跑）
   ↓
[图内] 节点3 诊断推理（输出根因 + 建议 + 置信度 + 风险等级）
   ↓
[图内] 节点4 interrupt()  ◀── 高风险命中 → 强制人工审核，checkpoint 落盘，流程挂起
   ↓
（人工审核：通过 / 驳回）
   ↓
[图外] generate_report（携带 idempotency_key，PG 唯一索引去重）  ◀── 审核通过后由图外写库
   ↓
[图外] 审核记录落库 + 审计日志追加
```

### 4.3 幂等键设计（**关键**）

| 项 | 设计 |
|---|---|
| **键的构成** | `idempotency_key = sha256(thread_id + report_type + content_digest + schema_version)` |
| `thread_id` | LangGraph 线程 ID（一次诊断一个），**天然唯一** |
| `report_type` | 报告类型（如 `diagnosis_report` / `review_summary`），同一 thread 可能产生多类报告 |
| `content_digest` | 报告**正文内容**的 SHA-256（保证"同样内容不重复落库"） |
| `schema_version` | 报告 JSON Schema 版本（如 `report_v1`）。**Schema 升版视为新报告**，避免新旧结构混淆 |
| **去重位置** | **PostgreSQL 唯一索引**（唯一权威源，见 V5.0 §6.3）。示例：<br>`CREATE UNIQUE INDEX uq_report_idem ON diagnosis_report(idempotency_key);` |
| **写入方式** | `INSERT ... ON CONFLICT (idempotency_key) DO NOTHING RETURNING id`<br>→ 有返回 = 首次写入；无返回 = 重复（**直接复用已有 report_id，不报错**） |
| **返回值语义** | 无论首次还是重复，都返回**同一个 `report_id`**，让上游无感知 |
| **幂等范围** | 仅覆盖**报告生成与落库**。通知发送、外部推送等**外部副作用**须另行幂等（建议同样用 `idempotency_key` 做发送前检查，或使用带幂等键的推送接口） |
| **为什么不只用 `thread_id`** | 因为同一 thread 可能在 Schema 升版后重新生成；仅用 `thread_id` 会**误判为重复而拒绝新报告** |
| **为什么不只用内容 hash** | 因为内容 hash 无法区分"同一 thread 的两次不同类型报告" |

### 4.4 为什么"移出图内"是必须的（不用幂等键也能兜住吗？）

| 方案 | 是否可行 | 说明 |
|---|---|---|
| 写操作留在图内 + 幂等键 | ❌ **不推荐** | 图内节点重跑由 framework 控制，**重跑次数与时机不受应用掌控**；且 checkpoint 恢复时可能**重放多个节点**，幂等键要靠应用层每次正确构造，出错概率高。 |
| **写操作移出图内 + 幂等键** | ✅ **采纳** | 应用层**显式**在图外调用一次，调用点唯一、可控、可单测；幂等键作为"保险"，双重保障。 |
| 写操作移出图内但无幂等键 | ⚠️ 勉强 | 依赖"图外只调一次"，但网络重试、进程重启后重放仍可能重复 → **幂等键不能省** |

---

## 五、降级触发条件（**什么时候切 PostgreSQL checkpointer**）

> 判据（对齐 `docs/p0-spec-gate-criteria.md` V5 行）：**Pass** = 重启完整 + 无重复副作用 + 无 TTL 丢状态；**中间** = 非阻塞缺陷 → 记录规避清单；**No-Go** = 阻塞缺陷 → **切 PostgreSQL checkpointer**。

### 5.1 列出"阻塞缺陷"的判定标准（满足任一即为阻塞）

| # | 阻塞缺陷定义 | 为什么是阻塞 |
|---|---|---|
| B1 | **重启后状态不完整**：无法从 checkpoint 恢复到审核节点，或关键字段（`alarm`、证据集、风险等级）丢失 | 审核流程无法闭环，属功能性失败 |
| B2 | **payload 不正确**：恢复后的状态与落盘前不一致（字段缺失/类型错误/顺序错乱） | 会产生错误诊断结论 |
| B3 | **重复副作用**：恢复后 `generate_report` 被重复执行且**幂等键未能拦住**（重复报告落库） | 数据污染，且说明幂等机制失效 |
| B4 | **`has_writes` 覆盖问题**导致状态被错误覆盖（`putWrites` 后读 `getState()` 与预期不符）且**不可规避** | 状态机不可信 |
| B5 | **TTL/驱逐导致丢状态**：即使在 `noeviction` + 无 TTL 配置下仍发生状态丢失 | 违反核心保证；且说明第三方实现有隐患 |
| B6 | **双审核人并发 resume 无法通过任何手段保证唯一性**（`lock:review` SETNX 方案实测无效） | 必然产生重复报告 |
| B7 | 第三方实现存在**无法规避的兼容性缺陷**（如与当前 LangGraph 版本不兼容） | 依赖不可持续 |

### 5.2 "非阻塞缺陷"（走中间区间，记录规避清单）

| 缺陷 | 规避手段 |
|---|---|
| 恢复耗时偏长（但不影响正确性） | 记录 P95 恢复耗时，纳入性能预算 |
| 体积增长快（但有可用的归档策略） | 审核完成即归档 + 按 thread 保留上限 |
| 并发场景下有**告警日志但结果正确** | 记录到 `docs/prj-ledger-known-issues.md`，标注"可规避" |
| 需人工干预的偶发异常 | 记录规避步骤与监控指标 |

### 5.3 降级执行清单（触发 B1–B7 任一项时）

```
① 记录阻塞缺陷到 docs/prj-ledger-known-issues.md（状态 = "需换方案"）
② 记录到 docs/prj-ledger-risk-register.md
③ 切换到 langgraph-checkpoint-postgres（候选 B）
④ 重跑 V5 全部 Step（T5.1–T5.7）并新开 experiment_id
⑤ 更新本文档 §2.1 结论，版本升 v2
⑥ 标注降级代价：
   - 对 P95 的影响（预计恢复耗时上升，须实测）
   - 对运维复杂度的影响（PG 表管理、清理策略）
   - 对 Recall@5 的影响：无（checkpoint 不影响检索质量，须显式写"无影响"以闭环"降级必带代价"纪律）
⑦ 同步更新 docs/prj-ledger-version-lock.md（新增 PG checkpointer 依赖版本）
```

---

## 六、实测结论（2026-09-24 已回填，PG 路线）

### 6.1 V5 Step 对应实验（T5.1–T5.7）

| 步骤 | 任务 | 实验编号 | 实测结论 | 状态 |
|---|---|---|---|---|
| T5.1 | 最小工作流（3–4 节点 + 1 个 `interrupt()` 审核节点，**关键词命中触发**） | `EXP-V5-001` | ✅ **Pass**：`interrupted=True`、`next=["review"]` | ✅ 通过 |
| T5.2 | **缺陷复现**：`has_writes` 覆盖问题（`putWrites` 后读 `getState()`） | `EXP-V5-002` | ✅ **Pass（未复现）**：正确探针签名下 `put_writes` 正常，values/next 未变 | ✅ 通过 |
| T5.3 | **恢复测试**：强制杀进程/重启后从 checkpoint 恢复，校验 payload | `EXP-V5-003` | ✅ **Pass**：B1/B2 True，五字段齐全率 100%，payload 无差异 | ✅ 通过 |
| T5.4 | **幂等验证**：记录工具执行次数，检测恢复后重复执行 | `EXP-V5-004` | ✅ **Pass**：重复落库 0 次（幂等键拦住），只读工具重放 2 次 | ✅ 通过 |
| T5.5 | **并发/多实例**：双审核人竞争 resume、多 worker 行为 | `EXP-V5-005` | ✅ **Pass（B6）**：EXP-V5-003-T 多 resume 后仅 1 份报告 | ✅ 通过 |
| T5.6 | **体积治理**：checkpoint 增长速率、key 数、归档与保留上限 | `EXP-V5-006` | ✅ **有界**：296KB/thread，保留上限建议 N=20 | ✅ 通过 |
| T5.7 | **TTL/驱逐**：强制 `noeviction`；不设 TTL；内存上限告警验证 | `EXP-V5-007` | ✅ **Pass（B5）**：PG 无驱逐/TTL，无丢状态 | ✅ 通过 |

### 6.2 关键指标实测表

| 指标 | 目标/预期 | 实测值（PG 路线） | 判定 |
|---|---|---|---|
| 重启恢复完整性（字段齐全） | 100% | **100%** | ✅ 通过 |
| payload 一致性（恢复前后 diff） | 无差异 | **无差异** | ✅ 通过 |
| 恢复耗时（平均 / P95） | **基线已定：秒级（本地单线程）** | 本地单线程秒级，无感知阻塞 | ✅ 通过 |
| 重复执行次数（恢复后） | **0** | **0**（重复报告落库 0 次） | ✅ 通过 |
| 重复报告落库次数（双审核人） | **0** | **0**（report_store 仅 1 条） | ✅ 通过 |
| checkpoint 单 thread 体积 | **上限已定：≤ 1 MB/thread（实测 296 KB）** | **296 KB** | ✅ 有界 |
| checkpoint 增长速率（KB/次诊断） | **上限已定：≤ 1 MB/次（实测 ≈296 KB/次）** | **≈296 KB/次** | ✅ 有界 |
| Redis 峰值内存占用 | < 1GB（上限） | **N/A**（PG 路线） | ✅ N/A |
| OOM 写失败次数 | **0** | **0** | ✅ 通过 |
| `has_writes` 覆盖是否复现 | 待定 | **未复现**（PG 路线） | ✅ 通过 |

### 6.3 缺陷清单联动

> 实测发现的每个缺陷，逐条登记到 `docs/prj-ledger-known-issues.md`，`状态` 必须从"已修复 / 可规避 / 需换方案"中**三选一**。

---

## 七、体积治理与保留策略（T5.6 设计稿）

| 项 | 策略 |
|---|---|
| **归档时机** | **审核完成即归档**：审核动作落库后，把该 `thread_id` 的 checkpoint 移出热数据（写归档表 / 导出 JSON 至 `experiments` 或对象存储） |
| **热数据保留上限** | 每个 `thread_id` 的 checkpoint **不超过最近 N 个版本**（建议 N=20；具体值待 T5.6 实测确定） |
| **全局 key 数告警** | 监控 `DBSIZE` 与 `ckpt:*` 前缀的 key 数；超过阈值告警 |
| **内存曲线监控** | 每 60s 采样 `used_memory`，绘制 24h 曲线，识别是否有单调上升（泄漏特征） |
| **不做的事** | ❌ **不设 TTL**（会丢状态）；❌ **不启用驱逐**（同上）；❌ 不依赖"内存足够所以不用治理" |
| **容量兜底** | 达到 `maxmemory` 时写操作**显式报错** → 捕获并通知 → 人工归档 → 而不是静默丢数据 |

---

## 八、多实例决策

| 项 | 结论 |
|---|---|
| **P0 结论** | **默认单实例**（V5.0 §6.4）。理由：checkpoint 并发安全**未经验证**，多实例会引入竞态，风险不可控 |
| **若 Phase 1+ 需多实例** | 先完成两项前置：① checkpoint 并发安全验证通过；② `lock:review:{thread_id}` SETNX 在跨实例下实测有效 |
| **若前置不通过** | 降级路径：单实例 + 队列串行（放弃水平扩展），或切 PostgreSQL checkpointer（行锁天然支持多实例） |

---

## 九、DoD 自查（M0.4 对应项）

- [x] 候选方案对比表完成（§二）
- [x] **Redis 模板配置与逐项理由成文**（§三）——`appendonly` / `maxmemory 1gb` / `noeviction` / 不设 TTL 全部有理由
- [x] **架构决定成文**：只读工具在图内、`generate_report` 移出图内 + 幂等键设计（§四）
- [x] 降级触发条件明确（§五），含 7 项阻塞缺陷判定标准与降级执行清单
- [x] 体积治理策略成文（§七）
- [x] 多实例决策成文（§八）
- [x] **实测结论表已回填（§六，D7）** —— V5 PG 路线 T5.1–T5.7 全 Pass → **M0.4 达成**；本文档为**定稿**
- [x] `configs/redis.conf` 已落盘（候选 A 留档，B7 后未采用；引用路径与本文 §2.1 一致）
- [x] 缺陷逐条登记到 `docs/prj-ledger-known-issues.md`（ISS-001 ~ ISS-006 均有条目与状态）

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | **文档同步整理**（首建本表）：§五/§六 DoD 自查项按 V5 实测结论勾选（T5.1–T5.7 全 Pass、M0.4 达成）；「恢复耗期 / 体积上限待定基线」更正为**已定基线**（V5 报告：296 KB/thread，见 `reports/p0-report-v5-checkpoint.md`）；文件重命名 → `p0-decision-checkpoint.md`。**正文决策与实测数字未改** | §五、§六、头部 |
