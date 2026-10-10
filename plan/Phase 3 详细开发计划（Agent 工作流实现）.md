# Phase 3 详细开发计划（Agent 工作流实现）

> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §五 / §六 / §九
> **前一阶段**：Phase 2（混合检索）——须 **M2.4 门禁通过**后启动
> **本阶段定位**：把"数据能力 + 检索能力"编排为**可运行、可中断、可恢复、可追溯的 Agent 工作流**——LangGraph 状态图、五工具集成、置信度路由、混合推理、人工审核。
> **执行主体**：单人（"机器并行、人串行"）
> **总工期**：25 个工作日（P3-D1 – P3-D25，占比 25%）
> **制定日期**：2026-09-24

---

## 目录

- [一、阶段目标与出口](#一阶段目标与出口)
- [二、阶段前置（Phase 1/2 移交物核对）](#二阶段前置phase-12-移交物核对)
- [三、状态图设计](#三状态图设计)
- [四、工作分解（WBS）](#四工作分解wbs)
- [五、分周计划（P3-D1 – P3-D25）](#五分周计划p3-d1--p3-d25)
- [六、关键模块详细设计](#六关键模块详细设计)
- [七、里程碑](#七里程碑)
- [八、测试计划](#八测试计划)
- [九、验收标准与门禁](#九验收标准与门禁)
- [十、风险与应对](#十风险与应对)
- [十一、交付物与目录](#十一交付物与目录)
- [十二、检查清单](#十二检查清单)

---

## 一、阶段目标与出口

### 1.1 阶段目标

> 交付一个**端到端可运行**的 LangGraph Agent：
> **告警触发 → 传感器分析 → 知识检索 → 图谱推理 → 诊断推理 → 置信度路由 → （人工审核）→ 报告生成**，
> 具备**状态持久化、中断恢复、幂等、降级、可观测**五项工程属性。

### 1.2 阶段出口（M3.5）

| 出口物 | 判据 |
|---|---|
| 状态图 | 六节点 + 条件路由全部实现，可通过开关做消融 |
| 工具集成 | 五工具全部接入，错误码/超时/重试/幂等符合契约 |
| 置信度 | 复合公式实现，校准后 `ECE ≤ 0.10` |
| 混合推理 | 本地/云端路由生效，含脱敏与预算熔断 |
| 人工审核 | `interrupt()`/`resume()` 可用；超时/并发/幂等策略生效 |
| 可靠性 | 重启后可恢复；无重复副作用 |
| 可观测 | Langfuse Trace 全覆盖 + 关键指标打点 |

### 1.3 与前后阶段的关系

```
Phase 1（数据）+ Phase 2（检索）
   └─► Phase 3（本阶段：Agent 编排）
            ├─► Phase 4 前端：审核界面、实时推送、报告展示
            ├─► Phase 5 评测：幻觉率/引用正确率/端到端延迟
            └─► 输出 e2e 路径供 Phase 5 硬化
```

---

## 二、阶段前置（Phase 1/2 移交物核对）

| # | 移交物 | 来源 | 用途 | 状态 |
|---|---|---|---|---|
| 1 | `schemas/tools_v1.json` | Phase 0 | 五工具契约基线 | ☐ |
| 2 | `app/tools/retrieve_knowledge.py` | Phase 2 | 检索节点 | ☐ |
| 3 | 图谱召回与 `graph_support` 规则 | Phase 2 | 置信度输入 | ☐ |
| 4 | `query_sensor` 实现 + 时序 Schema | Phase 1 | 传感器节点 | ☐ |
| 5 | 告警事件流（`AlarmEvent`） | Phase 1 | 图入口 | ☐ |
| 6 | `work_orders` 表 + 查询 | Phase 1 | 历史工单节点 | ☐ |
| 7 | `docs/checkpoint-decision.md` + Redis 模板 | Phase 0/1 | 状态持久化 | ☐ |
| 8 | `docs/known-issues.md` | Phase 0 | 规避清单 | ☐ |
| 9 | `docs/role-decision.md` + Prompt v1 | Phase 0 | 模型分工 | ☐ |
| 10 | `version-lock.md` | Phase 0 | 依赖版本 | ☐ |

> **若 Phase 0 判定 checkpoint 走 PostgreSQL**，本阶段直接按该结论实现（不重复验证）。

---

## 三、状态图设计

### 3.1 图结构

```
                        ┌─────────┐
              START ───►│ parse_alarm │  告警解析（确定性）
                        └─────┬───┘
                              ▼
                        ┌──────────────┐
                        │ analyze_sensor │  query_sensor
                        └───────┬──────┘
                                ▼
                        ┌──────────────────┐
                        │ retrieve_evidence │  retrieve_knowledge + query_graph
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │ get_history       │  get_maintenance_history
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │ diagnose          │  deepseek-r1:7b 推理 + 置信度计算
                        └────────┬─────────┘
                                 ▼
                        ┌──────────────────┐
                        │   route (条件)    │  按优先级判定（见 §3.3）
                        └──┬────┬─────┬────┘
             confidence<0.5│    │0.5-0.75│high risk
                           ▼    ▼        ▼
                     ┌────────┐ ┌──────────────┐ ┌──────────────┐
                     │degrade │ │escalate_cloud│ │human_review  │
                     └───┬────┘ └──────┬───────┘ │  (interrupt) │
                         │             │         └──────┬───────┘
                         ▼             ▼                ▼
                     ┌──────────────────────────────────────┐
                     │           finalize                    │
                     └──────────────┬───────────────────────┘
                                    ▼
                                  END
   ────────────────────────────────────────────────────────────
   ★ generate_report 为**写操作，位于图外**（审核通过后触发）
```

### 3.2 节点清单

| 节点 | 类型 | 执行体 | 只读/写 | 超时 |
|---|---|---|---|---|
| `parse_alarm` | 确定性 | 规则解析 | 只读 | 100ms |
| `analyze_sensor` | 工具 | `query_sensor` | 只读 | 3s |
| `retrieve_evidence` | 工具 | `retrieve_knowledge` + `query_graph` | 只读 | 2s / 3s |
| `get_history` | 工具 | `get_maintenance_history` | 只读 | 2s |
| `diagnose` | LLM | `deepseek-r1:7b` + 置信度计算 | 只读 | 30s |
| `escalate_cloud` | LLM | LiteLLM → 云端 | 只读 | 20s |
| `human_review` | 人工 | `interrupt()` | — | 4h（可配） |
| `finalize` | 确定性 | 证据校验 + 组装 | 只读 | 200ms |
| `generate_report` | 工具 | **图外**写操作 | 写 | 5s |

### 3.3 条件路由（**严格优先级，首个命中生效**）

```
1. if retry_count ≥ 3 且仍失败        → degrade（输出降级报告）
2. elif confidence < 0.50             → degrade（"初步判断，建议人工确认"）
3. elif confidence < 0.75             → escalate_cloud；云端失败 → degrade
4. elif risk_level == "high"          → human_review（interrupt）
5. else                               → finalize
```

### 3.4 State 定义（类型化，Pydantic）

```python
class DiagnosisState(BaseModel):
    # 输入
    alarm: AlarmEvent
    thread_id: str
    # 运行态
    sensor_report: QuerySensorOutput | None = None
    evidence: list[EvidenceItem] = []
    graph_paths: list[GraphPath] = []
    work_orders: list[WorkOrder] = []
    diagnosis: str | None = None
    root_causes: list[str] = []
    suggestions: list[str] = []
    confidence: float = 0.0
    confidence_breakdown: dict = {}
    risk_level: Literal["low", "medium", "high"] = "low"
    # 控制
    retry_count: int = 0
    escalate_cloud: bool = False
    degrade_reason: str | None = None
    human_review: dict | None = None
    # 产出
    report_id: str | None = None
    errors: list[dict] = []
```

> 每步经 Pydantic 校验；校验失败写 `errors` 并触发重试/降级。

---

## 四、工作分解（WBS）

| 包 | 名称 | 核心内容 | 关键产出 |
|---|---|---|---|
| **A** | 图骨架与只读节点 | State 类型化、`parse_alarm`/`analyze_sensor`/`retrieve_evidence`/`get_history` | `app/graph/build.py` |
| **B** | 诊断推理节点 | 推理 Prompt、`deepseek-r1:7b` 接入、根因/建议生成 | `app/graph/nodes/diagnose.py` |
| **C** | 置信度与路由 | 复合置信度、校准、条件边 | `app/confidence/` |
| **D** | 混合推理 | LiteLLM 路由、脱敏、预算熔断、离线降级 | `app/router/` |
| **E** | 人工审核 | `interrupt()`/`resume()`、超时、并发锁、幂等 | `app/graph/nodes/review.py` |
| **F** | 报告与写操作 | 报告 Schema、图外 `generate_report`、幂等键 | `app/report/` |
| **G** | 可靠性与可观测 | Checkpointer、重试、Langfuse Trace、指标打点 | `app/observability/` |

### 4.1 依赖关系

```
A ─► B ─► C ─► D
         └─► E ─► F
A,G ───────────►（贯穿）
```

---

## 五、分周计划（P3-D1 – P3-D25）

### 第 1 周（D1–D5）· 图骨架与只读节点

| 天 | 任务 | 产出 |
|---|---|---|
| D1 | 建立 StateGraph 骨架 + `DiagnosisState`（Pydantic 校验）；接入 Checkpointer（按 Phase 0 结论） | `app/graph/build.py` |
| D2 | `parse_alarm`（确定性规则：设备/测点/阈值/严重度）+ `AlarmEvent` 规范化 | `app/graph/nodes/parse_alarm.py` |
| D3 | `analyze_sensor` 接入 `query_sensor`（错误码/超时/重试） | `app/graph/nodes/analyze_sensor.py` |
| D4 | `retrieve_evidence` 接入 `retrieve_knowledge` + `query_graph`（并行） | `app/graph/nodes/retrieve_evidence.py` |
| D5 | `get_history` 接入 + 四只读节点串联冒烟（用固定告警跑通） | `reports/p3-skeleton.md` |

> **出口 M3.1**：只读链路跑通，State 流转正确。

### 第 2 周（D6–D10）· 诊断推理与报告

| 天 | 任务 | 产出 |
|---|---|---|
| D6 | 诊断 Prompt v1（证据约束、引用强制、输出 JSON Schema） | `prompts/diagnose_v1.md` |
| D7 | `diagnose` 节点接入 `deepseek-r1:7b`（剥离 `think`、约束解码） | `app/graph/nodes/diagnose.py` |
| D8 | 根因/建议抽取 + 与证据关联（每条结论挂 `citation`） | 同上 |
| D9 | 报告 Schema 定义（`reports` 表 + `payload` JSONB） | `db/migrations/0003_reports.sql` |
| D10 | 图外 `generate_report`（幂等键 + 唯一索引） | `app/report/generate.py` |

> **出口 M3.2**：完整节点链可产出结构化诊断结论与报告。

### 第 3 周（D11–D15）· 置信度与混合推理

| 天 | 任务 | 产出 |
|---|---|---|
| D11 | 复合置信度实现（检索 0.35 / 传感器 0.20 / 图谱 0.15 / 自评 0.30） | `app/confidence/compute.py` |
| D12 | 置信度校准集构建（用评测集标注正确/错误）+ 温度缩放 | `app/confidence/calibrate.py` |
| D13 | ECE 评估（目标 ≤0.10）；阈值 0.75 依据落定 | `reports/p3-calibration.md` |
| D14 | LiteLLM 云端路由：脱敏前置 + 超时 + 失败降级 | `app/router/cloud.py` |
| D15 | 预算熔断（`budget:cloud:{day}`）+ 离线降级；条件边全量接入 | `app/router/budget.py` |

> **出口 M3.3**：置信度可解释、校准达标，混合路由生效。

### 第 4 周（D16–D20）· 人工审核与可靠性

| 天 | 任务 | 产出 |
|---|---|---|
| D16 | 高风险**确定性规则**判定（关键词/操作类型，**不依赖 LLM**）+ `interrupt()` 审核节点 | `app/graph/nodes/review.py`、`configs/risk_rules.yml` |
| D17 | `resume()` 恢复 + 审核状态机（pending/approved/rejected/timeout） | 同上 |
| D18 | 审核生命周期：4h 通知备用审核人、24h 超时降级、并发锁 `lock:review:{thread_id}` | `app/review/lifecycle.py` |
| D19 | 幂等：写操作 `idempotency_key`；**写操作移出图内**验证 | `app/report/idempotency.py` |
| D20 | 可靠性测试：杀进程恢复、重复 resume、Redis 驱逐防护（`noeviction`） | `reports/p3-reliability.md` |

> **出口 M3.4**：审核链路可靠，无重复副作用。

### 第 5 周（D21–D25）· 可观测、端到端与验收

| 天 | 任务 | 产出 |
|---|---|---|
| D21 | Langfuse Trace 全覆盖（每节点 span + 工具调用 + token 统计） | `app/observability/tracing.py` |
| D22 | 指标打点：节点耗时、置信度分布、升级率、降级率、审核覆盖率 | `app/observability/metrics.py` |
| D23 | 端到端场景测试（主场景"离心泵轴承振动"+ 高风险/低置信/云端升级） | `tests/e2e/` |
| D24 | 安全加固：输入净化（Prompt 注入）、工具白名单、审计落库 | `app/security/` |
| D25 | 验收汇总 + `p3-handover-p4.md` | **M3.5** |

---

## 六、关键模块详细设计

### 6.1 节点实现范式

```python
async def analyze_sensor(state: DiagnosisState) -> dict:
    try:
        out = await with_timeout(query_sensor(state.alarm.device_id, ...), 3.0)
        return {"sensor_report": out}
    except TimeoutError:
        return {"errors": [{"node": "analyze_sensor", "code": "E_TIMEOUT"}],
                "retry_count": state.retry_count + 1}
```

**统一约定**：只读工具在图内；节点只返回**增量 dict**（LangGraph 合并）；异常写 `errors` 而非抛出（由路由统一处置）。

### 6.2 诊断 Prompt 与输出约束

```
系统：你是工业设备诊断专家。仅基于提供的证据做判断。
规则：
 1) 每条根因/建议必须挂 citation（chunk_id 或 graph path）；
 2) 无证据支撑时输出"依据不足"，不得编造；
 3) 涉及停机/高压/电气/动火/吊装等操作，标记 requires_review=true；
 4) 输出严格 JSON Schema（见 prompts/diagnose_v1.md）。
```

**输出结构**：

```json
{
  "diagnosis": "…",
  "root_causes": [{"cause": "轴承磨损", "citations": ["c_00123"], "confidence_hint": 0.8}],
  "suggestions": [{"action": "检查润滑", "citations": ["c_00456"], "risk": "low"}],
  "requires_review": true
}
```

### 6.3 置信度实现（对接 V5.0 §6.1）

```python
confidence = (
    0.35 * retrieval_score      # Top-K 检索分归一化均值
  + 0.20 * sensor_consistency   # 传感器异常与候选故障模式一致性
  + 0.15 * graph_support        # 有路径=1，无=0.3
  + 0.30 * llm_self_score       # 温度缩放后的自评
)
```

- `confidence_breakdown` 全量写入 State（可解释）；
- 校准流程：评测集标注 → 温度缩放 → `ECE ≤0.10` → 反推 0.75 阈值；
- **阈值变更须重新校准并记录**。

### 6.4 混合推理路由

| 项 | 设计 |
|---|---|
| 网关 | LiteLLM（OpenAI 兼容） |
| 触发 | `confidence ∈ [0.50, 0.75)` |
| 脱敏 | 送云端前剥离设备编号/工艺参数/厂区信息 |
| 超时 | 20s；失败 → 降级（`degrade_reason="cloud_unavailable"`） |
| 预算 | `budget:cloud:{day}` 计数，超限熔断 → 强制本地降级 |
| 记录 | 每次升级写审计（含脱敏前后 hash） |

### 6.5 人工审核生命周期

| 项 | 策略 |
|---|---|
| 触发 | 条件路由优先级 4（`risk_level == "high"`） |
| 判定源 | **确定性规则**：`configs/risk_rules.yml` 中的关键词/操作类型；**不依赖 LLM** |
| 中断 | `interrupt(payload={report_preview, risk_level, evidence})` |
| 恢复 | `resume({action, comment, reviewer_id})` |
| 超时 | 4h → 通知备用审核人；24h → 自动转"待人工确认"状态，**流程不挂起** |
| 并发 | `lock:review:{thread_id}` SETNX，防双审核人重复出报告 |
| 职责分离 | 报告提交者**不得**自审 |
| Checkpoint | 不设 TTL + `noeviction`；审核完成即归档 |

### 6.6 报告与幂等

```python
idempotency_key = sha256(f"{thread_id}:{sorted(citation_ids)}:{risk_level}")
```

- PG `reports.idempotency_key` 建**唯一索引**；
- `generate_report` **在图外**、审核通过后调用；
- 重复调用返回既有 `report_id`（不新建）。

### 6.7 可观测性

| 维度 | 实现 |
|---|---|
| Trace | Langfuse：每节点一个 span；工具调用记录入参/耗时；LLM 记录 token/`think` 占比 |
| 指标 | 节点 P95、置信度分布、云端升级率、降级率、审核覆盖率、审核平均时长 |
| 日志 | 结构化 JSON（`trace_id` 贯穿） |
| 告警 | 审核超时、云端预算超限、checkpoint 异常增长 |

---

## 七、里程碑

| 里程碑 | 内容 | 时间 | 通过条件 |
|---|---|---|---|
| **M3.1** | 图骨架与只读链路 | D5 | 四只读节点串联冒烟通过 |
| **M3.2** | 诊断与报告 | D10 | 产出结构化结论 + 报告落库（幂等） |
| **M3.3** | 置信度与混合推理 | D15 | `ECE ≤0.10`；路由与熔断生效 |
| **M3.4** | 审核与可靠性 | D20 | 重启恢复 + 无重复副作用 + 并发安全 |
| **M3.5** | 可观测与验收 | D25 | Trace/指标齐备；e2e 通过；移交 Phase 4 |

---

## 八、测试计划

### 8.1 分层测试

| 层级 | 范围 | 用例 |
|---|---|---|
| 单元 | 节点函数、置信度公式、风险规则 | 输入输出契约、边界值 |
| 契约 | 五工具入参/返回符合 `tools_v1.json` | 合法/非法/超时/错误码 |
| 集成 | 图内多节点串联、Checkpointer | 状态合并、增量返回 |
| 端到端 | 完整告警→报告 | 见 §8.2 |

### 8.2 端到端场景（必测）

| # | 场景 | 期望 |
|---|---|---|
| E1 | 主场景：离心泵轴承振动异常（中风险） | 正常出报告，含引用 |
| E2 | 高风险（涉及停机） | 触发 `interrupt()` 人工审核 |
| E3 | 低置信度（<0.5） | 输出降级"初步判断" |
| E4 | 中置信度（0.5–0.75，云端可用） | 升级云端并成功出报告 |
| E5 | 中置信度 + 云端不可用 | 离线降级，标注原因 |
| E6 | 工具超时/失败 | 重试 ≤3 次后降级 |
| E7 | 服务重启于审核中 | resume 后状态完整、无重复报告 |
| E8 | 双审核人并发 resume | 仅产生 1 份报告（锁生效） |
| E9 | 审核超时 | 4h 通知备用；24h 降级不挂起 |
| E10 | Prompt 注入尝试 | 被净化拦截，工具白名单不被绕过 |

### 8.3 测试纪律

- 固定 `seed` 与 `temperature`，保证可复现；
- 每场景记录到 `experiment-log`；
- e2e 结果纳入 `reports/p3-e2e.md`。

---

## 九、验收标准与门禁

### 9.1 量化指标

| 指标 | 目标 |
|---|---|
| 工具调用首次成功率 | ≥ 90%（Phase 0 V1 结论复核） |
| 引用正确率 | ≥ 90%（每条结论均有来源） |
| **幻觉率** | **≤ 10%**（人工 3 级评分） |
| 置信度 ECE | ≤ 0.10 |
| 高风险审核覆盖率 | 100% |
| 重启恢复成功率 | 100% |
| 重复副作用（恢复/并发） | 0 |
| `P95 端到端`（本地路径） | < 3s |

### 9.2 门禁判定

| 情况 | 处置 |
|---|---|
| 全项达标 | **M3.5 通过**，进入 Phase 4 |
| 幻觉率 10–15% | 中间区间：加强引用强制 + 降级阈值上调；记录处置 |
| `P95` 3–4s | 中间区间：缓存 + 减少云端升级概率；记录延迟-质量权衡 |
| 引用正确率 <90% | **阻塞**：引用强制未生效，必须修复 |
| 恢复后出现重复报告 | **阻塞**：幂等/写操作位置缺陷，必须修复 |

> 中间区间 **≠ 通过**，须写处置动作与代价。

---

## 十、风险与应对

| 编号 | 风险 | 影响 | 应对 | 归属 |
|---|---|---|---|---|
| P3-R1 | `deepseek-r1:7b` 输出不可解析 | 诊断节点失败 | 剥离 `think` + JSON 约束解码 + 重试 | W2 |
| P3-R2 | 置信度校准不达标 | 路由失真 | 检查自评校准；必要时降权自评、提高检索权重 | W3 |
| P3-R3 | 云端升级拖慢端到端 | `P95` 超标 | 预算熔断 + 缓存 + 计入单独统计口径 | W3 |
| P3-R4 | 显存争抢（推理+重排） | 延迟抖动 | 错峰调度；重排降级 CPU | 全程 |
| P3-R5 | Checkpointer 缺陷 | 审核不可恢复 | 按 Phase 0 `known-issues.md` 规避；必要时切 PG | W4 |
| P3-R6 | 恢复后重复写报告 | 数据污染 | 写操作移出图内 + 幂等键唯一索引 | W4 |
| P3-R7 | Prompt 注入 | 越权/绕过审核 | 输入净化 + 工具白名单 + 高风险判定不依赖 LLM | W5 |
| P3-R8 | 高风险判定漏报 | 安全风险 | 规则覆盖操作类型清单 + 评审 | W4 |
| P3-R9 | 节点异常吞掉导致空结论 | 输出不可用 | `errors` 统一路由 + 降级而非静默 | 全程 |

---

## 十一、交付物与目录

### 11.1 目录增量

```
project/
├─ app/
│  ├─ graph/
│  │  ├─ build.py                 # StateGraph 组装
│  │  ├─ state.py                 # DiagnosisState
│  │  └─ nodes/
│  │     ├─ parse_alarm.py
│  │     ├─ analyze_sensor.py
│  │     ├─ retrieve_evidence.py
│  │     ├─ get_history.py
│  │     ├─ diagnose.py
│  │     ├─ review.py
│  │     └─ finalize.py
│  ├─ confidence/
│  │  ├─ compute.py
│  │  └─ calibrate.py
│  ├─ router/
│  │  ├─ cloud.py                 # LiteLLM 路由 + 脱敏
│  │  └─ budget.py                # 预算熔断
│  ├─ report/
│  │  ├─ generate.py              # 图外写操作
│  │  └─ idempotency.py
│  ├─ review/lifecycle.py
│  ├─ observability/{tracing.py,metrics.py}
│  └─ security/sanitize.py
├─ prompts/diagnose_v1.md
├─ configs/{risk_rules.yml,router.yml}
├─ db/migrations/0003_reports.sql
├─ tests/{unit,contract,e2e}/
└─ reports/
   ├─ p3-skeleton.md
   ├─ p3-calibration.md
   ├─ p3-reliability.md
   ├─ p3-e2e.md
   └─ P3-summary.md
```

### 11.2 交付物清单

| 类别 | 交付物 |
|---|---|
| 编排 | 状态图 + 六节点 + 条件路由 |
| 推理 | 诊断 Prompt + 根因/建议抽取 + 引用强制 |
| 置信度 | 复合公式 + 校准报告 + 阈值依据 |
| 路由 | 云端升级（脱敏/熔断/降级） |
| 审核 | `interrupt/resume` + 生命周期 + 并发锁 |
| 报告 | 报告 Schema + 图外幂等写 |
| 可靠性 | Checkpointer 配置 + 恢复测试报告 |
| 可观测 | Langfuse Trace + 指标打点 |
| 移交 | `p3-handover-p4.md` |

---

## 十二、检查清单

### 通用规则
- [ ] 五工具调用严格遵循 `tools_v1.json`，禁止绕过契约
- [ ] 节点异常统一写 `errors`，由路由处置，不静默
- [ ] 所有 LLM 调用固定 `seed`/`temperature` 并记录
- [ ] 写操作**一律在图外**，携带幂等键

### 第 1 周（M3.1）
- [ ] State 类型化 + Pydantic 校验生效
- [ ] 四只读节点串联冒烟通过
- [ ] Checkpointer 按 Phase 0 结论接入

### 第 2 周（M3.2）
- [ ] 诊断输出符合 JSON Schema
- [ ] 每条结论均有 citation
- [ ] 报告落库 + 幂等唯一索引

### 第 3 周（M3.3）
- [ ] 复合置信度 + breakdown 落盘
- [ ] ECE ≤0.10，阈值依据可解释
- [ ] 云端路由含脱敏 + 熔断 + 降级

### 第 4 周（M3.4）
- [ ] 高风险确定性规则生效
- [ ] `interrupt/resume` + 超时 + 并发锁
- [ ] 重启恢复无重复副作用

### 第 5 周（M3.5）
- [ ] Langfuse Trace 全覆盖
- [ ] E1–E10 端到端全部通过
- [ ] 安全加固（注入/白名单/审计）
- [ ] `p3-handover-p4.md` 齐备

---

## 附：Phase 3 → Phase 4 移交要点

| 移交项 | 用途 |
|---|---|
| 状态图与节点接口 | 前端触发诊断 / 展示进度 |
| `diagnosis:progress` / `diagnosis:done` 事件 | Socket.IO 实时推送 |
| `review:required` payload 结构 | 审核界面渲染 |
| 审核状态机与超时策略 | 前端审核操作与超时提示 |
| 报告 Schema | 报告详情页展示 |
| 置信度 breakdown | 前端展示"为何这样判断" |
| Langfuse Trace | 演示时的可追溯证据 |
