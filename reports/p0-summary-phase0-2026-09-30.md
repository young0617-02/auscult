# p0-summary-phase0-2026-09-30
> **⚠️ 历史留痕（2026-10-08 文档同步加注，正文结论未改）**：本文所载判定为 **2026-09-30** 时点。文件名已按规范改为 `p0-summary-phase0-2026-09-30.md`（原 `plan/Phase 0 任务总结.md`）。 Phase 0 任务总结（原置于 `plan/`，按新规范移入 `reports/` 并归为阶段总结）；文中「`M0.6` 不予放行」为当时状态。 当前口径见 `README.md` §当前状态速览 与 `docs/p0-spec-gate-criteria.md` §六；裁决依据 `reports/p0-gate-m02-verdict-2026-10-08.md`。

> ## Phase 0 交付物落地（含 T1.9 落地选型闭环）
>
> - 项目：云侧工业 IoT 诊断 Agent 系统 · 主场景：离心泵轴承振动异常诊断
> - 项目根：`<REPO>`
> - 阶段：Phase 0 技术验证与范围锁定（D0 + D1–D10）
> - 生产方式：多人机并行；本轮口径 = **补齐全部文档/脚本/评测集交付物，实测统一留空标注「结构就绪、待实测填入」，不真实启动环境跑实验**
> - 总结日期：2026-09-24

---

## 一、任务目标

依据上游 `p0-plan-detailed-d1-d10.md`，将 **D1–D10 的全部交付物**在 `<REPO>` 落地：

1. 冻结判据、版本、Schema、端口、硬件基线等"框架与前置"类交付物；
2. 产出可执行的实验**执行器脚本**（均带 `--selftest` 且通过）；
3. 产出**评测集**与**标注/数据来源规范**；
4. 出具各验证项报告 + P0 门禁评审合集；
5. 登记上游文档矛盾与阻塞项，**不静默修改**，统一待用户裁决。

**红线**：绝不编造实测数字。未执行项一律写 `【待 D? 实测填入】`。

---

## 二、完整任务清单（已完成 / 未完成）

> 使用说明：**「已完成」** 行给出产出物落点；**「未完成」** 行在「确认结果/填写」列**留空**，推荐方案已给出，请填写你方结论或直接确认后勾选完成。

### 2.1 ✅ 已完成

| # | 任务 | 产出物 / 落点 | 说明 |
|---|---|---|---|
| C-01 | T1.2 硬件采集 | `env/hardware.json` | 实测采集 |
| C-02 | T1.3 端口检查 | `env/ports.md` | 11/12 空闲实测 |
| C-03 | T1.4 组件版本登记 | `env/env-baseline-v2.md`（v1 已作废留档） | v1（09-23）已升版 v2（09-24） |
| C-04 | T1.1 `.wslconfig` 安装 | `%UserProfile%\.wslconfig` | ✅ 已安装并核验：live MemTotal≈20GB / NCPU 10 / Swap 8GB |
| C-05 | T1.5 目录初始化 | 项目目录树 | — |
| C-06 | T1.6 Schema v1 冻结 | `schemas/tools_v1.json` | 5 工具，status=FROZEN |
| C-07 | T1.7 数据来源盘点 | `docs/p1-spec-data-sources.md` | 含模拟数据兜底 |
| C-08 | T1.8 实验登记规范 | `docs/prj-template-experiment-log.md` | 字段与每日开工四条 |
| C-09 | 判据定稿（判据前置铁律） | `docs/p0-spec-gate-criteria.md` | M0.1–M0.6 三档齐全 |
| C-10 | 每日清单 | `docs/p0-checklist-daily.md` | D1–D10 出口清单 |
| C-11 | 评测集 + 标注规范 | `evals/golden_set_v1.jsonl`(50) + `docs/prj-spec-labeling.md` | V7 判题集 |
| C-12 | V1 用例集 | `evals/v1_cases.jsonl`(20) | 5 类型 × 3 难度 |
| C-13 | V2 模拟语料 | `evals/corpora_v1/corpus_100.jsonl`(100) | — |
| C-14 | 执行器（5 个，全部 `--selftest` 通过） | `scripts/llm_adapter.py` / `judge_tools.py` / `run_v1.py` / `run_v2.py` / `run_v5.py` | — |
| C-15 | 角色分工 / Schema 映射 / checkpoint 决策 / 审核生命周期 / prj-ledger-known-issues | `docs/p0-decision-model-role.md` / `prj-spec-schema-mapping.md` / `p0-decision-checkpoint.md` / `prj-spec-review-lifecycle.md` / `prj-ledger-known-issues.md` | — |
| C-16 | 风险册 / 版本锁定（v1 落盘） | `docs/prj-ledger-risk-register.md` / `docs/prj-ledger-version-lock.md` | RSS：15 项待锁定（见 U-05） |
| C-17 | MVP 范围 / P1 移交 | `docs/p0-spec-scope-mvp.md` / `docs/p0-handover-p1.md` | — |
| C-18 | 各验证项报告（框架/判据/执行器就绪，实测空位） | `reports/p0-report-v1-tool-call` / `p0-report-v2-hybrid-retrieval` / `p0-report-v3-ingest-license` / `p0-report-v4b-resources` / `p0-report-v5-checkpoint` | 状态②/③ |
| C-19 | P0 门禁评审合集 | `reports/p0-gate-review.md` | 逐项判定 + 矛盾登记 |
| C-20 | 环境基线配套 | `env/wslconfig.proposed` / `wslconfig.bak` / `configs/redis.conf` / `mosquitto.conf` / `docker/compose.base.yml` / `prompts/tool_call_prompt_v1.md` | 配置/方案就绪 |
| C-21 | 报告索引 | `reports/README.md` | 状态同步至「截至 D10 交付物复核」 |
| C-22 | **T1.9 落地选型闭环**（OSS + 自研解码器 ≤2 天，判「需降级·有条件通过」） | `docs/p0-design-sparkplug-decoder.md`（方案 + 工期≈1.9 人日）/ `configs/decoder_schema_mapping.json`（机器可读映射）/ `docker/compose.ingest.yml`（Mosquitto + TDengine`3.3.8.0` + 解码器三件套） | 模拟器方案定稿（自建 `scripts/spb_simulator.py`，实现待 D4 编码阶段）；TDengine tag/digest 与解码器依赖已锁入 `docs/prj-ledger-version-lock.md` §二 |

### 2.2 ⏳ 未完成（确认结果列留空，请在下方填写或确认）

| # | 任务 | 状态 / 原因 | 推荐方案（可执行路径） | 确认结果 / 填写 |
|---|---|---|---|---|
| U-01 | **T1.1 `.wslconfig` 安装** | ✅ 已安装并核验：`wsl --shutdown` + 重启 Docker，live `docker info` MemTotal≈20GB / NCPU=10 / Swap 8GB | 已核验通过（2026-09-24）；基线已升 v2 | ✅ |
| U-02 | **T1.9 TDengine 授权确认** | ✅ **已闭环（文档层 + 实物层）**：裁定 **OSS + 自研 Sparkplug B 解码器（≤2 天）**，判「需降级·有条件通过」 | 见 `reports/p0-report-v3-ingest-license.md`：实物核验 `tdengine/tsdb:3.3.8.0` 无官方连接器 → 自研解码器（≤2 天） | ✅ |
| U-03 | **D1-P2 GPU 直通验证** | ✅ **已裁决（2026-09-24）**：**改走宿主原生 Ollama**（推理统一走宿主 `127.0.0.1:11434`，容器仅承载 DB/存储，不承载模型推理）；GPU 直通保持 **UNVERIFIED** 但**不再阻塞**（V1/V2/V5 实测均已走宿主 Ollama 跑完，容器内推理无真实用点）。已更新 `docs/prj-ledger-version-lock.md` §二.2.4 / `docs/prj-ledger-known-issues.md` ISS-008 / `docs/prj-ledger-risk-register.md` R-V4b-2 | 见 `docs/prj-ledger-version-lock.md` §二.2.4；ISS-008 状态改为「已决议改走宿主 Ollama」；R-V4b-2 标记「已裁决改走宿主」 | ✅ |
| U-04 | **Ollama 版本决定（0.34.2 vs 0.34.3）** | ✅ **已决（2026-09-24）**：**锁定维持 0.34.2，不升级 0.34.3/0.34.4**（ISS-009 建议 + 已安装运行 + V1 全流程固定同版本防行为漂移）；V1 实测已按 0.34.2 开跑 | 见 `docs/prj-ledger-version-lock.md` §二.2.3 已登记 | ✅ |
| U-05 | **版本锁定 15 项待锁定** | `docs/prj-ledger-version-lock.md` §三：**TDengine（§二.2.1）、解码器依赖（§二.2.7）、Mosquitto（§二.2.1）已锁定**；**V2 项 BGE-M3（dim1024/digest，§二.2.2）、PostgreSQL/ParadeDB 镜像 digest、Python 依赖（pymilvus 3.0.2 / psycopg 3.3.6 / jieba 0.42.1）已锁定（§二.2.8，2026-09-25）**；ParadeDB 真 BM25 **已由 K-V2-1 闭环验证可用（ngram，2026-09-28）** | 随各验证实测回填，保持与各报告 digest 一致 | ✅ **已收敛**（初始口径 15 项 → 余 EMQX〔备选〕/ 前端锁文件） |
| U-06 | **V1 实测（M0.2）** | ⏳→⚠️→️**挂起（2026-09-24～09-28）**：三路实测齐全——本地两模型×20×3（`EXP-V1-001` 无约束基线）+ **约束解码全量 EXP-V1-003 闭环**（格式退化根除、可解析率 1.00）+ **云端上界 EXP-V1-002=0.60**；按第二轮新口径重判均 **No-Go**。**复审 few-shot 扩容 EXP-V1-004（2026-09-28 实测）**：首次成功率 qwen 0.50 / deepseek 0.35（仍 <70%），重试后 qwen 1.00 / ds 0.85；**qwen 拒止误调用 15→0**（拒止强化成功）、多工具首次仍全灭（7B 结构性硬限）。**按分档判据重判（EXP-V1-004）**：本地单工具 33%/28%、参数校验 75%/50%、多轮 67%/67%、无效拒绝 100%/67%，数据抽取类均未过 85% 线。**结论：few-shot 未让任一数据抽取类类型越 85% 线，云端 0.60 佐证 7B 参数精确抽取为硬上限** | 明细 `reports/p0-report-v1-tool-call.md` §4.2–4.4、`experiments/v1/summary-EXP-V1-004.csv`；**M0.2 = 未通过（No-Go）**；**按用户决定 V1 挂起**（判未闭环）。**处置路径：参数归一化纠错已实测否决**（EXP-V1-NORM，uplift=0）；**以 EXP-V1-004 few-shot 按分档重判为据，架构由「混合（本地保留单工具/参数校验）」修正为「R-2/R-3 工具调用上云 + 多工具架构切分（拆单工具多轮）」**，R-4 证据归纳/诊断（合规锁死本地）、R-1/R-5/检索/写操作/审计/有效拒绝/降级兜底**保持本地**（**非全上云**）——见 `docs/p0-decision-model-role.md` §4.6 / `docs/p0-spec-gate-criteria.md` §3.1.1 / `reports/p0-report-v1-tool-call.md` §十。**R-4 本地证据归纳/诊断可用性 = 新增未验证项（ISS-014）**，现值 0.67 为多轮工具调用分、非证据归纳分，待 P1 专项测试（见 `docs/prj-ledger-known-issues.md`）**（ISS-014 已闭环 Pass：EXP-R4-001，2026-09-29，R-4 本地归纳可用，见 `p0-decision-model-role.md` §6.1）**。**P5/P6 增补（2026-09-30）**：① **P5 Schema 简化（tools_v3.json）实测负结果** → 已回退 `tools_v2.json`；② **P6 多工具拆步（方案 B）实测负结果**——EXP-V1-009（拆步）vs EXP-V1-010（ISS-024 修复后单响应基准）干净 A/B，多工具档 qwen **40%→20%**、ds **13.3%→0%**；机制为 qwen 编排障碍消除后失败全部收窄到参数值错（步序/工具名 15/15 全对）、ds 无收益；**多工具档 No-Go 处置改指 P7 方案 A（云编排）**；③ **ISS-024 修复（few-shot 真生效）为新基准**（qwen 0.60→0.68、ds 0.52→0.56），但 ds 拒止恶化 83%→33% 单列专项；④ **单工具档 57%/67% 为新暴露独立 blocker**。**M0.2 仍 No-Go** | ⚠️ **M0.2 = No-Go（已实测）**：处置链 ①②③④ + 复审 F1–F6 **全部执行仍未翻转**；归因修订为「判据口径缺陷 + 任务信息不足 + 模型部分错」混合归因 |
| U-07 | **V2 检索实测（M0.3）** | ✅ **实测已完成（2026-09-24/25）**：独立 Milvus 实例 `auscult-v2-milvus`（19531/9092）＋ParadeDB PG（5927/`auscult_v2`）；jieba 抽检 32/32；质量对比 6 组已回填 `reports/p0-report-v2-hybrid-retrieval.md` §4.4。**结论**：dense/hybrid 两路持平（0.90/0.95）、**Milvus 稀疏 BM25 对中文可用（Recall@5=0.92，最高）**、pgvector 稀疏 tsvector 对中文=0；判据 **Pass**（压力档已实测 EXP-V2-LOAD 2026-09-28，M0.3 条件项全解除）。**补充（2026-09-28）：K-V2-1 已闭环**——ParadeDB pg_search 真 BM25 可用 ngram tokenizer（`experiments/v2/raw/K-V2-1.md`），『BM25 实现间对比』划 P1 已闭环（EXP-V2-BM25）；**压力档三档实测 2026-09-28（EXP-V2-LOAD）**——10 万块 Milvus P95 5.6 ms/1.28 GB vs pgvector 170.6 ms/0.33 GB | 已回填 `reports/p0-report-v2-hybrid-retrieval.md` §〇/§二/§三/§四/§五/§六/§七/§十/§十一 及 `docs/prj-ledger-version-lock.md` §二.2.8 | ✅ **V2 = Pass**（真 BM25 对标 EXP-V2-BM25 + 压力档 EXP-V2-LOAD 均闭环） |
| U-08 | **V3 接入实测（M0.3）** | ✅ **已闭环（编码 + 真实联调，2026-09-24）**：`scripts/self_decoder.py`（M1–M6）、`scripts/spb_simulator.py`（`--selftest` 均通过）、`docker/Dockerfile.decoder`、`protos/sparkplug_b.proto`（tahu，含 `d/h/u` 子表互斥命名 + 反引号修复） | 起 Mosquitto`2` + TDengine`3.3.8.0` + 解码器（`docker compose -f docker/compose.ingest.yml up`）→ 模拟器灌数 **四类边界 4/4 实测通过**（建表/新增metric旁路/re-birth/离线，见 `reports/p0-report-v3-ingest-license.md` §6.2）；聚合 P95≈10.2ms、三容器内存实测（§9）；已回填 `reports/p0-report-v3-ingest-license.md` §6/§7/§8/§9 | ✅ |
| U-09 | **V4b 压测实测（M0.5）** | ✅ **实测已完成（2026-09-24）**：全组件运行态压测（S0–S8）实测数据落 `experiments/v4b/raw/EXP-V4B-*.md`；**口径 B（宿主总占用）**核算峰值 **26.38 GB > 24 GB**，超幅 **9.9% ≤ 10%** → 判据 **中间区间（需分组启动 + 按需加载）**；本项目实际增量 ≈ **6.73 GB**（容器合计 ≈1.38GB + Ollama 开销）完全在预算内；容器内内存大户 = **Neo4j（871.1 MiB）**；GPU 直通按 U-03 **改走宿主原生 Ollama**（不依赖容器直通）；**M0.5 判「部分达成」（V4b 压测数据已产出，判为中间区间，未到 Pass）** | 已回填 `reports/p0-report-v4b-resources.md` §〇/§四.1 实测摘要 及 `docs/prj-ledger-version-lock.md` §二.2.1（neo4j digest） | ✅（**2026-09-29 干净机重测升 Pass（17.89GB ≤ 24GB）**；历史 26.38GB 中间区间口径保留） |
| U-10 | **V5 LangGraph 实测（M0.4）** | ✅ **实测已完成（2026-09-24）**：`langgraph 1.2.12` 等依赖已装（`uv pip install`，版本锁入 `docs/prj-ledger-version-lock.md` §二.2.9）；T5.1–T5.7 全部 **Pass**（PG 路线）。**罕见决策**：原默认候选 A（Redis checkpointer）因 **B7（redis-py↔redis-stack 连接握手被服务端关闭）** 阻塞，经用户批准切 **候选 B（PostgreSQL checkpointer）**，B7 根因修正（非缺 RediSearch） | 已回填 `reports/p0-report-v5-checkpoint.md` §四/§六（EXP-V5-001~004 落 `experiments/v5/raw/`）；`docs/p0-decision-checkpoint.md` §2.1；`docs/prj-ledger-version-lock.md` §二.2.9；**M0.4 判定改为"达成"** | ✅ |
| U-11 | **V6 数据来源 / 版权确认** | 结论未实；已用模拟数据兜底 | 若 P1 需真实手册/工单，须先完成许可确认；否则维持模拟数据 + 局限声明 | |
| U-12 | **V7 标注双人校验（Kappa）** | 可选增强；当前为单人标注 | 需上线时引入第二标注人做 Cohen's Kappa；当前结论仅标「初步验证」 | |
| U-13 | **M0.6 门禁评审放行** | 未放行（原因收窄为仅剩 **M0.2** / V1 工具调用 No-Go） | 待 U-06（V1 处置）补齐后复核重评。**P6 结论（2026-09-30）**：多工具档拆步（方案 B）实测负结果 → 处置改指 **P7 方案 A（云编排）**；M0.2 仍 No-Go、M0.6 仍不放行 | |

### 2.3 待裁决（5 项）+ 上游矛盾（9 条，见 §五）

| # | 待确认项 | 现状 | 推荐口径 | 确认结果 |
|---|---|---|---|---|
| D-01 | V1 中间区间处置步骤数 | 上游 2 vs 报告 4 | 取四步（对齐 p0-decision-model-role §四） | ✅ **已裁定（2026-09-29）= 四步**；权威为 `docs/p0-decision-model-role.md` §四，上游 §五 / `p0-report-v1-tool-call.md` §7.2 视为"两步加固 + 两步兜底"摘要 |
| D-02 | M0.1 条件项数 | 上游 3 vs 实测 6 | 以 6 项（D1-status）为准 | ✅ **已裁定（2026-09-29）= 6 项**；以 `reports/daily/D1-status.md` §六 为准，M0.1 判 ✅ 达成 |
| D-03 | `R-新2`/`R-新3` 编号冲突 | **已复核：无冲突** | 以 prj-ledger-known-issues §五 为准 | ✅ **已复核（2026-09-30）**：`docs/p0-decision-model-role.md` §5.3 已使用 **`R-新3`**；`R-新2` 全仓仅指 GPU 直通（ISS-008），无串线 → 勾销 |
| D-04 | V4b 24GB 门禁线口径 | ✅ **已确认 = 口径 B（宿主总占用）**（2026-09-24，U-09）：Windows 宿主 + Docker/WSL2 容器 + 宿主 Ollama；门禁算式基数=物理内存 × 75% | 按口径 B 核算：**干净机重测 17.89GB ≤ 24GB → Pass（2026-09-29）**；历史 26.38GB 中间区间口径保留不改 | ✅ |
| D-05 | V4b `.wslconfig` 设计值 vs 门禁线 | ✅ **已裁决（2026-09-24）**：`.wslconfig` 设计值 memory=20GB 已生效（Docker 上限 ≈20GB），门禁线按 **宿主总占用（口径B）** 评估，两值不矛盾 | 20GB 是容器侧 WSL2 配额上限；24GB 是按物理内存算的宿主门禁线，两者口径不同，已由口径 B 统一 | ✅ |

---

## 三、交付物清点

### 3.1 类别核对

| 类别 | 数量 | 状态 |
|---|---|---|
| 执行器 `scripts/` | 5 执行器 + 1 归一化工具 | ✅ 自检全通过（另含 `param_normalizer.py`，EXP-V1-NORM） |
| 评测集 `evals/` | 3 | ✅ 行数 50 / 20 / 100 |
| 文档 `docs/` | 15 | ✅ 齐备（含新增 `p0-design-sparkplug-decoder.md`） |
| 报告 `reports/` | 8 | ✅ 齐备 |
| 基线 `schemas/` `env/` `configs/` `docker/` `prompts/` | — | ✅ 齐备（configs 新增 `decoder_schema_mapping.json`；docker 新增 `compose.ingest.yml`） |

### 3.2 执行器自检结论

| 脚本 | 职责 | 自检结论 |
|---|---|---|
| `llm_adapter.py` | V1 适配层（Schema 注入 / `think` 剥离 / 静默退化识别） | ✅ 通过 |
| `judge_tools.py` | V1 判分器（draft-07 / time_range 等价 / 六类归类 / 判据分档） | ✅ 通过 |
| `run_v1.py` | V1 批量执行器（多轮历史 / 回灌 / 续跑 / 落盘） | ✅ 通过 + dry-run |
| `run_v2.py` | V2 检索对照（dense/sparse/hybrid + jieba 抽检） | ✅ 通过 + check-analyzer + dry-run |
| `run_v5.py` | V5 checkpoint（T5.1–T5.7） | ✅ 通过；图执行路径待依赖后首跑 |
| `param_normalizer.py` | V1 参数归一化层（白名单：时长别名 / 标识符 trim / 数字转义；EXP-V1-NORM 载体） | ✅ 通过（`--selftest`，2026-09-28） |

---

## 四、门禁结论

| 里程碑 | 结论 |
|---|---|
| M0.1 约束与基线锁定 | ⚠️ **条件通过**（`.wslconfig` 已安装并核验 ≈20GB/10vCPU，基线已升 v2；T1.9 授权已定稿**=需降级（OSS + 自研 Sparkplug B 解码器 ≤2 天）**，授权不阻塞，实物层已复核 `tdengine/tsdb:3.3.8.0`） |
| M0.2 V1 完成 | ❌ **未达成 / V1 挂起（2026-09-28 复审后）**：V1 三路实测齐全但未过闸——约束解码全量 qwen 0.35 / deepseek 0.45 <70%、云端上界 0.60；**few-shot 复审 EXP-V1-004** 首次 qwen 0.50 / ds 0.35（仍 <70%），qwen 拒止误调用 15→0。M0.2 = **No-Go<70%**；**按用户决定 V1 挂起**（待定处置收窄：**参数归一化纠错已实测 uplift=0 否决**，待 用例/Schema 复审 / 承认 7B 上界）。**P5/P6 增补（2026-09-30）**：P5 Schema 简化负结果（已回退 v2）、P6 多工具拆步负结果（多工具 qwen 40%→20%、ds 13.3%→0%）、ISS-024 修复后新基准（单工具 57%/67% 为独立 blocker）→ 处置改指 P7 方案 A（云编排）；**M0.2 仍 No-Go** |
| M0.3 V2 + V3 完成 | ⚠️ **有条件**—— V2 **Pass**（jieba 32/32、Milvus 原生 BM25 可用，混合 `Recall@5`=0.91 ≥ 0.90；**真 BM25 稀疏对标已闭环 EXP-V2-BM25 2026-09-28**——ParadeDB ngram sparse `Recall@5`=0.90 vs Milvus 0.92、hybrid 打平 0.91；**压力档已实测 EXP-V2-LOAD 2026-09-28**——10 万块 Milvus P95 5.6 ms/1.28 GB vs pgvector 170.6 ms/0.33 GB，条件项全部解除）；V3 **已闭环**（U-08，四类边界 4/4 实测通过） |
| M0.4 V5 完成 | ✅ **达成**（V5 实测 PG 路线 T5.1–T5.7 全 **Pass**，U-10；Redis→PG checkpointer 降级、B7 根因已修正） |
| M0.5 V4b + V6 + V7 完成 | ✅ **达成（2026-09-29）**—— V4b **Pass**（干净机基线下 6 容器 + qwen2.5:7b 宿主峰值 **17.89GB ≤ 24GB**，EXP-V4B-CLEANRM-<WORKSTATION>；历史 26.38GB 中间区间口径保留）；V6/V7 **结构 Pass**（模拟数据兜底 + 单人标注） |
| M0.6 总判定 | **不予放行（原因收窄为仅剩 M0.2）** —— M0.3（V2 条件项已全解除 + V3 已闭环）、**M0.5 已达成**；仅 **M0.2（V1 R-2/R-3 工具调用 No-Go 且已挂起）** 未闭合；须补齐 V1 处置后复核重评 |

验证项逐项判定：

| 验证项 | 判定 |
|---|---|
| V1 | **No-Go / V1 挂起**（U-06：约束解码 qwen 0.35 / deepseek 0.45 <70%、few-shot 复审 EXP-V1-004 首次 qwen 0.50 / ds 0.35 仍未过，qwen 拒止误调用 15→0；云端上界 0.60；**M0.2 未达成**，按用户决定挂起，处置待定（参数归一化纠错已实测 uplift=0 否决）。**P5/P6（2026-09-30）**：Schema 简化负结果（已回退 v2）+ 多工具拆步负结果（EXP-V1-009 vs 010：多工具 qwen 40%→20%、ds 13.3%→0%）+ ISS-024 修复后新基准（单工具 57%/67% 独立 blocker）→ 处置改指 P7 方案 A（云编排）；**V1 仍 No-Go**） |
| V2 | **Pass**（U-07：jieba 32/32、Milvus 原生 BM25 可用，混合 `Recall@5`=0.91 ≥ 0.90）；**真 BM25 稀疏对标已闭环 EXP-V2-BM25（2026-09-28）**：ParadeDB 真 BM25（ngram）sparse `Recall@5`=0.90 vs Milvus 0.92、hybrid 打平 0.91，显式声明 ngram 子串 vs jieba 语义口径差异；tsvector 降级淘汰；**压力档已实测 EXP-V2-LOAD（2026-09-28）**：10 万块 Milvus P95 5.6 ms/1.28 GB vs pgvector 170.6 ms/0.33 GB，M0.3 条件项全部解除 |
| V3 | **条件通过**（U-08：已闭环，四类边界 4/4 实测通过，见 `reports/p0-report-v3-ingest-license.md`） |
| V4a | **Pass**（约束采集落盘 `env/` 三件套） |
| V4b | **Pass（2026-09-29 干净机重测）**（U-09）：本机 <WORKSTATION> 关停非基线应用后，模糊启动 6 容器 + qwen2.5:7b 常驻宿主峰值 **17.89GB ≤ 24GB**（平均 17.51GB；EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29）；历史口径B 峰值 26.38GB（含多项目共存因子）**保留不改**；分组启动 + 按需加载落地清单 §12.4 仍然有效 |
| V5 | **Pass（PG 路线）**（U-10）：T5.1–T5.7 全 Pass，**M0.4 达成** |
| V6 / V7 | **结构 Pass**（模拟数据兜底 + 单人标注，Kappa 可选未做） |

---

## 五、登记的上游矛盾与阻塞项（未静默修改）

### 5.1 上游矛盾

| # | 矛盾 |
|---|---|
| 1 | V1 中间区间处置步骤数 2 vs 4 |
| 2 | `prj-ledger-known-issues` 页头范围与表内条目不符（ISS-007/008/010） |
| 3 | M0.1 条件项数 3 vs 6 |
| 4 | `R-新2`/`R-新3` 编号冲突 |
| 5 | V4b `.wslconfig` 设计值 20GB < 门禁线 24GB |
| 6 | `compose.base.yml` 使用 `tdengine/tdengine:latest`（违反禁 latest 纪律） |
| 7 | `hardware.json` 主机名/时间不一致 |

### 5.2 阻塞项

| 编号 | 阻塞 | 影响 | 对应清单项 |
|---|---|---|---|
| B-1 | ~~`.wslconfig` 未安装~~ → **已解除**（live≈20GB 核验通过，基线 v2） | ~~V4b 门禁判据不成立~~ → 已具评估前提 | U-01（✅ 已闭环） |
| B-2 | ~~GPU 直通未验证~~ → **已裁决（2026-09-24）**：**改走宿主原生 Ollama**，GPU 直通保持 UNVERIFIED 但**不阻塞**（推理统一走宿主 11434，容器仅 DB/存储） | ~~V4、「GPU 可直通」无法判定~~ → 已决议推理不依赖容器直通，V1/V2/V5 均走宿主 Ollama | U-03（✅ 已闭环） |
| B-3 | ~~langgraph 依赖未安装~~ → **已解除**（`langgraph 1.2.12` 等已装，V5 T5.1–T5.7 全 Pass，PG 路线） | V5 图执行路径已真跑 | U-10（✅ 已闭环） |
| B-4 | TDengine 授权~~未查证~~ → **已定稿（文档层 + 实物层，2026-09-24）**：裁定 **OSS + 自研 Sparkplug B 解码器（≤2 天）**，判「需降级·有条件通过」；授权不阻塞 | 时序路线已定：OSS 镜像 `tdengine/tsdb` + 自研解码器（放弃官方连接器） | U-02（✅ 已闭环） |

**§五 已知问题（V2 登记）**：

| 编号 | 问题 | 影响 | 状态 |
|---|---|---|---|
| **K-V2-1** | **ParadeDB 真 BM25【已闭环 2026-09-28】**：`paradedb/paradedb`（pg_search 0.25.10）上 `USING bm25` 建索引 + INSERT 已成功（根因：key_field 绑定 + 镜像无 chinese/zhparser，改用 `ngram` tokenizer） | V2 可脱离 tsvector 降级走真 BM25；『BM25 实现间对比』（Milvus vs ParadeDB，含 Jieba/ngram 分词口径差异）**划入 P1 专项**；本报告 V2 结论数值维持 tsvector 口径 | ✅ **已闭环**（`experiments/v2/raw/K-V2-1.md`；`reports/p0-report-v2-hybrid-retrieval.md` §二.2.4） |

---

## 六、下一步（需用户指令）

**Phase 0 实测进度：V3/V5 已闭环保障；V4b 实测闭环且**处置已落地并核对+留痕（§12.4）**（仍为中间区间，未到 Pass）；V2（K-V2-1 已闭环，真 BM25 可用，压力档已闭环）；V1 已挂起；M0.6 未放行。**

1. 确认 §2.2 仍留空的项（U-01~U-05/07/08/09/10 已闭环；U-06 **V1 挂起**；U-11/12/13 未闭环）；
2. **V1（M0.2）已挂起（用户决定）**：三路实测 + few-shot 复审 EXP-V1-004（首次 qwen 0.50 / ds 0.35 仍 No-Go，qwen 拒止误调用 15→0）已留痕 `experiments/v1/summary-EXP-V1-004.csv`；处置路径收窄（**参数归一化纠错已实测 uplift=0 否决**，EXP-V1-NORM）。**P5/P6 结论（2026-09-30）**：P5 Schema 简化负结果（已回退 `tools_v2.json`）+ P6 多工具拆步（方案 B）负结果（EXP-V1-009 vs 010：多工具 qwen 40%→20%、ds 13.3%→0%）→ **多工具档 No-Go 处置改指 P7 方案 A（云编排）**；ISS-024 修复（few-shot 真生效）为新基准（qwen 0.60→0.68、ds 0.52→0.56），单工具档 57%/67% 为独立 blocker；
3. **V2（M0.3）**：**真 BM25 稀疏对标已闭环（EXP-V2-BM25，2026-09-28）**——ParadeDB 真 BM25（ngram）sparse `Recall@5`=0.90 vs Milvus 0.92、hybrid 打平 0.91（K-V2-1 正解建索引，`experiments/v2/raw/EXP-V2-BM25.md`）；**压力档已实测（EXP-V2-LOAD，2026-09-28）**——10 万块 Milvus P95 5.6 ms/1.28 GB vs pgvector 170.6 ms/0.33 GB（`experiments/v2/raw/EXP-V2-LOAD/`），M0.3 条件项全部解除；
4. **V4b（M0.5）已由「中间区间」升 Pass（2026-09-29 干净机重测，EXP-V4B-CLEANRM-<WORKSTATION>）**：压测中间区间处置 **落地清单已固化 p0-report-v4b-resources §12.3**（检索/状态/时序/LLM 四档命令，以 `compose.base.yml` 为基准）；§9.1 降级代价表的 **P95 冷加载已由【待实测】回填为实测**（qwen 8.90s / r1 9.00s，p0-report-v4b-resources §6.1）；**2026-09-29 本机干净基线重测宿主峰值 17.89GB ≤24GB → Pass**（历史 26.38GB 中间口径保留，含多项目共存因子，不追改）；
5. **M0.6 门禁重评**：M0.3（V2 条件项全解除 + V3 闭环）、**M0.5（V4b 升 Pass）均闭合**；仅剩 **M0.2（V1 处置待定）** 未闭环；逐项复核后重评 P0 是否放行。

---

## 修订记录

| 日期 | 修订人 | 修订原因 | 影响范围 |
|---|---|---|---|
| 2026-09-24 | 本人 | 初始建立：总结本轮 Phase 0 交付物落地全过程 | — |
| 2026-09-24 | 本人 | 增补 §二「完整任务清单」，按已完成/未完成分列，未完成项留空待确认并附推荐方案 | §二（整体并入原有各节，重建文档结构） |
| 2026-09-24 | 本人 | **执行 T1.1 `.wslconfig` 安装并核验**：复制 + `wsl --shutdown` + 重启 Docker，live `docker info`≈20GB/10vCPU/8GB，基线升 v2；同步 U-01、B-1、M0.1 及各文档状态（R2/R3/R-V4b-1/ISS-007/L-01 闭环）；C 清单重编号 | §二、§三（M0.1）、§四、§五 |
| 2026-09-24 | 本人 | **T1.9 授权定稿（文档层 + 实物层）**：裁定 **OSS + 自研 Sparkplug B 解码器（≤2 天）**，判「需降级·有条件通过」；解 U-02/B-4/M0.1 授权阻塞；镜像实物层已复核 `tdengine/tsdb:3.3.8.0` 无官方连接器（`reports/p0-report-v3-ingest-license.md`） | §二（U-02）、§四（M0.1）、§五（B-4）、§六 |
| 2026-09-24 | 本人 | **T1.9 判定全链路同步一致性**：将「可用（Free Tier）」回退为「需降级（OSS + 自研解码器）」并同步所有关联状态文档——prj-ledger-known-issues（ISS-010 主表/对照/详细块）、prj-ledger-risk-register（R8/R-V3-1/R-V3-5/R-新4/R16/ISS-010 对照）、p0-handover-p1（L-03/ISS-010/M0.1/M0.3/V3/P0-2/承接#3/6.2/§2.7/修订记录）、p0-gate-review（M0.1/M0.3/V3/交付物表/B-2）、p0-spec-gate-criteria（M0.1/M0.3）、prj-spec-schema-mapping（R-V3-1）、reports/README（索引/授权风险）、p0-checklist-daily（T1.9/D1-P3/M0.1/勾选）、prj-ledger-version-lock（TDengine/taosX/红线提示——镜像由 `tdengine/tdengine:latest` 整改为 `tdengine/tsdb:3.3.8.0`）、compose.base.yml（镜像名+注释）；D1-status 保留为历史快照不回溯 | §二、§四、§五、§六、各关联文档 |
| 2026-09-24 | 本人 | **文档重命名 + T1.9 落地同步**：文件更名为「p0-summary-phase0-2026-09-30.md」；同步 T1.9 落地选型闭环（C-22 新增）——自研解码器方案与工期≈1.9 人日（`docs/p0-design-sparkplug-decoder.md`）、映射 JSON（`configs/decoder_schema_mapping.json`）、编排（`docker/compose.ingest.yml`）、TDengine/解码器依赖锁定（prj-ledger-version-lock §二）；同步 §三 清点（docs 15 / configs+docker 新增）、§2.2 的 U-05/U-08、§六 下一步（进入编码阶段的前提） | 标题、§二（C-22 / U-05 / U-08）、§三、§六、修订记录 |
| 2026-09-24 | 本人 | **V1 本地实测完成 + U-04 版本已决同步**：V1 本地两模型实测 120 组 / 296 条已产出（判据均 No-Go，8 指标回填 `reports/p0-report-v1-tool-call.md` §四）；U-04 Ollama 版本已决锁定 0.34.2（`docs/prj-ledger-version-lock.md` §二.2.3 已登记）；同步 §四 门禁判定（V1 无法判定 / V3 条件通过）、§六 下一步第 4 点 | §二（U-04 / U-06）、§四、§六、修订记录 |
| 2026-09-25 | 本人 | **V2 检索实测完成并回填（U-07 闭环，2026-09-25）**：jieba 32/32、Milvus 原生 BM25 对中文可用（混合 `Recall@5`=0.91 ≥ 0.90）、6 组质量结果回填 `reports/p0-report-v2-hybrid-retrieval.md` §4.4、判据 Pass、参数基线选定值回填；BGE-M3/ParadeDB/Python 依赖锁入 `docs/prj-ledger-version-lock.md` §二.2.2/§二.2.8；同步 §四 验证项判定（V2=条件 Pass）、§六 下一步第 4 点；压力档暂缓待 D5；登记 K-V2-1（ParadeDB 真 BM25 悬置，稀疏对标未闭环） | §二（U-05/U-07）、§四（V2 判定）、§五（K-V2-1）、§六、修订记录 |
| 2026-09-24 | 本人 | **V4b 压测完成 + V5/M0.4 状态同步（2026-09-24）**：V4b 全组件压测（S0–S8）实测完成，口径B 峰值 26.38GB>24GB、超 9.9%≤10% → **中间区间（分组启动）**；V5（U-10）T5.1–T5.7 全 Pass → **M0.4 达成**；同步 U-09、§四 里程碑与验证项判定、D-04/D-05 裁决、B-3 解除、§六 下一步 | §二（U-09/D-04/D-05）、§四、§五（B-3）、§六、修订记录 |
| 2026-09-28 | 本人 | **云端 baseline 模型锁定 + V1 智能校验口径复核（U-06 补充）**：EXP-V1-002 云端上界实测 Qwen/Qwen3.8-27B 首次成功率 0.60，已锁入 `docs/prj-ledger-version-lock.md` §三 第 10 行、`env/cloud.json` `is_locked=true`；U-06 结论维持 **M0.2 = 未通过（No-Go）**，下一步 = 复审 20 用例与 Tool Schema v1 后重测 | §二（U-06）、修订记录 |
| 2026-09-28 | 本人 | **V4b 中间区间处置落地 + K-V2-1 闭环同步（2026-09-28）**：V4b 处置落地——分组启动 + 按需加载清单固化 `reports/p0-report-v4b-resources.md` §12.3（检索/状态/时序/LLM 四档命令），§9.1 降级代价表 P95 冷加载由【待实测】回填为实测（qwen 8.90s / r1 9.00s，§6.1），p0-gate-review §三.1 V4b 行同步；V2 K-V2-1（ParadeDB 真 BM25）技术链路已闭环；同步 §六 进度行 / 第 4、5 点、§四 验证项判定 | §四、§六、修订记录 |
| 2026-09-28 | 本人 | **真 BM25 稀疏对标闭环（EXP-V2-BM25，M0.3 补齐）**：为 `kb_chunks` 建 `USING bm25`+ngram 索引（`experiments/v2/raw/bm25_init.sql`），跑通 Milvus vs ParadeDB 真 BM25 对标——sparse `Recall@5` 0.92/0.90、hybrid 打平 0.91，显式声明 ngram 子串 vs jieba 语义口径差异，Milvus 仍主路线；tsvector 降级淘汰，pgvector 稀疏由 0→0.90；V2 判定由「条件 Pass（稀疏对标划 P1）」更新为「条件 Pass（真 BM25 对标已闭环，压力档暂缓）」；M0.6 重评依赖收敛为 V1 处置 / V2 压力档 / V4b 分组启动落地 | §四（M0.3/V2/M0.6）、§六（第 3/5 条）、修订记录 |
| 2026-09-28 | 本人 | **压力档闭环（EXP-V2-LOAD，M0.3 条件项全解除）**：新增 `v2_synth_corpus.py`/`v2_load_test.py`，`v2_pg_build.py` 改 5433+bm25+sparse，Milvus sparse-only 建库隔离 embedding；三档延迟 P95/内存峰值/建库耗时实测（10 万块 Milvus 5.6 ms/1.28 GB vs pgvector 170.6 ms/0.33 GB，均 ≪ Docker ≈20 GB）；V2 由「条件 Pass（压力档暂缓）」更新为「**Pass**」，M0.3/M0.6 理由更新，M0.6 重评依赖收敛为 V1 处置 / V4b 分组启动落地 | §四（M0.3/V2/M0.6）、§六（第 3/5 条）、修订记录 |
| 2026-09-28 | 本人 | **参数归一化纠错评估否决同步（EXP-V1-NORM）**：新建 `scripts/param_normalizer.py` + `judge_tools.py --normalize`，对 EXP-V1-004 重判 217 条记录 0 变化、uplift=0；归一化路径关闭，V1 处置收窄为 用例/Schema 复审 / 承认 7B 上界；同步 M0.2 行、§四 V1 行、§六 第 2 点 | §四（M0.2/V1）、§六（第 2 条）、修订记录 |
| 2026-09-28 | 本人 | **P0 遗留收口（文档/登记同步）**：U-06（V1）处置路径表述收窄（参数归一化已否决）已同步；§三 交付物清点登记 `param_normalizer.py` + EXP-V1-NORM（scripts 计 5 执行器 + 1 工具） | §二（U-06）、§三（3.1/3.2）、修订记录 |
| 2026-09-28 | 本人 | **判据分档重校 + 云端约束重测 + 多工具架构切分同步（U-06）**：云端约束解码（EXP-V1-005）首次 0.55 仍<90% 单线，支撑判据按类型分档重校（`docs/p0-spec-gate-criteria.md` §3.1.1）与多工具架构切分（`docs/p0-decision-model-role.md` §4.6）；U-06 处置路径由「收窄为用例/Schema 复审/承认 7B 上界」更新为「参数归一化纠错已实测否决 + 判据按类型分档重校 + 云端工具调用转正 + 多工具架构切分」 | §二（U-06）、修订记录 |
| 2026-09-28 | 本人 | **架构整线化结论校正（U-06，EXP-V1-004 few-shot 按分档重判）**：本地单工具 33%/28%、参数校验 75%/50%、多轮 67%/67% 均未过 85% 线 → 架构由「混合（本地保留单工具/参数校验）」修正为「**整线云端工具调用转正 + 多工具架构切分（拆单工具多轮）**」，仅 qwen「无效拒绝（100%，纯安全拒绝）」可本地留（deepseek 无效拒绝 67% 不可靠）；U-06 处置路径与状态按分档重判为据更新。**再补充（并入）：收回"整线/全上云"过度外推**——V1 判据只测 R-2/R-3，正确口径 = **「R-2/R-3 工具调用上云 + 多工具架构切分」；R-1/R-4/R-5/检索/写操作/审计/有效拒绝/降级兜底保持本地（非全上云）**；**新增未验证项 ISS-014（R-4 本地证据归纳/诊断可用性）**，现值 0.67 为多轮工具调用分、非证据归纳分，待 P1 专项测试；同步 U-06 行 | §二（U-06）、修订记录 |
| 2026-09-30 | 本人 | **P6 结论回填（V1 仍 No-Go）**：P6「多工具架构切分（方案 B 拆单工具多次调用）」落地并实测——EXP-V1-009（拆步）vs EXP-V1-010（修复 ISS-024 后单响应基准）干净 A/B，多工具档 qwen 40%→20%、ds 13.3%→0%，**方案 B 为负结果**（其余四档基本持平）；机制为 qwen 编排障碍消除后失败收窄到参数值错、ds 无收益；**多工具档 No-Go 处置改指 P7 方案 A（云编排）**。同步 §二（U-06/U-13）、§四（M0.2/V1 判定）、§六 第 2 点；判据口径见 `docs/p0-spec-gate-criteria.md` §3.1.1 | §二（U-06/U-13）、§四（M0.2/V1）、§六、修订记录 |
| 2026-10-08 | 单人（本人） | 文档同步整理：加「历史留痕」横幅（正文结论一字未改）；文件重命名 → `p0-summary-phase0-2026-09-30.md` | 头部 / 索引 |
