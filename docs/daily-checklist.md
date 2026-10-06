# 每日执行检查清单（Daily Checklist）v1

> **对应任务**：Phase 0 每日开工 / 收工自检
> **里程碑**：M0.1–M0.6（各日出口见 §三）
> **上游依据**：`Phase 0 详细开发计划（D1-D10 可执行版）.md` §八「每日执行检查清单」（通用规则 + D1 / D2–D3 / D4–D5 / D6–D7 / D8–D9 / D10 各出口）
> **状态**：已定稿（可执行）
> **环境基线引用**：`env/env-baseline-v2.md` ｜ 判据源：`docs/gate-criteria.md`
> **版本**：v1 ｜ **制定日期**：D1（计划）

---

## 一、每日开工四条（逐字对齐上游计划 §八 通用规则）

- [ ] 今日 V 项的 **Pass / 中间 / No-Go 已定义**（见 `docs/gate-criteria.md`）
- [ ] 实验已按 `docs/experiment-log-template.md` 登记（digest / seed / prompt 版本 / commit）
- [ ] 原始数据已落盘 `experiments/**/raw/`（可追溯，含断点续跑）
- [ ] 结论将引用 `env-baseline-v2.md` 版本号

> **四条不满足，不开工。**

### 1.1 四条的自检要点

| # | 条目 | 自检要点 | 不满足的后果 |
|---|---|---|---|
| 1 | 判据已定义 | 打开 `docs/gate-criteria.md` §二 判据总表，确认今日 V 项三档齐全；V1 须确认判据口径是**首次成功率**；V2 须确认对照路线已声明；V3 须确认授权结论已三选一；V4 须确认 24GB 门禁线的口径已定义 | 违反"判据前置"铁律，验证结论整批作废 |
| 2 | 实验已登记 | 字段齐全：`experiment_id` / `date` / `env_baseline_version` / `image_model_digests`（必须是 digest，禁止 tag 或 `latest`）/ `seed` / `prompt_version` / `num_ctx` / `temperature` / `code_commit` / `hardware_snapshot` / `raw_data_path` | 结论不可复现，视为无法追溯 |
| 3 | 原始数据已落盘 | 路径在 `experiments/**/raw/`；文件**只增不改**；脚本支持从已有 JSONL 跳过已完成条目、续跑后追加，不得清空 | 数字无法回溯，结论作废 |
| 4 | 结论引用基线版本号 | 报告首部声明 `env-baseline-v2`；报告中的组件版本须与 `docs/version-lock.md` 完全一致（含 digest）；使用模拟数据的结论须附局限声明 | 结论不可比，视为作废 |

> 本条与 `docs/experiment-log-template.md` §七「每日开工四条」**逐字一致**，两处不得出现分歧。

---

## 二、每日收工动作

| # | 动作 | 落点 | 要求 |
|---|---|---|---|
| 1 | 当日状态记录 | `reports/daily/D<n>-status.md` | 逐任务写"计划动作 / 实际状态 / 产出物 / 证据或缺口"；并对"已完成 / 部分完成 / 未完成"三项分别计数 |
| 2 | 新增问题与风险登记 | `docs/risk-register.md` | 统一字段：风险 / 概率 / 影响 / 触发条件 / 应对 / 剩余风险；并标注关联的上游风险编号（R1–R16） |
| 3 | 判据或结论变更 | 对应文档的「修订记录」表 | 凡判据、结论、口径发生变更，**必须追加一行**修订记录（日期 / 修订人 / 原因 / 影响范围）；变更不得就地覆盖原文 |
| 4 | 实验登记归档 | `experiments/<v>/log.md`（本阶段可先在报告附录内以同结构登记） | 每条实验一个小节；原始数据只增不改 |
| 5 | 阻塞项显式列出 | 当日状态记录的"阻塞项"小节 | 写明"卡住的下游结论"与"解除需要什么"，并标注关联风险编号 |
| 6 | 中间区间处置登记（如当日触发） | `reports/P0-summary.md` | 每条处置留"做了什么 + 代价是多少"两行，代价须量化到 `Recall@5` 与 `P95` 两列（规范见 `docs/gate-criteria.md` §四） |

> **纪律**：判据一旦定稿，**变更即升版**。任何"改了判据但没留修订记录"的情况，视为判据失效。

---

## 三、各日出口检查清单

### 3.1 D1 出口（对应里程碑 **M0.1**）

- [x] `.wslconfig` 已安装并核验（`docker info`≈20GB / 10vCPU / 8GB swap）
- [x] 基线已升版 `env-baseline-v2.md`（2026-09-24 采集）
- [x] `env-baseline-v2.md` 字段完整
- [x] `tools_v1.json` 冻结
- [x] `data-sources-v1.md` 含兜底
- [x] TDengine 授权结论已出（2026-09-24：需降级，OSS + 自研解码器 ≤2 天）

> 当前状态：`.wslconfig` **已安装并核验**（2026-09-24，`docker info`≈20GB/10vCPU），基线已升 v2；TDengine 授权**已定稿 = 需降级（OSS + 自研解码器 ≤2 天），授权不阻塞** → **M0.1 已收尾为「✅ 达成」（2026-09-29，口径裁决见 `reports/P0-summary.md` §5.2）**（本节为早期快照，M0.2± 仍需后续里程碑更新）。

### 3.2 D2–D3 出口（对应里程碑 **M0.2**）

- [ ] V1 报告 8 指标齐全（首次/重试分开 + 云端 baseline）
- [ ] 分工决策含 70–90% 中间区间
- [ ] 50 条评测集 + 标注规范

### 3.3 D4–D5 出口（对应里程碑 **M0.3**）

- [ ] Milvus digest + jieba analyzer 抽检通过
- [ ] 参数基线表 + 检索对比
- [ ] Schema 映射（4 类边界）+ `query_sensor` 契约 + 告警路线

### 3.4 D6–D7 出口（对应里程碑 **M0.4**）

- [ ] checkpoint 恢复/幂等/并发/体积 全部有结论
- [ ] Redis 模板 + 审核生命周期策略

### 3.5 D8–D9 出口（对应里程碑 **M0.5**）

- [ ] 资源实测表 + 分组策略 + 替代代价
- [ ] 版本锁定清单 + 风险册 + MVP 停止条件

### 3.6 D10 出口（对应里程碑 **M0.6**）

- [ ] 6 项验证逐项 Pass/中间/No-Go
- [ ] 中间项处置动作 + 指标代价
- [ ] 版本锁定与报告 digest 一致
- [ ] P1 移交清单可直接使用

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
| T1.7 数据来源盘点 | 已完成 | `docs/data-sources-v1.md` |
| T1.8 实验登记规范 | 已完成 | `docs/experiment-log-template.md` |
| T1.9 TDengine 授权确认 | ✅ **已完成（2026-09-24，文档层 + 实物层）** | 落点 `reports/v3-auth.md` 第一段：裁定 OSS + 自研解码器 ≤2 天，判「需降级·有条件通过」 |

**状态统计**：已完成 9 项（T1.1–T1.9）；无未完成项。

### 4.2 当前阻塞项

| 编号 | 阻塞项 | 实测事实 | 卡住的下游结论 | 解除需要什么 |
|---|---|---|---|---|
| **D1-P1** | `.wslconfig` 未安装 | `%UserProfile%\.wslconfig` 实测不存在（`Test-Path` → False）；Docker 引擎内存上限 **16656285696 bytes = 15.51GB**（= 32GB 的 50%，Docker Desktop 默认分配），NCPU=20；设计值 `memory=20GB / processors=10 / swap=8GB` 未落地 | **V4b 全组件压测（D8）**；**V4b 的 24GB 门禁判据不成立**；M0.5 的资源实测结论 | 用户择机执行安装 + `wsl --shutdown`（会中断 WSL2 与正在运行的 `nacos-standalone` 容器）；回滚路径见 `env/wslconfig.bak` §三 |
| **D1-P2** | GPU 直通未验证 | WSL2 内 GPU 直通 **UNVERIFIED**；本机仅有 `docker-desktop` 工具发行版，其内无 `nvidia-smi`，且无通用 Linux 发行版可供验证 | **V4 判据中"GPU 可直通"分支**；V1 的 GPU 可用性结论 | 安装通用 Linux 发行版（如 Ubuntu）后执行 `nvidia-smi` 验证 |
| **D1-P3** | TDengine 授权~~未查证~~ → **已定稿（2026-09-24）** | **已查证**：官方 Sparkplug B 连接器仅 All-in-One/Enterprise（IDMP + taosX）；OSS 镜像 `tdengine/tsdb:3.3.8.0` 实测**无 taosX/连接器**；端口 6030 / 6041 / 1883 实测空闲（**端口空闲 ≠ 授权可用，已由实物层坐实**） | **V3 接入方案（D4–D5）**；M0.3 的时序路线结论 | **已闭环**：裁定 OSS + 自研 Sparkplug B 解码器 ≤2 天，判「需降级·有条件通过」，授权不阻塞（`reports/v3-auth.md` §四.1） |

**关联风险**：D1-P1 关联 R2 / R3 / R9；D1-P2 关联 R2 / R10；D1-P3 关联 R8 / R15。

**附带待办（非阻塞）**：Ollama 当前 0.34.2、存在 0.34.3 可升级 —— 须在 V1 开跑**之前**决定升或不升，并把最终版本与 digest 写入 `docs/version-lock.md`（关联 R7）。

### 4.3 里程碑现状

| 里程碑 | 达成状态 | 依据 |
|---|---|---|
| M0.1 | ✅ **达成**（2026-09-29 收尾） | `reports/daily/D1-status.md` §六（采集快照）+ `reports/P0-summary.md` §5.2（最终裁决）；T1.1 `.wslconfig` 已安装核验 ≈20GB/10vCPU（ISS-007）；T1.9 授权已定稿 = 需降级（OSS + 自研解码器 ≤2 天），授权不阻塞 |
| M0.2 | **未达成（V1 No-Go）** | `reports/P0-summary.md` §1.2/§三 决策4/决策5（约束解码 qwen 0.35 / ds 0.45 <70%、云端上界 0.60；**P5 Schema 简化负结果（已回退 v2）+ P6 多工具拆步负结果（多工具 qwen 40%→20%、ds 13.3%→0%）+ ISS-024 修复后新基准（单工具 57%/67% 为独立 blocker）→ 处置改指 P7 方案 A**；**P7 混合形态实测（EXP-M02-001：云端 27B 单响应编排，首次 0.60、多工具用例级 50%、参数值正确率 0.5882）→ 处置链①②③④全执行仍 No-Go，下一步复审参数值判据/用例口径**） |
| M0.3 | ✅ **达成**（V2 Pass + V3 封板） | `reports/v2-report.md` §11（**真 BM25 对标已闭环 EXP-V2-BM25**，检索/压力档 Pass）；`reports/v3-auth.md`（四部分实测达成，已封板，决策3） |
| M0.4 | ✅ **达成**（T5.1–T5.7 PG 全流程 Pass） | `docs/checkpoint-decision.md` §2.1/§6.1（重启完整 + 无重复副作用 + 无 TTL 丢状态；B1–B6 未触发） |
| M0.5 | ✅ **达成**（V4b 干净机重测 Pass 17.89GB ≤24GB） | `reports/v4b-report.md` §12.5、`experiments/v4b/raw/EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29.md`（V6/V7 结构 Pass） |
| M0.6 | **未放行** | 原因收窄为仅剩 **M0.2**（V1 R-2/R-3 工具调用 No-Go 挂起） |

> **本表进度快照已逐项回填实测结论（2026-09-30）**：M0.1 / M0.3 / M0.4 / **M0.5** 均已✅达成，仅剩 **M0.2（V1 R-2/R-3 工具调用 No-Go，已挂起）** 未达成 → **M0.6 未放行**（原因收窄为仅剩 M0.2）。各 V 项判据与设计早已定稿（前置条件就绪），判据定稿 ≠ 里程碑达成；达成与否以「实测 + 门禁裁决」为准。

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
| D1（计划） | 单人（本人） | 初始建立：承接 `docs/experiment-log-template.md` §七 对「`docs/daily-checklist.md` §一」的引用；固化上游计划 §八 通用规则与各日出口；写入 D1 进度快照（取自 `reports/daily/D1-status.md`） | — |
| 2026-09-30 | 单人（本人） | 补齐里程碑结论不一致：§4.3 M0.3/M0.4 由「未达成」回填为「✅ 达成」（M0.3 = V2 真 BM25 闭环 Pass + V3 封板；M0.4 = PG checkpointer T5.1–T5.7 全流程 Pass）；同步更新 §4.3 附注——仅剩 M0.2（V1 No-Go）未达成、M0.6 未放行。早前（2026-09-29）已回填 M0.5 升 Pass 与 M0.6 原因收窄 | §4.3 |
| 2026-09-30 | 单人（本人） | **P7 混合形态结论回填**：§4.3 M0.2 行补 `EXP-M02-001`（云端 27B 单响应编排，首次 0.60、多工具用例级 50%、参数值正确率 0.5882）→ 处置链①②③④全执行仍 No-Go；同步 §三 决策5 指针；**M0.2 仍 No-Go、M0.6 仍不予放行** | §4.3 |
