# Phase 0 → Phase 1 移交清单（Handover P1）v1

> **对应任务**：T10.4（P1 移交清单）
> **里程碑**：M0.6（P0 门禁评审 · D10）
> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §九；`p0-plan-detailed-d1-d10.md` §三 D10 / §六.2；`p1-plan-detailed.md` §二
> **环境基线引用**：`env/env-baseline-v2.md` v2（2026-09-24 采集）
> **版本**：v1 ｜ **制定日期**：D10 ｜ **状态**：清单已定稿；**各验证项实测与阻塞项状态已于 2026-09-29 ~ 09-30 全量回填**（仅 checkpoint 恢复耗时、MinerU 等少数项保留 `【待实测】`/转 P1）

---

## 一、移交目的与使用方式

### 1.1 目的

本清单是 **Phase 0（技术验证与范围锁定）→ Phase 1（数据接入与知识库构建）** 的**唯一移交凭据**，回答三件事：

1. **P0 交出了什么**（可直接复用的资产，见 §二）；
2. **P1 第一天先做什么**（按优先级排序，见 §三）；
3. **哪些问题没闭环**（自动成为 P1 遗留问题，见 §四、§五）。

### 1.2 使用方式

| 项 | 说明 |
|---|---|
| **可直接作为 P1 的输入基线** | 本清单即为 `Phase 1 详细开发计划` §二「阶段前置（Phase 0 移交物核对）」的**勾选依据**；逐项核对即可开工 |
| **不重复劳动** | 建库参数、Schema、契约、评测集**直接复用**，不重新调参、不重做评测集 |
| **未闭环项自动成为 P1 遗留问题** | 依 `docs/prj-ledger-known-issues.md` §一 规则 6：「本清单在 P0 结束时随 `docs/p0-handover-p1.md` 移交，**未闭环项自动成为 P1 遗留问题**」 |
| **引用纪律** | 所有版本/digest 一律引用 `env/env-baseline-v2.md` 与 `docs/prj-ledger-version-lock.md`；本文件不另起第二份环境描述 |
| **降级前提** | 若 V3 判定连接器为商业授权，P1 接入形态改用 `reports/p0-report-v3-ingest-license.md` 指定的降级路径，**工期 +2 天并顺延里程碑** |

> **纪律**：本清单**不代替**门禁评审结论。若 M0.6 未通过，P1 **不得**以"清单已移交"为由启动；须先完成门禁过闸。
>
> **【2026-10-08 门禁放行注记】** ✅ **`M0.6` 已于 2026-10-08 放行** —— `M0.2` 经用户授权按「**同日多轮聚合口径**」达成（`docs/p0-spec-gate-criteria.md` **§3.1.3**；实测 `EXP-M02-040`：3 轮同日聚合 225 样本 = **整体 Pass**）；报告 `reports/p0-gate-m02-verdict-2026-10-08.md`。→ **本清单可作为 P1 输入基线，Phase 1 可启动**。**残余风险列入 P1 持续监控**：单轮口径仍不稳、多工具档聚合余量仅 5.0pp、结论依赖 provider 版本（`ISS-028`，云端不可 digest 化）。

---

## 二、P0 已交付资产清单

> 状态口径：**已定稿** = 内容可直接复用；**待实测回填** = 结构/判据已定稿，实测数字待补。

### 2.1 环境基线（`env/`）

| 资产 | 用途 | 状态 |
|---|---|---|
| `env/env-baseline-v2.md` | **唯一环境基线**，所有实验与结论引用其版本号 | 已定稿为 **v2**（2026-09-24 采集；T1.1 已落地，WSL2 配额 20GB/10vCPU）；v1 留档作废 |
| `env/hardware.json` | 硬件实测（32GB / RTX 4060 8GB / 20 逻辑核 / 各盘剩余）+ V4a 预判约束 | ✅ **已刷新（2026-09-29 重采，零警告）**：初采 2026-09-23T20:59:50；旧 v1 快照留档 `env/hardware-v1-2026-09-23.json` |
| `env/ports.md` | 端口分配基线（12 端口，11/12 空闲），后续所有 compose 必须遵守 | 已定稿（§四 已冻结） |
| `env/wslconfig.proposed` | `.wslconfig` 已安装方案（memory=20GB / processors=10 / swap=8GB） | ✅ 已安装并核验 live≈20GB/10vCPU/8GB（2026-09-24） |
| `env/wslconfig.bak` | 回滚路径（§三：删除文件 + `wsl --shutdown`） | 已定稿 |

### 2.2 契约与 Schema

| 资产 | 用途 | 状态 |
|---|---|---|
| `schemas/tools_v1.json` | **5 工具 Schema v1（冻结）**：`search_knowledge` / `query_sensor` / `query_graph` / `get_maintenance_history` / `generate_report` | 已定稿（T1.6 冻结；**改动即升版**） |
| `docs/prj-spec-schema-mapping.md` | Sparkplug topic/metric → 超级表/列映射 | ✅ **已定稿**（四类边界 4/4 实测通过；R-V3-5 已实现 / R-V3-6 已闭环；心跳兜底未实现见 ISS-017，2026-09-24） |
| `prompts/tool_call_prompt_v1.md` | 工具调用提示词 v1 | 已定稿（触发中间区间处置则升 v2） |

### 2.3 评测集与语料（`evals/`）

| 资产 | 规模 | 用途 | 状态 |
|---|---|---|---|
| `evals/golden_set_v1.jsonl` | **50 条** | V2 质量对比 / P1 召回抽检 / P2 检索指标 / P5 一致性检验的**唯一基准** | 已定稿（标注依据 `docs/prj-spec-labeling.md`；一致性检验待 P5） |
| `evals/v1_cases.jsonl` | **20 条** | V1 工具调用用例（5 类型 × 3 难度，对齐主场景） | 已定稿 |
| `evals/corpora_v1/corpus_100.jsonl` | **100 条** | V2 检索对照语料 / P1 建库输入规格 | 已定稿（模拟语料，带 `synthetic: true`） |

### 2.4 配置与编排

| 资产 | 用途 | 状态 |
|---|---|---|
| `configs/redis.conf` | `appendonly yes` + `maxmemory 1gb` + `maxmemory-policy noeviction` | 已定稿 |
| `configs/mosquitto.conf` | MQTT Broker 配置（Mosquitto 2.x 默认选型） | 已定稿 |
| `docker/compose.base.yml` | Milvus/etcd/MinIO/PG/Redis/Neo4j/TDengine 编排基线 | 已定稿（`mem_limit` 待 V4b 仲裁回填） |

### 2.5 脚本（`scripts/`）

| 资产 | 用途 | 状态 |
|---|---|---|
| `scripts/collect_env.ps1` | 硬件/环境采集 | 已定稿 |
| `scripts/check_ports.ps1` | 端口复核（与 `env/ports.md` 基线一致） | 已定稿 |
| `scripts/llm_adapter.py` | V1 两模型统一适配层（Schema 注入 / `think` 剥离 / 静默退化识别） | ✅ 已交付（`--selftest` 通过） |
| `scripts/judge_tools.py` | V1 自动判分器（draft-07 校验 / `time_range` ±10% 等价 / 七类失败归类 / 判据分档） | ✅ 已交付（`--selftest` 通过） |
| `scripts/run_v1.py` | V1 批量执行器（用例集 / 多轮历史 / 校验回灌 / 断点续跑 / 原始落盘） | ✅ 已交付（`--selftest`、`--dry-run` 通过） |
| `scripts/run_v2.py` | V2 检索对照执行器（Milvus / pgvector × dense/sparse/hybrid，含 `--check-analyzer` jieba 抽检） | ✅ 已交付（`--selftest`、`--check-analyzer`、`--dry-run` 通过） |
| `scripts/run_v5.py` | V5 checkpoint 可靠性执行器（T5.1–T5.7：恢复 / 幂等 / 并发 / 体积 / TTL） | ✅ 已交付（`--selftest` 通过）；**图执行路径已真跑（PG 路线，`EXP-V5-001~004`）** |
| `scripts/gbnf_grammar.py` | 约束解码约束生成（**实际载体 = JSON Schema**，供 Ollama `/api/chat` 的 `format`） | ✅ 已交付（`--selftest`、`--print` 通过） |
| `scripts/param_normalizer.py` | V1 参数归一化纠错层（白名单 R1/R2/R3；**已实测否决，uplift=0**） | ✅ 已交付（`--selftest` 通过） |
| `scripts/run_cloud_baseline.py` | 云端上界校准执行器（裸跑 EXP-V1-002 / 约束解码 EXP-V1-005） | ✅ 已交付（`--selftest` 通过） |
| `scripts/v2_pg_build.py` | V2 对照侧建库灌数（ParadeDB ngram BM25 索引） | ✅ 已交付（**无 `--selftest`**） |
| `scripts/v2_synth_corpus.py` / `scripts/v2_load_test.py` | V2 压力档语料合成与延迟 / 内存实测 | ✅ 已交付（**无 `--selftest`**） |
| `scripts/spb_simulator.py` | 自建 Sparkplug B 模拟器（`--scenario` 五类边界 / `--ingest` 连续灌数） | ✅ 已交付（`--selftest` 通过，四类边界实测 4/4） |
| `scripts/self_decoder.py` | 自研 Sparkplug B 解码器（M1–M6：proto / 订阅分流 / 建表 / 写入 / 离线 / re-birth） | ✅ 已交付（`--selftest` 通过） |
| `scripts/v3_ingest_direct.py` / `scripts/run_v3_alert.py` / `scripts/verify_query_sensor.py` | V3 标准数据集直写 / 告警路线 A（阈值+滑窗）/ `query_sensor` 聚合契约验证 | ✅ 已交付（**无 `--selftest`**） |

### 2.6 文档（`docs/`）

| 资产 | 用途 | 状态 |
|---|---|---|
| `docs/p1-spec-data-sources.md` | 数据来源盘点 + 自编模拟数据兜底路线 + 局限声明固定文本 | 已定稿（版权/隐私书面结论**待外部**） |
| `docs/prj-spec-labeling.md` | 评测集与标注规范 v1（7 类配额 + 难度分布 + 一致性检验计划） | 已定稿 |
| `docs/p0-decision-model-role.md` | 模型 → 角色分工决策框架 + V1 判据 + 中间区间处置动作 | ✅ **已回填**（§六 结论表已按 EXP-V1-003/004/005 实测填入；§三 已补分档重校说明） |
| `docs/p0-decision-checkpoint.md` | Redis/PostgreSQL/SQLite checkpointer 方案对比 + Redis 配置定稿 | ✅ **已定稿**（§2.1 结论 = 采纳候选 B PostgreSQL checkpointer；§三 已补网络段与执行器默认值） |
| `docs/prj-spec-review-lifecycle.md` | 审核生命周期策略（超时/死锁/并发/幂等/eviction） | 已定稿 |
| `docs/prj-ledger-known-issues.md` | 已知缺陷清单（**ISS-001 – ISS-037**），**随本清单移交** | ✅ **已回填至 ISS-037**（ISS-001~014 全部闭环；09-29 新增 015–023；09-30 新增 024–026；10-05 新增 027–029；10-06 新增 030–034、036；10-07 新增 035/037。**P1 遗留未闭环项：`ISS-028`（provider 漂移，缓解非消除）、`ISS-037`（原始记录无 schema 约束）+ 新登记「`pytest` 未进依赖锁」**） |
| `docs/prj-template-experiment-log.md` | 实验登记模板（digest/seed/prompt 版本/num_ctx/temperature/commit） | 已定稿 |
| `docs/p0-spec-scope-mvp.md` | **MVP 范围 + Must 链 13 项 + Won't + 停止条件 + 降级代价表** | ✅ 已定稿（**Must 链 13 项「当前状态」列已按 V1–V5 实测逐项回填**，含 3 项缺口标注，见其 §六） |
| `docs/p0-spec-gate-criteria.md` | **门禁判据集**（M0.1–M0.6 过闸条件 + 中间区间处置 + 三态口径） | ✅ 已定稿（**§3.1.1 分档判据、§3.7 R-4 判据、§六 里程碑状态均已回填**） |
| `docs/p0-checklist-daily.md` | D1–D10 每日勾选清单（任务 / 产出物 / 判据 / 阻塞登记） | ✅ 已定稿（逐日勾选已回填） |
| `docs/prj-ledger-risk-register.md` | **风险登记册 v1**：R1–R16 主风险册 + 实例化风险 + 硬风险升级清单 + ISS 对照 | ✅ 已定稿（**§5.3 闭环状态、§三.3.2 R-V1-7/R-V1-8、§六 D7/D8 回填均已完成，2026-09-30**） |
| `docs/prj-ledger-version-lock.md` | **版本锁定清单 v1**：8 镜像 + 2 模型双 digest + 工具链 + 实验固定参数 + Schema 版本 | 已定稿（**"15 项待锁定"为初始口径，实测后已收敛**：§三 多行已标 ✅，**reranker 已本地选用 `BAAI--bge-reranker-v2-m3`（2026-09-29）**，仅余 EMQX / 前端锁文件等，见其 §三） |
| `docs/p0-handover-p1.md` | 本文件 | 已定稿 |

### 2.7 报告（`reports/`）

| 资产 | 用途 | 状态 |
|---|---|---|
| `reports/p0-report-v1-tool-call.md` | V1 工具调用对比（8 项指标定义 + 判据 + 处置预案） | ✅ **已实测回填**（8 项指标 + 云端 baseline 全部回填；结论 **No-Go**，见 `reports/p0-gate-review.md` §二） |
| `reports/p0-report-v2-hybrid-retrieval.md` | V2 混合检索（版本/digest/analyzer/质量对比/参数基线表） | ✅ **已实测回填**（质量对比 6 组 + 真 BM25 对标 EXP-V2-BM25 + 压力档 EXP-V2-LOAD 全部闭环，见其 §4.4/§七） |
| `reports/p0-report-v3-ingest-license.md` | V3 授权结论（第一段，D1 必出）+ 接入方案（第二段） | ✅ **已封板定稿（2026-09-29，决策3）**：授权 = 需降级（OSS + 自研 Sparkplug B 解码器 ≤2 天），授权不阻塞；接入链路 + Schema 映射 + `query_sensor` 契约 + 告警路线 A 四部分**实测达成**；仅解码器吞吐（~80ms/条）列 P1 |
| `reports/p0-report-v4b-resources.md` | V4b 全组件资源实测 | ✅ **已实测（2026-09-29 干净机重测升 Pass）**：全栈 6 容器 + 单 7B 宿主峰值 **17.89GB ≤ 24GB**，见其 §12.5；历史 26.38GB 中间区间口径保留 |
| `reports/daily/D1-status.md` | D1 当日状态与阻塞项记录 | 已定稿 |
| `reports/p0-report-v5-checkpoint.md` | V5 checkpoint 可靠性（T5.1–T5.7 设计 + 判据 + B1–B7 映射 + 降级代价表） | ✅ **已实测回填**（T5.1–T5.7 **全 Pass**，PG 路线；结论见 `reports/p0-report-v5-checkpoint.md`） |
| `reports/p0-gate-review.md` | 门禁评审合集 + 逐项判定 + 交付物核对 + 上游矛盾登记 + P1 移交 | **已产出**（状态③）；门禁结论 = ✅ **M0.6 于 2026-10-08 放行**（决策34；正文 §一/§二 的「不予放行」为 09-30 时点，已由 `reports/p0-gate-m02-verdict-2026-10-08.md` 取代） |

### 2.8 目录骨架

| 资产 | 状态 |
|---|---|
| `configs/ docker/ docs/ env/ evals/ experiments/{v1,v2,v5}/raw/ prompts/ reports/daily/ schemas/ scripts/` | 已建成（T1.5 完成） |

---

## 三、P1 首日待办（按优先级）

> 上游明确：**MinerU 解析质量是 Phase 1 最大不确定项**（风险 R14），**必须首日验证**，不通过立即影响后续工期。

| 优先级 | 动作 | 依赖 | 验收方式 |
|---|---|---|---|
| **P0-1** | **MinerU 解析 Spike（R14，P1 最大不确定项）**：用 MinerU 解析 **3 类样本**——① 文本型 PDF ② 扫描件 PDF ③ 含表格 PDF，检查文本完整率 / 表格还原 / 图片处理 | 模拟语料就绪（`docs/p1-spec-data-sources.md` §三 模拟数据规格）；MinerU 引擎可用 | **判据**：文本型 PDF 文本完整率 ≥95%；扫描件 OCR 可读；三样本均能产出结构化 markdown。产出 `reports/p1-mineru-spike.md`。**不通过应对**：改用 PyMuPDF + PaddleOCR 组合，评估 +1~2 天工期 |
| **P0-2** | **A1 接入骨架**：起 Mosquitto + TDengine + 自研 Sparkplug B 解码器，打通 MQTT 连接 | **V3 授权结论**（**已定稿** = 需降级（OSS + 自研解码器 ≤2 天），见 §四 L-03） | `docker/compose.ingest.yml` 可启动；MQTT 连接打通。走降级路径，工期 +2 天并顺延里程碑 |
| **P0-3** | **环境复用**：复用 `env/env-baseline-v2.md`，启动 Milvus/Neo4j/PG/Redis | 环境基线（已定稿）；**`.wslconfig` 已安装并核验**（≈20GB/10vCPU，2026-09-24，见 §四 L-01） | 各组件健康检查通过；版本/digest 与 `docs/prj-ledger-version-lock.md` 一致 |
| **P1-1** | **PG 迁移**：建立 `documents / doc_chunks / knowledge_versions / work_orders / outbox / alerts` 表 | PG 已启动 | `db/migrations/0001_init.sql` 执行成功（对应 `Phase 1 详细开发计划` §5.8 DDL） |
| **P1-2** | **P0 遗留项收口**：按 §四 表格逐条认领（至少完成 L-01、L-03 的处置判定） | 各遗留项责任动作 | 每条遗留项在 §四 表格中更新状态为「已闭环 / 已转 P1 任务」 |
| **P1-3** | **模拟数据 seed 策略确认并登记** | `docs/prj-template-experiment-log.md`（已定稿） | seed 记入实验登记；模拟数据带 `synthetic: true` 标记（`docs/p1-spec-data-sources.md` §3.2 强制约束） |
| **P2-1** | **版权/隐私书面结论推进**（R15，唯一不可控外部依赖） | 外部回复 | 依 `docs/p1-spec-data-sources.md` §5.2 联系人表推进；未闭环则维持"模拟数据兜底" |
| **P2-2** | **建库参数基线复用确认**：核对 V2 参数基线表可直接采用 | V2 Step2/Step3 结论（当前未出，见 §四 L-08） | 参数**直接复用不重新调参**；若 V2 未出结论，须先补 V2 或显式声明"沿用候选值 + 待重测" |
| **P2-3** | **V4b 干净机重测宿主占用 → ✅ 已完成（升 Pass）**（2026-09-29）：本机关停非基线应用后全栈 6 容器 + qwen2.5:7b 宿主峰值 **17.89GB ≤24GB → V4b 升 Pass**（记录 `experiments/v4b/raw/EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29.md`；执行计划 `plan/p1-plan-v4b-cleanrm.md` 已兑现）。**仍留待 P1 并行项**：双 7B 错峰实测 + reranker（bge-reranker-v2-m3）驻留实测 | 专用干净机（本机，关停非基线应用）｜`docker/compose.base.yml` 四档组件｜宿主 Ollama 127.0.0.1:11434 | 判据 p0-spec-gate-criteria **§3.4**（V4 门禁线算式与口径）：≤24GB→**Pass（17.89GB）** / ≤26.4→中间 / >26.4→No-Go。实验ID `EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29`，未覆盖 `EXP-V4B-ISO-2026-09-28` |

> **并行提示**：A 主线（IoT 接入）与 B 主线（知识库构建）可**机器并行、人串行**；B1（MinerU）为关键路径起点。

---

## 四、遗留问题与阻塞项移交表

> **移交规则**：本表未闭环项**自动成为 P1 遗留问题**（依据 `docs/prj-ledger-known-issues.md` §一 规则 6）。
> **编号规则**：L-xx 为本清单新增移交编号；ISS-xxx 沿用 `docs/prj-ledger-known-issues.md` 原编号，不改号、不删除。

### 4.1 阻塞项（P0 已确认，P1 必须处置）

| 编号 | 问题 | 当前状态 | P1 需做什么 | 关联风险 |
|---|---|---|---|---|
| **L-01** | **`.wslconfig` 已安装并核验**：配置已复制至 `%UserProfile%\.wslconfig` → `wsl --shutdown` → 重启 Docker，live `docker info` **MemTotal≈20GB / NCPU=10 / Swap=8GB**，基线已升 `env-baseline-v2.md` | 🟢 **已核验**（2026-09-24） | V4b 门禁判据**已具评估前提**；后续按**容器内口径**（20GB 仍 < 24GB 宿主线）评测，见 `docs/p0-spec-gate-criteria.md` | R2、R3、R9；R-新1 |
| **L-02** | **GPU 直通 UNVERIFIED**：本机仅有 `docker-desktop` 工具发行版，**无通用 Linux 发行版**，其内无 `nvidia-smi` | 🟢 **已裁决（2026-09-24，U-03）→ 不再阻塞**：改走**宿主机原生 Ollama**（推理统一走 `127.0.0.1:11434`，容器仅承载 DB/存储）；GPU 直通保持 UNVERIFIED 但无真实用点。已同步 `docs/prj-ledger-version-lock.md` §二.2.4 / `prj-ledger-known-issues.md` ISS-008 / `prj-ledger-risk-register.md` R-V4b-2 | 若未来需**容器内推理**，须先安装通用发行版（如 Ubuntu）执行 `nvidia-smi` 重开验证；两条路径在报告中分开陈述 | R2、R10；R-新2 |
| **L-03** | **TDengine 授权已定稿（2026-09-24，文档层 + 实物层）**：裁定 **OSS 社区版 `tdengine/tsdb` + 自研 Sparkplug B 解码器 ≤2 天**，判「需降级·有条件通过」，授权不阻塞（R8 主风险已缓解） | 🟡 **已定稿（有条件通过）** | P1 接入走 OSS + 自研解码器；**自研工期 ≤2 天**，超期即回退 No-Go（MQTT JSON 直写）；方案与量化口径见 `reports/p0-report-v3-ingest-license.md` §三；后续落地时按 Broker 最重方案重算内存 | R8、R15；R-新4 |
| **L-04** | **Ollama 0.34.2 → 0.34.3 升级决策未做**（R7 版本漂移）：实测存在 0.34.3 可升级 | 🟢 **已决（2026-09-24，U-04）**：**锁定 0.34.2，不升级 0.34.3/0.34.4**（ISS-009）；V1 全流程已按 0.34.2 开跑，版本登记见 `docs/prj-ledger-version-lock.md` §二.2.3 | 若后续确需升级：**相关实验全部重跑**并升版环境基线，新开 `experiment_id` | R7；R-新3 |
| **L-05** | **版权/隐私书面结论待外部**（R15）：设备手册、维修工单、故障案例、拓扑图纸、标准规范均未取得书面结论 | 中（**待外部**，工期不可控） | 维持"**默认自编模拟数据**"兜底主线；按 `docs/p1-spec-data-sources.md` §5.2 推进书面索取；取得真实语料后以**同一评测集与同一流程重测** | R15 |
| **L-06** | **`docs/prj-ledger-known-issues.md` 未闭环缺陷**：~~ISS-001 – ISS-013 中多数状态列仍为"待 D7 / D2 填入"~~ | 🟢 **已闭环（2026-09-29 ~ 10-08）**：**ISS-001 – ISS-037 状态列已全部回填**，均为「已修复 / 可规避 / 需换方案」**三选一，无留空** | 仅需承接 §4.2 中标注「转 P1」的条目（ISS-012 量化档复核、ISS-015 鉴权、ISS-017 心跳兜底、ISS-025/026 口径复核） | 见 §4.2 |
| **L-07** | ~~**V5 checkpoint 实测未执行**~~ | 🟢 **已闭环（2026-09-24）**：T5.1–T5.7 **全 Pass**（PG 路线，Redis→PG checkpointer 降级、B7 根因修正）；ISS-001 – ISS-006 已全部收敛；方案决策见 `docs/p0-decision-checkpoint.md` §2.1 | **唯一残余**：checkpoint **恢复耗时实测**（`【待实测】`，见 `reports/p0-gate-review.md` §三 V5 行） | R11、R12、R-M5 |
| **L-08** | **V2 检索路线与参数基线未定**（质量对比与压力档未执行） | **已闭环（2026-09-28）** | 已补做 V2 Step1–Step3 并经实测闭环：jieba analyzer 抽检 32/32、质量对比 6 组回填 `reports/p0-report-v2-hybrid-retrieval.md` §4.4、**真 BM25 对标（EXP-V2-BM25）与压力档（EXP-V2-LOAD，10 万块 Milvus 5.6 ms/1.28 GB vs pgvector 170.6 ms/0.33 GB）均已完成**；P1 建库可沿用实测基线表 | R6、R5、R-M6 |
| **L-09** | **`docs/prj-ledger-version-lock.md` 与 `docs/prj-ledger-risk-register.md` 已落盘（v1）**，但版本锁定表中仍有待锁定项（**初始口径 15 项，实测后已大幅收敛**：TDengine / BGE-M3 / ParadeDB / Neo4j / Mosquitto / 云端模型 / Ollama 决策 / **reranker（已本地选用 `BAAI--bge-reranker-v2-m3`，2026-09-29）**均已锁；**余项为 EMQX（备选）/ 前端锁文件（Phase 0 无前端工程）**） | 中（**已产出、大幅收敛**） | 随各验证实测回填 `docs/prj-ledger-version-lock.md` §三 待锁定项（EMQX 仅当启用时，前端锁 P1 前端落地时）；版本锁定须与各验证报告 digest 一致（停止条件 S3 的判定依据） | R7、R-M10 |
| **L-10** | ~~**V4b 门禁线口径未定义**~~（24GB 指"容器内峰值"还是"宿主总占用"） | 🟢 **已裁决（2026-09-24，U-09）= 口径 B（宿主总占用）**：门禁线基数即"物理内存 × 75%"；已按口径 B 核算并经干净机重测**升 Pass（17.89GB ≤ 24GB，2026-09-29）** | 无（口径已定稿并落地；后续按同一口径复测） | R3；R-V4b-3 |

### 4.2 `docs/prj-ledger-known-issues.md` 缺陷移交明细（**随本清单移交**）

| 缺陷编号 | 所属组件 | 影响摘要 | 当前状态 | P1 需做什么 | 关联风险 |
|---|---|---|---|---|---|
| **ISS-001** | LangGraph checkpoint（`has_writes` 行为） | 状态机判断依据不可信，审核状态可能被错误覆盖 | ✅ **可规避（PG 路线未复现）**：正确探针签名下 B4 未触发 | 不依赖 `has_writes` 做业务判断；改用业务层显式状态字段 + writes 追加不覆盖 | R11 / R-M5 |
| **ISS-002** | checkpoint / 工具执行 | 恢复后重复副作用（重复报告、重复落库） | ✅ **可规避**：实测**重复落库 0 次**；只读工具重放 2 次（天然幂等放行） | 维持 `generate_report` 移出图内 + `idempotency_key` + PG 唯一索引 | R12 |
| **ISS-003** | Redis checkpointer | TTL/驱逐导致**状态永久丢失** | ✅ **可规避**：**PG 路线无驱逐/TTL → 无丢状态**（Redis 侧 N/A） | 若启用 Redis：`noeviction` + checkpoint 不设 TTL + 内存告警 | R11 |
| **ISS-004** | 审核并发控制 | 双审核人并发 resume → 产生两份报告 | ✅ **可规避**：PG 唯一索引 + 幂等键兜底，实测多次 resume 仅产 **1 份**报告 | 维持 SETNX 锁 + PG 唯一索引 + CAS 三层防护；P0 默认单实例 | R12 |
| **ISS-005** | Redis checkpointer | **第三方实现**，版本兼容性与行为一致性无官方保证 | 🟠 **需换方案（已切 PG）**：B7（redis-py ↔ redis-stack 握手被服务端关闭）→ 已切官方 `langgraph-checkpoint-postgres`，T5.1–T5.7 全 Pass | **已闭环**；三处同步（本清单 / `p0-decision-checkpoint.md` §2.1 / `prj-ledger-risk-register.md` R-M5）已完成 | R-M5 |
| **ISS-006** | Redis checkpoint 体积 | 体积无上限增长 → 达 `maxmemory` 后写失败，审核中断 | ✅ **可规避**：**PG 侧有界 296KB/thread**，增长可控 | 按 thread 保留最近 N 个版本（实测建议 N=20）；审核达终态即归档 | R11 / R13 |
| **ISS-007** | WSL2 / Docker 资源配额 | ~~**V4b 全组件压测结论无效**~~ | ✅ **已修复（2026-09-24 闭环）**：`.wslconfig` 已安装核验 ≈20GB/10vCPU/8GB swap | 无（同 L-01 已闭环）；后续按容器内口径评估 | R-新1 |
| **ISS-008** | WSL2 GPU 直通 | V4 判据"GPU 可直通"无法确认；可能改变容器内推理方案 | ✅ **已裁决（2026-09-24）**：改走**宿主机原生 Ollama**，GPU 直通保持 UNVERIFIED 但**不再阻塞** | 无（同 L-02）；若需容器内推理再重开验证 | R-新2 |
| **ISS-009** | Ollama | 版本漂移 → V1 结论短期失效、实验不可复现 | ✅ 已锁定 0.34.2（不升级） | **同 L-04**；V1 全流程固定同一版本 | R-新3 |
| **ISS-010** | TDengine / taosX | 官方 Sparkplug B 连接器仅 All-in-One/Enterprise（IDMP + taosX）；OSS **无 taosX/连接器**（已实测） | 🟡 **已定稿（有条件通过）** | **同 L-03**：OSS + 自研解码器 ≤2 天 | R8 / R-新4 |
| **ISS-011** | LLM 输出解析 | `think` 污染 → 把格式失败误判为能力不足 | ✅ 已修复（适配层统一剥离，可解析率 1.00） | 确认 `scripts/llm_adapter.py` 统一剥离 `think` 后再判 JSON；单列统计污染率 | R-新5 |
| **ISS-012** | 模型对比公平性 | 量化档不一致 → 分工决策建立在不可比数字上 | ✅ 可规避（引用对比数字须声明"量化档未知"；**P1 补测**） | 记录并拉齐量化档；胜出者补 Q8/FP16 复核；无法拉齐则显式声明不公平 | R-新6 |
| **ISS-013** | Ollama 服务行为 | 静默退化（返回 200 但无 `tool_calls`）→ 指标失真 | ✅ 已修复（`llm_adapter` 置位 `tool_calls_missing` → 判分器记「格式退化」） | 由适配层置位标志后由判分器单独归类统计（**非**判分器内断言）；单独统计退化次数 | R-新3 |
| **ISS-015 – ISS-023** | Redis 容器网络 / 多工具指标命名 / 心跳兜底 / `hardware.json` 过期 / 采集脚本三项（WSL 挂起·NUL 序列化·`.ps1` 非 ASCII）/ WSL2 端口探活 / V2 汇总表覆盖写 | 2026-09-29 审计新增 | ✅ 已修复 / 可规避（逐条见 `docs/prj-ledger-known-issues.md` §二；D-1/D-2/D-4 转 P1） | 见 `reports/p0-summary-project-2026-09-29.md` 附录 A | V5 / V1 / V3 / V4a / V2 |
| **ISS-024 – ISS-026** | V1 提示词装配（few-shot 恒取 v1）/ 云端路径亦 No-Go（参数值语义瓶颈）/ 拒止行为对 prompt 文本敏感且不可迁移 | 2026-09-30 新增 | ✅ ISS-024 已修复；ISS-025 / ISS-026 已闭环处置并转 P1 | 见 `reports/p0-review-v1-criteria-r3.md` | V1 |

### 4.3 移交处置纪律

| 规则 | 说明 |
|---|---|
| 状态三选一 | 每条缺陷状态必须为「已修复 / 可规避 / 需换方案」，**禁止留空、禁止写"待观察"** |
| 规避须具体 | 「可规避」的规避手段必须具体到**可执行步骤**，不得写"注意一下" |
| 换方案须闭环 | 「需换方案」条目必须同时出现在 `docs/p0-decision-checkpoint.md` §2.1 与 `docs/prj-ledger-risk-register.md` |
| 代价必标 | 触发中间区间的规避项，须记录**指标代价**（对 `Recall@5` / `P95` 的影响），并同步 `docs/p0-spec-scope-mvp.md` §五 |
| 编号不复用 | 缺陷编号一经分配不得复用；关闭后保留行，仅在状态列标注 |

---

## 五、P0 未达成的里程碑清单

### 5.1 里程碑达成情况总览

| 里程碑 | 内容 | 计划时点 | 达成情况 | 未达成原因 |
|---|---|---|---|---|
| **M0.1** | 约束与基线锁定 | D1 | ✅ **达成（2026-09-29 收尾）** | T1.1 `.wslconfig` **已安装并核验**（≈20GB/10vCPU，基线 v2，ISS-007 闭环）；T1.9 TDengine 授权**已定稿 = 需降级（OSS + 自研解码器 ≤2 天），授权不阻塞**；环境基线/Schema v1/数据来源/实验登记模板均已就绪（口径裁决见 `reports/p0-gate-review.md` §5.2） |
| **M0.2** | V1 完成 | D3 | ✅ **达成（2026-10-08，§3.1.3 同日多轮聚合口径）** | 约束解码全量 qwen 0.35 / ds 0.45 <70%、云端上界 0.60；few-shot 分档重判本地数据抽取类均未过 85% → **R-2/R-3 工具调用 No-Go**；**P5 Schema 简化负结果（已回退 v2）+ P6 多工具拆步负结果（多工具 qwen 40%→20%、ds 13.3%→0%）+ ISS-024 修复后新基准（单工具 57%/67% 为独立 blocker）→ 处置改指 P7 方案 A；P7 混合形态实测（EXP-M02-001，云端 27B 单响应编排）首次成功率 0.60（12/20）→ 处置链①②③④全执行仍 No-Go（多工具用例级 50%、参数值正确率 0.5882）→ 复审参数值判据/用例口径（**后续留痕：10-05 `ISS-029` 路径 B 修订用例元数据、10-06 `ISS-036` 拆档、10-07 `ISS-035` 按职责拆分 + H21 收敛为中间区间、10-08 H22 聚合 225 样本整体 Pass**；裁决 `reports/p0-gate-m02-verdict-2026-10-08.md`） |
| **M0.3** | V2 + V3 完成 | D5 | ✅ **达成（2026-09-28）** | V2 Pass（真 BM25 对标 EXP-V2-BM25 + 压力档 EXP-V2-LOAD 均闭环）；V3 已封板（四类边界 4/4 + `query_sensor` 契约 P95≈26.2ms + 告警路线 A Must#1/#2 PASS，见 `reports/p0-report-v3-ingest-license.md` §12.2） |
| **M0.4** | V5 完成 | D7 | ✅ **达成** | V5 PG 路线 T5.1–T5.7 全 Pass（Redis→PG checkpointer 降级，B7 根因修正） |
| **M0.5** | V4b + V6 + V7 完成 | D9 | ✅ **达成（2026-09-29）** | V4b 干净机重测 Pass（宿主峰值 17.89GB ≤24GB，`reports/p0-report-v4b-resources.md` §12.5）；V6/V7 结构 Pass |
| **M0.6** | P0 门禁评审 | D10 | ✅ **放行（2026-10-08）** | M0.1–M0.5 全部达成；M0.2 于 10-08 按 `docs/p0-spec-gate-criteria.md` §3.1.3 达成 → **Phase 0 过闸、Phase 1 可启动**。**残余风险（不略去）**：单轮口径仍不稳（R1 单轮仍判中间区间）、多工具档余量仅 5.0pp、云端结论依赖 provider 版本（`ISS-028`/`R-V1-10`）→ 三项列入 P1 持续监控，改动前后须按同口径复测 |

### 5.2 各验证项实测状态（未执行原因）

| 验证项 | 计划时点 | 实测状态 | 未执行原因 |
|---|---|---|---|
| V4a 约束采集 | D1 | ✅ **已执行（实测）** | — |
| V1 LLM 工具调用 | D2–D3 | ✅ **已实测 → Pass（2026-10-08，`M0.2` 达成）** | **裁决臂** = `EXP-M02-040`（H22，同日 3 轮、合并 225 样本，`docs/p0-spec-gate-criteria.md` §3.1.3）：单工具 92.6% / 参数校验 100% / 多工具 75.0% / 多轮 100% / 拒止 100% / 澄清 100% → 整体 Pass（合并首次成功率 0.9422）。**处置链留痕**：约束解码全量 qwen 0.35 / ds 0.45 + 云端上界 0.60 → P5 Schema 简化（负结果，回退 v2）→ P6 多工具拆步（负结果：多工具 qwen 40%→20%、ds 13.3%→0%）→ P7 混合形态 `EXP-M02-001`（首次 0.60、多工具用例级 50%、参数值正确率 0.5882）判 No-Go → `ISS-029` 路径 B 用例元数据修订（10-05）→ `ISS-036` 拆「拒止/澄清」档（10-06）→ `ISS-035` 按职责拆分判据对象 + `scripts/gate_rules.py`/`run_e2e.py`（10-07）→ `EXP-M02-039` 收敛为中间区间（10-07）→ **10-08 聚合口径过闸**。**残余风险**：单轮口径仍不稳、多工具余量 5.0pp、依赖 provider 版本 |
| V2 混合检索 | D4–D5 | ✅ **Pass** | jieba 抽检 32/32；混合 `Recall@5` 0.91；真 BM25 对标 EXP-V2-BM25（ParadeDB ngram sparse 0.90 vs Milvus 0.92）+ 压力档 EXP-V2-LOAD（10 万块 Milvus P95 5.6ms/1.28GB）均闭环 |
| V3 时序接入 | D4–D5 | ✅ **已封板（条件通过）** | 四类边界 4/4 通过；`query_sensor` 契约 P95≈26.2ms；告警路线 A Must#1/#2 PASS；生产吞吐瓶颈（解码器 REST ~80ms/条）列 P1 |
| V4b 全组件压测 | D8 | ✅ **Pass（干净机重测）** | 全栈 6 容器 + 单 7B 宿主峰值 17.89GB ≤24GB（`EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29`）；历史 26.38GB 中间区间口径保留 |
| V5 checkpoint 可靠性 | D6–D7 | ✅ **Pass（PG 路线）** | `langgraph` 已装，T5.1–T5.7 全 Pass；Redis→PG checkpointer 降级，B7 根因修正 |
| V6 数据来源与范围锁定 | D9 | ⏳ **部分完成** | 数据盘点与兜底路线已定稿（`docs/p1-spec-data-sources.md`）；版权/隐私书面结论**待外部**（L-05）→ 按兜底结论判为**中间区间**；范围与停止条件已写入 `docs/p0-spec-scope-mvp.md` |
| V7 评测集与标注规范 | D2–D3 | ✅ **产出已定稿** | `evals/golden_set_v1.jsonl`（50 条）+ `docs/prj-spec-labeling.md` 已定稿；**一致性检验（Cohen's Kappa）待 P5** |

### 5.3 P1 需承接的事项

| # | P1 需承接 | 依据 |
|---|---|---|
| 1 | **MinerU 解析 Spike**（R14，P1 最大不确定项）作为 P1 关键路径起点 | `Phase 1 详细开发计划` §四 D1 |
| 2 | ~~**L-01 / L-02 资源阻塞项的收口**~~ → 🟢 **已闭环**：L-01 `.wslconfig` 已核验（≈20GB/10vCPU）、L-02 已裁决改走宿主 Ollama；P1 建库**可直接复用 v2 基线**的内存结论 | §四 L-01 / L-02 |
| 3 | **L-03 授权落地**（已定稿 = 需降级（OSS + 自研解码器 ≤2 天）；决定 P1 接入形态，工期 +2 天） | §四 L-03；`Phase 1` §二 降级预案 |
| 4 | **L-07 / L-08 的补做或显式声明**（V5 checkpoint、V2 检索路线），否则 P1 建库参数与 P3 审核链路均继承未验证假设 | §四 L-07 / L-08 |
| 5 | **L-09 版本锁定清单与风险登记册**（P1 建库/接入须与 digest 一致） | §四 L-09；`Phase 1` §二 移交物 #3 |
| 6 | **L-05 版权/隐私书面结论推进**，未闭环则维持模拟数据兜底 | §四 L-05 |
| 7 | **§4.2 缺陷（ISS-001 – ISS-037）**的收敛（状态三选一）**已完成**；仅标注「转 P1」的条目继续滚动（ISS-012 量化档复核 / ISS-015 容器鉴权 / ISS-017 心跳兜底 / ISS-025·026 口径复核） | `docs/prj-ledger-known-issues.md` §一 规则 6 |

> **纪律**：P1 **只做 Must 相关**（依 `docs/p0-spec-scope-mvp.md` §二）；Should/Could 不计入 P1 范围。

---

## 六、移交检查清单

> 全部勾选后，本清单方可作为 P1 的输入基线；未勾选项须在 §四 表格中登记为遗留问题。

### 6.1 资产完整性

- [x] 环境基线齐备：`env/env-baseline-v2.md`、`env/hardware.json`、`env/ports.md`、`env/wslconfig.proposed`、`env/wslconfig.bak`
- [x] 契约齐备：**活动基线** = `schemas/tools_v4.json`（含测点目录，`EXP-M02-040` 即此配置）+ `prompts/tool_call_prompt_v4.md`（⭐ 当前最优候选）；历史留档 = `schemas/tools_v1.json`（v1 **FROZEN**）、`tools_v2/v3`、`tools_v5`（H3 实验版、实测否决未采纳）、`prompts/tool_call_prompt_v1.md`（评测活动版本之一）、`v2`（⛔ 含测试集泄漏 `ISS-032`，禁用于评测）
- [x] 评测集齐备且行数正确：`evals/golden_set_v1.jsonl`（50 行）、`evals/v1_cases.jsonl`（20 行）、`evals/corpora_v1/corpus_100.jsonl`（100 行）
- [x] 配置与编排齐备：`configs/redis.conf`、`configs/mosquitto.conf`、`docker/compose.base.yml`
- [x] 文档齐备（**现共 16 份**，命名与职责见 `docs/prj-spec-document-standard.md`）：`docs/p1-spec-data-sources.md`、`docs/prj-spec-labeling.md`、`docs/p0-decision-model-role.md`、`docs/p0-decision-checkpoint.md`、`docs/prj-spec-review-lifecycle.md`、`docs/prj-ledger-known-issues.md`、`docs/prj-template-experiment-log.md`、`docs/p0-spec-scope-mvp.md`、`docs/p0-spec-gate-criteria.md`、`docs/p0-checklist-daily.md`、`docs/prj-ledger-risk-register.md`、`docs/prj-ledger-version-lock.md`、`docs/p0-handover-p1.md`、`docs/p0-design-sparkplug-decoder.md`、`docs/prj-spec-schema-mapping.md`、`docs/prj-spec-document-standard.md`
- [x] 报告齐备（**现共 25 份 + `daily/` 2 份**，索引见 `reports/README.md`）：`reports/p0-report-v1-tool-call.md`、`reports/p0-report-v2-hybrid-retrieval.md`、`reports/p0-report-v3-ingest-license.md`、`reports/p0-report-v4b-resources.md`、`reports/p0-report-v5-checkpoint.md`、`reports/p0-gate-review.md`、`reports/daily/D1-status.md`
- [x] 执行器齐备（**现共 22 个 `.py`，其中 16 个支持 `--selftest`；另有 2 个 `.ps1`**）：核心 = `scripts/run_e2e.py`（**端到端唯一权威入口**：规则门 → 云端工具调用）+ `scripts/gate_rules.py`（纯规则前置门，零 LLM 调用）+ `scripts/refusal_gate.py` + `scripts/aggregate_runs.py`（§3.1.3 聚合裁决器）+ `scripts/llm_adapter.py`、`scripts/judge_tools.py`、`scripts/run_v1.py`、`scripts/run_v2.py`、`scripts/run_v5.py`
- [x] 回归测试齐备：`tests/` **176 用例**（`python -m pytest tests/ -q` 离线秒级全绿）—— ⚠️ **`pytest` 尚未登记进 `requirements.txt` 与版本锁**，P1 开工前补锁
- [x] 用例与迁移集：`evals/v1_cases.jsonl`（20，`ISS-029` 路径 B 修订版）、`evals/v1_refusal_transfer_v1.jsonl`（无泄漏迁移集）、`evals/v1_adversarial_v1.jsonl`（自建对抗集）、原件归档 `evals/v1_cases-pre-2026-10-05/06.jsonl`
- [x] 目录骨架齐备：`archive/ configs/ docker/ docs/ env/ evals/ experiments/ plan/ prompts/ reports/ schemas/ scripts/ tests/`（`plan/`、`tests/` 原清单漏列；`archive/` 为 2026-10-08 新增的非项目文档归档）

### 6.2 阻塞项已交接

- [x] L-01 `.wslconfig` **已安装并核验**（≈20GB/10vCPU/8GB swap，2026-09-24，ISS-007 闭环）→ **阻塞已解除**
- [x] L-02 GPU 直通 UNVERIFIED **已裁决**：改走宿主原生 Ollama（`127.0.0.1:11434`），容器仅 DB；GPU 直通分支仍不可判定但**无真实用点、不再阻塞**
- [x] L-03 TDengine 授权已定稿（需降级 = OSS + 自研解码器 ≤2 天）已交接，且降级路径与自研工期口径（≤2 天，超期回退 No-Go）已写明
- [x] L-04 Ollama 升级决策**已做**：锁定 **0.34.2 不升级**（ISS-009）；"V1 开跑前冻结"已遵守
- [x] L-05 版权/隐私书面结论待外部已交接，且兜底结论（维持自编模拟数据 + 局限声明）已写明
- [x] L-10 V4b 门禁线口径**已裁决 = 口径 B（宿主总占用）**，并已按此核算**升 Pass（17.89GB ≤ 24GB，2026-09-29）**

### 6.3 风险册已同步

- [ ] 全部阻塞项已登记到 `docs/prj-ledger-risk-register.md`（R2 / R3 / R7 / R8 / R9 / R10 / R11 / R12 / R15 / R-新1 – R-新6）
- [ ] `docs/prj-ledger-known-issues.md` §五「与风险册的对应关系」表已逐条核对一致
- [ ] 标为「需换方案」的缺陷已同步至 `docs/p0-decision-checkpoint.md` §2.1 与 `docs/prj-ledger-risk-register.md`，形成闭环

### 6.4 评测集与语料可追溯

- [ ] `evals/golden_set_v1.jsonl` 每行含 `qid / question / answer_points / relevant_chunk_ids / category / difficulty / source_doc`，7 类配额与难度分布符合 `docs/prj-spec-labeling.md` §2.1–§2.2
- [ ] `relevant_chunk_ids` 指向的块在 `evals/corpora_v1/corpus_100.jsonl` 中**真实存在**
- [ ] 模拟语料与元数据均带 `synthetic: true` 标记，**未与真实数据混放**
- [ ] 模拟数据 seed 已记录，实验登记字段（digest / seed / prompt 版本 / `num_ctx` / `temperature` / commit）可用
- [ ] 局限声明固定文本（`docs/p1-spec-data-sources.md` §3.3）已在各报告中逐份引用

### 6.5 范围与代价

- [ ] `docs/p0-spec-scope-mvp.md` §二 Must 链 13 项已逐条给出可验收判据
- [ ] `docs/p0-spec-scope-mvp.md` §五 降级代价表三列（`Recall@5` / `P95` / MVP 范围）**无留空**
- [ ] 已明确「无影响」的行（如 V5 checkpoint 降级对 `Recall@5`）已给出依据
- [ ] `docs/p0-spec-scope-mvp.md` §四 停止条件 S1–S3 与 T1–T8 已定稿且可判定

### 6.6 门禁与判定

- [ ] M0.1 – M0.6 的达成情况已在 §五 逐条写明（含未达成原因）
- [ ] `reports/p0-gate-review.md` 已产出（含逐项判定、中间区间处置记录、上游矛盾登记与 P1 移交）
- [x] 7 项验证项（V1–V7）已逐项判 Pass / 中间 / No-Go（当前：**V1 = No-Go**；**V2 / V4a / V4b / V5 = Pass**；**V3 = 条件通过（已封板）**；**V6 / V7 = 结构 Pass**）
- [ ] 中间区间项**未被当作通过**处理
- [ ] M0.6 门禁评审结论已出（通过 / 条件通过 / 未通过），并已在本清单标注

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| D10 | 单人（本人） | 初始建立：移交目的、P0 资产清单、P1 首日待办、遗留问题与阻塞项移交表、未达成里程碑清单、移交检查清单 | — |
| D10 | 单人（本人） | **交付物复核后同步**：§2.5 五个执行器由「缺口」改为已交付（自检通过）；§2.6 补登 p0-spec-gate-criteria / p0-checklist-daily / prj-ledger-risk-register / prj-ledger-version-lock；§2.7 补登 p0-report-v5-checkpoint / p0-gate-review；§四 L-07 / L-09 状态更新；§五 M0.6 与 V5 行更新；§6.1 / §6.6 勾选项同步 | §二、§四、§五、§六 |
| 2026-09-29（原【待 L-01/L-03 闭环】） | 单人（本人） | ~~回填 §四 阻塞项状态~~ → **已完成**：L-01 `.wslconfig` 已安装核验（≈20GB/10vCPU）、L-03 TDengine 授权已定稿（OSS + 自研解码器 ≤2 天） | §四（L-01 / L-03） |
| 2026-09-30（原【待各验证项实测】） | 单人（本人） | ~~回填 §二 资产状态、§五 里程碑达成情况~~ → **已完成**：V1–V5 全部实测回填；M0.3/M0.4/M0.5 达成、**M0.6 未放行仅剩 M0.2** | §二、§五 |
| 2026-09-30（原【待 M0.6 评审】） | 单人（本人） | ~~回填门禁评审结论与 §六.6 勾选结果~~ → **已完成**：门禁评审结论 = **M0.6 不予放行**（唯一原因 M0.2 / V1 No-Go）；§6.6 验证项判定同步 | §六 |
| 2026-09-24 | 单人（本人） | **L-03 / T1.9 授权闭环**：裁定 OSS + 自研 Sparkplug B 解码器 ≤2 天（判需降级·有条件通过）；同步 M0.1、M0.3、V3、P0-2、§五 承接#3、§6.2 checklist、ISS-010 | §四（L-03）、§五、§六、§4.2 |
| 2026-09-29 | 单人（本人） | **决策2/决策3 落定 + 版本锁定残余闭合**：**决策2** V4b **维持中间区间不升 Pass，转 P1**（升 Pass 需专用干净机重测，双7B 错峰 + 干净机重测记 P1）；**决策3** V3 **直接定稿封板**（仅解码器 REST 逐条 ~80ms/条 吞吐列 P1，见 `p0-report-v3-ingest-license.md` 状态④）。版本锁定 §三 增第 16 行（Dockerfile base `python:3.12-slim` 待锁定，网络不可达未能实测 digest）；§三 第 15 行前端锁处置（Phase 0 无前端工程，首版前端锁延 P1）；§五 修订记录 `【待 D4】` 占位行标记完成。p0-gate-review §三 增决策2/3 处置记录 | `reports/p0-gate-review.md` §三、`docs/prj-ledger-version-lock.md` §三/§五、`docker/Dockerfile.decoder`、`README.md` |
| 2026-09-29 | 单人（本人） | **M0.1 收尾为达成（方案 A）**：M0.1 由「条件通过」升为「✅ 达成」（`reports/p0-gate-review.md` §5.2 裁决，以 D1-status §六 6 项为准；T1.1 `.wslconfig` 已核验 ≈20GB + T1.9 授权已定稿 + 其余条件齐备）。§五 M0.1 行同步更新为「达成」；**不改变 M0.6 未放行**（仍因 M0.2 V1 No-Go + M0.5 V4b 中间区间，见 `p0-gate-review.md` §一） | §五（M0.1） |
| 2026-09-30 | 单人（本人） | **§五 里程碑/验证项状态全量回填（P6 结论并入）**：§5.1 M0.2–M0.6 与 §5.2 V1–V5 由"未执行"更新为实测结论——M0.3/M0.4/M0.5 已达成、M0.6 未放行仅剩 M0.2（V1 No-Go）；V1 补 P5 Schema 简化负结果（已回退 v2）与 P6 多工具拆步负结果（EXP-V1-009 vs 010：多工具 qwen 40%→20%、ds 13.3%→0%）、ISS-024 修复后新基准，多工具档处置改指 **P7 方案 A（云编排）** | §五（§5.1/§5.2） |
| 2026-09-30 | 单人（本人） | **P7 混合形态实测回填（V1 处置链第④步，仍 No-Go）**：`EXP-M02-001`（云端 `Qwen/Qwen3.8-27B` × 20 用例 × 1，Schema v2 结构化输出，多工具不拆步）首次成功率 **0.60（12/20）→ 整体 No-Go**（单工具 67%/多轮 33%/无效拒绝 67% 均 <70%；参数校验 75%、多工具 50% 落中间）；多工具集合覆盖 1.00 但用例级 50% → 编排无问题、卡参数值（参数值正确率 0.5882）。**处置链 ①②③④ 已全部执行仍 No-Go → 下一步复审参数值判据/用例口径**。§5.1 M0.2 与 §5.2 V1 行同步；**M0.2 仍 No-Go、M0.6 仍不予放行** | §五（§5.1 M0.2、§5.2 V1） |
| 2026-09-30 | 单人（本人） | **全文档一致性同步（资产/阻塞项状态随实测回填）**：① §2.6 `prj-ledger-known-issues.md` 收录范围 **ISS-018 → ISS-026**，p0-spec-scope-mvp / p0-spec-gate-criteria / p0-checklist-daily / prj-ledger-risk-register / prj-spec-schema-mapping 五行「待回填」→ **已回填**；② §2.7 报告状态 v1 / v2 / v3 / v4b / v5 五行「待实测 / 未执行」→ **已实测回填**（v3 已封板、v4b 已升 Pass）；③ §三 P0-3「`.wslconfig` 当前未落地」→ 已核验；④ §四.1 **L-02 / L-04 / L-06 / L-07 / L-10** 状态由「阻塞 / 决策未做 / 未执行 / 待定义」→ **已裁决 / 已决 / 已闭环**；⑤ §4.2 **ISS-001 – ISS-008** 由「待 D7 判定」→ 实际结论（**ISS-005 = 需换方案已切 PG**，其余可规避 / 已修复 / 已裁决），并将 **ISS-015–018 → ISS-015–023**、新增 **ISS-024–026** 行；⑥ §6.2 阻塞项交接清单与 §6.6 验证项判定（原写「V1/V2/V3/V4b/V5 = **无法判定**」，**与同文件 §5.2 直接矛盾**）已更正；⑦ 页头状态声明与 §5.3 承接事项同步；⑧ **修订记录中 3 条过期占位行**（【待 M0.6 评审】/【待各验证项实测】/【待 L-01/L-03 闭环】）回填为实际完成记录 | 页头、§二（2.2/2.6/2.7）、§三、§四（4.1/4.2）、§五（5.3）、§六（6.2/6.6） |
| 2026-10-07 | 单人（本人） | **`ISS-035` 处置（经授权）**：§5.1 M0.2 由 No-Go 收敛为**中间区间**（`EXP-M02-039` 最差档 = 多工具 66.7%）、`M0.6` 当时仍不放行（**该时点已由 10-08 取代**）；判据对象按职责拆分见 `docs/p0-spec-gate-criteria.md` §3.1.2 | §四.2、§五 |
| 2026-10-08 | 单人（本人） | **移交生效同步**：§5.1 M0.2 → ✅ 达成、M0.6 → ✅ **放行**；§5.2 V1 行由「已实测 → No-Go」改为 **Pass** 并保留完整处置链留痕；§二 交付物口径更正（缺陷册 ISS-037 / 文档 16 份 / 报告 25 份 / 执行器 22 个〔16 含自检〕/ **活动基线 = `tools_v4` + `prompt_v4`**，原清单只列 `tools_v1`+`prompt_v1`）；§6.6 核对表逐条勾选并补 `run_e2e`/`gate_rules`/`aggregate_runs`/`tests/` 176 用例/迁移集与对抗集；目录骨架补列 `plan/`、`tests/`、`archive/`；**新登记 P1 前置项：`pytest` 未进 `requirements.txt` 与版本锁**；文件重命名 → `p0-handover-p1.md`（命名规范 `docs/prj-spec-document-standard.md`） | §二、§4.2、§五、§6.6、修订记录 |
