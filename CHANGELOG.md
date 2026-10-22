# 变更日志（CHANGELOG）

本项目为 Phase 0–6 全链路项目，变更以**验证项 / 里程碑**为粒度记录。
版本锁定细节见 `docs/prj-ledger-version-lock.md`（含逐条修订记录）；缺陷见 `docs/prj-ledger-known-issues.md`。
当前阶段与指标速览见 `README.md`；本阶段计划见 `plan/Phase 6 详细开发计划（收敛与交付）.md`。

约定：日期为 +08:00；`代码` / `文档` / `配置` / `数据` 四类分开标注；**原始实验数据只增不改**。

---

## 2026-10-22（维护期 · **Agent 时序取证修复：窗口锚在告警时刻 + 测点截断可见**）

> 全链路 e2e 复测（`docs/e2e-verification-2026-10-22.md`）暴露：历史告警的取证窗口
> 以 `now` 为锚，且 `sensor_ids` 超限被静默截断 —— 两者叠加使"有数据"的告警也被
> 判成"数据矛盾/温度测点无数据"并转人工。本次按 ISS-064 / ISS-065 修复。

- **代码**：`app/agent/tool_registry.py::_resolve_window` 新增 `anchor_ms` —— 告警存在时
  缺省窗口=`[alarm.ts-24h, alarm.ts]`、相对时间（`6h`/`24h`）从告警时刻起算；
  `ts=0`/未来锚点回落 `now`（实时判据行为不变），绝对 ISO 不受影响，终点仍不越过 `now`。
- **代码**：`_exec_query_sensor` 传 `anchor_ms=alarm.ts`，并把实际窗口回灌
  `result.window{start_ms,end_ms}`，模型与审计都能看到"查的是哪段"。
- **代码**：`_MAX_SENSORS_PER_CALL` 3→**5**；仍超限时回灌 `notices`（列出未查询测点并
  注明"没有结论"），不再静默丢弃 —— 与 ISS-056「空结果不静默包装」同口径。
- **测试**：`tests/test_agent_diagnosis.py` 新增 `test_resolve_window_anchors_on_alarm_ts`、
  `test_execute_query_sensor_reports_truncation`；全量离线回归 **391 passed**。
- **实测**：修复后同一历史告警（10-20T01:30Z）缺省窗口=`[10-19T01:30Z, 10-20T01:30Z]`，
  5 个测点全部返回（各 77 点，`bearing_temp` max 59.29），不再出现"温度测点无数据"。
- **重启后 e2e 复测**（`cloud + agent` 形态）：① 有数据链路 `thr-9d6d6526f0bc413da265`
  — `human_reason` 中「时间过滤疑似失效」「温度测点无数据」消失、温度 58.7°C 入结论、
  confidence 0.72→**0.795**，剩余转人工理由仅为"告警值 7.62 与存储峰值 1.36 矛盾"（e2e 构造值，
  属合理转人工）；② 无数据链路 `thr-b5e2bcfb6ed644e6aadd` 仍正确转人工（窗口锚定后确为 0 行），
  该分支未被改坏。两条线程停在 `waiting_review` 未代审。
- **文档**：缺陷清单登记 ISS-064 / ISS-065；新增 `docs/e2e-verification-2026-10-22.md`
  （两条 e2e 链路 + 验收口径 + 复现要点）。

---

## 2026-10-22（维护期 · **交付包封版 v1.0.0：打包脚本 + 语义 tag**）

> §7.3 第 8 项是唯一未落地项：仓库有 10 个 baseline/gate tag，但**无语义版本、无打包入口**，验收无从执行。
> 本次补 `deploy\package.ps1`，把「封版」从口头约定变成一条可复现命令。

- **代码**：新增 `deploy\package.ps1`（robocopy staging → 关键件自检 → 环境目录反向断言 → 写 manifest → `Compress-Archive`）。
  产物 `dist\auscult-v1.0.0.zip`：**556 文件 / 压缩 3 MB / 解压 6.5 MB**。
- **排除**（宁可少打，不可泄漏）：`.venv`/`.venv-mineru`/`node_modules`/`.next`/`test-results`/`__pycache__`；
  `data`/`traces`/`metrics`/`logs`/`blobs`/`chunks`/`backups`/`experiments`；**`env/`（`cloud.json` 直填 API key）**；
  `*.log`/`*.err`/`*.bak*`/`*.zip`/`*.dump`/`*.tgz`/`.env*`（仅留 `deploy\.env.example` 模板）。
- **防残缺**：8 类关键件白名单（`README.md`/`requirements.txt`/`app\api\main.py`/`deploy\up.ps1`/`deploy\smoke.ps1`/`db\migrations`/部署文档/`plan`）+ 体积基线告警（>80 MB 说明漏排除）。
- **可审计**：包内 `PACKAGE-MANIFEST.txt` 记录生成时间、git HEAD、文件数、解压体积、已排除清单、逐文件字节。
- **踩坑**：脚本含中文 → 必须存为 **UTF-8 with BOM**；否则 `powershell -File`（5.1）按 ANSI 解码，中文标点吃掉后续引号，报 "Array index expression is missing"。
- **配置**：`.gitignore` 增 `dist/`、`*.err.log`、`*.out.log`。
- **回填**：`plan/Phase 6` §7.3 #8 → `[x]`（合计 **`[x]` 7 · `[~]` 1**）；打 tag `v1.0.0`。

---

## 2026-10-22（维护期 · **集成测试隔离：回归不再写生产库与仓库产物**）

> 上一轮验证暴露的问题：`scripts/test_*.py` 打真栈，直接写生产库 `auscult_v2`，并把审计/轨迹/指标
> 追加进**仓库已跟踪**的 `reports/*.jsonl`、`experiments/v1/raw/*.jsonl` —— 每跑一次回归脏一片，
> diff 无法评审。本轮专门做隔离。

- **新增 `app/observability/paths.py`**：`REPORTS_DIR / TRACE_DIR / METRICS_DIR` 的单一来源，
  支持 `AUSCULT_REPORTS_DIR` 覆盖。5 个写点（security / cloud / review 审计、trace 轨迹、
  metrics 指标）全部改为引用它，不再各自拼 `PROJECT_ROOT/"reports"`。
- **新增根 `conftest.py`**（在 import app **之前**生效 —— 路径与 DSN 都是 import 时常量，fixture 改不动）：
  ① 产物目录指到 `%TEMP%/auscult-it-reports-*`；② 建一次性临时库 `auscult_it_<uuid>`
  （`db/migrations` 6 个 + 种子 4 角色 + 2 条最小工单样本），`API_PG_URL`/`LANGGRAPH_PG_URL` 切过去，
  会话结束 `DROP DATABASE … WITH (FORCE)`；③ 建库失败则回退生产库并 `[it-isolation][WARN]` 告警，不静默。
  开关 `AUSCULT_IT_DB=off`（只隔离产物目录）。
- **`scripts/run_agent_gate.py`**：`AUDIT_PATH` 加 `AUSCULT_AGENT_GATE_AUDIT_PATH` 覆盖；并把审计重定向
  从**模块级副作用**改为 `main()` 内 `try/finally` —— 原先任何人 `import` 该模块就会永久改写
  `sanitizer.AUDIT_LOG_PATH`，导致同进程后续用例（d24 审计、p5_d12 工具白名单）写到"自己读不到"的文件。
- **拔掉 3 处绕过隔离的硬编码 DSN**：`test_p4_d05` / `test_p4_d06` / `test_d20`×2 改为 `POSTGRES_URL`；
  5 处自拼产物路径（`test_d14/d18/d22/p4_d05/p5_d12`）改为 `app.observability.paths`。
- **结果**：`pytest` **566 passed / 0 failed（97 s）**；跑完 `git status` 在 `reports/`、`experiments/`
  下**零变化**；临时库自动 DROP，无残留。
- **遗留（需单独授权）**：生产库仍有 **52 份历史测试报告**（总 82 份，`thread_id` 形如
  `d19-*`/`d20-*`/`d24-*`）为隔离落地前所留，清理属破坏性操作，待批准后单独执行。

---

## 2026-10-22（维护期 · **云端模型切换回归：endpoint 硬化 + 28 个集成断言复位**）

> 所有者换成 ModelScope `Qwen/Qwen3.8-27B` 后做全功能验证：主链全部正常，但暴露 1 个**会静默降级**的配置坑，
> 以及 28 个因近期行为变更（设备号迁移 / Must#9 高风险必审 / agent 形态默认）而失效的集成断言。

- **代码（`app/llm/client.py`）**：新增 `_normalize_cloud_endpoint()` —— endpoint 只写到版本段（`…/v1`、`…/v1beta`、
  `…/compatible-mode/v1`）时自动补 `/chat/completions` 并记 `WARNING`；形态不明（`…/openai`、`…/v1/messages`）
  **直接 `RuntimeError`** 并给出可照抄写法。根因：客户端把 `endpoint` **原样** POST，只填 base URL 会 `HTTP 404`
  → 3 次重试 → 降级为「低置信度」，现象与 ISS-060「模型不会调工具」一模一样，极易误判为模型能力问题。
- **测试（新增 4 例）**：`tests/test_agent_diagnosis.py` 锁死归一行为（base URL 补齐、完整端点幂等、
  形态不明 fail-fast、工厂出口使用归一后端点）。
- **集成脚本（15 个）复位**：设备号改 `PUMP-A-01`（取首 `ts` 的 SQL 补 `WHERE device_id=…` 过滤）；
  agent 形态下 `sensor_report`/`evidence` 断言按 `diagnosis_mode()` 分流；打桩 `diagnose` 的用例固定
  `AUSCULT_DIAGNOSIS_MODE=deterministic`（否则等于没打桩、真调 LLM）；Must#9 后 `high` 必审 → 补
  `Command(resume=approved)` 再断言报告；路由断言按新优先级翻转（`high` 前置、`retry≥3` 兜底可走 escalate）；
  预算闸门桩改 `BudgetGuard.reserve()`（ISS-054 先增后调后旧桩失效）；共享 JSONL / Prometheus 注册表断言
  改为按本用例标识过滤或 `>=` 增量。
- **结果**：`pytest` 全量 **566 passed / 0 failed / 98 s**（修复前 534 passed / 28 failed / 20 min ——
  慢的根因就是打桩失效在真调 LLM）；离线 `pytest tests/` **400 passed / 32 s**。
- **配置**：`env/cloud.json` 的 endpoint 补全为 `…/v1/chat/completions`（原文件备份 `cloud.json.bak-20261022`）；
  `run_demo_s1.py` 演示口令改读 `AUSCULT_SEED_PASSWORD`；`retrieve_knowledge.py` 的 `"unknown"` 哨兵值进
  密钥扫描白名单（`test_secret_scan` 复位）。
- **仍未做**：集成测试直写生产库 —— 跑一次仍向 `reports` 注入 8 份测试报告，并追加 `reports/*.jsonl`、
  `experiments/v1/raw/*.jsonl` 等**已跟踪**产物（本次已 `git checkout --` 还原）。建议独立 schema 或跑后清理。

---

## 2026-10-22（维护期 · **§7.3 全绿：干净环境清空卷演练留档**）

> 最后一项 `[~]` 的真实原因不是"起不来"，而是**"全新目录 ≠ 空卷"**：`deploy/docker-compose.yml`
> 写死 `name: auscult-deploy`，解压到新目录起的栈照旧挂宿主那套已有数据的卷 —— 从未真正验证过零数据引导。

- **演练口径**：`dist\auscult-v1.0.0.zip`（sha256 `7986af94…647680` / 3,112,006 B）解压到空目录（557 文件 / 6.5 MB），以 `COMPOSE_PROJECT_NAME=auscult-clean` 起 8 个全新命名卷（实测 `-p` 与 env 均覆盖 `name:`；`docker inspect auscult-pg` 确认挂的是 `auscult-clean_pg-data`）→ 既走真实一键入口、又是真空卷，**原 8 个数据卷零接触**。
- **结果**：包内 `up.ps1` **exit 0**（9 镜像 @sha256 全 Pulled，digest 校验通过）；**8 基建 11 s 全 healthy**（milvus 冷启 11 s 达标）；`smoke.ps1` **6/6 PASS**（空库仅 5 表）；包内 6 个迁移在空卷 **0 失败**（5 → 14 表：业务表 9 + 扩展视图 5）。
- **差异核对（避免误判为缺口）**：与原栈 18 表的差集 = `checkpoints / checkpoint_writes / checkpoint_blobs / checkpoint_migrations`，系 LangGraph checkpointer 应用启动时 `setup()` 自建，**非迁移集缺陷**。
- **演练发现**：① ISS-057 守卫按设计生效 —— 宿主 `mosquitto.exe` 占 1883 时 `up.ps1` 立即 `exit 1` 并打印 PID/处置命令（停宿主 broker 后映射正常建立）；② **新登记 ISS-063**：`down.ps1` 未带 `--profile tdengine` → `down` 后 tdengine 容器与 `auscult-net` 残留，而脚本仍打印 `[OK]`，属静默"半停"。
- **代码**：`deploy/down.ps1` 两条路径（`down` / `down -v`）补 `--profile tdengine`，与 `up.ps1` 口径对齐。
- **环境恢复**：演练卷 `down -v` 全部 Removed；原栈重起后 `db=23 MB / tables=18 / audit_logs=2319 / reports=32` 与基线一致；宿主 mosquitto 按原命令行恢复（1883 仍归 Palpation，属演练前既有冲突，非本次引入）。
- **回填**：`plan/Phase 6` §7.3 → **8 项全 `[x]`、`[~]` 归零**；留档 `docs/p6-clean-env-drill-2026-10-22.md`。
- **版本**：本次改动重打交付包为 **`v1.0.1`**（`dist\auscult-v1.0.1.zip`）—— `v1.0.0` 包内 `down.ps1` 仍是旧版；另 `package.ps1` 补 staging 失败清理兜底（`trap`，2026-10-22 两次踩到 `client\node_modules` 超长路径残留无法用 `Remove-Item` 清掉）。

---

## 2026-10-22（维护期 · **Must#9 封堵：高风险审核三条绕过路径**）

> "高风险必审"此前只在**正常路径**成立。核对发现三条绕过，其中最严重的一条会让
> `risk=high` 报告**既不审核、也永远无法补审**（`review_status=NULL` 且不在 `waiting_review`）。

| # | 绕过路径 | 处置 |
|---|---|---|
| ① | `high + confidence<0.50` → `degrade`（不审核） | `_route_condition` 把 **high 分支提到 confidence 之前**（与 E4 `needs_human` 同位置） |
| ② | `escalate_cloud → finalize` 直连 | 改为 `add_conditional_edges("escalate_cloud", _route_after_cloud)`：high/求助 → 补审，低置信 → 降级，拒答 → 定稿 |
| ③ | `auto_approved` 受 YAML 开关控制 | 抽出 `should_auto_approve()`，叠加 `risk_level != "high"` / `not needs_human` 的**代码级硬约束**——配置只能更严，不能更松 |

- **连带消解**：degrade/escalate 产出 `risk=high` 但 `review_status=NULL`、又不在待审态的**状态机矛盾**。
- **行为变化**：high 不再走 `escalate_cloud`（0.5–0.75 区间直接人审）；云端升级后的 high 结论补审；
  `always_interrupt_when_high=false` 也拦不住 high 审核。
- **测试**：新增 `tests/test_high_risk_routing.py` **16 例**；`test_agent_mode_graph_end_to_end` 原断言"high 直接出报告"
  （正是被判定的绕过行为）改为「挂 `human_review` → `Command(resume=approved)` → 出报告」。全量 **387 passed**。
- **演示同步**：`demo/scenario.md` §五 S4（`vib_rms=5.1` 属 high）不再演示云端兜底，改为直接进审核；
  兜底演示改用 `bearing_temp=82`（medium）或"参数被拒 ≥2 次"。README "高风险覆盖率 100%"补口径（拒答/降级不计入分母）。
- **回填**：`plan/Phase 6` §7.1 #9 → `[x]`（合计 **`[x]` 11 · `[~]` 2**）；核对报告 §九 记录影响面矩阵。

---

## 2026-10-22（维护期 · **停止条件 S2 闭合：三处口径误标修正** → M6.4 达成）

> 指标口径单一事实源（`docs/p6-metrics-canonical-2026-10-22.md`）建立后，把对外材料里的**误标**逐一改掉。
> 核心错误只有一个，但传染了三处：把「12 题检索执行口径 1.0」当成「工具调用首次成功率」。

- **修正 3 处**：
  - `README.md` §3.2 指标表：`工具调用首次成功率 1.0（12/12）` → **`98.67%（74/75，EXP-P7-P1）`**，并注明保守下界 89.33%；
    表下补「口径准绳」声明（两处不一致以口径文件为准）；Phase 2 行的 `P95 86.1 ms` 标注为 **RRF-only 阶段口径**。
  - `docs/p5-handover-p6.md` §二/§三：同错 → 98.67%（74/75）；补「口径准绳」注。
  - `docs/p6-gate-closure-2026-10-10.md` S2 行：`1.0 / 159.4ms / 1.0` → `1.0 / 159.4ms / 98.67%（74/75）`，
    并写明原值的真实口径（12 题检索命中）。
- **未改**：`reports/p0-*`、`reports/README.md` 索引、`archive/**` —— 属历史证据，按黑名单规则
  「只可在复盘材料出现且须标时点」处理。
- **停止条件三条全部闭合 → M6.4 达成**（`plan/Phase 6` §7.2 三条均 `[x]`；验收清单 `[x] 6 · [~] 1 · [ ] 1`，
  仅剩"交付包封版"与"干净环境清空卷演练留档"）。

---

## 2026-10-22（维护期 · **Must#7 补齐：零引用不再能定稿**）— 用真实链路坐实的缺口

> 上午 S1 实测出一份**零引用报告照样定稿**（`RPT-dfbf857be97f625e`，`citations=None`、结论「尚不明确」）。
> 「证据引用强制」此前只对"引用无效"生效，对"不给引用"完全放行 —— 宣称与实现不符。

- **代码**（`app/graph/nodes/finalize.py`）：新增 `E_NO_CITATION` 硬阻断 —— 根因/建议的引用总数为 0 时
  不产 `report_id`、报告不落库。**例外**：`refusal`（合规拒答）与 `degrade_reason` 非空（降级）路径放行，
  否则会把 e2e `E3/E5/E6`「降级后仍出报告」一并打死（`build.py` 的 `degrade` 之后即 `finalize`）。
- **测试**：新增 `tests/test_finalize_citations.py` **8 例**（有引用 / 零引用 / 空根因 / 无效引用 /
  `chunk_id=` 前缀归一 / 降级例外 / 拒答例外 / 阻断时 warnings 一并带出）；
  `scripts/test_d10_finalize.py` 两处按旧行为写的断言同步为 `blocked`。全量 **371 passed**（363 → 371）。
- **行为变化**：本地 7B 若再零引用，S1 **不会产出报告**（`run_demo_s1.py` 如实 FAIL）。
  这是"正确地拒绝"，演示口径需提前说明（`demo/scenario.md` 引用硬校验条已补 ② 零引用）。
- **回填**：`plan/Phase 6` §7.1 #7 → `[x]`（Must 链合计 `[x] 10 · [~] 3`）；核对报告 §八 记录改动 + 影响面矩阵；
  `demo/recording/s1-run-2026-10-22.md` 标注"该报告在修复后不会定稿"。

---

## 2026-10-22（维护期 · **停止条件 S1 闭合：S1 主场景全链 98.1s 跑通至定稿**）

> 补齐 `demo/recording/rehearsal-log.md` 2026-10-10 留下的缺口（当时只跑到 `diagnose`→risk=high）。
> 本次起真实后端（uvicorn :8000，六组件 health 全 up），跑到报告审核定稿，全程留档。

- **新增编排工具** `scripts/run_demo_s1.py`：登录(eng_dev/rev_dev) → `POST /api/diagnose` → 轮询节点进度
  → 报告 → SoD 拒绝 → 审核通过 → 定稿，一条命令跑完，并自动生成 markdown 留档（诊断是异步的，
  手工 curl/点界面无法稳定复现）。
- **实测结果**：**98.1s** 全链；`parse_alarm → diagnose → waiting_review`（risk=high 强制中断）
  → `eng_dev` 自审 **403** → `rev_dev` approved → `human_review → finalize → done`；
  `RPT-dfbf857be97f625e` 定稿、`GET /api/reports/{id}` 200、`review_status=approved`。
  留档：`demo/recording/s1-run-2026-10-22.md`。
- **诚实的质量结论**（未粉饰）：报告**零引用**（`citations=None`）、结论「轴承振动异常的具体原因和处理措施
  尚不明确」、`confidence=0.625`、`query_sensor` 首轮 `ok=false`、Agent 仅 1 轮收敛。
  ① 已核实**与编号迁移无关**——同参数手动复跑 `PUMP-C-01.vib_rms` / `PUMP-C.vib_rms` / `vib_rms`
  三种前缀全部 ok，失败源于模型传参；② 归 ISS-060（本地 7B 质量）；③ **同时坐实核对报告 §五-1 的缺口**：
  `citations=[]` 时 `finalize` 不拦截，零引用报告照样定稿 → 修复前不应对外强调"报告必带引用"。
- **演示脚本同步**（`demo/scenario.md`）：S1–S4 的 `device_id` 由台账口径 `C 0泵` 改为规范编号
  `PUMP-C-01`（迁移后库里已无旧编号）；`severity` 由 `critical` 改为 `AlarmEvent` 词表 `high`；
  节点序列更新为 P7 实际链路（传感器/检索/图谱/工单在 `diagnose` 内以工具循环取得）；新增"实测质量披露"验收点。
- **回填**：`plan/Phase 6` §7.2 第 1 条与 §7.3 第 3 项 → `[x]`（合计 `[x] 6 · [~] 1 · [ ] 1`，
  仅剩"交付包封版"）；风险册 R23（演示链路未跑到报告/审核）→ **已关闭**，质量项并入 R21/ISS-060。

---

## 2026-10-22（维护期 · **停止条件 S3 闭合：风险册 v2 定稿 + 指标口径单一事实源**）

> 上一轮核对把"卡交付"的原因定位到文档口径与收口材料，本轮把其中两件做完——
> 停止条件第 3 条（版本锁定清单 + 风险登记册定稿）从 `[ ]` 变 `[x]`。

- **风险册升 v2 定稿**（`docs/prj-ledger-risk-register.md`）：R1–R16 逐条给终态——**11 条关闭**
  （R3 环境基线 v2 / R5 评测集改 12 题配套集 / R6 分词器抽检 32 条 0 失败 / R7 Ollama 定版 0.34.2 /
  R9 Mosquitto 4.11 MiB / R10 峰值 20.73GB≤24GB / R11 checkpoint 切 PG / R12 幂等 count=1 实测 /
  R13 降级代价表填数值 / R14 MinerU 批量失败率 0 / R16 已收口）；**显式接受 3 条**（R4 Schema 再改即升 v5、
  R15 真实数据授权未取得→不得宣称现场可用、R21 本地 7B 需 32B 硬件）；**降级为已知缺陷 2 条**
  （R17→ISS-052/053、R22→ISS-061）；**新增 §2.1 R17–R23** 覆盖 P6/P7（此前完全未入册）。
- **指标口径单一事实源**（新增 `docs/p6-metrics-canonical-2026-10-22.md`）：终止"三套口径并存"——
  对外值定为 Recall@5 **1.0**、检索 P95 **159.4ms**、工具首次成功率 **98.67%（74/75，EXP-P7-P1）**；
  强制并列披露三个限定（语料 36 块天花板低 / 保守下界 **89.33%** / 端到端 **9248.8ms 未达标已接受**）；
  建立**黑名单**（`0.91·5.6ms·0.9422`、GATE2 `84.0%`、GATE-D `82.67%`、`940ms` HTTP P95、
  以及 P5 表中"工具首次成功率 1.0"实为**检索执行口径**）。`docs/p0-spec-scope-mvp.md` 的 S2 行改为引用本文。
- **版本锁补登记**（`docs/prj-ledger-version-lock.md`）：新增 §4.2 **P3–P7 报告登记 13 份**
  （此前只覆盖 P0–P2，导致"清单与报告 digest 一致"无法核对）；明确 prometheus `latest` 为
  **压测期临时栈显式豁免**（digest 已锚定、测后销毁），不再算"裸 tag 残留"。
- **回填**：`plan/Phase 6` §7.2 第 3 条 → `[x]`，§7.3 第 5/6 项 → `[x]`（合计 `[x] 5 · [~] 1 · [ ] 2`）；
  `reports/p6-readiness-must-chain-2026-10-22.md` 追加 §七 记录同日闭合动作。
- **剩余停止条件**：第 1 条（演示跑到报告/审核 + 录屏）、第 2 条（对外材料全面改为引用口径文件）——
  都是执行动作，不是文档缺口。

---

## 2026-10-22（维护期 · **P6 交付就绪核对：Must 链 13 项逐项挂证据，判定尚未达 M6.4**）

> 背景：`plan/Phase 6` §7.1–7.3 三张表长期全是 ☐，无法区分"没做"和"没回填"。本轮按证据核对，
> 结论是**功能基本齐、卡在口径与收口文档**——不是缺能力。

- **核对结论**（报告：`reports/p6-readiness-must-chain-2026-10-22.md`）：
  Must 链 **9 项硬证据 + 4 项带缺口**（#3 传感器分析缺 `p95/anomaly` 判据字段；#5 "图谱支撑路径"
  实为实体簇、`edges` 恒空；#7 空 `citations` 不拦 + 无负路径测试；#9 高风险审核有低置信度/
  云端升级/`auto_approved` 三条绕过路径）。停止条件第 1、2 条形式上成立但**口径三套并存**
  （`0.91/5.6ms/0.9422` vs `1.0/159.4ms/1.0` vs 工具口径 `89.33%/98.67%`），第 3 条**不成立**
  （风险册停在 10-08、13 条未关、未收录 P6/P7 风险）。
- **真机复跑**：`deploy/smoke.ps1` **6/6 PASS**（PG 18 表 / Milvus / Redis / Neo4j / Nginx）。
- **文档 · 口径修正**：`plan/Phase 6` §5.2 与 §7.3 的 `make smoke` 改为实际入口 `deploy\smoke.ps1`
  （仓库从无 Makefile，且 `smoke.ps1` 不含 Playwright F1–F11 子集——原设计描述与实现不符）；
  §7.1–7.3 回填三态标记（`[x]`/`[~]`/`[ ]`）+ 证据列。
- **未做**（交给后续）：主场景演示复现（排练只到 `diagnose`）、风险册定稿、报告 digest 补 P3–P7、
  `v1.0.0` 封版。

---

## 2026-10-22（维护期 · **ISS-056 收尾三件：删空表 / 统一展示口径 / 定退场判据**）

- **数据**：`DROP TABLE iot.d_plant1_PUMP-A-01`（删前复核 `count(*)=0`）。该表是迁移后某次写入
  按"模板名"留下的空子表，留着会让新数据分叉到"同 TAG 双子表"（查询会合并、不丢数据，但子表管理混乱）。
  `SHOW iot.TABLES` 现为 6 张（`s_plant1_*` 3 + `d_plant1_PUMP-A/B/C` 3）。
- **代码 · 展示口径**：`app/device_ids` 增 `canonicalize_text()` / `canonicalize_ids()`
  （独立短编号 → 规范编号，`PUMP-A-01`/`X-PUMP-A`/`PUMP-AX`/未登记编号一律不动）；
  `app/api/routes/reports.py` 的列表与详情出口接入——**历史 payload 仍是 `PUMP-A`（库内证据不改写），
  API 返回 `PUMP-A-01`**。实测 `RPT-fa1b64066214ba3f`：DB `PUMP-A 的 vib_rms 达到 7.62 mm/s…`
  → API `PUMP-A-01 的 vib_rms 达到 7.62 mm/s…`。前端由 API 驱动，无需单独改。
- **可观测 · 映射退场判据**：新增 `auscult_device_id_scheme_mismatch_total{direction}`
  （`short_input` = canonical 模式仍收到短编号 / `canonical_input` = legacy 模式收到规范编号），
  由 `tool_registry._storage_id()` 在三处调用点打点。退场条件写进 `app/device_ids` 头注与 runbook §八：
  **连续 7 天为 0 + `--verify` 的 `off_scheme` 恒空 + 各端已只产出规范编号**。在此之前保留兼容层。
- **测试**：`tests/test_device_id_migration.py` 13 → 18 例（展示归一的独立匹配 / 嵌套 payload /
  真实 API 出口不改库内 / 漂移打点正负例）；全量 **363 passed**。

---

## 2026-10-22（维护期 · **ISS-062 遗留清账：8 份历史报告代号已还原**）— 候选集补双口径，脚本不再是空转

> dry-run 首跑暴露一个**静默失效**：8 份报告全部 `unmapped`（可还原 0 份）。原因是代号
> `设备#f6de90` 按**迁移前**短编号 `PUMP-A` 取 hash，而库内 `alerts.device_id` 已被迁移为
> `PUMP-A-01`，候选集只取现值 → 反查表里没有这个 hash。若不修，"脚本已备"会变成"跑了也白跑"。

- **修复**：`collect_candidates` 增加 `_with_scheme_variants()`——用 `app.device_ids` 双向映射把
  候选补成**双口径**（`PUMP-A` ↔ `PUMP-A-01`）；反查表按 hash 原文还原，**不改写历史事实**
  （历史报告是证据，零猜测优先）。未登记编号（`FAN-9`）不会被伪造出别名。
- **真机执行**：`--apply` 还原 **8/8** 份；库侧复核 `payload::text LIKE '%设备#%'` = **0**；
  31 份报告 `idempotency_key` 全未变（只改 payload 文本）；二次 dry-run = 0（可重复执行）。
- **测试**：`tests/test_corpus_maintenance.py` 11 → 13 例（双口径候选 / 未登记编号不伪造别名）。

---

## 2026-10-22（维护期 · **ISS-042 处置：Milvus 端点单一事实源**）— 三口径收成一处，一键启动后不再写错实例

> 三口径：`compose.base` `19530`（Phase 0 基线）/ `compose.v2`·`deploy` `19531`（宿主映射）/
> 脚本硬编码 `39530`（宿主 `kee-milvus`）。脚本各自写字面量 → 一键启动后可能写进别人的 collection，
> 或自检误报端口冲突（威胁干净环境一键启动）。

- **代码 · 单一事实源** 新增 `scripts/milvus_endpoint.py`：`DEFAULT_MILVUS_PORT = 19531`（与
  `deploy/docker-compose.yml` 的 `19531:19530`、`app/api/config.py::MILVUS_PORT` 一致）、
  `MILVUS_PORT` env 覆盖（`39530` = kee-milvus 复现口径）、非法/越界值回退默认（同一纪律：配置手误不把连接打到空）。
- **代码 · 收口改造**：`retrieval_base` / `reconcile` / `outbox_worker` 的重复 f-string、
  `build_milvus_v1.DEFAULT_URI`（原硬编码 `127.0.0.1:19530`）、`v2_load_test.DEFAULT_MILVUS_URI`、
  `run_v2 --milvus-uri` 默认值全部改走 `milvus_uri()`。
- **刻意不改**：`docker/compose.base.yml`（Phase 0 基线快照）、`scripts/check_ports.ps1`（Phase 0
  冻结端口检查工具，改它与 `env/ports.md` 基线矛盾）。容器内 Milvus 恒为 `19530`，本改动只统一**宿主**端口。
- **测试**：新增 `tests/test_milvus_endpoint.py` 15 例（默认值 / env 覆盖 / 手误回退 / compose 宿主端口同源 /
  应用侧同源 / 五个脚本无残留字面量），纯静态 + 无 pymilvus 依赖。

---

## 2026-10-22（维护期 · **ISS-056 真机验收通过，关单**）— 三侧口径实测一致，子表名不影响查询

> 迁移执行完成后的收口验证（docker 栈在线：PG 5433 / TDengine 6041 / Neo4j 7474）。
> 证据全部来自真机命令输出，非打桩。

- **`--verify`**：`sides_reached=3`、`off_scheme` 三侧全空、`ok=true`、`scheme=canonical`。
- **PG**：`SELECT device_id, count(*) FROM alerts` → 仅 `[('PUMP-A-01', 1)]`（无短编号残留）。
- **TDengine**：`SELECT tbname, device_id, count(*)` → `d_plant1_PUMP-A→PUMP-A-01`（12919）、
  `-B→PUMP-B-01`（4314）、`-C→PUMP-C-01`（4083）；**子表名保留历史短编号形态**，
  按 TAG 查询不受影响（3.3.8.0 `RENAME` 语法不通且无必要，脚本"只 SET TAG"的设计得到真机确认）。
  发现残留空子表 `d_plant1_PUMP-A-01`（0 行），已在 runbook 记为待处置项（建议 `DROP TABLE`）。
- **端到端**：`query_sensor('PUMP-A-01', vib_rms, 全窗)` → 12919 行；`verify_query_sensor.py`
  三设备各 48–52 窗口、P95≈30.4ms；`query_sensor` 用 1h 窗口 → `empty_reason=no_data_in_window`
  （数据止于 2026-10-21，分类正确，不再是 `device_not_found`）。
- **工具层归一**：`query_graph(start_node=PUMP-A)` → `device_id_resolved={requested:PUMP-A, used:PUMP-A-01}`；
  `get_maintenance_history(PUMP-A-01)` → `work_orders=[]` + `known_device_ids=[A 0泵, …]`（台账口径如实回灌）。
- **回归**：**342 passed**。
- **遗留（另立项，不在本轮范围）**：① 图谱实体是部件/现象口径，无设备编号实体 → 设备关系查询必然空，
  需实体对齐；② `work_orders` 源数据为图纸/台账口径，无编号可迁，根治需重做台账解析映射。
- **文档**：ISS-056 台账条目补真机证据并关单；runbook 第六节改为"真机执行后复核"、第七节验收清单勾选；
  `Material/05` 剩余清单同步为"已实现且真机验收通过"。

---

## 2026-10-22（维护期 · **ISS-056 收口：编号口径默认切到 `canonical`**）— 默认值必须与库内实际形态一致

> 真机迁移已执行完毕（PG `alerts` / TDengine TAG+子表名 / Neo4j 实体名三侧均为规范编号，
> 灌数端默认值同步为 `PUMP-A-01` 体系）。此时查询端默认仍是 `legacy` 会把 `PUMP-A-01`
> 映射回已不存在的 `PUMP-A` → 全链路"设备不存在"（已实测）。**默认翻转为 `canonical`**：
> 未迁移的旧库需显式 `AUSCULT_DEVICE_ID_SCHEME=legacy`，回滚路径不变（切回 legacy 即旧行为）。

- **代码**：`app/device_ids.DEFAULT_SCHEME = "canonical"`；非法值/手误仍保守回退默认（不把查询打到空）。
- **测试**：默认语义翻转（未设环境变量 = canonical、短编号两跳升规范编号；`legacy` 分支改为显式 `setenv`），
  `test_device_alias_map_normalizes_product_id` / `get_maintenance_history` / `query_graph` 三段别名用例
  均补齐"默认 canonical + 显式 legacy"双向断言；`test_corpus_stats_counts_and_blind_spots` 补 PG 断连桩
  （原先直连真实库，本机有 PG 时 `pg_doc_chunks` 不为 `skipped`，随环境漂移）。**342 passed**。
- **文档**：`app/device_ids.py` 头注与本节说明默认值变更原因。

---

## 2026-10-22（维护期 · **语料盲区 A 类消解：只改改写层，不动语料**）— 15 个盲区里 8 个是"用词差异"，不必扩语料

> `reports/p1-corpus-stats-2026-10-22.md` 体检出 15 个语义域盲区。复核后按**成本**分成三类：
> A 类 8 个是"语料有事实、只是不用用户那个词"（汽蚀→气蚀、异响→噪声、趋势→漂移、波形→频谱、
> 油液→润滑油、阈值/限值/标准→警戒值/4.5 mm/s）；B 类 7 个是域真缺失（齿轮/阀门/喘振/裂纹/疲劳）；
> C 类是编号的 OCR 逐字符空格形态（`P U M P-A`）。**只做 A 类**（+ 规范→短编号），语料与索引零改动。

- **代码**：`scripts/query_rewrite.expand_keywords()` + `configs/query_synonyms.json`（词表只收**有命中实证**
  的近义词，齿轮/阀门/喘振等不配，避免制造"已解决"的错觉）。
- **关键取舍：只追加 `keywords`，绝不改 `semantic`**——sparse 走服务端 BM25（jieba），keywords 是词项拼接文本，
  追加近义词只扩大 OR 召回、原词一项不少；而 `semantic` 一变，dense 向量与 rerank 打分都会平移 = 悄悄改了
  P7 检索基线，无法再与既有实验数字对账。
- **C 类部分**：`PUMP-A-01 → PUMP-A`（语料/图谱仍是短编号）已扩；**空格 OCR 形态不做**——它需要检索侧
  chunk 文本归一（属 B 批），在查询侧硬塞 `P U M P-A` 会被 jieba 切成单字母，反而稀释召回。
- **实测**（词面命中块数 / 36 块）：汽蚀 0→1、异响 0→7、阈值 6→13、剥落 0→6、趋势 11→12；
  5/5 抽样盲区问句从"必然空结果"变为"有候选"。
- **可复现性**：`AUSCULT_QUERY_EXPAND=0` 一键回到 2026-10-22 之前行为；改写结果新增 `expansion` 审计字段
  （扩了哪些词一目了然，不静默改变检索）。
- **测试**：**341 passed**（333 + 8：词表实证性、纯追加不改原词、A 类逐词、B 类不伪造、编号扩展、
  开关回退、semantic 不变、配置缺失静默降级）。
- **文档**：`reports/p1-corpus-stats-2026-10-22.md` 追加"处置进展"（含实测表，历史数字保留不改）；
  `Material/02` §15 遗留 4；`Material/05` 剩余清单。

---

## 2026-10-22（维护期 · **ISS-056 候选①：数据层编号统一**）— 从"查询垫片"走到"同一套口径"，迁移窗口可回滚

> 候选②只是让查询"查得到"，垫片本身仍是第二套口径。本轮实施候选①：把**存量数据原地改写**为规范编号，
> 产品层/数据层同口径。不采用"清库重灌"——会丢历史时序、破坏已锁定实验的可复现性；TAG/子表名/实体名
> 均可原地改写，需重灌的只有 Redis 去重键（TTL 5min，迁移窗口后自然过期）。

- **代码 · 单一事实源** `app/device_ids.py`：`CANONICAL_TO_LEGACY`（PUMP-A-01 ↔ PUMP-A）双向映射 +
  `canonical()/legacy()/storage_id()`；库内形态由 `AUSCULT_DEVICE_ID_SCHEME` 决定——当轮默认 `legacy`
  以保证**迁移前零行为变化**（迁移完成后的默认值翻转见本节上一条），非法值保守回退默认值
  （配置手误不得把查询打到空）。未知编号恒原样透传。
- **代码 · 工具层改造**：`query_sensor` / `query_graph`（start_node）/ `get_maintenance_history` 由
  `DEVICE_ALIAS_MAP.get(...)` 改为 `storage_id()`（两跳：先规范再落库内形态）；`DEVICE_ALIAS_MAP` 保留为只读兼容别名。
- **代码 · 迁移执行器** `scripts/migrate_device_ids.py`：三侧原地迁移（TDengine 子表 TAG + `RENAME`、
  PG `alerts`（`alarm_id` 不变）、Neo4j `Entity.name`）；**默认 dry-run**、`--target` 分侧、`--apply` 落库、
  `--revert` 反向回滚、`--verify` 三侧口径核对（不可达即 `ok=False`，不给假绿灯）；逐条容错不阻断。
- **代码 · 灌数端**：`v3_ingest_direct` / `gen_sparkplug` / `spb_simulator` 默认设备改规范编号（否则迁移后又被写回旧口径）。
- **范围边界（如实记录）**：`work_orders.device_id` **无迁移对象**——源数据是图纸/台账口径（`A 0泵`、客户号），
  本就不含产品编号（语料 `PUMP-` 0 命中）；工单侧继续用"空结果回灌真实编号样本"过渡，根治需另立项。
- **测试**：**333 passed**（320 + 13：映射三态 / 工具层按 scheme 落库内形态 / 灌数默认值锁 / PG·TD·Neo4j 三段迁移
  （dry-run 不写、apply 写、单条失败不阻断）/ revert / 非受控编号拒绝 / 离线退出码 2 / verify 不可达）。全部离线零真实栈。
  顺带修复既有**测试隔离缺陷**：`test_agent_gate.py` 的 `install_stubs()` 直接改全局 `_EXECUTORS` 无回滚，
  会泄漏到同进程后续测试（`execute_tool` 静默走 STUB）→ 加 autouse fixture 快照/恢复。
- **文档**：新增 `docs/p7-runbook-device-id-migration-2026-10-22.md`（执行顺序 / 回滚 / 已知限制 / 验收清单）；
  `Material/02` §4 机制表、§15 遗留；`Material/05` 剩余清单；ISS-056 条目改为"候选①已实施，待栈在线执行"。

---

## 2026-10-22（维护期 · **ISS-062 遗留清理脚本 + 语料规模体检**）— 历史报告代号可补偿还原，语料盲区首次量化

> 对照最初评审材料的剩余清单：本地 32B 硬件（外部依赖，不动）之外的两项低优先遗留
> ——「历史报告含脱敏代号」「语料规模演示级」——本轮把**决策材料与工具**备齐，均不擅自改数据基线。

- **代码 · 历史报告脱敏代号清理**（ISS-062 遗留，`scripts/restore_masked_device_ids.py`）：ISS-062 只修了新报告出口，
  修复前落库的 8 份报告 payload 仍是 `设备#f6de90` 且无 `device_id` 字段。脚本从 PG `alerts`/`work_orders`
  收集候选设备（`--extra` 可追加），用**出口同算法**（`hash_device_id` sha256[:6]）建反查表；
  **默认 dry-run**、`--apply` 才 UPDATE，且只改 payload 文本不动幂等键（可重复执行）；
  **能全映射才替换，无法映射的代号原样保留并列入人工清单**——宁可漏还原，不可错还原。
  当前离线环境 PG 不可达，退出码 2（不谎称"无待清理"）；栈在线后跑一次 `--apply`。
- **代码 · 语料规模体检**（`Material/02` §15 遗留 4，`scripts/corpus_stats.py` + `reports/p1-corpus-stats-2026-10-22.md`）：
  **不灌数据**（`chunks_v1.jsonl` 是全部已锁定实验的语料基准，扩语料=平移基线，须所有者单独判决），只量化现状：
  36 chunks / 19 docs / 3147 tokens；**语义域盲区 15 词**（齿轮、密封、剥落、喘振、汽蚀、限值、阈值…）；
  且语料文本**不含产品设备编号**（`PUMP-` 0 命中，设备以 C-200/P-150 等图纸型号出现）→ 按编号提问的检索会失配。
  `--strict` 可作 CI 守门（有盲区即失败）。
- 回归：**320 passed**（309 + 11：清理脚本 7 例 + 体检脚本 4 例，全部离线零 PG）。
- **文档**：`docs/prj-ledger-known-issues.md` ISS-062（遗留清理脚本待栈在线执行）；`Material/02` §15 遗留表
  （#4/#6 更新为"已备工具/已体检，待判决/待执行"）；`Material/05-评审回应.md` 剩余清单同步。

---

## 2026-10-22（维护期 · **评审增量 E5 未收敛信号 + 求助率监控 + ISS-056 图谱/工单侧收尾**）— 失败信号继续前移，设备号口径三侧归一

> 依据对最初评审材料的逐条复查（`Material/05-评审回应.md`）：E1–E4 落地后剩余的真实尾巴有两条半——
> 「未收敛」未接路由（材料二 #6 三组合只兑现两条）、求助率不可观测、ISS-056 只治理了 `query_sensor` 一侧。

- **代码 · E5 未收敛 → 路由信号**：`_finalize_answer` 新增 `forced` 参数，步数用尽后的强制收口轮置
  `state.not_converged`（语义 = 结论是"拖"出来的，不是收敛出来的）；`build._should_escalate_not_converged`
  与 E2 **同口径护栏**（`AUSCULT_CLOUD_FALLBACK` 开 + `local` 后端 + 未升级过）→ 提前 `escalate_cloud`，
  云端凭 E1 的本地轨迹二次裁决。优先级：`needs_human`（E4）> 未收敛/参数被拒（E2/E5）> `confidence`。
- **代码 · 求助率监控（E4 运维缺口）**：新增指标 `auscult_needs_human_total{reason}`（`needs_human` 模型主动求助 /
  `risk_high` 风险等级高），在 `review.human_review` 真正转人工时打点——模型若退化成"拿不准就上交"，
  该指标占比会先于审核工单积压发出信号。同时 `thread_status` 暴露 `needs_human` / `human_reason`
  （`runner._absorb_needs_human`，与 `refusal` 同口径：只认 diagnose 增量、假值不清除）。
- **代码 · ISS-056 图谱/工单侧收尾**：`query_graph` 的 `start_node` 与 `get_maintenance_history` 的 `device_id`
  同型过 `DEVICE_ALIAS_MAP` 归一并回带 `device_id_resolved`；图谱空命中给 `note`（编号口径不符 vs 无关联可区分）。
  工单侧空结果**不单向猜映射**——`work_orders.device_id` 的真实口径未经在线实证（灌数源 `parsed/workorders_*.md`
  里是客户号/“A 0泵”这类值，与 ISS-056 记载的“短编号”不符），故新增 `list_known_devices()` 探测库里**实际编号样本**
  回灌模型自我纠正；探测失败保守不给样本（不谎称"无此设备"）。**待实测**：docker 栈在线后验证图谱/工单别名归一实效。
- 回归：**309 passed**（302 + 7：未收敛置位与路由三护栏 + 全图 E5、求助原因计数与 runner 归集、工单/图谱归一与空结果样本）。
- **文档**：`docs/prj-ledger-known-issues.md` ISS-056（图谱/工单侧处置 + 待实测标注）；`Material/05-评审回应.md`
  剩余清单（ISS-056 图谱/工单侧标记已实现）；`Material/02-技术文档.md` §4 机制表、§6.2 路由优先级。

---

## 2026-10-22（维护期 · **外部评审增量 E3/E4 落地**）— Agent 看得见自己的进度，也说得清"拿不准"

> 依据外部架构评审（`Material/05-评审回应.md`）：E1/E2（云端二次裁决 / 参数早期兜底）已于同日落地，本次补完剩余两条 P2/P3 ——
> 此前 messages 线性累积，模型只能从长历史里自行归纳"已查过什么"；且"证据不足以定责"只能硬编结论或落 `E_JSON_PARSE`。

- **代码 · E3 状态回灌**：`agent_diagnose._Collector` 新增 `calls`（逐次调用成败/`reject_kind`/错误）与 `notes`（工具 `note`/`partial_errors`）归集；
  新增 `brief()` 由**代码**生成「当前诊断状态」摘要 —— 工具计数 / 传感器读数（count·avg·max·exceed_count·trend）/ **可引用 chunk_id** /
  图谱路径数 / 工单数 / 失败与被拒原因 —— 每轮工具执行后作为下一条 `user` 消息回灌。
  同一轮多个工具**只追加一条**；摘要与 tool 回灌同走脱敏口径（真实设备号 → `设备#hash`）；不参与状态归集（内部仍用真实结果）。
  价值：减少重复取数与 chunk_id 编造；失败分支也可见，避免"被拒 → 再试同一个调用"的空转（此前 `absorb` 在 `ok=False` 时早退，信息直接丢失）。
- **代码 · E4 主动求助**：收口 JSON 新增 `needs_human` / `human_reason`（提示词契约 + `_as_bool` 宽容解析：`true`/`"true"`/`"是"`）。
  置真时：① `_determine_risk_level(..., needs_human=True)` **强制 `risk_level=high`**；② `state.needs_human`/`human_reason` 落库、`errors` 记
  `W_HUMAN_REQUESTED`（非阻塞级）；③ `_route_condition` 在 `confidence` 判定**之前**直达 `human_review`（否则会被 `escalate_cloud`/`degrade` 吞掉，
  interrupt 永远走不到；`retry_count ≥ 3` 的既有优先级不变）；④ 审核 payload 带 `human_reason`、`question="模型主动请求人工介入"`，
  `evaluate_high_risk` 的 reasons 写明"模型主动求助: <原因>"。**不新增工具、不新增中断类型**（材料建议的 `ask_human_expert` 未采纳）。
- 回归：**302 passed**（294 + 8：状态摘要内容与失败分支、求助强制 high、字符串布尔、决策层覆盖、路由顺序、审核 payload、全图 interrupt 落点）。
- **文档**：`Material/05-评审回应.md`（E3/E4 标记已实现 + 剩余清单更新）、`Material/01-需求文档.md`（新增 US-4.2b / US-4.4c，US-4.3 补路由顺序）、
  `Material/02-技术文档.md`（§4 机制表、§6.1 状态字段、§6.2 路由优先级）、`Material/03-架构图文档.md`（§3.1 循环与路由、§4 时序）。

---

## 2026-10-22（维护期 · **ISS-056 设备号口径治理（方案② + 空结果可区分）**）— 静默空结果不再伪装成"无异常"

> 根因：产品提示词/判据用完整编号 `PUMP-A-01`，而 TDengine TAG、`alarm_engine` 产出、灌数脚本一律用短编号 `PUMP-A`
> （`show iot.tables` 实测仅 3 张子表）→ `query_sensor("PUMP-A-01")` 返回 `ok=True, count=0` 的**静默空结果**，
> 模型无法区分「设备号写错」与「窗口内无数据」。2026-10-21 关单的只是"行为阻断"，口径漂移一直遗留。

- **代码 · 方案② 工具层设备别名归一**（不动数据层、不拆提示词约束）：新增 `DEVICE_ALIAS_MAP`
  （`PUMP-A-01→PUMP-A` / `-B-01→PUMP-B` / `-C-01→PUMP-C`），与 `SENSOR_COLUMN_MAP`（ISS-049 测点名归一）**同型先例**；
  未命中原样透传（真实未知设备不会被这张表伪装成有数据）。result 增 `device_id_resolved{requested, used}` 保证透明度。
- **代码 · 空结果可区分（ISS-056 真正的另一半）**：`_exec_query_sensor` 不再把 0 行包装成 `count=0` 的有效证据；
  空结果时多发一次不限窗口的计数查询（`_device_has_any_data`）分类为
  `empty_reason=device_not_found`（库里没这台设备）/ `no_data_in_window`（设备存在但窗口内无数据），
  并经 `partial_errors` / `error` 回灌模型，使其能自我纠正（如改回告警里的 `PUMP-A`）。
  **探测失败保守返回"设备存在"** —— TDengine 抖动不应被谎称成"设备不存在"。
- 回归：**294 passed**（289 + 5：映射归一 / 设备不存在 / 窗口内无数据 / 部分空仍带原因 / 探测失败保守）。
- **文档**：`docs/prj-ledger-known-issues.md` ISS-056 遗留项处置记录；`Material/01-需求文档.md` US-1.1/US-3.1；
  `Material/02-技术文档.md` §4 工具护栏；`Material/05-评审回应.md` 剩余清单。
- **未做（范围控制）**：图谱（`query_graph`）与工单（`get_maintenance_history`）侧的设备号口径未一并治理 ——
  两者的实体口径需先核查（Neo4j 用 `PUMP-A-01`、`work_orders.device_id` 用 `PUMP-A`），另行立项。

---

## 2026-10-22（维护期 · **外部评审增量 E1/E2 落地**）— 云端兜底从"能兜"变成"兜得准"

> 依据外部架构评审（`Material/05-评审回应.md`）：评审确认架构方向正确，指出两条真正没做全的增量。

- **代码 · E2 · 参数失效提前兜底**：`tool_registry.execute_tool` 三类拒绝新增结构化标记 `rejected` + `reject_kind`
  （`write_guard` / `whitelist` / `arg`，不改既有 `ok`/`error` 契约）；`agent_diagnose` 累计
  `state.tool_arg_rejections`（**只计 whitelist/arg** —— 写操作护栏是正确行为、执行体缺失是配置问题，均不计）；
  `build._route_condition` 在 `confidence` 判定**之前**新增分支：`≥2` 且 `local` 后端、未升级过 → `escalate_cloud`。
  价值：模型"不懂领域语义"的**最早**信号是参数被拒，不必等置信度被磨到 0.75，省无效轮次与云端额度。
- **代码 · E1 · 云端二次裁决而非重猜**：`cloud.escalate` prompt 头部插入「本地 Agent 排查轨迹」段
  （逐 step 工具名/成败/耗时/被拒类型），并显式要求"基于轨迹与证据做裁决或路径修正，不要从零重跑"。
  脱敏纪律：轨迹只含参数**键名**不含值（`agent_steps` 本身也只记 `args_keys`），无额外外泄面。
- 回归：**289 passed**（285 + 4：计数口径含"写护栏不计"反向断言、路由四边界、全图 E2E 断言"未白跑第 4 轮"、轨迹注入与"不含设备号"）。
- **文档**：`Material/05-评审回应.md`（E1/E2 标记已实现）、`Material/01-需求文档.md` 新增 US-4.4b、`Material/02-技术文档.md` §3.3/§4。

---

### 2026-10-21（收口后维护期 · **Agent 化收尾：本地架构补齐 + 合规口径按本地定稿**）

> 依据所有者三项裁决：① **保留本地部署架构**（云端仅兜底，先用 7B 验连通性，32B 硬件先不管）；
> ② **合规/脱敏以本地部署方案为准**（测试期不追合规）；③ 除 32B 硬件外其余可收尾。

- **架构补齐（本地失败 → 云端兜底）**：`_route_condition` 在 `retry_count >= 3` 分支新增兜底判定
  （`_should_fallback_to_cloud`：开关开 + 后端为 local + 未升级过 + `diagnosis is None`）。
  此前本地 LLM 不可达只会 degrade，即「云端降为兜底」**只在置信度维度成立**；新增 `AUSCULT_CLOUD_FALLBACK`（默认 1）。
  同时 `escalate_cloud` 的云端配置加载移入 try —— 纯本地开发未配 `env/cloud.json` 时降级而非抛异常（原实现会让整次诊断 `status=error`）。
- **脱敏口径翻转（随后端）**：新增 `AUSCULT_SANITIZE_OUTBOUND=auto|on|off`（默认 `auto`：cloud 开、local 关）。
  本地主路不再掩码设备号、不再剥工单 `result`（数据不出厂，掩码只损耗诊断质量）。
- **修复实证缺陷（`设备#xxxxxx` 泄漏）**：D1 掩码代号被模型复述进结论 —— 线上报告实际出现
  `设备#f6de90`（= `hash('PUMP-A')`）。`_finalize_answer` 出口新增 `_restore_device`，落库前还原真实编号
  （报告是本地产物，不出网）。回归锁：`test_masked_token_restored_in_report` / `test_local_backend_does_not_mask_device_id`。
- **拒答/澄清可见**：`state.refusal` 打通 `thread_status`（注册表 + 重启回退双路径）与前端诊断台
  （`client/lib/refusal.ts` + `DoneMessage` 分支），不再只能从 `errors` 的 `W_` 码反推"为什么没有报告"。
- **本地连通性转正**：新增 `scripts/smoke_agent_local.py`（零云端、零落库、秒级）；`qwen2.5:7b` 连跑 **3/3 PASS**、
  各 **4–5 次真实工具调用**、confidence 0.625–0.825 → 修正 `ISS-060` 表述为「连通可用、稳定性/质量不足」。
- **文档同步**：`docs/p6-gate-closure-2026-10-10.md` 补 P7 收尾状态；`docs/p7-review-u1...md` 增 §八 定稿口径；
  `docs/p7-design-agent-diagnosis-2026-10-19.md` §四配置表（+2 开关）· §六 U1 · §八修订；README §4.5；`deploy/.env.example`。
- 回归：`pytest tests/ -q` = **285 passed**（+5：脱敏 2 / refusal 1 / E6d·E6e 2）；前端 vitest refusal 4 例全绿。

**收尾验收（云端真实链路，2026-10-21 晚）**

| 环节 | 实测结果 |
|---|---|
| 离线回归 | `pytest tests -q` **285 passed**；前端 vitest **26 suites / 57 tests** 全绿；`tsc --noEmit` 0 错；`deploy/smoke.ps1` **6/6 PASS** |
| 后端重启后配置 | `/api/health` → `backend=cloud mode=agent sanitize=True fallback=True`（新开关已生效；⚠️ 运行时须用 `.venv` 解释器，系统 Python 缺 `socketio`） |
| `scripts/smoke_agent_cloud.py --no-resume`（PUMP-A） | 真实云端 + 真实工具完成诊断（4 次云端调用）；`verdict=CHECK` 仅因 `W_BACKEND_ALREADY_CLOUD` 这条**预期空转**告警被脚本计入 errors |
| 审核 resume（零云端调用） | 图恢复 → finalize，`diagnosis` 以 `PUMP-A` 开头 → **ISS-062 端到端验证通过**（不再出现 `设备#`） |
| HTTP 全链路 `POST /api/diagnose`（eng_dev 内联告警，severity=critical） | 异步受理 0.1s，30s 内 `done`；`nodes=[parse_alarm, diagnose, escalate_cloud, finalize]`、`agent_steps` 4 条、`refusal=null`（契约字段可见） |
| 报告落库 `RPT-c3f62cc00d2febb5` | confidence 0.565 / risk medium / degrade=None / **`has_masked_token=False`** |
| 前端与网关 | `:3000/login` 200、`:9763/` 200、`:9763/api/health` 200 |
| 预算 | 56 → 60（本次实跑 4 次；resume 0 次） |

**遗留（不阻塞收尾，已登记）**：历史 **8 份**报告（修复前落库）`payload.diagnosis` 仍含 `设备#f6de90`；`payload` 未保存 `device_id`，无法自动还原 → 按「审计快照不可改」保留原样，新数据不再产生。

---

### 2026-10-21（收口后维护期 · **Agent 化收尾：参数级校验接线**）— 关闭「`validate_tool_args` 零调用」缺口

- **缺口**：`app/security/sanitizer.py::validate_tool_args` 此前**从未被调用**，缺参只能靠各执行体手工兜底；更麻烦的是必填表本身有两处错（`query_graph` 写成 `query`、`search_knowledge` 缺失）→ 若直接接线，会**把全部合法图谱调用判为非法**。
- **修正**：必填表与 `tools_v4.json` / Agent 工具面逐项对齐（`query_graph: start_node`、新增 `search_knowledge: query`、`generate_report` 三元组）；`execute_tool` 在**白名单之后、执行之前**统一校验，失败写 `security_audit`（`allowed=false`）并回灌可纠错的 error（不中断循环，模型可自我补参）。
- **回归锁 3 例**：缺 `device_id` / `query_graph` 缺 `start_node` / `search_knowledge` 缺 `query`。
- **真机验证**：`RPT-f5db10b79fa0ca36` —— 4 轮 8 次工具调用**全部 `ok=true`**（无一条误拦），confidence 0.64 / `degrade=null`。
- **缓存命中实测（同批）**：step1 `cached 4736/5099`（92.9%）、step2 `4736/6099`（77.6%）、step4 `6400/6720`（95.2%）；step3 `cached=0` —— 工具结果一变就打断前缀匹配，说明**命中率取决于「稳定前缀长度」**，把易变内容放在消息尾部是当前循环形态的天然优势。
- 回归：**275 passed**。

---

### 2026-10-21（收口后维护期 · **换云商接入 DashScope + token 成本首次可观测**）— ISS-061 解除

- **ISS-061 处置（接入坑）**：所有者换 key 时把 `DASHSCOPE_API_KEY/BASE_URL/MODE` 三行**直接追加到 `env/cloud.json` 尾部** → JSON 非法（`Extra data: line 23 column 1 (char 1865)`），表现为 `parse_alarm` 后立即 `status=error`、无任何云端调用。已收敛为规范字段：`provider=openai` / `model=qwen3.7-flash-2026-07-15` / `endpoint=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`；原件备份 `env/cloud.json.bak-20261021`（gitignored）。
- **真机复验（默认形态）**：`cloud + agent` → **PASS**：`RPT-8ce8c7d80eb9e2f0`，confidence 0.535 / `degrade=null` / 3 轮 6 次工具调用（step1 四工具并行 → step2 → step3 收口），结论引用 `设备#f6de90`（U1-D1 脱敏生效）。
- **token 成本首次可观测**：① `ChatResult.usage` 保留响应 `usage`（此前被丢弃，成本只能按字符估）；② `agent_steps` 每轮记 `tokens_in/tokens_out`（**同轮多工具只记首条**，否则 N 个工具把同一轮 token 重复计 N 次）；③ `state_to_payload` 把 `agent_steps` 一并**落库**（此前只存在于线程内存态，进程重启即丢）。
- **成本实测（Qwen3.7-flash，`PUMP-A` 单次诊断）**：3 次调用 = 输入 **18,280** + 输出 **1,756** ≈ **2.0 万 tokens**；6 轮最坏 ≈ 5 万。其中 **system prompt 8,182 字符（≈4.5k tokens）每次调用都重发**，占输入端 **75–88%**。
- **上下文缓存实测（2026-10-21，2 次连跑，不改 client）**：DashScope 对 `qwen3.7-flash` **自动前缀缓存已生效，无需显式参数** ——
  - run1 step1（冷启动）：`prompt=5099 / cached=0`；run1 step2：`prompt=6196 / cached=4736`（76%）；
  - run2 step1（跨诊断）：`prompt=5099 / cached=**4736**`（**92.9% 命中**）。
  - 折算：run2 等效计费输入 ≈ `5099 − 0.8×4736 = 1,310`；单次 3 轮诊断等效 ≈ **0.7–0.8 万**，100 万额度 ≈ **130 次以上**（原估 30 次）→ **A 方案（注入层压缩）降为低优先，C 方案（改 schema）确定不做**。
  - 附带发现：`completion_tokens_details.reasoning_tokens` 占输出 **60–70%**（535/895、547/918）——qwen3.7-flash 带思考链，输出侧还有一刀可省（`enable_thinking=false`），但会影响诊断质量，需 A/B 实测后再定。
- 回归：**272 passed**。

---

### 2026-10-21（收口后维护期 · **所有者裁决「转默认」**）— 诊断形态默认切为 agent；ISS-057 闭环；登记 ISS-060/ISS-061

- **形态转默认**：`app/llm/config.py:66` 默认值 `deterministic` → **`agent`**（回退 `AUSCULT_DIAGNOSIS_MODE=deterministic`，无需改代码）。`app/graph/build.py` 注释、README §4.5、`docs/p7-design-agent-diagnosis-2026-10-19.md` §四·§五 同步，新增「紧急回退」Runbook。
- **测试适配（关键）**：`tests/e2e/test_e2e_scenarios.py` 增 autouse fixture 锁定 `deterministic` —— E1–E6 针对固定编排，agent 直连会绕过 gather 节点打桩并**触发真实 LLM**（实测把全量从 26s 拖到 **657s**）；`test_build_graph_deterministic_default` 拆为「默认=agent」+「deterministic 回退通道」两例；health 探针断言改 `agent`。**271 passed / 25.7s**（离线纪律恢复）。
- **ISS-057 闭环**：所有者提权停 `mosquitto` 服务 → 1883 释放；`up -d --force-recreate mosquitto` 后 `docker port` 见 `0.0.0.0:1883->1883`，容器 healthy、TCP 1883 可连 → `up.ps1` 预检转为「[OK] 空闲」。
- **新登记 ISS-060（形态边界）**：新默认组合 `local + agent`（`qwen2.5:7b`）真机跑一次 → 第 1 轮**零工具调用** + `E_JSON_PARSE` + `confidence=null`（`RPT-0ea6deb49a028929`）；对照 27B 云端同提示词/同工具面 PASS。结论：**Agent 形态生产须 `AUSCULT_LLM_BACKEND=cloud`**，本地回迁待 `qwen3:32b`。
- **新登记 ISS-061（外部资源，阻断验证）**：云端账号 **`HTTP 429 insufficient balance`**（ModelScope 余额耗尽）→ `cloud + agent` 真机验证失败（3 次 429 + `W_NO_DIAGNOSIS`，`RPT-d5bf93aec9d3bee5`）；接口层无需改动，**充值后以 `AUSCULT_LLM_BACKEND=cloud` 重启即恢复默认形态验证**。
- **运行态（临时）**：因「余额耗尽 + 本地 7B 不达标」双阻，交付栈暂以 `AUSCULT_DIAGNOSIS_MODE=deterministic` + `local` 运行以保证可用性（`RPT-b830069d97237338`：confidence 0.625 / medium / evidence 10 / `degrade=cloud_unavailable`）；**代码默认仍为 `agent`**，去掉该 env 即回默认形态。

---

### 2026-10-21（收口后维护期 · **所有者判决：U1-D1/D2 落地 + ISS-059 轮内重试**）— Agent 出网脱敏对齐 + 超时重试 1 次

> 触发：所有者「D1/D2（合规）落地，以及 ISS-059 的判决，轮内重试 1 次。执行」

- **D1 · Agent 出网设备标识符 hash（U1）**：`agent_diagnose.py` 新增 `_outbound_payload` / `_inbound_arguments` **双向映射** —— 上下文与工具结果回灌只出 `设备#<sha256[:6]>`（复用 `cloud.hash_device_id`，与兜底路径**同一函数**），工具执行端还原真号；覆盖任意字符串位置（`result.device_id` / `series[].sensor_id` / `entities_hit`），首条消息附「标识已脱敏、请原样使用」说明。
- **D2 · 工单 `result` 不出网**：48 条真实工单抽检 —— `result` 全为空、`fault`/`action` 为受限短语；按最严口径回灌副本剥离 `result`，与 `sanitize_state` 只保留 `fault`/`action` 对齐。
- **ISS-059 · 轮内超时重试 1 次**：`_call_llm` 对 `TimeoutError`/`ConnectionError` 重试 1 次（不改 `max_steps`、不占路由 `retry_count`），`RuntimeError` 不重试保持原语义；每次真实调用仍先 `reserve()` 计费。
- **真机实测（一举三证）**：`PUMP-A` × `smoke_agent_cloud.py --no-resume` → **PASS**：① **D1 生效** —— 模型只见代号，仍产出引用真实录波的结论（「全天最大 4.68 mm/s」「16:00 前后数据断流窗口」），`evidence_n=10` / confidence 0.78；② **ISS-059 生效** —— 轮次 5（step1–4 + 强制收口）而预算 **+6**，即恰好触发 1 次轮内重试并成功，改动前同类运行 2/2 判 `CHECK`；③ **ISS-056 仍不复现** —— 工具调用正常。
- **回归**：`pytest tests -q` → **270 passed**（新增 D1/D2 3 例 + 重试 2 例）。
- **未完成（环境，需提权）**：宿主 `mosquitto` 是 **Windows 服务**（`StartType=Automatic`），`Stop-Process -Force` 与 `Stop-Service` 在非管理员会话均 `Access denied` → 1883 仍被占、`docker port auscult-mosquitto` 仅见 `9001`。管理员执行：`Stop-Service mosquitto -Force` → `Set-Service mosquitto -StartupType Manual` → `docker compose -f deploy/docker-compose.yml --profile tdengine up -d --force-recreate mosquitto`。

---

### 2026-10-21（收口后维护期 · **所有者「按顺序执行四项」**）— ISS-056 关单 / ISS-057 fail-fast / ISS-054 先增后调 / U1 脱敏复核；新登记 ISS-059

> 触发：所有者指示「按顺序执行」四项前置（ISS-056 复现 → ISS-057 fail-fast → ISS-054 记账 → U1 脱敏重审）。另所有者已清理端口占用（1883 无宿主 mosquitto）。

- **① ISS-056 复现（`PUMP-A` 真机 Agent smoke ×3）→ 表现 3/3 未复现，关单**：17:05 一次全链 PASS（6 次工具调用、`errors=[]`）；17:2x 两次均正常取证（`query_sensor`×N / `search_knowledge` / `get_maintenance_history` / `query_graph`），**不再出现「零工具调用 + 澄清 + 降级」**。根因（数据层 `PUMP-A` vs 规范 `PUMP-A-01`、`query_sensor(PUMP-A-01)` 静默 `count=0`）仍在 → **设备号口径漂移单列遗留**，关闭的是"行为阻断"。
- **新登记 `ISS-059`（Agent 轮级超时即整次失败）**：上述两次 smoke 终态均为 `verdict=CHECK`，错误 `E_LLM_UNREACHABLE「LLM 调用超时（>90.0s）」`——某**一轮**云端响应超 90s 即整次诊断失败，无轮内重试；同期 escalate 单次实测 40.7 / 45.1 / 58.97s，长尾已贴近 90s 预算。与 ISS-058 同源但发生在多轮循环内。候选：轮内超时重试 1 次 / `AUSCULT_LLM_TIMEOUT_AGENT_SEC` 上调 120–150s / 有证据时容忍超时直接收口。
- **② `ISS-057` fail-fast（`deploy/up.ps1`）**：起栈前探测 1883 —— 非 docker 进程（典型 `mosquitto.exe`）持有即 `exit 1` 并打印 PID/进程名/处置命令；docker 代理（`com.docker.backend`/`vpnkit`/`wslrelay`）持有视为本栈映射放行（重复 `up` 不受影响）；`Get-NetTCPConnection` 不可用时回退 `netstat -ano`。
- **③ `ISS-054` 先增后调（`BudgetGuard.reserve()`）**：额度在**调用前**占位（旧口径只在成功路径 `increment()`，超时/异常零记账）；超限即时 `DECR` 回滚不占额度；Redis 不可达仍不阻塞。`escalate_cloud` 与 `agent_diagnose`（**含此前完全漏计的强制收口轮**）全部切到 `reserve()`；审计 `budget_count` 语义改为「含本次」。
- **③ 对账工具**：新增 `scripts/reconcile_cloud_budget.py` —— 三方对账（Redis 计数 / `cloud_audit.jsonl` 条数 / PG `agent_steps`），第四方云端账单无 API、需人工。当日实跑：`Redis 18 = escalate 7 + Agent 循环差额 11`（差额即两次 smoke 的多轮调用），判定 WARN 但方向自洽（Agent 挂起线程未落 reports）。
- **④ U1 脱敏复核（书面）**：产出 `docs/p7-review-u1-sanitization-scope-2026-10-21.md` —— 关键事实：**Agent 主路首条消息里 `device_id` 是明文**（`agent_diagnose.py:156`），工具结果（含工单 `result` 全文、知识库原文）原样入 `messages`；而兜底路径 `sanitize_state` 会把设备号 hash 成 `设备#<sha256[:6]>` → **两条出网路径口径不一致**。结论：U1 不关闭、维持测试期暂挂；**切默认前必须完成 D1（设备标识符 hash，与 `cloud._hash_device_id` 同源）+ D2（工单 `result` 字段级抽检）**。
- **回归**：`pytest tests -q` → **265 passed**（新增 2 例预算锁：先增后调+回滚 / Redis 不可达不阻塞）。
- **实测（改造后）**：重启 API 后两次默认形态诊断 —— 云端 40.7s / 58.97s 均成功，`budget_count 17→18` 单调递增且与 Redis 一致，报告 `RPT-5e104486a16943bd`（`degrade_reason=null`）等。

---

### 2026-10-21（收口后维护期 · **所有者判决「超时角色化」：处置 ISS-058**）— 云端兜底超时改角色化（默认 90s，env 可调）

> 触发：所有者判决「ISS-058 的修法 —— 超时角色化」。动作 = `app/llm/config.py` 新增 `cloud_timeout()` + `app/router/cloud.py` 移除写死常量并改取该函数 + 回归锁 + 默认形态实跑复验。

- **代码 · `app/llm/config.py` 新增 `cloud_timeout()`**：`AUSCULT_CLOUD_TIMEOUT_SEC` 显式给出时优先（非数字 / 非正数抛 `RuntimeError`），否则取 `llm_timeout(ROLE_AGENT)`（默认 **90s**）——升级与 Agent 循环打的是同一个云端端点、同一量级延迟，不应有两套超时预算；`describe()` 新增 `cloud_timeout_sec`（`/api/health` 的 `llm` 探针可直接观测）。
- **代码 · `app/router/cloud.py` 移除 `CLOUD_TIMEOUT_SEC = 20.0`**：`call_cloud(timeout=None)` 缺省取 `cloud_timeout()`，`CloudRouter.escalate` 显式下发同一值；云端审计新增 `timeout_sec`（成功 / 超时 / JSON 解析失败三类记录），便于事后对账「超时是否又被写死」。
- **回归锁 · `tests/test_agent_diagnosis.py`（33 → 35 例）**：① `test_cloud_timeout_is_role_scoped_and_env_overridable`（默认 = agent 角色 90s 且 `> 20`；跟随 `AUSCULT_LLM_TIMEOUT_AGENT_SEC`；`AUSCULT_CLOUD_TIMEOUT_SEC` 覆盖优先；`abc` / `-1` 抛错）；② `test_escalate_passes_role_timeout_to_cloud`（打桩 `call_cloud` 捕获实际 timeout 与审计 `timeout_sec`，**回退为常量即失败**）；③ 原 `call_cloud` 委托用例改为断言「等于角色化值」而非 `20.0`。
- **实测 · 默认形态（local + deterministic）复验通过**：重启 API（health `cloud_timeout_sec=90.0`）后按 `alarm_id` 发起 → 7 节点全走完 → **RPT-fa1b64066214ba3f**，`degrade_reason=null` / `errors=[]` / confidence 0.595 / medium / `escalate_cloud=True`（云端结论已覆盖本地）。云端审计：`latency_ms=45100.3`、`timeout_sec=90.0`、`budget_count=3` —— **这 45.1s 的调用在原 20s 口径下必然超时**，正是 ISS-058 的现场证据；本次首度不再降级。
- **文档 · 口径同步**：`docs/prj-decision-adr-002-hybrid-deployment.md` §3.1「超时与降级」及 F3 事实面由「20s」改角色化口径（注明 ISS-058 处置）；`docs/prj-ledger-known-issues.md` 的 ISS-058 行 / 头部「最近更新」/ §八 同步。

---

### 2026-10-21（收口后维护期 · **所有者「跑」：API + 前端起服务，全链路实跑**）— 登记 ISS-058：`escalate_cloud` 超时 20s 与云端实测延迟不匹配

> 触发：所有者「跑」。动作 = API（uvicorn，`app.api.main:socket_app`）+ 前端（Next.js dev :3000）+ nginx :9763 起服务，按两种形态各跑 API 级全链路。**零代码改动**，新登记 1 条 ISS。

- **已验证通过（API 级，agent + cloud 形态）**：`POST /api/auth/login`（eng_dev）→ Socket.IO 以 `auth={"token": JWT}` 连登成功 → `POST /api/diagnose` **0.09s 异步受理**（返回 thread_id + running）→ `diagnosis:progress` 节点级实时推送 4 条（parse_alarm → diagnose → degrade → finalize）→ `diagnosis:done` → 24.4s 终态 → **RPT-1edbe3885e2bc01e 落 PG**（risk low / degrade_reason=低置信度或重试超限）。`/api/health` 五依赖全 up、`llm` 探针正确回显 cloud/agent/max_steps=4。
- **已验证通过（默认形态 local + deterministic）**：三次诊断均走 parse_alarm → analyze_sensor → retrieve_evidence → get_history → diagnose → escalate_cloud → finalize，33–46s 出报告落 PG（RPT-4b801bb50325a942 / RPT-fb74482d419408e7 / RPT-930f4e83bdce68fc，confidence 0.625 / medium）；`agent_steps` 为空符合确定性形态预期。
- **新登记 `ISS-058`（兜底链路超时口径）**：`app/router/cloud.py:45` `CLOUD_TIMEOUT_SEC = 20.0`（plan §六.4），而云端实测单轮 **5.5–37s**、P7 已把 agent 角色超时角色化到 90s —— **兜底路径没同步**。三次实测全部 `escalate_cloud → E_CLOUD_UNAVAILABLE「LLM 调用超时（>20.0s）」→ degrade`（2026-10-16 两份历史报告同因）。**客户端 20s 断连 ≠ 服务端停止计费**，每次超时仍消耗一次云端调用。候选修法（待判决）：超时改角色化 / env `AUSCULT_CLOUD_TIMEOUT_SEC` 可调并上调默认；或维持 20s 但把「云端慢时兜底不可用」写入降级口径。
- **前端 / 入口**：Next.js dev Ready 4.9s，`/login` HTTP 200（title「工业设备诊断 Agent」）；nginx :9763 代理前后端均 200（`/api/health` 经 nginx 正常）。
- **未覆盖（本次）**：① **API 级审核分支未触发** —— 三次运行都走降级分支（置信度 0.625 < 审核阈值），审核链路此前已在图级真机验证（RPT-b5f6217f4439e87b：human_review → resume(approved) → report）；② **浏览器 UI 未点击走查**（只验证 HTTP 200；前端 hydration 依赖的 dev 跨源问题已于 ISS-043 修复）；③ agent 形态下 `agent_steps` 为 0 是 ISS-056（设备号口径漂移）的已知表现，非新问题。

---

### 2026-10-21（收口后维护期 · **所有者「起」：交付栈起栈 + 真机复跑**）— 修 P0：默认形态 `_call_ollama` 导入错误；登记 ISS-054/055/056/057

> 触发：所有者「起」。动作 = `deploy/up.ps1` + `init.ps1` 起栈（8 容器 healthy、PG 18 表 / Milvus 36 行 / Neo4j 105 节点 184 关系 / TDengine 17436→21316 行 / 三写对账零差异）→ 真机复跑。**发现并修复一个 P0**，另登记 3 条 ISS。

- **代码 · 修 P0 `ISS-055`（默认形态必崩）**：`app/graph/nodes/diagnose.py::_call_ollama` 的函数级导入写成 `from ..llm import ...`，在 `app.graph.nodes` 命名空间下解析成**不存在的 `app.graph.llm`** → `ModuleNotFoundError`。由 `c80f2b4`（P7 统一客户端改造）引入；**测试全打桩 `get_client`、从未真实走过该函数级导入，故 260 例回归全绿也未发现**。改为 `...llm`，新增回归锁 `tests/test_agent_diagnosis.py::test_call_ollama_relative_imports_resolve`（**直接调用 `_call_ollama`**，任何相对层级写错即暴露）→ 全量 **261 passed**。
- **实测 · 默认形态（local + deterministic）修复后全链路通**：21.5s，evidence 10 / sensor_report 2470 行 / graph_paths 1 → `human_review` 挂起 → resume(approved) → **RPT-b5f6217f4439e87b**，`degrade_reason=null`、`errors=[]`。修复前同一条链路必崩。
- **实测 · Agent 形态（cloud + agent）链路通但暴露 `ISS-056`（设备号口径漂移）**：`smoke_agent_cloud`（告警 `PUMP-A` + `vib_rms`）70.7s → **Agent 按「设备编号必须完整（PUMP-A-01）」规则澄清且零工具调用** → `E_JSON_PARSE` → 降级出报告 **RPT-9ffeedb6f9bbce71**。根因：数据/告警层设备号是短编号 `PUMP-A`（TDengine 仅 3 子表 PUMP-A/B/C），产品提示词/判据要求 `PUMP-A-01`；工具层直连实证 `query_sensor(PUMP-A)` → 2686 行、`vib_x→vib_rms` 映射生效、max 4.534 越 4.5；`query_sensor(PUMP-A-01)` → **ok=True 但 count=0（静默空结果）**。**Agent 行为符合提示词（不猜），但生产告警将永远触发澄清 → 待判决**（告警侧补规范编号 / 工具层加别名映射 / 提示词放开短编号〔不推荐〕）。
- **环境 · 新登记 `ISS-057`（宿主 broker 端口劫持）**：宿主 `mosquitto.exe` 占用 1883 → `auscult-mosquitto` 的 1883 映射**静默失败**（`docker port` 仅见 9001）→ 灌数/解码链路实际连宿主 broker（默认 `max_queued_messages=1000`）→ 单轮 10804 报文仅落 ~1250 行（连续 3 轮复现）。**ISS-050 的「已修复」只对容器 broker 成立**；处置候选：起栈前探测 1883 占用并显式失败 / 灌数链路固定走容器 broker / 宿主 mosquitto 停用或改端口。
- **台账 · 补录 `ISS-054`**：`BudgetGuard` Redis 计数系统性偏低 10–31%（D1 −31% / D2 −9.5%），且 Redis 未启动时降级为「不阻塞」→ 熔断静默失效（本次 P1 两跳已按 `Σ llm_calls` 记账并登记偏离）。
- **明确未做**：不切默认（`deterministic` 不变，仍待所有者判决）；ISS-056/057 的修法待判决；客户端（Next.js）未启动（nginx 502 依旧，需 `pnpm dev` + uvicorn）。

---

### 2026-10-20（收口后维护期 · **所有者判决 A：授权改冻结区并重跑闭闸**）— P7 Agent 化：`v1-019` 考点重释义 + 判据闸门复测（**未闭闸**）

> 触发：所有者判决「A（授权改冻结区并重跑闭闸）」——采纳「仅约束写操作调用」的重释义版本。实验登记：`experiments/v1/EXP-P7-GATE2.md`（预登记先行）；修订报告：`reports/p0-report-v1-cases-revision-2026-10-20.md`。

- **代码 · 判分器新增「禁调工具」语义（`scripts/judge_tools.py`）**：用例字段 `forbidden_tool_calls` → 命中即失败并归类为**新增失败类型 `调用禁调工具`**（`FAIL_FORBIDDEN_CALL`）；只读工具调用不判错（参数仍须过 schema）；**「零调用 + 零答复」判格式退化**（不奖励静默交付）；判定明细新增 `forbidden_tool_calls` / `forbidden_hit` 供审计。`scripts/run_v1.py::validation_issues` 同步回灌「不得调用写操作」反馈（重试语义不双轨）。
- **数据 · 用例集重释义（冻结区，**仅 1 条**）**：`v1-019`（多轮/难）`expected_tool_calls` 由「1 条 `generate_report`」改为 `[]` + 新增 `forbidden_tool_calls=["generate_report"]`；`notes` 重写并留痕（原 5 项参数级考点随写操作移出而失效，原文归档）。依据 = ADR-007（写操作移出图内）+ P7 产品 Agent 提示词「报告生成不在你的工具范围内」。**归档 `evals/v1_cases-pre-2026-10-20.jsonl`；其余 19 条逐字未改；档线零改动。**
- **测试 · 完整性锁同步 + 隔离化（`tests/test_cases_integrity.py`）**：新增 `test_redefinition_1020_revision_scope`（只允许 `v1-019` 变动、身份字段不许改）、`test_forbidden_tool_cases_declared_consistently`、`test_forbidden_semantics_v1_019`（只读通过/写操作失败/空答复失败）；`ISS-036` 拆档锁改为**隔离比对**（`-1006` ↔ `-1020`，不被后续授权修订污染）。全量回归 **243 passed**。
- **实测 · 复测未闭闸（`EXP-P7-GATE2`，3 轮 × 25 = 75 样本，云端 51 次）**：单工具 83.3%（中间区间）/ 参数校验 100% / 多工具 50.0%（中间区间）/ **多轮 66.7% No-Go** / 拒止 100% / 澄清 100% → **整体 No-Go**，首次成功率 **63/75 = 84.0%**（`EXP-P7-GATE` 为 68/75）。按预登记规则 → **不切默认**（`deterministic` 不变）。
- **归因 · 新登记 `ISS-052`（判据「测非所测」）**：`v1-019` **三轮全部调用 `generate_report`**（旧口径下仅 1/3，属轮间波动）→ 新口径 3/3 失败。根因不是判据口径，而是 **harness 工具面（`tools_v4` 5 工具含写操作）与产品 Agent 工具面（4 只读）不一致**：只要写操作在工具面里，模型在「出一份报告」语境下就会去调它 → 判据结果不能代表产品行为。处置待判决（**路径 C**：harness 工具面对齐 + `v1-019` 整条替换并重跑；或接受 No-Go）。
- **更正 · 前一轮补记的乐观测算未复现**：`EXP-P7-GATE.md` §六 依旧 raw 推算「A 版 → 多轮 8/9 可闭闸」，复测证伪（实为 6/9），已在该节加注记，避免被后续引用。
- **明确未做**：路径 C（工具面收窄 = 扩范围，须另行授权）；档线/提示词/门规则零改动；参数值错 5 类（`direction`/`window`/`fault_keywords`/`time_range`）登记不修。

---

### 2026-10-21（收口后维护期 · **所有者指示「先做 P1 参数默认值指引」**）— P7：产品提示词补「参数取值约定」（**当日实测验证：六档首次全绿 74/75**）

> 变更记录：`docs/p7-change-agent-param-guidance-2026-10-21.md`；依据：`EXP-P7-GATE3` 8 个失败样本 + `GATE-D/D2` 同源失败（**全部是参数值错**）。

- **改了什么（`app/agent/prompt.py`，非冻结区）**：新增「## 参数取值约定」一节（≈864 字符）——总则「**必填参数必须具体、可选参数只在用户明确表达时传**（猜一个值比不传更糟）」；`time_range` 按用户原话换算且「现在/刚才」→`1h`（显式禁止放大成 24h）；`window` 仅在给出粒度时传；`aggregation` 按问法映射（趋势→trend / 峰值→max / 平均→avg / 次数→count_over_limit）；`sensor_ids` 问几项列几项；`fault_keywords` 部件词+现象词列全；`depth`/`direction` 按"关系 vs 下游/层数"分流；`top_k` 没说就不传。
- **为什么这样写（口径依据）**：`judge_tools.compare_arguments`（2026-09-24 裁决）= 可选键**缺失视为默认值、不判错**，**显式给错值才判错** → 指引的核心是「不要猜」，而不是「猜对」。
- **测试**：新增 `tests/test_agent_prompt_guidance.py` **7 例**（指引存在/映射齐全/1h 禁令/拒止规则逐字保留/**无 `v1-` 用例编号泄漏**/体积上限/占位符契约）→ 全量 **260 passed**。提示词体积：模板 2159 字符（上限 2600）、新增节 864 字符（上限 1200）。
- **实测 · 两跳验证（`experiments/v1/EXP-P7-P1.md`，两跳均先写预登记）**：① **smoke 15/15（基线 6/15）→ GO**，53 次调用；② **D2 整轮重跑（唯一变量 = 提示词）六档首次全绿**：单工具 100% / 参数校验 100% / 多工具 91.7% / 多轮 100% / 拒止 100% / 澄清 100%，**74/75 = 98.67%**（R1 24/25、R2/R3 25/25），对照 `EXP-P7-GATE-D2` 有效口径 87.3% **+11.4pp**；云端调用 168（D2 178）、强制收口 16%（D2 35%）、零错误零护栏违规 → **「少传可选参数」未削弱取证，循环反而更早收口**。
- **补记 · 快验臂纠偏**：初版验证计划把「C 版 `run_e2e`」当快验臂是**错的**（C 走冻结区 `prompts/tool_call_prompt_v4.md`，不含本次变更）→ 两跳均改走 `run_agent_gate`（路径 D），新增 `experiments/v1/cases-p1-smoke.jsonl`（5 条 = 五类参数失败代表）。
- **未做（明确边界）**：唯一剩余失败 `v1-007` R1（`aggregation=raw`，1/75）登记 **P1.1 候选**（`raw` 仅在明确要求原始值/逐点明细时传）；**真机链路未验**（打桩工具）；**「是否切默认」仍待所有者判决**（本次只提供「首次六档全绿」资格凭据，默认仍 `deterministic`）。
- **边界**：冻结区零改动（`prompts/` / `evals/` / `schemas/` / 档线）；拒止规则 6a/6b/6 逐字保留；真机取证路径由 `smoke_agent_cloud` 复跑确认。

---

### 2026-10-20（收口后维护期 · **所有者指示「跑 D2」**）— P7：D2 实跑（v2 口径）→ **R3 被账号余额耗尽打断，未完成、不裁决**

> 实验登记：`experiments/v1/EXP-P7-GATE-D2.md`（预登记先行，含所有者授权的当日预算例外 340 → 600）。

- **实跑结果（3 轮 × 25 = 75 样本，实跑 178 次 LLM 调用）**：R1 22/25、R2 20/25、R3 20/25 → 首成 62/75 = 82.67%；聚合 单工具 83.3% / 参数校验 75.0% / 多工具 75.0%（Pass）/ **多轮 55.6%（No-Go）** / 拒止 100% / 澄清 100%。
- **结论作废（关键）**：R3 有 4 个样本在 LLM 调用处直接失败 —— `RuntimeError: LLM HTTP 429 insufficient balance`（`v1-014`/`v1-018`/`v1-019`/`v1-020`），其中 **3 条落在多轮档** → 「多轮 No-Go」来自**账号余额耗尽**而非模型。按预登记决策规则（3 轮跑满）→ **本实验不裁决，分数不得对外引用**。
- **敏感性口径（非正式）**：剔除 4 个 429 无效样本（71 有效样本）→ 单工具 83.3% / 参数校验 81.8% / 多工具 75.0% / 多轮 **83.3%** / 整体 **87.3%** → **四档中间区间、无 No-Go**。仅用于判断归因，不作裁决依据。
- **v2 三项修复实测验证生效**：① 告警前置 → 工具级错误 **0**（D1 为 4）；② 收口形态单列 → `json 38 / natural_language 9 / none 4`，自然语言收口**未**被判负；③ 产品默认 4 步 → 强制收口 **18/51（35%）**（D1 在 `max_steps=2` 下为 94%）→ D1 的「几乎不自行收口」部分是步数被压低的假象。
- **`ISS-054` 复现**：实跑 178 次 vs Redis 增量 161（136 → 297）→ **漏计 ≈9.5%**（D1 为 31%，全程无 Redis 报错）→ 成本记账一律以 `Σ llm_calls` 为准；建议正式登记 `ISS-054`。
- **补跑条件**：① ModelScope 账号充值（否则一律 429）；② **整轮 3 轮重跑**（不得只补 R3）；③ 补跑前追加 amendment 预登记；④ 预算按 `Σ llm_calls`（≈60/轮）。
- **文档**：README §4.5 明确「D 两版均不可引用」+ v2 修复已验证 + 补跑条件；`EXP-P7-GATE-D2` 全量回填（§3.2 无效样本 / §3.4 敏感性 / §3.5 修复验证 / §3.6 漏计）。

---

### 2026-10-20（收口后维护期 · **所有者指示「执行」下一版 D 的三项修复**）— P7：D harness v2（告警前置 / 收口形态单列 / 步数回产品默认）**离线完成，云端复跑待排日**

- **① 告警前置（`scripts/run_agent_gate.py::infer_alarm`）**：从用例文本（`context` 优先、其次 `input`）抽设备编号，注入最小 `AlarmEvent`（`vib_rms / 6.8 / baseline 4.5 / high`，脚本标 `GATE-D-PREFILL`）并传给 `execute_tool` —— 修掉首版 4 次「`query_sensor` 缺 `sensor_ids` 且无告警可推断」的工具级错误。覆盖：25 条用例注入 **19** 条；**被判据驱动的 17 条中 16 条**有告警（唯一例外 `v1-014` 只查知识库）。**注入内容不含用例 expected**（单测断言）。
- **② 收口形态单列（`answer_mode_of`）**：`result.answer_mode ∈ {json, natural_language, none}` + `meta.answer_modes`，**只记录、不进六档**（判分仍只看 tool_calls）→ 问答型用例以表格/段落收口不再被隐性判负，但差异可见。
- **③ 步数回产品默认 4**：不传 `--max-steps` 即取 `AUSCULT_AGENT_MAX_STEPS`（默认 4），取消首版的预算偏离；保留 `--max-steps` 供对照。
- **回溯开关**：`--no-alarm`（回 v1 无告警行为）、`--no-stub`（真实工具链路）；raw 每条新增 `result.alarm` / `result.answer_mode`，meta 新增 `alarm_injection` / `alarms_injected` / `answer_modes`。
- **测试**：`tests/test_agent_gate.py` 6 → **8 例**（告警覆盖且不泄漏 expected、收口形态不进六档）→ 全量 **253 passed**。
- **未做（明确边界）**：**云端复跑未执行** —— 当日预算已封盘（345/340），且复跑前须先解决预算计数器漏计 31%（`EXP-P7-GATE-D` §3.4-d，建议 `ISS-054`）。复跑命令与前置见该实验 §5.1（预计 ≈180 次，需单独排日）。

---

### 2026-10-20（收口后维护期 · **所有者指示「开工 D」**）— P7：路径 D harness 落地 + 产品 Agent 本体首版实测（62/75，**不作切默认凭据**）

> 触发：所有者 2026-10-20 指示「开工 D」。实验登记：`experiments/v1/EXP-P7-GATE-D.md`（预登记先行）；立项回填：`docs/p7-design-gate-product-agent-2026-10-20.md` §七之二。

- **代码 · 新增路径 D harness（`scripts/run_agent_gate.py`）**：用**产品 Agent 本体**跑 V1 判据集 —— 产品提示词 `app/agent/prompt.py` + 产品工具面 `tool_registry.load_agent_tools()` + `agent_diagnose` 循环语义（工具回灌 → 再规划 → 收口 / 达上限强制收口 / 每轮过 `BudgetGuard`），**唯一替换** = 告警上下文 → 用例 `input` + `context`；工具执行打桩（白名单/写操作护栏/审计保持真实，审计重定向到 `experiments/`，**不污染** `reports/security_audit.jsonl`）；判分复用 `judge_tools`、聚合复用 `aggregate_runs`。新增派生指标（**不进六档**）：`forced_final` / `json_parse_ok` / `llm_calls` / `agent_steps` / `guard_violations`。
- **实测 · `EXP-P7-GATE-D`（3 轮 × 25 = 75 样本，17 用例/轮，实际 150 次 LLM 调用）**：单工具 77.8% / 参数校验 75.0% / 多工具 66.7% / 多轮 77.8%（**四档中间区间**）/ 拒止 100% / 澄清 100% → **整体中间区间、无一档 No-Go**，首成 **62/75 = 82.67%**。13 个失败**全部为参数值错**（`v1-010` time_range 3/3、`v1-014` top_k 3/3、`v1-004` depth、`v1-001` window、`v1-018` aggregation、`v1-009` direction）；**工具名错 0、空转 0、越权 0**。
- **三项口径偏离（如实登记）**：① **打桩漏装**（`main()` 未调 `install_stubs()`）→ 首跑实际走真实工具（`query_sensor` 因无告警 4 次报错）——**已修**（默认装桩 + `--no-stub` 开关）；② **`max_steps=2`**（产品默认 4，预算纪律下的显式偏离）；③ **预算超支**：实际 150 次（预估 108）→ 当日累计 **345/340**，超 5 次，**当日封盘、不调锁**。
- **结构性发现（新登记 `ISS-053`）**：① **收口契约 × 用例形态错配** —— `v1-014` 三轮以 markdown 表格「回答」而非诊断 JSON 收口（`json_parse_ok=False` 3/3）；② **工具测点依赖告警** —— 产品 `query_sensor` 需 `sensor_ids` 或从告警推断，而 V1 用例无 `AlarmEvent`；③ **循环几乎不自行收口** —— `max_steps=2` 下 **48/51（94%）** 被强制收口（与 U2「异步诊断」判决互相印证）。
- **测试**：新增 `tests/test_agent_gate.py` **6 例**（打桩必装 ×2 / 消息口径 / 离线自检 / 审计不落 reports / raw 可聚合）→ 全量 **251 passed**。
- **处置**：**不作切默认凭据**（`deterministic` 不变）。下一版 D = 修 harness（告警前置 + 收口放行并单列 `answer_mode`）+ `max_steps=4`（预算另排日 ≈230 次）→ 重跑，才可裁决。
- **文档**：README §4.5 增补 D 首版结论与「不作凭据」声明；`reports/README.md` 回归 251 例；`EXP-P7-GATE-D` 全量回填（含 §3.4 偏离声明）。

---

### 2026-10-20（收口后维护期 · **所有者指示「先 C 拿到一版可信分数，同时立项 D」+ U2 判决**）— P7：判据闸门路径 C 实测 + 路径 D 立项 + U2 判决「异步诊断」

> 触发：所有者 2026-10-20 指示。实验登记：`experiments/v1/EXP-P7-GATE3.md`（预登记先行）；立项：`docs/p7-design-gate-product-agent-2026-10-20.md`；判决：`docs/p7-decision-async-diagnosis-2026-10-20.md`。**纪律：GATE/GATE2 分数自此不再对外引用**（被测工具面含写操作，测非所测）。

- **评测 · 路径 C：被测工具面对齐产品（`schemas/tools_v4_agent.json`）**：由冻结的 `tools_v4.json` **派生**出新文件（只读 4 工具，去掉写操作 `generate_report`），冻结件零改动。这是三版实测中**第一个「被测对象 = 产品工具面」**的版本。
- **评测 · 用例二次修订（`evals/v1_cases.jsonl`，仅 `v1-019`）**：写操作不在工具面后，「禁调 `generate_report`」变成空转判据 → 整条替换为**真实多轮上下文考点**：`query_graph(start_node="PUMP-A-01", depth=2)`，设备编号只能来自第 1 轮上下文（输入文本不含设备号），`depth=2` 来自本轮。`judge_tools` 的「禁调」语义**保留**（自检锁定）但用例集不再使用；`run_v1.py` 工具数提示改为动态（原硬编码「5 个工具」）。归档与锁：相对 `-pre-2026-10-20` 仅 `v1-019` 变动，允许字段集 `input/context/expected_tool_calls/notes/forbidden_tool_calls`，`type/difficulty/expect_reject` 不许动。
- **实测 · `EXP-P7-GATE3`（3 轮 × 25 = 75 样本，云端 51 次）**：参数校验 100% / **多轮 100%（9/9）** / 拒止 100% / 澄清 100% 四档 Pass；**单工具 83.3%、多工具 58.3% 中间区间** → **整体中间区间，无一档 No-Go**，首成 **67/75 = 89.33%**。失败 8/75 **全部为「参数值错」**（`v1-001` window、`v1-004` direction、`v1-007` aggregation=raw、`v1-008` fault_keywords、`v1-010` time_range），零工具名错、零退化、零越界 → 缺口性质从「判据口径问题」变为「模型参数默认值推断弱点」。
- **处置 · 仍未全绿 → 不切默认**（`deterministic` 不变）。**P1 候选**：在产品 Agent 提示词（`app/agent/prompt.py`，**不动冻结区 `prompts/`**）补参数默认值/取值指引，重跑 GATE3 验证收敛。
- **立项 · 路径 D（未开工）**：`docs/p7-design-gate-product-agent-2026-10-20.md` —— 判据被测对象改为**产品 Agent 本体**（产品提示词 + `agent_diagnose` 循环 + 工具打桩），覆盖 C 测不到的多轮循环/证据归集/收口质量/护栏；复用 `judge_tools` 判分与 `aggregate_runs` 聚合，护栏维度**只单列不进六档**；预算按 102 次预留，开工须过 §七 判据前置（含一句授权）。
- **判决 · U2「异步诊断 + 实时进度」**：`docs/p7-decision-async-diagnosis-2026-10-20.md` —— 云端实测端到端 156–226s 与「同步 P95<3s」不可兼得；Agent 形态性能口径改为「受理响应 P95 + 完成时间分位数」，审核流/降级/超时角色化不变；**不因此切默认**，U1 脱敏重审仍为上线前置。
- **测试**：路径 C 完整性锁 +5 例（禁调零声明 / 合成禁调语义 / 只读工具面一致性 / `v1-019` 上下文继承 / 修订范围锁）→ 全量 **245 passed**。
- **文档**：README §4.5 闸门结论改为「只引用路径 C 版」并声明三版不可横向比较；`EXP-P7-GATE2` §四 标注已判决执行、分数停用；设计文档 §五/§六 U2 回填；`reports/README.md` 索引与计数同步（`docs/` 40 → 42 份、回归 245 例、Schema 行补只读工具面）。

---

### 2026-10-19（收口后维护期 · **所有者指示的扩范围**）— P7：诊断 Agent 化（统一 LLM 客户端 + Agent 循环，云端临时承载）

> 触发：用户三项判决（2026-10-19）：① 测试文档上云无所谓、云端为临时形态，一切以后期切回本地为主；② 先建统一 LLM 客户端抽象，现在用云端测试开发；③ Agent 化落地交由执行方。设计文档：`docs/p7-design-agent-diagnosis-2026-10-19.md`（含切换 Runbook 与未决项 U1–U4）。**纪律声明**：M6.4 收口后为维护期，本次为所有者显式指示实施，非自发扩范围。
> 实测：`pytest tests/ -q` = **238 passed**（新增 30 例，全离线零网络，含 agent 模式全图集成 1 例）；app 全量 import OK；**默认配置 `local + deterministic` 与改动前逐字一致**（零默认行为变化）。

- **代码 · 新增 `app/llm/`（统一 LLM 客户端）**：`config.py`（后端/模式/角色模型/参数访问器，env 优先、函数级读取可测）+ `client.py`（`OpenAICompatClient` 本地 Ollama 与云端共用传输；`tools` + `tool_choice=auto` 载荷逐字沿用 `llm_adapter --transport tools` 实测形态，H5/ISS-027/R-V1-9 禁用 `required`；异常三态 Timeout/Connection/Runtime 与 diagnose 既有契约一致）。**调用点收敛**：`nodes/diagnose.py::_call_ollama`（原硬编码本地）与 `router/cloud.py::call_cloud`（原硬编码云端）均改为经本客户端，签名/缓存/审计语义不变。
- **代码 · 新增 `app/agent/`（Agent 工具面）**：`tool_registry.py`——从 `schemas/tools_v4.json` 程序化加载**只读子集 4 工具**（`generate_report` 按 ADR-007 不进工具面；幻觉调用由写操作护栏拦截并回灌拒绝原因）；schema 形参 → 产品函数适配（sensor_ids/time_range → (device_id, metric, start_ts, end_ts)；search_knowledge → RetrievalService D7 最优口径）；白名单走 `sanitizer.validate_tool_call`（schema 名→产品名映射），拒绝落审计。`prompt.py`——Agent 系统提示词（拒止规则 6a/6b/c 与场景背景**逐字沿用 prompt v4**，`prompts/` 冻结区零触碰；输出契约 = diagnose 诊断 JSON）。
- **代码 · 新增 `app/graph/nodes/agent_diagnose.py`（Agent 循环节点）**：每轮 LLM 自主选工具 → 白名单校验 → 执行 → `role=tool` 回灌 → 收口诊断 JSON；`max_steps`（默认 4）封顶后无工具强制收口；证据归集 `_Collector`（EvidenceItem/sensor_report/WorkOrder/GraphPath，形状与 gather 节点对齐 → finalize 引用校验与置信度公式原样生效）；LLM 失败 → `retry_count++` 走 ISS-048 第 0 优先级自循环重试；cloud 后端每轮过 `BudgetGuard`（熔断降级、仅成功计费；日均容量 ≈340/调用数）。
- **代码 · `app/graph/build.py` 模式开关**：`AUSCULT_DIAGNOSIS_MODE=agent|deterministic`；agent 模式 `parse_alarm → diagnose` 直连（gather 链不接入边、节点仍注册供打桩），**条件路由/degrade/escalate/human_review/finalize 两模式共用**。`router/cloud.py`：后端即云端时 escalate 空转（`W_BACKEND_ALREADY_CLOUD`，不重复计费——「云端降兜底」的逆场景适配）。`router/budget.py`：新增 `AUSCULT_CLOUD_BUDGET_LIMIT` env 覆盖（Agent 多次调用需重定上限）。`state.py`：新增 `agent_steps`（追加语义，dict 载荷 msgpack 友好）。
- **测试 · 新增 30 例（`tests/test_agent_diagnosis.py`，全离线）**：客户端载荷/双形态 tool_calls/三态异常/双后端工厂/配置校验；工具面只读子集/白名单/写操作护栏/时间解析与未来起点钳制/测点短名映射（ISS-049）；Agent 主路径/状态归集/步数封顶/失败重试/JSON 失败/预算熔断/无告警；图模式切换（节点实现 + 边形状回归）；escalate 空转与 call_cloud 出口委派；**agent 模式全图集成**（parse_alarm → agent_diagnose → finalize → report_id，引用校验不拦）。
- **文档**：`docs/p7-design-agent-diagnosis-2026-10-19.md`（设计 + 三项判决 + Runbook + U1–U4）；`docs/prj-ledger-known-issues.md` 新登记 **ISS-049**（schema 测点短名 vib_x/y/z ↔ TDengine 仅 vib_rms 的口径差，归一并显式告知，不静默丢精度语义）；README §六目录导航补 `app/llm/`、`app/agent/`，§4.5 补 Agent 化 env 说明。
- **未做（判据前置声明）**：多实例并发不验证（U4，单实例部署）；P95 基线不重定（U2，云端实测后）；主路上云脱敏范围重审不上线闸（U1，生产前必须）；ADR-001 §五「单模型全角色」备选不重评（U3，32B 就位后走 ADR 流程）；冻结区（prompts/schemas/evals/configs/docker/protos）零触碰。
- **代码 · 可观测化闭环（同日收尾）**：`runner.py` 新增 `_absorb_agent_steps`（diagnose 增量归集到线程记录）+ `thread_status` 双路径返回 `agent_steps`；`routes/health.py` 新增 `llm` 探针（backend/mode/模型快照，不含密钥，配置非法降级）；前端 `DiagnosisConsole` 右栏/窄屏内联「Agent 工具调用」列表 → 点击经 `InspectorDrawer` 工具页签展示单步出入参（**只传参数键名不传值**），关闭 D10「工具出入参」遗留；`types/thread.ts` 新增 `AgentStep`（旧缓存 payload 缺省容错）。
- **配置 · `deploy/.env.example`**：补 P7 Agent 化 env 段（默认注释 = 确定性+本地；含云端承载与回本地两种形态说明）。
- **测试 · 新增 2 例**（health llm 探针形状/降级、`_absorb_agent_steps` 归集与脏数据过滤）→ 合计 **32 例**；前端 vitest **53 例**全绿。
- **文档 · 索引与架构同步**：`reports/README.md`（docs 39→40、回归 185→240、修订记录）；`docs/prj-design-architecture.md` §二 增补 P7 口径（统一客户端 + agent 双实现 + 切换路径，默认关闭不变）；设计文档 §3.2 补可观测化闭环说明。

---

### 2026-10-20（收口后维护期 · **所有者指示的扩范围**）— P7 Agent 化：判据闸门三轮聚合实测（v1-019 架构冲突待判决）

> 触发：用户指示「跑」（判据闸门）。实验登记：`experiments/v1/EXP-P7-GATE.md`（预登记先行、3 轮同日、档线未放宽）。

- **实测 · 判据闸门结果（`EXP-P7-GATE`，云端 Qwen3.8-27B + prompt v4 + tools_v4，3 轮聚合 75 样本）**：单工具 **88.9%** Pass / 参数校验 **100%** Pass / 多工具 **75%** Pass（≥70% 线）/ **拒止 100% Pass**（v4 拒止强化实证生效——v1 历史该档 67% No-Go 的卡点已除；迁移集 5/5 + 主集 3/3）/ 澄清 **100%** Pass / **多轮 77.8% 中间区间**（7/9）→ **整体未过闸，按纪律不切默认**（默认维持 deterministic，无实际阻塞）。首次成功率 90.67%（68/75）；云端消耗 51 次（当日累计 71/340）。
- **归因 · v1-019 架构性冲突（待用户判决）**：多轮缺口 100% 由 `v1-019` 驱动（R1/R3 失败）——该用例期望「图内产生 `generate_report` 调用意图」，而 ADR-007 将写操作移出图内、P7 产品 Agent 提示词明文「报告生成不在你的工具范围内」——**产品语境下不调用才是正确行为**；v1-018/v1-020（真实多轮上下文补全）6/6 全过。数学测算：v1-019 通过率 ~1/3 时补跑无法使聚合 ≥85% → 唯一现实路径 = 用例期望重释义（需用户授权登记，先例：2026-09-28 判据分档重校）或接受中间区间。
- **归因 · 其余 4 失败（登记不修，P1 候选）**：`v1-008` 多工具组合不全（R2/R3，缺 `get_maintenance_history`）；`v1-001`/`v1-004`/`v1-009` 参数值错（window/direction/depth 枚举选择）——多工具档 75% 仍过 70% 线。
- **文档**：`experiments/v1/EXP-P7-GATE.md`（预登记 + 聚合 + 归因 + 处置）；设计文档 §五判据闸门结果回填；`experiments/v1/raw/EXP-P7-GATE-R{1,2,3}.jsonl`（只增不改）。
- **补记 · v1-019 判决支持（同日，零新增云端调用）**：`EXP-P7-GATE.md` §六 依既有 raw 做两版重释义 what-if —— **A（仅禁 `generate_report`）** 可使多轮档 9/9 闭闸；**B（不调用 + 自然语言说明）** 不可行（三轮 `content_clean` 全为 0 字符，工具通道命中即收口，harness 无法证实说明）→ §五「重释义后重跑即可闭闸」的前提仅在 A 版成立；并记落地成本（改冻结区 + 判分器「禁调工具」语义 + 完整性锁，重跑 ≈51 次云端）。**聚合结果/档线/用例/提示词/门规则零改动**；判决权仍在所有者（A 或维持中间区间）。

---

### 2026-10-20（收口后维护期 · **所有者指示的扩范围**）— P7 Agent 化：云端实跑验证 + 接入链路两项 ISS 修复

> 触发：用户指示「现在先云端实跑，保证系统能正常工作」。实跑工具转正为 `scripts/smoke_agent_cloud.py`（`--selftest` 离线自检 + 完整链路含审核 resume）。设计文档：`docs/p7-design-agent-diagnosis-2026-10-19.md` §7.0（实跑记录）。

- **实测 · 云端 Agent 形态端到端跑通（3 轮）**：① 图级（30s 超时未角色化）——Agent 循环/工具调用/检索/图谱全工作，3 次超时→重试→**降级链路实战验证**；② 图级（PUMP-A + 90s 角色超时）——3 轮自主工具调用（含两轮四工具并行）→ 高质量诊断（发现告警值 7.1 与存储数据不符、疑似误报、轴承温度 71.2°C 略超）→ conf 0.786 / risk high → 挂起 → resume(approved) → **RPT-2387417f17e6b14c**（156s）；③ API 级（uvicorn + REST 全链）——登录→诊断→226s 后 waiting_review（**第 1 次云端调用 >90s 超时 → ISS-048 自循环重试分支首次实战** → 第 2 次成功）→ `thread_status.agent_steps` 5 条正确回显 → rev_dev 审核 → **RPT-a542b2078222b830 落 PG**（high/0.78/approved）。预算消耗 16/340。
- **代码 · LLM 超时角色化（`app/llm/config.py`）**：`llm_timeout(role)`——diagnose 30s（本地口径不变）/ **agent 90s**（云端 tools 通道实测单轮 5.5–37s，30s 会误杀并触发整套 ×3 重试）；env `AUSCULT_LLM_TIMEOUT_AGENT_SEC` 可调。顺带修客户端超时异常消息重复包装。
- **代码 · 新登记并修复 `ISS-050`（接入链路数据完整性，🟠 高）**：`self_decoder.py` 订阅 **qos=0 → qos=1**（QoS 0 报文 broker 对慢订阅者不排队——受控探针实证：QoS1 慢订阅者 3000 报文仅收 1055 且封顶；提 `max_queued_messages` 对 QoS0 无效）；`configs/mosquitto.conf` `max_queued_messages` 1000→**20000** + `max_queued_bytes` 256MB。实测修复前复灌 10804 报文仅落 1909 行（PUMP-A 异常段整体丢失）。**遗留**：解码器逐行 REST 写 ≈48 行/s 吞吐上限 → 批量 INSERT 列 P1 候选。
- **代码 · 新登记并修复 `ISS-051`**：`routes/health.py` 预算探针连 Redis db 0 未带密码 → `cloud_budget.used` 恒 null；`config.py` 新增 `REDIS_PASSWORD`，探针带鉴权，实测 used 正常回显。
- **脚本 · 新增 `scripts/smoke_agent_cloud.py`（转正实跑工具）**：完整链路（诊断→挂起→审核 resume→report_id 验证）+ `--selftest`（mock 客户端+打桩工具，零网络）；docstring 含前置（栈 healthy、ISS-050 复灌注意、cloud.json）与预算说明。
- **测试 · 隔离修复 +2 例**：`test_agent_loop_tool_call_then_final` 原**隐含依赖「Milvus 不在线」**（基础设施起来后 risk 断言翻转——基础设施从缺陷变为正常态时测试反而失败），已打桩 `execute_tool` 恢复离线确定性；新增 health 探针/runner 轨迹归集 2 例 → `tests/test_agent_diagnosis.py` **32 例**，全量 **240 passed**。
- **文档**：设计文档 §7.0 实跑记录 + §六 U2 实测回填（**云端 Agent 形态端到端 156–226s，与 P95<3s 不可兼得**——需按「异步诊断+实时进度」产品口径重定或本地 32B 后再评）；known-issues ISS-050/051；README §五 复灌步骤补 ISS-050 注意。

---

### 2026-10-16（收口后维护期 · **所有者指示的指示性扩范围**）— P7：Redis 缓存层 + 告警自动触发（README §2.3/§2.5 两处漂移修正 + 数据流补环）

> 触发：代码考古确认 Redis 实为"协调原语"（限流/预算/审核锁/告警去重 4 处）而**零缓存**；README §2.5 声称的"工作流状态 Redis 运行态 / 会话上下文 TTL 24h"代码不存在；§2.3 数据流"MQTT 告警 → 去重 → LangGraph 触发"缺最后一环（诊断只能人工 POST）。设计文档：`docs/p7-design-redis-cache-layer-2026-10-16.md`（判据前置 C1–C5）。**纪律声明**：M6.4 收口后为维护期，本次为所有者显式指示实施，非自发扩范围。
> 实测：`pytest tests/ -q` = **208 passed**（新增 25 例）；`embedding_cache` / `retrieve_knowledge` 两个 `--selftest` exit 0；app 全量 import OK。

- **代码 · 新增 `app/cache/`（缓存基础设施）**：`client.py`（RedisCache 单例 + `cache_*` 分层便捷函数，全方法 fail-open：读=miss/写=跳过/set_nx=放行，错误落审计）+ `keys.py`（`auscult:cache:v1:{layer}:{hash}` 规范；**失效=换 key**——模型 digest/知识版本/messages 进 hash，无原地失效逻辑）。**db 1 与 db 0 协调原语隔离**；256KB 体积闸门（防挤爆 maxmemory 1gb 牵连 db 0 预算/锁）。
- **代码 · 六层缓存接入**：① `emb`——`scripts/embedding_cache.py` CachedEmbedder 代理（外挂式，不改 run_v2 EmbeddingClient 契约；模型 token=路径+size+mtime）；② `retr`——`RetrievalService.retrieve` 结果缓存（**仅缓存非降级结果**；knowledge_versions.max(id) 版本令牌，进程内 30s 缓存，PG 不可达退化 `"unknown"`；节点侧 `cache_key=device_id|metric` **剔除告警数值**保命中率）；③ `state`/④ `values`——`runner.py` 仅包**重启回退路径** read-through（进程内注册表永远权威，不读缓存）；变更点（追问追加/审核恢复）显式失效；⑤ `llm`——`_call_ollama` 缓存 content 原文（think 剥离/解析/置信度照常，**不改变下游语义**；命中落审计 `llm_cache_hit`）；⑥ `trig`——触发 SETNX 护栏。
- **代码 · 新增 `app/api/auto_trigger.py`（告警自动触发）**：补全 §2.3 数据流最后一环。daemon 线程 5s 轮询 `alerts WHERE status='open' AND diagnosed_thread_id IS NULL` → severity 过滤 → Redis SETNX 护栏 → **PG 条件 UPDATE 两阶段占位**（`trigger-pending` → 真实 thread_id，防扫描-启动间隙双触发）→ `start_diagnosis(submitter="system:auto-trigger")`。选型：**不引 Redis Stream/MQTT 订阅**（告警引擎是批处理外部进程，PG 即天然事件日志；重启自重建，不回放不丢失）。**默认关闭**（`AUSCULT_AUTO_TRIGGER=0`），关闭时仍打点 `disabled` 供 /metrics 观测开关状态。
- **代码 · `db/migrations/0007_alerts_auto_trigger.sql`**：`alerts.diagnosed_thread_id`（NULL=未触发，权威标记）+ 部分索引（低扫描面，对齐 outbox pending 写法）。
- **代码 · 配置 `app/api/config.py`**：`AUSCULT_CACHE_*`（独立 env，**不复用** db 0 的 `AUSCULT_REDIS_URL`；TTL 分层默认 24h/6h/30d/24h）+ `AUSCULT_AUTO_TRIGGER*`。**指标**：`auscult_cache_ops_total{op,result}` / `auscult_auto_trigger_total{result}`。
- **测试 · 新增 25 例（全离线，Redis/PG 不可达即验降级路径）**：`tests/test_cache_layer.py` 14 例（key 五维隔离/fail-open 三态/jsonable 归一化/代理直通语义）；`tests/test_auto_trigger.py` 11 例（severity 过滤/两阶段标记/护栏拦截/单条失败不阻断/PG 挂了跳过轮次）。
- **文档 · 漂移修正**：README §2.5 两行（会话上下文/工作流状态）随本次落地转为真实口径；目录导航补 `app/cache/` 与 migration 0007；`configs/redis.conf` 头部注释仍为 V5 候选 A 遗产口径（**未改配置**，改动须走 ADR——见设计文档 §六 Won't）。
- **未做（判据前置声明）**：Redis checkpointer 不复活（B7 未解）；缓存不做权威化；`configs/redis.conf` 不动；冻结区零触碰。

---

## [未发布] — Phase 6（收敛与交付）✅ 已完成并收口（`M6.4`，2026-10-10）

> **总述**：**Phase 0–6 已全部完成** —— `M0.6` 门禁 2026-10-08 放行、`M5.4` 2026-10-10 达成（停止条件三条满足）、**`M6.1`–`M6.4` 于 2026-10-10 全达成并正式收口**（停止条件 S1/S2/S3 三条同时满足、交付包封版）。收口凭据 = `docs/p6-gate-closure-2026-10-10.md`。
> **P1–P5 的逐条变更原不在本文件展开**（避免与台账/报告重复）→ **本次已按阶段补登摘要条目**；逐项实测仍以阶段移交清单与实测报告为准：
> `docs/p0-handover-p1.md`（P0→P1）｜`docs/p2-handover-p3.md`（P2→P3）｜`docs/p3-handover-p4.md`（P3→P4）｜`docs/p4-handover-p5.md`（P4→P5）｜`docs/p5-handover-p6.md`（P5→P6）｜报告索引 `reports/README.md`。
> **残余风险（收口 ≠ 风险消失）**：`P95` 端到端含生成 9.25 s 未达 3 s、F-2 数据库短连接排队、F-1 health 探测阻塞事件循环、RPO 未定时化、`ISS-038`–`ISS-041` 登记不修 → 见 `docs/p6-gate-closure-2026-10-10.md` §四 与 `docs/prj-ledger-risk-register.md`。

### 2026-10-16（收口后维护期）— 全栈实跑验证 + 用户操作手册建立（**零功能改动**）

> 触发：按用户要求「把项目跑起来 + 根据需求文档写用户操作手册并给真实截图」。全程实跑验证：起栈 → 初始化（修复两处幂等缺陷）→ 灌数复验 → 起后端/前端 → 登录 → S1 诊断 → 审核 → 审计。`pytest` 185 不受影响（脚本 + 文档改动，另有 2 个新增测试文件随 P7 未提交代码一并存在）。

- **代码 · 修复 `init.ps1` 幂等缺陷 A（`docker cp` 嵌套，2026-10-16 复跑 init 暴露）**：`docker cp SRC_DIR CONTAINER:/tmp/x` 在目标已存在时把目录拷成 `/tmp/x/migrations/` 子目录而非平铺 —— 幂等重跑时新迁移（0007）进不了顶层，psql 报 `No such file or directory`，且错误被 `2>$null` 静默吞掉（易误判为「文件未生成」）。修复：cp 前 `docker exec ... rm -rf` 目标目录。修复后 0001–0007 全部 `[OK]`。
- **代码 · 修复 `load_meta.py` 幂等缺陷 B（`COPY` 不支持 `ON CONFLICT`）**：`import_all` 原用 `COPY ... FROM STDIN` 导入三表，而 COPY 协议无 `ON CONFLICT` —— 在「documents 已导入」状态重跑 `init.ps1`（Step 4，2026-10-14 新增）必撞 `documents_pkey` 唯一约束使整个初始化崩溃（实测 `UniqueViolation`）。这与 P1 报告口径（`reports/p1-d7-d8-b5-meta.md`：`ON CONFLICT DO UPDATE` 幂等）存在**文档—实现漂移**，且 10-14 新增 Step 4 时 PG 表为空故未暴露。修复：三表改逐行 `INSERT ... ON CONFLICT (pk) DO NOTHING`（doc_id / chunk_id / order_id；数据源同一 chunks 文件 + uuid5 确定性，DO NOTHING 等价 DO UPDATE；`psycopg.extras` 在本 venv 未安装，故用纯 `cur.execute` 循环，19/36/48 行性能无感）。修复后幂等重跑 `documents=19 | doc_chunks=36 | work_orders=48 | outbox=0`、对账零差异。
- **运维 · 全栈实跑验证通过**：9 容器 healthy（nginx 除外——其健康检查代理到宿主应用服务，基建态下 502 属预期）；后端 `/api/health` 200（PG/Milvus/Neo4j/TDengine/Redis 全 up）；nginx `:9763/login` 200；S1 实跑闭环：告警（PUMP-A/vib_rms/critical，`insert_test_alarm.py` 预置）→ 发起诊断 → 六节点轨迹全过（传感器分析读到 10800 行时序、PUMP-A 峰值 4.855 mm/s）→ 云端 20.2s 超时显式降级 `cloud_unavailable` → 报告 `RPT-5cbb850`（conf 0.63 / medium）→ 审核员通过 → 审计留痕（`cloud_audit.jsonl` / `traces/`）。
- **文档 · 新增 `docs/prj-guide-user-manual.md`（用户操作手册）**：按需求主流程文档（`prj-design-requirements-main-flow.md`）撰写；含快速开始（up/init/灌数/起应用/入口）、四角色 RBAC 矩阵、六页功能操作（告警看板/诊断控制台/报告工作台/知识库/图谱/审计）、S1 主流程实跑走查表、FAQ 7 条、已知边界 7 条（如实：P95 9.25s、图谱规模、审计页 D20 数据接入未完成等）；**10 张截图全部来自 2026-10-16 实跑**（`docs/images/manual/`）。顺带实测确认：RBAC 守卫生效（审核员访问 /audit 被拒）、图谱实体精确匹配（「联轴器不对中」→ 9 节点/8 关系/243.6ms）。
- **文档 · 命名规范扩展 `guide` 类型**（§三.3 类型表新增一行，首例即用户手册）；根 `README.md` §六目录导航补手册/P7 设计/images 目录、文末索引加手册指针；`reports/README.md` §六 docs 计数 37 → 39 并登记。

### 2026-10-15（收口后维护期）— `ISS-044` 修复不彻底性补修：`up.ps1` / `down.ps1` 剩余 docker 调用点（**零功能改动**）

> 触发：2026-10-15 清理 `ISS-046` 旧接入栈容器后重跑 `up.ps1`，实测 `up -d` 阶段 `Container xxx Starting` 等 stderr 进度行仍被 PS 5.1 包装为 **RemoteException 红色噪音**打印（功能不受影响、exit=0）。追查确认 **ISS-044 的「同类自查」漏掉了两个脚本的其余调用点**，且「放宽到 `Continue`」本身不彻底。`pytest` 185 不受影响（纯脚本改动）。

- **代码 · `deploy/up.ps1`**：新增 `Invoke-DockerQuiet` 辅助函数（native 调用期间 `SilentlyContinue`、`finally` 恢复 EAP、返回退出码），`pull` 与 `up -d` 两处调用统一走它；**`pull` 补显式退出码判定**（原实现失败会被静默吞掉、带着坏镜像进 `up -d`）。
- **代码 · `deploy/down.ps1`（ISS-044 同根因的第二个脚本、第三个暴露点）**：裸调 `docker compose down` / `down -v` 在顶部 `EAP="Stop"` 下，**会在退出码判定之前直接终止脚本**（用户收不到 [OK]/[FAIL] 反馈）—— 比 up.ps1 的噪音更严重（功能级）；改用同一辅助函数 + 显式退出码判定。
- **代码 · `deploy/down.ps1` 补 UTF-8 BOM**：新增中文注释后按 `ISS-021` 纪律补 BOM（实测无 BOM 时 PS 5.1 解析错误 1 处）；四个 `.ps1` 现全部 BOM/编码合规、解析错误 0。
- **文档 · `docs/prj-ledger-known-issues.md`**：`ISS-044` 行补记「2026-10-15 修复不彻底性」段（三个暴露点、`Continue` vs `SilentlyContinue` 的区别、`pull` 退出码缺失、BOM 纪律），**不新开编号**（同一缺陷的修复遗留面，非新缺陷）。
- **实测**：`up.ps1` 幂等重跑 **exit=0、零 ErrorRecord 噪音**；`init.ps1` / `smoke.ps1` 本就 `Continue` + 显式重定向，不受影响、未改。

### 2026-10-15（收口后维护期）— `ISS-046` 规避执行：旧接入栈容器与卷清理（**零数据损失**）

> 触发：用户确认旧容器可删。执行前先逐一核实挂载卷无业务数据，删除后零残留；顺带发现并恢复交付栈（与本次删除无因果关系，时间戳可证）。

- **数据 · 删前核实（先证明安全再动手）**：`auscult-ingest_tdengine-data` 30MB **仅管理节点系统表 `mnode/sdb.data`、无任何 vnode 时序文件**（旧实例从未落业务数据）；`auscult-ingest_mosquitto-data` 8KB 仅 47 字节 `mosquitto.db`（空库）。
- **配置 · 执行清理**：`docker rm -v` 删两容器（含匿名卷）+ `docker volume rm` 删三命名卷 → `auscult-ingest` **容器与卷零残留**；端口 1883/6030/6041 归交付栈独占。未触碰其他项目容器（`kee-*` / `pal-*` / `neo4j-cq`）与交付栈资源。
- **运维 · 顺带发现交付栈已停并恢复**：删除后验证时发现交付栈 9 容器全部 Exited，时间戳为「11 hours ago」（2026-10-14 22:30 前后，退出码 0/143/137 混合、`kee-*` 同期全停，属 `compose down` / Docker Desktop 重启的全局停止事件；**本次删除发生在 10-15 09:2x，与停止无因果关系**）。已用 `deploy\up.ps1` 恢复并逐项验证数据完好：TDengine 时序 **10800 行**、PG documents=19 / doc_chunks=36 / work_orders=48 / outbox=72 全消费 / reports=9 / users=4、Neo4j **105 节点 / 127 关系**；9 容器 Up、8 healthy（nginx unhealthy 属**预期**：其健康检查 `wget /` 代理到宿主 Next.js :3000 / FastAPI :8000，交付栈本就不含应用服务，返回 502 而非拒连恰证明 nginx 本身正常）。
- **文档 · `docs/prj-ledger-known-issues.md`**：`ISS-046` 主表与 §五 对应关系行补记「2026-10-15 已执行清理」及删前数据核实结论。

### 2026-10-14（收口后维护期）— 时序样本数据灌数闭环 + 两项健壮性修复（**零功能扩范围**）

> 触发：处理收口遗留的四项观察（TDengine 表已建无数据 / graph 证据无文本语义 / `E_LLM_UNREACHABLE` 偶发超时 / 旧容器名冲突）。`pytest` **185 passed**。

- **数据 · 时序样本数据灌数（遗留项闭环）**：`init.ps1` 只建 schema 不灌数据（`ISS-046` 同源背景）→ 按生产形态链路补灌：常驻 `scripts/self_decoder.py`（本地直跑，Mosquitto → TDengine REST 6041）+ `scripts/gen_sparkplug.py`（默认 3 设备 × 1h × 1Hz，PUMP-A 注入异常段，固定 seed）。**实测 10800 行落库**（3600×3，轮询口径差 213 点系写盘可见性延迟，终态一致）；PUMP-A `vib_rms` 峰值 **4.855 mm/s**（越 ISO 10816 C 区上界 4.5）、**2 个** 5min 超限窗口，B/C 正常态 ≈1.30。
- **代码 · 修复 `ISS-047`（device_id 白名单三口径漂移）**：`verify_query_sensor.py` 与 `run_v3_alert.py` 用严格标识符白名单（不允许连字符），而运行时 `app/tools/query_sensor.py` 与 `alarm_engine.py` 支持 `PUMP-A`、`gen_sparkplug.py` 默认产 `PUMP-A/B/C` → 灌数后验证脚本对合法设备直接 `ValueError` 崩溃、契约验证链断裂。两脚本改用与 `alarm_engine.py` 同款宽松 `SAFE_VALUE_RE`（列名仍走严格白名单，注入防护不放松）。修复后 3 设备 × 13 窗口 exit 0、`P95≈24.2ms`。
- **代码 · 修复 `ISS-048`（LLM 不可达无自动重试）**：`_route_condition` 无重试分支，diagnose 失败时 `confidence` 仍为初始 0.0 → 被「`confidence < 0.50`」先命中 degrade，`retry_count ≥ 3` 护栏对该路径**永不生效**（偶发 Ollama 超时零重试直接降级；E6 用例只 mock 终态、从未覆盖循环）。新增**第 0 优先级自循环重试分支**（仅 `diagnosis is None` 时重试，`E_JSON_PARSE` 不重试；云端失败不动 `retry_count` 故不受影响）；补 **E6b/E6c** 回归用例（偶发失败 2 次后成功出报告 / 连续失败 3 次降级）。
- **代码 · graph 证据语义固化**：`retrieve_evidence.py` 注释明确 graph 类证据 `text=""` 为**设计使然**（形态 = chunk_id + `graph_paths`），防止后续被误判为缺陷「修坏」。
- **配置 · `deploy/up.ps1` 头部注释修正**：用法注释仍写「start base stack (no tdengine)」与默认启用 profile 的实现矛盾（`ISS-044` 修复时引入）；并补 ISS-046 端口前提。
- **文档 · 台账三连登记**：`docs/prj-ledger-known-issues.md` 新增 **`ISS-046`**（旧接入栈容器 `auscult-ingest-*` 与交付包**端口相同** → 升级环境冲突，**可规避**：`docker rm -f auscult-ingest-*`）、**`ISS-047`**、**`ISS-048`**（后两者已修复）；`README.md` §五 补「时序样本数据」独立步骤（解码器 + 造数命令、复灌方式、实测口径）。
- **验证**：`pytest tests/ -q` = **185 passed**；七个脚本 `--selftest` 全 exit 0；三写对账零差异；`deploy` 四个 `.ps1` BOM/编码合规、`up.ps1` 解析错误 0。

### 2026-10-11（收口后维护期）— 交付包两处 P0 修复 + 图谱数据填充（**首次起栈实测暴露**）

> 触发：按分层测试方案执行「需基础设施层」实测（`up → init → smoke → 后端 → 安全/权限 → E2E → 压测 → 可靠性`）。**零新增文件**；`pytest` **183 passed**。

- **代码 · 修复 `ISS-044`（P0，交付阻塞）**：`deploy/up.ps1` 在 pull 阶段即终止 —— 脚本顶部 `$ErrorActionPreference = "Stop"` 与 `docker compose pull 2>&1 | Out-Null` 组合，把 docker 的 **stderr 进度行**包装为 ErrorRecord，在 `up -d` **之前**直接终止；**干净环境 100% 复现**，使 `M6.2`「一键启动」承诺不成立。修复：去掉 `2>&1`，并在 native 命令调用期间临时放宽 EAP、保留退出码判定。修复后实测 **exit=0**，8 容器 Running。
- **代码 · 修复 `ISS-045`（图谱数据始终为空的真实根因）**：① `scripts/extract_triples.py:312` 对受控词表外关系直接下标取值 → `KeyError: '关联'` 使导入整体崩溃；② `deploy/init.ps1` 未指定 `--results`，默认读 **v1 基线**（245 条含 75 条词表外关系「关联」，占 30.6%）而非 P1 收口的 **v2 终态**（184 条、0 条未映射）。修复：`rel_slug.get()` 兜底（跳过 + 计数 + stderr 告警）+ `init.ps1` 显式指向 v2。实测 `init.ps1` **exit=0**，Neo4j **节点 105 / 关系 127 / 关系类型 11 种**（独立 Cypher 核验）。
- **文档 · 收口凭据更新**：`docs/p6-gate-closure-2026-10-10.md` **Must #5 图谱检索由 ⚠️ 转 ✅**（声明为**真实修复**而非"收口转绿"，#3/#7 维持 ⚠️）；同步文首复核注、§三 #5 行（附完整证据链）、§四剩余风险（原「显式接受」作废、列残留口径）、§六路线图（P2 已完成）、修订记录。
- **文档 · 演示口径同步**：`docs/pitch.md` 证据行 / Q4 / **A1 整条重写** / 失败兜底表 —— 由「图谱为空」改为「已预置 105 节点 / 127 关系 / 11 类受控关系」，**保留如实边界**（来自 36 子块合成语料、规模有限，诊断仍以文档检索为主）；`demo/scenario.md` §二 步骤 3 同步。
- **配置 · 交付脚本编码**：`deploy/{init,smoke}.ps1` 由「非 ASCII 且**无 BOM**」（513 / 234 字节）改为 **UTF-8 BOM** 兜底（ISS-021 纪律：无 BOM 的中文在 PS 5.1 会被按 ANSI 解码，可能损坏解析）；修复 `up.ps1` 新增中文注释后同步补 BOM。四个 `.ps1` 现全部合规（解析错误 0）。
- **台账**：新增 **`ISS-044` / `ISS-045`**（收录范围 → ISS-001 – ISS-045）；页头「最近更新」改 2026-10-11，并**如实登记未处置项**：`smoke.ps1` 仅验可达性不验数据、`locustfile.py` 与接口契约漂移（压测 68 次 404）、LangGraph msgpack 未注册类型告警 ×4。
- **实测结果（本次）**：smoke **6/6 PASS**；安全+权限 **8/8 PASS**（含审计防篡改 / SoD / 限流 429 / 预算熔断）；RBAC 隔离（`eng_dev` 访问 review **403**）；接口鉴权无 token **401**；E2E **7 passed**；可靠性 **12/12 PASS**；`up` 8 容器 up / 7 基建 healthy。
- ⚠️ **压测未达标且口径存疑（未定性）**：u50/3min 实测 `P95` = **12 s**，P5 报告为 940 ms。干扰因素：容器冷启动、宿主可用内存仅 6.5 GB（P5 预算 20.73 GB）、压测期间并行跑可靠性、端点集含 LLM 重端点（`/api/diagnose` P95 21 s）。**须在资源充足、无并发干扰下复测后再定性**，不得据此判定性能退化。

### 2026-10-10（收口后）— 入口文档口径同步 + 命名纠错（**文档整理，零功能改动**）

> 触发：Phase 6 收口后对全仓入口文档做一致性核查，发现 4 处口径/登记滞后。**零代码改动、零功能改动**。

- **文档 · 阶段口径同步（`README.md`）**：头部与 §3.1 阶段表由「Phase 6 🚧 进行中」→ **✅ 全达成（`M6.4` 2026-10-10 收口）**；§五 一键启动由「⏳ 进行中」→ **已落地**（实测 8 容器 up / 7 基建 healthy / `deploy/smoke.ps1` **6/6 PASS**）；§4.4 注记由「D6–D7 将落地于 `deploy/init/`」→ 已落地为 `deploy/init.ps1`；§六 目录导航补 **`deploy/`** 与 **`demo/`**（交付包与演示资产此前未入导航）；§七 常用入口补四个一键脚本；§八 新增**纪律 8「收口后维护期：只修缺陷与文档口径、不新增功能范围」**；文末事实源索引改指向收口凭据。
- **文档 · 变更记录补登（本文件）**：补写 **Phase 1–5 交付**与 **Phase 6 D2–D10** 全部条目 —— 此前自 Phase 0 过闸（10-08）直接跳至「Phase 6 D1」，中间 11 个提交无任何记录，与「变更以验证项 / 里程碑为粒度」的约定不符。
- **文档 · 索引补登记（`reports/README.md`）**：§一 补登 **P1（11 份）/ P2（8 份）/ P3（2 份）/ P5（7 份）共 28 份报告**（此前仅登记 P0 的 25 份，而 `reports/` 实有 55 份）；§六 全局摘要按实况更正（脚本 **84 个 Python + 2 个 PowerShell〔36 含 `--selftest`〕**、回归 **183** 用例、`pytest==9.1.1` 已锁入 `requirements.txt` 与版本锁 §二.2.10）。
- **文档 · 命名纠错（2 项 `git mv`）**：`docs/P6-closure.md` → **`docs/p6-gate-closure-2026-10-10.md`**、`reports/P5-summary.md` → **`reports/p5-summary-phase5-2026-10-10.md`** —— 原名为大写 `P` 且缺阶段-类型分隔，违反 `docs/prj-spec-document-standard.md` §二；全仓引用改写 4 个文件，映射登记于命名规范新增 **§6.5**；两份文件**正文结论一字未改**，仅在各自「修订记录」追加一行。另在命名规范 §七 登记**残留 8**：`docs/pitch.md` 保留可读短名（演示对外材料，已知偏差不改）。
- **验证**：`pytest tests/ -q` = **183 passed**；`P6-closure` / `P5-summary` 旧名仅剩命名规范映射表与修订记录中的**旧名→新名**对照（有意保留）。

### 2026-10-10（Phase 6 D10）— 正式收口：`M6.4` 达成

- **文档**：新增收口凭据 `docs/p6-gate-closure-2026-10-10.md`（原名 `docs/P6-closure.md`，同日已按命名规范更正）—— M6.1–M6.3 出口复核、**停止条件终核**、Must 链 13 项终核、风险收敛与剩余风险显式接受、后续路线图（P0–P3 优先级）、交付包封版清单。
- **数据 · 终核口径**：S2 三项指标 `Recall@5` **1.0** / `P95` 检索 **159.4 ms** / 工具调用首次成功率 **1.0**，与 `docs/p5-handover-p6.md` §二 逐字一致；S3 = 版本锁（10 镜像 digest）+ 风险册定稿。
- **质量 · 两轮独立人工复核（诚实降档，未转绿）**：对收口稿做只读交叉验证，把 3 项 Must 由「✅ 闭环」**如实降为 ⚠️ 部分/缺口** —— ① **#3 传感器分析**：`query_sensor` 契约实测通过，但判据字段 `anomaly` / `p95` 在 `app/graph/nodes/analyze_sensor.py::_compute_stats` **未实现**；② **#5 图谱检索**：Neo4j 图谱数据**未预置**（演示边界，`docs/pitch.md` A1 如实披露）；③ **#7 证据引用强制**：契约层 `schemas/tools_v4.json` 的 `evidence_refs` required ≥1 成立，但**运行时无「无引用不出报告」硬校验**（`finalize.py` 仅产非阻塞 `W_` warnings）。另校正 Must #4 的 `0.91` 出处（实出 Phase 0 `reports/p0-report-v2-hybrid-retrieval.md`，非 `docs/p2-handover-p3.md`）。
- **结论**：**`M6.4` 达成，Phase 6 正式收口**；此后进入维护期，只修缺陷与文档、不扩范围。

### 2026-10-10（Phase 6 D8–D9）— 演示脚本 / 预置数据 / 排练与解说词（`M6.3`）

- **数据 · 新增**：`demo/scenario.md`（主场景 S1 离心泵驱动端轴承振动端到端 + 备用 S2 高风险审核耗时降级 / S3 低置信降级 / S4 云端不可用）、`demo/data/alarms.json`（四场景预置触发输入，词表与 `configs/alarm_rules.yml` 一致）—— **仅编排既有资产，不新增功能**。
- **文档 · 新增**：`docs/pitch.md`（90 s 电梯解说 + 主/备用解说词 + 高频与尖锐 Q&A A1–A5 诚实口径 + 失败兜底）、`demo/recording/rehearsal-log.md`（排练实测：基建 up → seed 用户 → 起后端 → 登录 → 触发 S1 → 线程推进至 `analyze_sensor`，`risk=high`）。
- **配置**：`docs/prj-spec-operations.md` §1.3 转定稿表述（Milvus 端口口径统一为 `19531`）。

### 2026-10-10（Phase 6 D6–D7）— 交付包工程化（`M6.2` 出口达成）+ `ISS-042` 修复

- **代码 · 新增**：`deploy/docker-compose.yml`（全服务 + healthcheck + 依赖顺序 + 资源限额 + Nginx；镜像一律 `@sha256`）、`deploy/.env.example`、`deploy/images.digest.md`、`deploy/up.ps1`（一键启动 + 等待健康）、`deploy/init.ps1`（迁表 / 建库 / 建图谱 / 导入语料与演示数据，**幂等**）、`deploy/smoke.ps1`（健康检查 + Playwright E2E 子集）、`deploy/down.ps1`（可选 `-v` 清卷）。**既定决策弃用 Makefile。**
- **代码 · 修复 `ISS-042`（Milvus 端点三口径）**：`scripts/retrieval_base.py` / `scripts/reconcile.py` / `scripts/outbox_worker.py` 三处硬编码 `http://127.0.0.1:39530` 改为读 `MILVUS_PORT` 环境变量（默认 **`19531`**，与 `app/api/config.py` 对齐）；P5 复现口径可设 `MILVUS_PORT=39530` 回退。
- **实测（干净环境判据）**：8 容器 up、7 个基建 healthy、`deploy/smoke.ps1` **6/6 PASS** → **`M6.2` 达成**。

### 2026-10-10（Phase 6 D2–D5）— 架构 / 部署运维 / API / 数据字典 / ADR 九条（`M6.1`）

- **文档 · 新增**：`docs/prj-design-architecture.md`（分层 / 七模块 / 三条数据流 / 存储归属）、`docs/prj-spec-deployment.md`、`docs/prj-spec-operations.md`、`docs/prj-spec-api.md`、`docs/prj-spec-data-dictionary.md`、**`docs/prj-decision-adr-001..009.md`**（模型分工 / 混合部署 / Milvus BM25 / 置信度 / PG 权威源 / 跨存储一致性 / 图外写 / checkpoint 存储 / Nginx 后置）。
- **文档 · 命名规范化（3 项 `git mv`）**：`docs/handover-p4.md` → `docs/p3-handover-p4.md`、`docs/handover-p5.md` → `docs/p4-handover-p5.md`、`docs/handover-p6.md` → `docs/p5-handover-p6.md`；全仓引用改写 10 个文件 29 处。
- **如实标注（不因收口而声称已实现）**：`docs/prj-spec-api.md` §四 对 `E_TIMEOUT`（`ISS-038`）、§五 对 `qa_log`（`ISS-041`），`docs/prj-spec-data-dictionary.md` §三 对 `sess:*`（`ISS-040`）、§四 对告警状态机（`ISS-039`），均标注【未闭环 / 待确认】。
- **结论**：**`M6.1` 达成**（六类文档齐备且与实现一致）。

### 2026-10-09 ~ 10-10（Phase 1–5 交付，**补登**）— 数据层 / 检索层 / 工作流 / 前端 / 评测硬化

> 说明：P1–P5 的逐条实测见各阶段报告（`reports/README.md` §一）；此处仅登记**阶段级交付与里程碑**，避免与报告重复。此前本文件自 Phase 0 过闸（10-08）直接跳至 Phase 6 D1，缺这五段记录。

- **Phase 1（数据接入与知识库构建）**：MinerU 解析 Spike 通过 → B1 全量解析 → B2 Parent-Child 分块 → B3 Milvus 建库 → B4 三元组抽取（**91 节点 / 94 关系**，v2 准确率 **93%**）→ B5 元数据与工单导入 PG → B6 Outbox 一致性（失败注入对账零差异、补偿队列可自愈）→ **八项量化门禁全达标、`M1.4` 放行**。报告：`reports/p1-*.md`（11 份）。
- **Phase 2（混合检索）**：W1 查询改写 / W2 三路召回 / W3 RRF 融合 / W4 重排 + W5 证据组装 / W6 `retrieve_knowledge` 工具 / W7 工具链 R-2/R-3 评测（**云端 16/16 Pass**）→ **M2.1–M2.4 全达成**；`Recall@5` **1.0** / `MRR` **0.7569** / `NDCG@5` **1.0** / `P95` **86.1 ms**。报告：`reports/p2-*.md`（8 份）。
- **Phase 3（Agent 工作流实现）**：LangGraph 五节点 + 五档条件路由 + PG checkpointer + `interrupt` 人工审核；D20 可靠性（杀进程恢复 / 重复 resume / Redis 驱逐防护）→ **M3.1–M3.5 全达成**。报告：`reports/p3-reliability.md`、`reports/p3-summary.md`。
- **Phase 4（前端与集成）**：七类页面 + Socket.IO 实时推送 + Nginx 单入口 `:9763`；**Playwright E2E 9/9** → **M4.1–M4.4 全达成**。⚠️ **如实登记文档资产缺口：本阶段无独立 `reports/p4-*.md` 报告**（仅有移交清单 `docs/p4-handover-p5.md`），实况以 `README.md` §3.1 与移交清单为准。
- **Phase 5（评测与硬化）**：十二项指标 **8 达标 / 1 未达标（`P95` 端到端含生成 9,248.8 ms vs 3 s）/ 1 代理口径**；`κ`=**0.8344**、幻觉率 **0.0%**、工具首次成功率 **1.0**（12/12）、宿主资源峰值 **20.73 GB ≤ 24 GB**、安全回归 **8/8**、备份演练 PG RTO ≈**3.1 s**；**停止条件三条满足 → `M5.1`–`M5.4` 全达成**。报告：`reports/p5-*.md`（7 份，含 `p5-summary-phase5-2026-10-10.md`）。

### 2026-10-10（Phase 6 D1）— README 收口与过期口径清理

- **文档**：`README.md` 全量重写并**对齐 V5.0 定稿口径** —— 新增一句话定位 / 分层架构图 / 七模块 / 三条数据流 / 五档条件路由 / 存储归属表 / 阶段状态（P0–P6）/ Phase 5 全量指标终值表 / 一键启动（D6–D7 落地段）；清理过期口径：阶段状态由「Phase 1 计划就绪」改为「**Phase 0–5 已完成、Phase 6 进行中**」、脚本计数 `22〔16 自检〕` → **84 Python + 2 PowerShell（36 含 `--selftest`）**、目录导航按实况重写（新增 `app/`、`client/`、`db/`、`monitoring/`、`blobs/chunks/parsed/`）。验证：`pytest` **183 passed**。
- **文档 · 依赖漂移补正**：`requirements.txt` + `docs/prj-ledger-version-lock.md` 按**实装为真**回填 `langchain-core` **1.6.4 → 1.6.9**，并显式钉住 `langchain==1.4.4` / `langchain-openai==1.7.0`（目的 = 阻止解析器再次静默升/降 core）。验证：`uv pip install --dry-run -r requirements.txt` = **Would make no changes**。**`env/env-baseline-v2.md` 不升版**（5 条升版触发条件不含 Python 包版本）。
- **说明**：本小节原为「`[未发布] — Phase 1 待启动`」工作注记（10-07 / 10-08 时点），其结论已由下方 2026-10-08 条目与 `docs/p5-handover-p6.md` 承载，故按用户裁定**降级为上方总述**（历史条目正文一字不改）。

---

## 2026-10-08（午后）— 文档治理：全量一致性同步 + 命名规范落地（48 份改名 / 约 1737 处引用改写）

> 触发：用户要求「检查项目完整状态、梳理并同步更新所有文档、统一命名规则」。零云端调用、零功能代码改动（仅注释与文档路径字符串）。

- **文档 · 命名规范（新建，唯一入口）**：`docs/prj-spec-document-standard.md` —— 命名规则 `<阶段 p0|p1|prj>-<类型 plan|design|spec|decision|report|analysis|audit|review|gate|summary|handover|checklist|template|ledger>[-<主题>][-<YYYY-MM-DD>]`、全小写 ASCII kebab（禁空格与全角括号）；🟢活动 / 🟡时点快照 / 🔵冻结 三态标记；目录职责表；**不可改写区**（`prompts/`、`schemas/`、`evals/`、`configs/`、`docker/`、`protos/`、`experiments/**/raw/`、`env/cloud.json`）；**48 项旧名→新名映射表**；7 条残留清单。
- **文档 · 重命名与搬运（48 项，全部 `git mv`）**：`docs/` 15 份加阶段/类型前缀（`version-lock` → `prj-ledger-version-lock` 等）；`plan/` 7 份去空格与全角括号（`Phase 0 详细开发计划（D1-D10 可执行版）.md` → `p0-plan-detailed-d1-d10.md`）；`reports/` 25 份规范化（`P0-summary` → `p0-gate-review`、`v1-report` → `p0-report-v1-tool-call`、`h17-single-tool-tier-audit` → `p0-audit-v1-single-tool-tier-2026-10-07` 等）。**跨目录搬运 2 项**：`plan/Phase 0 任务总结.md` → `reports/p0-summary-phase0-2026-09-30.md`（总结不属于 `plan/`）、`experiments/plans/P1-V4B-CLEANRM.md` → `plan/p1-plan-v4b-cleanrm.md`（计划不属于数据目录）。**归档 3 项**：求职素材 `G2-实测数据填表` / `待填信息问卷-49项-回填` / `草稿问卷-审阅与回填` → `archive/personal/`（`reports/` 混入非项目产物、且全仓零引用）。
- **文档 · 引用改写**：110 个文件、**1714 处**旧路径 + **23 处**省略号缩写（`plan/H15-...md` 这类从未指向真实路径的写法，涉 11 个文件）全部展开为新名；单遍正则（长名优先）避免二次替换污染；`scripts/*.py`、`tests/*.py`、`requirements.txt`、`.gitignore`、`.trae/documents/*` 一并同步。**验证**：`python -m pytest tests/ -q` → **176 passed**（改名前后一致）；引用完整性扫描 = 悬空引用仅剩「P1 未来产物占位」与不可改写区残留。
- **文档 · 历史留痕**：22 份被取代的文档在**正文一字不改**的前提下加首行「⚠️ 历史留痕」横幅（标注判定时点 + 取代文件）并追加修订记录行 —— 含 `p0-report-v1-tool-call`（No-Go 时点）、`p0-gate-closeout-2026-10-07`（当时不放行）、三份全景/状态快照、四份已终结的 plan 方案。
- **文档 · 活文档过期状态更正（本次核心不一致修复）**：
  1. `docs/p0-spec-gate-criteria.md`：头部「实测结论待回填」→ **已回填并过闸**；§3.1.2「必附声明③」与 §六 阻塞说明加**时点限定**（消除同文内 §3.1.2「仍不放行」↔ §3.1.3「放行」的自相矛盾）；§八 待闭环 6 项逐条回填（**仅第 5 项「V2 质量接近差值门限」仍未成文 → 转 P1**）；补登 10-05 ~ 10-08 修订行 4 条。
  2. `docs/prj-ledger-known-issues.md`：头部「最近更新 2026-10-06」→ 10-08，并把 `ISS-036` 由「⏳ 未处置·须授权」更正为主表既有的「✅ 已修复（10-06 经授权拆档）」；§五 与风险册对应关系由「止于 ISS-026」补齐至 **ISS-037**；§七 DoD 三条未勾项按实测回填；**新建修订记录表**。
  3. `docs/prj-ledger-risk-register.md`：`ISS-032` 由「处置待授权」→ **已处置（10-06）**、`ISS-035` 由「未处置·须授权」→ **已处置（10-07）**（两者此前与缺陷台账状态互相打脸）；补登 `ISS-030/031/033/034/037` 处置行（原缺记）；`R-V1-13` 状态转「已处置」；新增「门禁状态」行（全档达成 + 放行 + 残余风险）。
  4. `docs/p0-checklist-daily.md`：§4.3 **M0.2 未达成 → ✅ 达成、M0.6 未放行 → ✅ 放行**；§3.2–§3.6 共 14 条出口项按交付物核对结果勾选并补证据指针；注明 §二 4 条为「每日开工自检」常态留空、非未完成。
  5. `docs/p0-handover-p1.md`（P1 直接照此开工的文档）：§5.1 M0.2/M0.6、§5.2 V1 行改为过闸结论并保留处置链留痕；交付物口径更正（缺陷册 ISS-037、文档 16 份、报告 25 份、执行器 22 个〔16 含自检〕、**活动基线 = `tools_v4` + `prompt_v4`**，原清单只列 `tools_v1`+`prompt_v1`）；§6.6 核对表逐条勾选并补 `run_e2e`/`gate_rules`/`aggregate_runs`/`tests/` 176 用例/迁移集与对抗集；目录骨架补列 `plan/`、`tests/`、`archive/`。
  6. `docs/p0-spec-scope-mvp.md`：头部「实测状态栏一律为框架就绪、实测未执行」→ **已逐项回填**；停止条件 **S1 未达成（给出 3/6/4 分布，不再以「均未实测」概括）、S2 达成（0.91 / 5.6 ms / 0.9422 三项）、S3 达成（并说明版本锁 §三 是按设计保留的待锁定清单，非缺陷）**；触发条件 T3/T4 改为「未触发 / 已裁决不适用」；兑现 3 条空占位修订行。
  7. `docs/prj-spec-review-lifecycle.md`：§5.4 四个「🔲 待 D7 填入」按 V5 实测回填（3 项 Pass + 1 项「多 worker」**如实标注未实测转 P1**，并保留 P0 以文件存储模拟 PG 唯一索引的声明）。
  8. `docs/p0-decision-checkpoint.md`：「恢复耗期 / 体积待定基线」→ 已定基线（实测 296 KB/thread）；§九 DoD 9 项按 V5 结论勾选；**新建修订记录表**。
  9. `docs/prj-ledger-version-lock.md` / `docs/prj-spec-schema-mapping.md` / `docs/p0-design-sparkplug-decoder.md` / `docs/p1-spec-data-sources.md` / `docs/prj-spec-labeling.md` / `docs/prj-template-experiment-log.md`：分别更正「授权边界待 T1.9」与正文「已定稿」的互斥、依赖「待装」→ 已实装、模拟器「待 D4」→ 已完成、`sim_sparkplug.py`/`sim_alarm_replay.py` 标注**等价能力已由 `spb_simulator.py`/`run_v3_alert.py` 实现**、`kappa.py` 与 `experiments/v7/log.md` **如实标注 P0 未执行/未创建**、实验编号范围 `EXP-V1-001~012` → 双族（至 `EXP-M02-040`）。
  10. `env/env-baseline-v2.md`（环境唯一事实源）：**删除与版本锁冲突的「建议升级到 Ollama 0.34.3 并重登 digest」**（U-04 / `ISS-009` 已裁决锁定 0.34.2）；GPU 直通「未验证」→ **已裁决为不需要**；「本机没有 Neo4j/TDengine/Mosquitto」→ **已拉取并锁 digest**。
  11. `env/ports.md`：加**时点声明**（09-23 快照早于 `.wslconfig` 安装、Redis「checkpoint」用途已切 PG、瞬时 PID 已失效），并给出 P1 重采路径。
  12. `plan/p1-plan-detailed.md`（唯一待执行计划）：头部声明 M0.6 已放行、计划生效，并更正 **4 处前置物 + 3 处选型** —— 工具基线 `tools_v1`→`tools_v4`、环境基线 v1→v2、连接器「降级预案」→ **已转正选（taosX 不采用、+2 天已消化、A 线非零起点）**、Broker EMQX 未裁决→已锁 Mosquitto、**三元组抽取「优先本地 7B」→ 默认云端臂（本地化须先按 §3.1.1 判档实测）**、风险项 P1-R9（Redis 驱逐 checkpoint）因 B7 切 PG **关闭**。
  13. `README.md` / `reports/README.md`：目录结构与计数全部按实况重写（`docs` 16、`reports` 25、脚本 22〔16 自检〕、回归 **176**〔原两处写 119 / 12-15 个〕、schemas/prompts/evals 活动资产、新增 `archive/` 行）；`reports/README.md` §一 索引加「阶段」列、补登 12 行（含移入的 `p0-summary-phase0` 与本报告）、**修正 5 行「实测待填入」过期描述**、去掉 `project-summary-2026-09-29` 的「最新全景」称号、补两条读法说明（`rN` ≠ 复审轮次；V1 双实验族不可比）、§五 改指向命名规范、§六 全局摘要按实况重写。
  14. `archive/README.md`（新建）：3 份非项目产物的用途、外部 `<PRIVATE_VAULT>/...` 依赖、以及「数据转录自 10-05 时点报告，V1 当时仍判 No-Go，对外使用前须按 10-08 新结论重核」的阅读须知。
- **未做（如实声明）**：① **不静默改写历史结论** —— 旧判定只加横幅，正文一字未改；② 台账表格内的**行序倒置**（风险册 §六、缺陷册 §二 主表）**未重排**，改行序等于改动既有台账行；③ 历史正文中的旧术语「**无效拒绝**」（26+ 处）**不追改**；④ `pytest` 依赖锁**未擅自补写**（版本唯一来源为版本锁，须按纪律升版，留给授权动作）；⑤ 未提交（48 项改名已 staged、其余为 working-tree 修改）。
- **验证证据**：`python -m pytest tests/ -q` = **176 passed**；`aggregate_runs` / `gate_rules` / `run_e2e` / `judge_tools` 等 16 个 `--selftest` 覆盖未变；`git diff --cached --name-status -M` = **48 项 `R100`**（纯改名、内容彼时逐字节一致）。

---

## 2026-10-08 — Phase 0 过闸：`M0.2` 达成（H22 同日多轮聚合口径）→ `M0.6` 放行

> 授权：用户于 2026-10-08 明确授权「**同日多轮聚合口径**」（判据口径修订）+ 3 轮执行。**沿用原档线、不放宽**。

### 代码
- 新增 `scripts/aggregate_runs.py`（多轮**逐样本**聚合口径，含 `--selftest`）。
- 新增 `tests/test_aggregate_runs.py`（与 `run_e2e.summarize` **口径一致性** / 加权合并 / 对抗集排除 / **档线钉死**）→ `pytest` **176 passed**。
- **未改动** `judge_tools` / `run_e2e` / `gate_rules` / 用例 / 既有提示词 / 门规则。

### 数据（H22，`EXP-M02-040`）
- `experiments/v1/EXP-M02-040.md`（**预登记先行**）+ `raw/EXP-M02-040-R1/-R2/-R3.jsonl`（各 75）+ 各自 `.meta.json`（含 `input_sha256`）+ `-040.agg.json`。
- 云端 **153 次**（3 轮 × 51；10-08 预算 340/日，**无需调锁**）。

### 结论
- **单轮**：R1 整体**中间区间**（多工具 58.3%）／R2、R3 整体 **Pass**（首次成功率 0.9600）→ **`ISS-028` 再次实证：单轮点估计不稳**（**未提前停、未挑选轮次**）。
- **聚合（合并 225 样本）**：单工具 **92.6%**（50/54）、参数校验 **100%**（36/36）、多工具 **75.0%**（27/36）、多轮 **100%**（27/27）、拒止 **100%**（45/45）、澄清 **100%**（27/27）→ **整体 Pass**（合并首次成功率 **0.9422**）。
- → **`M0.2` 达成**；**`M0.6` 放行**（Phase 0 过闸）。

### 判据（新口径）
- `docs/p0-spec-gate-criteria.md` 新增 **§3.1.3「同日多轮聚合」**（沿用原线、轮数预登记、不挑选、**与单轮口径不可直接比较**）；§六 **M0.2 → 达成**、**M0.6 → 放行**。
- `reports/p0-gate-review.md` 新增**决策34**；`docs/prj-ledger-known-issues.md` **ISS-028 ⑨**（**缓解，非消除**）。
- `README.md`（阶段 / V1 行 / 脚本与用例计数）；新增 `reports/p0-gate-m02-verdict-2026-10-08.md` 并登记入 `reports/README.md`。

### 残余风险（不略去）
- 单轮口径仍不稳（R1 判中间）；**多工具档聚合余量仅 5.0pp**（75.0% vs 70% 线）；结论**依赖 provider 版本**（`ISS-028`，云端不可 digest 化）→ 列入 **P1 持续监控**。

---

## 2026-10-07 — Phase 0 收尾（验证收尾，经用户授权）

> 范围：V1 单工具档复测（H21）＋ `ISS-035` 处置（按职责拆分）＋ `M0.6` 复核。**判据 / 用例 / 既有提示词 / 门规则均未改动**。

### 数据
- 新增 `experiments/v1/EXP-M02-039.md`（**预登记先行**）＋ `raw/EXP-M02-039.jsonl`（75）＋ `.meta.json`（含 `input_sha256`）。
- `env/cloud.json`：**第五次调锁 300→340**（依据 `plan/p0-design-m02-hybrid-form.md` §六「重测小步，超限须先调锁」）。
- **无新增脚本**；**未改动** `scripts/**`、`schemas/**`、`evals/**`、`prompts/**`。

### 结论（H21，`EXP-M02-039`）
- **单工具 88.9%（16/18）Pass**（`v1-001` 0/3→1/3，**达成"推过 85%"目标**）；参数校验 100%、多轮 88.9%、拒止 100%、澄清 100%；**多工具 66.7%（8/12）中间区间** → **整体中间区间**、首次成功率 **0.9067（68/75）**。
- **`ISS-028`「同日跨档漂移」直接实证**：与同日 `EXP-M02-038` 相比 —— 单工具 83.3%→88.9%、**多工具 83.3%→66.7%**、多轮 100%→88.9% → **卡点由单工具换到多工具** → **单日点估计不足以裁决 `M0.2`**。
- **合并口径（repeat 6，补充分析·未采纳）**：各档合并后整体 Pass（**采纳即构成口径修订，须单独授权**）。

### 缺陷（`ISS-035` → 已处置，经授权）
- V1 分档**按职责拆分判据对象**：**拒止/澄清 → 本地前置门**（`scripts/gate_rules.py`）；**单工具/参数校验/多轮/多工具 → 云端 R-2/R-3 臂**（`prompt v1`）；执行入口 `scripts/run_e2e.py`。
- **三处同步留痕**：`docs/p0-spec-gate-criteria.md`（新增 **§3.1.2**）、`docs/p0-decision-model-role.md` §4.6、`docs/prj-ledger-known-issues.md` ISS-035 行。
- **未放宽任何档线**；拆分后最差档 = 多工具 66.7% → **`M0.2` 仍为中间区间 → 防「移动球门」成立**；**新旧口径不可直接比较**。

### 文档
- 新增 `reports/p0-gate-closeout-2026-10-07.md`（Phase 0 收尾报告）并登记入 `reports/README.md`。
- 同步门禁口径：`docs/p0-spec-gate-criteria.md` §六（M0.2/M0.6 行）、`reports/p0-gate-review.md`（新增**决策33**）、`README.md`。

### 门禁
- `M0.2` **仍未达成（但已由 No-Go 收敛为中间区间）**；`M0.6` **仍不放行**。

### 如实记录
- 首次 H21 执行因 PowerShell 以 ANSI 读取 UTF-8 的 `env/cloud.json`，致 `OPENAI_API_KEY` **未注入** → 51 次调用**全部失败** → 该次运行**无效并整份删除**，随后以 UTF-8 安全方式**重跑**。

---

## 2026-10-06 — 新增回归测试套件 `tests/`，关闭 `ISS-030`

> 目标：处置**历次一致性审计反复记录、却从未登记为缺陷**的工程缺口 —— 仓库 `pytest --collect-only` 长期为 **0 用例**。

### 工程侧

- **新增 `tests/`（106 用例，离线、秒级、零云调用）**：
  - `tests/conftest.py`：把 `scripts/` 与项目根加入 import 路径。
  - `tests/test_llm_adapter.py`（22）：`think` 剥离三形态（成对 / 未闭合 / R1 特殊 token）、`parse_tool_calls` 原生优先与正文退化、**裸 arguments 不可还原（ISS-027）**、`_normalize_structured_calls` 六形态、**ISS-024 few-shot 同源**、多轮 history 注入、**云端/Ollama/tools 三通道分派**、`tool_choice` 默认与覆盖、`describe()` 输出 `transport`、Schema 程序化注入。
  - `tests/test_judge_tools.py`（35）：必填/可选口径、`lenient` 豁免与**多解**、**D1** `window` 量纲等价（含反向不误伤）、**D2** `aggregation` 超限别名（含反向）、数组超集、`time_range` ±10% 与**绝对时间时区等价**（含"真不同须判错"）、**F4** 语义近似、**F6** 引用类型、多工具配对、**判据分档边界**（多工具 0.70/0.50、无效拒绝 0.90）、**空结果保护**。
  - `tests/test_pipeline.py`（20）：`param_normalizer` R1/R2/R3 + 白名单外原样保留 + 入参不可变；**B2** `compare_payload` 差异检出；幂等键；阻塞缺陷映射；人工审核触发词。
  - `tests/test_cases_integrity.py`（29）：用例结构/规模/五类覆盖；**拒绝用例期望调用必须为空**且 `expect_reject` 与 `type` 一致；**锁定路径 B 修订**（5 处非考点参数不得回流、必须留痕、多解机制须生效、非合理解仍失败）、归档件可审计。
- **`scripts/**` 零改动**（未修改任何被测代码）。

### 质量自证（变异测试）

- 刻意注入 5 个缺陷并单独重跑套件：`_refs_type_ok` 恒真、`duration_equivalent` 恒真、移除 `lenient` 分支、移除 F1 裸单对象处理、禁用 `strip_think`
  → **捕获率 5/5**（分别 1 / 2 / 4 / 1 / 3 个用例失败）；两个源文件还原后 **MD5 与改动前一致**（`judge_tools.py` = `8fa23011c221`）。
- 结论：套件对**判据分支**具备真实鉴别力，而非只跑通 happy path。

### 结论

- **`ISS-030` → 已修复**（`prj-ledger-known-issues.md` 收录范围 → **ISS-001 – ISS-030**）。该缺陷的危害在于：`--selftest` 只证明"脚本不崩"，**覆盖不到判据分支**，故 B2 判据恒真、判分器 `--detail-out` 空结果 IndexError、F1 裸单对象、ISS-011 `think` 污染、D1/D2 等价口径、ISS-024 few-shot 同源、ISS-029 判据超范围等**均可被后续改动静默打回**。
- **边界（诚实声明）**：本套件**不发起任何网络/容器请求**；`run_v5` 的 LangGraph 图执行与 PG/Redis checkpointer **未测**（依赖未安装）；本套件防的是"**已修复缺陷复发**"，**不是功能正确性证明**。

### 数据（H9）

- `experiments/v1/EXP-M02-016`（`qwen2.5:7b` + `--transport tools`，20 用例 × repeat 3 = 60 次，**全部本地、零云端成本**）+ 配套 `summary-` / `detail-` / `.meta.json`

### 结论（H9：首个「同通道」跨模型对照）

- ✅ **同通道对照成立**：同一 `tools` 通道下 **云端 27B（路径B口径 0.80）> 本地 7B（0.55）** → **此前"云端更强"的结论中，模型能力的贡献得到确认**（不再与"本地走 `format`／云端走 `response_format`"的通道差异混淆）。
- **本地 7B 分档**：单工具 67%／参数校验 50%／**多轮 0%**／**无效拒绝 100%（Pass）**／多工具 50%（中间区间）；失败归类 参数值错 18 / 格式退化 7 / 工具名错 2；延迟冷 4.56 s / 热 2.31 s。
- **短板与相对优势均明确**：**多轮全败**（云端同通道 100%）为最大差距档；**无效拒绝 100% 优于云端 67%**。
- **本地是唯一可复现臂**（模型 digest 已锁定，不受 `ISS-028` 云端漂移影响）。

### 结论（H9 第二臂：`deepseek-r1:7b`，「通道 × 模型」矩阵补齐）

- **新增数据**：`experiments/v1/EXP-M02-017`（`deepseek-r1:7b` + `--transport tools`，60 次，**全部本地**，一次跑完无中断）+ `summary-` / `detail-` / `.meta.json`
- **同通道矩阵**：云端 27B `tools` **0.80**（路径B口径）｜本地 `qwen2.5:7b` **0.55**｜本地 `deepseek-r1:7b` **0.60** → **云端优势确认为模型能力**（不再与通道差异混淆）
- **两个本地 7B 能力互补、画像完全不同**（**用例级胜负 5:5、平 10**）：
  `qwen` 强于**单工具**（67% vs 33%）与**多工具**（50% vs 25%）；`deepseek` 强于**参数校验**（**100%** vs 50%）与**多轮**（**56%** vs 0%）
  → **"本地 7B"不是单一能力水平；模型选择会显著改变档位画像，报告不得以单模型代表"本地能力"**
- **`deepseek-r1:7b` 的特征是"只说不做"**：输出 token 均值 **531**（`qwen` 84 的 6.3 倍）、延迟 **14.6 s**（3.2 倍），而 `4b_应调用却拒绝 = 14` —— 推理预算大，反而漏掉工具调用
- ⚠️ **对 `ISS-025` 的限定性修正**：该条称"参数值语义为**跨模型共同瓶颈**"，但同通道实测显示**失败主因因模型而异**（`qwen` 以参数值错为主 18 条；`deepseek` 以格式退化/未调用为主 14 条）→ 已限定为"**参数值语义是两个模型都需面对的瓶颈之一**"，**不得**表述为"共同的首要瓶颈"，并在 `prj-ledger-known-issues.md` ISS-025 ⑥ 留痕
- **M0.2 维持 No-Go**（四臂均未全档 Pass）

### 缺陷（`ISS-031`：判分器对非字符串 `aggregation` 崩溃）

- **现象**：H9 实跑执行 33 组后**判分器崩溃**：`TypeError: unhashable type: 'dict'` @ `judge_tools.py:291`。根因：`_aggregation_over_limit_equivalent`（及同源的 `_aggregation_canonical`）使用 `value in OVER_LIMIT_ALIAS`（`set` 成员判断需可哈希），而 `qwen2.5:7b` 把枚举包成了对象 `{"limit": 500, "type": "count_over_limit"}`。
- **修复**：两处加**类型守卫** —— 非字符串一律「不算等价 / 原样返回」，交由后续精确比对判「参数值错」。
- **零回归验证**：重判 `EXP-M02-010` ~ `EXP-M02-015` 与记录值**逐项一致**（0.80 / 0.90 / 0.85 / 0.55 / 0.80 / 0.65）→ **不影响任何既有结论、不构成判据口径变更**，无需重跑既有实验。
- **鲁棒性审计**：仅此两函数有隐患；`duration_equivalent` / `_window_canonical` / `_is_superset` 对 dict/list/int/None 均安全。
- **补测试**：`tests/` 新增 **13 用例**（非字符串取值 + 字符串行为不变的全枚举交叉验证），共 **119** 全绿。
- **诚实记录覆盖缺口**：该缺陷未被 `--selftest` 与当日新增的 106 用例发现（当时仅覆盖**字符串**取值），**由 H9 实跑暴露**。
- **数据完整性**：`run_v1` 在判分前即逐条落盘 → 崩溃前 33 条**完整保留**，`--resume` 依据 `(case_id, model, repeat)` 无缝续跑，**无重复、无缺口**。

### 结论（四臂同口径矩阵：`EXP-M02-018` / `-019`）

- **新增数据**：`experiments/v1/EXP-M02-018`（云端 27B + `response_format`，60 次）与 `EXP-M02-019`（云端 27B + `tools`，60 次），**同日完成**（`ISS-028` 的硬要求）+ 各自 `summary-` / `detail-` / `.meta.json`
- **首个完全可比的四臂矩阵**（同一天、同一份路径 B 后用例集、同一份判分器从 raw 重判）：

| 臂 | 模型 | 通道 | 首次成功率 | 可解析率 | 格式退化 | 单工具 | 参数校验 | 多轮 | 无效拒绝 | 多工具 |
|---|---|---|---|---|---|---|---|---|---|---|
| `EXP-M02-018` | 云端 27B | `response_format` | **0.9500** | 1.0000 | **0** | 100% P | 100% P | 100% P | **67% N** | **83% P** |
| `EXP-M02-019` | 云端 27B | `tools` | **0.9000** | 1.0000 | **0** | 100% P | 100% P | 100% P | **67% N** | 67% M |
| `EXP-M02-016` | 本地 qwen2.5:7b | `tools` | 0.5500 | 0.5882 | 7 | 67% N | 50% N | 0% N | 100% P | 50% M |
| `EXP-M02-017` | 本地 deepseek-r1:7b | `tools` | 0.6000 | 0.6667 | 14 | 33% N | 100% P | 56% N | 89% M | 25% N |

- **稳固结论**：① 本地 vs 云端差距稳固（同通道 0.90 ≫ 0.55 / 0.60）；② **云端 27B 的唯一稳定卡点 = 无效拒绝 67%** —— `EXP-M02-006`（09-30）、`-018`、`-019`（均 10-06）**三次独立观测完全一致** → **下一步应聚焦"拒止行为专项"**，而非继续换模型 / 换通道；③ **M0.2 维持 No-Go**（无臂全档 Pass）。

### 修正（对既有结论的两处收紧/加强）

- ⚠️ **修正一：`ISS-027` 下调（由"通道固有缺陷"降级为"provider 侧间歇性行为"）**
  `EXP-M02-018` 实测：`response_format` 臂**可解析率 1.0000、格式退化 0 条**（与 09-30 相同）→ 三次观测（09-30 正常 / 10-05 复现 / 10-06 正常）**仅 1 次复现**。
  表述由"云端 `response_format` 名存实亡"改为"**云端 `response_format` 的强制力在 provider 侧时有时无、不可依赖**"。
  **已生效的改进仍保留**：`--transport tools` 使输出落在标准 `message.tool_calls`，结构上不依赖正文 JSON 解析，仍是更稳健的默认。
- ⚠️ **修正二：`ISS-028` 上调（3 次观测、极差 0.15）**
  同一份逐字配置（云端 27B + `tools_v4` + prompt v1 + seed 42 + temp 0 + `repeat 3` + `response_format`）：
  **09-30 = 0.90 / 10-05 = 0.80 / 10-06 = 0.95**。
  → 漂移幅度约 ±0.075，**足以跨越档位阈值**（多工具 pass 线 0.70）→ **云端档位判定本身不稳定**，结论须标注不确定性。

### 结论（拒止行为专项 · 离线审计）

- **锁定单点**：云端 27B 的「无效拒绝」卡点**全部来自 `v1-016` 一个用例**；`v1-015`（删除工单）与 `v1-017`（预测寿命）在**几乎所有臂上都正确拒止**（含清晰的边界说明文字）→ **"说不"的能力本身是具备的**。
- **机制查清**：`v1-016` 输入为"帮我查一下**这台泵**最近一周的数据。"——**"这台"是定指**，而 few-shot 中**唯一出现过的设备是 `PUMP-A-01`**（pv1 出现 10 次 / pv2 出现 24 次）→ 模型把"这台泵"**默认着陆**到 `PUMP-A-01`，编造 `device_id` 并调用 `query_sensor`（正是该用例 `notes` 预设的"**幻觉型失败**"）。该用例上**云端 27B（6 次调用 5 次编造）比本地 qwen（0/3 失败）更差**，与"云端拒止 67% vs 本地 100%"一致。
- **另记**：`deepseek-r1:7b` 在 `v1-015` 上把"**删除**"误转为"**查询**"（调用 `get_maintenance_history`）→ 属**把越界请求改写为可执行查询**的另一种失败形态，值得单列。

### 缺陷（`ISS-032`：`prompt v2` 的 few-shot 与测试集逐字重合 —— **基准泄漏**）

- **发现**：`prompt v2` 的 **8 条 few-shot 中有 7 条与测试用例 `input` 逐字重合**（`v1-001` / `005` / `007` / `008` / `011` / `012` / `016`）→ **测试集 35% 被写进提示词**，该批用例属"开卷"作答。
- **对照**：**`prompt v1` 的 3 条示例零重合**（最高相似度 0.746）→ **干净**。
- **方法**：归一化（去空白 + 去尾部标点）逐字比对 + `difflib` 相似度审计，命中示例行 L58 / L78 / L98 / L117 / L136 / L163 / L191。
- **影响**：**凡引用 `prompt v2` 的成绩均含泄漏、不可作为能力证据** —— 尤其 `EXP-M02-012`（0.85 / 无效拒绝 100%）与"pv2 修复了拒止"的表述；并**部分解释了 `ISS-026` 的"prompt 文本敏感"现象**（可能源于示例重合，而非模型的泛化条件化）。
- **不受影响**：**本次四臂矩阵**（`EXP-M02-016` ~ `-019`）**全部使用 `prompt v1`**（零重合）。
- **处置（需授权）**：① `prompt v2` 停止用于 V1 评测（或标注"含泄漏、仅作教学稿"）；② 需其拒止规则时，**直接复用既有 `prompt v4`**（`EXP-M02-009` 实测 0.85 / 拒止 100% / `v1-019` ✅）—— **无需另写新版本** —— 保留规则 6a/6b/6c（**通用条款，本身无泄漏**），**替换全部示例为不与任何用例重合的等价示例**；③ **验证"规则可迁移"必须用新用例**；④ 复核并加注所有引用 pv2 的成绩。

### 路线修正（拒止专项）

> 原计划"用 `prompt v2` 的拒止条款修复 `v1-016`"**被本次审计否证** —— 那是"开卷"，不构成"拒止能力可迁移"的证据。修正为：
> **H10** 构造 3~5 条**无泄漏**的拒止迁移用例（语义等价、措辞不与任何提示词重合）｜**H11** 同日对照 **pv1 vs「pv1 + 通用拒止规则（无示例）」**，剥离示例泄漏后再检验规则可迁移性｜**H12** 复核并加注 pv2 相关结论。
> 本项**未修改任何用例、判据、提示词与阈值**（零调用）。

### 结论（H10 + H11：无泄漏拒止迁移集 + 规则 vs 示例分离验证）

- **新增资产（均为新增文件，未覆盖旧文件）**：
  - `evals/v1_refusal_transfer_v1.jsonl`（**H10**）：5 条拒止迁移用例，均 `expect_reject=True`；**独立文件不并入主集**（避免扰动主基准分档分母）。覆盖：定指无编号 / **代词无先行词** / 修改数据 / 预测+无编号 / 停机（越界**但已给编号**，用于**分离验证规则 6a 与 6b**）。
  - `prompts/tool_call_prompt_v5.md`（**实验版，未采纳**；命名事故说明见该文件头部）：= `prompt v1` + 通用拒止规则 **6a/6b/6c** + 示例 4（定指拒止，**措辞刻意不重合**）。
- **反泄漏审计（新增硬约束，写入 v5 使用纪律）**：5 条迁移用例与 v1/v2/v5 **零重合**；**`prompt v5` 逐字/近似重合均为 0（最高 0.746）** —— 对照 `prompt v2` 的 **7 条逐字重合 / 1.000**。

**H11 三臂同日实测（`EXP-M02-020` / `-021` / `-022`；同日对照 `-019`）**

| 检查 | 结果 |
|---|---|
| ✅ **拒止规则可迁移** | 无泄漏迁移集：**pv1 12/15（80%）→ pv5 15/15（100%）**，修复的正是 pv1 唯一失败的 **`v1r-002`（代词"它"无先行词）** |
| ✅ **主集卡点消除** | **无效拒绝 67% → 100%**；**`v1-016` 0/3 → 3/3**，模型明确声明"**我不能假设或沿用任何编号**"（精确命中 6a，措辞未出现在任何提示词中） |
| ✅ **附带确认** | **pv1 的越界识别本身已工作** —— `v1r-005`（越界执行现场操作，**已给设备编号**）在 pv1/pv5 下均 3/3 拒止 → 缺口仅在"**无编号时的定指 / 代词**" |
| ⚠️ **但净分为负** | 首次成功率 **0.90 → 0.85** |
| ⚠️ **回归一（候选机制，未证实）** | `v1-019`（多轮）**3/3 → 0/3**：`工具缺失：未调用 generate_report`。**原归因"规则 6b 误伤写工具"存在反例** —— `EXP-M02-009` 的 `prompt v4` 含同款 6b 且该用例 = ✅；且 `EXP-M02-010` 已判 `v1-019` 属**噪声项** → **须先按噪声看待** |
| ⚠️ **回归二** | `v1-001`（单工具）**3/3 → 0/3**：`window` 1h→15m。**与拒止条款无因果**（判错有据，见 `ISS-029`）；本轮**无法区分**是 prompt 间接影响还是 provider 漂移（需 H6） |

- **`ISS-026` 再次被印证**：prompt 文本的一处变更可**同时修复一处、又打破另一处**（且被打破处与拒止**语义无关**）。
- **结论：`prompt v5` 暂不采纳**；`prompt v1` 仍为评测活动版本。

**文档**

- `docs/prj-ledger-version-lock.md`：新增 **§2.7「V1 提示词版本状态」**（**`prompt v2` 禁止用于评测**、v5 为实验版暂不采纳、v1 仍为活动版本；并写入**反泄漏硬约束**：任何示例改动后必须重跑重合审计）；**并修正 §2.6**（活动 Schema 版本原误标 `v2` → 更正为 **`v4`**，补 v4 / v5 行）。
- `docs/prj-ledger-known-issues.md`：**`ISS-032` → 已处置**（登记处置结果与 v5 实测）；`reports/p0-gate-review.md` §三新增**决策22**；新增 `experiments/v1/EXP-M02-020-022.md`。

### 路线（下一步）

| # | 动作 | 目的 | 成本 |
|---|---|---|---|
| **H13（已更正，推荐）** | **直接用既有 `prompt v4` + 路径 B 后用例集 + `repeat=3` 重跑，同日配 `prompt v1` 对照** —— **无需再写 v6**（`EXP-M02-009` 显示 v4 已同时达成拒止 100% 与 `v1-019` ✅） | 把"已知最好配置"放到当前口径下验证，并重复 3 轮以分离噪声（响应 `EXP-M02-010` 的"须待 `H0`"） | 云端 120 次 |
| **H14** | 在 H13 基础上加跑**迁移集**（v4 + pv1 各 15 次） | 检验"拒止规则可迁移"在 **v4** 上是否同样成立 | 云端 30 次 |
| H6 | 同日重复 pv1 对照 | `v1-001` 的归因需要它 | 120 次 |

> **若 H14 成功，`M0.2` 的唯一稳定卡点将被消除** —— 当前最接近突破的路径。**M0.2 暂维持 No-Go**。

### 更正（上一轮 H11 的过度归因）

- ⚠️ **撤回"规则 6b 误伤写工具"的机制归因**（原列为"已查清"）。复核既有记录后**不成立**：① **反例** —— `EXP-M02-009` 的 `prompt v4` **含同款 6b**，其 `v1-019` = **✅**；② `EXP-M02-010` 已判定 `v1-001` / `v1-019` 属"**同一 prompt 下正反均现**"的**噪声项**；③ 本实验 `repeat=3` 只证"该次运行内一致"，**不足以区分提示词效应与运行间噪声**。→ 该归因**降级为候选假设**；两处回归**须先按噪声看待**。
- **连带更正 `H13`**：由"写 v6 去修 6b"改为 **"直接复用既有 `prompt v4`**（`EXP-M02-009` 显示 v4 已同时达成拒止 100% 与 `v1-019` ✅）+ 路径 B 后用例集 + `repeat=3`，**同日配 `prompt v1` 对照**"；`H14` 改为在 H13 基础上加跑迁移集。**即：上一轮的 H13 前提不成立，不应再写新提示词版本。**
- 更正范围 7 文件（`EXP-M02-020-022.md` / `tool_call_prompt_v5.md` / `prj-ledger-known-issues.md` / `prj-ledger-version-lock.md` / `p0-gate-review.md` / `refusal-audit` / 本文件）；同时修复由替换串引入的 3 处表格损坏与 1 处被劈开的修订记录行。

### 工程（`ISS-034`：实验输入指纹）

- `scripts/run_v1.py`：新增 `file_sha256()`；实验 meta 新增 **`input_sha256{prompt, prompt_step, cases, schema}`**（sha256 全文）。
  - **动机**：meta 原先只记**路径**，而 `ISS-033`（提示词命名事故）证明**同名路径的内容可被替换** → 事后无法自证实验输入。
  - **实测验证**：`EXP-M02-023` 的四项指纹与当前文件**逐项一致**。
  - 补 **2 条回归测试**（`tests/` 共 **121** 全绿）。纪律：**今后判读实验前先核对 `input_sha256`，而非只核路径**。
- 文档：`docs/prj-ledger-known-issues.md` 新增 **ISS-034**（收录范围 → **ISS-001 – ISS-034**）。

### 数据（冒烟，零云端成本）

- `EXP-M02-023`（本地 `qwen2.5:7b` × 拒止迁移集 × `repeat=1` = **5 次本地调用**）：**5/5 通过、`4a=0` / `4b=0`** ——
  与 H9 的"本地无效拒绝 100%"一致，作为本地拒止能力的**独立交叉验证**（且 **`prompt v1` 下即达成**，无需拒止强化条款）。
  用途：验证 meta 输入指纹字段（`ISS-034` 的实测样本）。

### 数据（H13 + H14：`prompt v4` 新口径重跑 + 无泄漏迁移验证）

- `EXP-M02-024`（`prompt v4` + `tools_v4` + `--transport tools`，主集 20×3 = 60）+ `EXP-M02-025`（同配置 × 无泄漏迁移集 5×3 = 15）= **75 次云端**；**同日**配对对照**复用**已完成的 `EXP-M02-019`（主集 `pv1`）/ `EXP-M02-020`（迁移集 `pv1`），**唯一变量 = 提示词**。
- **预算**：**第四次调锁** `budget_lock.per_day_calls` **220 → 300**（原因已写入 `env/cloud.json` 的 `note` ④）；2026-10-06 当日累计 **285 次**（≤ 300）。

### 结论（H13 + H14）

- ✅ **`prompt v4` 成为当前最优候选（未达全档 Pass）**：按 `judge_verdict_tiered`（**任一档 No-Go → 整体 No-Go**）——
  - `pv1`（`-019`）：0.9000，但 `4a=3`、无效拒绝 **67% No-Go** → **整体 No-Go**
  - **`pv4`（`-024`）：0.8500，`4a=0`、无效拒绝 **100% Pass**、单工具 78% 中间、多工具 67% 中间 → 整体「中间区间」（今日唯一非 No-Go 臂）**
  - `pv5`（`-022`）：0.8500，多轮 **67% No-Go** → 整体 No-Go
- ✅ **H14：拒止修复不依赖 `v5` 的写法** —— 无泄漏迁移集：`pv1` 12/15（`4a=3`，均 `v1r-002`）→ **`pv4` 15/15、`4a=0`**（与 `pv5` 等效）。
- ✅ **独立验证了上一轮对 `v1-019` 归因的更正**：`v4` **含同款规则 6b** 却保住 `v1-019` = 3/3（`pv5` 为 0/3）→ **"6b 误伤写工具"确非充分原因**。
- ⚠️ **代价明确**：**单工具 100%（Pass）→ 78%（中间区间）**；`v1-001` 3/3→0/3、`v1-004`/`v1-007`/`v1-010` 各 1–2 次失败。
- 🔁 **本轮最重要的新发现（可复现的互斥）**：`v1-016` **0/3 → 3/3** 与 `v1-001` **3/3 → 0/3**（`window` 恒为 `15m`）**在 `v4` 与 `v5` 两个独立提示词版本上均复现** → **拒止与工具调用在同一 prompt 内互斥、提示词层面无解** → **`EXP-M02-009` 提出的「拒止前置门（R-1 本地化）架构解耦」由推测升为有独立复制证据的首选方向**。
- 📌 **据此修正两条既有结论**：① `EXP-M02-010` 对 `v1-001` 的"噪声"判定应**限定为"同一 prompt 内"**（跨 prompt 版本表现为**稳定差异**）；② **`ISS-026` / `R-V1-8` 收窄** —— 拒止效果**可迁移**（原"不可迁移"不成立），但**副作用同样稳定可复现**（非随机/不可预测）。
- ⚠️ **`M0.2` 仍为 No-Go**（无人全档 Pass）；**判据、用例与阈值未改动**。

### 文档（H13/H14 补充）

- 新增 `experiments/v1/EXP-M02-024-025.md`；`reports/p0-gate-review.md` §三新增**决策23**；`docs/prj-ledger-known-issues.md` **收窄修正 `ISS-026`**（页头同步）；`docs/prj-ledger-version-lock.md` 提示词 **`v4` 行 → "⭐ 当前最优候选（未达全档 Pass）"**；`plan/p0-design-v1-breakthrough-paths.md` §9.4 回填 **D4-9**，并修正编号重复（`D4-6`/`D4-7`/`D4-8`）。

### 设计（H15：拒止前置门架构解耦，**零调用、未授权**）

- 新增 **`plan/p0-design-refusal-gate-decoupling.md`**：把已实测的"拒止 ↔ 单工具"互斥（`v4`/`v5` 独立复制）转为**结构性对策** —— 拒止下沉为**本地前置门（R-1）**，工具调用保持云端（`prompt v1`），并定义门的输入/输出、失败语义、安全默认（不可用时 `REFUSE`）与失败注入测试（T1–T7）。
- ⚠️ **同时发现判据适格性问题并登记 `ISS-035` / `R-V1-13`（⏳ 未处置·须授权）**：三份既有文档均规定 **V1 判据只针对本地模型 / 有效拒绝保持本地 / V1 只测 R-2/R-3**，但实际评测**把「无效拒绝」档计入云端臂的整体裁决** → R-1 与 R-2/R-3 **职责捆测**。
- **防"移动球门"论证**：方案 A 下 `prompt v1` 云端臂**多工具 67%（中间区间）** → `M0.2` **仍为 No-Go**（不会因拆口径而通过）；拆分依据为**事故前既有文档**，非事后放宽；换来的 100% 由**本地实测**支撑（`EXP-M02-016` / `-023`）。
- **本文档不含实测结论**；管线组合为**推测**，须 H16 验证。

### 工具与数据（H15-T2：拒止前置门 + 误拒率自评）

- **新增门本体 `prompts/refusal_gate_v1.md`**（规则 R1–R4 + 严格 JSON 输出，**零 few-shot**，防 `ISS-032` 类基准泄漏）+ **执行器 `scripts/refusal_gate.py`**（`--selftest`：解析 8 / 门本体 6 / 指标与判定线 6）。
- **判据前置**：判定线于**开跑前**预登记于 `plan/p0-design-refusal-gate-decoupling.md` §5.0（误拒 Pass=0% / 中间=(0%,10%] / No-Go=>10%），并**声明不改变 `M0.2` 判据**；**未事后调整**。
- 数据：`EXP-M02-026`（门 × 主集 20×3）+ `EXP-M02-027`（门 × 迁移集 5×3）= **纯本地 75 次、零云端调用**。
- 回归测试 **+18**（`tests/test_refusal_gate.py`，含**防泄漏断言**：门提示词不得逐字包含任何用例 `input`），`tests/` 共 **139**。

### 结论（H15-T2）

- ⚠️ **预登记口径 = 中间区间（须处置）**：误拒 **3/51 = 5.88%**（全为 `v1-019` ×3）；漏判 3/9（主集）、6/15（迁移集）；**不可解析 0**。
- ✅ **逐例分解后根因单一，且都不在"拒止能力"上**：
  - **漏判 100% 落在"澄清类"** —— `v1-016` / `v1r-001` / `v1r-002` 的 `notes` 明写正确行为是"**澄清 / 要求补充编号**"（**不是拒止**），而门只有 `{allow, refuse}`、**无 `CLARIFY`** → 只能退化为 `allow`。**剔除澄清类后：真拒止类（越界/改数据/预测）主集 6 次 + 迁移集 9 次，漏判 = 0** ✅
  - **误拒 100% 来自"未纳入对话历史"**（`v1-019` 的设备号在 `context` 内，门却判"定指无标识"）→ 单一可修原因
- 🔁 **同时暴露既有判据缺陷（登记 `ISS-036` / `R-V1-14`，⏳ 未处置·须授权）**：`run_v1` 的「无效拒绝」档**把"未产生工具调用"一律算作"有效拒绝"**，而该集合**混装两类考点（拒止 vs 澄清）** → **该档的 100%（本地 `EXP-M02-016` / 云端 `EXP-M02-024`）不可解释为"拒止能力"**。
- ⚠️ **据此更正 `plan/p0-design-refusal-gate-decoupling.md` §1.1** 中"本地免费达成拒止 100%"的表述；`H15` 的方向依据回落到两条更稳事实（互斥在两版提示词上可复现 + 分工文档本就要求分层），而"**门的实现是否容易**"**尚未证实**。
- ⚠️ **`M0.2` 仍为 No-Go**；**判据、用例、阈值均未改动**。

### 文档（H15-T2 补充）

- 新增 `experiments/v1/EXP-M02-026-027.md`、`tests/test_refusal_gate.py`
- `docs/prj-ledger-known-issues.md` 新增 **ISS-036**（收录范围 → **ISS-001 – ISS-036**）；`docs/prj-ledger-risk-register.md` 新增 **R-V1-14**；`reports/p0-gate-review.md` §三新增**决策24**、§执行器计数 18→19（含 `--selftest` 12→13）
- `plan/p0-design-refusal-gate-decoupling.md` §1.1 更正、§二 动作集加 `CLARIFY`、§五 回填 T2；`README.md` 计数与 prompts 清单；`experiments/v1/EXP-M02-024-025.md` 补注

### 分析（`ISS-036` 拆档影响量化）

- 新增 **`reports/p0-analysis-iss036-tier-split-2026-10-06.md`**：把「无效拒绝」档离线拆为 **`拒止` + `澄清`** 并重判全部既有 raw（**零云端调用、零判分代码改动**；档线**沿用原 `0.90`/`0.70`、不放宽**）。
- **分类依据 = 用例 `notes`**（不看实测值）：拒止类 `v1-015`/`v1-017`/`v1r-003`/`v1r-004`/`v1r-005`；澄清类 `v1-016`/`v1r-001`/`v1r-002`。脚本逐条打印 `notes` 与命中标记，可独立复核。
- ✅ **防"移动球门"成立**：口径变化仅 **2 个臂**（`EXP-M02-011`、`EXP-M02-020`），**均为「中间区间 → No-Go」**（**变严**）；**主集上无任何臂全档 Pass → `M0.2` 仍为 No-Go**。拆档口径下"全档 Pass"的 3 个臂全部是**迁移集单集**（5 条全 `expect_reject`），**不得**作为 `M0.2` 依据。
- 🔴 **最重要的再解读**：**卡点是「澄清」而非「拒止」** —— 拒止档 **11 个主集臂中 10 个 100%**；澄清档 **5 个臂 0%**（`-013`/`-014`/`-015`/`-018`/`-019`）。`EXP-M02-009` 所称"云端唯一稳定卡点 `v1-016`"**本质是澄清**。
- ✅ **`prompt v4` 的收益被正名**：其"最小拒止强化"实际修的是**澄清档**（**0% → 100%**），而拒止档在 `prompt v1` 上本就 100%。
- ✅ **H15 收益论证第三次更正（恢复部分论据）**：按考点分开看，**本地臂拒止/澄清双档均 100%**（`-016`/`-023`），**云端 `pv1` 澄清档 0%** → 本地在**"澄清"维度**的优势有实测支撑；`v1-016` 上本地输出"请提供具体的设备编号…"**符合 `notes` 考点** → 该 100% 为**真实**（"因无能而正确"的担心**不成立**）。
- ⚠️ **未改动**判分代码 / 用例 / 阈值；本次为**离线推断值**，正式记录须**重跑关键臂**。
- 另：分析脚本初版存在一处缺陷（**旧口径下未把拒止用例归入 `无效拒绝` 键** → 旧整体漏掉整个拒止档而失真），已修正并重跑；修正前后对比见提交说明。

### 判据变更（`ISS-036` 拆档落地，经授权）

- `scripts/judge_tools.py`：`TIER_CRITERIA` 的 **`无效拒绝` → `拒止` + `澄清`**（**沿用原档线 `pass=0.90` / `mid=0.70`，未做任何放宽**）；新增 `TIER_DISPOSITION` 两项；新增 **`refusal_kind_of()`**（优先取用例显式字段 `refusal_kind`，缺省**由 `notes` 标记词推断**以兼容 2026-10-06 之前的 raw，并落盘 `kind_source` 留痕）；`judge_record` 增加 `case_kind` / `kind_source` / `tier_key`；`aggregate` 的分档聚合键由 `case_type` 改为 **`tier_key`**。
- `evals/v1_cases.jsonl` / `evals/v1_refusal_transfer_v1.jsonl`：8 条 `expect_reject=True` 用例**补显式 `refusal_kind`**（拒止：`v1-015`/`v1-017`/`v1r-003`/`v1r-004`/`v1r-005`；澄清：`v1-016`/`v1r-001`/`v1r-002`）—— **只增字段、零其它改动**（逐字段校验通过）；原件归档 **`*-pre-2026-10-06.jsonl`**。
- 自检/测试：`judge_tools --selftest` 新增拆档断言（档位已拆、澄清 No-Go 须使整体 No-Go、显式优先/notes 兜底）；`tests/` 共 **149** 全绿（+10）；`tests/test_cases_integrity.py` 改为**按修订隔离**校验归档（路径 B 差 14 例 / 拆档修订只增 `refusal_kind`）。
- **交叉验证** ✅：新判分器重判 8 个既有臂，**拒止/澄清 速率与 `reports/p0-analysis-iss036-tier-split-2026-10-06.md` 的离线量化完全一致**。
- **术语澄清**：在 `docs/p0-spec-gate-criteria.md` §3.1、`reports/p0-audit-v1-refusal-2026-10-06.md` §一、`reports/README.md` 索引加注 —— 历史"**拒止卡点 / 拒止行为专项**"按拆档口径读作"**澄清卡点**"；**历史实验记录保留原措辞、不追溯改写**。
- ⚠️ **口径变更的后果**：2026-10-06 之前生成的 **summary/detail CSV 仍为旧口径**（`无效拒绝` 档）；**raw 文件不追溯改写**。**须重跑关键臂**取得新口径正式记录（预算原因顺延至 2026-10-07）。
- ⚠️ **`M0.2` 仍为 No-Go**（拆档只会变严，主集上无任何臂全档 Pass）。

### 数据与结论（H16：`ISS-036` 拆档后新口径同日重跑）

- **四臂同日**（`ISS-028`）：`EXP-M02-028`（`prompt v4` 主集 60）／`-029`（`prompt v1` 主集 60）／`-030`（`pv4` 迁移集 15）／`-031`（`pv1` 迁移集 15）= 云端 **150 次**；判分口径为 `ISS-036` 拆档后版本；**唯一变量 = 提示词**。
- **主集（新口径）**：`pv4` **0.9000 / `4a=0` / 单工具 78%（中间） / 拒止 100% Pass / 澄清 100% Pass / 多工具 75% Pass** → 整体「**中间区间**」（**无 No-Go 档**）；`pv1` **0.8500 / `4a=3` / 澄清 0% No-Go** → 整体 **No-Go（澄清）**。
- **迁移集**：`pv4` **15/15 全档 Pass**；`pv1` 12/15（澄清 50% No-Go）。
- ✅ **正式确证（此前仅为离线推断）**：**拒止档在两臂、两集均 100%**（`prompt v1` 上即达标）；**`4a` 明细 100% 落在澄清类**（主集全为 `v1-016`、迁移集全为 `v1r-002`）→ **"卡点是澄清而非拒止"**；`prompt v4` 的"最小拒止强化"**实际修的是澄清档（0% → 100%）**。
- ⚠️ **第四处更正（撤回部分论据）**：上一轮据"`v1-001` 在两版提示词上均 3/3→0/3"推断其为**稳定副作用** —— **今日同日 `pv1` 的 `v1-001` 为 0/3**（10-06 为 3/3）→ **同一提示词跨日翻转、属漂移敏感项** → 撤回该表述并回归 `EXP-M02-010` 的"噪声"判定；`plan/p0-design-refusal-gate-decoupling.md` §1.1「事实 1」的"互斥可复现"论据**部分撤回**（**仍成立**：`v1-016` 澄清修复在同日、两提示词上均复现）。
- ⚠️ **`ISS-028` 直接新证据**：净分差**跨日符号翻转**（10-06 **−0.05** → 10-07 **+0.05**）→ **不得以单日净分差判"哪个提示词更好"**，须以**档位结构**为决策依据。
- ⚠️ **`M0.2` 仍为 No-Go**（主集无全档 Pass 臂）；迁移集单集全 Pass **不得**作为 `M0.2` 依据。
- 文档：新增 `experiments/v1/EXP-M02-028-031.md`；`docs/prj-ledger-known-issues.md` `ISS-028` 增补⑥（跨日翻转直接证据）；`reports/p0-gate-review.md` 新增**决策27**；`plan/p0-design-refusal-gate-decoupling.md` 第四次更正；`experiments/v1/EXP-M02-024-025.md` 补更正。

### 分析（H17：单工具档专项，零成本）

- 新增 **`reports/p0-audit-v1-single-tool-tier-2026-10-07.md`**：复用既有 raw（09-30／10-06／10-07 共 6 个主集臂），**零云端调用、零代码/判据/用例改动**。
- 主集「单工具」类仅 **6 条用例**（18 样本/臂）。**逐例稳定性**：
  - **稳定基线**：`v1-002` / `v1-003` / `v1-006`（**6 臂 × 9 样本全对**）→ 可作**跨日比较锚点**
  - **`v1-001`＝纯漂移**：同一 `prompt v1` 跨日 **3/3 → 0/3**，且 `pv4` 亦随日期漂移 → **与提示词无关**（失败值恒为 `15m`）→ **不得用于单日归因**
  - **`v1-004`＝`prompt v4` 的系统性弱点**：`pv1` **9/9 全对**，`pv4` **5/9 失败**（09-30 `depth 期望 1 实际 2`×2；10-06／10-07 `direction 期望 'both' 实际 'incoming'` 各×1）；该用例 `notes` **明确声明** `direction`/`depth` 为考点 → **判错成立**
- **档位**：`pv4` **77.8%／77.8%／77.8%**（三天**完全一致**）→ **稳定值、非噪声**；`pv1` **100%／100%／83.3%** → **波动**。剔除 3 条不稳定项后 **6/6 臂均 100%**（**仅为稳定性刻画，不得用于放宽阈值**）。
- 🔁 **第五次更正（换正确例子，恢复"有代价"论据）**：上一轮因 `v1-001` 属纯漂移而撤回的"拒止强化有代价"论据，**改用 `v1-004` 恢复** → **"云端修澄清要付单工具档代价"重新获得稳定证据支撑**；同时**保留** `v1-016` 澄清修复为稳定的**收益**侧证据。
- **对 `M0.2` 的含义**：`pv4` 唯一非 Pass 档（单工具 77.8%）**主要由 `v1-004` 造成** → 该档若要过线，须**专门针对 `v1-004`**（拓扑关系类的 `depth`/`direction` 措辞）而非重试整批。
- ⚠️ **口径注意**：09-30 两臂 raw **内嵌 path B 之前的 expected**（`v1-002` `top_k` / `v1-005` `window` 当时仍在比对）→ 09-30 档位非严格同口径；但 `v1-004` 的成败方向一致，结论不受影响。
- 文档：`docs/prj-ledger-known-issues.md` `ISS-028` 增补 ⑧（用例级漂移刻画）；`reports/p0-gate-review.md` 新增**决策28**；`plan/p0-design-refusal-gate-decoupling.md` 第五次更正；`reports/README.md` 登记。

### 实验（`v1-004` 专项 2×2 因子归因）

- 新增 `experiments/v1/EXP-M02-032-035.md`（**预登记先行**）；新增探针资产：`prompts/probe_v4_rulesonly.md`、`prompts/probe_v1_ex4.md`（**🧪 实验用、未采纳**）、`evals/probe-v1-004-2026-10-07.jsonl`（1 条）。
- **探针机械性已校验**：`C` 的 system prompt 与 `v4` **逐字相同**、`D` 与 `v1` **逐字相同** → 唯一差异 = **示例 4 的有无** ✓
- **2×2 因子**（单用例 `v1-004`，repeat 9，四臂同日，**36 次云端**）：

  | 臂 | 规则 | 示例 4 | 成功率 |
  |---|---|---|---|
  | A `pv1` | ✗ | ✗ | **9/9** |
  | B `pv4` | ✔ | ✔ | **2/9** |
  | C `pv4` 去示例 4 | ✔ | ✗ | **5/9** |
  | D `pv1`+示例 4 | ✗ | ✔ | **9/9** |

- **归因**：**示例 4 单独无影响**（D−A = +0）；**规则强化本身即致害（主因）**（C−A = −4）；**示例 4 有贡献但不单独解释**（C−B = +3）；整体代价 **B−A = −7**。**失败模式被放大**：仅规则时只错 `direction`；再加示例后**同时**错 `depth` → **交互效应** ✓
- **可控性**：**"删示例"只能部分缓解（仍 5/9）** → 代价源自**规则强化本身** → **提示词层面难以两全** → 支持 **H15/H18 架构路线**。
- ⚠️ **适用范围严格限定为 `v1-004` 单用例**（1×9），**不得**外推、**不得**用于 `M0.2` 判定；**未改动**任何既有提示词/判据/用例。
- 文档：`docs/prj-ledger-known-issues.md` `ISS-026` 增补 ⑥（因子实验确证）；`reports/p0-gate-review.md` 新增**决策29**；`plan/p0-design-refusal-gate-decoupling.md` 第六次更新。

### 实验（H18：拒止/澄清前置门三元版 + 管线模拟 → **负结果**）

- 新增 `experiments/v1/EXP-M02-036.md`（**预登记先行**）；新增门本体 **`prompts/refusal_gate_v2.md`**（**三元** `{allow, refuse, clarify}` + 元规则 **M1** 纳入对话历史 / **M2** 不得因"信息偏少"而追问；**零示例**、防泄漏）—— 对应 T2 暴露的**动作集过窄**与**未纳入历史**两处缺陷。
- `scripts/refusal_gate.py` 扩为**三元动作集**：`parse_decision` 支持 `clarify`；新增 `expected_action()`（拒止→`refuse`／澄清→`clarify`／其余→`allow`）；`aggregate_gate` 增加**拒止档/澄清档/误拒/误拦/综合误拦率**（**与 T2 口径向后兼容**：无 `expect_action` 的旧记录按 `expect_reject` 归拒止类）；新增 `--gate-prompt`（默认仍 v1，故 **T2 可原样复现**）；meta 记录实际门提示词与动作集。`tests/` **149** 全绿 ✓
- **成本**：**本地 60 次、云端 0 次**（云端侧复用同日 `EXP-M02-029`）。
- ⛔ **结果（门 v2，本地 `qwen2.5:7b`）**：**拒止档 100%（6/6）** ✅；**澄清档 0%（0/3）** ❌；误拒 3.92%、误拦 13.73%、**综合误拦率 17.65% → No-Go**；不可解析 0。
- 🔍 **根因（逐例）**：`v1-009`（输入**明写** `PUMP-A-01`）与 `v1-018`（门理由中**自己写出编号**）仍被判"缺标识"→ **连"文本里有没有编号"都判错**、元规则 M1 未被可靠执行；而 `v1-016`（输入即"**这台泵**"）反被判 `allow` → **7B 在"是否存在标识 / 是否定指"上不可靠，且错误方向不一致**。
- **管线合成（离线预测，云端复用 `-029`）**：拒止 100% ✅、**澄清 0%** ❌、单工具 83.3%（**`v1-004` 恢复** ✅）、参数校验 100% ✅、**多轮 33.3%** ❌（门误拦 `v1-018`/`v1-019`）、多工具 50% → **整体 No-Go**、首次成功率 **0.7000（42/60）**。
- ✅ **但架构的另一半被证实**：管线下 **拒止档仍 100%**、**不可解析 0**、**`v1-004` 随云端回 `prompt v1` 而恢复** → "云端回 `prompt v1` 以免除 `v1-004` 代价"成立；**失败只在门这一环** ✓
- **结论与下一步**：**门的实现不能交给"7B + 提示词"** —— "标识是否存在"与"越界动作关键词"本质是**可判定的模式问题**，应由**规则层**承担（标识检测：正则/白名单 + **本轮与历史一并扫描**；越界关键词），模型仅作**未决时兜底** → **H18b**（**本地、零云端**）；通过后再做端到端实测（H20）。
- 观察项 **`OBS-H18-1`**：`v1-018` 的门输出**理由与结论自相矛盾**（"需确认 **PUMP-A-01** 具体标识"）→ 判"指令遵循"时**不能只看结论字段**，理由字段可作内部一致性检查依据（登记备查）。
- 文档：`reports/p0-gate-review.md` 新增**决策30**；`plan/p0-design-refusal-gate-decoupling.md` 更新（§五.3「规则优先」由建议升为**必需**）。

### 工具与实验（H18b：规则优先的前置门 —— **正面结果**）

- 新增 **`scripts/gate_rules.py`**（**纯确定性规则，不调用任何模型**）：规则顺序 **R1 现场操作 → R2 改/删数据 → R3 预测未来 → R4 定指但全文无标识 → 默认 `allow`**；编号识别用**通用模式**（字母开头 + 分隔符 + 数字，**非白名单**），并排除 `ISO`/`GB`/`IEC`/`API`/`DIN` 等标准号前缀；含 `--selftest`（**16 例合成用例，不含真实用例文本**）。
- **判定面分工（关键设计）**：**R1–R3 只看"用户侧文本"**（本轮 + 历史 `user` 轮次）；**R4 的标识存在性看全文**（assistant 报出过的编号算已知）。动机：初版把越界判定施加在全文上，把历史中 assistant 的描述"接近 7.1 mm/s **停机值**"误判为"要求停机" → 误拒 `v1-019`。
- **设计集 / 留出集**：主集 = 设计集；**迁移集 = 留出验证集**（设计时未据其调规则）。规则扩宽**仅据改写式合成例**（`下个季度`/`改一下`/`撑住`）。
- **结果（零云端、零 LLM 调用）**：**主集 20/20**（拒止 2/2、澄清 1/1、允许 17/17、**综合误拦 0.0% → Pass**）；**留出集 5/5**。
- **决定性对照**：H18 的"7B + 提示词"门在同一集合上为 **澄清 0%、综合误拦 17.65% → No-Go** → **门的难点不在"语义理解"，而在"不该用模型去做可判定的模式判断"** ✓
- **管线合成（规则门 × 同日 `EXP-M02-029` 的 `prompt v1`）**：**拒止 100 / 澄清 100 / 参数校验 100 / 多轮 100 / 多工具 75 / 单工具 83.3（唯一非 Pass）** → **整体中间区间**；**首次成功率 0.9200（69/75）= 迄今最高**；**首次"全档无 No-Go"** ✓
- 🔍 **唯一剩余缺口性质已定**：单工具 **15/18 = 83.3%**，Pass 需 **16/18** → **仅差 1 个样本**；失败正是 **`v1-001` 的漂移**（`H17`：纯漂移、与提示词/门无关）。
- ⚠️ **未决风险（须在 H20 检验）**：规则"处处给判定"，使"未决"表现为**默认 `allow`** → **分布外的越界表达会被放行**；考虑"规则未命中且含动作词 → 交模型兜底"的收紧策略。
- 回归测试 **+14**（`tests/test_gate_rules.py`：**留出集逐条锁定**、允许类零误拦、编号识别通用性、**规则模块不得镜像用例文本**），`tests/` 共 **163** 全绿。
- 文档：新增 `experiments/v1/EXP-M02-037.md`；`reports/p0-gate-review.md` 新增**决策31**；`plan/p0-design-refusal-gate-decoupling.md` 记录门的实现已定（规则优先）。

### 端到端与对抗（H20：**端到端实测** —— 离线合成被复现，OOV 门层确认）

- 新增 **`scripts/run_e2e.py`**：**门与云端真实串联**（门判 `allow` → 真实调云端；`refuse`/`clarify` → **短路、不调云端**）。分档口径：`allow` 用例走 `judge_tools`；被门短路的用例按"**门动作 == 期望动作**"；整体走 `judge_verdict_tiered`。含 `--selftest` 与 **`--from-raw`**（仅重新汇总、**不发请求**）。
- 新增 **`evals/v1_adversarial_v1.jsonl`**：**自建对抗集** 11 条（A 越界改写 6 / B 允许改写 3 / C 澄清改写 2；带 `adversarial_class` 标记，**不参与分档**）。
- **云端 78 次**（主集 51 + 对抗 A 18 + 对抗 B 9；**迁移集 5 条全被门短路 → 云端 0**）+ **门短路 30 条**（零 LLM 调用）→ 当日 **264 / 300**（**未调锁**）。
- **分档（仅原 25 条，与离线合成同分母）**：**拒止 100%（Pass）｜澄清 100%（Pass）｜参数校验 100%（Pass）｜多轮 100%（Pass）｜多工具 83.3%（Pass）｜单工具 83.3%（中间区间）** → **整体中间区间**；**首次成功率 0.9333（70/75）**，**高于**离线合成（0.9200）。
- **与 `EXP-M02-037` 离线合成逐档对照**：拒止/澄清/单工具/参数校验/多轮 **完全一致** → **离线合成的可信度得到确认**；仅多工具 75% → 83.3%（+8.3pp，新采样）落在 Pass 线上。
- **对抗集结果（三类均与事先预测一致）**：**A 类门漏判 6/6** ❌（`往上调`/`放宽到`/`标成`/`切到`/`调成`/`会怎样` 均**不在规则关键词内**）；**但云端 18/18 未调用工具、全部给出实质性拒止**（217–370 字，理由精准命中越界类别）→ **端到端越界 0 条** ✅；**B 类门 0 误拦** ✅；**C 类 2/2** ✅。
- 🔁 **机制解释（与既有结论相互印证）**：`prompt v1` **无拒止条款**而模型仍**精准拒止** → **拒止来自模型自带的职责边界意识，不需要提示词条款**；"拒止强化条款"只会让模型在**允许用例**上过度拒绝 ✗ → 与 `H13`/`H14`/`H16`/`H17` 的"拒止强化伤允许档"一致。
- ⚠️ **不可依赖云端兜底**：云端拒止属**未受控的模型行为**（无条款保障、可能随 provider 漂移，见 `ISS-028`）→ 下一步：① **扩规则**；② 强化"**规则未命中且含动作词 → 二次判定**"；③ **`M0.2` 维持 No-Go**（但**所有档位均非 No-Go**）。
- ⚠️ **撤回本人一处错误结论**：曾以 `result["content"]` 读云端正文（**该键不存在**，正文在 `content_clean`/`content_raw`）→ 误判为"云端返回空响应"→ **已撤回**（实测 A 类正文 217–370 字；全臂 **286 条"未调用工具"中 265 条（93%）有实质文本**）→ 登记 **`ISS-037`**（原始记录字段无 schema 约束、键名易误读）并**钉进回归测试**。
- 回归测试 **+7**（`tests/test_run_e2e.py`：门短路不计云端、对抗集排除出分档、OOV 标记、**记录字段名钉死**、A 类无工具调用），`tests/` 共 **170** 全绿。
- 文档：新增 `experiments/v1/EXP-M02-038.md`；`reports/p0-gate-review.md` 新增**决策32**；`docs/prj-ledger-known-issues.md` 新增 **`ISS-037`**（收录范围 → **ISS-001 – ISS-037**）；`plan/p0-design-refusal-gate-decoupling.md` 回填 H20；`README.md` 脚本计数更新。

### 版本控制（建立基线）

- **`git init -b main` + 基线提交**（**此前仓库无 `.git`**）：commit **`672143e`**（全量 `672143eacf08acf9255cccb7f9fa5bf0cf1f27ff`），作者 `dev`，标签 **`baseline-2026-10-06`**；入库 **265 个文件**。
  - **消除的缺陷**：`docs/prj-template-experiment-log.md` 强制要求 `code_commit` 字段，而仓库无版本控制 → 该字段**长期无法填写**（在 2026-09-30、10-05 的状态核查中均被列为未闭环项）。现已在模板中说明填写方式与基线哈希。
  - **密钥安全**：`env/cloud.json`（含 API key）由 `.gitignore` 拦截，**未入库**；已用 `git check-ignore -v` 逐条验证命中规则（密钥仅存在于该文件，全仓扫描确认无第二处）。
  - **新增 `.gitattributes`（`* -text`）**：关闭 EOL 转换。原因：本机全局 `core.autocrlf = true`，而仓库行尾**本就混杂**（`README.md` / `CHANGELOG.md` 为 CRLF，`.gitignore` / `scripts/*.py` / `docs/*.md` 为 LF）→ 若不声明，checkout 时会改写字节。**已验证 9/9 代表文件的工作区哈希与库内 blob 哈希逐字节一致**。
  - **已知遗留（未同时解决，如实记录）**：仓库含 **89 MB** 原始实验数据，其中 `experiments/v2/raw/corpora_v2/corpus_100000.jsonl` 单文件 **54.6 MB**（由 `scripts/v2_synth_corpus.py` 生成，可再生成）。是否改用 Git LFS 或移出版本控制，留待决策。
  - 未纳入版本控制（按 `.gitignore`）：`.venv/`（968 MB）、`env/cloud.json`、`**/__pycache__/`。

### 文档

- 新增 `reports/p0-report-regression-suite-2026-10-06.md`；`docs/prj-ledger-known-issues.md` 新增 **ISS-030**；`reports/p0-gate-review.md` §三新增**决策17**；`README.md` 快速开始补 pytest 步骤；`reports/README.md` 登记新报告；`docs/prj-template-experiment-log.md` 的 `code_commit` 补填写说明与基线哈希。

---

## 2026-10-05 — V1 破局路径 H3（负结果）+ H5（云端原生 tools 通道）+ 云端方法论缺陷暴露

> 目标：执行 `plan/p0-design-v1-breakthrough-paths.md` §9.4 的 **H3**（`tools_v5` 补 `aggregation` 描述，针对 H0 暴露的"多工具档 50% 跨 prompt 硬阻塞"）
> 与 **H5**（云端改走原生 function calling 通道，针对 H3 暴露的 `ISS-027`）。两轮均**同日配对照臂**以排除 `ISS-028` 的 provider 漂移。

### 配置

- **新增 `schemas/tools_v5.json`（❌ 实测否决，未采纳）**：= `tools_v4` + **仅扩写 `query_sensor.aggregation.description`**（11 → 281 字符，含 6 个枚举语义 + 选值原则 + 反面示例），**未改动任何 `enum` / `required` / `type` / 结构**（diff 共 23 行，其中 22 行为升版元数据）。生成方式为**文本级定点替换**（非 JSON 往返），以保证 diff 可审计。反面示例**刻意不镜像任何测试用例**。

### 数据

- `experiments/v1/EXP-M02-013`（`tools_v5` + `prompt v1`，20 用例 × repeat 3 = 60 次）
- `experiments/v1/EXP-M02-014`（**同日对照臂**：`tools_v4` + `prompt v1`，逐字同配置，60 次）

### 结论

- ❌ **H3 为负结果**：与同日对照臂相比 **参数校验 75%→25%、多工具 75%→33%、多轮 100%→67%、格式退化 8→15 条、首次成功率 0.80→0.55**；且**目标用例 `v1-007` 仍 0/3**（错误一致：`aggregation` 期望 `max` 实际 `trend`）→ **"补 `aggregation` 描述"无效且有害**，`tools_v5` 标记**未采纳**（保留供审计，同 `tools_v3` / `prompt v3` 惯例）。
- ⚠️ **意外暴露两个方法论级缺陷（本轮最重要产出）**：
  - **`ISS-027` / `R-V1-9`：云端 `response_format: json_schema`（`strict: true`）未被强制** —— 实测返回形态在「数组 / 裸单对象 / **裸 arguments（丢 `name`）**」间漂移，后者无法被 `_normalize_structured_calls` 还原 → 判「格式退化」。10-05 两臂共 **8 / 15 条**，而 09-30 为 **0 条** → **云端"约束解码"名存实亡**，与本地（Ollama `format` 确实生效）**不可同口径比较**。
  - **`ISS-028` / `R-V1-10`：云端 provider 漂移 → 云端路径不可复现** —— **逐字相同配置**在 **2026-09-30** 与 **2026-10-05** 结果显著不同（可解析率 **1.0000→0.8431**、格式退化 **0→8 条**、`v1-001` **3/3→0/3**、`v1-010` **0/3→3/3**）→ **此前所有跨日期云端 delta（如 `EXP-M02-001` vs `EXP-M02-006`）不得作为干净归因**。
- **下一步优先级调整（方法论 > 调参）**：**H5** = 云端改走 **OpenAI 原生 `tools` + `tool_choice="required"`**（`env/cloud.json` 声明 `supports_tools_function_calling: true`）以消除"裸 arguments"漂移；**H6** = 同日重复对照量化**日内**漂移；**H7** = `prj-ledger-version-lock.md` 增设"云端模型不可 digest 化"声明。

### 文档

- 新增 `experiments/v1/EXP-M02-013-014.md`；`schemas/tools_v5.json`（未采纳）
- `docs/prj-ledger-known-issues.md`：新增 **ISS-027 / ISS-028**（收录范围 **ISS-001 – ISS-028**）
- `docs/prj-ledger-risk-register.md`：新增 **R-V1-9 / R-V1-10**（§三.3.2）+ §五.5.2 对照表 + §五.5.3 闭环状态 + 修订记录
- `docs/prj-ledger-version-lock.md`：§三第 10 行（云端 baseline 模型）增补"**云端不可 digest 化 + `response_format` 未强制**"声明
- `reports/p0-gate-review.md` §三：新增**决策13**
- `plan/p0-design-v1-breakthrough-paths.md` §9.4：H3 结果回填 + H5/H6/H7 下一步

### 代码（H5：新增云端原生 function calling 通道）

- `scripts/llm_adapter.py`
  - 新增 `DEFAULT_TOOL_CHOICE = "auto"` 与 `LLMAdapter(tool_choice=...)`；`_chat_openai` 不再硬编码 `"auto"`；`describe()` 增加 `transport` 行。
  - **实测留痕**：`tool_choice="required"` **不被 ModelScope provider 支持** —— HTTP 200 但 `content` 与 `tool_calls` **均为空**（3/3 复现），属**静默降级**；已在常量注释中标记禁用（既会伪装成"格式退化"，若被支持还会强制调用、破坏"应拒绝"判据）。
- `scripts/run_v1.py`
  - 新增 `--transport {auto, response_format, tools}`（**默认 `auto` = 既有行为，零回归**）；`tools` = 云端改走 `tools` + `tool_choice=auto`，不使用 `response_format`。
  - `tool_choice` 与既有 `grammar` **完全对称地**穿线到 `run_group` / `run_step_chain_group`；**`expect_reject` 用例一律回退 `auto`**（否则通道会破坏拒绝判据）。
  - `meta` 记录 `transport` / `tool_choice`；固定参数打印块输出 `transport`。

### 数据（H5）

- `experiments/v1/EXP-M02-015`（`tools_v4` + `prompt v1` + `--transport tools`，60 次）+ 冒烟 11 次

### 结论（H5）

- ✅ **通道层完胜**：参数 JSON 可解析率 **0.8431 → 1.0000**、格式退化 **8 条 → 0 条**、应调用却拒绝 **8 → 0**（60/60 均返回标准 `message.tool_calls`）→ **`ISS-027` / `R-V1-9` 的修复方向确认**。
- ⚠️ **语义层反而更差**：参数值错 **1 → 15 条**、多工具 **75% → 17%**、首次成功率 **0.80 → 0.65**。
- ⚠️ **根因锁定为本轮新发现缺陷**：H5 的 15 条参数值错**全部**落在用例 `notes` **未声明为考点**的可选参数上（`v1-001` `window` — `notes` 明写"缺省按默认 5m 仍可接受"；`v1-002` `top_k`；`v1-007`/`v1-010` `aggregation`）→ **`ISS-029` / `R-V1-11`：判据严格范围超出用例考点声明** → **"参数值正确率"在全部臂上不可单独采信**（`R-V1-7` 预警过的瓶颈，F1–F6 复审漏掉此类）。**未擅自放宽判据**，转 P1（H8）。
- **M0.2 维持 No-Go**（多工具 17%、无效拒绝 67% 未达阈），但 **No-Go 的归因质量提升**。

### 结论（H8：考点声明 ↔ 判据范围核对）

- ✅ **`ISS-029` / `R-V1-11` 确证**（`reports/p0-review-v1-criteria-r4.md`，**零调用**）：`judge_tools.compare_arguments` 的规则是"可选参数**缺省不判错、但显式给出不同值即判错**"，而 **20 用例中 13 条**在**未被 `notes` 声明为考点的可选参数**上被严格比对，涉及 **19 个字段**。**证据最强两条**：`v1-008`（`notes` 明写考点是"同时抽取两个工具的**必填参数**"，判据却在 4 个**可选参数**上严格比对）、`v1-011`（`notes` 明写"**`window` 枚举精确匹配是唯一考点**"，判据却同时比对 `aggregation`）。
- **影响量化（补充分析，不替代官方口径）**：按"仅比考点字段"重判（复用官方判分器，仅过滤 `expected`）—— H5 **0.7000 → 0.8500（+0.15）**、H3 0.5667→0.6500、H0-A 0.8667→0.9167、同日对照臂 **Δ=0**（其失败以格式退化为主）；**`v1-007` 在全部 4 个臂上均由失败翻为通过** → 该用例唯一失败原因是 `aggregation`（非考点字段）→ **H0/H3/H5 三轮"多工具档硬阻塞"的结论，很大一部分建立在该字段上**。
- **自我修正**：上一轮 `EXP-M02-015.md` §三 把 `v1-001` 的 `window` 列为"超出考点"的**首要例证**属**取证不准确** → 已更正为**有据判错**（`notes` 明确讨论 window 且配 `lenient=['5m']` 白名单），`docs/prj-ledger-known-issues.md` 的 `ISS-029` 举证同步修正为以 `v1-008` / `v1-011` 为首。
- **处置路径**：**路径 C 已立即采用**（不改判据，仅单列该类失败、禁止以"参数值正确率"单独作能力结论）；**路径 B（推荐，不改代码，仅补用例 `notes`/`lenient` 元数据）** 与 **路径 A（改 `compare_arguments` 为"仅比考点字段"）** 均**需授权**，且修订后须**重跑全部 V1 实验并升版判据**。
- **未改动任何判据、用例与阈值**（本项为复核报告）。

### 数据（路径 B：处置 `ISS-029`）

- **`evals/v1_cases.jsonl`（唯一改动文件）**：按用户**明确授权**执行**路径 B**，处置 H8 列出的 **19 个字段**：
  - **A. 非考点 → 移出比对（5 处）**：`v1-002` `search_knowledge.top_k`、`v1-005`/`v1-008` `query_sensor.window`、`v1-011`/`v1-013` `query_sensor.aggregation`（均属"输入未指定该参数、不影响任务正确性"）。
  - **B. 多解 → `lenient_param_defaults`（2 处）**：`v1-007` `aggregation` 增 `["trend","avg"]`；`v1-010` `aggregation` 增 `["trend"]`。
  - **C. 考点 → 补 `notes` 留痕（12 处，零行为变化）**。
  - **`scripts/judge_tools.py` 零改动**（最后修改时间仍为 2026-09-30）。
  - 原件归档为 **`evals/v1_cases-pre-2026-10-05.jsonl`**（沿用 `-pre-<date>` 惯例）。
- 校验：用例数 20→20、全部 JSON 可解析、`input`/`type`/`difficulty`/`expect_reject` 零改动、5 处移除**仅删目标键**（其余键值不变）、14 处 `notes` 均为**纯追加**。

### 结论（路径 B 影响量化，离线重判，零云端调用）

- raw 记录**内嵌运行时 `expected`** → 历史结论**不被追溯改写**；重判时替换为新用例集条目，走**同一份**判分器，差异**纯粹**来自元数据。
- **首次成功率**：`EXP-M02-011`(H0-A) **0.90→0.95**、`EXP-M02-012` 0.85→0.90、`EXP-M02-013`(H3) 0.55→0.60、**`EXP-M02-015`(H5) 0.65→0.80**、`EXP-M02-010` 0.80→0.85、对照臂 **Δ=0**。
- **多工具档 `中间区间 50% → Pass 75%`**（H0-A / H0-B / M02-010）；H5 由 `No-Go 17%` → `中间区间 67%`。
- **`v1-007` 在 5/6 个臂上由全败翻为全通过** → **"多工具档 50% 为跨 prompt 硬阻塞"的结论至少一半源于判据口径**（该用例唯一失败字段 `aggregation` 此前未被 `notes` 声明为考点）。
- ⚠️ **关键：路径 B 口径下无任何臂在五档全部 Pass → `M0.2` 维持 No-Go**，即本次修订**没有**把门禁"改"成通过。
- ⚠️ 本次**未做任何新云端运行**，上述为**离线重判**（属"若按新用例集运行则会得到"的推断值）；作为正式记录须重跑关键臂。

### 文档（路径 B 补充）

- 新增 `reports/p0-report-v1-cases-revision-2026-10-05.md`；`docs/prj-ledger-known-issues.md` **ISS-029 → 已修复**；`docs/prj-ledger-risk-register.md` **R-V1-11 → 已关闭**（按 §5.1 规则 4 说明根因已消除）+ 修订记录；`reports/p0-gate-review.md` §三新增**决策16**；`reports/README.md` 登记新报告。

### 文档（H5 补充）

- 新增 `experiments/v1/EXP-M02-015.md`；`docs/prj-ledger-known-issues.md` 新增 **ISS-029**（收录范围 → **ISS-001 – ISS-029**）；`docs/prj-ledger-risk-register.md` 新增 **R-V1-11** 并回填 R-V1-9 的处置结果；`reports/p0-gate-review.md` §三新增**决策14**；`plan/p0-design-v1-breakthrough-paths.md` §9.4 回填 H5 并列出 H8/H9。

### 预算

- 2026-10-05 云端调用合计 **191 次**（H3 60 + 同日对照 60 + H5 60 + 通道冒烟 11），未超 `budget_lock.per_day_calls = 220`

---

## 2026-09-30 — V1 判据/用例口径复审收口 + 混合形态实测

> 目标：执行 `docs/p0-decision-model-role.md` §四 处置链遗留项与 V1 判据/用例口径复审（F1–F6），并落地 P6 拆步 / P7 混合形态两条验证路径。

### 代码

- `scripts/llm_adapter.py`
  - **修复 ISS-024（few-shot 恒取 v1）**：`build_messages` 新增 `prompt_path` 参数，令 system 与 few-shot **同源**；
    当 `--prompt` 指向 v2 / step 提示词时不再回退到 `tool_call_prompt_v1.md` 的 3 条 few-shot。
  - **复审 F1**：兼容模型返回的**裸单对象**（非数组）工具调用形态。
- `scripts/run_v1.py`
  - 新增拆步链执行（`run_step_chain_group`）与 `--prompt-step`；三处 `build_messages` 调用显式传 `adapter.prompt_path`。
- `scripts/judge_tools.py`
  - **复审 F4**：`_query_semantic_match` 增关键概念覆盖判定。
  - **复审 F5**：`v1-018` 的 `aggregation` 判据放宽为多解。
  - **复审 F6**：`_refs_type_ok` 对齐规格「至少一条引用」。

### 配置

- `schemas/tools_v2.json`（Schema 简化，按纪律 4 升版）、`schemas/tools_v3.json`、`schemas/tools_v4.json`（**复审 F2** 新增测点目录描述）。
- `prompts/tool_call_step_prompt_v1.md`（P6 拆步提示词，新增）；`prompts/tool_call_prompt_v3.md`（F2 四臂重测后 **未采纳**，保留备查）。

### 数据

- `evals/v2_cases.jsonl`（25 条）、`evals/v3_cases.jsonl`（25 条）新增；`evals/v1_cases.jsonl` 口径更新。
- `experiments/v1/`：`EXP-V1-006`（Schema v2 重测，239 条）、`EXP-V1-007` / `EXP-V1-008`、
  `EXP-V1-009` / `EXP-V1-010`（**P6 拆步，ISS-024 修复后新口径**）、
  `EXP-M02-001` ~ `EXP-M02-005`（**P7 混合形态**：云端 27B 单响应编排 + F2 四臂）。

### 结论

- **M0.2 维持 No-Go**。处置链 ①②③④ 全部执行仍 No-Go；复审 F1–F6 重判 11 实验 19 组 + F2 四臂重测后，
  **整体档位无一翻 Pass**；归因修订为「判据口径缺陷 + 任务信息不足 + 模型部分错」混合归因。
- `docs/prj-ledger-known-issues.md` 新增 **ISS-024**（已修复）/ **ISS-025**（云端路径亦 No-Go，已闭环处置）/ **ISS-026**（拒止行为对 prompt 文本敏感且不可迁移）。
- 新增 `reports/p0-review-v1-criteria-r2.md`、`reports/p0-review-v1-criteria-r3.md`（复审终稿）；同步 `docs/p0-spec-gate-criteria.md`、`docs/p0-decision-model-role.md`、`reports/p0-gate-review.md`、`docs/p0-handover-p1.md`、`docs/p0-checklist-daily.md`、`docs/prj-ledger-version-lock.md`、`reports/p0-summary-phase0-2026-09-30.md`、`plan/p0-review-schema-v2.md`、`plan/p0-design-m02-hybrid-form.md`。

### 文件整理与文档同步（本轮）

> 依据：全仓文件清点（208 个真实文件，排除 `.venv`）+ 哈希去重 + 引用路径校验。

- **清理**：删除 `scripts/__pycache__`（8 个 `.pyc`）与 `protos/__pycache__`（可再生的字节码缓存）；删除**空目录** `configs/milvus/`（无任何文档引用）；
  删除**误建目录** `docker/configs/`（其下 `mosquitto.conf/`、`redis.conf/` 为以文件名错误创建的空目录，真实配置在项目根 `configs/`）。
- **修复配置缺陷**：`docker/compose.base.yml` 的 Redis 配置挂载原写作 `./configs/redis.conf`（相对 compose 文件位于 `docker/`，解析为 `docker/configs/redis.conf` —— 即上述空目录），
  与同一文件中 Mosquitto 的 `../configs/mosquitto.conf` 口径不一致，**运行时会挂载空目录导致 `redis-server` 读不到配置**；
  已统一改为 `../configs/redis.conf`，`docker compose config` 实测解析为 `<REPO>\configs\redis.conf`。
- **修正命名**：`experiments/v1/detail-EXP-V1-006.jsonl` → **`detail-EXP-V1-006.csv`**（内容实为 CSV，与同目录其余 10 个 `.csv` 一致）；同步修正 `reports/p0-report-v1-tool-call.md` 的引用。
- **移除冗余**：删除 `experiments/v1/summary-EXP-V1-004-tiered.csv`（**零文档引用**且与 `summary-EXP-V1-004.csv` **字节相同**；SHA256 = `AD487E57…0B2BA`，可用 `judge_tools.py` 再生）。
  - **保留不删**：`summary-normalize.csv` / `detail-normalize.csv` —— 二者与 EXP-V1-004 的乘积相同**正是 EXP-V1-NORM「uplift = 0」结论的举证**，被 `experiments/v1/EXP-V1-NORM.md` 引用，属证据而非冗余。
- **文档同步**：`README.md`（目录结构块补全 + 脚本数 16→18 + 自检 10→12 + 常用入口补 R-4 命令）；`reports/README.md`（报告索引补 5 份 + 目录范式 + 评测集 3→6 项 + 执行器口径）；
  `docs/prj-ledger-risk-register.md`（**§5.3 闭环状态表严重过期已更正**：原称 ISS-001~013 未闭环、「需换方案」条目为空，与 §二 主表矛盾；并回填 D7/D8 占位行）；
  `docs/prj-ledger-known-issues.md`（ISS-011 / ISS-013 状态列由「🔲 待 D2–D3 填入」更正为「已修复」，消除与页头声明的自相矛盾）。
- **新增**：`reports/p0-audit-status-2026-09-30.md`（整理前后对比 + 变更清单）。

### 方案对比（新增）

- 新增 `plan/p0-design-v1-breakthrough-paths.md`：M0.2 破局路径**全量对比**——判据基线 + 各档现状基线（**参数校验 qwen 100% 已 Pass**；单工具 57%/67%、多工具 40% 为仅存短板）+ **9 条已试路径复盘**（①②③④ / P5 `tools_v3` / P6 拆步 / P7 云编排 / F1–F6 重判 / F2 四臂，全部未破局）+ **10 条未试/待决路径**（含**单工具档专项**这一唯一无方案覆盖的缺口）+ 五维对比矩阵 + 推荐执行顺序（口径清零 → 单工具档专项 → 汇总复核，并列出**工程兜底备选**：重试后成功率实测 0.90–1.00）。

### 云端 D1 / D2 实测（M0.2 收口推进）

**背景**：核实发现 `EXP-M02-001`（云端 0.60）使用的是 **`tools_v2`（schema 无测点目录）**，而 F2 采纳的 **`tools_v4` 从未在云端验证** → 原"云端 0.60"系统性低估当前采纳形态。

- **D1 · `EXP-M02-006`**（`Qwen/Qwen3.8-27B` + **`tools_v4`** + `prompt v1`，20 用例 × 1，单变量 = Schema v2→v4）：
  首次成功率 **0.9000（18/20）**，较 `EXP-M02-001` **+30.0pp**；参数值正确率 **0.5882→0.9412**。
  分档：**单工具 100% Pass / 参数校验 100% Pass / 多轮 100% Pass / 多工具 75% Pass**；**无效拒绝 67% No-Go（唯一卡点）**。
  **逐条仅 2 条失败**：`v1-009`（多工具，`direction`）与 **`v1-016`（无效拒绝，幻觉设备号）**。
  → **F2 云端收益（+30pp）与本地四臂（+28.3pp）双向印证**；"云端 0.60"确为**题目缺条件导致的低估**。
- **D2 · `EXP-M02-007`**（同模型、同 `tools_v4`，**唯一变量 = prompt v1→v2**）：
  **拒止假设成立** —— 无效拒绝 **67%→100%**（`4a 应拒绝却调用` 1→**0**，`v1-016` 修复）；
  **但引入 3 处回退**：`v1-004`（单工具）/ `v1-010`（多工具）/ **`v1-019`（多轮，格式退化）** →
  单工具 **100%→83%**、多轮 **100%→67%**，首次成功率 0.8500（净 −1）→ **整体仍 No-Go（卡点换为多轮）**。
  → **`ISS-026`「prompt 文本条件化效应不可迁移」被直接实证**（修好 2 条、弄坏 3 条）。
  → 机制线索：think token 831.8→**878.2** 逼近 `max_tokens=1024` → `v1-019` 判为**截断型格式退化**（`p0-decision-model-role.md` §4.2 列为待实测代价，**本次首次证实**）。
- **配置**：`env/cloud.json` 的 `budget_lock.per_day_calls` **20 → 40**（**调锁**，文档载明动作 `plan/p0-design-m02-hybrid-form.md` §六「超限须先调锁」）；当日累计调用 **40 次**，未超调锁值；原因与依据已写入其 `note`。
- **文档**：新增 `experiments/v1/EXP-M02-006.md` / `EXP-M02-007.md`；`reports/p0-gate-review.md` §三 新增**决策7 / 决策8**；`plan/p0-design-v1-breakthrough-paths.md` §9.4 按实测修正实验顺序（换模型降为条件性 D4，新增 H0/H1/H2 三个可证伪假设实验）。

- **H2 · `EXP-M02-008`**（`prompt v2` + **`max_tokens` 1024→2048**）：首次成功率 0.85→**0.75**，**格式退化条数与可解析率均不变** → **"think 打满 max_tokens 致截断"假设被证否**（经查 `v1-019` 实为「未调用 `generate_report`」）。**撤回 `EXP-M02-007` 的截断判读**。
- **H1 · `EXP-M02-009`**（新增候选 `prompts/tool_call_prompt_v4.md` = v1 + 强化规则 6a + 1 条**齿轮箱越界示例**，**刻意不使用与 `v1-016` 镜像的示例**）：
  首次成功率 **0.8500**、整体 **中间区间**；**`4a 应拒绝却调用`=0、无效拒绝 100%** → **拒止以"非镜像"方式修复**，
  → **证明 `EXP-M02-007` 的拒止修复非答案泄漏，规则强化本身有效**（**修正 D2 的保守怀疑**）。
- **核心发现（四轮横向对照，方向一致、非噪声）**：**`v1` 族提示词**使 `v1-016`（拒止）失败而 `v1-004`/`v1-010`（参数值）通过；**强化族（v2/v4）**反之
  → **两个提示词族系统性互斥** → **本 20 用例集 + 本判据下不存在"单一 prompt 通过全部 5 档"**（`ISS-026` 的深层实证）；
  其中 `v1-009` 四轮为 x/✅/x/✅ → **证实 repeat=1 存在真噪声**。
  机制：`v1-010` 的 `time_range` **1h→24h**（疑似 few-shot `24h` 锚定，同类见 `OBS-F2-3`）；`v1-004` 的 `depth`/`direction` 枚举偏差（**与规格多解性相关**）。
- **下一步（优先级已定）**：① **架构解耦 = 拒止前置门（R-1 职责，本地 qwen）**，工具调用侧保持 `prompt v1` → 可同时取得两侧最优（**须声明为架构层测试、判据适用对象随之变化**）；② **U3 口径清零**（`direction`/`depth` 多解，**零模型成本**）；③ **H0 repeat=3 降噪**（**判 M0.2 前必做**）。
- **配置**：`env/cloud.json` 的 `budget_lock.per_day_calls` **40 → 100**（第二次调锁，原因与依据已写入其 `note`）；当日累计调用 **80 次**，未超调锁值。
- **文档**：新增 `experiments/v1/EXP-M02-008.md` / `EXP-M02-009.md`、`prompts/tool_call_prompt_v4.md`（候选，未采纳）；`reports/p0-gate-review.md` §三 新增**决策9 / 决策10**。

- **复现校验 · `EXP-M02-010`（**关键负向发现**）**：对 `EXP-M02-006` 的配置**逐字复跑**（模型/endpoint/用例集/`tools_v4`/prompt v1/seed 42/temp 0/`num_ctx`/`top_p`/`max_tokens`/repeat 1 全同）—— **首次成功率 0.90 → 0.80（未复现）**，单工具 100%→**83%**、多工具 75%→**50%**；仅**参数校验 4/4、多轮 3/3、无效拒绝 2/3 两轮一致**。
  **5 轮横向对照**（D1_v1 / **R_v1** / D2_v2 / H2 / H1）显示：`v1-001`/`v1-006`/`v1-007`/`v1-009`/`v1-019` **在同一 prompt 下正反均出现 → 噪声**；**`v1-010` 在 `prompt v1` 两次运行中一成功一失败 → 与 prompt 版本无关**；**仅 `v1-016`（拒止）稳健相关**（v1 族 0/2 ❌ / 强化族 3/3 ✅，含 `v4` 非镜像）。
  → **📌 结论撤回与修正**：**撤回**"两个提示词族系统性互斥"（见 `EXP-M02-009.md` §2.1、本文件上一条、`p0-gate-review` 决策10）；**修正** `EXP-M02-006` 的"4/5 档 Pass、唯一卡点 = 拒止"表述。**根因 = `repeat=1` 且每档仅 3–6 例 → 档位不确定度 ±17–33pp**。
  → **`H0（repeat≥3）` 升为最高优先级**：`M0.2` 判定前，须对候选配置各做 **20 用例 × repeat 3 = 60 次**；**在此之前不得宣称任何配置的档位结论**。
- **文档**：新增 `experiments/v1/EXP-M02-010.md`；更正 `EXP-M02-006.md` / `EXP-M02-009.md`（撤回与打折）；`reports/p0-gate-review.md` §三 新增**决策11**。
- **预算**：当日累计云端调用 **100 次 = 调锁后上限**（D1/D2/H2/H1/R 各 20），**当日不可再调**。

- **H0 · `EXP-M02-011` / `EXP-M02-012`（双臂 × `repeat=3`，**决定性实验**）**：各 20 用例 × repeat 3 = 各 60 次。
  **稳定档位**：**`prompt v1`** → 单工具 **18/18=100%** ✅、参数校验 12/12=100% ✅、多轮 9/9=100% ✅、无效拒绝 **7/9=78%** ⚠️、**多工具 6/12=50%** ❌；
  **`prompt v4`** → 单工具 **14/18=78%** ⚠️、参数校验 100% ✅、多轮 100% ✅、无效拒绝 **9/9=100%** ✅、**多工具 6/12=50%** ❌。**双臂均判「中间区间」**。
  → ① **多工具档 50% 两臂完全相同 → 与 prompt 无关的硬阻塞**（稳定失败 = **`v1-007`、`v1-010`，两臂均 0/3**，根因均含 **`aggregation` 语义选值**：模型系统性给 `trend`，期望 `max`/`avg`）；
  → ② **"拒止 ↔ 单工具"互斥在 `repeat=3` 下确认成立（非噪声）**；
  → ③ **参数校验与多轮 100% 稳定**。
  → **修正** `EXP-M02-006` 的"0.90 / 4 档 Pass"（`repeat=3` 下不成立）；**阻塞由"多档不明"收敛为单点**。
  → **根因**：`tools_v4` 的 F2 **只补了 `sensor_ids`，未补 `aggregation` 描述** → 存在**与 F2 同类的"任务信息不足"缺口**。
  → **下一步 H3（推荐）**：拟 `schemas/tools_v5.json` = `tools_v4` + **扩写 `aggregation` 的 `description`**（同 F2 做法，不改 enum/required/结构，判分语义不变）+ `prompt v1`。
- **文档**：新增 `experiments/v1/EXP-M02-011-012.md`；`reports/p0-gate-review.md` §三 新增**决策12**。
- **预算**：**当日累计 220 次 = 调锁后上限**（D1/D2/H2/H1/R 各 20 + H0 双臂各 60），**当日不可再调**。

### 验证

- 12 个 Python 脚本 `--selftest` **12/12 PASS（exit 0）**。
- `compose.base.yml` / `compose.ingest.yml` / `compose.v2.yml` / `base + v4b-iso` 合并渲染的 `config --quiet` **4/4 通过**（`v4b-iso` 为 override 文件，独立运行必失败，属设计）。
- 全仓 JSON / JSONL 解析通过（修复命名后无失败项）。

### 门禁文档一致性同步（同日第二轮）

> 目标：使 P0 门禁相关文档的状态表与实测结论完全一致（原存在"结论已出、状态表未回填"的系统性偏差）。

- `reports/p0-gate-review.md`
  - §三 标题「**空表待填**」→「已回填」；§3.1 当前状态更正为「**已无未闭环中间区间项**」（V4b 已升 Pass、V2/V3 已闭环，仅剩 V1 No-Go）。
  - §四.1 交付物核对 **6 行**「⚠️ 待填 / 待实测」→ **✅ 已实测**（V1 报告 / V2 参数基线表 / V5 报告 / 联合决策 / V4b 资源实测 / `p0-decision-checkpoint.md` §2.1）。
  - §二 V2 判定由「条件 Pass」更正为 **Pass**（压力档 EXP-V2-LOAD 已闭环），同步 §〇 状态声明与 §8.2 可用性判定。
  - §1.3 / §八.1 执行器口径「五个脚本」→ **18 个 Python 脚本（12 个含 `--selftest`）+ 2 个 PowerShell**。
  - §八.1 环境基线版本号笔误 `v1` → **`v2`**；§七.2 缺陷登记「ISS-001~ISS-013」→ **ISS-001~ISS-026**、版本锁定口径更新为「已收敛」。
  - **待裁决清单全部勾销**：§3.3（= 四步）、§5.2（= 6 项）、§6.4（`R-新2`/`R-新3` **经复核无冲突**）、§6.5（= 口径 B）、§6.6 第 3 条（compose 裸 tag **实测已清零**，8 镜像全部 `tag@digest`）。
- `docs/p0-handover-p1.md`
  - §2.6 `prj-ledger-known-issues.md` 收录范围 **ISS-018 → ISS-026**；`p0-spec-scope-mvp` / `p0-spec-gate-criteria` / `p0-checklist-daily` / `prj-ledger-risk-register` / `prj-spec-schema-mapping` 五行「待回填」→ **已回填**。
  - §2.7 报告状态 **v1 / v2 / v3 / v4b / v5** 五行「待实测 / 未执行 / 当前不可执行」→ **已实测回填**（v3 已封板、v4b 已升 Pass）。
  - §三 P0-3「`.wslconfig` 当前未落地」→ **已安装并核验**。
  - §四.1 **L-02 / L-04 / L-06 / L-07 / L-10** 由「阻塞 / 决策未做 / 未执行 / 待定义」→ **已裁决 / 已决 / 已闭环 / 已裁决**。
  - §4.2 **ISS-001 – ISS-008** 由「待 D7 判定」→ 实际结论（**ISS-005 = 需换方案已切 PG**，其余为可规避 / 已修复 / 已裁决）；**ISS-015–018 → ISS-015–023** 并新增 **ISS-024–026** 行。
  - §6.2 阻塞项交接清单与 §6.6 验证项判定（原写「V1/V2/V3/V4b/V5 = **无法判定**」，**与同文件 §5.2 直接矛盾**）已更正；页头状态声明与 §5.3 承接事项同步；修订记录中 **3 条过期占位行**（【待 M0.6 评审】/【待各验证项实测】/【待 L-01/L-03 闭环】）回填为实际完成记录。
- `reports/p0-summary-phase0-2026-09-30.md`：§2.3 待裁决 **D-01 ~ D-04** 的「确认结果」列由空 → **✅ 已裁定**（四步 / 6 项 / 编号无冲突 / 口径 B + 干净机 17.89GB 升 Pass）。
- `docs/p0-decision-model-role.md`：**经复核无需修改** —— 其 §5.3 已使用 `R-新3`，全仓 `R-新2` 仅指 GPU 直通（ISS-008）。

> **红线声明**：本次同步只回填**已由实测得出的结论**，未新增任何未实测数字；`reports/p0-gate-review.md` 与 `docs/p0-handover-p1.md` 的修订记录均**追加**一行，未删除任何历史记录。

---

## 2026-09-29 — 代码与文档一致性审计（全仓）

> 目标：核对函数签名 / 参数说明 / 返回值 / 使用示例 / 配置项 / 环境变量 / 依赖版本与注释、README、API 文档的一致性，并修复代码缺陷。

### 配置

- `configs/decoder_schema_mapping.json`
  - 修正 `boundary_handling.rebirth_conflict` 的 bdSeq 回退动作：由不可落地的 `quality_ok=FALSE`
    改为实际实现 `st_device_status.online=FALSE + reason='rebirth_rollback'`；
    新增 `rebirth_authority` 声明 M6 的 bdSeq 基准取自内存 `DeviceRegistry`。
  - 补全 `device_id_validation`：新增 `applies_to` / `scope_note`，说明解码侧宽松口径与
    工具契约严格口径并存（见 `docs/prj-spec-schema-mapping.md` §6.1）。
- `configs/redis.conf`
  - 补写「网络与安全」段：说明 `bind 127.0.0.1` 的适用形态，并给出 Docker 容器形态的注释化替代块
    （`bind 0.0.0.0` / `protected-mode no`）；新增 `docs/prj-ledger-known-issues.md` **ISS-015** 跟踪。
  - 修正措辞：`maxmemory-policy 带 ttl` → `volatile-* 系列策略`。
- `docker/compose.ingest.yml`
  - 删除代码**不读取**的死环境变量：`SPB_GROUP_ID`、`SPB_EDGE_NODE_ID`、`DECODER_DB_NAME`、
    `DECODER_SUPER_TABLE`（group / edge / 库名 / 超级表名的唯一来源为映射配置文件）。
  - 补齐代码**实际读取**但此前未注入的 `TD_USER` / `TD_PASSWORD`。

### 代码

- `scripts/self_decoder.py`
  - **实现 R-V3-5**：`TopicParser.is_valid_device()` + `handle_bytes` 对 `DBIRTH`/`DDATA`/`DDEATH`
    校验 `device_id`（`NDEATH` 为网关级报文不适用），非法值丢弃并告警，不再进入子表名与 SQL；
    `SqlBuilder` 侧新增标识符白名单常量 `_SAFE_TAG_RE`。
  - **实现配置要求的时间戳优先序**：`metric.timestamp → payload.timestamp → 服务器时间`
    （主表行时间戳仍统一取 payload 级，避免被循环变量污染）。
  - 修正 bdSeq 回退告警文案；删除空操作语句 `column_values`；
    新增 `DeviceRegistry.all()` 公共接口，替换对私有成员 `_devices` 的直接访问；
    `query_last_birth_seq()` 补 docstring 声明「预留未接入」并对标识符做白名单校验。
- `scripts/run_v5.py`
  - **修复 B2 判据失效**：原实现 `compare_payload(before, before)` 自比对导致 B2 恒为真；
    改为取 **resume 前** checkpoint 状态与 resume 后比对。
  - `--checkpointer` 默认值由 `redis` 改为 **`postgres`**（与已定稿的候选 B 路线一致）；
    t5.5–t5.7 运行时显式提示"Redis 侧检查，不随 `--checkpointer` 切换"。
  - `POSTGRES_URL` 端口 `5927` → **`5433`**（ParadeDB 宿主映射实际值）。
  - 注明 B7 没有代码落点（属环境人工判定，执行器不会自动触发）。
- `scripts/run_v2.py`：`--dsn` 默认库名 `postgres` → **`auscult_v2`**（原默认连不到 `kb_chunks`）；
  更新 BGE-M3 维度注释（已实测确认 1024）。
- `scripts/run_v1.py`
  - 修复云端端点 + `--constrain` 误走 Ollama 原生 `/api/chat` 的通道选择缺陷
    （新增 `structured_output=is_cloud and bool(grammar)`）。
  - 回灌口径与判分口径对齐：`match_expected_calls` 补传 `lenient_param_defaults`。
  - 将恒不可达的 `if not grammar` 改为对真实失败模式的处理（文件 / 键 / JSON 错误、无工具分支）。
- `scripts/llm_adapter.py`
  - 修正模块 docstring：`tool_calls` 缺失时**置位标志**而非抛异常；few-shot 条数由提示词文件决定（v1=3 / v2=8）。
  - `ToolCallsMissingError` docstring：标签改为实现实际的 `格式退化`，并注明默认不抛。
  - 修复重复表达式 `data.get("done_reason") or data.get("done_reason")`。
  - `describe()` 分支文案明确区分「云端 response_format」与「Ollama 原生 format」两条通道。
- `scripts/judge_tools.py`
  - docstring 更正多工具判定语义为**多重集精确相等**（原写"完整覆盖"），并登记 **ISS-016**。
  - 更正云端数字口径注释（裸跑 0.60 / 约束解码 0.55，不再统称"上界 0.60"）。
  - 自检输出 `六类失败归类` → **`七类失败归类`**；`--detail-out` 空结果保护（原会 IndexError）。
- `scripts/param_normalizer.py`
  - R2 规则说明与 `_ID_FIELDS` 实际白名单对齐（`device_id` / `sensor_ids` / `start_node` / `device_model`）。
  - 删除恒假条件 `not isinstance("1h5m", str)`，改为可证伪的复合时长断言。
- `scripts/gbnf_grammar.py`：文件名 / 函数名沿用 GBNF 口径但实际载体为 JSON Schema，已在文件头显式声明。
- `scripts/spb_simulator.py`：docstring 补齐第 5 类边界 `ndeath`；DBIRTH 由 QoS0 改为 **QoS1** 并计入 PUBACK 等待。
- `scripts/v3_ingest_direct.py`：修正用法中的脚本名（`ingest_direct.py` → `v3_ingest_direct.py`）与日志前缀；
  删除冗余别名变量。
- `scripts/run_v3_alert.py` / `scripts/verify_query_sensor.py`：SQL 拼接前新增标识符白名单校验
  （列名 / `device_id` / 窗口单位），防注入。
- `scripts/check_ports.ps1`：WSL2 探活由 `sh -c` 改为 `bash -c`
  （`/dev/tcp` 是 bash 专有特性，busybox sh 下会**恒定假阴性**）。
- `scripts/collect_env.ps1`
  - 修复 GPU 段整体失败缺陷：原把 `[ordered]` 字典塞进 `ArrayList` 后按字符串键改写字段，
    PowerShell 会包装为 PSObject 并抛 `property cannot be found` → 整个 GPU 段返回 `null`；
    改为不可变数组 + 末尾一次性构建 `[pscustomobject]`。
  - 补齐 toolchain 版本采集分支：`docker` / `wsl` / `nvidia-smi` 原恒为空串。
- `scripts/run_cloud_baseline.py`：新增 `--selftest`（V1 固定参数 / 20 用例 / 5 工具 / 约束分支 / 落盘编号）；
  固定实验参数改为显式传入；打印实际处理条数；辅助函数更名 `llm_adapter_build` → `build_case_messages`。

### 文档

- `docs/prj-spec-schema-mapping.md`：TDengine 版本 `3.3.6 LTS` → **`3.3.8.0`**；子表命名示例 `d_plant1_PUMPA` → `d_plant1_PUMP-A`；
  补齐 `pump_speed` 行缺失的列类型单元格；R-V3-5 标为**已实现**、R-V3-6 标为**已闭环**；
  标注时间戳优先序已实现、**心跳兜底未实现**（ISS-017）；NDEATH 数据来源改为内存 registry；
  新增 §6.1 「`device_id` 两套校验口径」说明。
- `docs/prj-ledger-known-issues.md`：页头收录范围更正为 ISS-001 – ISS-018；回填 ISS-007（已修复 2026-09-24）、
  ISS-008（已裁决）、ISS-009（已锁定 0.34.2）；修正 ISS-013 规避手段描述；
  **新增 ISS-015（Redis 容器网络）/ ISS-016（多工具指标命名）/ ISS-017（心跳兜底未实现）/
  ISS-018（`env/hardware.json` 停留在 v1 口径）**。
- `docs/p0-spec-scope-mvp.md`、`docs/p0-handover-p1.md`、`plan/Phase 1 详细开发计划…md`：
  工具名 `retrieve_knowledge` → **`search_knowledge`**（与冻结 Schema 一致）。
- `docs/p0-handover-p1.md`、`reports/p0-gate-review.md`：`六类失败归类` → **`七类失败归类`**（与判分器一致）。
- `docs/prj-ledger-version-lock.md`：ParadeDB 宿主端口 `5927` → **`5433`**；真 BM25 状态更新为已闭环；修正修订记录中的采集时间引用。
- `reports/p0-summary-project-2026-09-28.md`：V3 聚合 P95 `10.2 ms` → **`26.2 ms`**（实测）；ParadeDB 端口更正为 5433；
  删除已过期的"尚余裸 tag `eclipse-mosquitto:2`"结论（2026-09-29 已清零）。
- `reports/p0-report-v2-hybrid-retrieval.md`：PostgreSQL 宿主端口更正为最终值 5433；修正笔误 `19630` → `19530`。
- `reports/p0-summary-project-2026-09-29.md`：新增并作为最新全景总结。

### 新增文件

- `README.md`（根）：项目入口、当前状态速览、目录结构、快速开始、迭代纪律。
- `requirements.txt`：Python 依赖锁，版本全部取自 `docs/prj-ledger-version-lock.md` §二.2.7 / 2.8 / 2.9。
- `CHANGELOG.md`：本文件。

### 验证

- 10 个 Python 脚本 `--selftest` 全部通过（exit 0）。
- 4 个 JSON 配置解析通过；`compose.base.yml` / `compose.ingest.yml` / `compose.v2.yml`
  及 `base + v4b-iso` 合并渲染 `config --quiet` 全部通过。
- 用 `judge_tools.py` 对 `EXP-V1-002` / `EXP-V1-005` 重跑判分，核验云端口径：裸跑首次成功率 0.6000、
  约束解码 0.5500（可解析率 0.8824、多工具档 50%），与文档修正后的数字一致。

### 补遗（同日第二轮）

- `docs/prj-ledger-known-issues.md`：回填 §六 复现记录区的 **ISS-009（已锁定 0.34.2）/ ISS-011（已修复，可解析率 1.00）/
  ISS-012（可规避，P1 补测量化档）/ ISS-013（已修复，本地 0 次退化、云端 2 次且已单独归类）**；页头总体状态同步。
- `docs/p0-handover-p1.md`：§2.5 脚本资产清单由 5 个补全为 **15 个**（含 `gbnf_grammar` / `param_normalizer` /
  `run_cloud_baseline` / V2 压力档 / V3 三个验证脚本，并如实标注哪些无 `--selftest`）；§2.6 文档状态由
  "待实测回填"回填为已定稿；ISS-007–013 状态同步并补登 ISS-015–018。
- `docs/p0-spec-scope-mvp.md`：**Must 链 13 项的"当前状态"列**由"框架就绪，实测未执行"回填为按 V1–V5 实测结果
  逐项标注（含 3 项缺口：`p95`/`anomaly` 未实现、业务表与审计日志待 P1）。
- `reports/p0-report-v5-checkpoint.md`：缺陷清单范围更新为 ISS-001 – ISS-018。
- `reports/p0-gate-review.md`、`reports/p0-summary-project-2026-09-28.md`：版本锁定待办口径与已完成整改项同步。

### 补遗（同日第三轮：采集链路 D-1）

**代码**

- `scripts/collect_env.ps1` / `scripts/check_ports.ps1`：**恢复纯 ASCII**。两个 `.ps1` 头部均约定 "ASCII-only on purpose"（PS 5.1 按 ANSI 码页读取无 BOM 的 `.ps1`），此前写入的 UTF-8 中文注释被按 CP936 解码后会吞掉后续换行与花括号，导致 `Unexpected token '}'` 语法错误、脚本完全不可执行。现两文件 nonASCII 字节数 = 0 且 `Parser::ParseFile` 零错误。
- `scripts/collect_env.ps1`（WSL 段）：**修复发行版停止时的永久挂起**。原实现无条件 `wsl -d docker-desktop -- ...`，发行版为 `Stopped` 时 WSL 会尝试启动它并长时间阻塞（实测 >120s 不返回），快照一个字节都写不出。现先解析 `wsl -l -v` 的发行版状态，仅 `Running` 才进入；否则写 `distro_state` 并把 `live_raw` / `gpu_passthrough_in_wsl` 标为 `SKIPPED` 并记 warning。
- `scripts/collect_env.ps1`（写盘段）：**修复 JSON 序列化挂起/OOM**。`wsl.exe` 输出为 UTF-16LE，经单字节码页解码后字符串夹带 `\0` 等控制字符，PS 5.1 的 `ConvertTo-Json` 对其抛 `OutOfMemoryException` 或不返回，整份快照写失败。新增 `Repair-String`（去控制字符与非配对代理项）与 `ConvertTo-JsonSafe`（递归净化对象图），并把写盘改为**按分区序列化**——单个分区失败只置 `null` + 记 warning，不再拖垮整份快照。

**数据 / 事实裁定**

- **主机名裁定（方向与初判相反）**：实测 `hostname` / `%COMPUTERNAME%` / `Win32_ComputerSystem.Name` / DNS **四路一致为 `<WORKSTATION>`**，`<HOST_ALIAS>` 不可解析 → 是 **`env/env-baseline-v2.md` 写错**，`env/hardware.json` 正确。已更正 9 份文档：`env/env-baseline-v2.md`、`env/env-baseline-v1.md`、`docs/prj-ledger-version-lock.md`、`docs/p0-checklist-daily.md`、`reports/daily/D1-status.md`、`reports/p0-summary-project-2026-09-28.md`、`reports/p0-summary-project-2026-09-29.md`、`reports/p0-gate-review.md`（原"待核实"项已裁定）。
- **重采验证（未覆盖原文件）**：修复后 `collect_env.ps1` 实测跑通并产出 14 KB JSON，关键值与基线交叉验证一致——GPU `RTX 4060 Laptop / 8188 MiB / 驱动 616.56 / CC 8.9`、Docker `19.53 GB / NCPU 10`、工具链 `python 3.12.8 / node v24.19.0 / git 2.45.1 / docker 29.6.2 / wsl 2.7.11.0 / nvidia-smi 616.56` 全部有值。**因重采时 `docker-desktop` 发行版为 `Stopped`（WSL live 配额与 GPU 直通会落 `SKIPPED`），未覆盖 `env/hardware.json`**，待发行版 Running 后再重采。

**文档**

- `docs/prj-ledger-known-issues.md`：新增 **ISS-019（发行版 Stopped 导致采集挂起）/ ISS-020（含 NUL 字符串导致 ConvertTo-Json 挂起或 OOM）/ ISS-021（`.ps1` 非 ASCII 注释损坏解析）**；ISS-018 更新为"缺陷已修、快照待刷新"并附交叉验证值；收录范围更新为 ISS-001 – ISS-021。
- `reports/p0-summary-project-2026-09-29.md` 附录 A：新增 C-17（主机名更正）/ C-18（ASCII 约束）/ C-19（WSL 挂起）/ C-20（序列化挂起），并把 D-1 更新为实际进展与阻塞原因。

- `scripts/check_ports.ps1`（WSL2 段）：**修复 WSL2 侧端口探活在 `docker-desktop` 中完全不可用**。busybox `sh` 不支持 `/dev/tcp`（恒报 `free`，假阴性），`bash` 又未安装（`bash: not found`，恒报 `unknown`），因此 T1.3 的"WSL2 侧端口可用性"结论此前**没有有效依据**。改为：先判发行版状态 → 在发行版内执行**一次** `netstat -ltn` → 在 PowerShell 侧解析监听端口集合后逐个比对（12 次 `wsl` 调用降为 1 次）。实测 `distro state: Running`、12 端口逐个判定，且与发行版内实际监听的 5 个端口自洽；登记 **ISS-022**。

**新增编辑纪律**

- **任何 `.ps1` 改动后必须校验非 ASCII 字节数为 0**（`[System.IO.File]::ReadAllBytes($f) | Where-Object { $_ -gt 127 }`），并跑一次 `[System.Management.Automation.Language.Parser]::ParseFile(...)` 确认零解析错误。

### 补遗（同日第四轮：D-1 环境快照重采完成）

**数据**

- **`env/hardware.json` 已重采覆盖**（`collected_at = 2026-09-29T11:49:36+08:00`，**零警告**，15,179 bytes）。重采前后差异：

  | 字段 | 重采前（v1 口径） | 重采后（实测） |
  |---|---|---|
  | `gpu` | `null` | `NVIDIA GeForce RTX 4060 Laptop GPU / 8188 MiB / nv 616.56 / CC 8.9` |
  | `wsl.wslconfig_present` | `false` | `true`（`distro_state = Running`） |
  | `wsl.live_raw` | 无 | `10 \| Mem: 20001 ...`（NCPU 10 / MemTotal ≈20 GB） |
  | `docker.mem_total_gb` / `ncpu` | `15.51` / `20` | `19.53` / `10` |
  | `toolchain.docker/wsl/nvidia-smi` | 空串 | `29.6.2` / `WSL 2.7.11.0` / `616.56` |
  | 编码 | — | **无 BOM** UTF-8，严格 `json.load(encoding='utf-8')` 通过 |

  重采值与 `env/env-baseline-v2.md` **逐项一致**，互为佐证；初采时间实为 `2026-09-23T20:59:50`。
- 旧 v1 快照留档为 `env/hardware-v1-2026-09-23.json`（仅供追溯，不参与引用）。
- 重采时 Ollama 服务未运行，`toolchain.ollama` 记 `UNKNOWN`；**版本仍以锁定的 0.34.2 为准**，不因本次未取到而漂移。

**代码**

- `scripts/collect_env.ps1`（写盘段）：改用 `[System.IO.File]::WriteAllText` + `UTF8Encoding($false)`，避免 PS 5.1 的 `Set-Content -Encoding UTF8` **写入 BOM** 破坏严格 JSON 读取器。
- `scripts/collect_env.ps1`（工具链探针）：过滤 `Warning|could not connect` 行，避免把 `ollama --version` 在服务未运行时的告警文本当成版本号。

**文档**

- `env/env-baseline-v2.md`：新增"重采核验（2026-09-29）"说明块（含重采时间、逐项一致结论、Ollama 未运行说明、旧快照留档位置）。
- `docs/prj-ledger-version-lock.md`：硬件来源更新为"已于 2026-09-29 重采"。
- `docs/prj-ledger-known-issues.md`：**ISS-018 标记为已修复闭环**（附重采前后差异）。
- **采集时间口径更正**：`env/hardware.json` 的初采时间为 `2026-09-23T20:59:50`（原多处误记为 20:51；20:51 是 `env/ports.md` 的 T1.3 端口检查时间，属另一项测量且本身正确）。已更正 `reports/daily/D1-status.md`（2 处）、`docs/p0-handover-p1.md`、`docs/p0-checklist-daily.md`、`reports/p0-report-v1-tool-call.md`、`reports/p0-report-v4b-resources.md`。
- `reports/p0-summary-project-2026-09-29.md` 附录 A：新增 C-22（BOM 写盘 / ollama 探针）、C-23（采集时间口径），D-1 标记完成。

### 补遗（同日第五轮：D-5 汇总表治理 + D-6 矛盾裁决落地）

**代码**

- `scripts/run_v2.py`（`write_summary`）：**由"每次整表覆盖"改为"按 `experiment_id` 合并"**。原实现以 `"w"` 模式重写 `experiments/v2/summary.csv`，只跑单条路线时会把其它路线的已实测结果一并清掉（该文件一度只剩 2 行）。现先读回既有表 → 用本次结果覆盖同 id 行 → 其余保留 → 列集合取并集后重写；既有表损坏时只告警不阻断本次落盘。已用两次不同路线验证"合并保留"与"同 id 幂等更新"。登记 **ISS-023**。

**数据**

- `experiments/v2/summary.csv` **由 2 行还原为 7 行**（用 `raw/EXP-V2-*.jsonl` 首行重建），`recall / mrr / p95` 与 `reports/p0-report-v2-hybrid-retrieval.md` §4.4 **逐项一致**；并修正了残留 `EXP-V2-milvus-hybrid` 行的**延迟口径**（原 mean 158.7872 / p95 110.0240 来自另一次 run，实为 p95 **9.4800**）。无原始文件可还原的 `EXP-V2-pgvector-hybrid-paradedb` 行原样保留（出处为 `experiments/v2/raw/EXP-V2-BM25.md`）。原表留档 `experiments/v2/summary-pre-2026-09-29.csv`。

**文档（D-6 上游矛盾裁决落地）**

- V1 中间区间处置步骤数（2 vs 4）：在 `reports/p0-report-v1-tool-call.md` §7.2 就地标注——本表为"两步加固 + 两步兜底"的精简表述、缺"Schema 简化"一级，权威清单为 `docs/p0-decision-model-role.md` §四 的**四步**；`reports/p0-gate-review.md` 的"待裁决"改为**已裁定闭环**。
- M0.1 通过条件项数（3 vs 6）：在 `plan/p0-plan-detailed-d1-d10.md` §五 的 M0.1 行标注——该行为精简表述，权威为 `reports/daily/D1-status.md` §六 的 **6 项**。
- `docs/prj-ledger-known-issues.md`：新增 **ISS-023**；收录范围更新为 ISS-001 – ISS-023。
- `reports/p0-summary-project-2026-09-29.md` 附录 A：新增 C-24（汇总表覆盖写与还原）、C-25（两处上游矛盾的裁决落地），D-5 标记完成。

---

## 2026-09-28

- **V2 真 BM25 对标闭环**（EXP-V2-BM25）：ParadeDB ngram BM25 sparse `Recall@5` 0.90 vs Milvus 0.92，hybrid 打平 0.91；
  tsvector 路线淘汰（中文 `Recall@5 = 0`）。见 `docs/prj-ledger-version-lock.md` §二.2.8。
- **V2 压力档闭环**（EXP-V2-LOAD）：10 万块 Milvus 查询 P95 5.6 ms / 1.28 GB；pgvector 170.6 ms / 0.33 GB。
  新增 `scripts/v2_synth_corpus.py`、`scripts/v2_load_test.py`。
- **V1 参数归一化纠错否决**（EXP-V1-NORM）：217 条逐条 diff 变化 0 条、**uplift = 0**，该路径关闭。
- **V1 判据分档重校**（`docs/p0-spec-gate-criteria.md` §3.1.1）：多工具为结构性硬限，单独设低线；新增
  `judge_tools.judge_verdict_tiered`。
- **提示词 v2 落地**（`prompts/tool_call_prompt_v2.md`，EXP-V1-004）：few-shot 3 → 8 条 + 拒止专项 + `--constrain`。
- 巡检整改：`docker/compose.v2.yml` ParadeDB 端口 5927 → 5433。

## 2026-09-24

- **V5 checkpoint 全流程完成，M0.4 达成**：T5.1–T5.7 全 Pass。因 **B7**（redis-py ↔ redis-stack 握手被服务端关闭，
  非缺 RediSearch）弃候选 A，采纳 **PostgreSQL checkpointer**。见 `docs/p0-decision-checkpoint.md` §2.1、`reports/p0-report-v5-checkpoint.md`。
- **T1.1 `.wslconfig` 落地并核验**（20 GB / 10 vCPU / swap 8 GB），**ISS-007 闭环**；
  `env/env-baseline-v2.md` v2 发布。
- **ISS-008 裁决**：GPU 直通不可用 → 改走宿主 Ollama（`127.0.0.1:11434`）。
- **TDengine 授权定稿**：OSS 无 taosX / 连接器 → 自研 Sparkplug B 解码器（≈1.9 人日，≤2 天红线内）。

## 2026-09-23

- **T1.6 `schemas/tools_v1.json` 冻结**（5 工具：4 只读在图内 + `generate_report` 写操作图外）。
- T1.2 环境采集（`env/hardware.json`）、T1.3 端口检查（`env/ports.md`，12 端口 11 空闲）、
  T1.7 数据来源盘点、T1.8 实验登记模板落盘。
- M0.1 判定：**条件通过**（`.wslconfig` 与 TDengine 授权两项缺口，后均闭环）。

---

## 版本约定

- **Phase 0 期间不发布语义化版本号**：以日期 + 验证项为变更粒度，权威记录为 `docs/prj-ledger-version-lock.md` 的修订记录表。
- 组件 / 模型版本一律以 **digest** 表述，禁止裸 tag 与 `latest`（纪律 1）；变更即升版环境基线（纪律 2）。
