# 每日执行检查清单（Daily Checklist）v1

> **对应任务**：Phase 0 每日开工 / 收工自检
> **里程碑**：M0.1–M0.6（各日出口见 §三）
> **上游依据**：`p0-plan-detailed-d1-d10.md` §八「每日执行检查清单」（通用规则 + D1 / D2–D3 / D4–D5 / D6–D7 / D8–D9 / D10 各出口）
> **状态**：已定稿（可执行）
> **环境基线引用**：`env/env-baseline-v2.md` ｜ 判据源：`docs/p0-spec-gate-criteria.md`
> **版本**：v1 ｜ **制定日期**：D1（计划）

---

## 一、每日开工四条（逐字对齐上游计划 §八 通用规则）

> 说明：§二 为**每个工作日开工时逐条打勾**的自检项，故常态下显示为未勾 —— **不代表项目未完成**；里程碑达成状态只看 §四.3。

- [ ] 今日 V 项的 **Pass / 中间 / No-Go 已定义**（见 `docs/p0-spec-gate-criteria.md`）
- [ ] 实验已按 `docs/prj-template-experiment-log.md` 登记（digest / seed / prompt 版本 / commit）
- [ ] 原始数据已落盘 `experiments/**/raw/`（可追溯，含断点续跑）
- [ ] 结论将引用 `env-baseline-v2.md` 版本号

> **四条不满足，不开工。**

### 1.1 四条的自检要点

| # | 条目 | 自检要点 | 不满足的后果 |
|---|---|---|---|
| 1 | 判据已定义 | 打开 `docs/p0-spec-gate-criteria.md` §二 判据总表，确认今日 V 项三档齐全；V1 须确认判据口径是**首次成功率**；V2 须确认对照路线已声明；V3 须确认授权结论已三选一；V4 须确认 24GB 门禁线的口径已定义 | 违反"判据前置"铁律，验证结论整批作废 |
| 2 | 实验已登记 | 字段齐全：`experiment_id` / `date` / `env_baseline_version` / `image_model_digests`（必须是 digest，禁止 tag 或 `latest`）/ `seed` / `prompt_version` / `num_ctx` / `temperature` / `code_commit` / `hardware_snapshot` / `raw_data_path` | 结论不可复现，视为无法追溯 |
| 3 | 原始数据已落盘 | 路径在 `experiments/**/raw/`；文件**只增不改**；脚本支持从已有 JSONL 跳过已完成条目、续跑后追加，不得清空 | 数字无法回溯，结论作废 |
| 4 | 结论引用基线版本号 | 报告首部声明 `env-baseline-v2`；报告中的组件版本须与 `docs/prj-ledger-version-lock.md` 完全一致（含 digest）；使用模拟数据的结论须附局限声明 | 结论不可比，视为作废 |

> 本条与 `docs/prj-template-experiment-log.md` §七「每日开工四条」**逐字一致**，两处不得出现分歧。

---

## 二、每日收工动作

| # | 动作 | 落点 | 要求 |
|---|---|---|---|
| 1 | 当日状态记录 | `reports/daily/D<n>-status.md` | 逐任务写"计划动作 / 实际状态 / 产出物 / 证据或缺口"；并对"已完成 / 部分完成 / 未完成"三项分别计数 |
| 2 | 新增问题与风险登记 | `docs/prj-ledger-risk-register.md` | 统一字段：风险 / 概率 / 影响 / 触发条件 / 应对 / 剩余风险；并标注关联的上游风险编号（R1–R16） |
| 3 | 判据或结论变更 | 对应文档的「修订记录」表 | 凡判据、结论、口径发生变更，**必须追加一行**修订记录（日期 / 修订人 / 原因 / 影响范围）；变更不得就地覆盖原文 |
| 4 | 实验登记归档 | `experiments/<v>/log.md`（本阶段可先在报告附录内以同结构登记） | 每条实验一个小节；原始数据只增不改 |
| 5 | 阻塞项显式列出 | 当日状态记录的"阻塞项"小节 | 写明"卡住的下游结论"与"解除需要什么"，并标注关联风险编号 |
| 6 | 中间区间处置登记（如当日触发） | `reports/p0-gate-review.md` | 每条处置留"做了什么 + 代价是多少"两行，代价须量化到 `Recall@5` 与 `P95` 两列（规范见 `docs/p0-spec-gate-criteria.md` §四） |

> **纪律**：判据一旦定稿，**变更即升版**。任何"改了判据但没留修订记录"的情况，视为判据失效。

---

## 三、各日出口检查清单

### 3.1 D1 出口（对应里程碑 **M0.1**）

- [x] `.wslconfig` 已安装并核验（`docker info`≈20GB / 10vCPU / 8GB swap）
- [x] 基线已升版 `env-baseline-v2.md`（2026-09-24 采集）
- [x] `env-baseline-v2.md` 字段完整
- [x] `tools_v1.json` 冻结
- [x] `p1-spec-data-sources.md` 含兜底
- [x] TDengine 授权结论已出（2026-09-24：需降级，OSS + 自研解码器 ≤2 天）

> 当前状态：`.wslconfig` **已安装并核验**（2026-09-24，`docker info`≈20GB/10vCPU），基线已升 v2；TDengine 授权**已定稿 = 需降级（OSS + 自研解码器 ≤2 天），授权不阻塞** → **M0.1 已收尾为「✅ 达成」（2026-09-29，口径裁决见 `reports/p0-gate-review.md` §5.2）**（本节为早期快照，M0.2± 仍需后续里程碑更新）。

### 3.2 D2–D3 出口（对应里程碑 **M0.2**）

- [x] V1 报告 8 指标齐全（首次/重试分开 + 云端 baseline）—— **2026-10-08 复核**：`reports/p0-report-v1-tool-call.md` + 裁决报告 `reports/p0-gate-m02-verdict-2026-10-08.md`；交付物逐文件核对见 `reports/p0-gate-review.md` §四
- [x] 分工决策含 70–90% 中间区间 —— `docs/p0-decision-model-role.md` §4.6（R-2/R-3 转云、拒止留本地）
- [x] 50 条评测集 + 标注规范 —— `evals/golden_set_v1.jsonl`（50 条）+ `docs/prj-spec-labeling.md`

### 3.3 D4–D5 出口（对应里程碑 **M0.3**）

- [x] Milvus digest + jieba analyzer 抽检通过 —— digest 见 `docs/prj-ledger-version-lock.md`；抽检见 `reports/p0-report-v2-hybrid-retrieval.md`
- [x] 参数基线表 + 检索对比 —— `reports/p0-report-v2-hybrid-retrieval.md`（真 BM25 对标 `EXP-V2-BM25` + 压力档闭环，混合 Recall@5 0.91）
- [x] Schema 映射（4 类边界）+ `query_sensor` 契约 + 告警路线 —— `docs/prj-spec-schema-mapping.md`；V3 封板：四类边界 4/4、`query_sensor` P95 ≈ 26.2 ms、告警 Must#1/#2 PASS（`reports/p0-report-v3-ingest-license.md`）

### 3.4 D6–D7 出口（对应里程碑 **M0.4**）

- [x] checkpoint 恢复/幂等/并发/体积 全部有结论 —— V5 PG 路线 T5.1–T5.7 全 Pass（`reports/p0-report-v5-checkpoint.md`，M0.4 达成；决策见 `docs/p0-decision-checkpoint.md` §六）
- [x] Redis 模板 + 审核生命周期策略 —— `configs/redis.conf`（候选 A 留档，B7 后未采用）+ `docs/prj-spec-review-lifecycle.md`

### 3.5 D8–D9 出口（对应里程碑 **M0.5**）

- [x] 资源实测表 + 分组策略 + 替代代价 —— `reports/p0-report-v4b-resources.md` §12.5（干净机 17.89 GB ≤ 24 GB → Pass）+ §6.3 降级代价标注
- [x] 版本锁定清单 + 风险册 + MVP 停止条件 —— `docs/prj-ledger-version-lock.md` + `docs/prj-ledger-risk-register.md` + `docs/p0-spec-scope-mvp.md`

### 3.6 D10 出口（对应里程碑 **M0.6**）

- [x] 6 项验证逐项 Pass/中间/No-Go —— `reports/p0-gate-review.md` §二（**2026-10-08 更新：V1 亦判 Pass**，见决策34）
- [x] 中间项处置动作 + 指标代价 —— `reports/p0-gate-review.md` §三（V4b 历史 26.38 GB 中间区间 → 干净机重测升 Pass；V1 处置链 P5/P6/P7 + `ISS-035`/`ISS-036`/§3.1.3 全程留痕）
- [x] 版本锁定与报告 digest 一致 —— `reports/p0-gate-review.md` §6.6 第 3 条：compose 裸 tag **实测已清零**（8 镜像全部 `tag@digest`）
- [x] P1 移交清单可直接使用 —— **2026-10-08 `M0.6` 放行后生效**：`docs/p0-handover-p1.md`（交付物 / 遗留项 / 预算已按 10-08 口径同步）

---

## 四、当前进度快照（截至 D1）

> 数据来源：`reports/daily/D1-status.md`（环境数据采集时间 **2026-09-23 20:59:50** +08:00）。本表**只搬运该记录中的实测值，不新增任何数字**。

### 4.1 D1 已完成项（T1.1–T1.9）

| 任务 | 状态 | 产出物 |
|---|---|---|
| T1.1 WSL2 / Docker 配置 | **部分完成**（方案与备份就绪，安装动作未执行） | `env/wslconfig.proposed`、`env/wslconfig.bak` |
| T1.2 硬件采集 | 已完成（实测） | `env/hardware.json` |
| T1.3 端口检查 | 已完成（实测） | `env/ports.md` |
| T1.4 组件版本登记 | 已完成（实测采集） | `env/env-baseline-v2.md` |
| T1.5 目录初始化 | 已完成 | 目录树 |
| T1.6 Schema v1 冻结 | 已完成 | `schemas/tools_v1.json` |
| T1.7 数据来源盘点 | 已完成 | `docs/p1-spec-data-sources.md` |
| T1.8 实验登记规范 | 已完成 | `docs/prj-template-experiment-log.md` |
| T1.9 TDengine 授权确认 | ✅ **已完成（2026-09-24，文档层 + 实物层）** | 落点 `reports/p0-report-v3-ingest-license.md` 第一段：裁定 OSS + 自研解码器 ≤2 天，判「需降级·有条件通过」 |

**状态统计**：已完成 9 项（T1.1–T1.9）；无未完成项。

### 4.2 当前阻塞项

| 编号 | 阻塞项 | 实测事实 | 卡住的下游结论 | 解除需要什么 |
|---|---|---|---|---|
| **D1-P1** | `.wslconfig` 未安装 | `%UserProfile%\.wslconfig` 实测不存在（`Test-Path` → False）；Docker 引擎内存上限 **16656285696 bytes = 15.51GB**（= 32GB 的 50%，Docker Desktop 默认分配），NCPU=20；设计值 `memory=20GB / processors=10 / swap=8GB` 未落地 | **V4b 全组件压测（D8）**；**V4b 的 24GB 门禁判据不成立**；M0.5 的资源实测结论 | 用户择机执行安装 + `wsl --shutdown`（会中断 WSL2 与正在运行的 `nacos-standalone` 容器）；回滚路径见 `env/wslconfig.bak` §三 |
| **D1-P2** | GPU 直通未验证 | WSL2 内 GPU 直通 **UNVERIFIED**；本机仅有 `docker-desktop` 工具发行版，其内无 `nvidia-smi`，且无通用 Linux 发行版可供验证 | **V4 判据中"GPU 可直通"分支**；V1 的 GPU 可用性结论 | 安装通用 Linux 发行版（如 Ubuntu）后执行 `nvidia-smi` 验证 |
| **D1-P3** | TDengine 授权~~未查证~~ → **已定稿（2026-09-24）** | **已查证**：官方 Sparkplug B 连接器仅 All-in-One/Enterprise（IDMP + taosX）；OSS 镜像 `tdengine/tsdb:3.3.8.0` 实测**无 taosX/连接器**；端口 6030 / 6041 / 1883 实测空闲（**端口空闲 ≠ 授权可用，已由实物层坐实**） | **V3 接入方案（D4–D5）**；M0.3 的时序路线结论 | **已闭环**：裁定 OSS + 自研 Sparkplug B 解码器 ≤2 天，判「需降级·有条件通过」，授权不阻塞（`reports/p0-report-v3-ingest-license.md` §四.1） |

**关联风险**：D1-P1 关联 R2 / R3 / R9；D1-P2 关联 R2 / R10；D1-P3 关联 R8 / R15。

**附带待办（非阻塞）**：Ollama 当前 0.34.2、存在 0.34.3 可升级 —— 须在 V1 开跑**之前**决定升或不升，并把最终版本与 digest 写入 `docs/prj-ledger-version-lock.md`（关联 R7）。

### 4.3 里程碑现状

| 里程碑 | 达成状态 | 依据 |
|---|---|---|
| M0.1 | ✅ **达成**（2026-09-29 收尾） | `reports/daily/D1-status.md` §六（采集快照）+ `reports/p0-gate-review.md` §5.2（最终裁决）；T1.1 `.wslconfig` 已安装核验 ≈20GB/10vCPU（ISS-007）；T1.9 授权已定稿 = 需降级（OSS + 自研解码器 ≤2 天），授权不阻塞 |
| M0.2 | ✅ **达成（2026-10-08）** | **H22 同日多轮聚合口径**（`docs/p0-spec-gate-criteria.md` §3.1.3，经用户授权、档线一字未改）：`EXP-M02-040` 3 轮同日、合并 225 样本 → 单工具 **92.6%** / 参数校验 **100%** / 多工具 **75.0%** / 多轮 **100%** / 拒止 **100%** / 澄清 **100%** → **整体 Pass**（合并首次成功率 **0.9422**）。裁决与残余风险见 `reports/p0-gate-m02-verdict-2026-10-08.md`。**历史处置链（保留）**：09-30 判 No-Go（约束解码 qwen 0.35 / ds 0.45、云端上界 0.60；P5/P6/P7 三步处置均负结果）→ 10-07 收敛为**中间区间**（`EXP-M02-039` 最差档 = 多工具 66.7%，并实证 `ISS-028` 同日跨档漂移）→ 10-08 过闸 |
| M0.3 | ✅ **达成**（V2 Pass + V3 封板） | `reports/p0-report-v2-hybrid-retrieval.md` §11（**真 BM25 对标已闭环 EXP-V2-BM25**，检索/压力档 Pass）；`reports/p0-report-v3-ingest-license.md`（四部分实测达成，已封板，决策3） |
| M0.4 | ✅ **达成**（T5.1–T5.7 PG 全流程 Pass） | `docs/p0-decision-checkpoint.md` §2.1/§6.1（重启完整 + 无重复副作用 + 无 TTL 丢状态；B1–B6 未触发） |
| M0.5 | ✅ **达成**（V4b 干净机重测 Pass 17.89GB ≤24GB） | `reports/p0-report-v4b-resources.md` §12.5、`experiments/v4b/raw/EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29.md`（V6/V7 结构 Pass） |
| M0.6 | ✅ **放行（2026-10-08）** | **Phase 0 过闸**：M0.1 / M0.2 / M0.3 / M0.4 / M0.5 全部达成；M0.2 依 §3.1.3 聚合口径于 10-08 达成 → **Phase 1 可启动**。合集与决策见 `reports/p0-gate-review.md`（**决策34**）+ `reports/p0-gate-m02-verdict-2026-10-08.md`；移交见 `docs/p0-handover-p1.md` |

> **本表进度快照**（2026-09-30 首轮回填；**2026-10-08 更新**）：M0.1 / M0.2 / M0.3 / M0.4 / M0.5 / **M0.6 全部达成并放行**。**残余风险不因放行消失**：单轮口径仍不稳（R1 单轮仍判中间区间）、多工具档余量仅 **5.0pp**、云端结论依赖 provider 版本（`ISS-028` / `R-V1-10`）→ 三项已列入 P1 持续监控，任何改动前后须按**同口径**复测。各 V 项判据与设计早已定稿（前置条件就绪）；判据定稿 ≠ 里程碑达成，达成与否以「实测 + 门禁裁决」为准。

### 4.4 环境基线关键实测值（供开工自检核对）

| 项 | 实测值 |
|---|---|
| 主机 / OS | `<WORKSTATION>` / Windows 10 Pro 25H2 build 26200，x64 |
| CPU / 物理内存 | i7-13650HX（6P+8E，20 逻辑核）/ 32GB |
| GPU / 显存 | RTX 4060 Laptop，驱动 616.56，compute capability 8.9 / 8188 MiB（采集时已用 1282 MiB） |
| CUDA Toolkit | 默认路径下未安装（Ollama 自带 CUDA 运行时） |
| WSL 版本 / 内核 | 2.7.11.0 / 6.18.33.2-2；发行版仅 `docker-desktop` |
| Docker / Compose | 29.6.2 / v5.3.1；内存上限 15.51GB；NCPU 20 |
| Python / Node / Git | 3.12.8 / v24.19.0 / 2.45.1.windows.1 |
| Ollama | 0.34.2（存在 0.34.3 可升级；升级须重新登记 digest） |
| 端口 | 11/12 空闲，无需重映射；11434 被宿主 Ollama 占用属预期 |
| 磁盘 | C 剩 94.3GB / D 剩 429.8GB / E 剩 62.5GB |

> **引用纪律**：以上数据引自 `env/env-baseline-v2.md` v2（2026-09-24 采集），与 `env/hardware.json` 一致。任何报告只能引用这一个版本号，不得另起第二份环境描述。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| D1（计划） | 单人（本人） | 初始建立：承接 `docs/prj-template-experiment-log.md` §七 对「`docs/p0-checklist-daily.md` §一」的引用；固化上游计划 §八 通用规则与各日出口；写入 D1 进度快照（取自 `reports/daily/D1-status.md`） | — |
| 2026-09-30 | 单人（本人） | 补齐里程碑结论不一致：§4.3 M0.3/M0.4 由「未达成」回填为「✅ 达成」（M0.3 = V2 真 BM25 闭环 Pass + V3 封板；M0.4 = PG checkpointer T5.1–T5.7 全流程 Pass）；同步更新 §4.3 附注——仅剩 M0.2（V1 No-Go）未达成、M0.6 未放行。早前（2026-09-29）已回填 M0.5 升 Pass 与 M0.6 原因收窄 | §4.3 |
| 2026-09-30 | 单人（本人） | **P7 混合形态结论回填**：§4.3 M0.2 行补 `EXP-M02-001`（云端 27B 单响应编排，首次 0.60、多工具用例级 50%、参数值正确率 0.5882）→ 处置链①②③④全执行仍 No-Go；同步 §三 决策5 指针；**M0.2 仍 No-Go、M0.6 仍不予放行** | §4.3 |
| 2026-10-08 | 单人（本人） | **过闸回填**：§4.3 M0.2 由「未达成（V1 No-Go）」改为 ✅ **达成（2026-10-08，`docs/p0-spec-gate-criteria.md` §3.1.3 同日多轮聚合口径）**，M0.6 由「未放行」改为 ✅ **放行**；§3.2–§3.6 共 14 条出口项按 `reports/p0-gate-review.md` §四 逐文件核对结果勾选并补证据指针（§二 的 4 条为**每日开工自检**项，常态留空、不代表未完成）；§4.3 快照注记补列三项残余风险（单轮口径仍不稳 / 多工具档余量 5.0pp / 结论依赖 provider 版本）；文件重命名 → `p0-checklist-daily.md`。**历史判定链（09-30 No-Go → 10-07 中间区间）以括注保留，未抹去** | §二、§3.2–§3.6、§4.3、修订记录 |
