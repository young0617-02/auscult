# P7 设计 — 诊断 Agent 化：统一 LLM 客户端 + Agent 循环（云端临时承载，本地为目标形态）

> **文件编号**：`docs/p7-design-agent-diagnosis-2026-10-19.md`
> **日期**：2026-10-19 ｜ **阶段**：P7（收口后维护期）｜ **状态**：🟢 **已落地（代码 + 测试 + 本文档）**
> **纪律声明**：M6.4（2026-10-10）已收口进入维护期；本文档对应**所有者显式指示的扩范围动作**（用户三项判决，见 §一），非自发扩范围。判决记录以本文档为准。

---

## 〇、一句话

把诊断段从「固定编排 + LLM 只做推理」升级为「**LLM 自主规划工具调用的 Agent 循环**」；LLM 调用统一为**可切后端的单一客户端出口**；现阶段用**云端 API 承载测试开发**，换硬件 + qwen3:32b 后**配置翻转即回本地**，云端降为 escalate 兜底路径。

## 一、用户三项判决（2026-10-19，本文档的授权依据）

| # | 判决 | 落地口径 |
|---|---|---|
| ① | 测试文档上云无所谓，脱敏可做；云端是临时形态，**一切以后期切回本地为主**；回本地后无合规要求 | 不因合规阻塞开发；`app/router/cloud.py` 既有脱敏/预算/审计三件套保留；**主路上云的脱敏范围重审列为上线前闸门**（§六 U1），不进本次代码 |
| ② | 先建**统一 LLM 客户端抽象**，现在用云端测试开发，保证 Agent 化后系统正常，后期可直接切回本地 | 本次落地核心（§三） |
| ③ | Agent 化与优化交由执行方落地；信息不足/冲突时提问判决 | 冲突与信息不足项均已显式登记（§六 U1–U4），无阻塞项 |

## 二、目标 / 非目标

**目标**

- G1 单一 LLM 出口：`app/llm`（本地 Ollama / 云端双传输，tools 通道，配置驱动）；
- G2 Agent 循环节点：LLM 自主调工具取证 → 回灌 → 收口诊断 JSON（`max_steps` 封顶）；
- G3 模式开关：`AUSCULT_DIAGNOSIS_MODE=agent\|deterministic`，**下游契约与路由不变**；
- G4 可逆：后期 `AUSCULT_LLM_BACKEND=local` + 本地 32B 即完成主体回迁，云端自动降兜底；
- G5 全离线回归（新增 30 例含 agent 模式全图集成，`pytest` 全量 238 passed）。

**非目标（本次明确不做）**

- N1 不做多实例/多 worker 并发验证（V5 同款口径限制，单实例部署）；
- N2 不重定 P95 端到端基线（Agent 多轮往返的延迟实测后再定，§六 U2）；
- N3 不改 `prompts/`、`schemas/`（冻结区零触碰；Agent 系统提示词内嵌于 `app/agent/prompt.py`，拒止规则逐字沿用 prompt v4）；
- N4 不做微调/量化；不动审核 interrupt / 幂等 / 降级链路。

## 三、架构

### 3.1 统一 LLM 客户端（`app/llm/`）

```
app/llm/
├─ config.py     # 后端/模式/角色模型/参数访问器（env 优先，函数级读取可测）
└─ client.py     # OpenAICompatClient（本地+云端共用传输）+ get_client(role) 工厂
```

- **请求形态**逐字沿用 `scripts/llm_adapter.py` 的 `--transport tools` 实测载荷：`tools` + `tool_choice=auto`（H5/ISS-027/R-V1-9：**禁用 `required`**，云端静默退化）；`options.num_ctx` 对非 Ollama 后端安全忽略。
- **异常契约**与 `nodes/diagnose.py` 既有口径一致：`TimeoutError` / `ConnectionError` / `RuntimeError` → 上层走「重试 → 降级」既有路由。
- **角色模型**：`role=diagnose`（确定性诊断，默认 `deepseek-r1:7b`）/ `role=agent`（Agent 循环，默认 `qwen2.5:7b`）；**后期单模型 32B 双角色合一**（两个 env 指向同一模型即可，ADR-001 §五「单模型全角色」备选的否决理由——7B 能力不足——在 32B 条件下消失，须按 §六 U3 重测后正式重评）。
- **调用点收敛**：`nodes/diagnose.py::_call_ollama`（原硬编码本地 Ollama）与 `router/cloud.py::call_cloud`（原硬编码云端）均改为经本客户端；签名与审计/缓存语义不变。

### 3.2 Agent 循环节点（`app/graph/nodes/agent_diagnose.py`）

```
parse_alarm → diagnose[agent_diagnose] → [条件路由，与确定性形态逐字相同]
                    │
                    ├─ 每轮：client.chat(messages, tools=只读工具面)
                    ├─ 有 tool_calls → 白名单校验 → execute_tool → role=tool 回灌 → 下一轮
                    ├─ 无 tool_calls → _strip_think + _extract_json → 诊断契约
                    └─ 达 max_steps（默认 4）→ 无工具强制收口轮
```

- **证据归集**（`_Collector`）：工具结果 → `EvidenceItem`（knowledge/graph）/ `sensor_report` / `WorkOrder` / `GraphPath`，形状与 `analyze_sensor`/`retrieve_evidence`/`get_history` 节点对齐 → `finalize` 引用校验与置信度复合公式原样生效。
- **写操作护栏**：`generate_report` **不进工具面**（ADR-007）；模型幻觉调用该名 → `tool_registry` 拦截并回灌拒绝原因（白名单外用 `sanitizer.validate_tool_call` 同一口径，拒绝落审计 `tool_call`）。
- **失败契约**：LLM 传输失败 → `retry_count++` + `diagnosis=None` → 命中 ISS-048 修复后的第 0 优先级自循环重试（≤3 次）→ degrade。**离线兜底即当前确定性图**（本地 Ollama 可用时切 `AUSCULT_DIAGNOSIS_MODE=deterministic` 即可回退）。
- **预算**：后端为 cloud 时每轮调用过 `BudgetGuard`（熔断 → `degrade_reason=budget_exceeded`，不计费）；仅成功调用计数。**算术：一次诊断 ≤ max_steps+1 次调用 → 日均容量 = 340 / 调用数 ≈ 68–85 次诊断/天**（`AUSCULT_CLOUD_BUDGET_LIMIT` 可调，调锁纪律同 V1：超限先调锁再跑）。
- **轨迹**：`DiagnosisState.agent_steps`（追加语义，dict 载荷，msgpack 友好）逐轮记录 tool/ok/args_keys/latency。**可观测化闭环（2026-10-19 同日落地）**：`runner._absorb_agent_steps` 把 diagnose 增量归集到线程记录 → `thread_status` 双路径（注册表/重启回退）均返回 `agent_steps` → 前端 `DiagnosisConsole` 右栏「Agent 工具调用」列表点击 → `InspectorDrawer` 工具页签展示单步出入参（**只传参数键名，不传值**）；`/api/health` 新增 `llm` 探针（backend/mode/模型快照，不含密钥，配置非法降级 `config_invalid`）。前端 vitest 53 例全绿。

### 3.3 工具面与适配层（`app/agent/tool_registry.py`）

- 工具定义从 `schemas/tools_v4.json` **程序化加载只读子集**（4 个），OpenAI 格式同 `llm_adapter.load_tools`，description 追增 schema 自带 `when_to_use/when_not_to_use`；
- **schema 形参 → 产品函数适配**：`sensor_ids`/`time_range`（相对/ISO）→ `(device_id, metric, start_ts, end_ts)`；`search_knowledge` → `RetrievalService.retrieve`（D7 最优口径 cuda + no-rerank，设备可 env 覆盖）；`query_graph`/`get_maintenance_history` 直映；
- **已知口径差 ISS-049**：schema 测点短名 `vib_x/vib_y/vib_z` 在 TDengine 无分向列（仅 `vib_rms`），按 `SENSOR_COLUMN_MAP` 归一并在工具结果里**显式告知模型**（不静默丢精度语义）；
- 幻觉时间（未来起点）钳制回 24h 窗口；单次调用测点上限 3；知识块/工单/图谱命中截断后入 prompt（300/20/20）。

### 3.4 模式切换（`app/graph/build.py`）

| 模式 | 图形状 | diagnose 槽位实现 |
|---|---|---|
| `deterministic`（默认） | `parse_alarm → analyze_sensor → retrieve_evidence → get_history → diagnose` | `nodes/diagnose.py`（既有，零行为变化） |
| `agent` | `parse_alarm → diagnose`（gather 链不接入边，节点仍注册供测试打桩） | `nodes/agent_diagnose.py` |

条件路由、degrade/escalate_cloud/human_review/finalize 两模式**完全共用**；`escalate_cloud` 在后端即云端时空转（`W_BACKEND_ALREADY_CLOUD`，不重复计费）——这正是「云端从主通道降为兜底」的逆场景适配。

## 四、配置项（env）

| 变量 | 默认 | 说明 |
|---|---|---|
| `AUSCULT_DIAGNOSIS_MODE` | `deterministic` | `agent` = Agent 循环 |
| `AUSCULT_LLM_BACKEND` | `local` | `cloud` = 走 `env/cloud.json`（测试开发期） |
| `AUSCULT_LOCAL_MODEL_AGENT` | `qwen2.5:7b` | Agent 角色本地模型（后期 `qwen3:32b`） |
| `AUSCULT_LOCAL_MODEL_DIAGNOSE` | `deepseek-r1:7b` | 确定性诊断本地模型（后期 `qwen3:32b`） |
| `AUSCULT_LOCAL_OLLAMA_URL` | `http://127.0.0.1:11434/v1/chat/completions` | 本地端点 |
| `AUSCULT_AGENT_MAX_STEPS` | `4` | 单次诊断最大工具轮数（1–16） |
| `AUSCULT_LLM_TIMEOUT_SEC` / `AUSCULT_LLM_MAX_TOKENS` / `AUSCULT_LLM_NUM_CTX` | `30` / `2048` / `8192` | 推理参数 |
| `AUSCULT_CLOUD_BUDGET_LIMIT` | （cloud.json 的 340） | Agent 模式日预算覆盖 |
| `AUSCULT_RETRIEVAL_DEVICE` | `cuda` | Agent 检索服务设备（CPU 机设 `cpu`） |

## 五、切换 Runbook（现在云端 → 后期本地）

**现在（测试开发，云端承载）**

```powershell
$env:AUSCULT_LLM_BACKEND="cloud"
$env:AUSCULT_DIAGNOSIS_MODE="agent"
.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000
```

**判据闸门（切默认前必过）**：云端 + prompt v4 形（本提示词即 v4 拒止规则的产品化）+ `schemas/tools_v4` 只读面，按 V1 分档判据重跑 `run_e2e`（单工具/参数校验/多轮 ≥85%、多工具 ≥70%、**无效拒绝 ≥90%**——prompt v1 在该档仅 67%，v4 实测 100%）；同日多轮聚合口径（EXP-M02-040 同款）。

> **✅ 已执行（2026-10-20，`experiments/v1/EXP-P7-GATE.md`）**：3 轮同日聚合 75 样本——单工具 88.9% / 参数校验 100% / 多工具 75% / **拒止 100%** / 澄清 100% 全过线，**多轮 77.8% 中间区间**（7/9）→ **整体未过闸，不切默认**。
> 归因：多轮缺口 100% 由 `v1-019` 驱动（2/9）——该用例期望「图内调 `generate_report` 意图」，与 ADR-007（写操作移出图内）及产品 Agent 提示词明文禁令**架构性冲突**，产品语境下不调用才是正确行为；v1-018/v1-020（真实多轮上下文补全）6/6 全过。数学测算：v1-019 通过率 ~1/3 时补跑无法救聚合 → **待用户判决：用例期望重释义（需登记，先例 2026-09-28 判据分档重校）或接受中间区间**。
> 另 4 个失败为参数值错/多工具不全（v1-008/001/004/009），记为已知边界（P1 候选）。

> **✅ 判决已执行（2026-10-20，所有者选 A：授权改冻结区并重跑）**：`v1-019` 重释义为「**不得产生写操作调用**」（`expected_tool_calls=[]` + `forbidden_tool_calls=["generate_report"]`；判分器新增「禁调」语义），修订报告 `reports/p0-report-v1-cases-revision-2026-10-20.md`。
> **复测仍 No-Go（`experiments/v1/EXP-P7-GATE2.md`，3 轮 75 样本、云端 51 次）**：单工具 83.3% / 参数校验 100% / 多工具 50% / **多轮 66.7% No-Go** / 拒止 100% / 澄清 100% → 整体 No-Go，首成 63/75 = 84%。
> **根因修正（新登记 `ISS-052`）**：`v1-019` 三轮**全部调用 `generate_report`**，即缺口不是判据表述，而是 **harness 工具面含写操作、产品 Agent 工具面只有 4 只读工具** → 判据「测非所测」。**默认仍维持 `deterministic`**；下一步候选 = 路径 C（harness 工具面收窄 + `v1-019` 整条替换 + 重跑，属扩范围，须另行授权）或接受 No-Go。

**后期（换硬件 + qwen3:32b，回本地）**

```powershell
$env:AUSCULT_LLM_BACKEND="local"
$env:AUSCULT_LOCAL_MODEL_AGENT="qwen3:32b"
$env:AUSCULT_LOCAL_MODEL_DIAGNOSE="qwen3:32b"
# AUSCULT_DIAGNOSIS_MODE 保持 agent；云端自动仅存于 escalate 兜底路径
```

回迁验证 = 一次 `run_e2e` 分档重测（harness 模型无关）+ 延迟基线重测 + `pytest tests/ -q`。**产品形态在两次切换之间不变，随时可回退到确定性形态**（可逆性即安全垫）。

## 六、未决项与冲突登记（U1–U4）

| # | 项 | 性质 | 处置 |
|---|---|---|---|
| U1 | **主路上云的脱敏范围重审**：现行 `sanitize_state` 按「兜底路径」设计（仅 confidence∈[0.50,0.75) 触发）；Agent 化后所有工具结果过模型眼前。用户判决：测试期不阻塞 | 合规（判决①暂挂） | 上线生产前必须书面重审并显式立项；本文档即暂挂凭据 |
| U2 | **P95 端到端重定**：Agent 多轮往返 × 云端/32B 单轮延迟；现基线 9.25s 已未达标 | 性能 | **已实测（2026-10-20）**：云端单轮 5.5–37s（并行多工具轮更慢）、端到端 **156–226s**（含检索预热 ~30s 与一次 >90s 超时重试）——远超任何「秒级」口径；Agent 化与 P95<3s 在云端形态下**不可兼得**，需按「异步诊断 + 实时进度推送」产品口径重定（Socket.IO 已有进度事件），或本地 32B 后再评 |
| U3 | **ADR-001 §五「单模型全角色」备选重评**：32B 条件下原否决理由消失，但须分档实测后正式重评（不得直接改 ADR） | 决策流程 | 本地 32B 就位后按 V1 判据重测再走 ADR 修订 |
| U4 | **多实例并发**：与 V5 同款口径限制（单进程 SETNX/单实例）；Agent 循环放大调用频次后锁竞争面变大 | 范围外 | 维持单实例部署声明；多 worker 需求出现时另立实验编号 |

## 七、测试与实测

### 7.0 云端实跑记录（2026-10-20，`scripts/smoke_agent_cloud.py`）

> 前置：交付栈 9 容器 healthy；TDengine 复灌（PUMP-A 近 24h 5960 行、峰值 4.812 mm/s 越 4.5 阈值）；
> 形态 `AUSCULT_LLM_BACKEND=cloud + AUSCULT_DIAGNOSIS_MODE=agent`；预算消耗 16/340。

| 轮次 | 形态 | 结果 |
|---|---|---|
| 1（图级） | 30s  diagnose 超时（未角色化） | Agent 循环/工具调用/检索/图谱全部工作；3 次 >30s 超时 → 重试 → 降级出报告（降级链路实战验证）；发现设备号口径问题（PUMP-A-01 vs PUMP-A） |
| 2（图级） | PUMP-A + 90s 角色超时 | **成功**：3 轮自主工具调用（step1 四工具并行 / step2 四工具并行 / step3 两工具）→ 诊断 JSON（发现告警值 7.1 与存储数据不符、疑似误报、轴承温度 71.2°C 略超）→ confidence 0.786 / risk high → 挂起；resume(approved) → **RPT-2387417f17e6b14c**；耗时 156s |
| 3（API 级） | uvicorn + REST 全链 | **成功**：登录 → POST /api/diagnose → 226s 后 waiting_review（其中第 1 次云端调用 >90s 超时 → ISS-048 自循环重试 → 第 2 次成功，**重试分支首次实战**）→ `thread_status.agent_steps` 5 条正确回显 → rev_dev 审核通过 → **RPT-a542b2078222b830 落 PG**（risk high / conf 0.78 / approved）；`/api/health` 的 `llm` 探针正确回显 cloud/agent |

**实跑顺带修复**：ISS-050（解码器 QoS0 订阅 → 灌数丢消息，改 QoS1 + broker 队列扩容）、ISS-051（health 预算探针缺 Redis 鉴权 → used 恒 null）、LLM 超时角色化（diagnose 30s / agent 90s）。
**测试隔离修复**：`test_agent_loop_tool_call_then_final` 原隐含依赖「Milvus 不在线」（基础设施起来后 risk 断言翻转），已打桩 `execute_tool` 恢复离线确定性。

### 7.1 离线回归（全离线、零网络/零云端）

- 新增 `tests/test_agent_diagnosis.py` **32 例**：客户端载荷/双形态 tool_calls/三态异常/工厂；工具面只读子集/白名单/写操作护栏/时间解析/测点映射；Agent 主路径/状态归集/步数封顶/失败重试/JSON 失败/预算熔断；图模式切换（节点实现 + 边形状）；escalate 空转；**agent 模式全图集成**（parse_alarm → agent_diagnose → finalize → report_id）；health llm 探针/runner 轨迹归集。
- 全量回归：`pytest tests/ -q` = **240 passed**（默认 deterministic 形态零行为变化）。
- app 全量 import OK；默认配置快照 = `local + deterministic`（与改动前一致）。
- **实跑工具（转正）**：`scripts/smoke_agent_cloud.py`（`--selftest` 离线自检 / 默认完整链路含审核 resume；docstring 含前置与预算说明）。

## 八、修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-19 | 执行方（按用户三项判决） | 初版：Agent 化设计 + 三项判决记录 + 切换 Runbook + U1–U4 登记 | 本文档；`app/llm/`、`app/agent/`、`app/graph/`、`app/router/`、`tests/test_agent_diagnosis.py`、CHANGELOG、known-issues（ISS-049）、README |
| 2026-10-20 | 执行方（按所有者判决 A） | §五 判据闸门回填：`v1-019` 重释义后复测仍 No-Go（多轮 66.7%）；根因修正为新登记 `ISS-052`（harness 工具面含写操作 → 测非所测）；默认维持 `deterministic`，路径 C 待授权 | 本文档 §五/§八；`experiments/v1/EXP-P7-GATE2.md`；`reports/p0-report-v1-cases-revision-2026-10-20.md` |
