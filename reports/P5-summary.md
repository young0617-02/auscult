# Phase 5 验收汇总（D15 · M5.4）

> **日期**：2026-10-10 ｜ **阶段**：Phase 5（评测与硬化） ｜ **出口**：M5.4 压测与收敛
> **结论**：**M5.1–M5.4 全部达成**；停止条件三条同时满足 → **停止扩展范围，转入 Phase 6 收敛交付**
> **总声明**：本阶段全部指标基于**模拟数据**（模拟语料 + 本地 7B 生成/判定），为本地验证初步结论，不代表生产级评测；golden 50 题待扩语料后重评。

## 一、里程碑达成

| 里程碑 | 内容 | 判据 | 实测 | 判定 |
|---|---|---|---|---|
| **M5.1** | 评测体系硬化 | 全量指标报告 + Kappa 结论 | 十二项指标 8 达标 / 1 未达标（P95 端到端含生成）/ 1 代理口径；κ=**0.8344**；幻觉率 **0.0%** | ✅ |
| **M5.2** | 可观测与运维 | 指标/日志/告警齐备 + Compose healthcheck | D6 指标 6/6 · D7 面板 6/6 · D8 日志 5/5 · D9 告警 6/6 · D10 Compose 5/5 | ✅ |
| **M5.3** | 安全与权限 | 八项安全回归全通过 + 备份演练 | 安全回归 **8/8**；PG RTO 3.1s / Neo4j 16s / Milvus 5.3s | ✅ |
| **M5.4** | 压测与收敛 | 压测达标 + 备份演练 + 停止条件核对 | 三档 0% 错误、P95=100/190/940ms；30min 稳定性零漂移；宿主峰值 **20.73GB**；停止条件 3/3 | ✅ |

## 二、五项硬化成果

### 2.1 评测硬化（W1 / D1–D5）

| 项 | 口径 | 实测 | 报告 |
|---|---|---|---|
| RAGAS 四指标 | faithfulness / answer relevancy / context precision / context recall | context_precision **0.9861**（引用正确率代理） | [p5-eval.md](file:///d:/DSHproject/auscult/reports/p5-eval.md) |
| 双人标注 κ | Cohen's Kappa ≥0.7 | **0.8344**（第二标注者 = 本地 LLM，同一 labeling-spec） | [p5-kappa.md](file:///d:/DSHproject/auscult/reports/p5-kappa.md) |
| 幻觉率 | 3 级评分（无依据/部分/充分），判据 ≤10% | **0.0%**（A=10 / B=2 / C=0；B 级 2 条根因为语料数值冲突非编造） | [p5-hallucination.md](file:///d:/DSHproject/auscult/reports/p5-hallucination.md) |
| 端到端指标 | P95 检索 / P95 端到端 / 工具首次成功率 / ECE | 检索 **159.4ms** ✅；端到端 **9248.8ms** ❌（P50=1539.6ms ✅）；工具 **1.0**(12/12) ✅；ECE 0.0（零方差局限已声明） | p5-eval.md §三 |

### 2.2 可观测硬化（W2 / D6–D10）

| 天 | 交付 | 自测 |
|---|---|---|
| D6 | Prometheus 指标暴露（节点耗时/置信度分布/升级率/降级率/审核覆盖率/checkpoint key/云端预算） | 6/6 |
| D7 | 抓取配置 + Grafana 面板（**1 个总览看板 12 面板**，覆盖检索/推理/审核/资源四域） | 6/6 |
| D8 | 结构化 JSON 日志 + `trace_id` 贯穿 | 5/5 |
| D9 | 告警规则（Redis 内存 / GPU 显存 / 对账差异 / 审核超时 / 预算超限） | 6/6 |
| D10 | Compose 硬化（全服务 healthcheck + depends_on service_healthy + mem_limit/cpus） | 5/5 |

### 2.3 运维硬化（W3 / D11）

- Compose 全服务 healthcheck + 资源限额；备份恢复演练 **Pass**：[p5-backup.md](file:///d:/DSHproject/auscult/reports/p5-backup.md)
- RTO：PG **3.1s**（dump 1.0s + restore 2.1s + 校验）；Neo4j 冷备 16s（105 节点完好）；Milvus 5.3s；语料 SHA256 留痕
- RPO：演练 Pass；「≤24h 持续达成」依赖每日定时备份任务（挂 P6）

### 2.4 安全与权限硬化（W4 / D12–D13）

八项回归全通过（[p5-security.md](file:///d:/DSHproject/auscult/reports/p5-security.md)）：

| # | 项 | 实测 |
|---|---|---|
| ① | Prompt 注入防御 | 10/10 检出 + 净化 |
| ② | 工具白名单 | 白名单外拒绝 + PG/JSONL 双轨审计 |
| ③ | 高风险确定性判定 | 纯规则 **1.4ms**、可复现、零模型调用 |
| ④ | 审计不可篡改 | `audit_logs` append-only（UPDATE/DELETE/TRUNCATE 全拒） |
| ⑤ | 职责分离 SoD | 提交者不可自审 |
| ⑥ | 凭证扫描 | 141 文件无未知硬编码 |
| ⑦ | 限流熔断 | 端到端 `[401,401,401,429]` + `E_RATE_LIMITED` + `Retry-After` |
| ⑧ | 预算熔断 | 340 次写满 → 强制降级 |

> 期间修复真实 bug：`check_rate_limit` 同步函数被 `await` 调用（TypeError）；5 处硬编码凭证改 `os.environ.get`。

### 2.5 性能硬化（W5 / D14–D15）

[p5-perf.md](file:///d:/DSHproject/auscult/reports/p5-perf.md)：

| 档位 | 请求数 | req/s | 错误率 | P50 | P95 | P99 |
|---|---|---|---|---|---|---|
| u10 | 1,706 | 9.5 | 0% | 24ms | **100ms** | 310ms |
| u20 | 3,349 | 18.6 | 0% | 41ms | **190ms** | 860ms |
| u50 | 5,858 | 32.6 | 0% | 460ms | **940ms** | 2,200ms |
| 50 并发 30min | 59,593 | 33.1 | 0.01%（6×502 自愈） | 480ms | **940ms（零漂移）** | 1,200ms |

- 宿主内存峰值 **20.73GB ≤ 24GB 门禁**；Prometheus `up==1` 验证通过（Q4=B）
- 限流精确削峰：4,548 次 429 / 放行钳制 ~10/分，与令牌桶数学吻合

## 三、§7.1 全量指标终值（12 项）

| # | 指标 | 目标 | 终值 | 判定 |
|---|---|---|---|---|
| 1 | Recall@5 | ≥85% | 1.0 | ✅ |
| 2 | MRR | ≥0.75 | 0.7986 | ✅ |
| 3 | NDCG@5 | 报告值 | 1.0 | — |
| 4 | 引用正确率 | ≥90% | 0.9861（context_precision 代理） | ✅* |
| 5 | 幻觉率 | ≤10% | 0.0% | ✅ |
| 6 | 工具调用首次成功率 | ≥90% | 1.0（12/12） | ✅ |
| 7 | P95 检索 | <800ms | 159.4ms | ✅ |
| 8 | P95 端到端（本地含生成） | <3s | 9,248.8ms | ❌ |
| 9 | 置信度 ECE | ≤0.10 | 0.0（零方差，无区分度） | ✅* |
| 10 | 高风险审核覆盖率 | 100% | 100% | ✅ |
| 11 | Cohen's Kappa | ≥0.7 | 0.8344 | ✅ |
| 12 | 资源峰值 | ≤24GB | 20.73GB | ✅ |

> `*` 代理口径/局限已声明。第 8 项按 §7.2 超限记录，优化路径见 §六。

## 四、交付物清单

### 4.1 核心代码

| 类别 | 文件 |
|---|---|
| 可观测（新增） | `app/observability/prom_metrics.py`、`logging_config.py`；`metrics.py`（改） |
| 安全（新增） | `app/security/pg_audit.py`、`rate_limit.py`；`sanitizer.py`（改） |
| 数据库 | `db/migrations/0006_audit_logs.sql`（audit_logs + 3 append-only 触发器） |
| API/图（改） | `app/api/main.py`、`errors.py`、`runner.py`；`app/report/idempotency.py`；`app/graph/nodes/{analyze_sensor,get_history,retrieve_evidence}.py`；`app/tools/query_sensor.py` |
| 前端（改） | `client/components/common/ConfidenceBreakdown.tsx`、`client/components/features/ReportDetail.tsx`、`client/lib/types/report.ts` |

### 4.2 配置

| 资产 | 说明 |
|---|---|
| `monitoring/prometheus.yml` | 抓取宿主 127.0.0.1:8000 /metrics |
| `monitoring/alerts.yml` | 5 类告警规则 |
| `monitoring/grafana/` | datasources + dashboards 供给 + `auscult-overview.json`（12 面板） |
| `configs/logging.yml` | 结构化 JSON 日志 |
| `docker/compose.monitoring.yml` | 临时监控栈（digest 锚定，测后销毁） |
| `docker/compose.base.yml`（改） | healthcheck + depends_on + mem_limit/cpus |

### 4.3 测试与评测脚本

| 脚本 | 用途 |
|---|---|
| `scripts/eval_ragas.py` / `eval_kappa.py` / `eval_hallucination.py` / `eval_e2e.py` | W1 四项评测 |
| `scripts/test_p5_d06_metrics.py` / `d07_monitoring` / `d08_logging` / `d10_compose` / `d12_security` | W2/W4 自测（6/6+6/6+5/5+5/5+8/8） |
| `scripts/locustfile.py` | W5 压测 |

### 4.4 报告

`reports/p5-eval.md`、`p5-kappa.md`、`p5-hallucination.md`、`p5-backup.md`、`p5-security.md`、`p5-perf.md`、`P5-summary.md`（本文件）+ `docs/handover-p6.md`

### 4.5 实验留痕

`experiments/p5/w1/`（RAW + meta ×4）｜`experiments/p5/w5/`（locust CSV ×4 + 资源采样 5s + 窗口留痕）

## 五、停止条件核对（plan §7.3 / V5.0 §10.4）

| # | 停止条件 | 核对 | 证据 |
|---|---|---|---|
| 1 | Must 链端到端可演示（告警→报告→审核） | ✅ | Phase 4 E2E 9/9（m41+m42+m43）；Phase 5 各项回归未破坏 |
| 2 | ≥3 项量化指标达标（Recall@5 / P95 检索 / 工具首次成功率） | ✅ | 1.0 / 159.4ms / 1.0，三项同时达标 |
| 3 | 版本锁定清单 + 风险登记册定稿 | ✅ | 版本锁（10 镜像 digest，P5 新增 prom/grafana 第 9/10 行）+ risk-register 持续维护 |

**三条同时满足 → 停止扩展范围，Phase 6 转入收敛交付。**

## 六、已知问题（转 P6）

| # | 问题 | 处置方向 |
|---|---|---|
| 1 | P95 端到端（含生成）9.2s > 3s | 流式输出（首 token 口径）/ max_tokens 收紧 / 结构化输出（实测快 3–5 倍）/ 高频问答缓存 |
| 2 | F-2 每请求 PG 短连接 + async 同步 IO（u50 排队放大、0.01% 建连失败） | 切 `psycopg_pool`（依赖已锁定）+ 读路径路由改 `def` 线程池化 |
| 3 | F-1 tdengine down 时 health 同步探测阻塞事件循环（1s/次） | 探测改 `anyio.to_thread` / 缩短超时 / 结果缓存 |
| 4 | RPO 持续化 | 每日定时备份（Windows 计划任务）+ 产物滚动保留 7 份 + TDengine `taosdump` |
| 5 | 引用正确率严格口径 | 诊断链路 citations 抽检补测 |
| 6 | ECE 区分度 | 改 logit 置信度 / 多采样一致性后再校准 |
| 7 | golden 50 题 | 待扩语料后重评全部指标 |
| 8 | 审计 JSONL 轮转策略 | 量级极低，暂不阻塞 |

### 计划偏差登记

| 项 | 计划 | 实际 | 说明 |
|---|---|---|---|
| `reports/p5-ops.md` | W3 运维硬化报告 | 未单独出件 | 内容并入 [p5-backup.md](file:///d:/DSHproject/auscult/reports/p5-backup.md)（备份/RTO/RPO）+ Compose 硬化自测（`test_p5_d10_compose.py` 5/5） |
| Grafana 面板 | 4 个专项（检索/推理/审核/资源） | 1 个总览看板 12 面板 | 四域内容等价，合并组织 |

## 七、环境与复现

- **常驻**：v2-pg(5433) / redis(6379) / neo4j(7687) / milvus(39530) / nginx(9763)；**tdengine 停**（Phase 5 基线口径）
- **后端**：`.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000`（**须设 `MILVUS_PORT=39530`**，配置默认 19531 与实际映射不一致 → 记 P6 环境项）
- **监控栈**：临时件，测后 `docker compose -f docker/compose.monitoring.yml down -v` 销毁；digest 见 [prj-ledger-version-lock.md](file:///d:/DSHproject/auscult/docs/prj-ledger-version-lock.md) §二.2.1 第 9/10 行
- **复现命令**：见 p5-perf.md §八 / p5-backup.md §三 / p5-security.md §三

## 八、Phase 5 技术栈

Python 3.12 + uv ｜ RAGAS ｜ prometheus_client ｜ Locust 2.46.7 ｜ Redis Lua 令牌桶 ｜ PostgreSQL 18 + audit_logs 触发器 ｜ Grafana 11.1.0 / Prometheus（临时栈）

## 修订记录

| 日期 | 修订人 | 内容 |
|---|---|---|
| 2026-10-10 | 单人（本人） | 初始建立：M5.1–M5.4 验收汇总（五项硬化 + 12 项指标终值 + 停止条件核对 + 交付物清单 + 已知问题/计划偏差登记） |