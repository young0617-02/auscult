# 文档命名与整理规范（Document Standard）v1

> **层级**：项目级长期有效（跨阶段）｜ **制定日期**：2026-10-08（Phase 0 过闸后首次全量文档整理）
> **适用范围**：仓库内**叙述性 Markdown 文档**（`docs/`、`plan/`、`reports/`、`env/*.md`、`experiments/**/*.md`、`archive/`）
> **不适用**：工程资产目录（`prompts/`、`schemas/`、`evals/`、`configs/`、`docker/`、`protos/`、`scripts/`、`tests/`）与 `experiments/**/raw/` —— 见 §五「不可改写区」
> **当前状态**：🟢 **活动**（本文件是文档命名的唯一事实源；`reports/README.md` §五 与根 `README.md` 均指向此处）

---

## 一、为什么需要这份规范

Phase 0 结束时仓内共 60+ 份 Markdown，三种命名风格并存（`docs/` 用英文 kebab、`plan/` 用中文带空格与全角括号、`reports/` 混用 `v1-report` 与 `status-audit-2026-09-30`），后果在实测中已发生：

| 症状 | 实证 |
|---|---|
| 文件名读不出功能与阶段 | `plan/Phase 0 任务总结.md` 实为**阶段总结**却放在 `plan/`；`reports/v3-auth.md` 内容早已不止「授权」 |
| 版本号语义冲突 | `reports/v1-review-v2/v3/v4` 的后缀是**文档版号**，索引却按「复审轮次」解读，且缺「第三轮」、无 `v1-review-v1` |
| 空格 + 全角括号破坏 shell / glob | 3 份带空格、2 份带 `（）` 的文件名在 Git Bash 与 PowerShell 下均需引号包裹 |
| 路径被缩写致断链 | CHANGELOG 等 11 个文件里写着 `plan/H15-...md`（省略号缩写），**从未指向真实路径** |
| 改名/搬运后引用失联 | 整理前 `reports/` 有 3 份文件零引用（孤儿），索引漏登记 3 行 |

**本规范的目标**：只看文件名即可判断「谁在什么阶段、做什么用途、是否仍是当前口径」。

---

## 二、命名规则

```
<阶段>-<类型>-<主题>[-<日期>].md
```

1. **全小写 ASCII + 连字符**；禁止空格、全角括号、中文文件名。中文标题写在文件的一级标题里。
2. **阶段**（必填）：`p0` = Phase 0 技术验证与范围锁定（已过闸）｜`p1` = Phase 1 数据接入与知识库构建｜`prj` = 跨阶段长期有效（台账、模板、项目级规范）。
3. **类型**（必填，只能从下表选取）：

| 类型 | 含义 | 例 |
|---|---|---|
| `plan` | 开发/执行计划（尚未执行或进行中） | `p1-plan-detailed.md` |
| `design` | 方案与架构设计 | `p0-design-refusal-gate-decoupling.md` |
| `spec` | 规范、判据、约束（**权威口径**） | `p0-spec-gate-criteria.md` |
| `decision` | 决策与裁决记录 | `p0-decision-checkpoint.md` |
| `report` | 单项验证/专项实测报告 | `p0-report-v1-tool-call.md` |
| `analysis` | 离线量化与影响分析（多为零调用） | `p0-analysis-iss036-tier-split-2026-10-06.md` |
| `audit` | 审计与状态核查 | `p0-audit-status-2026-10-07.md` |
| `review` | 口径/判据复审记录 | `p0-review-v1-criteria-r3.md` |
| `gate` | 门禁与过闸裁决 | `p0-gate-m02-verdict-2026-10-08.md` |
| `summary` | 阶段/项目总结与全景 | `p0-summary-project-2026-09-29.md` |
| `handover` | 阶段移交 | `p0-handover-p1.md` |
| `checklist` | 勾选清单 | `p0-checklist-daily.md` |
| `template` | 登记模板 | `prj-template-experiment-log.md` |
| `ledger` | 台账（逐条追加、只增不删） | `prj-ledger-risk-register.md` |

4. **日期规则**：**一次性快照**（报告、审计、裁决、总结）**必须**带 `-YYYY-MM-DD`；**活文档**（台账、规范、模板、计划、索引）**不带**日期，改在文件头写「**最近更新**：YYYY-MM-DD」。
5. **复审记录的版号**：`r<N>` 表示**第 N 份复审记录文件**，与文档自身的修订次数无关；`r1` 位置由主报告占用时**不补空文件**，靠 `reports/README.md` §一 的对照说明解释（现状：`r2`=第一轮、`r3`=第二轮（F1–F6）、`r4`=第四轮（H8），**第三轮无独立文件**）。

---

## 三、文档状态标记（文件头必填一项）

| 标记 | 含义 | 允许的正文 |
|---|---|---|
| 🟢 **活动** | 当前口径，读者可据此行动 | 必须写「最近更新」日期；判定须与 `docs/p0-spec-gate-criteria.md` §六 一致 |
| 🟡 **时点快照 / 历史留痕** | 已被取代，仅供审计追溯 | 首行加横幅：判定所属时点 + 取代它的文件；**正文结论一字不改** |
| 🔵 **冻结** | FROZEN 资产、不可变原始记录 | 不得编辑；引用时注明冻结时点 |

> **纪律**：结论一经判定**不得静默改写**。改口径 = 追加「修订记录」行 + 必要时新增文件；旧文件转 🟡 并加横幅。此规则沿用 `reports/README.md` §二 三态与 `docs/p0-handover-p1.md` 的既有纪律，本文件不新增例外。

---

## 四、目录职责

| 目录 | 只放什么 | 命名规则 |
|---|---|---|
| `docs/` | 规范、判据、台账、决策、模板、移交 | §二 全规则 |
| `plan/` | **尚未执行或进行中**的计划与设计 | §2 规则；已执行完的阶段总结**移出**至 `reports/` |
| `reports/` | 实测报告、审计、裁决、总结、复审 | §2 规则 + 快照必带日期 |
| `reports/daily/` | 每日状态记录 | 沿用 `D<n>-status.md`（`n ∈ 1..10`，目录已表明阶段切片） |
| `env/` | 环境与端口基线 | **例外**：沿用 `env-baseline-v<N>.md`、`ports.md`（版本后缀即状态，v2 为唯一事实源，v1 留档） |
| `experiments/` | 实验登记（`EXP-*.md`）与 `raw/` 原始数据 | 实验 ID 命名，**不由本规范重命名**（与 `raw/` 一一对应） |
| `archive/` | **与项目技术验证无关**的个人/外部材料 | `archive/<类别>/<kebab>-<日期>.md`，须在 `reports/README.md` 标注「非项目产物」 |

根级 `README.md`（项目入口）与 `CHANGELOG.md`（变更日志）**保留标准名**，不加前缀。

---

## 五、不可改写区（文档整理不得触碰）

| 路径 | 原因 | 整理时的处置 |
|---|---|---|
| `experiments/**/raw/**` | 原始数据**只增不改**；内含当时文档路径 | 保留历史路径，**允许出现旧文件名**（3 处，见 §七残留） |
| `prompts/**` | 实验输入；正文含逐字发送的 System Prompt 代码块（`llm_adapter.load_system_prompt` 按代码块抽取），改动即污染实验语义 | 不改写，仅在新文档中以新名指代 |
| `schemas/**` | `tools_v1.json` **FROZEN**，`change_policy` 要求任何修改须升版 | 同上（其 `change_policy` 串内提及 `version-lock.md`，保留） |
| `evals/**`、`configs/**`、`docker/**`、`protos/**` | 用例集 / 部署与编译资产，属可复现链路 | 同上 |
| `env/cloud.json` | 含 API key，且被 `.gitignore` 排除 | **不读写内容**；其中 2 处旧文档路径保留（`docs/role-decision.md`、`docs/version-lock.md`） |

> **引用纪律**：文档内引用一律写**完整相对路径 + `.md`**（如 `docs/p0-spec-gate-criteria.md` §3.1.3），**禁止省略号缩写**（`plan/H15-...md` 这类写法已造成 23 处断链，本次已全部展开）。

---

## 六、全量重命名映射表（2026-10-08 执行，共 47 项）

> 本表是**旧名 → 新名**的唯一对照入口；历史文件（`reports/p0-audit-status-*`、`experiments/v1/EXP-*`、`CHANGELOG.md` 早期条目）中出现的旧名**属当时记录，不改写**，需定位文件时回查本表。

### 6.1 `docs/`（15 份重命名 + 1 份新增）

| 旧名 | 新名 | 用途 | 阶段 | 状态 |
|---|---|---|---|---|
| `docs/gate-criteria.md` | `docs/p0-spec-gate-criteria.md` | **门禁判据总表（权威口径）** | p0 | 🟢 |
| `docs/known-issues.md` | `docs/prj-ledger-known-issues.md` | 已知缺陷台账 ISS-001–037 | prj | 🟢 |
| `docs/risk-register.md` | `docs/prj-ledger-risk-register.md` | 风险登记册 R1–R16 + R-V* | prj | 🟢 |
| `docs/version-lock.md` | `docs/prj-ledger-version-lock.md` | **版本与 digest 唯一事实源** | prj | 🟢 |
| `docs/scope-mvp.md` | `docs/p0-spec-scope-mvp.md` | MVP 范围 / Must 链 13 项 / 停止条件 | p0 | 🟢 |
| `docs/handover-p1.md` | `docs/p0-handover-p1.md` | Phase 0 → Phase 1 移交清单 | p0 | 🟢 |
| `docs/daily-checklist.md` | `docs/p0-checklist-daily.md` | D1–D10 每日勾选 + 里程碑现状 | p0 | 🟢 |
| `docs/checkpoint-decision.md` | `docs/p0-decision-checkpoint.md` | checkpointer 方案裁决（B7 → PG） | p0 | 🟢 |
| `docs/role-decision.md` | `docs/p0-decision-model-role.md` | 模型 → 角色分工决策 | p0 | 🟡 |
| `docs/sparkplug-b-decoder.md` | `docs/p0-design-sparkplug-decoder.md` | 自研 Sparkplug B 解码器设计与实现 | p0 | 🟢 |
| `docs/schema-mapping.md` | `docs/prj-spec-schema-mapping.md` | Sparkplug topic/metric → 超级表/列映射 | prj | 🟢 |
| `docs/review-lifecycle.md` | `docs/prj-spec-review-lifecycle.md` | 人工审核生命周期策略 | prj | 🟢 |
| `docs/labeling-spec-v1.md` | `docs/prj-spec-labeling.md` | 评测集与标注规范 | prj | 🟢 |
| `docs/experiment-log-template.md` | `docs/prj-template-experiment-log.md` | 实验登记模板 | prj | 🟢 |
| `docs/data-sources-v1.md` | `docs/p1-spec-data-sources.md` | 数据来源与授权清单 | p1 | 🟢 |
| — | `docs/prj-spec-document-standard.md` | **本文件**：文档命名与整理规范 | prj | 🟢 |

### 6.2 `plan/`（6 份重命名 + 1 份移入 + 1 份移出）

| 旧名 | 新名 | 用途 | 阶段 | 状态 |
|---|---|---|---|---|
| `plan/Phase 0 详细开发计划（D1-D10 可执行版）.md` | `plan/p0-plan-detailed-d1-d10.md` | Phase 0 计划（**已执行完毕**） | p0 | 🟡 |
| `plan/Phase 1 详细开发计划（数据接入与知识库构建）.md` | `plan/p1-plan-detailed.md` | **Phase 1 计划（唯一仍有效）** | p1 | 🟢 |
| `plan/M02-V1-混合形态方案.md` | `plan/p0-design-m02-hybrid-form.md` | V1 混合形态方案（实测 No-Go，已被取代） | p0 | 🟡 |
| `plan/V1-破局路径方案对比.md` | `plan/p0-design-v1-breakthrough-paths.md` | 破局路径对比与复盘 | p0 | 🟡 |
| `plan/V1-schema-v2-复审建议.md` | `plan/p0-review-schema-v2.md` | Schema 升版复审建议 | p0 | 🟡 |
| `plan/H15-拒止前置门-架构解耦设计.md` | `plan/p0-design-refusal-gate-decoupling.md` | 前置门解耦设计（**已落地**为 `gate_rules.py`/`run_e2e.py`） | p0 | 🟡 |
| `experiments/plans/P1-V4B-CLEANRM.md` | `plan/p1-plan-v4b-cleanrm.md` | V4b 干净机重测计划（**已兑现升 Pass**） | p1 | 🟡 |
| `plan/Phase 0 任务总结.md` | **`reports/p0-summary-phase0-2026-09-30.md`** | 阶段总结 —— **跨目录搬运**（总结不属于 `plan/`） | p0 | 🟡 |

### 6.3 `reports/`（22 份重命名 + 1 份移入 + 3 份转归档）

| 旧名 | 新名 | 用途 | 阶段 | 状态 |
|---|---|---|---|---|
| `reports/P0-summary.md` | `reports/p0-gate-review.md` | **门禁评审合集（M0.6）** | p0 | 🟢 |
| `reports/phase0-m0.2-verdict-2026-10-08.md` | `reports/p0-gate-m02-verdict-2026-10-08.md` | ★ **过闸裁决（今日权威）** | p0 | 🟢 |
| `reports/phase0-closeout-2026-10-07.md` | `reports/p0-gate-closeout-2026-10-07.md` | 10-07 收尾（当时不放行） | p0 | 🟡 |
| `reports/v1-report.md` | `reports/p0-report-v1-tool-call.md` | V1 工具调用主报告 | p0 | 🟡 |
| `reports/v1-review-v2.md` | `reports/p0-review-v1-criteria-r2.md` | V1 口径复审（第一轮） | p0 | 🟡 |
| `reports/v1-review-v3.md` | `reports/p0-review-v1-criteria-r3.md` | V1 口径复审（第二轮 F1–F6） | p0 | 🟡 |
| `reports/v1-review-v4.md` | `reports/p0-review-v1-criteria-r4.md` | H8 考点范围核对（第四轮） | p0 | 🟡 |
| `reports/v1-cases-revision-2026-10-05.md` | `reports/p0-report-v1-cases-revision-2026-10-05.md` | `ISS-029` 路径 B 用例元数据修订 | p0 | 🟡 |
| `reports/v1-refusal-audit-2026-10-06.md` | `reports/p0-audit-v1-refusal-2026-10-06.md` | 拒止/澄清专项 + 泄漏审计 | p0 | 🟡 |
| `reports/h17-single-tool-tier-audit.md` | `reports/p0-audit-v1-single-tool-tier-2026-10-07.md` | 单工具档归因（实验代号 H17 移出文件名） | p0 | 🟡 |
| `reports/iss036-tier-split-analysis.md` | `reports/p0-analysis-iss036-tier-split-2026-10-06.md` | 拆档影响量化 | p0 | 🟡 |
| `reports/v2-report.md` | `reports/p0-report-v2-hybrid-retrieval.md` | V2 混合检索 | p0 | 🟢 |
| `reports/v3-auth.md` | `reports/p0-report-v3-ingest-license.md` | V3 时序接入 + 连接器授权 | p0 | 🟢 |
| `reports/v4b-report.md` | `reports/p0-report-v4b-resources.md` | V4b 资源实测 | p0 | 🟢 |
| `reports/v5-report.md` | `reports/p0-report-v5-checkpoint.md` | V5 checkpoint 可靠性 | p0 | 🟢 |
| `reports/regression-suite-2026-10-06.md` | `reports/p0-report-regression-suite-2026-10-06.md` | 回归套件与 `ISS-030` 关闭 | p0 | 🟢 |
| `reports/vcs-baseline-2026-10-06.md` | `reports/p0-report-vcs-baseline-2026-10-06.md` | Git 基线与密钥防护 | p0 | 🟢 |
| `reports/project-overview.md` | `reports/p0-summary-project-2026-09-28.md` | 全景快照（最早） | p0 | 🟡 |
| `reports/project-summary-2026-09-29.md` | `reports/p0-summary-project-2026-09-29.md` | 全景快照 + 附录 A 不一致清单 | p0 | 🟡 |
| `reports/status-audit-2026-09-30.md` | `reports/p0-audit-status-2026-09-30.md` | 状态审计与文件整理 | p0 | 🟡 |
| `reports/status-audit-2026-10-05.md` | `reports/p0-audit-status-2026-10-05.md` | 状态核查点（H3 收口后） | p0 | 🟡 |
| `reports/status-report-2026-10-07.md` | `reports/p0-audit-status-2026-10-07.md` | 全维度状态报告 | p0 | 🟡 |
| `reports/G2-实测数据填表-2026-10-05.md` | **`archive/personal/g2-measured-data-form-2026-10-05.md`** | 求职素材填表（**非项目技术产物**） | — | 📦 |
| `reports/待填信息问卷-49项-回填-2026-10-05.md` | **`archive/personal/job-questionnaire-49-backfill-2026-10-05.md`** | 求职问卷回填（同上） | — | 📦 |
| `reports/草稿问卷-审阅与回填-2026-10-05.md` | **`archive/personal/draft-questionnaire-review-2026-10-05.md`** | 简历草稿审阅（同上） | — | 📦 |

**未改名**：`README.md`（根与 `reports/`、`reports/daily/` 三级索引，标准名保留）、`CHANGELOG.md`、`reports/daily/D1-status.md`、`env/env-baseline-v{1,2}.md`、`env/ports.md`、`experiments/**/*.md`。

### 6.4 `docs/` 阶段移交清单命名规范化（2026-10-10 执行，3 项）

| 旧名 | 新名 | 用途 | 阶段 | 状态 |
|---|---|---|---|---|
| `docs/handover-p4.md` | `docs/p3-handover-p4.md` | Phase 3 → Phase 4 移交清单 | p3 | 🟢 |
| `docs/handover-p5.md` | `docs/p4-handover-p5.md` | Phase 4 → Phase 5 移交清单 | p4 | 🟢 |
| `docs/handover-p6.md` | `docs/p5-handover-p6.md` | Phase 5 → Phase 6 移交清单 | p5 | 🟢 |

### 6.5 收口后命名纠错（2026-10-10 执行，2 项）

> 背景：两项均为 2026-10-10 Phase 6 收口当日新增的文件，**未纳入 2026-10-08 的 §6.1–§6.4 全量整理**，故沿用了大写 `P` 的旧习惯名（违反 §二.1「全小写 ASCII」与 §二.2 阶段段必填）。

| 旧名 | 新名 | 用途 | 阶段 | 状态 |
|---|---|---|---|---|
| `docs/P6-closure.md` | `docs/p6-gate-closure-2026-10-10.md` | **Phase 6 收口唯一凭据（M6.4）** | p6 | 🟢 |
| `reports/P5-summary.md` | `reports/p5-summary-phase5-2026-10-10.md` | Phase 5 验收汇总（D15 / M5.4） | p5 | 🟢 |

> 两项均走 `git mv` + 全仓引用改写（受影响 4 个文件：两份 plan、`docs/prj-spec-document-standard.md`、被改名文件自身）；**正文结论一字未改**，仅在各自「修订记录」追加一行。

---

## 七、本次整理的残留与已知问题（不隐藏）

| # | 残留 | 影响 | 建议 |
|---|---|---|---|
| 1 | `experiments/**/raw/` 内 3 处旧路径（`reports/v2-report.md` ×2、`docs/gate-criteria.md` ×1） | 只读历史，点击落空 | 保持不改（不可变纪律）；需要定位时回查 §六 |
| 2 | `prompts/`(8 文件 16 处)、`schemas/`(4 文件)、`configs/`、`docker/`、`protos/`、`env/cloud.json`(2 处) 内仍写旧文件名 | 冻结资产内的注释性引用失效 | 依 §五 不改写；本表即为解释 |
| 3 | **`pytest` 未登记进 `requirements.txt` 与 `docs/prj-ledger-version-lock.md`** | 新机器上「改代码必跑 176 用例回归」不可执行（本机 `.venv` 即无 pytest，实跑于宿主 Python 3.12） | P1 开工前补锁版本并同步两处（已在缺陷台账登记） |
| 4 | 台账表格内**行序倒置**（`prj-ledger-risk-register.md` §六 10-06 之后接 09-30 行；`prj-ledger-known-issues.md` §二 ISS-037 排在 035/036 之前） | 阅读时需按日期重排 | **未重排**——改行序等于改动既有台账行，留待专门一次带修订说明的整理 |
| 5 | 历史正文中的旧术语「**无效拒绝**」大量保留（各 plan/报告合计 26+ 处） | 与现行「拒止 / 澄清」两档并存 | 依 `ISS-036` 只在新文档统一术语，历史行**不追改**（改等于抹掉拆档前的判据史） |
| 6 | `env/ports.md` 为 2026-09-23 快照，晚于 T1.1 的 `.wslconfig` 安装却未重采 | 端口冻结基线与 v2 环境基线时点不一致 | 已在文件头加时点声明；P1 起容器前重采并登记 `env/p1-audit-ports-<日期>.md` |
| 7 | 新文档写入后，`plan/`、`docs/`、`reports/` 计数已变（本规范 §六 为权威清单） | 根 README 与索引需同步 | 已同步（`reports/README.md` §一、根 `README.md` 目录结构） |
| 8 | **`docs/pitch.md` 不带阶段与类型前缀**（演示解说词，对外材料） | 与 §二 命名规则不符 | **保留不改**：演示/汇报场景需可读短名，已知偏差；若日后拆分为技术文档则按 §二 正名 |

---

## 八、新增 / 改名文档的操作清单

1. 按 §二 定名（阶段 + 类型 + 主题 [+ 日期]，ASCII kebab）。
2. 文件头写：**层级/阶段、对应验证项与里程碑、状态（🟢/🟡/🔵）、最近更新**。
3. 登记进对应索引：`reports/` → `reports/README.md` §一；`docs/`、`plan/` → 根 `README.md` 目录结构。
4. 引用他人文档用完整路径 + `.md`，不用省略号缩写。
5. 改名 = 走 `git mv` + **全仓改写引用**（排除 §五 不可改写区）+ 在本文件 §六 追加一行映射 + 追加「修订记录」。
6. 收尾跑 `python -m pytest tests/ -q`（文档改动亦会触及 `scripts/`、`tests/` 里的路径字符串）。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | 初始建立：Phase 0 过闸后全量文档整理（47 项重命名 / 搬运、1737 处引用改写）沉淀为本规范；含命名规则、状态三态、目录职责、不可改写区、全量映射表与 7 条残留问题 | 全仓文档 |
| 2026-10-10 | 单人（本人） | Phase 6 D1–D5 文档收口：P3/P4/P5 移交清单命名规范化（旧名→新名映射，含全仓引用改写） | 3 项 `git mv`（`docs/handover-p4.md`→`docs/p3-handover-p4.md`、`docs/handover-p5.md`→`docs/p4-handover-p5.md`、`docs/handover-p6.md`→`docs/p5-handover-p6.md`）；受影响 10 个文件 29 处引用改写（`CHANGELOG.md`、`README.md`、`docs/prj-design-architecture.md`、`app/graph/build.py`、`app/api/runner.py`、3 份 plan、`reports/p3-summary.md`、`reports/P5-summary.md`） |
| 2026-10-10 | 单人（本人） | **Phase 6 收口后命名纠错**：2 项 `git mv`（`docs/P6-closure.md`→`docs/p6-gate-closure-2026-10-10.md`、`reports/P5-summary.md`→`reports/p5-summary-phase5-2026-10-10.md`）+ 全仓引用改写 | 新增 §6.5 映射表；§七 新增残留 8（`docs/pitch.md` 保留可读短名的已知偏差）；受影响 4 个文件（两份 Phase 5/6 计划、本文件、被改名文件自身） |
