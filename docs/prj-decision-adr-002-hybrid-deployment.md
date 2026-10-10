# ADR-002：混合部署形态（本地优先 + 云端脱敏兜底）与不采用 LiteLLM 网关

> **层级**：项目级长期有效（ADR）｜ **对应里程碑**：`M6.1`（Phase 6 文档收口 · D5 产出）｜ **状态**：🟢 **活动**｜ **最近更新**：2026-10-10

---

## 一、状态

**Accepted**（2026-10-10 收敛确认）。
上游决策时点如实标注：混合部署形态选型于 `plan/工业设备诊断 Agent.md` §3.8 定稿（2026-09-21，V5.0 定稿）；「不采用 LiteLLM」的口径裁定于 2026-10-10 由用户确认（`docs/prj-design-architecture.md` §二 口径裁定 + §八 选型偏离登记表），本 ADR 为该裁定的**完整详述载体**（架构文档不重复，以免两处口径分叉）。

## 二、背景（Context）

- **合规刚性**：设备参数、工艺曲线不可上传公有云；纯云端形态直接被否（`plan/工业设备诊断 Agent.md` §3.8）。
- **本地能力有边界**：7B 模型推理质量封顶，需云端"最后保险"（同上 §3.8）。
- **可用性**：断网仍可完整跑通主流程，云端故障可降级（同上 §3.8）。
- **上游遗留**：`plan/工业设备诊断 Agent.md` §3.1 选型总表与 §4.1 分层图曾列「LLM 网关 LiteLLM（多云 fallback）」，§4.1 推理层写作「LiteLLM 网关」；实装后该表述**未落地**，需一份 ADR 把"为什么不用"说清楚（`docs/prj-design-architecture.md` §二 口径裁定 2026-10-10）。

## 三、决策（Decision）

### 3.1 混合部署形态：本地优先 + 云端脱敏兜底

| 要素 | 定稿口径 | 出处 |
|---|---|---|
| 形态 | **混合架构、本地优先**；纯云端/纯本地均不采纳 | `plan/工业设备诊断 Agent.md` §3.8 结论 |
| 升级触发 | 置信度 ∈ [0.50, 0.75) → `escalate_cloud`；云端失败 → 降级保留本地诊断 | `plan/工业设备诊断 Agent.md` §5.4；`app/graph/build.py` `_route_condition` |
| 脱敏前置 | 送云端前 `device_id` → `设备#<sha256[:6]>`（可追溯不可逆），剥离厂区/工艺参数标识，仅传"故障现象 + 通用知识 + 统计摘要"，**不传证据原文** | `plan/工业设备诊断 Agent.md` §3.8、§七 防线①；`app/router/cloud.py` `sanitize_state`/`_hash_device_id` |
| 预算熔断 | 每日上限 340 次（`budget:cloud:{YYYY-MM-DD}` Redis 按天计数），超限 → `degrade_reason="budget_exceeded"`；Redis 不可达不阻塞（审计记录） | `plan/工业设备诊断 Agent.md` §5.7、§7.1（R-M4）；`app/router/budget.py`；`app/api/config.py` `CLOUD_BUDGET_LIMIT` |
| 超时与降级 | 云端 20s 超时；失败 → `cloud_unavailable`，保留本地诊断并显式标注 `degrade_reason` | `plan/工业设备诊断 Agent.md` §5.4；`app/router/cloud.py` `CLOUD_TIMEOUT_SEC=20.0` |
| 审计 | 每次升级写 `reports/cloud_audit.jsonl`（脱敏前后 hash + 预算计数 + 延迟） | `app/router/cloud.py` `write_audit` |
| 术语澄清 | 项目名"云侧"指相对设备侧的"平台侧"层级，**不等于必须部署公有云** | `plan/工业设备诊断 Agent.md` §3.8 术语澄清 |

### 3.2 不采用 LiteLLM 网关，改自研 LLM 适配层

**决策**：推理层不自建/不引入 LLM 网关中间件；本地与云端两条调用路径均为**自研直调适配层**（本地 Ollama 原生 API + 云端 OpenAI 兼容端点），业务安全逻辑（脱敏/预算/审计/降级）在同一适配层内实现。

#### (a) 事实面（代码与依赖现状，2026-10-10 逐项验证）

| # | 事实 | 验证方式与结果 |
|---|---|---|
| F1 | **依赖清单无 litellm** | `requirements.txt` 全文核查：无 `litellm` 声明；全部依赖 `==` 精确锁定且注释要求与 `docs/prj-ledger-version-lock.md` 同步 |
| F2 | **全仓零代码引用** | Grep（不区分大小写）`litellm`：仅命中 4 个文件——`plan/工业设备诊断 Agent.md`（§3.1/§4.1 早期设计表述）、`plan/Phase 3 详细开发计划（Agent 工作流实现）.md`（节点表/模块表早期表述）、`app/router/__init__.py`（模块注释历史命名"D14: cloud.py — LiteLLM 云端路由"，**注释性旧称、非依赖引用**）、`docs/prj-design-architecture.md`（§二 口径裁定 + §八 偏离登记）。`app/` 与 `scripts/` 代码零 import |
| F3 | **云端调用为自研直调** | `app/router/cloud.py`：标准库 `urllib.request` POST OpenAI 兼容端点（配置读 `env/cloud.json`：provider/model/endpoint/api_key/budget_lock），`temperature=0.0`、`max_tokens=2048`，20s 超时，失败映射 `degrade_reason ∈ {budget_exceeded, cloud_unavailable}`（错误码 `E_BUDGET_EXCEEDED`/`E_CLOUD_UNAVAILABLE`/`E_CLOUD_JSON_PARSE`） |
| F4 | **预算熔断为自研** | `app/router/budget.py` `BudgetGuard`：Redis `INCR` 按天计数 + `EXPIRE` 7 天审计窗口，超 `per_day_calls` 熔断；Redis 不可达 → 不阻塞（`ok=True` + `reason="redis_unreachable"` + 审计）。预算上限 340 由 `app/api/config.py` `CLOUD_BUDGET_LIMIT`（`env/cloud.json` `budget_daily_limit` 可覆盖）暴露至 `/api/health` |
| F5 | **约束解码为自研路径** | `scripts/gbnf_grammar.py`：文件名沿用早期「GBNF」口径，**实际产出 JSON Schema dict**（顶层 `{type:array, items:{oneOf:[5 工具]}}`，`name` 用 `const` 锁定、全局 `additionalProperties:false`），供 Ollama 原生 `/api/chat` 的 `format` 字段——因 Ollama 0.34.2 **拒绝原始 GBNF 字符串**（报 `expected "json" or a valid JSON Schema object`）；`--selftest` 通过；由 `scripts/llm_adapter.py`/`run_v1.py`/`run_cloud_baseline.py` 消费（此链路**仅用标准库**，见 `requirements.txt` 头注） |
| F6 | **自研链路已实测闭环** | 约束解码全量实测（EXP-V1-003）：双模型参数 JSON 可解析率 **1.00**，格式退化（JSON 不可解析/参数缺失/`ToolCallsMissing`）**根除**；P5 安全回归预算熔断 340 通过、八项安全回归全过 | 

F6 出处：`docs/p0-decision-model-role.md` §4.1/§6.2；`docs/p5-handover-p6.md` §一 M5.3。

#### (b) 理由面（每条标注出处或"推断"）

| # | 理由 | 性质标注 |
|---|---|---|
| R1 | **Provider 仅两种形态**：本地 Ollama（宿主 `127.0.0.1:11434`）+ 云端单个 OpenAI 兼容端点兜底（`Qwen/Qwen3.8-27B` @ ModelScope）。LiteLLM 的核心价值是多云 fallback 与多 provider 归一（上游唯一理由即"多云 fallback"，`plan/工业设备诊断 Agent.md` §3.1），在"1 本地 + 1 云端"场景下该收益大部分落空 | Provider 数量 = **出处**（`README.md` §当前状态速览；`app/router/cloud.py`；`env/cloud.json` 键结构）；"收益落空"的工程判断 = **推断** |
| R2 | **约束解码走自研路径已闭环**：`gbnf_grammar.py` → JSON Schema → Ollama `format` 的链路实测可解析率 1.00（F5/F6）。LiteLLM 是否能等价透传 Ollama `format`/JSON Schema 级约束，项目文档无论述、本仓未实测 | **推断性理由（如实标注）**：前半句为实测事实（出处 `docs/p0-decision-model-role.md` §4.1/§6.2），后半句"LiteLLM 透传能力未验证"为推断——若未来引入须先实测 |
| R3 | **预算熔断/脱敏/审计属业务安全逻辑，本就自研**：`budget.py`/`cloud.py` 已实现"按天计数 + 脱敏前置 + jsonl 审计 + 显式降级"；LiteLLM 的路由/预算功能不覆盖这套项目自有语义（防线①脱敏、R-M4 预算熔断为项目安全设计），引入网关后这两块**仍需自研**，形成重复建设 | **出处**：`app/router/budget.py`、`app/router/cloud.py` 实装；`plan/工业设备诊断 Agent.md` §七 防线①、§7.1 R-M4 |
| R4 | **P6 收敛期不新增依赖**：Phase 5 收口判定"停止扩展范围，转入收敛交付"；依赖变更须同步 `docs/prj-ledger-version-lock.md`（纪律）。收敛期引入网关属反向操作 | **出处**：`docs/p5-handover-p6.md` §三 结论；`requirements.txt` 头注纪律 |
| R5 | **LiteLLM 本就是"未落地的早期表述"**：`docs/prj-ledger-version-lock.md` 无该依赖、代码无该引用（F1/F2），D14/D15 实装按 Phase 3 计划直接自研直调 | **出处**：`docs/prj-design-architecture.md` §二 口径裁定（2026-10-10 用户确认）；`app/router/cloud.py` 文件头交付物指针 |

## 四、备选方案与放弃理由（Options & Rejected）

**备选：引入 LiteLLM 作为 LLM 网关**（上游 §3.1/§4.1 早期设计）。若采用的预期收益与代价如下，**"实测/推断"分开标注**：

| 类别 | 内容 | 性质 |
|---|---|---|
| 预期收益 ① | 多云 fallback 与多 provider 统一接入层 | 出处（`plan/工业设备诊断 Agent.md` §3.1「多云 fallback」为上游唯一列明理由） |
| 预期收益 ② | 重试/超时/负载均衡内建 | **推断** |
| 预期收益 ③ | Token 计量与成本核算统一 | **推断** |
| 代价 ① | 新增第三方依赖：违反收敛期纪律，且须登记 `docs/prj-ledger-version-lock.md` 并纳入版本漂移监控（R-M10） | 出处（`docs/p5-handover-p6.md` §三；`requirements.txt` 纪律；`plan/工业设备诊断 Agent.md` §8.2 R-M10） |
| 代价 ② | 业务安全逻辑（脱敏前置/按天预算/jsonl 审计/降级语义）网关不覆盖，仍须自研并维护两层 | 出处（F3/F4 实装事实 + `plan/工业设备诊断 Agent.md` §七） |
| 代价 ③ | 自研约束解码路径（F5）能否经网关等价透传未验证，替换有实测风险 | **推断** |
| 代价 ④ | 自研适配层已实测可用（F6），替换属无增量收益的重构，收敛期引入回归风险 | 前半句出处（F6）；"无增量收益/回归风险"为**推断**（基于 P5 收敛纪律） |

**结论**：放弃 LiteLLM；该偏离已登记 `docs/prj-design-architecture.md` §八 选型偏离登记表（❌ 未采用）。

## 五、后果（Consequences）

| 类型 | 内容 |
|---|---|
| ✅ 正面 | 零新增依赖（收敛期纪律兼容）；调用路径单一、逐次审计可追溯（`cloud_audit.jsonl` 含脱敏前后 hash）；安全语义（脱敏/预算/降级）与调用同层实现，无跨层约定 |
| ⚠️ 负面 | 网关通用能力（自动重试、多实例负载均衡、多 provider 热切换）需自研时才具备；云端输出 JSON 解析失败仅计审计并按 `cloud_unavailable` 降级（`E_CLOUD_JSON_PARSE`），无自动修复 |
| 📎 已知边界 | `app/router/__init__.py` 模块注释残留"D14: cloud.py — LiteLLM 云端路由"历史命名（文档债，D5 仅在此登记、不改代码）；云端配置 `env/cloud.json` 含 API key、被 `.gitignore` 排除（`docs/prj-spec-document-standard.md` §五）；P95 端到端未达标与云端无关（瓶颈在本地生成输出长度，`docs/p5-handover-p6.md` §五） |

## 六、事实源

- `plan/工业设备诊断 Agent.md` §3.1、§3.8、§4.1、§5.4、§5.7、§7.1、§8.2
- `docs/prj-design-architecture.md` §二（口径裁定）、§5.6、§八（选型偏离登记）
- `requirements.txt`
- `app/router/cloud.py`、`app/router/budget.py`、`app/api/config.py`、`app/router/__init__.py`
- `scripts/gbnf_grammar.py`、`scripts/llm_adapter.py`
- `docs/p0-decision-model-role.md` §4.1、§6.2
- `docs/p5-handover-p6.md` §一、§三、§五
- `README.md` §当前状态速览

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | Phase 6 D5 初版（混合部署形态 + LiteLLM 不采用详述；事实面 6 项逐条验证、理由面 5 条逐条标注出处/推断） | 本文件 |
