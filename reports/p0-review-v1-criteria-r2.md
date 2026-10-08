# V1 判分/用例口径复审报告（v2）
> **⚠️ 历史留痕（2026-10-08 文档同步加注，正文结论未改）**：本文所载判定为 **2026-09-30** 时点。文件名已按规范改为 `p0-review-v1-criteria-r2.md`（原 `reports/v1-review-v2.md`）。 V1 判据/用例口径复审第 1 份记录（文档版号 v2）。 当前口径见 `README.md` §当前状态速览 与 `docs/p0-spec-gate-criteria.md` §六；裁决依据 `reports/p0-gate-m02-verdict-2026-10-08.md`。

> **P1 项**：判分/用例口径复审——judge_tools 语义匹配、evidence_refs 比 type；用例 5 类型×3 难度复核
> **状态**：🟡（判分器已改）→ ✅（本报告完成复核 + 新用例集冻结，重跑另行记录）
> **日期**：2026-09-30 ｜ **作者**：单人（本人）
> **判据**：`docs/p0-spec-gate-criteria.md` §3.1.1 按类型分档
> **判分实现**：`scripts/judge_tools.py`（已落地 v2 D1/D2/D3/D5）
> **Schema**：`schemas/tools_v2.json`（FROZEN 2026-09-30，consumers 已声明 → EXP-V1-007 重测）

---

## 〇、结论摘要

- **判分器已按 v2 口径修订完毕**（窗口量纲 D1 / 超限聚合别名 D2 / 绝对时间时区等价 D3 / generate_report 收敛 D5），20 例 old 判定在 v2 判分器下**无口径性失败**。
- **原 v1_cases.jsonl 保持字节不变**（历史资产，不追改）。
- **新建 `evals/v2_cases.jsonl`**：20 例（case_id 前缀 v1-→v2-，字段原样）+ 5 例补档，共 **25 例**，5 类型 × 3 难度矩阵**补齐**。
- **判定 diff**：新增用例为全新增，不产生对 20 例判定的回退；20 例因 D1/D2/D3/D5 仅带来"更宽松"的方向，无"原来对、现在错"的回归。
- **未实现项 — D4 多工具拆步**：`match_expected_calls` 仍为"单响应内工具名逐个配对"。故本次新增「多工具·易」用例仍按单响应多工具设计，不依赖拆步。

---

## 一、判分器口径现状（v2）

| 维度 | 实现位置 | 口径 |
|---|---|---|
| **D1 window 量纲等价** | `duration_equivalent`（judge_tools.py ~L264） | `15m`= `15min`= `900s`，不可解析（裸数字）仍判错 |
| **D2 aggregation 别名** | `_aggregation_over_limit_equivalent` + `_aggregation_canonical` | 仅超限类 `count_over_limit/count/over_limit/exceed_count` 等价；非超限聚合保持精确（中性） |
| **D3 绝对时间时区等价** | `parse_iso`（归一 UTC）+ `time_range_equivalent` | `+08:00` 与同刻 `Z`/省时区等价，仅时刻不同才判错 |
| **D5 generate_report 收敛** | `REPORT_VERDICT_KEYS` = {device_id, diagnosis_summary, evidence_refs} | 仅比这三键；severity/format/idempotency_key 不参与正确性 |
| **evidence_refs 比 type** | `_refs_type_ok` | 只比证据 type 覆盖率（sensor/knowledge/graph/maintenance），忽略具体 ref |
| **query 语义匹配** | `_query_semantic_match` | 精确/子串/bigram 交叠≥50% |
| **判据分档** | `judge_verdict_tiered` / `TIER_CRITERIA` | 单工具/参数校验/多轮 ≥85%、无效拒绝 ≥90%、多工具 ≥70%；整体=最差档位 |

**D4 多工具拆步（复审建议 §三.1）当前未在判分器中实现**——属架构切分方案的内容，不在本次"判定口径复审"范围，登记供后续。

---

## 二、20 例逐条判定复核（diff 清单）

> 判定对象：EXP-V1-006 已跑旧基准（20 例 tools_v1）在 v2 判分器下的差异。**方向均为放宽，无回归。**
> diff 符号：`= ` 判定不变 ｜ `▸` 口径放宽（原错/现吃宽容)

| case_id(v1) | case_id(v2) | 类型/难度 | 复核结论 | diff |
|---|---|---|---|---|
| v1-001 | v2-001 | 单工具/易 | window 显式 1h 已加 `lenient_param_defaults`（5m），且 v2 量纲归一 | ▸ 放宽 |
| v1-002 | v2-002 | 单工具/易 | category_filter 枚举合理 | = |
| v1-003 | v2-003 | 单工具/易 | fault_keywords ≤5 缺省可接受 | = |
| v1-004 | v2-004 | 单工具/中 | relation_types 枚举 + direction 双值 | = |
| v1-005 | v2-005 | 单工具/中 | sensor_id de/nde + aggregation=max | = |
| v1-006 | v2-006 | 单工具/中 | 设备编号误导（应走知识库） | = |
| v1-007 | v2-007 | 多工具/中 | 双工具串联，缺任一覆盖不全 | = |
| v1-008 | v2-008 | 多工具/难 | 跨源（时序+工单）参数互污染 | = |
| v1-009 | v2-009 | 多工具/难 | depth=2 + direction=outgoing | = |
| v1-010 | v2-010 | 多工具/难 | sensor_ids 双测点（拆两次不判错） | = |
| v1-011 | v2-011 | 参数校验/中 | window 变体（15min/900s）→ D1 量纲等价 | ▸ 放宽 |
| v1-012 | v2-012 | 参数校验/中 | count_over_limit 别名 → D2 | ▸ 放宽 |
| v1-013 | v2-013 | 参数校验/难 | ISO8601 +08:00 → D3 时区等价 | ▸ 放宽 |
| v1-014 | v2-014 | 参数校验/难 | category_filter 枚举，query 语义已放宽 | = |
| v1-015 | v2-015 | 无效拒绝/中 | 删除工单=写操作超界，保持高线 | = |
| v1-016 | v2-016 | 无效拒绝/中 | 缺 device_id 应澄清（幻觉型） | = |
| v1-017 | v2-017 | 无效拒绝/难 | 寿命预测超职责 | = |
| v1-018 | v2-018 | 多轮/中 | 上下文补全（device_id 跨轮） | = |
| v1-019 | v2-019 | 多轮/难 | generate_report → D5 收敛为 3 键比对 | ▸ 放宽 |
| v1-020 | v2-020 | 多轮/难 | 行为切换（上轮澄清→本轮调用） | = |

**小计**：`=` 直接保留 14 例 ｜ `▸` 口径放宽 6 例（v1-001/011/012/013/019，全部仅更宽松）。
**难度标注核对**：20 例 difficulty 标注与其考察点吻合，无错配。

---

## 三、新增 5 例（补档，5×3 矩阵补齐）

| case_id(v2) | 类型/难度 | 补齐目标 | 复考查点 |
|---|---|---|---|
| v2-021 | 单工具/难 | 单工具缺「难」 | 绝对时间含时区 + 驱动端测点映射 + trend + 1d 窗口（多考点） |
| v2-022 | 参数校验/易 | 参数校验缺「易」 | 单考点：aggregation=avg 恰选，缺省参数可容忍 |
| v2-023 | 多工具/易 | 多工具缺「易」 | 两步直白（query_sensor + search_knowledge），单响应多工具 |
| v2-024 | 多轮/易 | 多轮缺「易」 | 跨轮补全 device_id + 本轮时间/聚合 |
| v2-025 | 无效拒绝/易 | 无效拒绝缺「易」 | 数据导出超服务边界，应拒绝 |

完整用例见 `evals/v2_cases.jsonl`。矩阵现状：

| 类型 | 易 | 中 | 难 |
|---|---|---|---|
| 单工具 | ✓ | ✓ | ✓ |
| 参数校验 | ✓ | ✓ | ✓ |
| 多工具 | ✓ | ✓ | ✓ |
| 多轮 | ✓ | ✓ | ✓ |
| 无效拒绝 | ✓ | ✓ | ✓ |

---

## 四、落盘与校验

- 生成脚本：一次性 `scripts/build_v2_cases.py`（已用后删除，不保留）。
- 落盘前校验：每个 expected_tool_calls 经 `judge_tools.validate`（tools_v2）+ generate_report 3 键核对，全部通过；类型×难度矩阵断言 5×3 齐全。
- `v1_cases.jsonl` 未改动（字节不变）。

---

## 五、重跑（新基准）

- 实验 ID：**EXP-V1-007**（EXP-V1-006 已占用，且其 schema_version=tools_v1+CASES=v1，不沿用）。
- 配置：cases=v2_cases.jsonl（25 例）、schema=tools_v2.json、prompt=tool_call_prompt_v2.md、constrain=约束解码、repeat=3、seed=42、temp=0。
- 计划 150 组（2 模型 × 25 × 3），原始落盘 `experiments/v1/raw/EXP-V1-007.jsonl`。
- 判据按 §3.1.1 类型分档，整体=最差档位。

> **结果判定**：重跑原始数据与分档判定详见配套实验记录，不在本报告内重复（避免单一事实源分裂）。本报告为"口径复审"结论。

---

## 六、口径缺陷更正：few-shot 恒取 v1（2026-09-30）

> **登记**：`docs/prj-ledger-known-issues.md` **ISS-024**（🟠 高 / 已修复）。

| 项 | 说明 |
|---|---|
| 缺陷 | `scripts/llm_adapter.py` 的 `build_messages` 调 `load_fewshot()` 时未传路径，落回模块级默认 `PROMPT_PATH = tool_call_prompt_v1.md`。因此 `--prompt prompts/tool_call_prompt_v2.md` 时，**system 取了 v2、few-shot 仍是 v1 的 3 条** |
| 影响 | 本报告 §一 所称"few-shot 3→8 扩容"这一复审变量**实际从未生效**；EXP-V1-004 / 006 / 007 的"提示词增强"实为**只改 system**。各实验结论方向（均为 No-Go）不变 |
| 修复 | `build_messages` 新增 `prompt_path` 参数（system 与 few-shot 同源）；`run_group` / `run_step_chain_group` / dry-run 三处显式传路径；`--selftest` 增防回归自检（v2 装配条数必须多于 v1） |
| 新口径 | 修复后重跑 **EXP-V1-009**（拆步，P6）/ **EXP-V1-010**（模拟单响应多工具，对照）为"提示词变量干净"的新基准；历史 raw **不追改**，仅在实验记录中标注口径 |

---

## 修订记录

| 日期 | 修订人 | 变更 |
|---|---|---|
| 2026-09-30 | 单人（本人） | 初始建立：复核 20 例 old 判定（v2 判分器无回归、6 例放宽）、冻结 v2_cases.jsonl（25 例）、5×3 矩阵补齐、登记 D4 未实现、启动 EXP-V1-007 |
| 2026-09-30 | 单人（本人） | 新增 §六：登记 few-shot 恒取 v1 的口径缺陷更正（ISS-024）——§一 所称"few-shot 3→8 扩容"实际未生效，EXP-V1-009/010 为重跑新基准 |
| 2026-10-08 | 单人（本人） | 文档同步整理：加「历史留痕」横幅（正文结论一字未改）；文件重命名 → `p0-review-v1-criteria-r2.md` | 头部 / 索引 |
