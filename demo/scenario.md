# Demo 演示脚本（demo/scenario.md）

> **级别**：Phase 6 交付包 · 演示支撑（`M6.3` 输入）
> **最近更新**：2026-10-10
> **对应里程碑**：`D8`（演示脚本：主场景 + 备用场景）
> **口径**：仅**编排既有资产**（语料入库 / seed_users / 既有 REST+Socket 契约 / deploy 栈），
> 不新增功能、不改后端代码；触发输入见 `demo/data/alarms.json`。
> **依赖**：`M6.2` 交付已就绪（`deploy/up.ps1` + `deploy/init.ps1` 跑通，见 `docs/prj-spec-deployment.md`）。

---

## 一、演示前环境就绪（一次）

| 步骤 | 命令 / 说明 | 校验 |
|---|---|---|
| 1 起基建栈 | `.\deploy\up.ps1` | 8 容器 up，7 基建 healthy（nginx 依赖后端） |
| 2 初始化 | `.\deploy\init.ps1`（幂等；PG 迁移 / Milvus 建库 36 行） | `.\deploy\smoke.ps1` 6/6 PASS |
| 3 种子用户 | `.venv\Scripts\python.exe scripts\seed_users.py` | 幂等写入四角色 eng_dev/rev_dev/kb_dev/sys_dev |
| 4 起后端 | `.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000` | `curl http://127.0.0.1:8000/api/health` |
| 5 起前端 | `cd client; pnpm dev`（:3000） | 经 nginx :9763 访问 `http://localhost:9763` |
| 6 登录 | 四角色任一（默认密码 `Auscult#Dev2026`，生产须改密） | RBAC 看板可见 |

> 演示默认只起 ① 后端 ③ 前端；若需展示实时推送，确保前端 `pnpm dev` 已起（Socket.IO :8000 由 nginx WS 透传）。

---

## 二、主场景 S1 —— 离心泵轴承振动诊断闭环（端到端）

**目标**：从一条真实的 `vib_rms` 振动超限告警，走完「告警 → 证据 → 图谱 → 报告 → 高风险审核 → 审计」完整链路。

### 触发输入（`demo/data/alarms.json` → S1）

```
device_id = "PUMP-C-01"  metric = "vib_rms"  value = 6.2  severity = "high"
```

> **2026-10-22 更新**：`device_id` 随编号迁移改为**规范编号** `PUMP-C-01`（原 `C 0泵` 为台账口径，迁移后库里无此设备）；
> `severity` 用 `AlarmEvent` 词表 `high`（非 `alerts` 表的 `critical`，经 `_SEV_PG_MAP` 映射，见 `rehearsal-log.md` §二）。
> 全链已实测跑通并留档：`demo/recording/s1-run-2026-10-22.md`（98.1s，报告 `RPT-dfbf857be97f625e` 定稿）。

### 步骤

| # | 操作 | 预期演示点 |
|---|---|---|
| 1 | POST `/api/diagnose` `{alarm:{device_id:"PUMP-C-01", metric:"vib_rms", value:6.2, severity:"high"}}` | 返回 `thread_id`，`status=running` |
| 2 | 轮询 GET `/api/threads/{thread_id}` 或前端看 `diagnosis:progress` | 节点推进：**parse_alarm → diagnose**（P7 agent 化后，传感器/检索/图谱/工单四类证据在 `diagnose` 内部以工具循环取得，不再各占一个图节点）→ `human_review` → `finalize` |
| 3 | 观察证据 | 检索召回**振动判据 / 离心泵手册 / 轴承磨损故障案例**（Milvus 混检 + 图谱 ≤2 跳；图谱已预置 **105 节点 / 127 关系 / 11 类受控关系**，见 `docs/pitch.md` A1 —— 数据来自合成语料，规模有限） |
| 4 | 等待 `diagnosis:done` | 出结构化报告：结论 + **带出处引用** + 置信度 |
| 5 | 审核 | `risk=high` 命中 → `review:required` → **强制中断**，报告不自动定稿 |
| 6 | 双角色演示 SoD | 提交人审自己 → `E_PERMISSION` 拒绝；换 rev_dev 审 → 通过 |
| 7 | 定稿 + 审计 | 报告置定稿；`audit_logs` append-only 留痕（UPDATE/DELETE 拒） |

### 验收点

- 引用正确率口径：报告引用均指向语料 chunk（`citations` 字段，见 `docs/prj-spec-api.md` §2.4.3）；
- **引用硬校验（2026-10-14 起，2026-10-22 补强）**：① 引用无效（不在本次 evidence 的 chunk_id 集合内）→ `E_INVALID_CITATION`；② **零引用**（根因/建议都没给引用）→ `E_NO_CITATION`。两者都**不产出 `report_id`**、报告不落库，thread 带 `degrade_reason=invalid_citation_blocked`。降级/拒答路径不受 ② 限制。**演示若遇此态属"正确地拒绝"，不可绕过**；
- 高风险覆盖率 100%：`risk=high` 必进审核（五档路由第 4 档，`docs/prj-design-architecture.md` §5.1）；
- 职责分离：提交人不得自审（ISS-039 旁证：`validate_submitter`，`docs/prj-spec-data-dictionary.md`）；
- **时序数据降级（预期内）**：`deploy/up.ps1` 自 2026-10-14 起默认启用 TDengine，`init.ps1` 会建 `iot` 库与 3 个超级表；但**时序样本数据不在初始化范围内**（需另跑 `scripts/gen_sparkplug.py` + 自研解码器灌入）。未灌数时 `analyze_sensor` 走降级：`sensor_report=null` + `E_TD_TIMEOUT`，报告仍可生成（证据驱动不依赖传感器数据）—— 演示时如需完整传感器分析，须先灌数。
- **实测质量披露（2026-10-22，必读）**：全链跑通的同时，本地 7B 首次跑出**零引用 + 结论含糊**（`citations=[]`、`confidence=0.625`、`query_sensor` 首轮失败）。已核实**不是编号迁移导致**（同参数手动复跑 `PUMP-C-01.vib_rms` / `PUMP-C.vib_rms` / `vib_rms` 三种前缀全部 ok），属模型侧传参/早停（ISS-060）。现场建议：预跑 2 次选优，或切云端后端（`AUSCULT_LLM_BACKEND=cloud`，指标见 `docs/p6-metrics-canonical-2026-10-22.md`）。

---

## 三、备用场景 S2 —— 高风险强制审核 + 审核超时降级

**触发输入**：S2 `{device_id:"PUMP-C-01", metric:"bearing_temp", value:92.0, severity:"critical"}`

| # | 操作 | 预期 |
|---|---|---|
| 1 | 触发 S2 告警 → POST `/api/diagnose` | 轴承温度 92°C > 85（`thr_bearing_temp`）→ high |
| 2 | 等待强制中断 | `review:required`；流程挂起（checkpoint 落盘） |
| 3 | 演示审核锁 | 首个 rev 领取后 `lock:review:{thread_id}` SETNX；第二审单被拒 |
| 4 | 不审 → 演示超时 | 24h 超时自动降级（`resume({action:"timeout"})`），流程不挂死 |
| 4b | （可选）预演通知 | 4h 通知备用审核人事件说明（`check_review_timeout`） |

---

## 四、备用场景 S3 —— 低置信度降级显式化

**触发输入**：S3 `{device_id:"PUMP-C-01", metric:"motor_current", value:16.8, severity:"warning"}`

| # | 操作 | 预期 |
|---|---|---|
| 1 | 触发 S3 → POST `/api/diagnose` | 电流 16.8A > 14.145（`thr_motor_current`）→ medium |
| 2 | 观察结局 | 证据薄弱 → `confidence < 0.50` → **不自动出正式报告** |
| 3 | 验证降级显式化 | 响应含「初步判断，建议人工确认」+ `degrade_reason`（`docs/prj-design-architecture.md` §5.7） |

---

## 五、备用场景 S4 —— 云端兜底不可用降级

**触发输入**：S4 `{device_id:"PUMP-C-01", metric:"vib_rms", value:5.1, severity:"warning"}`

> ⚠️ **2026-10-22 路由调整（Must#9 修复①）**：`vib_rms=5.1 > 4.5` → `risk=high`，而新规则下
> **高风险优先于置信度分流**（`build.py::_route_condition`），因此本场景现在**直接进人工审核**，
> 不再走 `escalate_cloud`。云端兜底改由"参数被拒 ≥2 次 / 步数未收敛"（E2/E5）演示，
> 或临时把告警换成不触发 high 的指标（如 `bearing_temp=82`，阈值 85）。

| # | 操作 | 预期 |
|---|---|---|
| 1 | 触发 S4 | `risk=high` → **直接 `review:required`**（原预期为 `escalate_cloud`，已按新路由修正） |
| 2 | 若要演示云端兜底 | 用 `bearing_temp=82`（medium）或制造参数拒绝 ≥2 次 → `escalate_cloud` |
| 3 | 验证脱敏与预算 | 送云端前 `device_id`→`设备#<sha256[:6]>` 脱敏；`budget:cloud:` 按天计数（340/天） |
| 4 | 云端失败 | 20s 超时/失败 → `degrade_reason="cloud_unavailable"`；**升级后的 high 结论仍会补审**（`_route_after_cloud`） |

> 备用场景为「能力证明」，非每场必演；S3/S4 依赖模型置信度随机性，演示前建议预跑一次确认路径。

---

## 六、数据与留痕（演示后）

| 产物 | 路径 |
|---|---|
| 演示告警输入 | `demo/data/alarms.json` |
| 演示脚本 / 解说词 | `demo/scenario.md` / `docs/pitch.md` |
| 排练记录 | `demo/recording/rehearsal-log.md` |
| 诊断 Trace | `reports/traces/{thread_id}.jsonl` |
| 指标快照 | `reports/metrics/{date}.jsonl` |
| 审计 | `reports/review_audit.jsonl` / `reports/cloud_audit.jsonl` |
| 录屏留档 | `demo/recording/` |

---

> **演示纪律**：演示是「复现既有能力」，不是「演示新功能」；若现场某环节失败，按 `ISS-038–042` 台账口径如实说明、不编造（`docs/prj-ledger-known-issues.md`）。演示结束统一 `.\deploy\down.ps1` 复位。
