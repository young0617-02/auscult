# 文档一致性同步与命名整理核查报告 · 2026-10-08

> **报告状态声明**：① **已实测** —— 本报告中的计数、测试结果、git 状态均来自本机当次真实执行（`python -m pytest tests/ -q`、`git status`、`git diff --cached --name-status -M`、全仓引用扫描脚本）；不含任何估算值。
> **对应阶段**：Phase 0 已过闸 → Phase 1 启动前的**文档治理**（不产生新的验证结论）
> **触发**：用户要求「检查项目完整状态、梳理并同步更新所有文档、统一命名规则、输出状态概述 / 清单 / 命名规范 / 不一致与修正」
> **授权**：用户于 2026-10-08 选择 **① 全量重命名并同步改写所有引用 ② 历史报告只加「历史留痕」横幅 + 修订记录（正文不改）③ 3 份非项目文档移出 `reports/` 单独归档**
> **命名规范正文**：`docs/prj-spec-document-standard.md`（本报告的 §四 为其摘要）

---

## 一、项目当前状态概述

| 维度 | 状态 |
|---|---|
| 阶段 | **Phase 0（技术验证与范围锁定）已完成并过闸**；`M0.6` 于 **2026-10-08 放行** → Phase 1（数据接入与知识库构建）可启动 |
| 里程碑 | M0.1 ✅ / **M0.2 ✅（10-08）** / M0.3 ✅ / M0.4 ✅ / M0.5 ✅ / **M0.6 ✅ 放行** |
| M0.2 裁决依据 | `docs/p0-spec-gate-criteria.md` **§3.1.3「同日多轮聚合口径」**（经用户授权，档线一字未改）：`EXP-M02-040` 同日 3 轮、合并 225 样本 → 单工具 92.6% / 参数校验 100% / 多工具 75.0% / 多轮 100% / 拒止 100% / 澄清 100% → **整体 Pass**（合并首次成功率 0.9422） |
| 验证项 | V1 **Pass** ／ V2 **Pass**（混合 Recall@5 0.91）／ V3 **封板定稿**（四类边界 4/4、`query_sensor` P95 ≈26.2 ms）／ V4a **Pass**／ V4b **Pass**（干净机 17.89 GB ≤ 24 GB）／ V5 **Pass**（PG 路线、296 KB/thread）／ V6、V7 **结构 Pass** |
| **残余风险（放行不等于风险消失）** | ① 单轮口径仍不稳（R1 单轮仍判中间区间）；② 多工具档余量仅 **5.0 pp**（27/36，再跌 2 个样本即破线）；③ 云端结论**依赖 provider 版本、不可 digest 化**（`ISS-028` / `R-V1-10`）→ 三项列入 P1 持续监控，改动前后须按同口径复测 |
| 缺陷台账 | ISS-001 – ISS-037 全部有状态；未闭环 = `ISS-028`（缓解非消除）、`ISS-037`（已缓解）+ 本次新登记的 **`pytest` 依赖未锁** |
| 工程健康 | `pytest` **176 passed**（离线 0.34 s）；16/22 个脚本含 `--selftest`；git 工作树整理前干净（基线 `7e78dfa`） |
| Must 链 | 13 项中 **3 项已实测通过 / 6 项部分实测 / 4 项未执行**；端到端完整链路演示**尚未执行**（→ P1） |

---

## 二、文档清单（用途 · 所属阶段 · 状态）

> 状态标记：🟢 活动（当前口径，可据此行动）｜🟡 时点快照（已被取代，仅审计留痕）｜🔵 冻结（不可变资产）。
> **旧名 → 新名的完整映射见 `docs/prj-spec-document-standard.md` §六**（48 项），此处只给现状。

### 2.1 `docs/` — 16 份（治理与规范）

| 文件 | 用途 | 阶段 | 状态 |
|---|---|---|---|
| `p0-spec-gate-criteria.md` | **门禁判据总表**（M0.1–M0.6、§3.1.1 分档 / §3.1.2 职责拆分 / §3.1.3 聚合口径） | p0 | 🟢 |
| `prj-ledger-known-issues.md` | 已知缺陷台账（ISS-001–037） | prj | 🟢 |
| `prj-ledger-risk-register.md` | 风险登记册（R1–R16 + R-V1-9~14 等） | prj | 🟢 |
| `prj-ledger-version-lock.md` | **版本与 digest 唯一事实源** | prj | 🟢 |
| `p0-spec-scope-mvp.md` | MVP 范围 / Must 链 13 项 / 停止条件 S1–S3 / 质量目标 Q1–Q11 | p0 | 🟢 |
| `p0-handover-p1.md` | **P1 移交清单**（交付物 / 遗留项 / 核对表） | p0 | 🟢 |
| `p0-checklist-daily.md` | D1–D10 每日勾选 + 里程碑现状表 | p0 | 🟢 |
| `prj-spec-document-standard.md` | **文档命名与整理规范（本次新建）** | prj | 🟢 |
| `prj-spec-review-lifecycle.md` | 人工审核生命周期策略（超时/死锁/并发/幂等） | prj | 🟢 |
| `prj-spec-schema-mapping.md` | Sparkplug topic/metric → 超级表/列映射 | prj | 🟢 |
| `prj-spec-labeling.md` | 评测集与标注规范（V7） | prj | 🟢 |
| `prj-template-experiment-log.md` | 实验登记模板 | prj | 🟢 |
| `p1-spec-data-sources.md` | 数据来源与授权清单 | p1 | 🟢 |
| `p0-decision-checkpoint.md` | checkpointer 方案裁决（B7 → PG） | p0 | 🟢 |
| `p0-design-sparkplug-decoder.md` | 自研 Sparkplug B 解码器设计与实现记录 | p0 | 🟢 |
| `p0-decision-model-role.md` | 模型 → 角色分工决策 | p0 | 🟡（含 No-Go 时点表述，已加横幅） |

### 2.2 `plan/` — 7 份（仅 1 份仍有效）

| 文件 | 用途 | 阶段 | 状态 |
|---|---|---|---|
| `p1-plan-detailed.md` | **Phase 1 详细开发计划（唯一待执行）**，2026-10-08 已更正前置物与选型 | p1 | 🟢 |
| `p1-plan-v4b-cleanrm.md` | V4b 干净机重测计划（**已兑现升 Pass**） | p1 | 🟡 |
| `p0-plan-detailed-d1-d10.md` | Phase 0 计划（D1–D10 已执行完毕） | p0 | 🟡 |
| `p0-design-refusal-gate-decoupling.md` | 拒止前置门解耦设计（已落地为 `gate_rules.py`/`run_e2e.py`） | p0 | 🟡 |
| `p0-design-v1-breakthrough-paths.md` | 破局路径对比与复盘 | p0 | 🟡 |
| `p0-design-m02-hybrid-form.md` | V1 混合形态方案（实测 No-Go，已被取代） | p0 | 🟡 |
| `p0-review-schema-v2.md` | Schema 升版复审建议 | p0 | 🟡 |

### 2.3 `reports/` — 25 份（含本索引 `README.md`）+ `daily/` 2 份

| 组 | 文件 | 阶段 | 状态 |
|---|---|---|---|
| **权威** | `p0-gate-m02-verdict-2026-10-08.md`（过闸裁决）、`p0-gate-review.md`（门禁合集·决策34） | p0 | 🟢 |
| 五项验证 | `p0-report-v1-tool-call`（🟡 No-Go 时点）／ `v2-hybrid-retrieval`／ `v3-ingest-license`／ `v4b-resources`／ `v5-checkpoint` | p0 | 🟢×4 + 🟡×1 |
| V1 口径复审 | `p0-review-v1-criteria-r2 / r3 / r4`（**rN = 文件序号 ≠ 复审轮次**） | p0 | 🟡 |
| 专项与分析 | `p0-report-v1-cases-revision-2026-10-05`、`p0-analysis-iss036-tier-split-2026-10-06`、`p0-audit-v1-refusal-2026-10-06`、`p0-audit-v1-single-tool-tier-2026-10-07` | p0 | 🟡 |
| 状态审计 | `p0-audit-status-2026-09-30 / -10-05 / -10-07`、`p0-audit-doc-sync-2026-10-08`（本文件） | p0 | 🟡×3 + 🟢×1 |
| 工程侧 | `p0-report-regression-suite-2026-10-06`、`p0-report-vcs-baseline-2026-10-06` | p0 | 🟢 |
| 总结快照 | `p0-summary-project-2026-09-28 / -09-29`、`p0-summary-phase0-2026-09-30`（自 `plan/` 移入） | p0 | 🟡 |
| 收尾留档 | `p0-gate-closeout-2026-10-07`（当时判「不放行」） | p0 | 🟡 |
| 日报 | `daily/README.md`、`daily/D1-status.md` | p0 | 🟡（历史） |
| 索引 | `README.md` | prj | 🟢 |

### 2.4 其他目录

| 文件 | 用途 | 状态 |
|---|---|---|
| `env/env-baseline-v2.md` | **环境唯一事实源**（v2，2026-09-24 采集；10-08 复核并消除与版本锁的冲突） | 🟢 |
| `env/env-baseline-v1.md` | 历史环境基线（自标作废） | 🟡 |
| `env/ports.md` | 端口检查快照（10-08 加时点声明：09-23 早于 `.wslconfig` 安装、PID 已失效） | 🟡 |
| `experiments/` — **30 份**实验登记 `EXP-*.md`（与 `raw/` 对应；另有 7 份记录位于 `raw/` 内，随原始数据留档，合计 37 个 `.md`） | 🔵 |
| `experiments/**/raw/`（135 文件） | 原始实测数据 | 🔵 只增不改 |
| `archive/personal/*`（3 份） | 求职素材（**非项目技术产物**，2026-10-08 移出 `reports/`），见 `archive/README.md` | 📦 |
| `prompts/`(11)、`schemas/`(5)、`evals/`(11 jsonl)、`configs/`、`docker/`、`protos/` | 实验输入与部署资产（命名规则单列，本次不改写） | 🔵/🟢 |

---

## 三、本次修正的不一致问题（分类 · 前 → 后）

### A 类：活文档断言「当前状态」错误（12 处，最高危）

| # | 位置 | 原（错误/滞后） | 修正后 |
|---|---|---|---|
| A1 | `CHANGELOG.md` `[未发布]` 段（位于权威 10-08 条目**之上**） | 「M0.6 **未放行**；M0.2 仍为唯一阻塞」 | 「M0.1–M0.5 全部达成、**M0.6 已于 10-08 放行**」，并保留原判定为划除线留痕 + 补列三项残余风险 |
| A2 | `docs/p0-spec-gate-criteria.md` §3.1.2 必附声明③ ↔ §3.1.3 | 同文内「M0.2 仍为中间区间、M0.6 仍不放行」与新口径并存、无时点标注 | 加**时点限定**（该句为 10-07 判定，已由 §3.1.3 取代）；§六 阻塞说明改为划除线 + 现状 |
| A3 | `docs/p0-checklist-daily.md` §4.3（每日入口） | M0.2「未达成（V1 No-Go）」、M0.6「未放行」 | M0.2 ✅ 达成、M0.6 ✅ 放行，并保留 09-30 No-Go → 10-07 中间区间的判定链 |
| A4 | `docs/p0-handover-p1.md`（P1 直接照此开工） | §5.1 M0.2 ❌ / M0.6 ❌；§5.2 V1「已实测 → No-Go」 | 均改为过闸结论 + 完整处置链留痕（P5/P6/P7 → ISS-029/035/036 → H21 → H22） |
| A5 | `docs/prj-ledger-known-issues.md` 头部 | 「最近更新 2026-10-06」+「`ISS-036` ⏳ 未处置·须授权」**与主表「已修复」互斥** | 头部改为 10-08，`ISS-035/036/037` 状态与主表对齐 |
| A6 | `docs/prj-ledger-risk-register.md` §五 | `ISS-032`「处置待授权」（实际 10-06 已处置）、`ISS-035`「未处置·须授权」（实际 10-07 已处置）；**缺 `ISS-030/031/033/034/037` 行**；全册无门禁状态 | 三处状态更正 + 补 5 条处置行 + 新增「门禁状态」行；`R-V1-13` 转「已处置」 |
| A7 | `docs/p0-spec-scope-mvp.md` 头部 + §四 | 「实测状态栏一律为框架就绪、实测未执行」；S1/S2「未达成（三项均【待实测填入】）」 | 头部改为已逐项回填；**S1 未达成但给出 3/6/4 的真实分布**、S2 达成（0.91 / 9.48 ms / 0.9422）、S3 达成并说明版本锁 §三 是按设计保留的待锁定清单 |
| A8 | `docs/p0-spec-scope-mvp.md` §七 Q1–Q11 | **11 项质量目标全部仍是【待实测填入】**（尽管 Q1/Q2/Q6/Q8 早已实测） | Q1 0.9100、Q2 0.9300、Q6 9.48 ms（并披露同表稠密单路 2061.9 ms 超线）、Q8 六档全 Pass 回填；Q3/Q7/Q10/Q11 **如实标注未实测转 P1**，Q9 标注「单链路已验、统计量未做」 |
| A9 | `docs/prj-spec-review-lifecycle.md` §5.4 | 4 个「🔲 待 D7 填入」（V5 早已 Pass） | 3 项按 `EXP-V5-003-T` 回填 Pass；**「多 worker」如实标注 P0 未独立实测 → 转 P1**，并保留「P0 以文件存储模拟 PG 唯一索引」声明 |
| A10 | `docs/p0-decision-checkpoint.md` §六/§九 | 「待定基线 / 待定上限」+ DoD **9 项全未勾** +「未填则不得视为定稿」 | 基线已定（296 KB/thread）；DoD 按 V5 实测勾选并声明文档为定稿 |
| A11 | `env/env-baseline-v2.md` §八（**环境唯一事实源**） | 「建议 `ollama pull` 升级到 0.34.3 并重新登记 digest」——**与 U-04/`ISS-009` 已裁决「锁定 0.34.2 不升级」直接冲突**，被 36 个文件引用 | 该行标注**作废**并给出裁决依据与「若升级须按纪律升版 + 同口径复测」的条件；另更正「本机无 Neo4j/TDengine/Mosquitto」（已拉取并锁 digest）与「GPU 直通未验证」（已裁决不需要） |
| A12 | `README.md` V1 行「完整全景」指针 | 把 `project-summary-2026-09-29` 称「最新全景」（其内 V1 仍 No-Go、V4b 中间区间） | 改为 **10-08 裁决报告 = 今日权威**，三份全景统一标 🟡 历史快照 |

### B 类：计数与实况不符（18 处）

| 项 | 旧写法（分散在 README / reports 索引 / 移交清单 / CHANGELOG / 阶段总结） | 实况（本次实测） |
|---|---|---|
| 回归用例数 | 119 / 170 / 106 / 149 | **176**（`pytest` rc=0，0.34 s） |
| `docs/` 份数 | 13 / 15 | **16** |
| `reports/` 份数 | 「12 份报告」 | **26 + `daily/` 2** |
| 脚本数与自检覆盖 | 「18 个 Python 脚本（12 个含 `--selftest`，实测 12/12 PASS）」/「21 个脚本中 15 个已覆盖」 | **22 个 `.py`（16 个含 `--selftest`）+ 2 个 `.ps1`**；README 自检清单已补齐 16 个（含 `gate_rules`/`refusal_gate`/`run_e2e`/`aggregate_runs`） |
| 缺陷范围 | 「ISS-001 – ISS-018」（README 迭代纪律）/「ISS-001 – ISS-026」（移交清单 2 处） | **ISS-001 – ISS-037** |
| 活动 Schema/Prompt | 移交清单只列 `tools_v1.json` + `tool_call_prompt_v1.md` | **`tools_v4.json` + `tool_call_prompt_v4.md`**（v5 否决、v2 含泄漏禁用，已并列说明） |
| 执行器清单 | 移交清单只列 5 个脚本 | 22 个，且标注**权威入口** = `run_e2e.py` + `aggregate_runs.py` |
| 评测集 | 只列 6 项 | **11 个 `.jsonl` + 语料**（补无泄漏迁移集、对抗集、probe 集与 3 份归档原件） |
| 实验登记数 | 全景旧件与 README 口径不一 | **30 份非 raw 登记 + 7 份 raw 内记录 = 37 个 `.md`**（本次以 `git ls-files` 复核后统一） |
| 实验编号范围 | 模板写「EXP-V1-001 ~ 012」 | 双族：`EXP-V1-001~010` + `EXP-M02-001~040`（裁决臂 `-040`），并在索引中声明**两套不可直接比较** |

### C 类：死引用 / 死路径 / 错误章节号

| # | 位置 | 问题 | 处置 |
|---|---|---|---|
| C1 | `CHANGELOG.md`、`experiments/v1/EXP-M02-*.md`（5 份）、`reports/p0-gate-review.md`、`scripts/refusal_gate.py`、`tests/test_refusal_gate.py` 等 **11 个文件** | 写作 `plan/H15-...md`（**省略号缩写，从未指向任何真实文件**）共 **23 处** | 全部展开为真实路径 |
| C2 | `docs/p0-handover-p1.md`、`experiments/plans/`、`reports/p0-report-v4b-resources.md` 共 **5 处** | 引用 `p0-spec-gate-criteria §3.1.5` —— **该节不存在**（V4 门禁线实为 §3.4） | 全部改指 **§3.4** 并注明原误写 |
| C3 | `docs/p1-spec-data-sources.md` | `scripts/sim_sparkplug.py`、`scripts/sim_alarm_replay.py` 被读成「缺文件」 | 标注**等价能力已由 `spb_simulator.py` / `run_v3_alert.py` 实现并过自检**，P1 脚本为正式化而非从零 |
| C4 | `docs/prj-spec-labeling.md` | 引用 `scripts/kappa.py`、`experiments/v7/log.md` —— **两者均不存在** | 如实标注：Kappa 一致性检验 P0 **未执行**（单人标注、无第二标注人）、`experiments/v7/` **未创建** → 均转 P1；并把 V7 里程碑归属由 M0.2 更正为 M0.5 |
| C5 | `docs/prj-spec-schema-mapping.md` | 头部「授权边界与解码路径**待 T1.9 结论**」与同文 §290「已定稿（2026-09-24）」**自相矛盾** | 头部改为已定稿（V3 已封板） |
| C6 | `docs/p0-design-sparkplug-decoder.md` | 「paho-mqtt / taospy / grpcio-tools **待装**」（实际已锁进 `requirements.txt`）、「真实灌数填报待 D4」（实际 V3 已封板） | 两处按实况更正 |
| C7 | `plan/p1-plan-detailed.md` | 前置物指向 `tools_v1.json` 与 `env-baseline-v1.md`（**与「唯一事实源」相反**）；接入方案仍写 **taosX**（已裁决不采用）；「降级预案 + 工期 +2 天」（已消化）；Broker EMQX「未裁决」；**三元组抽取「优先本地 `qwen2.5:7b` + Schema 约束」与 M0.2 结论相悖**（本地 7B 结构化输出最弱）；风险项 P1-R9「Redis 驱逐 checkpoint」（已切 PG） | 6 处逐条更正并保留原口径（划除线），头部新增「启动前必读」列出全部更正 |

### D 类：命名与目录问题

| # | 问题 | 处置 |
|---|---|---|
| D1 | **48 份文件**命名不体现功能/阶段：3 份含空格、2 份含全角括号（shell/glob 需引号）、`v1-report`/`v3-auth`/`P0-summary` 读不出类型 | 全部按 `<阶段>-<类型>-<主题>[-<日期>]` 改名（`git mv`，git 判定 **R100** = 改名时代码逐字节一致） |
| D2 | 文档放错目录：`plan/Phase 0 任务总结.md`（总结混在计划里）、`experiments/plans/P1-V4B-CLEANRM.md`（计划混在数据里） | 分别搬运至 `reports/p0-summary-phase0-2026-09-30.md`、`plan/p1-plan-v4b-cleanrm.md`（空目录 `experiments/plans/` 移除） |
| D3 | `reports/v1-review-v2/v3/v4` 的 `vN` 是**文档版号**，索引却按「复审轮次」解读，且缺第三轮、无 `v1-review-v1` | 改名为 `p0-review-v1-criteria-r2/r3/r4`，并在 `reports/README.md` §一 与规范 §二.5 明确「**rN = 文件序号 ≠ 轮次**」及轮次对照 |
| D4 | `h17-single-tool-tier-audit` 把实验代号写进文件名（与 `EXP-*` 体系混淆） | 改为 `p0-audit-v1-single-tool-tier-2026-10-07.md`；实验代号保留在正文与 CHANGELOG |
| D5 | `reports/` 混入 3 份**非项目技术产物**（求职素材，含 `<PRIVATE_VAULT>/...` 外部路径、全仓零引用） | 移至 `archive/personal/` 并 ASCII 化改名；新建 `archive/README.md` 说明用途 + **提醒「数据转录自 10-05 时点、V1 当时仍判 No-Go，对外使用前须按 10-08 新结论重核」** |
| D6 | 旧索引约定的 `project-summary-YYYY-MM-DD.md` / `status-audit-YYYY-MM-DD.md` 范式与新规则冲突 | `reports/README.md` §五 改为指向命名规范，旧范式声明作废 |

### E 类：索引与可追溯性缺口

| # | 问题 | 处置 |
|---|---|---|
| E1 | `reports/README.md` §一 **漏登 12 份**（09-30 之后新增的报告从未登记，包括 10-08 过闸裁决报告的若干同批件）；且 3 份实际存在的文件（求职素材）根本不在索引体系内 | 重建 §一：27 行全量登记 + 新增「阶段」列；补登 `p0-summary-phase0-2026-09-30` 与本文件；归档件单列说明行 |
| E2 | §一 中 V1/V2/V3/V4b/V5 五份报告的状态列仍写「**8 项指标实测待填入 / 待执行 / 存在前置阻塞项**」，而 §六 同文写「V1–V5 均已实测」——**索引自身前后矛盾** | 五行全部改为「已实测 + 实测值 + 🟡 时点标注」 |
| E3 | §六 全局摘要停留在 09-30 口径（18 个脚本 / 12 自检 / V2「条件Pass」/ M0.5 未列全） | 按实况重写，并新增「回归测试」「归档」两个维度 |
| E4 | **8 份文档无修订记录表**（含被引用最多的 `known-issues`、`checkpoint-decision`、`data-sources`、`labeling`、`sparkplug`、`project-overview` 等） | 为 `prj-ledger-known-issues.md`、`p0-decision-checkpoint.md`、`p1-plan-detailed.md` **新建**修订记录表；其余按本次实际触及的文件逐一追加 |
| E5 | 判据文档修订记录止于 09-30，**10-05 ~ 10-08 的口径演进（拆档、职责拆分、聚合口径）未登记** | 补登 4 条修订行（标注「补登」，不冒充当时记录） |

### F 类：事实源之间的冲突（跨文档一致性）

| # | 冲突 | 裁定 |
|---|---|---|
| F1 | `env-baseline-v2`（环境唯一事实源）建议升 Ollama 0.34.3 ↔ `prj-ledger-version-lock`（版本唯一事实源）锁定 0.34.2 | 以**版本锁**为准（U-04 裁决），环境基线该行作废 |
| F2 | `plan/Phase 0 任务总结` 同文既写 V4b「17.89 GB Pass」又写「仍为中间区间未到 Pass」 | 以 `p0-report-v4b-resources` §12.5 为准；总结件加 🟡 横幅 |
| F3 | `p0-report-v4b-resources` §〇 摘要判「中间区间 / M0.5 部分达成」↔ 本文 §12.5 判 Pass | 正文不改，加横幅声明「以 §12.5 为准」 |
| F4 | `p0-review-v1-criteria-r4` L14 写「22 字段」↔ L63/L132 写「19 字段」 | **未改动**（属该报告内部数字分歧，需重新核对 `evals/v1_cases.jsonl` 修订统计才能定谁对）→ 列入 §五「待确认」 |
| F5 | 移交清单 / 缺陷册 / 风险册对 ISS 范围各说各话（018 / 026 / 037） | 统一为 **ISS-001 – ISS-037**（以缺陷册主表为准） |

### G 类：本次新发现的实质缺口（非文档笔误）

| # | 缺口 | 证据 | 建议 |
|---|---|---|---|
| G1 | **`pytest` 既不在 `requirements.txt` 也不在版本锁**，但 README 与迭代纪律把「改代码必跑回归」列为硬要求 | `grep -i pytest requirements.txt` 无匹配；`.venv/Scripts/python.exe -m pytest` → `No module named pytest`；宿主 `D:/Python312` 跑出 176 passed | P1 开工前补锁版本并同步 `requirements.txt` + `prj-ledger-version-lock.md`（须按纪律升版）→ **已在缺陷台账与风险册登记，未擅自写入依赖**（属配置变更，需授权） |
| G2 | `env/ports.md` 是 09-23 快照，**早于** T1.1 `.wslconfig` 安装，却被 v2 基线当作端口依据 | 文件头采集时间 2026-09-23 20:51；`.wslconfig` 核验为 2026-09-24 | P1 起容器前用 `scripts/check_ports.ps1` 重采，按新规范登记 `env/p1-audit-ports-<日期>.md` |
| G3 | V2「质量接近」的**差值门限数值从未成文**（判据前置铁律要求开跑前写下） | `gate-criteria` §八 第 5 项；§3.2 只写原则未写数值 | 转 P1：检索调参前先写下门限（已在判据文档 §八 标注未闭环） |
| G4 | Must 链 4 项未执行（图谱检索 / 审计日志 / 置信度降级路由 / 前端），端到端演示未做 | `p0-spec-scope-mvp` §2.1 行 5/11/12/13 | 属 Phase 1 范围，非 P0 缺陷；已在停止条件 S1 中如实登记为「未达成 → 转 P1」 |

---

## 四、命名规范建议（摘要，正文见 `docs/prj-spec-document-standard.md`）

```
<阶段>-<类型>-<主题>[-<YYYY-MM-DD>].md      全小写 ASCII + kebab，禁止空格 / 全角括号 / 中文文件名
```

- **阶段**：`p0`（已过闸）｜`p1`（进行中）｜`prj`（跨阶段长期有效）
- **类型**：`plan` `design` `spec` `decision` `report` `analysis` `audit` `review` `gate` `summary` `handover` `checklist` `template` `ledger`
- **日期**：**快照类必带** `-YYYY-MM-DD`；**活文档不带**，改在文件头写「最近更新：YYYY-MM-DD」
- **状态**：🟢 活动 / 🟡 时点快照（首行加横幅、正文不改）/ 🔵 冻结
- **例外**：根 `README.md`、`CHANGELOG.md`、三级 `README.md` 索引保留标准名；`env/env-baseline-v<N>.md` 与 `env/ports.md` 沿用版本后缀制；`reports/daily/D<n>-status.md` 沿用日序；`experiments/**` 与 `prompts/`、`schemas/`、`evals/` 等工程资产按资产命名，**不由文档规范重命名**
- **引用纪律**：写完整相对路径 + `.md`；**禁止省略号缩写**（`plan/H15-...md` 已造成 23 处断链）
- **整理纪律**：改名 = `git mv` + 全仓改写引用 + 在规范 §六 追加映射行 + 追加修订记录；收尾必跑 `pytest`

---

## 五、残留、未做与待确认（不隐藏）

| # | 事项 | 状态 |
|---|---|---|
| R1 | 不可改写区内仍存旧文件名：`prompts/`（8 文件 16 处）、`schemas/`（4）、`configs/`（4）、`docker/`（6）、`protos/`（1）、`evals/`、`experiments/**/raw/`（3）、`env/cloud.json`（3，含 API key 故未读写） | **有意保留**；规范 §六 映射表即为解释 |
| R2 | 台账**行序倒置**：风险册 §六（10-06 之后接 09-30 行）、缺陷册 §二 主表（ISS-037 排在 035/036 之前）、`p0-audit-status-2026-10-05` 表尾 | **未重排**（改行序 = 改动既有台账行）→ 需单独一次带修订说明的整理 |
| R3 | 历史正文中的旧术语「**无效拒绝**」大量保留（26+ 处） | **不追改**（抹掉即丢失拆档前的判据史）；新文档统一「拒止 / 澄清」 |
| R4 | `p0-review-v1-criteria-r4` 的「22 字段 ↔ 19 字段」内部分歧（F4） | **待确认**：需重算 `evals/v1_cases.jsonl` 修订字段数才能定谁对，本次未擅自改动 |
| R5 | `pytest` 依赖锁（G1） | **待授权**：写 `requirements.txt` + 版本锁属配置变更，不在文档整理授权范围内 |
| R6 | 收尾扫描：悬空引用 **77 处（去重后仍 77）**，构成为 命名规范映射表 45（有意保留旧名）+ 历史留痕横幅与整理记录中的原名 17（有意）+ **P1 未来交付物占位 9**（`p1-ingest`/`p1-mineru-spike`/`p1-triples-eval`/`docs/data-dictionary` 等，出自 P1 计划与移交清单，属正常）+ `env/cloud.json` 3（不可改写区）+ `archive/README.md` 3（引用旧路径以说明搬运，有意） | **非预期类别 = 0**；即除冻结区与未来占位外无断链 |
| R7 | 本次改动**尚未提交**：48 项改名已 staged（`R100`），65 个文件为工作树修改，2 个新文件未跟踪 | **待确认**：是否需要我提交（用户未要求，故未动） |
| R8 | 我自己的一次过度声明已当场更正：早先写入 scope-mvp 修订记录的一行称「§五、§七 已回填」，实际 §五 未采纳路线与 §七 多数指标仍为占位 → **已改写为「部分兑现」并逐项列明兑现范围** | 已更正（见该文件 §修订记录 10-08 行） |

---

## 六、验证证据（本次真机执行）

| 验证 | 命令 / 方法 | 结果 |
|---|---|---|
| 回归测试未受影响 | `python -m pytest tests/ -q`（宿主 `D:/Python312`） | **176 passed in 0.34s**，rc=0（改名前后各跑一次，结果一致） |
| 改名纯度 | `git diff --cached --name-status -M` | **48 条 `R100`**（改名时刻文件内容逐字节一致，非「删+增」） |
| 工作树状态 | `git status --short` | 65 个文件为内容修改；未跟踪仅剩 `archive/README.md`、`docs/prj-spec-document-standard.md`（均为本次有意新建） |
| 引用完整性 | 全仓扫描（排除 `.git/.venv/__pycache__/raw/冻结资产`），逐条 `os.path.isfile` | 悬空 **77 处**，全部归入 R6 的有意 / 正常类别，**非预期类别 0 处** |
| 陈旧断言扫描 | 对 23 份活文档按 18 个敏感串（`M0.6 未放行`/`待填入`/`119 用例`/`ISS-001 – ISS-018`/`0.34.3`/`taosX`…）计数并逐条判读 | 剩余命中全部落在「划除线 / 时点标注 / 修订记录 / 已裁决不采用 / 作废建议」等**有意保留的历史表述**中 |
| 清理 | 删除 3 次 shell 崩溃产生的 **17 个 0 字节垃圾文件**（文件名是 CJK 文本片段）与 `bash.exe.stackdump`，删除前逐个确认 size=0 且 mtime 落在本次会话 | 已清理，工作树无残留 |

**未验证**：R4 的字段数分歧（未重算）；R5 的依赖锁（未写入）；未运行任何云端调用（本次零 API 调用，故不影响 `EXP-M02-040` 的当日配额记录）。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | 初始建立：Phase 0 过闸后全量文档一致性同步与命名整理的核查报告（状态概述 / 清单与阶段 / 七类不一致修正 / 命名规范摘要 / 残留与待确认 / 验证证据）。执行明细见 `docs/prj-spec-document-standard.md` 与 `CHANGELOG.md` 2026-10-08（午后）条目 | 全仓文档、`reports/README.md`、根 `README.md`、`CHANGELOG.md` |
