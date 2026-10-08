# reports/ 报告索引与填写纪律

> 项目：云侧工业 IoT 诊断 Agent 系统（`<REPO>`）
> 阶段：Phase 0（技术验证与范围锁定，D0 + D1–D10）**已于 2026-10-08 过闸放行**，下一入口为 Phase 1（`plan/p1-plan-detailed.md`）
> **命名规范**：本目录文件按 `docs/prj-spec-document-standard.md` 统一命名（`<阶段>-<类型>-<主题>[-<日期>].md`）；2026-10-08 前的旧名见该规范 §六 映射表
> 主场景：离心泵轴承振动异常诊断
> 本索引对应计划：`plan/p0-plan-detailed-d1-d10.md` §三、§六（已执行完毕，🟡 留档）

---

## 一、报告清单

| 报告文件 | 阶段 | 对应验证项 | 对应任务 | 出口里程碑 | 责任人 | 当前状态 |
|---|---|---|---|---|---|---|
| `reports/p0-report-v1-tool-call.md` | p0 | V1 LLM 工具调用能力对比 | T2.1–T2.4 | **M0.2**（D3） | 单人（本人） | **已实测**（约束解码全量 / 云端上界 / few-shot 分档各臂留痕）。⚠️ **🟡 时点快照**：正文判定为「`M0.2` No-Go」，V1 现已判 **Pass**（2026-10-08 聚合口径），索引原写「8 项指标实测待填入」为 09-30 前口径 |
| `reports/p0-report-v2-hybrid-retrieval.md` | p0 | V2 混合检索方案验证 | V2 Step1–3 | **M0.3**（D5） | 单人（本人） | ✅ **已实测 · Pass**：混合 `Recall@5` **0.91**；真 BM25 对标（`EXP-V2-BM25`）+ 10 万块压力档（`EXP-V2-LOAD`，P95 5.6 ms）均闭环。索引原写「Step1/Step2 实测待填入」已过期 |
| `reports/p0-report-v3-ingest-license.md` | p0 | V3 TDengine + Sparkplug B 接入 | T1.9（D1 首步）+ V3 Step1–3 | **M0.3**（D5） | 单人（本人） | ✅ **已实测并封板定稿**（决策3）：授权 = 需降级（OSS + 自研解码器 ≤2 天）；四类边界 4/4、`query_sensor` P95 ≈ 26.2 ms、告警 Must#1/#2 PASS；生产吞吐瓶颈列 P1。索引原写「实测待执行」已过期 |
| `reports/p0-report-v4b-resources.md` | p0 | V4b 全组件运行态资源实测 | T8.1–T8.5 | **M0.5**（D9） | 单人（本人） | ✅ **已实测 · Pass**：干净机重测宿主峰值 **17.89 GB ≤ 24 GB**（§12.5），历史 26.38 GB 中间区间口径保留。⚠️ 文首 §〇 摘要仍写「中间区间 / `M0.5` 部分达成」——**以 §12.5 为准**；索引原写「压测实测表待填入 / 存在前置阻塞项」均已过期 |
| `reports/p0-report-v5-checkpoint.md` | p0 | V5 LangGraph checkpoint 可靠性 | T5.1–T5.7 | **M0.4**（D7） | 单人（本人） | ✅ **已实测 · Pass（PG 路线）**：T5.1–T5.7 全通过、重复落库 **0 次**、**296 KB/thread**、无 TTL 丢状态；Redis 候选因 B7 弃用（`configs/redis.conf` 留档）。索引原写「真实 LangGraph 结论待填入」已过期 |
| `reports/p0-gate-review.md` | p0 | 全量（V1–V7） | T10.1–T10.4 | **M0.6**（D10） | 单人（本人） | **门禁评审合集**：逐项判定、交付物核对、5 条上游矛盾登记、P1 移交；**决策34 = `M0.6` 放行（2026-10-08）**。⚠️ 文首 §〇/§一 仍写「`M0.6` 未放行、V1 No-Go」（09-30 时点），以 §1.2 与决策34 为准 |
| `reports/p0-summary-project-2026-09-28.md` | p0 | 全量（V1–V7） | — | — | 单人（本人） | 🟡 项目全景总览（2026-09-28 口径，三份全景中最早，保留备查）；当前状态以 `reports/p0-gate-m02-verdict-2026-10-08.md` 为准 |
| `reports/p0-summary-project-2026-09-29.md` | p0 | 全量（V1–V7） | — | — | 单人（本人） | 🟡 **全景快照（2026-09-29 时点）**：V1 判定、V4b 口径与缺陷编号范围（止于 ISS-018）均已过时；**附录 A 文档不一致清单（C-01 ~ C-25）仍具审计价值**。~~最新全景总结~~ → 当前状态以 `reports/p0-gate-m02-verdict-2026-10-08.md` 为准 |
| `reports/p0-review-v1-criteria-r2.md` | p0 | V1 判据/用例口径复审（第一轮） | — | — | 单人（本人） | V1 复审记录（判据分档、参数值口径） |
| `reports/p0-review-v1-criteria-r3.md` | p0 | V1 判据/用例口径复审（第二轮，F1–F6） | — | — | 单人（本人） | **V1 复审终稿**；含 ISS-025/ISS-026 处置与 M0.2 归因修订（2026-09-30） |
| `reports/p0-review-v1-criteria-r4.md` | p0 | V1 判据/用例口径复审（第四轮，**H8 考点范围核对**） | — | — | 单人（本人） | **考点声明 ↔ 判据范围一致性核对**：确证 `ISS-029`（13 用例 / 19 字段）+ 影响量化（H5 考点口径 +0.15）+ A/B/C 处置路径（零调用，2026-10-05） |
| `reports/p0-audit-status-2026-09-30.md` | p0 | 全仓（代码/依赖/构建/测试/文件） | — | — | 单人（本人） | **状态审计与文件整理报告**：整理前后对比 + 变更清单（2026-09-30） |
| `reports/p0-audit-status-2026-10-05.md` | p0 | 全仓（脚本/构建/数据/依赖/文档/门禁） | — | — | 单人（本人） | **状态核查点**（H3 收口后）：全维度通过项 + 与 09-30 对比的未闭环项 + 新增 2 项云端方法论缺陷（2026-10-05） |
| `reports/p0-report-v1-cases-revision-2026-10-05.md` | p0 | V1 用例集修订（**路径 B**） | — | — | 单人（本人） | **处置 `ISS-029`**：19 字段元数据修订（判分代码零改动）+ 原件归档 + 离线重判 6 臂影响量化（2026-10-05） |
| `reports/p0-analysis-iss036-tier-split-2026-10-06.md` | p0 | V1 判据口径（**`ISS-036` 拆档影响量化**） | — | — | 单人（本人） | **「无效拒绝」→「拒止」+「澄清」拆档的离线量化**：拆档**只会变严**、卡点再解读为**澄清**（零调用、零代码改动，2026-10-06）；🟡 文中「主集无全 Pass 臂 → `M0.2` 仍 No-Go」为当时结论 |
| `reports/p0-audit-v1-single-tool-tier-2026-10-07.md` | p0 | V1 判据口径（**单工具档专项核对**） | — | — | 单人（本人） | **单工具档缺口的两类归因**：`v1-001`＝纯漂移（`ISS-028`）、**`v1-004`＝`pv4` 的稳定副作用**；`pv4` 77.8% 三天一致（零调用，2026-10-07）；🟡 该缺口已由 H21/H22 复测闭合 |
| `reports/p0-report-regression-suite-2026-10-06.md` | p0 | 全仓（工程侧） | — | — | 单人（本人） | **关闭 `ISS-030`**：新增 `tests/`（**首建 106 用例，现 176 用例**）+ 变异测试捕获率 5/5 的质量自证（2026-10-06） |
| `reports/p0-report-vcs-baseline-2026-10-06.md` | p0 | 全仓（版本控制） | — | — | 单人（本人） | **首次纳入 Git 并建立基线**（`672143e` / 标签 `baseline-2026-10-06`）+ 密钥防护与字节一致性验证（2026-10-06） |
| `reports/p0-audit-v1-refusal-2026-10-06.md` | p0 | V1 **澄清/拒止**行为专项 + 基准效度审计（术语见 `ISS-036`） | — | — | 单人（本人） | **锁定云端唯一卡点 `v1-016` 与"指代默认着陆"机制**；**发现 `ISS-032`（`prompt v2` few-shot 与测试集逐字重合 7/20）**；修正拒止专项路线为 H10/H11/H12（零调用，2026-10-06） |
| `reports/p0-audit-status-2026-10-07.md` | p0 | 全量（V1–V7 + 工程侧） | — | — | 单人（本人） | **项目状态报告**（只读核查）：全局维度核查 + 任务进度分栏（已完成/进行中/未开始）+ 优化措施效果评估（13 项）+ 改进建议；🟡 现场验证 `pytest` **170** 全绿为当日数（**2026-10-08 复跑 176**），文中「`M0.6` 未放行」为当日判定 |
| `reports/p0-gate-closeout-2026-10-07.md` | p0 | V1（M0.2）+ `ISS-035` + 门禁 | — | **M0.6** | 单人（本人） | **Phase 0 收尾报告**（经授权）：H21 单工具档复测 **88.9% Pass** 但整体仍中间区间（卡点漂移为多工具 66.7%）+ `ISS-035` 按职责拆分处置。🟡 **本文「`M0.6` 仍不放行」已被 `reports/p0-gate-m02-verdict-2026-10-08.md` 取代**；`ISS-028` 同日跨档漂移实证仍为有效证据 |
| `reports/p0-gate-m02-verdict-2026-10-08.md` | p0 | V1（M0.2）+ 门禁过闸 | — | **M0.6** | 单人（本人） | **`M0.2` 裁决 / Phase 0 过闸报告**（经授权，同日多轮聚合口径）：H22 3 轮同日、合并 225 样本 → **整体 Pass**（单工具 92.6%／参数校验 100%／多工具 75.0%／多轮 100%／拒止 100%／澄清 100%）→ ✅ **`M0.2` 达成、`M0.6` 放行**；含残余风险声明与复现命令（2026-10-08） |
| `reports/daily/README.md` | p0 | — | — | — | 单人（本人） | 日报规范说明 |
| `reports/daily/D1-status.md` | p0 | — | T1.1–T1.9 | M0.1（D1） | 单人（本人） | D1 当日状态记录（含实测事实） |
| `reports/p0-summary-phase0-2026-09-30.md` | p0 | 全量（Phase 0） | T10 | **M0.6**（D10） | 单人（本人） | 🟡 **Phase 0 阶段总结**（原置于 `plan/Phase 0 任务总结.md`，2026-10-08 按命名规范移入 `reports/` 并归为总结类）；文中「`M0.6` 不予放行 / V4b 仍为中间区间」为 09-30 时点口径 |
| `reports/p0-audit-doc-sync-2026-10-08.md` | p0 | 全仓（文档治理） | — | — | 单人（本人） | **文档一致性同步与命名整理的核查报告**：项目当前状态概述 + 文档清单（含用途与阶段）+ 命名规范 + 不一致问题与修正结果 + 残留清单；命名规范正文见 `docs/prj-spec-document-standard.md`（2026-10-08） |
| *(已移出)* `archive/personal/g2-measured-data-form-2026-10-05.md`、`job-questionnaire-49-backfill-2026-10-05.md`、`draft-questionnaire-review-2026-10-05.md` | — | **非项目技术产物** | — | — | 单人（本人） | 求职素材 3 份，2026-10-08 移出 `reports/` 并改名；用途与阅读须知见 `archive/README.md` |

> V4a 的产出落在 `env/hardware.json`、`env/ports.md`、`env/wslconfig.*`，不单独出 report；V6/V7 的产出落在 `docs/p0-spec-scope-mvp.md`、`evals/golden_set_v1.jsonl`、`docs/prj-spec-labeling.md`。
>
> **两点读法说明（2026-10-08 加）**：① `p0-review-v1-criteria-rN` 的后缀 **`rN` 是复审记录文件序号（源自旧文档版号 v2/v3/v4），不等于「复审轮次」**——`r2` = 第一轮、`r3` = 第二轮（F1–F6 终稿）、`r4` = 第四轮（H8），**第三轮无独立文件**，`r1` 位置由主报告 `p0-report-v1-tool-call.md` 占用；② V1 实验族有两套 ID（早期 `EXP-V1-001~010` 与后续 `EXP-M02-001~040`），**裁决臂 = `EXP-M02-040`**，两套不可直接比较。

---

## 二、报告状态三态定义（每份报告开头必须声明）

每份报告第一段必须写"**报告状态声明**"，明确它属于以下哪一态：

| 状态 | 含义 | 允许出现的数字 |
|---|---|---|
| **① 已实测** | 数据来自本机真实执行，可追溯至 `experiments/**/raw/` | 可以是实测值，但必须标注采集时间与来源 |
| **② 设计与判据已定稿，实测待执行** | 目标/设计/判据/复现命令齐备，结果表留空 | **只能出现环境实测值与判据阈值**，性能/质量数字一律不得出现 |
| **③ 混合** | 部分实测（通常是环境段）+ 部分待执行 | 必须逐节标注哪一节是哪一态 |

> ⚠️ **红线：绝不编造实测数字。**
> 尚未执行的实测一律写成 `【待 D? 实测填入】`，禁止用"预计""大约""约等于"伪装成实测值。
> 一份诚实留空的报告，价值高于一份数字漂亮的假报告——因为 P0 的全部意义就是"别在错误路线上盖楼"。

---

## 三、填写纪律（每份报告都必须遵守）

### 3.1 引用纪律

1. **引用 `env/env-baseline-v2.md` 的版本号**：所有报告的环境章节必须写明"引自 `env-baseline-v2.md` v2（2026-09-24 采集）"，不得另行描述环境，避免出现第二份"事实源"。
   - 当前 `env/env-baseline-v2.md` 已定稿（v2 / 2026-09-24 采集），本目录各报告须按 **v2 / 2026-09-24 采集**引用。
2. **引用 `docs/prj-ledger-version-lock.md` 的 digest**：凡涉及组件/模型版本，一律以 digest 为准，禁止只写 `latest` 或 tag。
3. **报告之间的结论不得互相矛盾**：V2 的检索结论必须与 V4b 的内存约束一致；V1 的分工决策必须被 V4b 的驻留方案承认。出现矛盾时以 `reports/p0-gate-review.md` 的联合仲裁结论为准。

### 3.2 判据纪律

1. **判据前置**：任一 V 项开跑前，其 Pass / 中间 / No-Go 必须已在本报告中定稿。
2. **中间区间 ≠ 通过**：判定为"中间区间"时，必须写出**具体处置动作 + 指标代价**。只写"待观察""后续再看"视为未完成。
3. **降级必带代价**：任何轻量替代（换库、降精度、缩规模）都必须显式标注对 `Recall@5`、P95 延迟的影响。禁止出现"降级后仍宣称原指标"。

### 3.3 可追溯纪律

每次实验必须按 `docs/prj-template-experiment-log.md` 登记，至少包含：

- 镜像/模型 **digest**
- 随机 **seed**
- **prompt 版本**（如 `prompts/tool_call_prompt_v1.md`）
- `num_ctx`、`temperature`
- 代码 **commit**
- 原始数据落盘路径 `experiments/**/raw/`（含断点续跑信息）

---

## 四、三条铁律（上游计划 §1.4，全文重申）

1. **顺序不可跳**：阶段一（决策冻结）/ 阶段三（基线建立）必须先于阶段五（主验证执行），否则验证结论整批作废。
2. **判据前置**：任一 V 项开跑前，其 Pass/中间/No-Go 必须已定义。
3. **降级必带代价**：任何轻量替代都须标注对 `Recall@5`、P95 的影响。

---

## 五、文件命名与目录约定（正文见 `docs/prj-spec-document-standard.md`）

```
reports/
├─ README.md                                # 本文件：索引 + 填写纪律
├─ p0-gate-review.md                        # ★ 门禁评审合集（M0.6，含决策34）
├─ p0-gate-m02-verdict-2026-10-08.md        # ★ 今日权威：M0.2 达成 / M0.6 放行裁决
├─ p0-gate-closeout-2026-10-07.md           # 🟡 10-07 收尾（当时不放行）
├─ p0-report-v1-tool-call.md                # V1（M0.2，🟡 正文为 No-Go 时点）
├─ p0-report-v2-hybrid-retrieval.md         # V2（M0.3，Pass）
├─ p0-report-v3-ingest-license.md           # V3 + T1.9（M0.3，封板定稿）
├─ p0-report-v4b-resources.md               # V4b（M0.5，Pass 17.89 GB）
├─ p0-report-v5-checkpoint.md               # V5（M0.4，Pass PG 路线）
├─ p0-review-v1-criteria-r2/r3/r4.md        # V1 口径复审（**rN = 文件序号 ≠ 复审轮次**，见 §一 说明①）
├─ p0-report-v1-cases-revision-2026-10-05.md        # ISS-029 路径 B
├─ p0-analysis-iss036-tier-split-2026-10-06.md      # ISS-036 拆档量化
├─ p0-audit-v1-refusal-2026-10-06.md                # 拒止/澄清专项 + ISS-032
├─ p0-audit-v1-single-tool-tier-2026-10-07.md       # H17 单工具档归因
├─ p0-audit-status-2026-09-30 / -10-05 / -10-07.md  # 状态审计与核查（🟡 时点快照）
├─ p0-summary-project-2026-09-28 / -09-29.md        # 全景快照（🟡）
├─ p0-summary-phase0-2026-09-30.md                  # 阶段总结（原在 plan/，2026-10-08 移入）
├─ p0-report-regression-suite-2026-10-06.md         # ISS-030 回归套件
├─ p0-report-vcs-baseline-2026-10-06.md             # Git 基线
├─ p0-audit-doc-sync-2026-10-08.md                  # 本次文档整理核查报告
└─ daily/
   ├─ README.md                    # 日报规范
   └─ D<n>-status.md               # 当日状态记录，n ∈ 1..10
```

> **规则摘要**（全文见 `docs/prj-spec-document-standard.md`）：全小写 ASCII kebab、禁止空格与全角括号；`<阶段 p0|p1|prj>-<类型 plan|design|spec|decision|report|analysis|audit|review|gate|summary|handover|checklist|template|ledger>[-<主题>][-<YYYY-MM-DD>]`；**快照必带日期、活文档不带日期**（改在文件头写「最近更新」）；历史结论**只加横幅、不改正文**。原约定的 `project-summary-YYYY-MM-DD.md` / `status-audit-YYYY-MM-DD.md` 范式已被上述规则取代（旧名映射见规范 §六）。

- 新增报告必须同步登记到本索引第一节表格；
- 报告一经判定，结论不得静默修改；修正须在本报告末尾追加"修订记录"（日期 / 修订人 / 修订原因 / 影响范围）。

---

## 六、当前全局状态摘要（**2026-10-08 复核**；首版为 D10 交付物复核）

| 维度 | 状态 |
|---|---|
| 环境基线 | T1.1 `.wslconfig` **已安装并核验**（`docker info`≈20GB/10vCPU，基线升 v2）；T1.2/T1.3/T1.4 已完成 → 详见 `reports/daily/D1-status.md` |
| Schema | **活动基线 = `schemas/tools_v4.json`**（含测点目录，`EXP-M02-040` 即此配置）；`tools_v1.json` 为 D1 冻结的历史快照（5 工具），`v2`/`v3` 留档、`v5` 为 H3 实验版（实测否决、未采纳） |
| 授权风险 | **T1.9 TDengine 授权已定稿**（2026-09-24）= 需降级（OSS + 自研 Sparkplug B 解码器 ≤2 天），授权不阻塞 |
| 文档交付物 | ✅ **齐备**：`docs/` **16 份**（判据/台账/风险/版本锁/范围/移交/决策/模板/**命名规范 `prj-spec-document-standard.md`**…）；`plan/` 7 份（仅 `p1-plan-detailed.md` 为待执行，其余为 🟡 留档）；`reports/` **25 份（含本索引 README）+ `daily/` 2 份**（本索引 §一）。~~项目全景「最新」= 09-29~~ → 三份全景均为 🟡 时点快照，**当前状态查 `reports/p0-gate-m02-verdict-2026-10-08.md`** |
| 评测集 | ✅ **就绪**：`evals/golden_set_v1.jsonl`（50 条）、`evals/v1_cases.jsonl`（20 条，`ISS-029` 路径 B 修订版）、`evals/v2_cases.jsonl`（25）、`evals/v3_cases.jsonl`（25）、`evals/r4_cases.jsonl`（20）、`evals/corpora_v1/corpus_100.jsonl`（100 块）、**`v1_refusal_transfer_v1.jsonl`（无泄漏迁移集）**、**`v1_adversarial_v1.jsonl`（自建对抗集）**、`probe-v1-004-2026-10-07.jsonl`；原件归档 `v1_cases-pre-2026-10-05/06.jsonl`、`v1_refusal_transfer_v1-pre-2026-10-06.jsonl`（**顶层 11 个 `.jsonl` + 语料 1 个**） |
| 执行器 | ✅ **就绪且自检通过**：`scripts/` 共 **22 个 Python 脚本**（**16 个含 `--selftest`**）+ 2 个 PowerShell；权威入口 = `run_e2e.py`（规则门 → 云端）+ `aggregate_runs.py`（§3.1.3 聚合裁决）+ `gate_rules.py`/`refusal_gate.py`/`judge_tools.py`/`llm_adapter.py` |
| 回归测试 | ✅ `tests/` **176 用例**（2026-10-08 复跑全绿，离线秒级）；⚠️ **`pytest` 未登记进 `requirements.txt` 与版本锁**（`.venv` 内无 pytest）→ P1 开工前补锁 |
| 验证实测 | ✅ **V1–V5 均已实测**：V1 **Pass（2026-10-08 同日多轮聚合口径；前期 No-Go → 中间区间）** / V2 **Pass（混合 Recall@5 0.91，真 BM25 + 压力档闭环）** / V3 **封板定稿**（四类边界 4/4、`query_sensor` P95 ≈26.2 ms） / V4b **Pass（干净机重测 17.89GB，历史 26.38GB 中间口径保留）** / V5 **Pass（PG 路线）** / V4a、V6、V7 见门禁行；原始数据 `experiments/**/raw/` |
| 门禁 | ✅ **M0.1 / M0.2 / M0.3 / M0.4 / M0.5 全部达成 → M0.6 于 2026-10-08 放行（P0 过闸，Phase 1 可启动）**（`reports/p0-gate-m02-verdict-2026-10-08.md` + `reports/p0-gate-review.md` 决策34）；**残余风险**：单轮口径仍不稳、多工具档余量 5.0pp、依赖 provider 版本（`ISS-028`/`R-V1-10`）→ 列入 P1 持续监控 |
| 归档 | 📦 3 份**非项目技术产物**（求职素材）已于 2026-10-08 移出 `reports/` → `archive/personal/`，见 `archive/README.md` |

> 详细判定、交付物核对与上游矛盾清单见 `reports/p0-gate-review.md`。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-09-28 | 单人（本人） | **同步 V1 约束解码全量 + 云端上界实测新进展**：EXP-V1-003 约束解码全量闭环（格式退化根除、可解析率 1.00，首次 qwen 0.35 / deepseek 0.45，重试后 0.95/0.90）；EXP-V1-002 云端上界 **Qwen/Qwen3.8-27B** 首次成功率 0.60，已锁定入 `docs/prj-ledger-version-lock.md` §三 第 10 行、`env/cloud.json` `is_locked=true` | §六（V1 结论、门禁栏） |
| 2026-09-30 | 单人（本人） | **报告索引与目录约定同步实际文件状态**：§一 补登 5 份报告（p0-summary-project-2026-09-28 / p0-summary-project-2026-09-29 / p0-review-v1-criteria-r2 / p0-review-v1-criteria-r3 / p0-audit-status-2026-09-30）；§五 目录树补全并约定 `project-summary-*.md` / `status-audit-*.md` 命名范式；§六 评测集由 3 项补至 6 项、执行器由"五个脚本"更正为"18 个 Python 脚本（12 个含自检）" | §一、§五、§六 |
| 2026-10-08 | 单人（本人） | **补登（前几次会话新增报告未登记，本索引自 09-30 后未更新）**：`p0-report-v1-cases-revision`、`p0-audit-v1-refusal`、`p0-analysis-iss036-tier-split`、`p0-audit-v1-single-tool-tier`、`p0-audit-status-2026-10-05`、`p0-audit-status-2026-10-07`、`p0-report-regression-suite`、`p0-report-vcs-baseline`、`p0-gate-closeout-2026-10-07`、`p0-gate-m02-verdict-2026-10-08` 等 10 行（部分由当次会话登记，此处核对补齐）；**遗留问题：索引长期滞后于目录实况** → 已由 `docs/prj-spec-document-standard.md` §八 第 3 条确立「新增即登记」义务 | §一 |
| 2026-10-08 | 单人（本人） | **全量文档同步与命名整理**：① §一 表新增「阶段」列并按 `docs/prj-spec-document-standard.md` 重排，补登 `p0-summary-phase0-2026-09-30.md`（自 `plan/` 移入）与 `p0-audit-doc-sync-2026-10-08.md`（本次整理核查报告），并加「已移出 `archive/personal/` 的 3 份非项目产物」说明行；② **修正 5 行「实测待填入」的过期描述**（V1/V2/V3/V4b/V5 均已实测，逐一给出实测值与 🟡 时点标注）；③ 去掉 `project-summary-2026-09-29` 的「最新全景」称号（三份全景均为时点快照，当前状态改指 10-08 裁决报告）；④ §一 末补两条读法说明（`rN` ≠ 复审轮次、V1 双实验族 `EXP-V1-*` 与 `EXP-M02-*`）；⑤ §五 命名约定改为指向命名规范并给出新目录树；⑥ §六 全局摘要按实况更正（`docs` 16 份、`reports` 25 份、脚本 22 个〔16 含自检〕、回归 176 用例、活动 Schema = `tools_v4`、评测集补迁移集/对抗集与归档件、V2 由「条件Pass」更正为 **Pass**、门禁改为 **M0.1–M0.6 全部达成并放行** + 残余风险、新增「归档」维度）；⑦ 全文旧文件名引用已随重命名改写 | §一、§五、§六、修订记录 |