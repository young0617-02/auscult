# 云端模型切换后功能验证 · 2026-10-22

> **触发**：所有者更换云端模型（ModelScope `Qwen/Qwen3.8-27B`），要求启动项目并验证全部功能。
> **结论**：**系统可用**，但切换时踩到一个**配置口径坑**（endpoint 必须是完整 URL），修好后全链路通过；
> 另有 4 项**既有遗留**在验证中被暴露（非本次模型切换引入），见 §四。
> **运行态**：API `127.0.0.1:8000`（`AUSCULT_LLM_BACKEND=cloud` + `agent` 形态）· 前端 `:3000` · 网关 `:9763` · 9 容器全 healthy（nginx 依赖宿主后端，起前端后健康）

---

## 一、新模型连通性

| 项 | 结果 |
|---|---|
| provider / model | `openai` 兼容 / **`Qwen/Qwen3.8-27B`** |
| endpoint | `https://api-inference.modelscope.cn/v1/chat/completions` |
| 直连探活（最小 prompt） | **OK，2.8 s**，`prompt=52 / completion=125` tokens，返回 `model=Qwen/Qwen3.8-27B` |
| 额度/鉴权 | 无 429、无 401（`api_key` 39 字符 `ms-3…`，已按 ModelScope 口径） |

---

## 二、⚠️ 切换时的真实故障：endpoint 少写 `/chat/completions` → 诊断静默降级

**现象**：切完模型第一次诊断，1 秒内就 `status=done` 但 `agent_steps=[]`、`confidence=0`，
报告 `RPT-efcb5e100598a493` 内容为空、`degrade_reason=低置信度或重试超限`。

**根因**（报告 payload 里直接写明）：

```json
"errors": [
  {"code": "E_LLM_ERROR", "node": "agent_diagnose", "msg": "LLM HTTP 404: 404 page not found"},
  ... 共 3 条（3 次重试全部 404）
]
```

`app/llm/client.py` 的 `OpenAICompatClient` 契约是 **`endpoint` 传完整 URL（含 `/v1/chat/completions`）**，
它把该值**原样**作为 POST 目标；而新配置填的是 base URL `https://api-inference.modelscope.cn/v1`
（DashScope 那一版填的是完整 URL，所以此前没暴露）→ POST 打到 `/v1` → ModelScope 返回 404 页面。

**处置**：`env/cloud.json` 的 `endpoint` 补成完整 URL（原文件已备份 `env/cloud.json.bak-20261022`），重启 API 后复测通过。

**教训（建议后续硬化）**：这类错误在现象上是"零工具调用 + 低置信度降级"，很容易被误读为模型能力问题（ISS-060 同款表象）。
建议在 `_load_cloud_settings()` 加一条校验：endpoint 不以 `/chat/completions` 结尾时**自动补齐或直接报错**，
不要把它留到运行期变成"3 次 404 + 降级"。本次未改代码，只改配置。

---

## 三、功能验证矩阵（全部在 cloud + agent 形态下）

| # | 功能 | 结果 | 证据 |
|---|---|---|---|
| 1 | 健康检查 / 5 依赖 | ✅ | `code=0`，pg/milvus/neo4j/tdengine/redis 全 `up`，`llm.backend=cloud`、`sanitize_outbound=true`、`cloud_timeout_sec=90` |
| 2 | 鉴权 + 角色 | ✅ | `eng_dev`(engineer) / `rev_dev`(reviewer) 登录 200，`GET /api/auth/me` 200 |
| 3 | 诊断主链（cloud + agent） | ✅ | 3 次真机：`agent_steps` **6–7 步**，工具覆盖 `query_sensor`/`search_knowledge`/`get_maintenance_history`/`query_graph`，`evidence` 5–10 条 |
| 4 | 高风险必审（Must#9） | ✅ | 3 次均 `risk=high → waiting_review`，未直达定稿 |
| 5 | SoD 自审拦截 | ✅ | `eng_dev` 审自己的线程 → **403** |
| 6 | 审核 → 定稿 | ✅ | `rev_dev approved` → `done`，`nodes: parse_alarm → diagnose → human_review → finalize` |
| 7 | 报告可读 | ✅ | 库内中文正常（非控制台乱码）：`PUMP-A-01 振动烈度 7.62 mm/s 超阈值 4.5 mm/s 约 70%…`，`review_status=approved` |
| 8 | 报告列表/详情 | ✅ | `GET /api/reports` 返回 44 条；详情含 `human_review` 决策与风险词命中 |
| 9 | 告警查询 | ✅ | `GET /api/alarms` 200 |
| 10 | 知识库 | ✅ | `GET /api/knowledge/docs` 19 篇（`doc_type=procedure`） |
| 11 | 图谱邻居 | ✅ | `GET /api/graph/neighbors?entity=振动烈度&hops=1` → **7 节点 / 6 边** |
| 12 | 指标端点 | ✅ | `GET /metrics` → **29** 个 `auscult_*` 序列（含 `cloud_budget_used_ratio`） |
| 13 | Socket.IO | ✅ | 握手 `200`，`{"sid":"…","upgrades":["websocket"]}` |
| 14 | 前端页面 | ✅ | `:3000/` 200（14584 B）、`:3000/login` 200（18964 B） |
| 15 | Nginx 网关 + `/api` 反代 | ✅ | `:9763/` 200、`:9763/api/health` 200 |
| 16 | S1 演示全链路 | ✅ | `scripts/run_demo_s1.py` → **116.2 s PASS**，留档 `demo/recording/s1-run-cloudmodel-2026-10-22.md` |
| 17 | 离线单测 | ✅ | `pytest tests/` → **400 passed / 31.7 s**（含本次新增 4 例端点归一锁） |
| 18 | 全量套件（含集成） | ✅ | `pytest` → **566 passed / 0 failed / 98 s**（修复前 534 passed / 28 failed / 20 min） |

**成本**：本次验证消耗云端额度 **24 → 67**（43 次调用，含 3 次诊断 ×6–7 步 + 1 次 404 重试组），日限 340。

**未覆盖（与模型无关，如实标注）**：告警自动触发（`AUSCULT_AUTO_TRIGGER=0`，默认关）、追问 `/api/threads/{id}/ask`、知识库写入/准入（需 `kb_admin`）、报告**驳回**路径、前端点击级交互（只验到 HTTP/SSR 层）。

---

## 四、验证中暴露的既有问题（均与云端模型切换无关）

### 4.1 `pytest` 全量 534 passed / **28 failed**，失败全部集中在 `scripts/` 集成脚本

`tests/`（离线单测）**396/396 全绿**；`scripts/test_*.py` 是打真栈的集成脚本，其失败是**脚本没跟上 2026-10-22 的若干行为变更**：

| 失败簇 | 代表用例 | 归因 |
|---|---|---|
| 时序查询 0 行（`assert 0 > 0`） | `test_d3_analyze_sensor.py::test_query_sensor_real` | 设备号迁移后 TDengine TAG 已是 `PUMP-A-01`，脚本仍查 `PUMP-A` |
| 图谱空命中（`None is not None`） | `test_d3/d4/d6::test_graph_smoke`、`test_d5::test_m31_serial_smoke` | 图谱实体口径为"现象/测点/标准值"，脚本按设备号/工单口径断言（ISS-056 已登记的图谱遗留） |
| 期待 high 直达报告（`应生成 report_id: None`） | `test_d6_diagnose.py:182`、`test_d24_security.py::test_e10_prompt_injection_blocked` | **Must#9 高风险必审**（2026-10-22）后 high 不再直出报告，脚本断言未更新 |
| 密钥扫描失败 | `test_p5_d12_security.py::test_secret_scan`、`test_d24_security.py::test_audit_logging` | 扫描把 `scripts/run_demo_s1.py:45 PASSWORD=Auscult#Dev2026`（种子默认口令）与 `scripts/retrieve_knowledge.py:95 token=unknown…` 判为未知硬编码凭证 —— 白名单未收录 |
| 顺序相关（单跑通过） | `tests/test_agent_diagnosis.py::test_factory_cloud_backend` | 全量跑时被 `scripts/` 用例改动 `os.environ`/客户端缓存污染；`pytest tests/` 单独跑 **通过** |

### 4.2 集成测试直接写生产库

`scripts/test_*.py` 跑一次给 `reports` 表灌入 **8 份测试报告**（`thread_id` 形如 `d20-b4-…`），
`reports` 总数 36 → 44。演示/交接前应清理，或将集成脚本指向独立 schema/库。

### 4.3 `run_demo_s1.py` 相对 `--out` 在最后一步崩（已修）

`write_record()` 用 `out.relative_to(PROJECT_ROOT)`，而 `--out` 传相对路径时 `Path` 未 resolve → `ValueError`，
**链路全跑完却在写留档时崩**（最差的失败位置）。已修为先 `resolve()` 再取相对路径。

### 4.4 质量观察：`citations=0`

3 份报告 `evidence` 5–10 条但 `citations` 均为 0，结论里出现"时序/温度/工单数据全部缺失"的对空降级表述 ——
与 plan §7.2 已披露的 ISS-060 质量边界一致；另外仓库内时序数据止于 **2026-10-21 07:59**，
"最近 1 小时"窗口天然无数据，模型的"数据缺失"判断在事实层面成立。

---

## 五、后续硬化（同日已落地 1–3 项）

| # | 事项 | 状态 | 结果 |
|---|---|---|---|
| 1 | **endpoint 校验硬化** | ✅ 已完成 | `app/llm/client.py` 新增 `_normalize_cloud_endpoint()`：`…/v1`、`…/v1beta`、`…/compatible-mode/v1` 等 base URL 自动补 `/chat/completions` 并记 `WARNING`；形态不明（`…/openai`、`…/v1/messages`）**直接 `RuntimeError`** 并给出可照抄写法；补 4 例回归锁。API 已用新代码重启，`/api/health` 正常 |
| 2 | **集成断言修复** | ✅ 已完成 | 全量 `pytest`：**566 passed / 0 failed（98 s）**；离线 `pytest tests/`：**400 passed（32 s）**。详见 §5.1 |
| 3 | 密钥扫描白名单 | ✅ 已完成 | `run_demo_s1.py` 口令改读 `AUSCULT_SEED_PASSWORD`；`retrieve_knowledge.py` 的 `"unknown"` 哨兵值进白名单 |
| 4 | 集成测试隔离（直写生产库） | ⏳ **未做** | 跑一次仍会向 `reports` 表注入测试报告、并追加 `reports/*.jsonl`、`experiments/v1/raw/*.jsonl` 等**已跟踪**产物（本次已手工 `git checkout --` 还原）。建议独立 schema + 跑后清理 |
| 5 | 配置回滚 | — | `env/cloud.json.bak-20261022` 保留；回滚 DashScope 只需改回完整 endpoint |

### 5.1 断言修复清单（对应 §四.1 的 28 个失败）

| 失败簇 | 根因 | 修法 |
|---|---|---|
| `query_sensor` 0 行（d3/d4/d5/d6/d10） | 设备号已迁规范编号 `PUMP-A-01`，用例仍用 `PUMP-A`；且取首 `ts` 未按设备过滤（可能命中别的设备） | 用例改规范号；取首 ts 的 SQL 补 `WHERE device_id='PUMP-A-01'` |
| `sensor_report is not None`（d3/d4/d5/d6） | 默认 agent 形态图中**没有** `analyze_sensor` 节点，`sensor_report` 必然为空 | 按 `diagnosis_mode()` 分流：deterministic 保留原断言；agent 断言「无 `E_*` 硬错误 + 停在合法终态」 |
| 打桩 `diagnose` 被绕过（d16–d22、d24） | 图里 `diag_impl = agent_diagnose`，只 patch `diagnose` 等于没打桩 → 真调 LLM（慢、非确定） | 这些用例考审核/幂等/trace/指标，与形态无关 → `patch.dict("os.environ", {"AUSCULT_DIAGNOSIS_MODE": "deterministic"})` 固定形态（agent 等价验证在 `tests/test_agent_diagnosis.py`） |
| high 直达报告（d14/d24） | Must#9 后 `risk=high` 必进审核，不再直出报告 | 补 `Command(resume={"action": "approved", ...})` 后再断言报告；d14 另补 `c_002` 证据（云端建议引用了它，缺了会被引用硬校验拦成 blocked） |
| 路由断言（d1/d15） | ①`retry≥3` 在兜底开关开启（默认）时合法走 `escalate_cloud`；②`risk=high` 已前置到 confidence 之前（Must#9 ①） | 用例 `AUSCULT_CLOUD_FALLBACK=0` 隔离变量；`high + conf<0.50` 断言翻转为 `human_review` |
| 预算熔断（d15） | ISS-054「先增后调」后闸门改 `BudgetGuard.reserve()`，旧桩（redis `.get`→999999）失效 → 测试真的打云端 | 桩调整为 `BudgetGuard.reserve()` 返回 `(False, 341, 340, ...)` |
| 共享文件尾行（d24 审计 / p5_d12 工具白名单） | 审计 JSONL 是进程级共享，全量跑时尾行可能属于别的用例 | 改为按本用例标识过滤（`"d24-audit"` / `"delete_all_data"`） |
| 全局注册表精确增量（p5_d06） | Prometheus 注册表进程级共享，`==2.0` 易被其它用例/后台线程干扰 | `==` 改 `>=`（仍能抓「根本没接上」=0 的真回归） |
| 客户端工厂缓存（`test_factory_cloud_backend`） | `get_client` 按 `(backend, model)` 缓存，全量跑时拿到前序用例的旧实例 | 补 `reset_client_cache()` |
