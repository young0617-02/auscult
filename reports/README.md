# reports/ 报告索引与填写纪律

> 项目：云侧工业 IoT 诊断 Agent 系统（`<REPO>`）
> **阶段状态（2026-10-10 更新）**：**Phase 0–6 全部完成** —— Phase 0 已于 2026-10-08 过闸放行（`M0.6`）；Phase 1–5 依次交付（`M1.4`/`M2.1–M2.4`/`M3.5`/`M4.1–M4.4`/`M5.4`）；**Phase 6 于 2026-10-10 正式收口（`M6.4`）**。全项目阶段状态的唯一凭据 = `docs/p6-gate-closure-2026-10-10.md`。
> **命名规范**：本目录文件按 `docs/prj-spec-document-standard.md` 统一命名（`<阶段>-<类型>-<主题>[-<日期>].md`）；2026-10-08 前的旧名见该规范 §六 映射表，2026-10-10 的 2 项收口后纠错见其 **§6.5**
> 主场景：离心泵轴承振动异常诊断
> 本索引对应计划：`plan/p0-plan-detailed-d1-d10.md` §三、§六（已执行完毕，🟡 留档）
> ⚠️ **索引滞后说明（2026-10-10 修正）**：本索引此前**长期只登记 Phase 0 的 25 份报告**，而 `reports/` 实有 55 份 —— P1（11）/ P2（8）/ P3（2）/ P5（7）共 **28 份漏登记**。本次已补齐（见 §一 P1–P5 段），并按 `docs/prj-spec-document-standard.md` §八 第 3 条落实「新增即登记」。

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
| `reports/p0-report-v1-cases-revision-2026-10-20.md` | p0 | V1 用例集修订（**`v1-019` 重释义**） | — | — | 单人（本人，按所有者判决 A） | **判据考点与 ADR-007/产品工具面对齐**：仅 1 条用例（禁调 `generate_report`）+ 判分器「禁调」语义 + 复测 No-Go（多轮 66.7%，新登记 `ISS-052`，2026-10-20） |
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

**Phase 1（数据接入与知识库构建，2026-10-08 ~ 10-09，11 份）**

| 报告文件 | 阶段 | 对应验证项 | 对应任务 | 出口里程碑 | 责任人 | 当前状态 |
|---|---|---|---|---|---|---|
| `reports/p1-mineru-spike.md` | p1 | MinerU 解析 Spike（B1-Spike） | P1-D1 | — | 单人（本人） | ✅ **已实测 · 通过**（3 类样本判据 4/4） |
| `reports/p1-report-port-forward-fix-2026-10-08.md` | p1 | D1 宿主←容器端口转发失效的故障修复 | P1-D1（A1 骨架 / 环境复用） | — | 单人（本人） | 🟡 **时点快照（2026-10-08）**：故障已修复，D1-A1（MQTT 链路）与环境复用均达成；端口事实另见 `env/p1-audit-ports-2026-10-08.md` |
| `reports/p1-d2-a2-telemetry-2026-10-08.md` | p1 | A2 时序 Schema 落地 + Sparkplug B 模拟数据生成器 | P1-D2 | — | 单人（本人） | ✅ **已实测 · 达成**（`configs/tdengine/schema_master.sql` + `scripts/gen_sparkplug.py` 自检通过 + 端到端落库） |
| `reports/p1-d3-alarm-2026-10-08.md` | p1 | A3 告警引擎（阈值 + 滑动窗口 + Redis 去重）+ A4 端到端联调 | P1-D3 | — | 单人（本人） | ✅ **已实测 · 达成**（`configs/alarm_rules.yml` + `scripts/alarm_engine.py` 自检 + 全链路实测） |
| `reports/p1-d3-d4-b1-corpus.md` | p1 | B1 全量文档解析（MinerU） | P1-D3/D4 | — | 单人（本人） | ✅ **已实测 · 通过**（判据达成；Spike 的全量扩展） |
| `reports/p1-d4-b2-chunk.md` | p1 | B2 Parent-Child 分块 | P1-D4 | — | 单人（本人） | ✅ **已实测 · 通过**（判据达成；结块 Schema **v1**，36 子块） |
| `reports/p1-d4-d5-b3-milvus.md` | p1 | B3 Milvus 建库（向量化 + 冒烟） | P1-D4/D5 | — | 单人（本人） | ✅ **已实测 · 通过**（建库 + 链路冒烟；复用 V2 建库参数） |
| `reports/p1-d5-d7-b4-triples.md` | p1 | B4 三元组抽取（终态 · v2） | P1-D5–D7 | — | 单人（本人） | ✅ **已实测**：受控词表 v2 + 云端 27B 约束解码；Neo4j **91 节点 / 94 关系**；v2 准确率 **93%** |
| `reports/p1-d7-d8-b5-meta.md` | p1 | B5 元数据与维修工单导入（PostgreSQL） | P1-D7/D8 | — | 单人（本人） | ✅ **已实测**（`scripts/load_meta.py`，`ON CONFLICT DO UPDATE` 幂等） |
| `reports/p1-d8-d9-b6-consistency.md` | p1 | B6 三写一致性（Outbox + 补偿队列 + 对账） | P1-D8/D9 | — | 单人（本人） | ✅ **已实测**（失败注入下对账零差异、补偿队列可自愈） |
| `reports/p1-d9-gate-judgment.md` | p1 | 八项量化门禁判定（合并决策） | P1-D9 | **M1.4** | 单人（本人） | ✅ **八项门禁全部达标 → `M1.4` 达标放行**；三元组「仅作线索」限制已解除，7 条错配已下行留痕 |

**Phase 2（混合检索，2026-10-09，8 份）**

| 报告文件 | 阶段 | 对应验证项 | 对应任务 | 出口里程碑 | 责任人 | 当前状态 |
|---|---|---|---|---|---|---|
| `reports/p2-d1-w1-query-rewrite.md` | p2 | W1 查询改写器 | P2-D1 | — | 单人（本人） | ✅ **已实测**（`scripts/query_rewrite.py`，`--selftest` 0 失败） |
| `reports/p2-d1-w2-recall.md` | p2 | W2 多路召回编排（约束 P2-R4） | P2-D2/D3/D8 | — | 单人（本人） | ✅ **已实测**（三路 `--selftest` 0 失败；真实召回三路命中、`degraded_routes=[]`） |
| `reports/p2-d1-w3-rrf.md` | p2 | W3 RRF 融合 | P2-D4 | — | 单人（本人） | ✅ **已实测**（`scripts/fuse_rrf.py`，真实融合 top5 排序正确） |
| `reports/p2-d2-w4-w5-rerank-evidence.md` | p2 | W4 重排 + W5 证据组装 | P2-D2/D10 | — | 单人（本人） | ✅ **已实测**（probe/rerank/assemble 三脚本 0 失败；W2→W5 贯通、`degraded=false`） |
| `reports/p2-d3-m2-metrics.md` | p2 | **M2.3 配套评测集检索质量指标** | P2-D3 | **M2.3** | 单人（本人） | ✅ **四项指标全部达标**（D7 消融后 RRF-only 最优）：`Recall@5` **1.0** / `MRR` **0.7569** / `NDCG@5` **1.0** / `P95` **86.1 ms**；RAW `experiments/p2/m2/` |
| `reports/p2-d3-w6-retrieve-knowledge.md` | p2 | W6 `retrieve_knowledge` 工具实现 | P2-D3/D9/D11 | — | 单人（本人） | ✅ **已实测**（`--selftest` 0 失败；真实调用证据包结构完整） |
| `reports/p2-d3-w7-retrieve-tools.md` | p2 | W7 工具链接入 R-2/R-3 评测 | P2-D3 | — | 单人（本人） | ✅ **云端全量 16/16 Pass**（单工具 100% ≥85%）；RAW `experiments/p2/w7/` |
| `reports/p2-summary.md` | p2 | **Phase 2 阶段总结** | P2-D1–D20 | **M2.1–M2.4** | 单人（本人） | ✅ **四里程碑全部达成**；移交 `docs/p2-handover-p3.md` |

**Phase 3（Agent 工作流实现，2026-10-09，2 份）**

| 报告文件 | 阶段 | 对应验证项 | 对应任务 | 出口里程碑 | 责任人 | 当前状态 |
|---|---|---|---|---|---|---|
| `reports/p3-reliability.md` | p3 | D20 可靠性测试（杀进程恢复 / 重复 resume / Redis 驱逐防护） | P3-D20 | **M3.4** | 单人（本人） | ✅ **已实测 · Pass**（脚本 `scripts/test_d20_reliability.py`） |
| `reports/p3-summary.md` | p3 | **Phase 3 验收汇总** | P3-D1–D25 | **M3.5** | 单人（本人） | ✅ **`M3.5` 达成**（Trace/指标齐备；E2E 通过；移交 Phase 4） |

**Phase 4（前端与集成，2026-10-09）**

| 报告文件 | 阶段 | 对应验证项 | 对应任务 | 出口里程碑 | 责任人 | 当前状态 |
|---|---|---|---|---|---|---|
| *(缺口)* **无 `reports/p4-*.md`** | p4 | 七类页面 + Socket.IO + Nginx 单入口 | P4-D1–D20 | **M4.1–M4.4** | 单人（本人） | ⚠️ **如实登记文档资产缺口**：本阶段未产出独立 `reports/` 报告（仅有移交清单 `docs/p4-handover-p5.md`）；实况以 `README.md` §3.1（Playwright E2E **9/9**）与移交清单为准，**不因收口而补写** |

**Phase 5（评测与硬化，2026-10-09 ~ 10-10，7 份）**

| 报告文件 | 阶段 | 对应验证项 | 对应任务 | 出口里程碑 | 责任人 | 当前状态 |
|---|---|---|---|---|---|---|
| `reports/p5-eval.md` | p5 | W1 评测体系硬化（**十二项指标**） | P5-D1–D5 | **M5.1** | 单人（本人） | ✅ **8 达标 / 1 未达标（`P95` 端到端含生成 9,248.8 ms vs 3 s）/ 1 代理口径**；评测集 `evals/m2_acc_set.jsonl`（12 题）+ RRF-only + 全本地 |
| `reports/p5-kappa.md` | p5 | 标注一致性（Cohen's Kappa） | P5-W1-D2 | M5.1 | 单人（本人） | ✅ **`κ` = 0.8344 ≥ 0.70**（第二标注者 = 本地 LLM；规范 `docs/prj-spec-labeling.md` 修订一轮全留痕） |
| `reports/p5-hallucination.md` | p5 | 幻觉率（3 级评分） | P5-W1-D4 | M5.1 | 单人（本人） | ✅ **幻觉率 0.0%**（C 级 0/12）；B 级警告 2 条根因是语料数值冲突、非编造 |
| `reports/p5-perf.md` | p5 | W5/D14 端到端压测（Locust 2.46.7） | P5-D14 | **M5.4** | 单人（本人） | ✅ **Pass**：三档 + 30 min 稳定性全程 0% 服务器错误；u10/u20 `P95` <200 ms、u50 `P95`=940 ms；宿主峰值 **20.73 GB ≤ 24 GB**；RAW `experiments/p5/w5/` |
| `reports/p5-security.md` | p5 | W4/D12–D13 安全回归 | P5-D12/D13 | M5.3 | 单人（本人） | ✅ **8/8 PASS**（`scripts/test_p5_d12_security.py`） |
| `reports/p5-backup.md` | p5 | W3/D11 备份恢复演练 | P5-D11 | M5.3 | 单人（本人） | ✅ **Pass**：PG RTO ≈**3.1 s**、Neo4j/Milvus 冷备窗口 16 s / 5.3 s；**RPO 定时化未落地**，挂 P6 运维待办 |
| `reports/p5-summary-phase5-2026-10-10.md` | p5 | **Phase 5 验收汇总（阶段权威）** | P5-D15 | **M5.4** | 单人（本人） | ✅ **`M5.1`–`M5.4` 全达成 + 停止条件 3/3**；2026-10-10 由 `reports/P5-summary.md` 按命名规范**正名**（正文结论一字未改，见该文件修订记录） |

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
├─ p0-report-v1-cases-revision-2026-10-20.md        # v1-019 重释义（禁调写操作）+ ISS-052
├─ p0-analysis-iss036-tier-split-2026-10-06.md      # ISS-036 拆档量化
├─ p0-audit-v1-refusal-2026-10-06.md                # 拒止/澄清专项 + ISS-032
├─ p0-audit-v1-single-tool-tier-2026-10-07.md       # H17 单工具档归因
├─ p0-audit-status-2026-09-30 / -10-05 / -10-07.md  # 状态审计与核查（🟡 时点快照）
├─ p0-summary-project-2026-09-28 / -09-29.md        # 全景快照（🟡）
├─ p0-summary-phase0-2026-09-30.md                  # 阶段总结（原在 plan/，2026-10-08 移入）
├─ p0-report-regression-suite-2026-10-06.md         # ISS-030 回归套件
├─ p0-report-vcs-baseline-2026-10-06.md             # Git 基线
├─ p0-audit-doc-sync-2026-10-08.md                  # 本次文档整理核查报告
├─ p1-mineru-spike.md                               # P1-D1 MinerU 解析 Spike
├─ p1-report-port-forward-fix-2026-10-08.md         # P1-D1 端口转发故障修复（🟡 快照）
├─ p1-d2-a2-telemetry-2026-10-08.md                 # A2 时序 Schema + Sparkplug B 生成器
├─ p1-d3-alarm-2026-10-08.md                        # A3 告警引擎 + A4 端到端联调
├─ p1-d3-d4-b1-corpus.md                            # B1 全量文档解析
├─ p1-d4-b2-chunk.md                                # B2 Parent-Child 分块
├─ p1-d4-d5-b3-milvus.md                            # B3 Milvus 建库
├─ p1-d5-d7-b4-triples.md                           # B4 三元组抽取（终态 v2，准确率 93%）
├─ p1-d7-d8-b5-meta.md                              # B5 元数据与工单导入（PG）
├─ p1-d8-d9-b6-consistency.md                       # B6 Outbox + 补偿队列 + 对账
├─ p1-d9-gate-judgment.md                           # ★ 八项门禁判定 → M1.4 放行
├─ p2-d1-w1-query-rewrite.md                        # W1 查询改写
├─ p2-d1-w2-recall.md                               # W2 多路召回编排
├─ p2-d1-w3-rrf.md                                  # W3 RRF 融合
├─ p2-d2-w4-w5-rerank-evidence.md                   # W4 重排 + W5 证据组装
├─ p2-d3-m2-metrics.md                              # ★ M2.3 检索质量（Recall@5 1.0 / P95 86.1ms）
├─ p2-d3-w6-retrieve-knowledge.md                   # W6 retrieve_knowledge 工具
├─ p2-d3-w7-retrieve-tools.md                       # W7 工具链评测（16/16）
├─ p2-summary.md                                    # ★ Phase 2 总结（M2.1–M2.4）
├─ p3-reliability.md                                # D20 可靠性（M3.4）
├─ p3-summary.md                                    # ★ Phase 3 验收汇总（M3.5）
├─ *(缺口)* 无 p4-*.md                              # ⚠️ Phase 4 未产出独立报告，见 §一 缺口行
├─ p5-eval.md / p5-kappa.md / p5-hallucination.md   # W1 评测硬化（M5.1）
├─ p5-perf.md / p5-security.md / p5-backup.md       # W5 压测 / W4 安全 / W3 备份（M5.3–M5.4）
├─ p5-summary-phase5-2026-10-10.md                  # ★ Phase 5 验收汇总（M5.4，阶段权威）
└─ daily/
   ├─ README.md                    # 日报规范
   └─ D<n>-status.md               # 当日状态记录，n ∈ 1..10
```

> **计数（2026-10-10 实测）**：`reports/` 共 **55 份 `.md`** —— P0 24 份 + P1 11 份 + P2 8 份 + P3 2 份 + P5 7 份 + 索引与日报 3 份（本文件、`daily/README.md`、`daily/D1-status.md`）。

> **规则摘要**（全文见 `docs/prj-spec-document-standard.md`）：全小写 ASCII kebab、禁止空格与全角括号；`<阶段 p0|p1|prj>-<类型 plan|design|spec|decision|report|analysis|audit|review|gate|summary|handover|checklist|template|ledger>[-<主题>][-<YYYY-MM-DD>]`；**快照必带日期、活文档不带日期**（改在文件头写「最近更新」）；历史结论**只加横幅、不改正文**。原约定的 `project-summary-YYYY-MM-DD.md` / `status-audit-YYYY-MM-DD.md` 范式已被上述规则取代（旧名映射见规范 §六）。

- 新增报告必须同步登记到本索引第一节表格；
- 报告一经判定，结论不得静默修改；修正须在本报告末尾追加"修订记录"（日期 / 修订人 / 修订原因 / 影响范围）。

---

## 六、当前全局状态摘要（**2026-10-10 全面复核**；首版为 D10 交付物复核，2026-10-08 曾复核一次）

| 维度 | 状态 |
|---|---|
| 环境基线 | T1.1 `.wslconfig` **已安装并核验**（`docker info`≈20GB/10vCPU，基线升 v2）；T1.2/T1.3/T1.4 已完成 → 详见 `reports/daily/D1-status.md` |
| Schema | **活动基线 = `schemas/tools_v4.json`**（含测点目录，`EXP-M02-040` 即此配置）；`tools_v1.json` 为 D1 冻结的历史快照（5 工具），`v2`/`v3` 留档、`v5` 为 H3 实验版（实测否决、未采纳）；**`tools_v4_agent.json` = 路径 C 只读工具面**（2026-10-20 由 `tools_v4.json` 派生、去掉写操作 `generate_report`，用于 `EXP-P7-GATE3`，与产品 Agent 4 只读工具面对齐） |
| 授权风险 | **T1.9 TDengine 授权已定稿**（2026-09-24）= 需降级（OSS + 自研 Sparkplug B 解码器 ≤2 天），授权不阻塞 |
| 文档交付物 | ✅ **齐备**：`docs/` **43 份**（判据/台账/风险/版本锁/范围/移交/决策/模板/**命名规范 `prj-spec-document-standard.md`** / **需求主流程 `prj-design-requirements-main-flow.md`** / **用户操作手册 `prj-guide-user-manual.md`**〔2026-10-16 实跑验证 + `docs/images/manual/` 截图资产〕 + **Phase 6 收口新增**：架构 / 部署 / 运维 / API / 数据字典 / ADR-001..009 / **`p6-gate-closure-2026-10-10.md`（阶段状态唯一凭据）** / P7 设计 `p7-design-redis-cache-layer-2026-10-16.md` / **P7 Agent 化设计 `p7-design-agent-diagnosis-2026-10-19.md`** / **P7 路径 D 立项 `p7-design-gate-product-agent-2026-10-20.md`** / **P7 U2 判决 `p7-decision-async-diagnosis-2026-10-20.md`**〔产品形态 = 异步诊断 + 实时进度〕/ **P7 P1 变更 `p7-change-agent-param-guidance-2026-10-21.md`**〔参数取值约定，2026-10-21 实测：smoke 15/15 → D2 整轮六档首次全绿 74/75 = 98.67%，登记 `experiments/v1/EXP-P7-P1.md`〕）；`plan/` **14 份**（Phase 0–6 计划与设计，P0–P5 计划均为 🟡 留档）；`reports/` **56 份**（P0 25 / P1 11 / P2 8 / P3 2 / P5 7 + 索引与日报 3；**P4 无独立报告，见 §一 缺口行**）。~~项目全景「最新」= 09-29~~ → 三份全景均为 🟡 时点快照，**当前状态查 `docs/p6-gate-closure-2026-10-10.md`** |
| 评测集 | ✅ **就绪**：`evals/golden_set_v1.jsonl`（50 条）、`evals/v1_cases.jsonl`（20 条，`ISS-029` 路径 B + **2026-10-20 路径 C**：`v1-019` 换为真实多轮上下文考点 `query_graph`）、`evals/v2_cases.jsonl`（25）、`evals/v3_cases.jsonl`（25）、`evals/r4_cases.jsonl`（20）、`evals/corpora_v1/corpus_100.jsonl`（100 块）、**`v1_refusal_transfer_v1.jsonl`（无泄漏迁移集）**、**`v1_adversarial_v1.jsonl`（自建对抗集）**、`probe-v1-004-2026-10-07.jsonl`；原件归档 `v1_cases-pre-2026-10-05/06/20.jsonl`、`v1_refusal_transfer_v1-pre-2026-10-06.jsonl`（**顶层 `.jsonl` 共 14 个 + 语料 1 个**）；**只读工具面 `schemas/tools_v4_agent.json`**（路径 C：由冻结的 `tools_v4.json` 派生、去掉写操作 `generate_report`） |
| 执行器 | ✅ **就绪且自检通过**：`scripts/` 共 **86 个 Python 脚本**（**39 个含 `--selftest`**，2026-10-20 新增 `smoke_agent_cloud.py` 云端 Agent 实跑冒烟）+ 2 个 PowerShell；权威入口 = `run_e2e.py`（规则门 → 云端）+ `aggregate_runs.py`（§3.1.3 聚合裁决）+ `gate_rules.py`/`refusal_gate.py`/`judge_tools.py`/`llm_adapter.py` |
| 回归测试 | ✅ `tests/` **260 用例**（2026-10-21 实测全绿，约 106 s，离线秒级、零云调用；2026-10-14 新增 E6b/E6c 覆盖 `ISS-048` diagnose 自循环重试；**2026-10-19 P7 Agent 化新增 32 例**：LLM 客户端/工具注册/Agent 循环/图模式切换/可观测化；**2026-10-20 路径 C 新增 5 例** + **路径 D harness 6 例**（打桩必装 ×2 / 消息口径 / 离线自检 / 审计不落 reports / raw 可聚合，见 `ISS-053`）；**2026-10-21 P1 新增 7 例**：参数取值约定（映射齐全 / 1h 禁令 / 拒止规则保留 / 无用例编号泄漏 / 体积上限））；✅ **`pytest==9.1.1` 已锁入 `requirements.txt` 与 `docs/prj-ledger-version-lock.md` §二.2.10**（原「未登记进依赖锁」残留项已闭环）；前端 `client/tests/unit` vitest **53 例**（2026-10-19 实测全绿） |
| 验证实测（Phase 0） | ✅ **V1–V5 均已实测**：V1 **Pass（2026-10-08 同日多轮聚合口径；前期 No-Go → 中间区间）** / V2 **Pass（混合 Recall@5 0.91，真 BM25 + 压力档闭环）** / V3 **封板定稿**（四类边界 4/4、`query_sensor` P95 ≈26.2 ms） / V4b **Pass（干净机重测 17.89GB，历史 26.38GB 中间口径保留）** / V5 **Pass（PG 路线）** / V4a、V6、V7 见门禁行；原始数据 `experiments/**/raw/` |
| 验证实测（Phase 1–5） | ✅ **均已达阶段门禁并出报告**：P1 八项量化门禁全达标（`M1.4`）｜P2 `Recall@5` 1.0 / `MRR` 0.7569 / `NDCG@5` 1.0 / `P95` 86.1 ms（`M2.1`–`M2.4`）｜P3 可靠性 D20 Pass（`M3.5`）｜P4 前端 E2E 9/9（`M4.1`–`M4.4`）｜P5 十二项指标 8 达标 + κ 0.8344 + 幻觉率 0% + 峰值 20.73 GB（`M5.1`–`M5.4`）→ 逐项见 §一 P1–P5 段 |
| 门禁 | ✅ **M0.1–M0.5 全部达成 → `M0.6` 于 2026-10-08 放行（P0 过闸）**（`reports/p0-gate-m02-verdict-2026-10-08.md` + `reports/p0-gate-review.md` 决策34）；✅ **`M1.4` / `M2.1`–`M2.4` / `M3.5` / `M4.1`–`M4.4` / `M5.1`–`M5.4` / `M6.1`–`M6.4` 全部达成 → 项目于 2026-10-10 正式收口（`M6.4`）**。**残余风险（收口 ≠ 风险消失）**：`P95` 端到端含生成 9.25 s 未达 3 s、F-2 数据库短连接排队、F-1 health 探测阻塞事件循环、RPO 未定时化、Neo4j 图谱数据未预置、`ISS-038`–`ISS-041` 登记不修 → `docs/p6-gate-closure-2026-10-10.md` §四 |
| 交付包 | ✅ **`deploy/`（compose + 四个一键脚本 + `.env.example` + `images.digest.md`）与 `demo/`（scenario + 预置告警 + 排练留档）已封版**；`M6.2` 干净环境实测 8 容器 up / 7 基建 healthy / `smoke.ps1` **6/6 PASS** |
| 时序数据（TDengine） | ✅ **样本数据已灌（2026-10-14）**：`init.ps1` 只建 schema，样本数据走「常驻 `self_decoder.py` + `gen_sparkplug.py`」生产链路单独灌入，实测 **10800 行**（3600×3 设备）、PUMP-A `vib_rms` 峰值 **4.855 mm/s**（越 ISO 10816 C 区上界）、2 个 5min 超限窗口；`query_sensor` 契约验证 3 设备 × 13 窗口 exit 0、`P95≈24.2ms`。复灌步骤见 `README.md` §五 |
| 归档 | 📦 3 份**非项目技术产物**（求职素材）已于 2026-10-08 移出 `reports/` → `archive/personal/`，见 `archive/README.md` |

> 详细判定与上游矛盾清单（Phase 0）见 `reports/p0-gate-review.md`；**全项目当前阶段状态的唯一凭据见 `docs/p6-gate-closure-2026-10-10.md`**。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-09-28 | 单人（本人） | **同步 V1 约束解码全量 + 云端上界实测新进展**：EXP-V1-003 约束解码全量闭环（格式退化根除、可解析率 1.00，首次 qwen 0.35 / deepseek 0.45，重试后 0.95/0.90）；EXP-V1-002 云端上界 **Qwen/Qwen3.8-27B** 首次成功率 0.60，已锁定入 `docs/prj-ledger-version-lock.md` §三 第 10 行、`env/cloud.json` `is_locked=true` | §六（V1 结论、门禁栏） |
| 2026-09-30 | 单人（本人） | **报告索引与目录约定同步实际文件状态**：§一 补登 5 份报告（p0-summary-project-2026-09-28 / p0-summary-project-2026-09-29 / p0-review-v1-criteria-r2 / p0-review-v1-criteria-r3 / p0-audit-status-2026-09-30）；§五 目录树补全并约定 `project-summary-*.md` / `status-audit-*.md` 命名范式；§六 评测集由 3 项补至 6 项、执行器由"五个脚本"更正为"18 个 Python 脚本（12 个含自检）" | §一、§五、§六 |
| 2026-10-08 | 单人（本人） | **补登（前几次会话新增报告未登记，本索引自 09-30 后未更新）**：`p0-report-v1-cases-revision`、`p0-audit-v1-refusal`、`p0-analysis-iss036-tier-split`、`p0-audit-v1-single-tool-tier`、`p0-audit-status-2026-10-05`、`p0-audit-status-2026-10-07`、`p0-report-regression-suite`、`p0-report-vcs-baseline`、`p0-gate-closeout-2026-10-07`、`p0-gate-m02-verdict-2026-10-08` 等 10 行（部分由当次会话登记，此处核对补齐）；**遗留问题：索引长期滞后于目录实况** → 已由 `docs/prj-spec-document-standard.md` §八 第 3 条确立「新增即登记」义务 | §一 |
| 2026-10-08 | 单人（本人） | **全量文档同步与命名整理**：① §一 表新增「阶段」列并按 `docs/prj-spec-document-standard.md` 重排，补登 `p0-summary-phase0-2026-09-30.md`（自 `plan/` 移入）与 `p0-audit-doc-sync-2026-10-08.md`（本次整理核查报告），并加「已移出 `archive/personal/` 的 3 份非项目产物」说明行；② **修正 5 行「实测待填入」的过期描述**（V1/V2/V3/V4b/V5 均已实测，逐一给出实测值与 🟡 时点标注）；③ 去掉 `project-summary-2026-09-29` 的「最新全景」称号（三份全景均为时点快照，当前状态改指 10-08 裁决报告）；④ §一 末补两条读法说明（`rN` ≠ 复审轮次、V1 双实验族 `EXP-V1-*` 与 `EXP-M02-*`）；⑤ §五 命名约定改为指向命名规范并给出新目录树；⑥ §六 全局摘要按实况更正（`docs` 16 份、`reports` 25 份、脚本 22 个〔16 含自检〕、回归 176 用例、活动 Schema = `tools_v4`、评测集补迁移集/对抗集与归档件、V2 由「条件Pass」更正为 **Pass**、门禁改为 **M0.1–M0.6 全部达成并放行** + 残余风险、新增「归档」维度）；⑦ 全文旧文件名引用已随重命名改写 | §一、§五、§六、修订记录 |
| 2026-10-10 | 单人（本人） | **Phase 6 收口后索引补齐与口径同步（零功能改动）**：① §一 补登 **P1（11 份）/ P2（8 份）/ P3（2 份）/ P5（7 份）共 28 份报告** —— 此前本索引长期只登记 P0 的 25 份，而 `reports/` 实有 55 份；并**如实登记 Phase 4 无独立 `reports/p4-*.md` 的文档资产缺口**（不因收口而补写）；② 文首阶段状态改为 **Phase 0–6 全部完成、`M6.4` 于 2026-10-10 收口**，当前状态改指向 `docs/p6-gate-closure-2026-10-10.md`；③ §五 目录树补 P1–P5 全部报告并加 55 份计数注；④ §六 全局摘要按实况更正（脚本 **84 个 Python + 2 个 PowerShell〔36 含 `--selftest`〕**、回归 **183** 用例且 `pytest==9.1.1` 已锁入依赖与版本锁、`docs/` **36** 份、`reports/` **55** 份、`plan/` **14** 份、新增「验证实测（Phase 1–5）」与「交付包」两行、门禁栏改为 M0.6 + M1.4 + M2.1–M2.4 + M3.5 + M4.1–M4.4 + M5.1–M5.4 + **M6.4 全部达成**）；⑤ `reports/P5-summary.md` 已按命名规范 `git mv` 为 **`reports/p5-summary-phase5-2026-10-10.md`**（正文结论一字未改），§一 与 §五 同步新名 | 文首、§一（P1–P5 段 + Phase 4 缺口行）、§五、§六、修订记录 |
| 2026-10-14 | 单人（本人） | **维护期数据/健壮性收尾后的索引同步**：① §六「回归测试」用例数 183 → **185**（新增 E6b/E6c 覆盖 `ISS-048` diagnose 自循环重试）；② §六 新增「**时序数据（TDengine）**」一行 —— 样本数据经「常驻 `self_decoder.py` + `gen_sparkplug.py`」链路灌入，实测 **10800 行**、PUMP-A `vib_rms` 峰值 4.855 mm/s（越 ISO 10816 C 区上界）、`query_sensor` 契约验证 exit 0 / `P95≈24.2ms`，复灌步骤指向 `README.md` §五；③ 同批台账新增 `ISS-046`（旧接入栈容器端口冲突，可规避）/ `ISS-047`（device_id 白名单三口径漂移，已修复）/ `ISS-048`（LLM 不可达无自动重试，已修复） | §六、修订记录 |
| 2026-10-20 | 单人（本人，按用户指示执行） | **P7 云端实跑后的索引同步**：① §六「执行器」脚本数 85 → **86**（新增 `scripts/smoke_agent_cloud.py` 云端 Agent 实跑冒烟，含 `--selftest`；含 selftest 数 37 → 39）；② §六「回归测试」用例数 238 → **240**（新增 health 探针/runner 轨迹归集 2 例 + 测试隔离修复）；③ 文档交付物行维持 40 份（ISS-050/051 登记不新增文档） | §六、修订记录 |
| 2026-10-20 | 单人（本人，按所有者判决 A） | **`v1-019` 重释义后的索引同步**：① §一 补登 `p0-report-v1-cases-revision-2026-10-20.md`（`reports/` 55 → **56 份**，P0 24 → 25）；② §六 目录树补该报告；③ §二 评测集行补归档 `v1_cases-pre-2026-10-20.jsonl` + 重释义说明；④ 回归测试 240 → **243 例**（新增禁调语义 3 例） | §一、§二、§六、§八 |
| 2026-10-20 | 单人（本人，按所有者指示「先 C / 立项 D」+ U2 判决） | **路径 C / D 立项 / U2 判决后的索引同步**：① §二 文档交付物 `docs/` 40 → **42 份**（新增 `p7-design-gate-product-agent-2026-10-20.md` 路径 D 立项、`p7-decision-async-diagnosis-2026-10-20.md` U2 异步诊断判决）；② §六 目录树补该 2 份；③ 评测集行补只读工具面 `schemas/tools_v4_agent.json` 与 `v1-019` 路径 C 说明；④ 回归测试 243 → **245 例**（路径 C 锁：禁调零声明 / 合成禁调语义 / 只读工具面 / v1-019 上下文继承） | §二、§六、§八 |
| 2026-10-21 | 单人（本人，按所有者指示「先做 P1」） | **P1 参数取值约定后的索引同步**：① §二 文档交付物 42 → **43 份**（新增 `p7-change-agent-param-guidance-2026-10-21.md`）；② 回归测试 253 → **260 例**（提示词指引 7 例：映射齐全 / 1h 禁令 / 拒止规则保留 / 无 `v1-` 编号泄漏 / 体积上限） | §二、§八 |
| 2026-10-20 | 单人（本人，按所有者指示「开工 D」） | **路径 D harness 落地后的索引同步**：回归测试 245 → **251 例**（`tests/test_agent_gate.py` 6 例：打桩必装 ×2 / 消息口径 / 离线自检 / 审计不落 reports / raw 可聚合，对应 `ISS-053`）；**同日 v2 修复后 → 253 例**（+告警覆盖不泄漏 / 收口形态不进六档） | §六、§八 |
| 2026-10-19 | 单人（本人，按用户三项判决执行） | **P7 诊断 Agent 化后的索引同步（`docs/p7-design-agent-diagnosis-2026-10-19.md`）**：① `docs/` 计数 39 → **40**（新增 P7 Agent 化设计文档）；② §六「回归测试」用例数 185 → **240**（新增 32 例：LLM 客户端/工具注册/Agent 循环/图模式切换/可观测化；2026-10-19 实测全绿）并补前端 vitest **53 例**一行；③ 文档交付物行同步 40 份 | §六、修订记录 |
| 2026-10-16 | 单人（本人） | **用户操作手册建立后的索引同步**：① `docs/` 计数 36 → **39**（新增 `prj-guide-user-manual.md` 用户操作手册〔2026-10-16 实跑验证 + 10 张截图〕、`prj-design-requirements-main-flow.md` 需求主流程、`p7-design-redis-cache-layer-2026-10-16.md` P7 设计）；② §六 文档交付物行同步 39 份并注明手册与截图资产位置（`docs/images/manual/`）；③ 命名规范新增 `guide` 类型（用户手册），同批登记 | §六、修订记录 |