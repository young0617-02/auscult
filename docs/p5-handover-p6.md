# Phase 5 → Phase 6 移交清单

> **日期**：2026-10-10 ｜ **移交方**：Phase 5（评测与硬化） ｜ **接收方**：Phase 6（收敛交付）
> **M5.4 判定**：**达成**——压测达标 + 备份演练 + 停止条件核对（§三 三条全部满足，**停止扩展范围**，转入收敛交付）
> **总体声明**：Phase 5 全部指标基于**模拟数据**（模拟语料 + 本地 7B 生成/判定），为本地验证初步结论，不代表生产级评测；golden 50 题待扩语料后重评。

## 一、M5.x 出口汇总（D1–D15）

| 里程碑 | 出口判据 | 实测结果 | 报告 |
|---|---|---|---|
| **M5.1** 评测硬化 | 全量指标报告 + Kappa 结论 | 十二项指标：8 项达标、1 项未达标（P95 端到端 9248.8ms，处置已记录）、1 项代理口径（引用正确率 0.9861）、κ=**0.8344** ≥0.7；幻觉率 **0.0%**；ECE=0.0（零方差局限已声明） | [p5-eval.md](file:///d:/DSHproject/auscult/reports/p5-eval.md)、[p5-kappa.md](file:///d:/DSHproject/auscult/reports/p5-kappa.md) |
| **M5.2** 可观测 | 指标/日志/告警齐备 + Compose healthcheck | Prometheus 指标 6/6 + Grafana 面板 6/6 + 日志 5/5 + 告警 6/6 + Compose 硬化 5/5 自测全过 | `monitoring/`（alerts.yml + grafana/dashboards）+ `configs/logging.yml` |
| **M5.3** 安全硬化 | 八项安全回归全通过 | 注入 10/10 检出、工具白名单+双轨审计、高风险纯规则 1.4ms、audit_logs append-only（UPDATE/DELETE/TRUNCATE 全拒）、SoD、secret_scan 141 文件、限流 [401,401,401,429]、预算熔断 340 | [p5-security.md](file:///d:/DSHproject/auscult/reports/p5-security.md) |
| **M5.3** 备份演练 | RTO ≤30min / RPO ≤24h | PG RTO 3.1s、Neo4j/Milvus 冷备 16s/5.3s、语料 SHA256 留痕；RPO 持续达成依赖定时备份（P6） | [p5-backup.md](file:///d:/DSHproject/auscult/reports/p5-backup.md) |
| **M5.4** 压测收敛 | 三档压测 + 资源 ≤24GB + 稳定性 | 10/20/50 三档 0% 错误（P95=100/190/940ms）；50 并发 30min：59,593 请求、P95=940ms 零漂移、6×502（0.01%）自愈；宿主峰值 **20.73GB** ≤24GB；限流 4,548 次 429 精确削峰 | [p5-perf.md](file:///d:/DSHproject/auscult/reports/p5-perf.md) |

## 二、§7.1 全量指标终值（Phase 6 验收输入）

| 指标 | 目标 | 终值 | 判定 |
|---|---|---|---|
| Recall@5 | ≥85% | **1.0** | ✅ |
| MRR | ≥0.75 | **0.7986** | ✅ |
| NDCG@5 | 报告值 | 1.0 | — |
| 引用正确率 | ≥90% | 0.9861（context_precision 代理） | ✅* |
| 幻觉率 | ≤10% | **0.0%**（A=10/B=2/C=0） | ✅ |
| 工具调用首次成功率 | ≥90% | **1.0**（12/12） | ✅ |
| P95 检索 | <800ms | **159.4ms**（检索 API 口径 86ms，P2 D11） | ✅ |
| P95 端到端（本地含生成） | <3s | 9,248.8ms（P50=1,539.6ms 达标；瓶颈=生成输出长度，优化路径已列 P6） | ❌ |
| 置信度 ECE | ≤0.10 | 0.0（自评零方差，巧合性校准，无区分度） | ✅* |
| 高风险审核覆盖率 | 100% | 100%（规则强制 always_interrupt_when_high + 纯规则判定） | ✅ |
| Cohen's Kappa | ≥0.7 | **0.8344** | ✅ |
| 资源峰值 | ≤24GB | **20.73GB**（压测全窗口含监控栈+TDengine） | ✅ |

## 三、停止条件核对（plan §7.3 / V5.0 §10.4）

| # | 停止条件 | 核对 | 证据 |
|---|---|---|---|
| 1 | Must 链 13 项端到端可演示（告警→报告→审核一次完整跑通） | ✅ | Phase 4 M4.2/M4.4 真实链路：告警→诊断→证据卡片→报告→审核→追问闭环，E2E 9/9（m41+m42+m43）；M5.1–M5.4 各项回归未破坏 |
| 2 | ≥3 项量化指标达标（Recall@5≥85% + P95 检索<800ms + 工具首次成功率≥90%） | ✅ | 1.0 / 159.4ms / 1.0（12/12），三项同时达标 |
| 3 | 版本锁定清单 + 风险登记册定稿 | ✅ | [prj-ledger-version-lock.md](file:///d:/DSHproject/auscult/docs/prj-ledger-version-lock.md)（10 镜像 digest 锁定，P5 新增 prom/grafana 第 9/10 行）、[prj-ledger-risk-register.md](file:///d:/DSHproject/auscult/docs/prj-ledger-risk-register.md) 持续维护 |

**结论：三条同时满足 → 停止扩展范围，Phase 6 转入收敛交付。**

## 四、移交物（Phase 6 直接输入）

| 类别 | 资产 |
|---|---|
| 评测 | `scripts/eval_ragas.py` + RAGAS/κ/幻觉/端到端四套 RAW+meta（`experiments/p5/w1/`） |
| 可观测 | `monitoring/`（prometheus.yml / alerts.yml / grafana dashboards ×4）+ `configs/logging.yml`；监控栈为临时件（测后已 `down -v` 销毁，复现见 p5-perf.md §八） |
| 运维 | Compose 硬化版（healthcheck+mem_limit）；备份产物基线（`backups/`，不入 git）+ 复现命令 |
| 安全 | `db/migrations/0006_audit_logs.sql` + `app/security/`（pg_audit/rate_limit/sanitizer）+ 八项回归脚本 `scripts/test_p5_d12_security.py` |
| 性能 | `scripts/locustfile.py` + 压测原始数据（`experiments/p5/w5/`：CSV×4 + 资源采样 + 窗口留痕） |
| 台账 | 版本锁（镜像 9/10 行新增）、risk-register、known-issues（ISS 闭环状态） |

## 五、已知边界 / 遗留 P6（按优先级）

1. **P95 端到端（含生成）未达标**（9.2s vs 3s）：优化路径 = 流式输出（首 token 口径）/ max_tokens 收紧 / 结构化输出（实测快 3–5 倍）/ 高频问答缓存；
2. **F-2 数据库访问层**：`psycopg_pool` 连接池替换每请求短连接（压测触发 db.py 预留升级条件，0.01% 瞬时建连失败）+ 读路径路由 `def` 线程池化（u50 排队放大根因）；
3. **F-1 health 探测阻塞**：tdengine down 时同步探测阻塞事件循环（1s/次），改 anyio.to_thread / 缩短超时 / 结果缓存；
4. **RPO 持续化**：每日定时备份任务（Windows 计划任务）+ 产物滚动保留 7 份 + TDengine `taosdump` 演练；
5. **引用正确率严格口径**：RAGAS 代理口径已达标，诊断链路 citations 抽检补测；
6. **ECE 区分度**：生成置信度零方差 → 改 logit 置信度或多采样一致性后再校准；
7. **golden 50 题**：待扩语料后重评全部指标（Phase 2 收口约束延续）；
8. **审计 JSONL 轮转策略**（量级极低暂不阻塞）。

## 六、环境状态（移交时刻）

- 常驻：v2-pg(5433) / redis(6379) / neo4j(7687) / milvus(39530) / nginx(9763)；**tdengine 已停**（Phase 5 基线口径，profile 启用见 p5-perf.md §八）；
  > **milvus 端口口径澄清（2026-10-10，Phase 6 D4 补）**：本行 `39530` **不是笔误**，而是 P5 实测所用**宿主既有实例 `kee-milvus`**（非本项目 compose 起的容器，映射 `19530→39530`）—— `scripts/retrieval_base.py` / `reconcile.py` / `outbox_worker.py` 三处均硬编码 `MILVUS_URI = "http://127.0.0.1:39530"`（注释「kee-milvus 实际映射 19530→39530（P5 修正）」），P5 压测以 `MILVUS_PORT=39530` 覆盖后端默认。
  > 由此**存在三个并存口径**：① `docker/compose.base.yml` = `19530:19530`（本项目 base 栈）；② `docker/compose.v2.yml` = `19531:19530`（本项目 v2 业务栈，即 `app/api/config.py` 默认 `MILVUS_PORT=19531`）；③ `39530` = 宿主既有 `kee-milvus`（P5 实测口径，脚本硬编码）。
  > **对 Phase 6 的影响（已登记 `ISS-042`）**：干净环境一键启动（`M6.2` 判据）只能起本项目 compose 栈（①/②），**脚本硬编码的 39530 将连不上** → 必须在 D6–D7 改为读 `MILVUS_PORT` 环境变量，或由 `deploy/` 显式导出统一端口。
- 监控栈 kee-prometheus/kee-grafana **已销毁**（`down -v`，0 残留）；prom/grafana digest 已锁版本锁 §二.2.1 第 9/10 行；
- uvicorn 压测实例已停；`experiments/p5/w5/` 原始数据保留。
