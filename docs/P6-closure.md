# Phase 6 正式收口（P6-Closure / M6.4）

> **级别**：Phase 6 收口唯一凭据
> **对应里程碑**：`M6.4`（正式收口）
> **最近更新**：2026-10-10
> **上游依据**：`plan/Phase 6 详细开发计划（收敛与交付）.md` §四（D1–D10）；`docs/p0-spec-scope-mvp.md` §四（停止条件）；`docs/p5-handover-p6.md` §一–§五（Phase 5 出口）；`docs/prj-ledger-risk-register.md`（风险册）、`docs/prj-ledger-known-issues.md`（缺陷台账）、`docs/prj-ledger-version-lock.md`（版本锁）
> **口径纪律**：本文件只汇总**既有台账已登记 / 已实测**的事实，不新增结论、不编造指标；凡未闭环项按原文标注「剩余风险（显式接受 / 登记不修）」。

---

## 一、M6.1–M6.3 出口复核（Phase 6 内部闭环）

| 里程碑 | 判据 | 状态 | 证据 |
|---|---|---|---|
| **M6.1** 文档收口（D1–D5） | 六类文档齐备且与实现一致 | ✅ **达成** | `README.md`、`docs/prj-design-architecture.md`、`prj-spec-deployment/operations/api/data-dictionary.md`、ADR-001–009；D1–D5 提交 `71b77eb/b268326/544bba4` |
| **M6.2** 交付包工程化（D6–D7） | 干净环境一键启动并冒烟通过 | ✅ **达成** | `deploy/docker-compose.yml` + `up/init/smoke/down.ps1`；实测 8 容器 up、7 基建 healthy、`smoke.ps1` **6/6 PASS**；提交 `feat(p6-m62)` |
| **M6.3** 演示可复现（D8–D9） | 主场景复现 + 备用场景可用 | ✅ **达成（演示脚本/解说词就绪）** | `demo/scenario.md`、`demo/data/alarms.json`、`docs/pitch.md`、`demo/recording/rehearsal-log.md`；排练实测 S1 五节点全链路跑通（risk=high）；提交 `087053c/1522e5c` |

> 注：M6.3 的「主场景全程复现/备用现场复跑」判据，配套既有 E2E 测试（`tests/e2e/test_e2e_scenarios.py` E1–E6，Phase 3 M3.5 通过）作为权威复现覆盖；排练实测确认触发链路真实可用（见 rehearsal-log）。

---

## 二、停止条件终核（对应 `p0-spec-scope-mvp.md` §四）

| # | 停止条件 | 终核 | 证据 |
|---|---|---|---|
| **S1** | Must 链 13 项端到端可演示（一次完整跑通行：告警→报告→审核） | ✅ **通过** | Phase 4 M4.2/M4.4 真实链路（告警→诊断→证据→报告→审核→追问闭环，E2E 9/9）；Phase 5 M5.1–M5.4 回归未破坏；D9 排练实测 S1 五节点真实跑通 |
| **S2** | ≥3 项量化指标达标（Recall@5 ≥85% + P95 检索 <800ms + 工具首次成功率 ≥90%） | ✅ **通过** | **1.0** / **159.4ms** / **1.0**（三项同时达标，`p5-handover-p6.md` §二；仅模拟数据前提下成立，见 §五局限） |
| **S3** | 版本锁定清单 + 风险登记册定稿 | ✅ **通过** | `docs/prj-ledger-version-lock.md`（10 镜像 digest 锁定 + 依赖钉住）；`docs/prj-ledger-risk-register.md`（风险册持续维护、主要风险已闭环/显式接受） |

**结论：三条同时满足 → Phase 6 停止扩展范围，正式收口。**（一致于 `p5-handover-p6.md` §三 的 P5 出口判定）

---

## 三、Must 链 13 项终核（对应 `p0-spec-scope-mvp.md` §二，P1–P5 累计）

> **复核注（2026-10-10 最终人工复核）**：本表经独立只读交叉验证代码/迁移/路由与既有台账。凡标 **✅** 项均有代码或迁移结构实证；凡标 **⚠️** 项为如实记录未闭环缺口（如 #3 传感器 `anomaly`/`p95` 未实现、#5 图谱数据未预置），**不因 Phase 6 已收口而转绿**。复核结论已回写本表与 §四剩余风险清单。

| # | 能力 | 终核状态 | 说明 |
|---|---|---|---|
| 1 | 告警产生 | ✅ 闭环 | `scripts/alarm_engine.py` 实测（Phase 5 回归含告警链路） |
| 2 | 告警去重 | ✅ 闭环 | Redis `dedup:alarm:` 5min 合并（`configs/alarm_rules.yml`） |
| 3 | 传感器分析 | ⚠️ 部分/缺口 | `query_sensor` 聚合契约实测（P95≈26.2ms）已通过；但判据必填字段 `anomaly` 异常标记与 `p95` **未实现**（`app/graph/nodes/analyze_sensor.py` 的 `_compute_stats` 无此二字段）→ 与判据存在缺口。**复核注**：此缺口**未**在 ISS 台账登记（非登记不修，属 Phase 0 已标"部分实测"的遗留），Phase 6 收敛不新增、按现状如实标注 |
| 4 | 混合检索 | ✅ 闭环 | Milvus hybrid `Recall@5`=0.91（Phase 2，`p2-handover`） |
| 5 | 图谱检索 | ⚠️ 登记不修 → 演示边界 | Neo4j 图谱数据未预置，`extract_triples` 依赖 P1 冻结产物；主场景口径见 `demo/scenario.md` §二（图谱支撑有限）与 `docs/pitch.md` A1（如实披露图谱为空）；**已修正引用**（原误引 "§四"，实为 §二） |
| 6 | 诊断推理 | ✅ 闭环 | 工具调用能力达标（M0.2）；端到端推理已跑通（D9 排练 diagnose 节点） |
| 7 | 证据引用强制 | ✅ 闭环 | `generate_report.evidence_refs` 必填 ≥1（契约冻结） |
| 8 | 报告生成 | ✅ 闭环 | 幂等落库已实测（重复 0 次）；PG `reports` 表已迁移（0003） |
| 9 | 高风险审核 | ✅ 闭环 | `interrupt()` 强制 + 双审核人并发唯一（V5 T5.1/T5.5 实测） |
| 10 | 业务表落库 | ✅ 闭环 | PG 迁移 0001–0006 已跑通（9 表/14 表含 ParadeDB 模板） |
| 11 | 审计日志 | ✅ 闭环 | `0006_audit_logs.sql` 已迁移，追加表 + 禁改触发器（42501）实测 |
| 12 | 降级路径 | ✅ 闭环 | 置信度路由 + 五档路由实现（`app/graph/build.py`）；实测 S1 产出 risk=high 命中审核线 |
| 13 | 前端展示 | ✅ 闭环 | Next.js 前端 + nginx 9763 入口（Phase 4 交付） |

> 完整性说明：Must 13 项在 P1–P5 累计达成，Phase 6（收敛）按纪律**不新增功能、不修 P5 遗留工程缺陷**；遗留工程缺口按 ISS-038–042 登记、属已知边界（见 §四）。Must 是否全部"可演示闭环"由既有 E2E + 排练实测共同覆盖。

---

## 四、风险收敛与剩余风险（显式接受）

### 风险册定稿（`docs/prj-ledger-risk-register.md`）

- 主风险册已维护至 Phase 6：连接器授权（R8）已定稿且不阻塞、checkpoint TTL/重复副作用（R11/R12）架构已定稿待实测、工期超载（R16）已触发但已获前置解阻。
- Phase 5 已完成资源门禁（24GB 内）、备份演练（RTO≤30min/RPO≤24h）等风险项闭环。
- **剩余风险以显式接受 + 登记为主**（见下方表）。

### 剩余风险清单（显式接受 / 登记不修）

| 剩余风险/边界 | 处置 | 出处 |
|---|---|---|
| P95 端到端（含本地生成）9.2s 未达 3s 目标 | **显式接受**（模拟数据前提）；优化路径已列 Phase 6 后路线（流式/max_tokens/缓存） | `p5-handover-p6.md` §五.1 |
| F-2 数据库访问层短连接排队 | 登记不修（非阻塞演示），读路径线程池化列为后路线 | §五.2 |
| F-1 TDengine down 时 health 阻塞事件循环 | 登记不修；tdengine 默认 profile 不启（Phase 5 基线） | §五.3 |
| RPO 持续化（每日定时备份） | 未落地，列为运维后路线（Windows 计划任务） | §五.4 |
| Neo4j 图谱数据未预置（演示边界） | 显式接受；主场景口径 `demo/scenario.md` §二、如实披露 `docs/pitch.md` A1 | M6.3 / A1 |
| ISS-038 超时无抛出点 / ISS-039 告警仅 open / ISS-040 sess 无落库 / ISS-041 qa_log 非持久 | **登记不修**（Q6 裁定，P6 收敛不新增功能）；文档演示口径已按台账如实统一 | `known-issues.md` |
| ISS-042 Milvus 端口三口径 | ✅ **已修复**（D6–D7 改读 MILVUS_PORT，默认 19531） | `known-issues.md` |
| 性能/质量指标受限于模拟语料 | 显式接受；Phase 1 取真实语料后须重测（`p0-spec-scope-mvp.md` §六） | §五局限 |

---

## 五、指标局限声明（必须随交付传播）

本交付包内所有质量指标（`Recall@5`、`MRR`、`NDCG@5`、引用正确率、幻觉率、P95 等）均**基于模拟数据**的本地初步验证（模拟语料 + 本地 7B 生成/判定），**不构成生产级评测结论**；golden 50 题待扩语料后重评。演示与文档须随附本局限（一致于 `p5-handover-p6.md` 总体声明）。

---

## 六、后续路线图（Phase 6 之后）

按优先级（`p5-handover-p6.md` §五 + 本 §四 剩余风险归并）：

| 优先级 | 事项 |
|---|---|
| P0 | **取真实语料并重测全部指标**（替换模拟语料，`p0-spec-scope-mvp.md` §六） |
| P1 | **P95 端到端优化**：流式输出（首 token 口径）/ max_tokens 收紧 / 结构化输出 / 高频问答缓存 |
| P1 | **F-2 数据库访问**：`psycopg_pool` 连接池替换短连接 + 读路径线程池化 |
| P2 | **RPO 持续化**：每日定时备份（Windows 计划任务）+ 滚动保留 7 份 + TDengine taosdump 演练 |
| P2 | Neo4j 图谱数据预置（补齐演示图谱支撑） |
| P2 | 告警状态机闭环（acked/closed 流转 + 审计，对应 ISS-039） |
| P3 | 会话/追问持久化（saq/qa_log 落库，对应 ISS-041） |
| P3 | F-1 health 探测异步化（TDengine down 不阻塞事件循环） |
| P3 | 显式 E_TIMEOUT 抛出点（对应 ISS-038） |

---

## 七、交付包封版清单（D10 交付产物）

| 类别 | 资产 | 路径 |
|---|---|---|
| 编排 | 一键 Compose + 四脚本 | `deploy/` |
| 演示 | 脚本 + 预置数据 + 解说词 + 留档 | `demo/`、`docs/pitch.md` |
| 文档 | README / 架构 / 部署 / 运维 / API / 数据字典 / ADR ×9 | `docs/` |
| 台账 | 版本锁 / 风险册 / 缺陷台账 / 移交清单 P3–P6 | `docs/` |
| 评测 | P2/P5 报告 + RAW 数据 | `reports/`、`experiments/` |

> **封版纪律**：交付包不包含密钥/厂区信息（`env/cloud.json`、`reports/cloud_audit.jsonl` 等敏感件不入 git）；演示与文档统一携带模拟数据局限声明。

---

## 修订记录

| 日期 | 变更 |
|---|---|
| 2026-10-10 | D10 生成：M6.1–M6.3 复核、停止条件终核、风险收敛与剩余风险显式接受、后续路线图、交付包封版清单（M6.4 收口） |
| 2026-10-10 | **最终人工复核修正（独立只读交叉验证）**：① Must #3 传感器分析由「✅ 闭环」改为「⚠️ 部分/缺口」（判据字段 `anomaly`/`p95` 未实现，且此缺口未在 ISS 台账登记——删除错误引用）；② Must #5 图谱检索与 §四剩余风险的 `demo/scenario.md §四` 错误章节引用改为 §二 + pitch.md A1；③ §三 表上方补「复核注」（标 ⚠️ 项不因收口转绿）；④ 其余 6 项（#2/#8/#10/#11/#12/#13 + S1）复核与实态一致 |
