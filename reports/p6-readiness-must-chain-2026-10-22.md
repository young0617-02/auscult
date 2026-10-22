# P6 交付就绪核对：Must 链 13 项 / 停止条件 3 条 / 验收清单 8 项

> 2026-10-22 · 依据 `plan/Phase 6 详细开发计划（收敛与交付）.md:240-277`（V5.0 §10.1/§10.4）
> 方法：逐项找**可验证证据**（实测数字 / 通过用例 / 实现入口），不采信文档自述。
> 真机部分在本机 docker 栈在线状态下复跑（PG 5433 / TDengine 6041 / Milvus 19531 / Neo4j 7474）。

## 零、结论

| 维度 | 结果 |
|---|---|
| Must 链 13 项 | **13 项全部有硬证据**（#3/#5/#7/#9 均已同日闭合，见 §八–§十）；**无实质缺口** |
| 停止条件 3 条 | 第 1 条基本成立（缺 1 项实测）；第 2 条**形式达标但口径混乱**；第 3 条**不成立**（风险册未定稿） |
| 验收清单 8 项 | 4 项已具备（含今日实测 smoke 6/6）；3 项部分；1 项（主场景全程复现）未完成 |
| 判定 | **尚不能宣布 M6.4 完成**。挡住的是「文档口径一致性 + 风险册定稿 + 主场景复现 + 封版」，不是功能缺失。**同日已闭合风险册与口径两项，见 §七** |

标记约定：`✅` 有硬证据 / `⚠️` 有实现或部分证据、但存在必须记录的缺口 / `❌` 缺失。

---

## 一、Must 链 13 项（V5.0 §10.1）

| # | 能力 | 判定 | 证据 | 关键数字 / 缺口 |
|---|---|---|---|---|
| 1 | 告警产生 | ✅ | `scripts/alarm_engine.py:69-84,131`；`app/graph/nodes/parse_alarm.py:42-77`；`reports/p1-d3-alarm-2026-10-08.md:26-33`；`tests/test_auto_trigger.py` | 12 004 行落 TDengine；`thr_vib_rms` 1 条候选（4.5936>4.5，high），误报 0 |
| 2 | 告警去重 | ✅ | `scripts/alarm_engine.py:131-166`（Redis key + TTL 300s）、`:192`（内存降级）；`reports/p1-d3-alarm-2026-10-08.md:30-31` | 5min 内重跑 `dedup_count 1→2`、PG 仍 1 条；自检 3→1 |
| 3 | 传感器分析 | ✅ | `app/graph/nodes/analyze_sensor.py:26-95`（`p95`/`anomaly`/`anomaly_reasons`）；`app/tools/query_sensor.py:62-120`（`percentile`/`profile`/`stats`）；`tests/test_must3_must5_fields.py`（6 例） | 实跑 10 800 行、聚合 P95≈26.2ms。**2026-10-22 补齐判据字段**（见 §十）：`p95` 线性插值 + `anomaly` 可解释判据；真机 PUMP-C-01 窗口 71 点 → `p95=1.3621`、`anomaly=false`（1.29 未超 4.5，正确不误报） |
| 4 | 混合检索（Recall@5≥85%） | ✅ | `experiments/p2/m2/meta-m2.json:2-14`；`reports/p2-d3-m2-metrics.md:34`；`reports/p5-eval.md:13` | 交付口径 **Recall@5 = 1.0**（12 题）；旧口径 0.91（golden 50 题）。**注意**：12 题 + 36 子块天花板极低，且 `p2` 报告 MRR 与 `meta-m2.json` 不一致（0.7569 vs 0.7986） |
| 5 | 图谱检索（≥1 条支撑路径） | ✅ | `scripts/retrieve_graph.py:56-110`（Cypher 返 `path_nodes`/`path_rels`）；`app/graph/nodes/retrieve_evidence.py:90-125`（用 paths 构造 `GraphPath`）；`tests/test_must3_must5_fields.py`（3 例） | **2026-10-22 补真实路径**（见 §十）：真机返回 `振动烈度 -[THRESHOLDS]-> 1.8`（chunk=`criteria_1-1-c0`），`GraphPath.edges` 不再恒空；图谱 105 节点/127 关系 |
| 6 | 诊断推理 | ✅ | `app/graph/nodes/diagnose.py:337-375,195-230,271-286`；`tests/e2e/test_e2e_scenarios.py::test_e1_main_scenario` | e2e 21.5s 出 `RPT-b5f6217f4439e87b`；幻觉率 0.0、ECE 0.0（`reports/p5-eval.md:17,21`） |
| 7 | 证据引用强制 | ✅ | `app/graph/nodes/finalize.py:31-80`（`_validate_citations`）、`:107-111`（硬阻断 → `report_id=None`）；测试 `tests/test_finalize_citations.py`（8 例） | **2026-10-22 三重缺口全部补齐**：① 空 `citations` → `E_NO_CITATION` 硬阻断（拒答/降级例外）；② 补负路径回归锁 8 例；③ `test_d10_finalize.py` 旧断言同步。旁证：S1 实测零引用报告（`RPT-dfbf857be97f625e`）即为该缺口的真实案例 |
| 8 | 报告生成 | ✅ | `app/report/idempotency.py:121-205`；`app/api/routes/reports.py:37-89`；`db/migrations/0003_reports.sql:18-32`；`scripts/test_p4_d02_rest.py:121-157` | 幂等键唯一索引 + 显式 commit/rollback；HTTP 契约 R06–R13 通过 |
| 9 | 高风险强制审核 | ✅ | `app/graph/build.py:110-175`（路由 + `_route_after_cloud`）；`app/graph/nodes/review.py:57-105,170-220`（`should_auto_approve`）；`tests/test_high_risk_routing.py`（16 例） | **2026-10-22 三条绕过路径全部封堵**（见 §九）：① high 优先于 confidence 分流；② 云端升级后二次分流，high 补审；③ `auto_approved` 叠加代码级硬约束（配置无法关闭）。SoD + Redis 锁实测（`reports/p3-reliability.md:49`） |
| 10 | 业务表落库 | ✅ | `alerts`：`scripts/alarm_engine.py:168-179`；`reports`：`app/report/idempotency.py:148-180`；`work_orders`：`db/migrations/0001_init.sql:56-63` | 事务：报告显式 commit/rollback；告警批量单事务 + ON CONFLICT。**备注**：`agent_steps` 无独立表（是 `reports.payload` 的 JSONB 子结构）；`work_orders` 仅离线导入（`scripts/load_meta.py:246`） |
| 11 | 审计日志（不可篡改） | ✅ | `db/migrations/0006_audit_logs.sql:37-59`（BEFORE UPDATE/DELETE/TRUNCATE → `ERRCODE 42501`）；`scripts/test_p5_d12_security.py:161-180`；`reports/p5-security.md:14` | 三类变更实测全拒（8/8 PASS）。**边界**：JSONL 三件（review/cloud/security）是普通追加文件、可编辑；无哈希链；超级用户可 `DROP TRIGGER` |
| 12 | 降级路径 | ✅ | `app/graph/build.py:110-156`；`app/graph/nodes/retrieve_evidence.py:90-121`；`tests/e2e/test_e2e_scenarios.py:220,256,272,368` | E3/E5/E6/E6e 均断言降级后仍产出 `RPT-*` 且 `degrade_reason` 非空 |
| 13 | 前端展示 | ✅ | `client/app/(main)/{alarms,diagnosis,reports,reports/[id],knowledge,graph,audit}/page.tsx`；`client/tests/e2e/m41-m43`（9 例） | 2026-10-09 Playwright **9/9 PASS**（`docs/p4-handover-p5.md:36-38`）。**缺口**：`/audit` 页是空态占位；审核"提交"动作无 e2e；P4 之后无复跑记录 |

**合计**：✅ 9 项 / ⚠️ 4 项（#3、#5、#7、#9）/ ❌ 0 项。

---

## 二、停止条件 3 条（V5.0 §10.4）

| # | 条件 | 判定 | 证据与缺口 |
|---|---|---|---|
| 1 | Must 链 13 项端到端可演示（一次跑通告警→报告→审核） | ⚠️ | e2e `E1–E6` 覆盖到报告与审核（`tests/e2e/test_e2e_scenarios.py`）；但**演示排练只跑到 `diagnose`**（`demo/recording/rehearsal-log.md:17-19` 自述"留现场复跑"），报告生成/审核定稿未在演示链路上跑过，`demo/recording/` 无录屏 |
| 2 | ≥3 项量化指标达标 | ⚠️ | ① Recall@5 **1.0**（12 题）/0.91（50 题）✅；② 检索 P95 **159.4ms**（12 题）/86.1ms（RRF-only）✅；③ 工具首次成功率：**口径有三层**——文档写的 `1.0` 实为"12 题检索命中"口径（`reports/p5-eval.md:65`），真实 LLM 工具口径是 **89.33%**（`experiments/v1/EXP-P7-GATE3.md:69`）与 **98.67%**（`README.md:232`，打桩+单日）。**两套口径并存**（`docs/p0-spec-scope-mvp.md:113` 仍写 0.91/5.6ms/0.9422），需在交付文档统一为一份 |
| 3 | 版本锁定清单 + 风险登记册定稿 | ❌ | 风险册最近更新停在 **2026-10-08**，13 条未关闭（含 R14「未处理」），且未收录 P6/P7 新增风险（`docs/prj-ledger-risk-register.md:8,70`）；digest 交叉引用只覆盖 P0/P1/P2 报告，P3–P7 无登记（`docs/prj-ledger-version-lock.md:546-576`）；`prometheus latest（锚 digest）` 与自身"禁止裸 tag"纪律擦边 |

---

## 三、交付验收清单 8 项

| # | 验收项 | 判定 | 证据 / 缺口 |
|---|---|---|---|
| 1 | 干净环境 `docker compose up`，全服务健康 | ⚠️ | 本机实测：8 容器 up、7 基建 healthy（`deploy/smoke.ps1` 第 1 项 PASS）。**缺口**：无「全新目录 + 清空卷」演练留档（`plan:286` P6-R2 明确要求，且 `deploy/up.ps1:59-63` 自述该场景曾 100% 崩，ISS-044/057） |
| 2 | `make smoke` 冒烟通过 | ✅ | **入口口径已修正**：仓库无 Makefile，实际为 `deploy/smoke.ps1`。2026-10-22 复跑 **6/6 PASS**（PG 18 表 / Milvus healthz / Redis PONG / Neo4j / Nginx）。**判据偏宽**：第 6 项把 nginx 502 判 PASS（后端未起时） |
| 3 | 主场景演示全程复现 | ❌ | `demo/scenario.md` + `demo/data/alarms.json` 存在；排练止于 `diagnose`→risk=high（trace `reports/traces/thr-839f45544e274271a1c0.jsonl`），**报告与审核未演示**；备用场景 S2–S4 未实测 |
| 4 | 六类文档齐备 | ✅ | README / `prj-design-architecture` / `prj-spec-deployment` / `prj-spec-operations` / `prj-spec-api` / `prj-spec-data-dictionary` + ADR-001..009 全在（文件名按 `docs/prj-spec-document-standard.md:29-52` 正名，属合法偏离） |
| 5 | 版本锁定清单与各报告 digest 一致 | ⚠️ | 10 镜像 digest + 2 模型 + BGE-M3/reranker 齐全（`version-lock.md:43-93`）；**缺口**：报告 digest 只覆盖 P0–P2，P3–P7 未登记 |
| 6 | 风险册定稿（剩余风险显式接受） | ❌ | 同停止条件 3；`docs/p6-gate-closure-2026-10-10.md:87-98` 有显式接受清单，但风险册本体未同步 |
| 7 | 指标报告可查（含局限声明） | ✅ | `reports/p5-eval.md:5,68,72-79`（总声明 + ECE 局限 + 未达标处置）、`p2-d3-m2-metrics.md:74`、`docs/p6-gate-closure:102-104`。小缺口：`p5-perf.md` 无独立局限章节 |
| 8 | 交付包封版（tag / 压缩包） | ❌ | 有 10 个基线/gate tag（`baseline-2026-10-20`、`p7-p1-verified-2026-10-21` 等），但**无语义版本 tag、无打包脚本、无 zip**（`deploy/` 仅 up/init/smoke/down） |

**合计**：✅ 4 项 / ⚠️ 2 项 / ❌ 2 项。

---

## 四、挡交付的六个缺口（按处理成本排序）

| 优先级 | 缺口 | 处置动作 | 成本 |
|---|---|---|---|
| P0 | 风险册未定稿（13 条未关 + 未收录 P6/P7 风险） | 关闭/显式接受 13 条；补 P6/P7 条目（ISS-052/056/060–062） | 半天，纯文档 |
| P0 | 停止条件口径三套并存（0.91/5.6ms/0.9422 vs 1.0/159.4ms/1.0 vs 89.33%/98.67%） | 定一份"对外口径表"，其余文档改为引用 | 半天 |
| P1 | 主场景演示未跑到报告/审核 | 按 `demo/scenario.md` 跑通全链并录屏 | 1 天（含审核交互） |
| P1 | 干净环境无留档演练 | 新目录 + 清空卷跑 `up.ps1`，留输出 | 半天（需谨慎，避免覆盖现有卷） |
| P2 | 封版缺失（无 v1.0.0 tag / 打包） | 打 tag + 写打包脚本（zip，排除敏感件） | 半天 |
| P2 | 报告 digest 只到 P2 | 补 P3–P7 报告的 digest 段落 | 2 小时 |

## 五、功能侧真缺口（不影响交付演示，但应在风险册显式接受）

1. **#7 空 citations 不拦** → **已于同日修复**（`E_NO_CITATION`，见 §八）：原 `_validate_citations` 只在"给了引用但引用不存在"时阻断，`citations=[]` 直接跳过 → "证据引用强制"名不副实。
2. **#9 高风险三条绕过路径** → **已于同日修复**（见 §九）：high 优先于置信度、云端升级后补审、`auto_approved` 配置硬化。
3. **#3 判据字段缺 p95/anomaly**：Phase 0 MVP 判据与实现不一致，且未登记 ISS——建议登记一条，避免"判据漂移"重演 ISS-056 的老路。
4. **#5 graph_paths 名不副实**：`edges` 恒空，交付文档若宣称"支撑路径"会被追问；建议改称"命中实体簇 + chunk 归因"。
5. **#11 JSONL 审计无完整性保护**：DB 层有触发器硬约束，文件层没有；建议在风险册写明"接受"或加哈希链。
6. **#13 `/audit` 页占位 + P4 后 e2e 未复跑**：审核提交动作无端到端覆盖。

---

## 六、附：本次真机复跑记录（2026-10-22）

```
=== auscult deploy: smoke test ===
[1/6] All infra services healthy (nginx excluded - backend dependent)   PASS
[2/6] PG connected, 18 tables in public schema                          PASS
[3/6] Milvus healthz OK (metrics port 9092)                             PASS
[4/6] Redis PONG                                                        PASS
[5/6] Neo4j HTTP reachable                                              PASS
[6/6] Nginx reachable (502 expected - no backend running)               PASS
=== SMOKE RESULT: 6 passed, 0 failed ===
```

同期编号口径验收（详见 `docs/p7-runbook-device-id-migration-2026-10-22.md`）：`--verify` 三侧 ok、
`query_sensor(PUMP-A-01)` 命中 12 919 行、全量 `pytest tests -q` **363 passed**。

---

## 七、同日补充（2026-10-22 定稿动作）

本报告 §四 的六个缺口里，**成本最低的两个当天已闭合**：

| 缺口 | 处置 | 结果 |
|---|---|---|
| 风险册未定稿（13 条未关 + 未收录 P6/P7） | `docs/prj-ledger-risk-register.md` 升 **v2 定稿** | **11 条关闭**（R3/R5/R6/R7/R9/R10/R11/R12/R13/R14/R16，逐条挂实测证据）；**3 条显式接受**（R4 Schema 再改即升 v5、R15 真实数据授权未取得→不得宣称现场可用、R21 本地 7B 需 32B 硬件）；**2 条降级为已知缺陷**（R17→ISS-052/053、R22→ISS-061）；**新增 R17–R23** 覆盖 P6/P7（含 R23 演示链路未跑到报告/审核） |
| 停止条件口径三套并存 | 新增 `docs/p6-metrics-canonical-2026-10-22.md` 作**单一事实源** | 定唯一对外值：Recall@5 **1.0**、检索 P95 **159.4ms**、工具首次成功率 **98.67%（74/75）**；同时强制披露三个限定（语料 36 块天花板低 / 保守下界 89.33% / 端到端 9248.8ms 未达标已接受）；建立**黑名单**（0.91·5.6ms·0.9422、84.0%、82.67%、940ms、P5 表中"工具首次成功率 1.0"实为检索口径） |
| 版本锁报告 digest 只到 P2 + `latest` 擦边 | `docs/prj-ledger-version-lock.md` 新增 **§4.2 P3–P7 报告登记（13 份）**、明确 `latest` 临时栈豁免 | 验收项"清单与报告 digest 一致"可核对 |

**停止条件状态更新**：第 3 条（版本锁 + 风险册定稿）**✅ 已闭合**；第 1 条待"演示跑到报告/审核 + 录屏"、
第 2 条待"对外材料统一改为引用口径文件"。这属于**执行动作**，不再是文档缺口。

**仍缺（不影响本次定稿）**：主场景全程复现、干净环境留档演练、`v1.0.0` 封版、P3–P7 报告内文补 digest 段。

### 7.1 主场景全链复现（同日后续，已闭合）

停止条件第 1 条（演示跑到报告/审核）**已闭合**：`scripts/run_demo_s1.py` 一条命令跑完 7 步，
**98.1s** 出报告并完成审核定稿（`RPT-dfbf857be97f625e`，`review_status=approved`），留档
`demo/recording/s1-run-2026-10-22.md`。

同时**坐实了本报告 §五-1 的功能缺口**：本次报告 `citations=[]`（零引用）、结论「尚不明确」、
`confidence=0.625`，**`finalize` 未拦截、照样定稿** —— 与"证据引用强制"的宣称不符，可作为该缺口的
真实链路证据（修复前不应对外强调"报告必带引用"）。

质量根因已核实**与编号迁移无关**：同参数手动复跑 `query_sensor` 三种测点前缀（`PUMP-C-01.vib_rms` /
`PUMP-C.vib_rms` / `vib_rms`）全部 ok，失败来自模型传参 + 1 轮早停（ISS-060）。

---

## 八、Must#7 修复记录（2026-10-22，同日闭合）

**问题**：`finalize._validate_citations` 对"无效引用"硬阻断，但对"零引用"放行 → 零引用报告照样定稿。
S1 实测报告 `RPT-dfbf857be97f625e`（`citations=None`、结论「尚不明确」）就是活证据。

**改动**（`app/graph/nodes/finalize.py`）：

```python
total_citations = sum(len(rc.citations) for rc in state.root_causes) + sum(len(s.citations) for s in state.suggestions)
if not total_citations and not state.refusal and not state.degrade_reason:
    errors.append({"node": "finalize", "code": "E_NO_CITATION",
                   "msg": "结论未给出任何证据引用（无来源不出结论）"})
```

**为什么给降级/拒答开例外**：`build.py` 的 `degrade` 分支之后就到 `finalize`，而 e2e `E3/E5/E6`
断言"降级后仍产出 `RPT-*`"。若无条件拦截，会把"降级路径可用"一并打死 —— 这是把红线做过头。
拒答（`refusal`）同理：产出是"无法作答"，不是结论。

**影响面**：

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 正常诊断 + 有引用 | 出报告 | 出报告（不变） |
| **正常诊断 + 零引用** | **出报告** | **`report_id=None`**，thread 带 `blocked` + `E_NO_CITATION`，审核通过也不落库 |
| 无效引用 | 阻断 | 阻断（不变） |
| 降级 / 拒答 + 零引用 | 出报告 | 出报告（不变） |

**测试**：新增 `tests/test_finalize_citations.py` **8 例**（有引用/零引用/无效/前缀归一/降级例外/拒答例外/warnings 传播）；
`scripts/test_d10_finalize.py` 两处旧断言（按旧行为写的）已同步为 `blocked`。全量 **371 passed**。

**对演示的直接影响**：本地 7B 若再次零引用，S1 将**不产出报告**（`run_demo_s1.py` 如实 FAIL）。
这是"正确地拒绝"，演示口径须提前说明；建议现场用云端后端或预跑选优（见 `demo/recording/s1-run-2026-10-22.md` §五）。

---

## 九、Must#9 修复记录（2026-10-22，同日闭合）

### 三条绕过路径与处置

| # | 绕过路径 | 原因 | 处置 |
|---|---|---|---|
| ① | `high + confidence<0.50` → `degrade` | `_route_condition` 里 `confidence<0.50` 判在 `risk_level=="high"` 之前 | **把 high 分支提到 confidence 之前**（与 E4 `needs_human` 同位置） |
| ② | `escalate_cloud → finalize` 直连 | 图上 `add_edge("escalate_cloud", "finalize")`，云端结论不经分流 | 改为 `add_conditional_edges("escalate_cloud", _route_after_cloud)`：high/needs_human → `human_review`，低置信 → `degrade`，拒答 → `finalize` |
| ③ | `auto_approved`（`review.py`） | 只看 `risk_eval["needs_review"]`，而它受 `risk_rules.yml` 的 `always_interrupt_when_high` 控制 → 改 YAML 即可绕过 | 抽出 `should_auto_approve()`，叠加 `risk_level != "high"` 与 `not needs_human` 的**代码级硬约束**：配置只能更严，不能更松 |

### 连带修正的语义矛盾

degrade/escalate 路径曾产出 `risk=high` 但 `review_status=NULL`、又不在 `waiting_review` 态的报告——
**既不审核也永远无法补审**。修复①②后，high 不再能落到这两条路径（除拒答/极低置信度的非正式产出），
矛盾自然消解。

### 行为变化（需要同步的预期）

| 场景 | 修复前 | 修复后 |
|---|---|---|
| high + confidence 0.3 | `degrade`（不审核，无法补审） | **`human_review`** |
| high + confidence 0.6 | `escalate_cloud`（云端后直连定稿） | **`human_review`** |
| 云端升级后 high | `finalize` 定稿 | **补 `human_review`** |
| `always_interrupt_when_high=false` + high | `auto_approved` 自动通过 | **仍 `interrupt`** |
| medium + 低置信 | `degrade` | `degrade`（不变） |
| 拒答 | `finalize` | `finalize`（不变，无结论可审） |

### 测试

新增 `tests/test_high_risk_routing.py` **16 例**（三条路径逐条 + 不变量：medium 降级/升级不受影响、拒答短路）；
`tests/test_agent_diagnosis.py::test_agent_mode_graph_end_to_end` 原本假设 high 能直接到 `finalize`（正是被判定为绕过的行为），
已改为「断言图挂在 `human_review` → `Command(resume=approved)` → 再断言 `report_id`」。全量 **387 passed**。

### 演示影响

`demo/scenario.md` §五 S4（`vib_rms=5.1` 属 high）**不再演示云端兜底**，改为直接进审核；
云端兜底改由 `bearing_temp=82`（medium）或"参数被拒 ≥2 次"（E2）演示。

---

## 十、Must#3 / Must#5 修复记录（2026-10-22，同日闭合）

### #3 传感器分析：补 `p95` 与 `anomaly`

| 项 | 改动 |
|---|---|
| `query_sensor.percentile()` | 线性插值分位数（`q=0.95`），与 P95 口径一致，避免两套算法 |
| `query_sensor.profile()` → 返回体 `stats` | 补 `avg/max/min/**p95**`（原返回只有 `rows`/`count`，模型看不到分布） |
| `analyze_sensor._compute_stats()` | 补 `p95` / `anomaly` / `anomaly_reasons`；判据 = 超阈值点数 >0，或"趋势上升且峰值 >1.5×均值"；**给理由不只给布尔**，便于审核人复核 |

真机实测（PUMP-C-01，告警时刻窗口，71 点）：

```json
{"count": 71, "avg": 1.2986, "max": 1.3646, "p95": 1.3621,
 "anomaly": false, "anomaly_reasons": [], "threshold": 4.5, "trend": "stable"}
```

→ 该窗口实际未超阈值（1.29 < 4.5），`anomaly=false` 是**正确不误报**；此前实现没有这个字段，
既无法证实"能判异常"，也无法证实"不误报"。

### #5 图谱检索：返回真实路径

**根因**：Cypher `MATCH p = (s:Entity)-[:REL*1..2]-(e:Entity)` 已经拿到了路径，但 `RETURN` 只回
`cid`（chunk 归因），把 `p` 丢掉了；上层只好把"命中实体"塞进 `GraphPath.nodes`、`edges` 留空。

| 改动 | 说明 |
|---|---|
| `retrieve_graph` Cypher | `RETURN cid, [n IN nodes(p) | n.name] AS path_nodes, [r IN relationships(p) | type(r)] AS path_rels` |
| `retrieve_graph` 解析 | 输出 `paths: [{chunk_id, nodes, edges}]`；对旧格式（只 cid）**兼容**，只是没有 paths |
| `retrieve_evidence` | 优先用 `paths` 构造 `GraphPath(nodes, edges, description)`（最多 5 条）；无 paths 时兜底并**如实标注**"仅实体、无路径" |

真机实测：

```
entities_hit = ["振动烈度", "超标", "离心泵", "泵轴", "轴承箱", "温度"]
paths[0] = {"chunk_id": "criteria_1-1-c0", "nodes": ["振动烈度", "1.8"], "edges": ["THRESHOLDS"]}
```

→ `GraphPath.edges` 现在承载**真实受控关系类型**（`THRESHOLDS` / `HAS_PART` / `HAS_FAULT` …），
"支撑路径"与实际数据一致；`nodes` 也不再是"实体堆"，而是路径上的节点序列。

### 测试

新增 `tests/test_must3_must5_fields.py` **9 例**（P95 插值精度 / 阈值异常 / 无阈值尖峰 / 空窗口契约 /
`query_sensor.stats` / 路径解析 / 旧格式兼容 / `GraphPath.edges` 非空）；
全量 **396 passed**（387 → 396）。
