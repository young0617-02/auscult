# 实验登记规范模板（Experiment Log Template）v1

> **对应任务**：T1.8 ｜ **上游依据**：Phase 0 详细开发计划 §八「通用规则」
> **环境基线引用**：本模板中"硬件与 WSL 配额快照"字段须与 `env/env-baseline-v2.md` **逐字一致**
> **版本**：v1 ｜ **定稿日期**：D1 ｜ **状态**：已定稿
> **适用范围**：V1–V7 全部验证项，以及任何产生可比较数字的实验

---

## 一、为什么必须有这份规范

Phase 0 的结论是"**用数字做的技术决策**"。数字只有在**可复现**时才可信。本规范把每次实验的**环境、输入、参数、代码**四类信息固定下来，做到：

1. 任何人（包括两周后的自己）能按"复现命令"重跑出同一个结果；
2. 报告里引用的版本号与 digest 能回溯到唯一来源；
3. 出现异常结果时能判断是"结论"还是"环境漂移"。

---

## 二、必填字段定义

| 字段 | 类型 | 必填 | 说明 | 取值示例 |
|---|---|---|---|---|
| `experiment_id` | string | ✅ | 唯一编号，格式 `EXP-<验证项>-<序号>` | `EXP-V1-003` |
| `date` | date | ✅ | 实验执行日（本地时区） | `2026-09-22` |
| `phase_item` | enum | ✅ | 验证项编号 | `V1` / `V2` / `V3` / `V4a` / `V4b` / `V5` / `V6` / `V7` |
| `purpose` | string | ✅ | 一句话说明本次要回答什么问题 | "测 qwen2.5:7b 在 Schema v1 下的首次工具调用成功率" |
| `env_baseline_version` | string | ✅ | **环境基线版本号**（引用 `env/env-baseline-v2.md`） | `env-baseline-v2` |
| `image_model_digests` | map | ✅ | **镜像与模型 digest**（禁止写 `latest` 或裸 tag） | 见 §三范例 |
| `seed` | int | ✅ | 随机种子；模型侧若不可控须注明 | `42` |
| `prompt_version` | string | ✅ | 提示词文件路径 + 版本（**内容指纹见 `ISS-034` 修复后的 meta**） | 示例 `prompts/tool_call_prompt_v1.md`；⭐ 当前最优候选 = `prompts/tool_call_prompt_v4.md`；⛔ `v2` 含测试集泄漏（`ISS-032`），禁用于评测 |
| `num_ctx` | int | ✅ | 上下文窗口 | `8192` |
| `temperature` | float | ✅ | 采样温度 | `0.0` |
| `code_commit` | string | ✅ | Git commit（短 hash 或 `dirty-<hash>`）。**该字段自 2026-10-06 起可填写**：仓库基线提交 = `672143e`（标签 `baseline-2026-10-06`，见 `CHANGELOG.md` 2026-10-06）。工作区存在未提交改动时写 `dirty-<短hash>` | `672143e` |
| `hardware_snapshot` | string | ✅ | 硬件与 WSL 配额快照（**照抄基线**） | 见 §三范例 |
| `raw_data_path` | path | ✅ | 原始数据落盘路径（必须在 `experiments/**/raw/`） | `experiments/v1/raw/EXP-V1-003.jsonl` |
| `conclusion` | string | ✅ | 结论摘要（可量化则必须带数字） | "首次成功率 85%（17/20）→ 落入中间区间" |
| `anomalies` | string | ✅ | 异常与偏差（无则写"无"） | "2 次调用未返回 tool_calls，疑似静默退化" |
| `reproduce_cmd` | string | ✅ | 复现命令（可直接粘贴执行） | 见 §三范例 |

### 2.1 字段纪律（**违反即实验作废**）

1. `image_model_digests` 必须是 **digest**，不接受 tag。原因：tag 可被重新推送覆盖，digest 不会。
2. `hardware_snapshot` 必须与 `env/env-baseline-v2.md` **逐字一致**；若实测发现不一致，先修基线，再重跑实验。
3. `raw_data_path` 必须存在且为**原始响应**（未加工的 JSONL），加工后的汇总表另存。
4. `conclusion` 中出现的每个数字，必须能在 `raw_data_path` 里算出。
5. 中途改变任何参数（num_ctx/temperature/prompt）→ **必须新开 `experiment_id`**，不得在原有条目上覆盖。

---

## 三、填好的范例（V1 实测 qwen2.5:7b）

```yaml
experiment_id: EXP-V1-003
date: 2026-09-22
phase_item: V1
purpose: 在固定部署形态 + 工具 Schema v1 下，测 qwen2.5:7b 的工具调用首次成功率与参数可解析率
env_baseline_version: env-baseline-v2

image_model_digests:
  llm.qwen2.5_7b.layer:     "sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730"
  llm.qwen2.5_7b.manifest:  "sha256:2f15b3218f0552c60647ce60ada83632d2c09755b16259b13e3e4458e9ae419d"
  llm.deepseek-r1_7b.layer: "sha256:96c415656d377afbff962f6cdb2394ab092ccbcbaab4b82525bc4ca800fe8a49"
  llm.deepseek-r1_7b.manifest: "sha256:40fb844194b25e429204e5163fb379ab462978a262b86aadd73d8944445c09fd"
  runtime.ollama: "0.34.2"        # API http://127.0.0.1:11434

seed: 42
prompt_version: prompts/tool_call_prompt_v1.md
num_ctx: 8192
temperature: 0.0
code_commit: a1b2c3d

hardware_snapshot: >
  Windows 10 Pro 25H2 build 26200 / i7-13650HX (20 逻辑核) / 32GB 内存 /
  RTX 4060 Laptop 8GB (驱动 616.56, compute cap 8.9) /
  WSL2 2.7.11.0 内核 6.18.33.2-2 / Docker 当前内存上限 ≈20GB
  （`.wslconfig` 已安装核验 memory=20GB / processors=10 / swap=8GB）

raw_data_path: experiments/v1/raw/EXP-V1-003.jsonl
conclusion: >
  首次成功率 85%（17/20），参数可解析率 95%（19/20），平均延迟 2.3s，P95 延迟 4.1s，
  think token 占比 0%（qwen2.5 无 think 输出）。
  判据对照：首次成功率 85% 落入 70–90% 中间区间；可解析率 95% 达 Pass 线。
  → 处置动作按 docs/p0-decision-model-role.md §四执行（约束解码 + few-shot 复测）。

anomalies: >
  2 次请求返回空 tool_calls 且无错误码（Ollama 静默退化疑似），已单独记录；
  1 次 time_range 参数语义偏差 12%（超出 ±10% 容差），计入参数值不正确。

reproduce_cmd: >
  python scripts/run_v1.py --models qwen2.5:7b --repeat 3 --seed 42
    --num-ctx 8192 --temperature 0.0 --prompt prompts/tool_call_prompt_v1.md
    --out experiments/v1/raw/EXP-V1-003.jsonl
```

---

## 四、空白模板（复制即用）

```yaml
experiment_id: EXP-<验证项>-<三位序号>
date: <YYYY-MM-DD>
phase_item: <V1|V2|V3|V4a|V4b|V5|V6|V7>
purpose: <一句话：本次要回答什么问题>

env_baseline_version: env-baseline-v2

image_model_digests:
  <组件或模型名>: "sha256:<64 位十六进制>"
  <组件或模型名>: "sha256:<64 位十六进制>"

seed: <int>
prompt_version: <文件路径 + 版本>
num_ctx: <int>
temperature: <float>
code_commit: <短 hash 或 dirty-<hash>>

hardware_snapshot: >
  Windows 10 Pro 25H2 build 26200 / i7-13650HX (20 逻辑核) / 32GB 内存 /
  RTX 4060 Laptop 8GB (驱动 616.56, compute cap 8.9) /
  WSL2 2.7.11.0 内核 6.18.33.2-2 / Docker 内存上限 <填实测值>

raw_data_path: experiments/<v>/raw/EXP-<验证项>-<序号>.jsonl
conclusion: >
  <结论摘要；可量化则必须带数字；必须写明对照的是哪条判据（Pass/中间/No-Go）>
anomalies: >
  <异常与偏差；无则写"无">
reproduce_cmd: >
  <可直接粘贴执行的复现命令>
```

---

## 五、配套的"报告引用纪律"

> **纪律（硬性）**：**任何报告的结论必须写明所引用的环境基线版本号**，格式统一为：

```
> 环境基线：env-baseline-v2（见 env/env-baseline-v2.md）
> 关键 digest：qwen2.5:7b layer = sha256:2bada8a7…3730 ｜ milvusdb/milvus:v3.0.0 = sha256:49371c30…5862
```

具体要求：

| # | 要求 | 违反后果 |
|---|---|---|
| 1 | 报告首部必须声明环境基线版本号 | 结论不可比，视为作废 |
| 2 | 报告中出现的组件版本必须与 `docs/prj-ledger-version-lock.md` **完全一致（含 digest）** | **不一致即结论作废**（见 `docs/prj-ledger-version-lock.md` §纪律） |
| 3 | 报告引用的每个数字必须能追溯到某条 `experiment_id` | 视为无法复现 |
| 4 | 使用模拟数据的结论必须附 **局限声明**（见 `docs/p1-spec-data-sources.md` §3.3） | 视为过度声称 |
| 5 | 出现"降级"时必须标注对 `Recall@5`、`P95` 的影响 | 违反"降级必带代价"铁律 |

### 5.1 报告页头模板

```markdown
> **环境基线**：env-baseline-v2
> **验证项**：V1 ｜ **里程碑**：M0.2（✅ 2026-10-08 达成）｜ **实验编号**：`EXP-V1-001 ~ EXP-V1-010`（本地/云端单臂族）与 `EXP-M02-001 ~ EXP-M02-040`（混合形态与前置门族；裁决臂 = `EXP-M02-040`）
> **数据来源**：模拟数据（`synthetic: true`）｜ **局限**：基于模拟数据的初步验证
```

---

## 六、存放与命名

| 项 | 约定 |
|---|---|
| 登记条目存放 | 每条实验登记为一个 markdown 小节，追加在 `experiments/<v>/log.md`（P1 起启用；本阶段可先在报告附录内以同结构登记） |
| 原始数据 | `experiments/<v>/raw/EXP-<验证项>-<序号>.jsonl`（**只增不改**） |
| 汇总表 | `experiments/<v>/summary.csv`（可由脚本重算生成） |
| 断点续跑 | 脚本必须支持从已有 JSONL 跳过已完成条目，续跑后追加，不得清空 |
| 命名补充 | `EXP-<验证项>-<序号>` 的 `<验证项>` 为 V1–V7 时归 `experiments/v{1..7}/`（其中 V4b 归 `experiments/v4b/`）；**P1 专项（R-4 证据归纳，ISS-014）用 `EXP-R4-<序号>`，归 `experiments/r4/`**（不在 V1–V7 枚举内，单独建实验区，见 `docs/p0-spec-gate-criteria.md` §3.7） |

---

## 七、每日开工四条（与 `docs/p0-checklist-daily.md` §一 一致）

- [ ] 今日 V 项的 **Pass / 中间 / No-Go 已定义**（见 `docs/p0-spec-gate-criteria.md`）
- [ ] 实验已按本模板登记（digest / seed / prompt 版本 / commit）
- [ ] 原始数据已落盘 `experiments/**/raw/`（可追溯，含断点续跑）
- [ ] 结论将引用 `env-baseline-v2.md` 版本号

> **四条不满足，不开工。**