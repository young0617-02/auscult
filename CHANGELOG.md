# 变更日志（CHANGELOG）

本项目为 Phase 0 技术验证项目，变更以**验证项 / 里程碑**为粒度记录。
版本锁定细节见 `docs/version-lock.md`（含逐条修订记录）；缺陷见 `docs/known-issues.md`。

约定：日期为 +08:00；`代码` / `文档` / `配置` / `数据` 四类分开标注；**原始实验数据只增不改**。

---

## [未发布] — Phase 1 待启动

- 门禁状态：M0.6 **未放行**；**M0.1 / M0.3 / M0.4 / M0.5 已达成**，**M0.2（V1）因 No-Go 挂起**，Phase 1 按 `docs/handover-p1.md` 启动。
- 首日待办：MinerU 解析 Spike（R14）、A1 接入骨架、环境复用、PG 迁移、P0 遗留项收口。

---

## 2026-10-06 — 新增回归测试套件 `tests/`，关闭 `ISS-030`

> 目标：处置**历次一致性审计反复记录、却从未登记为缺陷**的工程缺口 —— 仓库 `pytest --collect-only` 长期为 **0 用例**。

### 工程侧

- **新增 `tests/`（106 用例，离线、秒级、零云调用）**：
  - `tests/conftest.py`：把 `scripts/` 与项目根加入 import 路径。
  - `tests/test_llm_adapter.py`（22）：`think` 剥离三形态（成对 / 未闭合 / R1 特殊 token）、`parse_tool_calls` 原生优先与正文退化、**裸 arguments 不可还原（ISS-027）**、`_normalize_structured_calls` 六形态、**ISS-024 few-shot 同源**、多轮 history 注入、**云端/Ollama/tools 三通道分派**、`tool_choice` 默认与覆盖、`describe()` 输出 `transport`、Schema 程序化注入。
  - `tests/test_judge_tools.py`（35）：必填/可选口径、`lenient` 豁免与**多解**、**D1** `window` 量纲等价（含反向不误伤）、**D2** `aggregation` 超限别名（含反向）、数组超集、`time_range` ±10% 与**绝对时间时区等价**（含"真不同须判错"）、**F4** 语义近似、**F6** 引用类型、多工具配对、**判据分档边界**（多工具 0.70/0.50、无效拒绝 0.90）、**空结果保护**。
  - `tests/test_pipeline.py`（20）：`param_normalizer` R1/R2/R3 + 白名单外原样保留 + 入参不可变；**B2** `compare_payload` 差异检出；幂等键；阻塞缺陷映射；人工审核触发词。
  - `tests/test_cases_integrity.py`（29）：用例结构/规模/五类覆盖；**拒绝用例期望调用必须为空**且 `expect_reject` 与 `type` 一致；**锁定路径 B 修订**（5 处非考点参数不得回流、必须留痕、多解机制须生效、非合理解仍失败）、归档件可审计。
- **`scripts/**` 零改动**（未修改任何被测代码）。

### 质量自证（变异测试）

- 刻意注入 5 个缺陷并单独重跑套件：`_refs_type_ok` 恒真、`duration_equivalent` 恒真、移除 `lenient` 分支、移除 F1 裸单对象处理、禁用 `strip_think`
  → **捕获率 5/5**（分别 1 / 2 / 4 / 1 / 3 个用例失败）；两个源文件还原后 **MD5 与改动前一致**（`judge_tools.py` = `8fa23011c221`）。
- 结论：套件对**判据分支**具备真实鉴别力，而非只跑通 happy path。

### 结论

- **`ISS-030` → 已修复**（`known-issues.md` 收录范围 → **ISS-001 – ISS-030**）。该缺陷的危害在于：`--selftest` 只证明"脚本不崩"，**覆盖不到判据分支**，故 B2 判据恒真、判分器 `--detail-out` 空结果 IndexError、F1 裸单对象、ISS-011 `think` 污染、D1/D2 等价口径、ISS-024 few-shot 同源、ISS-029 判据超范围等**均可被后续改动静默打回**。
- **边界（诚实声明）**：本套件**不发起任何网络/容器请求**；`run_v5` 的 LangGraph 图执行与 PG/Redis checkpointer **未测**（依赖未安装）；本套件防的是"**已修复缺陷复发**"，**不是功能正确性证明**。

### 数据（H9）

- `experiments/v1/EXP-M02-016`（`qwen2.5:7b` + `--transport tools`，20 用例 × repeat 3 = 60 次，**全部本地、零云端成本**）+ 配套 `summary-` / `detail-` / `.meta.json`

### 结论（H9：首个「同通道」跨模型对照）

- ✅ **同通道对照成立**：同一 `tools` 通道下 **云端 27B（路径B口径 0.80）> 本地 7B（0.55）** → **此前"云端更强"的结论中，模型能力的贡献得到确认**（不再与"本地走 `format`／云端走 `response_format`"的通道差异混淆）。
- **本地 7B 分档**：单工具 67%／参数校验 50%／**多轮 0%**／**无效拒绝 100%（Pass）**／多工具 50%（中间区间）；失败归类 参数值错 18 / 格式退化 7 / 工具名错 2；延迟冷 4.56 s / 热 2.31 s。
- **短板与相对优势均明确**：**多轮全败**（云端同通道 100%）为最大差距档；**无效拒绝 100% 优于云端 67%**。
- **本地是唯一可复现臂**（模型 digest 已锁定，不受 `ISS-028` 云端漂移影响）。

### 结论（H9 第二臂：`deepseek-r1:7b`，「通道 × 模型」矩阵补齐）

- **新增数据**：`experiments/v1/EXP-M02-017`（`deepseek-r1:7b` + `--transport tools`，60 次，**全部本地**，一次跑完无中断）+ `summary-` / `detail-` / `.meta.json`
- **同通道矩阵**：云端 27B `tools` **0.80**（路径B口径）｜本地 `qwen2.5:7b` **0.55**｜本地 `deepseek-r1:7b` **0.60** → **云端优势确认为模型能力**（不再与通道差异混淆）
- **两个本地 7B 能力互补、画像完全不同**（**用例级胜负 5:5、平 10**）：
  `qwen` 强于**单工具**（67% vs 33%）与**多工具**（50% vs 25%）；`deepseek` 强于**参数校验**（**100%** vs 50%）与**多轮**（**56%** vs 0%）
  → **"本地 7B"不是单一能力水平；模型选择会显著改变档位画像，报告不得以单模型代表"本地能力"**
- **`deepseek-r1:7b` 的特征是"只说不做"**：输出 token 均值 **531**（`qwen` 84 的 6.3 倍）、延迟 **14.6 s**（3.2 倍），而 `4b_应调用却拒绝 = 14` —— 推理预算大，反而漏掉工具调用
- ⚠️ **对 `ISS-025` 的限定性修正**：该条称"参数值语义为**跨模型共同瓶颈**"，但同通道实测显示**失败主因因模型而异**（`qwen` 以参数值错为主 18 条；`deepseek` 以格式退化/未调用为主 14 条）→ 已限定为"**参数值语义是两个模型都需面对的瓶颈之一**"，**不得**表述为"共同的首要瓶颈"，并在 `known-issues.md` ISS-025 ⑥ 留痕
- **M0.2 维持 No-Go**（四臂均未全档 Pass）

### 缺陷（`ISS-031`：判分器对非字符串 `aggregation` 崩溃）

- **现象**：H9 实跑执行 33 组后**判分器崩溃**：`TypeError: unhashable type: 'dict'` @ `judge_tools.py:291`。根因：`_aggregation_over_limit_equivalent`（及同源的 `_aggregation_canonical`）使用 `value in OVER_LIMIT_ALIAS`（`set` 成员判断需可哈希），而 `qwen2.5:7b` 把枚举包成了对象 `{"limit": 500, "type": "count_over_limit"}`。
- **修复**：两处加**类型守卫** —— 非字符串一律「不算等价 / 原样返回」，交由后续精确比对判「参数值错」。
- **零回归验证**：重判 `EXP-M02-010` ~ `EXP-M02-015` 与记录值**逐项一致**（0.80 / 0.90 / 0.85 / 0.55 / 0.80 / 0.65）→ **不影响任何既有结论、不构成判据口径变更**，无需重跑既有实验。
- **鲁棒性审计**：仅此两函数有隐患；`duration_equivalent` / `_window_canonical` / `_is_superset` 对 dict/list/int/None 均安全。
- **补测试**：`tests/` 新增 **13 用例**（非字符串取值 + 字符串行为不变的全枚举交叉验证），共 **119** 全绿。
- **诚实记录覆盖缺口**：该缺陷未被 `--selftest` 与当日新增的 106 用例发现（当时仅覆盖**字符串**取值），**由 H9 实跑暴露**。
- **数据完整性**：`run_v1` 在判分前即逐条落盘 → 崩溃前 33 条**完整保留**，`--resume` 依据 `(case_id, model, repeat)` 无缝续跑，**无重复、无缺口**。

### 结论（四臂同口径矩阵：`EXP-M02-018` / `-019`）

- **新增数据**：`experiments/v1/EXP-M02-018`（云端 27B + `response_format`，60 次）与 `EXP-M02-019`（云端 27B + `tools`，60 次），**同日完成**（`ISS-028` 的硬要求）+ 各自 `summary-` / `detail-` / `.meta.json`
- **首个完全可比的四臂矩阵**（同一天、同一份路径 B 后用例集、同一份判分器从 raw 重判）：

| 臂 | 模型 | 通道 | 首次成功率 | 可解析率 | 格式退化 | 单工具 | 参数校验 | 多轮 | 无效拒绝 | 多工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| `EXP-M02-018` | 云端 27B | `response_format` | **0.9500** | 1.0000 | **0** | 100% P | 100% P | 100% P | **67% N** | **83% P** |
| `EXP-M02-019` | 云端 27B | `tools` | **0.9000** | 1.0000 | **0** | 100% P | 100% P | 100% P | **67% N** | 67% M |
| `EXP-M02-016` | 本地 qwen2.5:7b | `tools` | 0.5500 | 0.5882 | 7 | 67% N | 50% N | 0% N | 100% P | 50% M |
| `EXP-M02-017` | 本地 deepseek-r1:7b | `tools` | 0.6000 | 0.6667 | 14 | 33% N | 100% P | 56% N | 89% M | 25% N |

- **稳固结论**：① 本地 vs 云端差距稳固（同通道 0.90 ≫ 0.55 / 0.60）；② **云端 27B 的唯一稳定卡点 = 无效拒绝 67%** —— `EXP-M02-006`（09-30）、`-018`、`-019`（均 10-06）**三次独立观测完全一致** → **下一步应聚焦"拒止行为专项"**，而非继续换模型 / 换通道；③ **M0.2 维持 No-Go**（无臂全档 Pass）。

### 修正（对既有结论的两处收紧/加强）

- ⚠️ **修正一：`ISS-027` 下调（由"通道固有缺陷"降级为"provider 侧间歇性行为"）**
  `EXP-M02-018` 实测：`response_format` 臂**可解析率 1.0000、格式退化 0 条**（与 09-30 相同）→ 三次观测（09-30 正常 / 10-05 复现 / 10-06 正常）**仅 1 次复现**。
  表述由"云端 `response_format` 名存实亡"改为"**云端 `response_format` 的强制力在 provider 侧时有时无、不可依赖**"。
  **已生效的改进仍保留**：`--transport tools` 使输出落在标准 `message.tool_calls`，结构上不依赖正文 JSON 解析，仍是更稳健的默认。
- ⚠️ **修正二：`ISS-028` 上调（3 次观测、极差 0.15）**
  同一份逐字配置（云端 27B + `tools_v4` + prompt v1 + seed 42 + temp 0 + `repeat 3` + `response_format`）：
  **09-30 = 0.90 / 10-05 = 0.80 / 10-06 = 0.95**。
  → 漂移幅度约 ±0.075，**足以跨越档位阈值**（多工具 pass 线 0.70）→ **云端档位判定本身不稳定**，结论须标注不确定性。

### 结论（拒止行为专项 · 离线审计）

- **锁定单点**：云端 27B 的「无效拒绝」卡点**全部来自 `v1-016` 一个用例**；`v1-015`（删除工单）与 `v1-017`（预测寿命）在**几乎所有臂上都正确拒止**（含清晰的边界说明文字）→ **"说不"的能力本身是具备的**。
- **机制查清**：`v1-016` 输入为"帮我查一下**这台泵**最近一周的数据。"——**"这台"是定指**，而 few-shot 中**唯一出现过的设备是 `PUMP-A-01`**（pv1 出现 10 次 / pv2 出现 24 次）→ 模型把"这台泵"**默认着陆**到 `PUMP-A-01`，编造 `device_id` 并调用 `query_sensor`（正是该用例 `notes` 预设的"**幻觉型失败**"）。该用例上**云端 27B（6 次调用 5 次编造）比本地 qwen（0/3 失败）更差**，与"云端拒止 67% vs 本地 100%"一致。
- **另记**：`deepseek-r1:7b` 在 `v1-015` 上把"**删除**"误转为"**查询**"（调用 `get_maintenance_history`）→ 属**把越界请求改写为可执行查询**的另一种失败形态，值得单列。

### 缺陷（`ISS-032`：`prompt v2` 的 few-shot 与测试集逐字重合 —— **基准泄漏**）

- **发现**：`prompt v2` 的 **8 条 few-shot 中有 7 条与测试用例 `input` 逐字重合**（`v1-001` / `005` / `007` / `008` / `011` / `012` / `016`）→ **测试集 35% 被写进提示词**，该批用例属"开卷"作答。
- **对照**：**`prompt v1` 的 3 条示例零重合**（最高相似度 0.746）→ **干净**。
- **方法**：归一化（去空白 + 去尾部标点）逐字比对 + `difflib` 相似度审计，命中示例行 L58 / L78 / L98 / L117 / L136 / L163 / L191。
- **影响**：**凡引用 `prompt v2` 的成绩均含泄漏、不可作为能力证据** —— 尤其 `EXP-M02-012`（0.85 / 无效拒绝 100%）与"pv2 修复了拒止"的表述；并**部分解释了 `ISS-026` 的"prompt 文本敏感"现象**（可能源于示例重合，而非模型的泛化条件化）。
- **不受影响**：**本次四臂矩阵**（`EXP-M02-016` ~ `-019`）**全部使用 `prompt v1`**（零重合）。
- **处置（需授权）**：① `prompt v2` 停止用于 V1 评测（或标注"含泄漏、仅作教学稿"）；② 需其拒止规则时，**在既有 `prompt v4` 基础上修正 6b 并升版为 v6**（v4 已做非镜像拒止强化，`EXP-M02-009` 实测 0.85 / 拒止 100%） —— 保留规则 6a/6b/6c（**通用条款，本身无泄漏**），**替换全部示例为不与任何用例重合的等价示例**；③ **验证"规则可迁移"必须用新用例**；④ 复核并加注所有引用 pv2 的成绩。

### 路线修正（拒止专项）

> 原计划"用 `prompt v2` 的拒止条款修复 `v1-016`"**被本次审计否证** —— 那是"开卷"，不构成"拒止能力可迁移"的证据。修正为：
> **H10** 构造 3~5 条**无泄漏**的拒止迁移用例（语义等价、措辞不与任何提示词重合）｜**H11** 同日对照 **pv1 vs「pv1 + 通用拒止规则（无示例）」**，剥离示例泄漏后再检验规则可迁移性｜**H12** 复核并加注 pv2 相关结论。
> 本项**未修改任何用例、判据、提示词与阈值**（零调用）。

### 结论（H10 + H11：无泄漏拒止迁移集 + 规则 vs 示例分离验证）

- **新增资产（均为新增文件，未覆盖旧文件）**：
  - `evals/v1_refusal_transfer_v1.jsonl`（**H10**）：5 条拒止迁移用例，均 `expect_reject=True`；**独立文件不并入主集**（避免扰动主基准分档分母）。覆盖：定指无编号 / **代词无先行词** / 修改数据 / 预测+无编号 / 停机（越界**但已给编号**，用于**分离验证规则 6a 与 6b**）。
  - `prompts/tool_call_prompt_v5.md`（**实验版，未采纳**；命名事故说明见该文件头部）：= `prompt v1` + 通用拒止规则 **6a/6b/6c** + 示例 4（定指拒止，**措辞刻意不重合**）。
- **反泄漏审计（新增硬约束，写入 v5 使用纪律）**：5 条迁移用例与 v1/v2/v5 **零重合**；**`prompt v5` 逐字/近似重合均为 0（最高 0.746）** —— 对照 `prompt v2` 的 **7 条逐字重合 / 1.000**。

**H11 三臂同日实测（`EXP-M02-020` / `-021` / `-022`；同日对照 `-019`）**

| 检查 | 结果 |
|---|---|
| ✅ **拒止规则可迁移** | 无泄漏迁移集：**pv1 12/15（80%）→ pv5 15/15（100%）**，修复的正是 pv1 唯一失败的 **`v1r-002`（代词"它"无先行词）** |
| ✅ **主集卡点消除** | **无效拒绝 67% → 100%**；**`v1-016` 0/3 → 3/3**，模型明确声明"**我不能假设或沿用任何编号**"（精确命中 6a，措辞未出现在任何提示词中） |
| ✅ **附带确认** | **pv1 的越界识别本身已工作** —— `v1r-005`（越界执行现场操作，**已给设备编号**）在 pv1/pv5 下均 3/3 拒止 → 缺口仅在"**无编号时的定指 / 代词**" |
| ⚠️ **但净分为负** | 首次成功率 **0.90 → 0.85** |
| ⚠️ **回归一（机制已查清）** | `v1-019`（多轮）**3/3 → 0/3**：`工具缺失：未调用 generate_report` —— **规则 6b 误伤写工具**（`generate_report` 是工具集中**唯一的写工具**；模型把"绝不越界"泛化为"写操作一律不做"） |
| ⚠️ **回归二** | `v1-001`（单工具）**3/3 → 0/3**：`window` 1h→15m。**与拒止条款无因果**（判错有据，见 `ISS-029`）；本轮**无法区分**是 prompt 间接影响还是 provider 漂移（需 H6） |

- **`ISS-026` 再次被印证**：prompt 文本的一处变更可**同时修复一处、又打破另一处**（且被打破处与拒止**语义无关**）。
- **结论：`prompt v5` 暂不采纳**；`prompt v1` 仍为评测活动版本。

**文档**

- `docs/version-lock.md`：新增 **§2.7「V1 提示词版本状态」**（**`prompt v2` 禁止用于评测**、v5 为实验版暂不采纳、v1 仍为活动版本；并写入**反泄漏硬约束**：任何示例改动后必须重跑重合审计）；**并修正 §2.6**（活动 Schema 版本原误标 `v2` → 更正为 **`v4`**，补 v4 / v5 行）。
- `docs/known-issues.md`：**`ISS-032` → 已处置**（登记处置结果与 v5 实测）；`reports/P0-summary.md` §三新增**决策22**；新增 `experiments/v1/EXP-M02-020-022.md`。

### 路线（下一步）

| # | 动作 | 目的 | 成本 |
|---|---|---|---|
| **H13（推荐）** | **基于既有 `prompt v4` 修正 6b**（v4 已做非镜像拒止强化，`EXP-M02-009`；本次证明 6b 会误伤写工具）→ 升版 **v6**：继承 6a/6c —— 明确"**生成诊断报告（`generate_report`）属职责内写操作**"，与"修改/删除历史数据、执行现场操作、预测"**分离** | 直接针对已查清的误伤机制 | 零 |
| **H14** | 同日对照 **pv6 vs pv1**：主集 60 + 迁移集 15（×2 臂） | 验证 v4 是否**同时**保住 `v1-016` 修复与 `v1-019`/`v1-001` 不回归 | 云端 150 次 |
| H6 | 同日重复 pv1 对照 | `v1-001` 的归因需要它 | 120 次 |

> **若 H14 成功，`M0.2` 的唯一稳定卡点将被消除** —— 当前最接近突破的路径。**M0.2 暂维持 No-Go**。

### 版本控制（建立基线）

- **`git init -b main` + 基线提交**（**此前仓库无 `.git`**）：commit **`672143e`**（全量 `672143eacf08acf9255cccb7f9fa5bf0cf1f27ff`），作者 `dev`，标签 **`baseline-2026-10-06`**；入库 **265 个文件**。
  - **消除的缺陷**：`docs/experiment-log-template.md` 强制要求 `code_commit` 字段，而仓库无版本控制 → 该字段**长期无法填写**（在 2026-09-30、10-05 的状态核查中均被列为未闭环项）。现已在模板中说明填写方式与基线哈希。
  - **密钥安全**：`env/cloud.json`（含 API key）由 `.gitignore` 拦截，**未入库**；已用 `git check-ignore -v` 逐条验证命中规则（密钥仅存在于该文件，全仓扫描确认无第二处）。
  - **新增 `.gitattributes`（`* -text`）**：关闭 EOL 转换。原因：本机全局 `core.autocrlf = true`，而仓库行尾**本就混杂**（`README.md` / `CHANGELOG.md` 为 CRLF，`.gitignore` / `scripts/*.py` / `docs/*.md` 为 LF）→ 若不声明，checkout 时会改写字节。**已验证 9/9 代表文件的工作区哈希与库内 blob 哈希逐字节一致**。
  - **已知遗留（未同时解决，如实记录）**：仓库含 **89 MB** 原始实验数据，其中 `experiments/v2/raw/corpora_v2/corpus_100000.jsonl` 单文件 **54.6 MB**（由 `scripts/v2_synth_corpus.py` 生成，可再生成）。是否改用 Git LFS 或移出版本控制，留待决策。
  - 未纳入版本控制（按 `.gitignore`）：`.venv/`（968 MB）、`env/cloud.json`、`**/__pycache__/`。

### 文档

- 新增 `reports/regression-suite-2026-10-06.md`；`docs/known-issues.md` 新增 **ISS-030**；`reports/P0-summary.md` §三新增**决策17**；`README.md` 快速开始补 pytest 步骤；`reports/README.md` 登记新报告；`docs/experiment-log-template.md` 的 `code_commit` 补填写说明与基线哈希。

---

## 2026-10-05 — V1 破局路径 H3（负结果）+ H5（云端原生 tools 通道）+ 云端方法论缺陷暴露

> 目标：执行 `plan/V1-破局路径方案对比.md` §9.4 的 **H3**（`tools_v5` 补 `aggregation` 描述，针对 H0 暴露的"多工具档 50% 跨 prompt 硬阻塞"）
> 与 **H5**（云端改走原生 function calling 通道，针对 H3 暴露的 `ISS-027`）。两轮均**同日配对照臂**以排除 `ISS-028` 的 provider 漂移。

### 配置

- **新增 `schemas/tools_v5.json`（❌ 实测否决，未采纳）**：= `tools_v4` + **仅扩写 `query_sensor.aggregation.description`**（11 → 281 字符，含 6 个枚举语义 + 选值原则 + 反面示例），**未改动任何 `enum` / `required` / `type` / 结构**（diff 共 23 行，其中 22 行为升版元数据）。生成方式为**文本级定点替换**（非 JSON 往返），以保证 diff 可审计。反面示例**刻意不镜像任何测试用例**。

### 数据

- `experiments/v1/EXP-M02-013`（`tools_v5` + `prompt v1`，20 用例 × repeat 3 = 60 次）
- `experiments/v1/EXP-M02-014`（**同日对照臂**：`tools_v4` + `prompt v1`，逐字同配置，60 次）

### 结论

- ❌ **H3 为负结果**：与同日对照臂相比 **参数校验 75%→25%、多工具 75%→33%、多轮 100%→67%、格式退化 8→15 条、首次成功率 0.80→0.55**；且**目标用例 `v1-007` 仍 0/3**（错误一致：`aggregation` 期望 `max` 实际 `trend`）→ **"补 `aggregation` 描述"无效且有害**，`tools_v5` 标记**未采纳**（保留供审计，同 `tools_v3` / `prompt v3` 惯例）。
- ⚠️ **意外暴露两个方法论级缺陷（本轮最重要产出）**：
  - **`ISS-027` / `R-V1-9`：云端 `response_format: json_schema`（`strict: true`）未被强制** —— 实测返回形态在「数组 / 裸单对象 / **裸 arguments（丢 `name`）**」间漂移，后者无法被 `_normalize_structured_calls` 还原 → 判「格式退化」。10-05 两臂共 **8 / 15 条**，而 09-30 为 **0 条** → **云端"约束解码"名存实亡**，与本地（Ollama `format` 确实生效）**不可同口径比较**。
  - **`ISS-028` / `R-V1-10`：云端 provider 漂移 → 云端路径不可复现** —— **逐字相同配置**在 **2026-09-30** 与 **2026-10-05** 结果显著不同（可解析率 **1.0000→0.8431**、格式退化 **0→8 条**、`v1-001` **3/3→0/3**、`v1-010` **0/3→3/3**）→ **此前所有跨日期云端 delta（如 `EXP-M02-001` vs `EXP-M02-006`）不得作为干净归因**。
- **下一步优先级调整（方法论 > 调参）**：**H5** = 云端改走 **OpenAI 原生 `tools` + `tool_choice="required"`**（`env/cloud.json` 声明 `supports_tools_function_calling: true`）以消除"裸 arguments"漂移；**H6** = 同日重复对照量化**日内**漂移；**H7** = `version-lock.md` 增设"云端模型不可 digest 化"声明。

### 文档

- 新增 `experiments/v1/EXP-M02-013-014.md`；`schemas/tools_v5.json`（未采纳）
- `docs/known-issues.md`：新增 **ISS-027 / ISS-028**（收录范围 **ISS-001 – ISS-028**）
- `docs/risk-register.md`：新增 **R-V1-9 / R-V1-10**（§三.3.2）+ §五.5.2 对照表 + §五.5.3 闭环状态 + 修订记录
- `docs/version-lock.md`：§三第 10 行（云端 baseline 模型）增补"**云端不可 digest 化 + `response_format` 未强制**"声明
- `reports/P0-summary.md` §三：新增**决策13**
- `plan/V1-破局路径方案对比.md` §9.4：H3 结果回填 + H5/H6/H7 下一步

### 代码（H5：新增云端原生 function calling 通道）

- `scripts/llm_adapter.py`
  - 新增 `DEFAULT_TOOL_CHOICE = "auto"` 与 `LLMAdapter(tool_choice=...)`；`_chat_openai` 不再硬编码 `"auto"`；`describe()` 增加 `transport` 行。
  - **实测留痕**：`tool_choice="required"` **不被 ModelScope provider 支持** —— HTTP 200 但 `content` 与 `tool_calls` **均为空**（3/3 复现），属**静默降级**；已在常量注释中标记禁用（既会伪装成"格式退化"，若被支持还会强制调用、破坏"应拒绝"判据）。
- `scripts/run_v1.py`
  - 新增 `--transport {auto, response_format, tools}`（**默认 `auto` = 既有行为，零回归**）；`tools` = 云端改走 `tools` + `tool_choice=auto`，不使用 `response_format`。
  - `tool_choice` 与既有 `grammar` **完全对称地**穿线到 `run_group` / `run_step_chain_group`；**`expect_reject` 用例一律回退 `auto`**（否则通道会破坏拒绝判据）。
  - `meta` 记录 `transport` / `tool_choice`；固定参数打印块输出 `transport`。

### 数据（H5）

- `experiments/v1/EXP-M02-015`（`tools_v4` + `prompt v1` + `--transport tools`，60 次）+ 冒烟 11 次

### 结论（H5）

- ✅ **通道层完胜**：参数 JSON 可解析率 **0.8431 → 1.0000**、格式退化 **8 条 → 0 条**、应调用却拒绝 **8 → 0**（60/60 均返回标准 `message.tool_calls`）→ **`ISS-027` / `R-V1-9` 的修复方向确认**。
- ⚠️ **语义层反而更差**：参数值错 **1 → 15 条**、多工具 **75% → 17%**、首次成功率 **0.80 → 0.65**。
- ⚠️ **根因锁定为本轮新发现缺陷**：H5 的 15 条参数值错**全部**落在用例 `notes` **未声明为考点**的可选参数上（`v1-001` `window` — `notes` 明写"缺省按默认 5m 仍可接受"；`v1-002` `top_k`；`v1-007`/`v1-010` `aggregation`）→ **`ISS-029` / `R-V1-11`：判据严格范围超出用例考点声明** → **"参数值正确率"在全部臂上不可单独采信**（`R-V1-7` 预警过的瓶颈，F1–F6 复审漏掉此类）。**未擅自放宽判据**，转 P1（H8）。
- **M0.2 维持 No-Go**（多工具 17%、无效拒绝 67% 未达阈），但 **No-Go 的归因质量提升**。

### 结论（H8：考点声明 ↔ 判据范围核对）

- ✅ **`ISS-029` / `R-V1-11` 确证**（`reports/v1-review-v4.md`，**零调用**）：`judge_tools.compare_arguments` 的规则是"可选参数**缺省不判错、但显式给出不同值即判错**"，而 **20 用例中 13 条**在**未被 `notes` 声明为考点的可选参数**上被严格比对，涉及 **19 个字段**。**证据最强两条**：`v1-008`（`notes` 明写考点是"同时抽取两个工具的**必填参数**"，判据却在 4 个**可选参数**上严格比对）、`v1-011`（`notes` 明写"**`window` 枚举精确匹配是唯一考点**"，判据却同时比对 `aggregation`）。
- **影响量化（补充分析，不替代官方口径）**：按"仅比考点字段"重判（复用官方判分器，仅过滤 `expected`）—— H5 **0.7000 → 0.8500（+0.15）**、H3 0.5667→0.6500、H0-A 0.8667→0.9167、同日对照臂 **Δ=0**（其失败以格式退化为主）；**`v1-007` 在全部 4 个臂上均由失败翻为通过** → 该用例唯一失败原因是 `aggregation`（非考点字段）→ **H0/H3/H5 三轮"多工具档硬阻塞"的结论，很大一部分建立在该字段上**。
- **自我修正**：上一轮 `EXP-M02-015.md` §三 把 `v1-001` 的 `window` 列为"超出考点"的**首要例证**属**取证不准确** → 已更正为**有据判错**（`notes` 明确讨论 window 且配 `lenient=['5m']` 白名单），`docs/known-issues.md` 的 `ISS-029` 举证同步修正为以 `v1-008` / `v1-011` 为首。
- **处置路径**：**路径 C 已立即采用**（不改判据，仅单列该类失败、禁止以"参数值正确率"单独作能力结论）；**路径 B（推荐，不改代码，仅补用例 `notes`/`lenient` 元数据）** 与 **路径 A（改 `compare_arguments` 为"仅比考点字段"）** 均**需授权**，且修订后须**重跑全部 V1 实验并升版判据**。
- **未改动任何判据、用例与阈值**（本项为复核报告）。

### 数据（路径 B：处置 `ISS-029`）

- **`evals/v1_cases.jsonl`（唯一改动文件）**：按用户**明确授权**执行**路径 B**，处置 H8 列出的 **19 个字段**：
  - **A. 非考点 → 移出比对（5 处）**：`v1-002` `search_knowledge.top_k`、`v1-005`/`v1-008` `query_sensor.window`、`v1-011`/`v1-013` `query_sensor.aggregation`（均属"输入未指定该参数、不影响任务正确性"）。
  - **B. 多解 → `lenient_param_defaults`（2 处）**：`v1-007` `aggregation` 增 `["trend","avg"]`；`v1-010` `aggregation` 增 `["trend"]`。
  - **C. 考点 → 补 `notes` 留痕（12 处，零行为变化）**。
  - **`scripts/judge_tools.py` 零改动**（最后修改时间仍为 2026-09-30）。
  - 原件归档为 **`evals/v1_cases-pre-2026-10-05.jsonl`**（沿用 `-pre-<date>` 惯例）。
- 校验：用例数 20→20、全部 JSON 可解析、`input`/`type`/`difficulty`/`expect_reject` 零改动、5 处移除**仅删目标键**（其余键值不变）、14 处 `notes` 均为**纯追加**。

### 结论（路径 B 影响量化，离线重判，零云端调用）

- raw 记录**内嵌运行时 `expected`** → 历史结论**不被追溯改写**；重判时替换为新用例集条目，走**同一份**判分器，差异**纯粹**来自元数据。
- **首次成功率**：`EXP-M02-011`(H0-A) **0.90→0.95**、`EXP-M02-012` 0.85→0.90、`EXP-M02-013`(H3) 0.55→0.60、**`EXP-M02-015`(H5) 0.65→0.80**、`EXP-M02-010` 0.80→0.85、对照臂 **Δ=0**。
- **多工具档 `中间区间 50% → Pass 75%`**（H0-A / H0-B / M02-010）；H5 由 `No-Go 17%` → `中间区间 67%`。
- **`v1-007` 在 5/6 个臂上由全败翻为全通过** → **"多工具档 50% 为跨 prompt 硬阻塞"的结论至少一半源于判据口径**（该用例唯一失败字段 `aggregation` 此前未被 `notes` 声明为考点）。
- ⚠️ **关键：路径 B 口径下无任何臂在五档全部 Pass → `M0.2` 维持 No-Go**，即本次修订**没有**把门禁"改"成通过。
- ⚠️ 本次**未做任何新云端运行**，上述为**离线重判**（属"若按新用例集运行则会得到"的推断值）；作为正式记录须重跑关键臂。

### 文档（路径 B 补充）

- 新增 `reports/v1-cases-revision-2026-10-05.md`；`docs/known-issues.md` **ISS-029 → 已修复**；`docs/risk-register.md` **R-V1-11 → 已关闭**（按 §5.1 规则 4 说明根因已消除）+ 修订记录；`reports/P0-summary.md` §三新增**决策16**；`reports/README.md` 登记新报告。

### 文档（H5 补充）

- 新增 `experiments/v1/EXP-M02-015.md`；`docs/known-issues.md` 新增 **ISS-029**（收录范围 → **ISS-001 – ISS-029**）；`docs/risk-register.md` 新增 **R-V1-11** 并回填 R-V1-9 的处置结果；`reports/P0-summary.md` §三新增**决策14**；`plan/V1-破局路径方案对比.md` §9.4 回填 H5 并列出 H8/H9。

### 预算

- 2026-10-05 云端调用合计 **191 次**（H3 60 + 同日对照 60 + H5 60 + 通道冒烟 11），未超 `budget_lock.per_day_calls = 220`

---

## 2026-09-30 — V1 判据/用例口径复审收口 + 混合形态实测

> 目标：执行 `docs/role-decision.md` §四 处置链遗留项与 V1 判据/用例口径复审（F1–F6），并落地 P6 拆步 / P7 混合形态两条验证路径。

### 代码

- `scripts/llm_adapter.py`
  - **修复 ISS-024（few-shot 恒取 v1）**：`build_messages` 新增 `prompt_path` 参数，令 system 与 few-shot **同源**；
    当 `--prompt` 指向 v2 / step 提示词时不再回退到 `tool_call_prompt_v1.md` 的 3 条 few-shot。
  - **复审 F1**：兼容模型返回的**裸单对象**（非数组）工具调用形态。
- `scripts/run_v1.py`
  - 新增拆步链执行（`run_step_chain_group`）与 `--prompt-step`；三处 `build_messages` 调用显式传 `adapter.prompt_path`。
- `scripts/judge_tools.py`
  - **复审 F4**：`_query_semantic_match` 增关键概念覆盖判定。
  - **复审 F5**：`v1-018` 的 `aggregation` 判据放宽为多解。
  - **复审 F6**：`_refs_type_ok` 对齐规格「至少一条引用」。

### 配置

- `schemas/tools_v2.json`（Schema 简化，按纪律 4 升版）、`schemas/tools_v3.json`、`schemas/tools_v4.json`（**复审 F2** 新增测点目录描述）。
- `prompts/tool_call_step_prompt_v1.md`（P6 拆步提示词，新增）；`prompts/tool_call_prompt_v3.md`（F2 四臂重测后 **未采纳**，保留备查）。

### 数据

- `evals/v2_cases.jsonl`（25 条）、`evals/v3_cases.jsonl`（25 条）新增；`evals/v1_cases.jsonl` 口径更新。
- `experiments/v1/`：`EXP-V1-006`（Schema v2 重测，239 条）、`EXP-V1-007` / `EXP-V1-008`、
  `EXP-V1-009` / `EXP-V1-010`（**P6 拆步，ISS-024 修复后新口径**）、
  `EXP-M02-001` ~ `EXP-M02-005`（**P7 混合形态**：云端 27B 单响应编排 + F2 四臂）。

### 结论

- **M0.2 维持 No-Go**。处置链 ①②③④ 全部执行仍 No-Go；复审 F1–F6 重判 11 实验 19 组 + F2 四臂重测后，
  **整体档位无一翻 Pass**；归因修订为「判据口径缺陷 + 任务信息不足 + 模型部分错」混合归因。
- `docs/known-issues.md` 新增 **ISS-024**（已修复）/ **ISS-025**（云端路径亦 No-Go，已闭环处置）/ **ISS-026**（拒止行为对 prompt 文本敏感且不可迁移）。
- 新增 `reports/v1-review-v2.md`、`reports/v1-review-v3.md`（复审终稿）；同步 `docs/gate-criteria.md`、`docs/role-decision.md`、`reports/P0-summary.md`、`docs/handover-p1.md`、`docs/daily-checklist.md`、`docs/version-lock.md`、`plan/Phase 0 任务总结.md`、`plan/V1-schema-v2-复审建议.md`、`plan/M02-V1-混合形态方案.md`。

### 文件整理与文档同步（本轮）

> 依据：全仓文件清点（208 个真实文件，排除 `.venv`）+ 哈希去重 + 引用路径校验。

- **清理**：删除 `scripts/__pycache__`（8 个 `.pyc`）与 `protos/__pycache__`（可再生的字节码缓存）；删除**空目录** `configs/milvus/`（无任何文档引用）；
  删除**误建目录** `docker/configs/`（其下 `mosquitto.conf/`、`redis.conf/` 为以文件名错误创建的空目录，真实配置在项目根 `configs/`）。
- **修复配置缺陷**：`docker/compose.base.yml` 的 Redis 配置挂载原写作 `./configs/redis.conf`（相对 compose 文件位于 `docker/`，解析为 `docker/configs/redis.conf` —— 即上述空目录），
  与同一文件中 Mosquitto 的 `../configs/mosquitto.conf` 口径不一致，**运行时会挂载空目录导致 `redis-server` 读不到配置**；
  已统一改为 `../configs/redis.conf`，`docker compose config` 实测解析为 `<REPO>\configs\redis.conf`。
- **修正命名**：`experiments/v1/detail-EXP-V1-006.jsonl` → **`detail-EXP-V1-006.csv`**（内容实为 CSV，与同目录其余 10 个 `.csv` 一致）；同步修正 `reports/v1-report.md` 的引用。
- **移除冗余**：删除 `experiments/v1/summary-EXP-V1-004-tiered.csv`（**零文档引用**且与 `summary-EXP-V1-004.csv` **字节相同**；SHA256 = `AD487E57…0B2BA`，可用 `judge_tools.py` 再生）。
  - **保留不删**：`summary-normalize.csv` / `detail-normalize.csv` —— 二者与 EXP-V1-004 的乘积相同**正是 EXP-V1-NORM「uplift = 0」结论的举证**，被 `experiments/v1/EXP-V1-NORM.md` 引用，属证据而非冗余。
- **文档同步**：`README.md`（目录结构块补全 + 脚本数 16→18 + 自检 10→12 + 常用入口补 R-4 命令）；`reports/README.md`（报告索引补 5 份 + 目录范式 + 评测集 3→6 项 + 执行器口径）；
  `docs/risk-register.md`（**§5.3 闭环状态表严重过期已更正**：原称 ISS-001~013 未闭环、「需换方案」条目为空，与 §二 主表矛盾；并回填 D7/D8 占位行）；
  `docs/known-issues.md`（ISS-011 / ISS-013 状态列由「🔲 待 D2–D3 填入」更正为「已修复」，消除与页头声明的自相矛盾）。
- **新增**：`reports/status-audit-2026-09-30.md`（整理前后对比 + 变更清单）。

### 方案对比（新增）

- 新增 `plan/V1-破局路径方案对比.md`：M0.2 破局路径**全量对比**——判据基线 + 各档现状基线（**参数校验 qwen 100% 已 Pass**；单工具 57%/67%、多工具 40% 为仅存短板）+ **9 条已试路径复盘**（①②③④ / P5 `tools_v3` / P6 拆步 / P7 云编排 / F1–F6 重判 / F2 四臂，全部未破局）+ **10 条未试/待决路径**（含**单工具档专项**这一唯一无方案覆盖的缺口）+ 五维对比矩阵 + 推荐执行顺序（口径清零 → 单工具档专项 → 汇总复核，并列出**工程兜底备选**：重试后成功率实测 0.90–1.00）。

### 云端 D1 / D2 实测（M0.2 收口推进）

**背景**：核实发现 `EXP-M02-001`（云端 0.60）使用的是 **`tools_v2`（schema 无测点目录）**，而 F2 采纳的 **`tools_v4` 从未在云端验证** → 原"云端 0.60"系统性低估当前采纳形态。

- **D1 · `EXP-M02-006`**（`Qwen/Qwen3.8-27B` + **`tools_v4`** + `prompt v1`，20 用例 × 1，单变量 = Schema v2→v4）：
  首次成功率 **0.9000（18/20）**，较 `EXP-M02-001` **+30.0pp**；参数值正确率 **0.5882→0.9412**。
  分档：**单工具 100% Pass / 参数校验 100% Pass / 多轮 100% Pass / 多工具 75% Pass**；**无效拒绝 67% No-Go（唯一卡点）**。
  **逐条仅 2 条失败**：`v1-009`（多工具，`direction`）与 **`v1-016`（无效拒绝，幻觉设备号）**。
  → **F2 云端收益（+30pp）与本地四臂（+28.3pp）双向印证**；"云端 0.60"确为**题目缺条件导致的低估**。
- **D2 · `EXP-M02-007`**（同模型、同 `tools_v4`，**唯一变量 = prompt v1→v2**）：
  **拒止假设成立** —— 无效拒绝 **67%→100%**（`4a 应拒绝却调用` 1→**0**，`v1-016` 修复）；
  **但引入 3 处回退**：`v1-004`（单工具）/ `v1-010`（多工具）/ **`v1-019`（多轮，格式退化）** →
  单工具 **100%→83%**、多轮 **100%→67%**，首次成功率 0.8500（净 −1）→ **整体仍 No-Go（卡点换为多轮）**。
  → **`ISS-026`「prompt 文本条件化效应不可迁移」被直接实证**（修好 2 条、弄坏 3 条）。
  → 机制线索：think token 831.8→**878.2** 逼近 `max_tokens=1024` → `v1-019` 判为**截断型格式退化**（`role-decision.md` §4.2 列为待实测代价，**本次首次证实**）。
- **配置**：`env/cloud.json` 的 `budget_lock.per_day_calls` **20 → 40**（**调锁**，文档载明动作 `plan/M02-V1-混合形态方案.md` §六「超限须先调锁」）；当日累计调用 **40 次**，未超调锁值；原因与依据已写入其 `note`。
- **文档**：新增 `experiments/v1/EXP-M02-006.md` / `EXP-M02-007.md`；`reports/P0-summary.md` §三 新增**决策7 / 决策8**；`plan/V1-破局路径方案对比.md` §9.4 按实测修正实验顺序（换模型降为条件性 D4，新增 H0/H1/H2 三个可证伪假设实验）。

- **H2 · `EXP-M02-008`**（`prompt v2` + **`max_tokens` 1024→2048**）：首次成功率 0.85→**0.75**，**格式退化条数与可解析率均不变** → **"think 打满 max_tokens 致截断"假设被证否**（经查 `v1-019` 实为「未调用 `generate_report`」）。**撤回 `EXP-M02-007` 的截断判读**。
- **H1 · `EXP-M02-009`**（新增候选 `prompts/tool_call_prompt_v4.md` = v1 + 强化规则 6a + 1 条**齿轮箱越界示例**，**刻意不使用与 `v1-016` 镜像的示例**）：
  首次成功率 **0.8500**、整体 **中间区间**；**`4a 应拒绝却调用`=0、无效拒绝 100%** → **拒止以"非镜像"方式修复**，
  → **证明 `EXP-M02-007` 的拒止修复非答案泄漏，规则强化本身有效**（**修正 D2 的保守怀疑**）。
- **核心发现（四轮横向对照，方向一致、非噪声）**：**`v1` 族提示词**使 `v1-016`（拒止）失败而 `v1-004`/`v1-010`（参数值）通过；**强化族（v2/v4）**反之
  → **两个提示词族系统性互斥** → **本 20 用例集 + 本判据下不存在"单一 prompt 通过全部 5 档"**（`ISS-026` 的深层实证）；
  其中 `v1-009` 四轮为 x/✅/x/✅ → **证实 repeat=1 存在真噪声**。
  机制：`v1-010` 的 `time_range` **1h→24h**（疑似 few-shot `24h` 锚定，同类见 `OBS-F2-3`）；`v1-004` 的 `depth`/`direction` 枚举偏差（**与规格多解性相关**）。
- **下一步（优先级已定）**：① **架构解耦 = 拒止前置门（R-1 职责，本地 qwen）**，工具调用侧保持 `prompt v1` → 可同时取得两侧最优（**须声明为架构层测试、判据适用对象随之变化**）；② **U3 口径清零**（`direction`/`depth` 多解，**零模型成本**）；③ **H0 repeat=3 降噪**（**判 M0.2 前必做**）。
- **配置**：`env/cloud.json` 的 `budget_lock.per_day_calls` **40 → 100**（第二次调锁，原因与依据已写入其 `note`）；当日累计调用 **80 次**，未超调锁值。
- **文档**：新增 `experiments/v1/EXP-M02-008.md` / `EXP-M02-009.md`、`prompts/tool_call_prompt_v4.md`（候选，未采纳）；`reports/P0-summary.md` §三 新增**决策9 / 决策10**。

- **复现校验 · `EXP-M02-010`（**关键负向发现**）**：对 `EXP-M02-006` 的配置**逐字复跑**（模型/endpoint/用例集/`tools_v4`/prompt v1/seed 42/temp 0/`num_ctx`/`top_p`/`max_tokens`/repeat 1 全同）—— **首次成功率 0.90 → 0.80（未复现）**，单工具 100%→**83%**、多工具 75%→**50%**；仅**参数校验 4/4、多轮 3/3、无效拒绝 2/3 两轮一致**。
  **5 轮横向对照**（D1_v1 / **R_v1** / D2_v2 / H2 / H1）显示：`v1-001`/`v1-006`/`v1-007`/`v1-009`/`v1-019` **在同一 prompt 下正反均出现 → 噪声**；**`v1-010` 在 `prompt v1` 两次运行中一成功一失败 → 与 prompt 版本无关**；**仅 `v1-016`（拒止）稳健相关**（v1 族 0/2 ❌ / 强化族 3/3 ✅，含 `v4` 非镜像）。
  → **📌 结论撤回与修正**：**撤回**"两个提示词族系统性互斥"（见 `EXP-M02-009.md` §2.1、本文件上一条、`P0-summary` 决策10）；**修正** `EXP-M02-006` 的"4/5 档 Pass、唯一卡点 = 拒止"表述。**根因 = `repeat=1` 且每档仅 3–6 例 → 档位不确定度 ±17–33pp**。
  → **`H0（repeat≥3）` 升为最高优先级**：`M0.2` 判定前，须对候选配置各做 **20 用例 × repeat 3 = 60 次**；**在此之前不得宣称任何配置的档位结论**。
- **文档**：新增 `experiments/v1/EXP-M02-010.md`；更正 `EXP-M02-006.md` / `EXP-M02-009.md`（撤回与打折）；`reports/P0-summary.md` §三 新增**决策11**。
- **预算**：当日累计云端调用 **100 次 = 调锁后上限**（D1/D2/H2/H1/R 各 20），**当日不可再调**。

- **H0 · `EXP-M02-011` / `EXP-M02-012`（双臂 × `repeat=3`，**决定性实验**）**：各 20 用例 × repeat 3 = 各 60 次。
  **稳定档位**：**`prompt v1`** → 单工具 **18/18=100%** ✅、参数校验 12/12=100% ✅、多轮 9/9=100% ✅、无效拒绝 **7/9=78%** ⚠️、**多工具 6/12=50%** ❌；
  **`prompt v4`** → 单工具 **14/18=78%** ⚠️、参数校验 100% ✅、多轮 100% ✅、无效拒绝 **9/9=100%** ✅、**多工具 6/12=50%** ❌。**双臂均判「中间区间」**。
  → ① **多工具档 50% 两臂完全相同 → 与 prompt 无关的硬阻塞**（稳定失败 = **`v1-007`、`v1-010`，两臂均 0/3**，根因均含 **`aggregation` 语义选值**：模型系统性给 `trend`，期望 `max`/`avg`）；
  → ② **"拒止 ↔ 单工具"互斥在 `repeat=3` 下确认成立（非噪声）**；
  → ③ **参数校验与多轮 100% 稳定**。
  → **修正** `EXP-M02-006` 的"0.90 / 4 档 Pass"（`repeat=3` 下不成立）；**阻塞由"多档不明"收敛为单点**。
  → **根因**：`tools_v4` 的 F2 **只补了 `sensor_ids`，未补 `aggregation` 描述** → 存在**与 F2 同类的"任务信息不足"缺口**。
  → **下一步 H3（推荐）**：拟 `schemas/tools_v5.json` = `tools_v4` + **扩写 `aggregation` 的 `description`**（同 F2 做法，不改 enum/required/结构，判分语义不变）+ `prompt v1`。
- **文档**：新增 `experiments/v1/EXP-M02-011-012.md`；`reports/P0-summary.md` §三 新增**决策12**。
- **预算**：**当日累计 220 次 = 调锁后上限**（D1/D2/H2/H1/R 各 20 + H0 双臂各 60），**当日不可再调**。

### 验证

- 12 个 Python 脚本 `--selftest` **12/12 PASS（exit 0）**。
- `compose.base.yml` / `compose.ingest.yml` / `compose.v2.yml` / `base + v4b-iso` 合并渲染的 `config --quiet` **4/4 通过**（`v4b-iso` 为 override 文件，独立运行必失败，属设计）。
- 全仓 JSON / JSONL 解析通过（修复命名后无失败项）。

### 门禁文档一致性同步（同日第二轮）

> 目标：使 P0 门禁相关文档的状态表与实测结论完全一致（原存在"结论已出、状态表未回填"的系统性偏差）。

- `reports/P0-summary.md`
  - §三 标题「**空表待填**」→「已回填」；§3.1 当前状态更正为「**已无未闭环中间区间项**」（V4b 已升 Pass、V2/V3 已闭环，仅剩 V1 No-Go）。
  - §四.1 交付物核对 **6 行**「⚠️ 待填 / 待实测」→ **✅ 已实测**（V1 报告 / V2 参数基线表 / V5 报告 / 联合决策 / V4b 资源实测 / `checkpoint-decision.md` §2.1）。
  - §二 V2 判定由「条件 Pass」更正为 **Pass**（压力档 EXP-V2-LOAD 已闭环），同步 §〇 状态声明与 §8.2 可用性判定。
  - §1.3 / §八.1 执行器口径「五个脚本」→ **18 个 Python 脚本（12 个含 `--selftest`）+ 2 个 PowerShell**。
  - §八.1 环境基线版本号笔误 `v1` → **`v2`**；§七.2 缺陷登记「ISS-001~ISS-013」→ **ISS-001~ISS-026**、版本锁定口径更新为「已收敛」。
  - **待裁决清单全部勾销**：§3.3（= 四步）、§5.2（= 6 项）、§6.4（`R-新2`/`R-新3` **经复核无冲突**）、§6.5（= 口径 B）、§6.6 第 3 条（compose 裸 tag **实测已清零**，8 镜像全部 `tag@digest`）。
- `docs/handover-p1.md`
  - §2.6 `known-issues.md` 收录范围 **ISS-018 → ISS-026**；`scope-mvp` / `gate-criteria` / `daily-checklist` / `risk-register` / `schema-mapping` 五行「待回填」→ **已回填**。
  - §2.7 报告状态 **v1 / v2 / v3 / v4b / v5** 五行「待实测 / 未执行 / 当前不可执行」→ **已实测回填**（v3 已封板、v4b 已升 Pass）。
  - §三 P0-3「`.wslconfig` 当前未落地」→ **已安装并核验**。
  - §四.1 **L-02 / L-04 / L-06 / L-07 / L-10** 由「阻塞 / 决策未做 / 未执行 / 待定义」→ **已裁决 / 已决 / 已闭环 / 已裁决**。
  - §4.2 **ISS-001 – ISS-008** 由「待 D7 判定」→ 实际结论（**ISS-005 = 需换方案已切 PG**，其余为可规避 / 已修复 / 已裁决）；**ISS-015–018 → ISS-015–023** 并新增 **ISS-024–026** 行。
  - §6.2 阻塞项交接清单与 §6.6 验证项判定（原写「V1/V2/V3/V4b/V5 = **无法判定**」，**与同文件 §5.2 直接矛盾**）已更正；页头状态声明与 §5.3 承接事项同步；修订记录中 **3 条过期占位行**（【待 M0.6 评审】/【待各验证项实测】/【待 L-01/L-03 闭环】）回填为实际完成记录。
- `plan/Phase 0 任务总结.md`：§2.3 待裁决 **D-01 ~ D-04** 的「确认结果」列由空 → **✅ 已裁定**（四步 / 6 项 / 编号无冲突 / 口径 B + 干净机 17.89GB 升 Pass）。
- `docs/role-decision.md`：**经复核无需修改** —— 其 §5.3 已使用 `R-新3`，全仓 `R-新2` 仅指 GPU 直通（ISS-008）。

> **红线声明**：本次同步只回填**已由实测得出的结论**，未新增任何未实测数字；`reports/P0-summary.md` 与 `docs/handover-p1.md` 的修订记录均**追加**一行，未删除任何历史记录。

---

## 2026-09-29 — 代码与文档一致性审计（全仓）

> 目标：核对函数签名 / 参数说明 / 返回值 / 使用示例 / 配置项 / 环境变量 / 依赖版本与注释、README、API 文档的一致性，并修复代码缺陷。

### 配置

- `configs/decoder_schema_mapping.json`
  - 修正 `boundary_handling.rebirth_conflict` 的 bdSeq 回退动作：由不可落地的 `quality_ok=FALSE`
    改为实际实现 `st_device_status.online=FALSE + reason='rebirth_rollback'`；
    新增 `rebirth_authority` 声明 M6 的 bdSeq 基准取自内存 `DeviceRegistry`。
  - 补全 `device_id_validation`：新增 `applies_to` / `scope_note`，说明解码侧宽松口径与
    工具契约严格口径并存（见 `docs/schema-mapping.md` §6.1）。
- `configs/redis.conf`
  - 补写「网络与安全」段：说明 `bind 127.0.0.1` 的适用形态，并给出 Docker 容器形态的注释化替代块
    （`bind 0.0.0.0` / `protected-mode no`）；新增 `docs/known-issues.md` **ISS-015** 跟踪。
  - 修正措辞：`maxmemory-policy 带 ttl` → `volatile-* 系列策略`。
- `docker/compose.ingest.yml`
  - 删除代码**不读取**的死环境变量：`SPB_GROUP_ID`、`SPB_EDGE_NODE_ID`、`DECODER_DB_NAME`、
    `DECODER_SUPER_TABLE`（group / edge / 库名 / 超级表名的唯一来源为映射配置文件）。
  - 补齐代码**实际读取**但此前未注入的 `TD_USER` / `TD_PASSWORD`。

### 代码

- `scripts/self_decoder.py`
  - **实现 R-V3-5**：`TopicParser.is_valid_device()` + `handle_bytes` 对 `DBIRTH`/`DDATA`/`DDEATH`
    校验 `device_id`（`NDEATH` 为网关级报文不适用），非法值丢弃并告警，不再进入子表名与 SQL；
    `SqlBuilder` 侧新增标识符白名单常量 `_SAFE_TAG_RE`。
  - **实现配置要求的时间戳优先序**：`metric.timestamp → payload.timestamp → 服务器时间`
    （主表行时间戳仍统一取 payload 级，避免被循环变量污染）。
  - 修正 bdSeq 回退告警文案；删除空操作语句 `column_values`；
    新增 `DeviceRegistry.all()` 公共接口，替换对私有成员 `_devices` 的直接访问；
    `query_last_birth_seq()` 补 docstring 声明「预留未接入」并对标识符做白名单校验。
- `scripts/run_v5.py`
  - **修复 B2 判据失效**：原实现 `compare_payload(before, before)` 自比对导致 B2 恒为真；
    改为取 **resume 前** checkpoint 状态与 resume 后比对。
  - `--checkpointer` 默认值由 `redis` 改为 **`postgres`**（与已定稿的候选 B 路线一致）；
    t5.5–t5.7 运行时显式提示"Redis 侧检查，不随 `--checkpointer` 切换"。
  - `POSTGRES_URL` 端口 `5927` → **`5433`**（ParadeDB 宿主映射实际值）。
  - 注明 B7 没有代码落点（属环境人工判定，执行器不会自动触发）。
- `scripts/run_v2.py`：`--dsn` 默认库名 `postgres` → **`auscult_v2`**（原默认连不到 `kb_chunks`）；
  更新 BGE-M3 维度注释（已实测确认 1024）。
- `scripts/run_v1.py`
  - 修复云端端点 + `--constrain` 误走 Ollama 原生 `/api/chat` 的通道选择缺陷
    （新增 `structured_output=is_cloud and bool(grammar)`）。
  - 回灌口径与判分口径对齐：`match_expected_calls` 补传 `lenient_param_defaults`。
  - 将恒不可达的 `if not grammar` 改为对真实失败模式的处理（文件 / 键 / JSON 错误、无工具分支）。
- `scripts/llm_adapter.py`
  - 修正模块 docstring：`tool_calls` 缺失时**置位标志**而非抛异常；few-shot 条数由提示词文件决定（v1=3 / v2=8）。
  - `ToolCallsMissingError` docstring：标签改为实现实际的 `格式退化`，并注明默认不抛。
  - 修复重复表达式 `data.get("done_reason") or data.get("done_reason")`。
  - `describe()` 分支文案明确区分「云端 response_format」与「Ollama 原生 format」两条通道。
- `scripts/judge_tools.py`
  - docstring 更正多工具判定语义为**多重集精确相等**（原写"完整覆盖"），并登记 **ISS-016**。
  - 更正云端数字口径注释（裸跑 0.60 / 约束解码 0.55，不再统称"上界 0.60"）。
  - 自检输出 `六类失败归类` → **`七类失败归类`**；`--detail-out` 空结果保护（原会 IndexError）。
- `scripts/param_normalizer.py`
  - R2 规则说明与 `_ID_FIELDS` 实际白名单对齐（`device_id` / `sensor_ids` / `start_node` / `device_model`）。
  - 删除恒假条件 `not isinstance("1h5m", str)`，改为可证伪的复合时长断言。
- `scripts/gbnf_grammar.py`：文件名 / 函数名沿用 GBNF 口径但实际载体为 JSON Schema，已在文件头显式声明。
- `scripts/spb_simulator.py`：docstring 补齐第 5 类边界 `ndeath`；DBIRTH 由 QoS0 改为 **QoS1** 并计入 PUBACK 等待。
- `scripts/v3_ingest_direct.py`：修正用法中的脚本名（`ingest_direct.py` → `v3_ingest_direct.py`）与日志前缀；
  删除冗余别名变量。
- `scripts/run_v3_alert.py` / `scripts/verify_query_sensor.py`：SQL 拼接前新增标识符白名单校验
  （列名 / `device_id` / 窗口单位），防注入。
- `scripts/check_ports.ps1`：WSL2 探活由 `sh -c` 改为 `bash -c`
  （`/dev/tcp` 是 bash 专有特性，busybox sh 下会**恒定假阴性**）。
- `scripts/collect_env.ps1`
  - 修复 GPU 段整体失败缺陷：原把 `[ordered]` 字典塞进 `ArrayList` 后按字符串键改写字段，
    PowerShell 会包装为 PSObject 并抛 `property cannot be found` → 整个 GPU 段返回 `null`；
    改为不可变数组 + 末尾一次性构建 `[pscustomobject]`。
  - 补齐 toolchain 版本采集分支：`docker` / `wsl` / `nvidia-smi` 原恒为空串。
- `scripts/run_cloud_baseline.py`：新增 `--selftest`（V1 固定参数 / 20 用例 / 5 工具 / 约束分支 / 落盘编号）；
  固定实验参数改为显式传入；打印实际处理条数；辅助函数更名 `llm_adapter_build` → `build_case_messages`。

### 文档

- `docs/schema-mapping.md`：TDengine 版本 `3.3.6 LTS` → **`3.3.8.0`**；子表命名示例 `d_plant1_PUMPA` → `d_plant1_PUMP-A`；
  补齐 `pump_speed` 行缺失的列类型单元格；R-V3-5 标为**已实现**、R-V3-6 标为**已闭环**；
  标注时间戳优先序已实现、**心跳兜底未实现**（ISS-017）；NDEATH 数据来源改为内存 registry；
  新增 §6.1 「`device_id` 两套校验口径」说明。
- `docs/known-issues.md`：页头收录范围更正为 ISS-001 – ISS-018；回填 ISS-007（已修复 2026-09-24）、
  ISS-008（已裁决）、ISS-009（已锁定 0.34.2）；修正 ISS-013 规避手段描述；
  **新增 ISS-015（Redis 容器网络）/ ISS-016（多工具指标命名）/ ISS-017（心跳兜底未实现）/
  ISS-018（`env/hardware.json` 停留在 v1 口径）**。
- `docs/scope-mvp.md`、`docs/handover-p1.md`、`plan/Phase 1 详细开发计划…md`：
  工具名 `retrieve_knowledge` → **`search_knowledge`**（与冻结 Schema 一致）。
- `docs/handover-p1.md`、`reports/P0-summary.md`：`六类失败归类` → **`七类失败归类`**（与判分器一致）。
- `docs/version-lock.md`：ParadeDB 宿主端口 `5927` → **`5433`**；真 BM25 状态更新为已闭环；修正修订记录中的采集时间引用。
- `reports/project-overview.md`：V3 聚合 P95 `10.2 ms` → **`26.2 ms`**（实测）；ParadeDB 端口更正为 5433；
  删除已过期的"尚余裸 tag `eclipse-mosquitto:2`"结论（2026-09-29 已清零）。
- `reports/v2-report.md`：PostgreSQL 宿主端口更正为最终值 5433；修正笔误 `19630` → `19530`。
- `reports/project-summary-2026-09-29.md`：新增并作为最新全景总结。

### 新增文件

- `README.md`（根）：项目入口、当前状态速览、目录结构、快速开始、迭代纪律。
- `requirements.txt`：Python 依赖锁，版本全部取自 `docs/version-lock.md` §二.2.7 / 2.8 / 2.9。
- `CHANGELOG.md`：本文件。

### 验证

- 10 个 Python 脚本 `--selftest` 全部通过（exit 0）。
- 4 个 JSON 配置解析通过；`compose.base.yml` / `compose.ingest.yml` / `compose.v2.yml`
  及 `base + v4b-iso` 合并渲染 `config --quiet` 全部通过。
- 用 `judge_tools.py` 对 `EXP-V1-002` / `EXP-V1-005` 重跑判分，核验云端口径：裸跑首次成功率 0.6000、
  约束解码 0.5500（可解析率 0.8824、多工具档 50%），与文档修正后的数字一致。

### 补遗（同日第二轮）

- `docs/known-issues.md`：回填 §六 复现记录区的 **ISS-009（已锁定 0.34.2）/ ISS-011（已修复，可解析率 1.00）/
  ISS-012（可规避，P1 补测量化档）/ ISS-013（已修复，本地 0 次退化、云端 2 次且已单独归类）**；页头总体状态同步。
- `docs/handover-p1.md`：§2.5 脚本资产清单由 5 个补全为 **15 个**（含 `gbnf_grammar` / `param_normalizer` /
  `run_cloud_baseline` / V2 压力档 / V3 三个验证脚本，并如实标注哪些无 `--selftest`）；§2.6 文档状态由
  "待实测回填"回填为已定稿；ISS-007–013 状态同步并补登 ISS-015–018。
- `docs/scope-mvp.md`：**Must 链 13 项的"当前状态"列**由"框架就绪，实测未执行"回填为按 V1–V5 实测结果
  逐项标注（含 3 项缺口：`p95`/`anomaly` 未实现、业务表与审计日志待 P1）。
- `reports/v5-report.md`：缺陷清单范围更新为 ISS-001 – ISS-018。
- `reports/P0-summary.md`、`reports/project-overview.md`：版本锁定待办口径与已完成整改项同步。

### 补遗（同日第三轮：采集链路 D-1）

**代码**

- `scripts/collect_env.ps1` / `scripts/check_ports.ps1`：**恢复纯 ASCII**。两个 `.ps1` 头部均约定 "ASCII-only on purpose"（PS 5.1 按 ANSI 码页读取无 BOM 的 `.ps1`），此前写入的 UTF-8 中文注释被按 CP936 解码后会吞掉后续换行与花括号，导致 `Unexpected token '}'` 语法错误、脚本完全不可执行。现两文件 nonASCII 字节数 = 0 且 `Parser::ParseFile` 零错误。
- `scripts/collect_env.ps1`（WSL 段）：**修复发行版停止时的永久挂起**。原实现无条件 `wsl -d docker-desktop -- ...`，发行版为 `Stopped` 时 WSL 会尝试启动它并长时间阻塞（实测 >120s 不返回），快照一个字节都写不出。现先解析 `wsl -l -v` 的发行版状态，仅 `Running` 才进入；否则写 `distro_state` 并把 `live_raw` / `gpu_passthrough_in_wsl` 标为 `SKIPPED` 并记 warning。
- `scripts/collect_env.ps1`（写盘段）：**修复 JSON 序列化挂起/OOM**。`wsl.exe` 输出为 UTF-16LE，经单字节码页解码后字符串夹带 `\0` 等控制字符，PS 5.1 的 `ConvertTo-Json` 对其抛 `OutOfMemoryException` 或不返回，整份快照写失败。新增 `Repair-String`（去控制字符与非配对代理项）与 `ConvertTo-JsonSafe`（递归净化对象图），并把写盘改为**按分区序列化**——单个分区失败只置 `null` + 记 warning，不再拖垮整份快照。

**数据 / 事实裁定**

- **主机名裁定（方向与初判相反）**：实测 `hostname` / `%COMPUTERNAME%` / `Win32_ComputerSystem.Name` / DNS **四路一致为 `<WORKSTATION>`**，`<HOST_ALIAS>` 不可解析 → 是 **`env/env-baseline-v2.md` 写错**，`env/hardware.json` 正确。已更正 9 份文档：`env/env-baseline-v2.md`、`env/env-baseline-v1.md`、`docs/version-lock.md`、`docs/daily-checklist.md`、`reports/daily/D1-status.md`、`reports/project-overview.md`、`reports/project-summary-2026-09-29.md`、`reports/P0-summary.md`（原"待核实"项已裁定）。
- **重采验证（未覆盖原文件）**：修复后 `collect_env.ps1` 实测跑通并产出 14 KB JSON，关键值与基线交叉验证一致——GPU `RTX 4060 Laptop / 8188 MiB / 驱动 616.56 / CC 8.9`、Docker `19.53 GB / NCPU 10`、工具链 `python 3.12.8 / node v24.19.0 / git 2.45.1 / docker 29.6.2 / wsl 2.7.11.0 / nvidia-smi 616.56` 全部有值。**因重采时 `docker-desktop` 发行版为 `Stopped`（WSL live 配额与 GPU 直通会落 `SKIPPED`），未覆盖 `env/hardware.json`**，待发行版 Running 后再重采。

**文档**

- `docs/known-issues.md`：新增 **ISS-019（发行版 Stopped 导致采集挂起）/ ISS-020（含 NUL 字符串导致 ConvertTo-Json 挂起或 OOM）/ ISS-021（`.ps1` 非 ASCII 注释损坏解析）**；ISS-018 更新为"缺陷已修、快照待刷新"并附交叉验证值；收录范围更新为 ISS-001 – ISS-021。
- `reports/project-summary-2026-09-29.md` 附录 A：新增 C-17（主机名更正）/ C-18（ASCII 约束）/ C-19（WSL 挂起）/ C-20（序列化挂起），并把 D-1 更新为实际进展与阻塞原因。

- `scripts/check_ports.ps1`（WSL2 段）：**修复 WSL2 侧端口探活在 `docker-desktop` 中完全不可用**。busybox `sh` 不支持 `/dev/tcp`（恒报 `free`，假阴性），`bash` 又未安装（`bash: not found`，恒报 `unknown`），因此 T1.3 的"WSL2 侧端口可用性"结论此前**没有有效依据**。改为：先判发行版状态 → 在发行版内执行**一次** `netstat -ltn` → 在 PowerShell 侧解析监听端口集合后逐个比对（12 次 `wsl` 调用降为 1 次）。实测 `distro state: Running`、12 端口逐个判定，且与发行版内实际监听的 5 个端口自洽；登记 **ISS-022**。

**新增编辑纪律**

- **任何 `.ps1` 改动后必须校验非 ASCII 字节数为 0**（`[System.IO.File]::ReadAllBytes($f) | Where-Object { $_ -gt 127 }`），并跑一次 `[System.Management.Automation.Language.Parser]::ParseFile(...)` 确认零解析错误。

### 补遗（同日第四轮：D-1 环境快照重采完成）

**数据**

- **`env/hardware.json` 已重采覆盖**（`collected_at = 2026-09-29T11:49:36+08:00`，**零警告**，15,179 bytes）。重采前后差异：

  | 字段 | 重采前（v1 口径） | 重采后（实测） |
  |---|---|---|
  | `gpu` | `null` | `NVIDIA GeForce RTX 4060 Laptop GPU / 8188 MiB / nv 616.56 / CC 8.9` |
  | `wsl.wslconfig_present` | `false` | `true`（`distro_state = Running`） |
  | `wsl.live_raw` | 无 | `10 \| Mem: 20001 ...`（NCPU 10 / MemTotal ≈20 GB） |
  | `docker.mem_total_gb` / `ncpu` | `15.51` / `20` | `19.53` / `10` |
  | `toolchain.docker/wsl/nvidia-smi` | 空串 | `29.6.2` / `WSL 2.7.11.0` / `616.56` |
  | 编码 | — | **无 BOM** UTF-8，严格 `json.load(encoding='utf-8')` 通过 |

  重采值与 `env/env-baseline-v2.md` **逐项一致**，互为佐证；初采时间实为 `2026-09-23T20:59:50`。
- 旧 v1 快照留档为 `env/hardware-v1-2026-09-23.json`（仅供追溯，不参与引用）。
- 重采时 Ollama 服务未运行，`toolchain.ollama` 记 `UNKNOWN`；**版本仍以锁定的 0.34.2 为准**，不因本次未取到而漂移。

**代码**

- `scripts/collect_env.ps1`（写盘段）：改用 `[System.IO.File]::WriteAllText` + `UTF8Encoding($false)`，避免 PS 5.1 的 `Set-Content -Encoding UTF8` **写入 BOM** 破坏严格 JSON 读取器。
- `scripts/collect_env.ps1`（工具链探针）：过滤 `Warning|could not connect` 行，避免把 `ollama --version` 在服务未运行时的告警文本当成版本号。

**文档**

- `env/env-baseline-v2.md`：新增"重采核验（2026-09-29）"说明块（含重采时间、逐项一致结论、Ollama 未运行说明、旧快照留档位置）。
- `docs/version-lock.md`：硬件来源更新为"已于 2026-09-29 重采"。
- `docs/known-issues.md`：**ISS-018 标记为已修复闭环**（附重采前后差异）。
- **采集时间口径更正**：`env/hardware.json` 的初采时间为 `2026-09-23T20:59:50`（原多处误记为 20:51；20:51 是 `env/ports.md` 的 T1.3 端口检查时间，属另一项测量且本身正确）。已更正 `reports/daily/D1-status.md`（2 处）、`docs/handover-p1.md`、`docs/daily-checklist.md`、`reports/v1-report.md`、`reports/v4b-report.md`。
- `reports/project-summary-2026-09-29.md` 附录 A：新增 C-22（BOM 写盘 / ollama 探针）、C-23（采集时间口径），D-1 标记完成。

### 补遗（同日第五轮：D-5 汇总表治理 + D-6 矛盾裁决落地）

**代码**

- `scripts/run_v2.py`（`write_summary`）：**由"每次整表覆盖"改为"按 `experiment_id` 合并"**。原实现以 `"w"` 模式重写 `experiments/v2/summary.csv`，只跑单条路线时会把其它路线的已实测结果一并清掉（该文件一度只剩 2 行）。现先读回既有表 → 用本次结果覆盖同 id 行 → 其余保留 → 列集合取并集后重写；既有表损坏时只告警不阻断本次落盘。已用两次不同路线验证"合并保留"与"同 id 幂等更新"。登记 **ISS-023**。

**数据**

- `experiments/v2/summary.csv` **由 2 行还原为 7 行**（用 `raw/EXP-V2-*.jsonl` 首行重建），`recall / mrr / p95` 与 `reports/v2-report.md` §4.4 **逐项一致**；并修正了残留 `EXP-V2-milvus-hybrid` 行的**延迟口径**（原 mean 158.7872 / p95 110.0240 来自另一次 run，实为 p95 **9.4800**）。无原始文件可还原的 `EXP-V2-pgvector-hybrid-paradedb` 行原样保留（出处为 `experiments/v2/raw/EXP-V2-BM25.md`）。原表留档 `experiments/v2/summary-pre-2026-09-29.csv`。

**文档（D-6 上游矛盾裁决落地）**

- V1 中间区间处置步骤数（2 vs 4）：在 `reports/v1-report.md` §7.2 就地标注——本表为"两步加固 + 两步兜底"的精简表述、缺"Schema 简化"一级，权威清单为 `docs/role-decision.md` §四 的**四步**；`reports/P0-summary.md` 的"待裁决"改为**已裁定闭环**。
- M0.1 通过条件项数（3 vs 6）：在 `plan/Phase 0 详细开发计划（D1-D10 可执行版）.md` §五 的 M0.1 行标注——该行为精简表述，权威为 `reports/daily/D1-status.md` §六 的 **6 项**。
- `docs/known-issues.md`：新增 **ISS-023**；收录范围更新为 ISS-001 – ISS-023。
- `reports/project-summary-2026-09-29.md` 附录 A：新增 C-24（汇总表覆盖写与还原）、C-25（两处上游矛盾的裁决落地），D-5 标记完成。

---

## 2026-09-28

- **V2 真 BM25 对标闭环**（EXP-V2-BM25）：ParadeDB ngram BM25 sparse `Recall@5` 0.90 vs Milvus 0.92，hybrid 打平 0.91；
  tsvector 路线淘汰（中文 `Recall@5 = 0`）。见 `docs/version-lock.md` §二.2.8。
- **V2 压力档闭环**（EXP-V2-LOAD）：10 万块 Milvus 查询 P95 5.6 ms / 1.28 GB；pgvector 170.6 ms / 0.33 GB。
  新增 `scripts/v2_synth_corpus.py`、`scripts/v2_load_test.py`。
- **V1 参数归一化纠错否决**（EXP-V1-NORM）：217 条逐条 diff 变化 0 条、**uplift = 0**，该路径关闭。
- **V1 判据分档重校**（`docs/gate-criteria.md` §3.1.1）：多工具为结构性硬限，单独设低线；新增
  `judge_tools.judge_verdict_tiered`。
- **提示词 v2 落地**（`prompts/tool_call_prompt_v2.md`，EXP-V1-004）：few-shot 3 → 8 条 + 拒止专项 + `--constrain`。
- 巡检整改：`docker/compose.v2.yml` ParadeDB 端口 5927 → 5433。

## 2026-09-24

- **V5 checkpoint 全流程完成，M0.4 达成**：T5.1–T5.7 全 Pass。因 **B7**（redis-py ↔ redis-stack 握手被服务端关闭，
  非缺 RediSearch）弃候选 A，采纳 **PostgreSQL checkpointer**。见 `docs/checkpoint-decision.md` §2.1、`reports/v5-report.md`。
- **T1.1 `.wslconfig` 落地并核验**（20 GB / 10 vCPU / swap 8 GB），**ISS-007 闭环**；
  `env/env-baseline-v2.md` v2 发布。
- **ISS-008 裁决**：GPU 直通不可用 → 改走宿主 Ollama（`127.0.0.1:11434`）。
- **TDengine 授权定稿**：OSS 无 taosX / 连接器 → 自研 Sparkplug B 解码器（≈1.9 人日，≤2 天红线内）。

## 2026-09-23

- **T1.6 `schemas/tools_v1.json` 冻结**（5 工具：4 只读在图内 + `generate_report` 写操作图外）。
- T1.2 环境采集（`env/hardware.json`）、T1.3 端口检查（`env/ports.md`，12 端口 11 空闲）、
  T1.7 数据来源盘点、T1.8 实验登记模板落盘。
- M0.1 判定：**条件通过**（`.wslconfig` 与 TDengine 授权两项缺口，后均闭环）。

---

## 版本约定

- **Phase 0 期间不发布语义化版本号**：以日期 + 验证项为变更粒度，权威记录为 `docs/version-lock.md` 的修订记录表。
- 组件 / 模型版本一律以 **digest** 表述，禁止裸 tag 与 `latest`（纪律 1）；变更即升版环境基线（纪律 2）。
