# P7 设计：Redis 缓存层 + 告警自动触发（auscult）

> **层级**：项目级设计文档｜ **状态**：🟢 已实现（2026-10-16）｜ **对应**：CHANGELOG `[未发布]` P7 条目
> **纪律声明**：本文档范围由项目所有者**显式指示**实施——`M6.4`（2026-10-10）收口后仓库处于维护期（"只修缺陷与文档口径，不新增功能范围"，README §八.8）。本次属**指示性扩范围**，按判据前置纪律在此登记动机、判据与回滚方式；后续任何进一步扩范围仍须另立阶段计划。

---

## 一、背景与动机

收口后代码考古得出三个事实（分析过程见对话记录，均有代码实证）：

1. **Redis 实际是"协调原语"而非缓存**：全项目仅 4 处使用——限流令牌桶（`rate_limit.py`）、云端预算计数（`budget.py`）、审核并发锁（`lifecycle.py`）、告警去重（`alarm_engine.py`）。**零 read-through 缓存**：检索/LLM/checkpoint/会话均不经 Redis。
2. **文档与实现漂移两处**：README §2.5 声称"工作流状态 = Redis 运行态""会话上下文 = Redis TTL 24h"，代码均不存在（checkpointer 因 B7 走 PG，`qa_log` 在内存注册表）。
3. **数据流缺环**：README §2.3 画"MQTT 告警 → 去重 → LangGraph 触发"，但 `app/` 无任何告警订阅器，诊断只能人工调 `POST /api/diagnose`（`routes/diagnose.py`）。

另：Redis 曾是 checkpointer 候选 A（默认），因 B7（redis-py↔redis-stack 握手被关闭）弃用走 PG（`docs/p0-decision-checkpoint.md`）；`configs/redis.conf` 的 `noeviction`/无 TTL 配置是该候选的遗产。

## 二、设计原则（四条，全部可从既有项目原则导出）

1. **非权威、可重建**：权威数据一律 PG。缓存丢失/过期/未命中最坏后果 = 回源重算。PG 唯一权威源（README §2.5）不可因缓存动摇。
2. **fail-open**：Redis 不可达 → 读按 miss、写按跳过、set_nx 按放行。与 `rate_limit.py`/`budget.py` "Redis 不可达不阻塞"既有降级哲学一致；每次错误落审计（`redis_cache_error`，warning）。
3. **失效 = 换 key**：一切影响输出的输入（模型 digest、prompt 版本、知识版本、messages 全文）进 key hash；输入变则 key 变，旧 key 靠 TTL 自然过期。**不做原地失效逻辑**——与 schemas 冻结区"修改须升版"同构，消灭"该失效没失效"类缺陷。
4. **DB 隔离**：缓存用 **db 1**；限流/预算/锁/去重等协调原语保持 **db 0**。两类 key 生命周期与语义不同；缓存可整库 flush，协调原语不可。

## 三、分层设计（六层）

| 层 | 缓存什么 | key 输入（失效维度） | TTL | 落点 |
|---|---|---|---|---|
| `emb` | BGE-M3 embedding | 模型 token（路径+size+mtime）+ 文本 | 30d | `scripts/embedding_cache.py`（CachedEmbedder 代理） |
| `retr` | 检索结果（W1→W5 全包） | knowledge_versions.max(id) + mode + top_k + use_rerank + 归一化语义 | 6h | `scripts/retrieve_knowledge.py::retrieve` |
| `state` | thread_status payload | thread_id | 24h | `app/api/runner.py::thread_status`（仅重启回退路径 read-through） |
| `values` | state values（ask 注入用） | thread_id | 24h | `app/api/runner.py::_load_thread_values` |
| `llm` | LLM content 原文 | model + 完整 messages | 24h | `app/graph/nodes/diagnose.py::_call_ollama` |
| `trig` | 告警触发 SETNX 护栏 | alarm_id | 7d | `app/api/auto_trigger.py` |

### 关键实现决策

- **检索缓存 key 归一化**：`retrieve_evidence` 节点传 `cache_key = device_id|metric`（**剔除告警数值/threshold**）。question 原文含逐次变化的数值，直接入 key 命中率趋零；而"某设备某指标的故障原因文档"与当次数值无关，归一化语义正确。
- **仅缓存非降级检索结果**：降级结果多是临时故障产物，缓存会把"一时不可用"固化成"一段时间不可用"。
- **版本令牌进程内 30s 缓存**：`knowledge_versions.max(id)` 每次检索直查 PG 不必要；PG 不可达 → token=`"unknown"`，退化为"无版本隔离 + TTL 有界"，30s 刷新窗口封顶陈旧度。
- **LLM 缓存只存 content 原文**（含 think）：think 剥离/JSON 解析/置信度计算全部照常执行——缓存不改变任何下游语义；命中落审计 `llm_cache_hit`（info）保证可复现口径可追溯。
- **state 缓存只包"重启回退路径"**：进程内注册表（内存 dict）比 Redis 快且永远权威，不做 read-through；缓存价值在进程重启后的 fallback（建 graph + PG 连接）。
- **体积闸门 256KB**：`noeviction + maxmemory 1gb` 下，大 payload 挤满内存会连带 db 0 的预算/锁写入失败（OOM command not allowed）。超限 value 不落缓存（打点 `set/skip`）。

## 四、告警自动触发

**流程**（`app/api/auto_trigger.py`，daemon 线程 5s 轮询）：

```
扫描 alerts WHERE status='open' AND diagnosed_thread_id IS NULL ORDER BY ts LIMIT 50
  → severity 过滤（AUSCULT_AUTO_TRIGGER_SEVERITY，空=全部）
  → Redis SETNX 护栏（trig key，TTL 7d）           # 快速去重
  → PG 条件 UPDATE → 'trigger-pending'（rowcount=1 才继续）  # 权威占位，防并发双触发
  → start_diagnosis(alarm, submitter="system:auto-trigger")
  → PG 回写真实 thread_id
```

**选型理由**：
- **不引 Redis Stream/MQTT 订阅**：告警引擎是批处理式外部进程（非长驻流式服务），PG 即天然事件日志；重启后扫描条件自重建，不回放历史、不丢未触发告警。
- **双层幂等**：Redis 护栏挡轮询重试，PG 条件 UPDATE 挡扫描-启动间隙（B7 后 Redis 定位为非权威，权威标记必须在 PG）。
- **默认关闭**（`AUSCULT_AUTO_TRIGGER=0`）：自动跑 LLM 诊断是行为变更。关闭时 watcher 仍起线程、每轮打点 `disabled`——/metrics 可持续观测开关状态，避免"配置写了没生效"的静默漂移。

**schema**：`db/migrations/0007_alerts_auto_trigger.sql` 新增 `alerts.diagnosed_thread_id`（NULL=未触发）+ 部分索引。

## 五、判据（Pass / 中间 / No-Go）——开跑前定稿

| # | 判据 | Pass | 中间区间处置 | No-Go |
|---|---|---|---|---|
| C1 | 全量回归 | `pytest tests/ -q` 全绿（本次 208 passed） | — | 任一失败即阻断合入 |
| C2 | fail-open | Redis 停止时：检索/诊断/追问/状态查询全部功能正常（穿透回源），审计有 `redis_cache_error` | — | 任一调用方因缓存故障抛错/卡死 |
| C3 | 缓存有效性 | 同 device+metric 二次告警检索 `cache_hit=true`；知识升版后新 key（旧 key 6h 内自然过期） | 命中率低于预期 → 检查归一化 key 是否含变量字段 | 升版后仍返回旧证据（串味） |
| C4 | 自动触发幂等 | 同告警仅 1 thread；`diagnosed_thread_id` 回写成功 | — | 双触发 / 标记丢失导致循环触发 |
| C5 | 降级可观测 | `auscult_cache_ops_total` / `auscult_auto_trigger_total` 在 /metrics 可见 | — | 指标缺失 |

**降级必带代价（README 核心取向）**：
- C3 命中率不足 → 检索 P95 收益归零，但**不劣于**无缓存基线（fail-open 保证）；
- C4 若双触发复现 → 立即 `AUSCULT_AUTO_TRIGGER=0` 关闭（默认态即关闭，回滚成本为零）；
- 缓存层整体回滚 = `AUSCULT_CACHE_ENABLED=0`（全短路，不建连接）。

## 六、不做（Won't）

- **不做 Redis checkpointer 复活**：B7 根因未消解，且 PG 路线 V5 实测全 Pass；缓存层不碰权威状态。
- **不做会话/工作流的权威化**：缓存永远非权威；`qa_log`/checkpoint 仍以内存注册表/PG 为准。
- **不改 `configs/redis.conf` 的 noeviction/无全局 TTL**：该配置是 V5 决策遗产，改动须走 ADR；本设计以"db 隔离 + 体积闸门 + per-key TTL"在应用层规避冲突。
- **不动冻结区**：`prompts/ schemas/ evals/ configs/ docker/ protos/ experiments/**/raw/ env/cloud.json` 一律未触碰。

## 七、风险登记（后续迭代用）

| 风险 | 缓解 | 状态 |
|---|---|---|
| 缓存挤占 maxmemory 牵连 db 0 协调原语 | 256KB 体积闸门 + db 隔离 + 保守 TTL | 已缓解，待长跑观测 |
| LLM 缓存命中掩盖模型/prompt 变更 | key 含 model + 完整 messages；prompt 冻结区升版即换 key | 已设计 |
| 自动触发与人工发起竞态 | PG 条件 UPDATE 占位；submitter 为系统身份（职责分离天然成立） | 已设计 |
| `trigger-pending` 卡死（占位后崩溃） | 人工经 SQL 修正（`UPDATE alerts SET diagnosed_thread_id=NULL WHERE diagnosed_thread_id='trigger-pending'`） | 已文档化，待观测 |

## 八、事实源

- 代码：`app/cache/`（keys/client）、`app/api/auto_trigger.py`、`app/api/runner.py`、`app/graph/nodes/diagnose.py`、`scripts/embedding_cache.py`、`scripts/retrieve_knowledge.py`、`db/migrations/0007_alerts_auto_trigger.sql`
- 测试：`tests/test_cache_layer.py`（14 例）、`tests/test_auto_trigger.py`（11 例）
- 上游决策：`docs/p0-decision-checkpoint.md`（B7）、`docs/prj-decision-adr-001-model-role.md`
- 指标：`auscult_cache_ops_total{op,result}` / `auscult_auto_trigger_total{result}`（`app/observability/prom_metrics.py`）

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-16 | 单人（本人） | P7 初版（所有者指示实施；判据前置 + 漂移修正 + 数据流补环） | 本文件 |
