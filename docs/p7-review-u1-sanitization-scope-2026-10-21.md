# U1 复核：Agent 主路上云的脱敏范围（2026-10-21）

> **性质**：合规前置评审（`docs/p7-design-agent-diagnosis-2026-10-19.md` §六 U1 的处置载体）
> **触发**：所有者指示「U1 脱敏重审 —— Agent 自主取证会带回更多原文，切默认前必须书面确认」
> **结论**：评审认定的两项前置 **D1/D2 已于同日落地**（见 §五、§七）——Agent 主路与兜底路径的脱敏口径已统一为同一 hash 函数 + 同一字段面；U1 的「切默认前必须完成」条件已**满足**，剩余为运营侧清单（D3）与逐点明细评估（D4）。
> **状态**：✅ 处置完成（2026-10-21，采纳选项 A）

---

## 一、背景：U1 原文与本次复核动因

U1 原文（`docs/p7-design-agent-diagnosis-2026-10-19.md:135`）：

> 现行 `sanitize_state` 按「兜底路径」设计（仅 confidence∈[0.50,0.75) 触发）；Agent 化后所有工具结果过模型眼前。用户判决：测试期不阻塞 ｜ 上线生产前必须书面重审并显式立项。

本次复核动因：2026-10-21 在 `PUMP-A` 上真机跑 Agent 形态（`scripts/smoke_agent_cloud.py`）确认——**Agent 的每一次工具调用结果都被原样回灌进云端 messages**，且**首条用户消息里的设备编号是明文**。这与兜底路径 `sanitize_state` 的「设备号 hash 后才出网」口径不同源。

---

## 二、事实面：两条出网路径的字段级对比

### 2.1 Agent 主路（`AUSCULT_LLM_BACKEND=cloud` + `AUSCULT_DIAGNOSIS_MODE=agent`）

| 出网内容 | 具体字段 | 是否脱敏 | 证据 |
|---|---|---|---|
| 首条用户消息 | `alarm.device_id`（**明文**，如 `PUMP-A`）、`metric`、`value`、`baseline`、`severity`、`ts` | **否** | `app/graph/nodes/agent_diagnose.py:150-165`（`_build_agent_context`） |
| 系统提示词 | 工具 schema + 拒止规则 + 参数取值约定 | 否（通用文案，无业务数据） | `app/agent/prompt.py:30-85` |
| `query_sensor` 结果 | `device_id`（明文）、`series[].sensor_id/column/ts/value`、`note` | **否** | `app/agent/tool_registry.py:150-192` |
| `search_knowledge` 结果 | `chunk_id`、`score`、**`text`（知识库原文，截断至 `_MAX_TEXT_CHARS`）** | **否** | `app/agent/tool_registry.py:207-227` |
| `query_graph` 结果 | `entities_hit`（实体名：设备/部件）、`hits[].chunk_id/score` | **否** | `app/agent/tool_registry.py:230-254` |
| `get_maintenance_history` 结果 | `device_id`（明文）、`work_orders[].order_id/fault/action/result/created_at` | **否** | `app/agent/tool_registry.py:257-276` |

### 2.2 兜底路径（`escalate_cloud`）

| 出网内容 | 处理 | 证据 |
|---|---|---|
| `alarm.device_id` | → `设备#<sha256[:6]>`（可追溯不可逆） | `app/router/cloud.py:81-84, 102` |
| `work_orders[].device_id` | → 同上 hash | `app/router/cloud.py:114-122` |
| `evidence[].text` | **原文保留**（理由是"知识库通用内容，无 PII"） | `app/router/cloud.py:87-100` |
| `sensor_report` / `graph_paths` | 统计摘要与通用关系描述 | `app/router/cloud.py:124-135` |

### 2.3 差异结论

| 维度 | Agent 主路 | 兜底路径 | 差异性质 |
|---|---|---|---|
| 设备编号 | **明文** | hash | **口径不一致（强标识符）** |
| 工单文本 | `fault/action/result` 全文 | `fault/action` 保留 | Agent 多出 `result`（处置结果，可能含现场描述） |
| 知识库原文 | 全文（截断） | 全文 | 一致（均保留） |
| 时序数值 | 明细序列（逐点） | 统计摘要（count/avg/max/trend） | **Agent 出网粒度更细** |
| 图谱实体名 | 实体名列表 | 通用关系描述（无点位标识） | **Agent 出网更具体** |

---

## 三、风险判定（按「可识别性 × 数据敏感度」）

| # | 项 | 等级 | 判定理由 |
|---|---|---|---|
| R1 | 设备编号明文出网 | **中** | 设备编号是唯一强标识符（结合厂区可定位到台套）；且与兜底路径口径不一致，说明"已认可 hash 的必要性" |
| R2 | 工单 `result` 全文 | **中** | 现场处置描述可能含人（班组/责任人）、工位、工艺参数；未做字段级抽检 |
| R3 | 知识库原文 | **低** | 通用标准/手册内容（如 ISO 10816 判据表），非厂内私有数据；与兜底路径同口径 |
| R4 | 逐点时序明细 | **低** | 数值本身无标识，但在 R1 成立时可与设备号关联 → 依赖 R1 处置 |
| R5 | 图谱实体名 | **低** | 部件/故障类型名（轴承/齿轮），非点位标识 |

---

## 四、处置选项（待所有者裁定）

| 选项 | 内容 | 成本 | 影响 |
|---|---|---|---|
| **A（已采纳）** | Agent 上下文与工具结果**只对设备标识符做 hash**（`device_id` → `设备#<sha256[:6]>`，与兜底路径共用同一函数），其余保留；`work_orders.result` 不出网 | 小（1 处上下文构造 + 1 处工具结果后处理 + 回归锁） | 与兜底路径口径统一；诊断质量基本无损（模型靠关系/现象推理，不依赖设备号字面） |
| B | 完整复用 `sanitize_state` 的脱敏面（含工单 device_id + 序列表述归一） | 中（需在 Agent 侧重建 state→sanitize 的映射，工具结果非 state 结构） | 口径最严，但要改写工具结果回灌链路，回归面大 |
| C | 维持现状，靠**部署形态声明**兜底（客户内网/专有云部署，云端为自建模型服务） | 零 | 仅在"云端即客户专有环境"时成立；对公有云 API（当前 ModelScope）**不成立** |

**推荐 A 的理由**：Agent 与兜底两条路径最终打的是同一个云端端点，超时/预算/审计都已统一口径（`llm_config.cloud_timeout()`），脱敏没有理由分裂；A 的改动面最小且不触碰冻结区。

---

## 五、结论与前置条件

**结论**：U1 的两项硬前置（D1/D2）**已于 2026-10-21 落地**，切默认的合规阻塞解除。

- **D1（已完成）**：Agent 出网内容中的设备标识符统一 hash —— `app/graph/nodes/agent_diagnose.py::_outbound_payload` / `_inbound_arguments` 双向映射，hash 函数复用 `app/router/cloud.py::hash_device_id`（与兜底路径**同一函数**，`_hash_device_id` 的公开别名）；覆盖任意字符串位置（`result.device_id`、`series[].sensor_id`、`entities_hit`）。回归锁 3 例：上下文不含明文 / 回灌副本不含明文且原结果不被就地改 / **端到端 messages 全程不含真实编号 + 工具仍拿真号**。
- **D2（已完成）**：`work_orders.result` 抽检 —— 生产库 `work_orders` 共 **48 条**，`result` **全部为空字符串**、`fault`/`action` 均为受限短语（无设备号/人名/工艺参数）。结论：当前数据面无实证风险；但按最严口径**该字段一律不出网**（`_outbound_payload` 对 `get_maintenance_history` 剥离 `result`），与 `sanitize_state` 只保留 `fault`/`action` 对齐。
- **D3（建议，未做）**：`docs/prj-spec-operations.md` 增加"云端数据面"章节，列明出网字段清单（当前分散在代码与 ADR，运营侧无单一清单）。
- **D4（保留）**：`sensor` 逐点明细是否降级为统计摘要，留待性能/成本评估（`EXP-P7-P1` 的 74/75 不依赖逐点明细）。

**遗留边界**：hash 只覆盖 `device_id` 字面值；若知识库原文/工单文本中**另含**设备名或厂区名（未经 `alarm.device_id` 表达），D1 无法自动掩码 → 该风险由 D3 清单化管理，接入新数据源时须复核。

---

## 六、附：本次复核用到的实证

| 项 | 证据 |
|---|---|
| Agent 首条消息明文设备号 | `app/graph/nodes/agent_diagnose.py:156`（`f"【告警】设备={alarm.device_id or '（未提供）'} ..."`） |
| 工具结果原样入 messages | `app/graph/nodes/agent_diagnose.py:296-309`（`tool_result_message(call.id, call.name, out)`） |
| 兜底路径 hash | `app/router/cloud.py:81-84`（`_hash_device_id` → `设备#<sha256[:6]>`） |
| 真机实测（Agent 出网内容随工具结果增长） | 2026-10-21 `thr-smoke-agent-1792573480`：6 次工具调用（`query_sensor`×3 / `retrieve_knowledge` / `get_maintenance_history` / `query_graph`），审计 `reports/security_audit.jsonl` 全部 `allowed=true` |

---

## 七、D1/D2 落地记录（2026-10-21）

| 项 | 实现 | 证据 |
|---|---|---|
| 双向映射 | `_inbound_arguments`（代号 → 真号，仅进程内）+ `_outbound_payload`（真号 → 代号，deepcopy 后替换，不动内部状态） | `app/graph/nodes/agent_diagnose.py:150-200` |
| 同一 hash 函数 | `cloud.hash_device_id`（`_hash_device_id` 公开别名） | `app/router/cloud.py:81-92` |
| 上下文说明 | 首条消息附「设备标识已脱敏为 `设备#…`，调工具请原样使用，系统执行时还原」 | `agent_diagnose.py:236-241` |
| D2 字段剥离 | `get_maintenance_history` 回灌副本删除 `work_orders[].result` | `agent_diagnose.py:172-176` |
| 回归锁 | 5 例（上下文掩码 / 回灌掩码+剥离+原对象不变 / 端到端不泄露 / 超时重试 / RuntimeError 不重试） | `tests/test_agent_diagnosis.py`（42 例单文件，全量 270） |
| **真机验证（D1 生效）** | `PUMP-A` × `smoke_agent_cloud.py --no-resume`：**PASS**，`evidence_n=10`、confidence 0.78，诊断结论引用了真实录波（"全天最大 4.68 mm/s"、"16:00 前后数据断流窗口"）→ 证明模型只见代号、工具端仍取到真实数据 | 2026-10-21 实跑（预算 18→24） |

---

## 八、定稿口径（2026-10-21 所有者二次裁决：合规以**本地部署方案**为准）

> 裁决要点：目标形态是「本地 qwen3:32b 为主 → 云端降为兜底」；测试开发期用云端 API 维持运行，
> **测试期不追合规**；数据合规与脱敏要求**按本地部署形态定义**，而不是按当前上云形态定义。

### 8.1 出网面的重新划定

| 路径 | 是否出网 | 脱敏要求 |
|---|---|---|
| Agent 主路 + `AUSCULT_LLM_BACKEND=local` | **否**（本机 Ollama） | **不脱敏**：明文设备号，工单 `result` 保留（本地不出网，掩码只损耗诊断质量） |
| Agent 主路 + `AUSCULT_LLM_BACKEND=cloud` | 是（**当前测试开发形态，临时**） | 沿用 D1/D2；可一键 `off` 以复现本地形态 |
| `escalate_cloud` 兜底 | 是（**唯一长期出网点**） | **D1/D2 必须保留**（设备号 hash + 工单 `result` 剥离）；D3/D4 仅对本路径有意义 |

### 8.2 开关与默认

`AUSCULT_SANITIZE_OUTBOUND=auto`（默认）——`cloud` 后端脱敏、`local` 后端不脱敏；
`on` / `off` 为强制档。实现：`app/llm/config.py::sanitize_outbound()` →
`agent_diagnose.agent_diagnose()` 内推导 `device_token`（空串即不掩码，`_outbound_payload` 直接原样返回）。

### 8.3 与 D1 的实质冲突及处置（已修）

D1 的掩码代号会被模型复述进结论 —— 实证：`reports.payload.diagnosis` 出现
`设备#f6de90`（= `hash('PUMP-A')`）。处置三件：

- 本地形态：主路不掩码 → 冲突消失；
- 云端形态：保留掩码，但**报告出口还原**真实编号（`_restore_device`；报告是本地产物，不出网）；
- 回归锁：`test_local_backend_does_not_mask_device_id` / `test_masked_token_restored_in_report`。

### 8.4 重新生效条件（仅当"主路长期走公有云"时）

若后续不换本地硬件、长期以公有云为主通道，则本文件 §三 的 R1–R4 与 D3/D4 **重新生效**，
须补运营侧出网字段清单与 `sensor` 逐点明细评估；**本地形态下不适用**。
