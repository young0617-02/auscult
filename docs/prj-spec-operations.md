# 运维手册（Operations Guide）

> **层级**：项目级长期有效 ｜ **对应里程碑**：`M6.1`（Phase 6 D3 文档收口） ｜ **状态**：🟢 活动
> **最近更新**：2026-10-10 ｜ **命名依据**：`docs/prj-spec-document-standard.md` §二/§三
> **上游依据**：`README.md` §四/§五/§七 ｜ `plan/Phase 6 详细开发计划（收敛与交付）.md` §四 D3、§5.1 ｜ `docs/p5-handover-p6.md` ｜ `reports/p5-backup.md` ｜ `reports/p5-perf.md` ｜ `env/env-baseline-v2.md`
> **配套文档**：部署手册 `docs/prj-spec-deployment.md`（前置条件 / 首次部署 / 环境变量 / 端口与服务总表）
> **版本纪律**：本文档不抄写组件版本号，唯一事实源 = `docs/prj-ledger-version-lock.md`

---

## 一、日常运维速查

### 1.1 启停与状态命令

| 操作 | 命令 | 备注 |
|---|---|---|
| 起基础组件栈 | `docker compose -f docker/compose.base.yml up -d` | 时序组件另加 `--profile tdengine`（默认不启） |
| 起业务库栈 | `docker compose -f docker/compose.v2.yml up -d` | `auscult_v2`@5433 + v2 Milvus@19531 |
| 起时序接入栈（V3 链路） | `docker compose -f docker/compose.ingest.yml up -d` | ⚠️ 与 base 栈第 3 组端口冲突，**不得同时启** |
| 起后端 | `.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000` | 经 Nginx 回源时绑 `0.0.0.0` |
| 起前端 | `cd client; pnpm dev` | :3000；经 Nginx 的单入口为 :9763。⚠️ dev 跨源放行见 `ISS-043`：Next.js 16 dev 会阻断非白名单来源的 `/_next/hmr`（用 `127.0.0.1` 访问会**页面永不 hydrate 且零报错**，且错误只出现在 Next dev 服务端日志）；`client/next.config.ts` 已配 `allowedDevOrigins: ["127.0.0.1"]`，故本仓 `127.0.0.1` 与 `localhost` **均可用**；**未配置该字段的环境只能用 `localhost`** |
| 起 Nginx（可选） | `docker compose -f docker/compose.nginx.yml up -d` | :9763 |
| 停某一栈（**保卷**） | `docker compose -f <编排文件> down` | 卷保留，见部署手册 §7.3 |
| 停并清卷（⚠️ 危险） | `docker compose -f <编排文件> down -v` | 仅限临时栈销毁或明确重建 |
| 状态总览 | `docker compose -f <编排文件> ps`；`docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"` | 健康检查定义见部署手册 §一 |
| 容器日志 | `docker compose -f docker/compose.ingest.yml logs mosquitto --tail 50` | 换服务名/编排文件同理 |
| 端口复查 | `powershell -File scripts\check_ports.ps1 -ShowOwner` | exit 0 = 无意外冲突 |
| 全量回归（改代码后必跑） | `.venv\Scripts\python.exe -m pytest tests/ -q` | pytest 残留问题见部署手册 §三 步骤 9 |

> 环境预检脚本：`scripts\collect_env.ps1`（硬件/工具链快照 → `env/hardware.json`）、`scripts\check_ports.ps1`（12 个冻结端口）。

### 1.2 日志与留痕位置

| 位置 | 内容 |
|---|---|
| `logs\auscult.log` | 后端应用日志（结构化 JSON，配置 `configs/logging.yml`） |
| `reports/traces/{trace_id}.jsonl` | 诊断 Trace（每行一个 span/llm/tool/event） |
| `reports/metrics/{date}.jsonl` | 指标快照 |
| `reports/security_audit.jsonl` / `reports/review_audit.jsonl` / `reports/cloud_audit.jsonl` | 安全 / 审核 / 云端调用审计 |
| `backups\` | 备份产物（**不入 git**，见 §三） |

> Trace/指标/审计文件清单来源：`docs/p3-handover-p4.md` §1.3。

### 1.3 移交时点常驻口径（参考）

Phase 5 移交时（`docs/p5-handover-p6.md` §六）：常驻 `v2-pg`(5433) / `redis`(6379) / `neo4j`(7687) / `milvus` / `nginx`(9763)；**tdengine 已停**（Phase 5 基线口径，profile 启用见 `reports/p5-perf.md` §八）；监控栈已销毁（`down -v`，0 残留）。
> 其中移交清单记录的 milvus 端口 `39530` **非笔误**，系 P5 实测所用**宿主既有实例 `kee-milvus`**（非本项目 compose 容器，映射 `19530→39530`）；`scripts/retrieval_base.py` / `reconcile.py` / `outbox_worker.py` 三处硬编码 `MILVUS_URI = "http://127.0.0.1:39530"`，P5 以 `MILVUS_PORT=39530` 覆盖后端默认。由此存在**三个并存口径**：① `docker/compose.base.yml`=`19530:19530`；② `docker/compose.v2.yml`=`19531:19530`（`app/api/config.py` 默认 `MILVUS_PORT=19531`）；③ `39530`=宿主既有 `kee-milvus`（P5 实测口径）。**干净环境一键启动只能起本项目 compose 栈（①/②），硬编码 39530 将连不上** → 已登记 `ISS-042`，列为 Phase 6 D6–D7 必做项（三处硬编码改读 `MILVUS_PORT`）。部署时实际连接以部署手册 §一 compose 实测端口为准。

---

## 二、监控与可观测

### 2.1 临时监控栈纪律（最重要）

> ⚠️ **Prometheus / Grafana 为临时栈：仅压测/观测期临时启动、测后立即销毁**（`docker compose -f docker/compose.monitoring.yml down -v`），不并入基础 compose 栈，护 24GB 宿主门禁（V4b 结论，`docker/compose.monitoring.yml` 文件头）。Phase 5 测后已销毁、0 残留（`docs/p5-handover-p6.md` §六）。

启动（镜像必须以 digest 形式经变量注入，禁裸 tag；digest 已锁 `docs/prj-ledger-version-lock.md` §二.2.1 第 9/10 行）：

```powershell
$env:PROMETHEUS_IMAGE = "prom/prometheus@sha256:<digest>"   # digest 获取方式见 docker/compose.monitoring.yml 文件头
$env:GRAFANA_IMAGE    = "grafana/grafana@sha256:<digest>"
docker compose -f docker/compose.monitoring.yml up -d
# 测后销毁（必须）：
docker compose -f docker/compose.monitoring.yml down -v
```

| 项 | 值（compose 实测） |
|---|---|
| Prometheus UI | `http://127.0.0.1:9091`（容器 9090；mem_limit 512m） |
| Grafana | `http://127.0.0.1:3001`（容器 3000；mem_limit 512m；匿名只读 Viewer；管理员密码 `GRAFANA_ADMIN_PASSWORD`，默认 `auscult-dev-grafana`） |
| 面板 | `monitoring/grafana/dashboards` ×4（M5.2 实测 Grafana 面板 6/6 自测过，`docs/p5-handover-p6.md` §一） |
| 告警规则 | `monitoring/alerts.yml`（M5.2 实测告警 6/6） |
| 端口冲突提示 | prometheus 宿主 9091 与 base 栈 milvus metrics(9091) 冲突，与 v2 业务栈(9092) 不冲突 |

> ⚠️ 若在监控栈运行期临时放行，须评估 24GB 门禁余量（§六）；测后**必须** `down -v` 销毁。

### 2.2 应用侧可观测

| 项 | 说明 |
|---|---|
| `/metrics` 端点 | `http://127.0.0.1:8000/metrics`，裸 exposition 格式；按路由模板打点（低基数），`/metrics` 自身不计（`app/api/main.py`） |
| Prometheus 指标 | M5.2 实测 6/6 自测通过（`docs/p5-handover-p6.md` §一 M5.2） |
| 结构化日志 | `configs/logging.yml` + `app/observability/logging_config.py`，落 `logs\auscult.log` |
| Trace / 指标 / 审计 JSONL | 见 §1.2 表 |
| 压测复现 | Locust：`README.md` §七；监控栈随压测的启停与资源采样流程见 `reports/p5-perf.md` §八 |

---

## 三、备份与恢复

### 3.1 目标 vs P5 实测（M5.3 备份演练，2026-10-09，`reports/p5-backup.md`）

| 指标 | 目标（Q6=B 判据） | P5 实测 | 判定 |
|---|---|---|---|
| RTO（恢复时间目标） | ≤30 min | PG：dump 1.0s + restore 2.1s + 校验 ≈ **3.1s**（不含应用重启） | ✅ 余量 >99% |
| Neo4j / Milvus 冷备窗口 | — | **16.0s**（含 stop+start）/ **5.3s** | ✅ |
| RPO（恢复点目标） | ≤24 h（每日备份） | 当前为**手动一次性备份**，「≤24h 持续达成」为**条件性结论** | ⚠️ 依赖每日定时任务落地（见 §3.4） |
| TDengine 备份 | taosdump | **仍未执行**（profile 未启动，无数据可备） | ⏳ **P6 未做 → 转后续路线 P2**：`docs/p6-gate-closure-2026-10-10.md` §四 已**显式接受**、§六 列为 P2「RPO 持续化 + TDengine `taosdump` 演练」；原「待 P6」口径**已随 P6 收口作废** |

### 3.2 备份产物清单（`backups\`，**不入 git**，含业务数据）

| 产物 | 对象 | 完整性验证（实测） |
|---|---|---|
| `auscult_v2_p5_20261009.dump`（4.97 MB） | PG `auscult_v2`（:5433，权威库） | 4 表行数一致：users=4 / reports=26 / work_orders=48 / audit_logs=5；**audit_logs 防篡改触发器 3/3 随恢复保留** |
| `neo4j_data_cold_20261009.tgz`（583 KB） | Neo4j 数据卷冷备（105 节点） | 重启后节点数 105 完好 |
| `milvus_data_cold_20261009.tgz`（70 KB） | Milvus 数据卷冷备（卷含 etcd/minio 全量） | tgz 结构完整 |
| `corpus_checksums_20261009.sha256` | 原始语料（chunks/ 4 文件） | 4/4 文件留痕，可校验篡改 |

### 3.3 复现命令（PowerShell，摘自 `reports/p5-backup.md` §三，按序执行）

```powershell
# ① PG：全量 dump → 恢复临时库 → 行数校验 → 销毁临时库
docker exec auscult-v2-pg pg_dump -U root -d auscult_v2 -Fc -f /tmp/auscult_v2_p5.dump
docker exec auscult-v2-pg createdb -U root auscult_v2_restore
docker exec auscult-v2-pg pg_restore -U root -d auscult_v2_restore --no-owner /tmp/auscult_v2_p5.dump
docker exec auscult-v2-pg psql -U root -d auscult_v2_restore -t -A -F'=' -c "SELECT 'users',count(*) FROM users UNION ALL SELECT 'reports',count(*) FROM reports UNION ALL SELECT 'work_orders',count(*) FROM work_orders UNION ALL SELECT 'audit_logs',count(*) FROM audit_logs"
docker cp auscult-v2-pg:/tmp/auscult_v2_p5.dump backups/auscult_v2_p5_<YYYYMMDD>.dump
docker exec auscult-v2-pg psql -U root -d postgres -c "DROP DATABASE auscult_v2_restore"

# ② Neo4j：停机冷备 → 启动 → 节点数验证（密码见 docker/compose.base.yml NEO4J_AUTH）
docker stop auscult-neo4j
docker run --rm -v auscult-p0_neo4j-data:/data -v <项目>/backups:/backup neo4j:5-community tar czf /backup/neo4j_data_cold_<YYYYMMDD>.tgz -C /data .
docker start auscult-neo4j
docker exec auscult-neo4j cypher-shell -u neo4j -p <pwd> "MATCH (n) RETURN count(n) AS nodes"

# ③ Milvus：停机冷备
docker stop auscult-milvus
docker run --rm -v auscult-p0_milvus-data:/data -v <项目>/backups:/backup alpine tar czf /backup/milvus_data_cold_<YYYYMMDD>.tgz -C /data .
docker start auscult-milvus

# ④ 语料 checksum
Get-ChildItem chunks -File | Get-FileHash -Algorithm SHA256 | Out-File backups/corpus_checksums_<YYYYMMDD>.sha256
```

### 3.4 恢复演练步骤

1. **PG**：按 §3.3 ① 恢复至临时库 → 核对 4 表行数一致 → 销毁临时库（实测 3.1s；`pg_restore` 对 `paradedb`/`tiger`/`topology` 3 个 schema 报非致命 already exists，系 ParadeDB 模板库预置，业务表零影响，可忽略——`reports/p5-backup.md` §四）；
2. **Neo4j / Milvus**：停容器 → 将 tgz **反向解包回同名数据卷** → 起容器 → 按 §3.3 ② 验证节点数/卷结构。⚠️ **口径更正（2026-10-10）**：原【待确认】称「反向解包的具体命令未留档，处置：随 Phase 6 D6–D7 补档至 `deploy/`（恢复脚本 + 本节回填）」—— **该处置未兑现**：`deploy/` 落地的是 `up.ps1` / `init.ps1` / `smoke.ps1` / `down.ps1`，**无恢复脚本**，本节亦未回填 → **转后续路线 P2**（与 §3.5 每日定时备份同批）。
3. **语料**：重算 SHA256 与 `corpus_checksums_*.sha256` 比对。

### 3.5 已知限制与待办（如实标注）

| 项 | 状态 |
|---|---|
| Neo4j 社区版不支持在线 dump（`STOP DATABASE` 报 Unsupported administration command）→ 降级为停机卷 tar 冷备，实测窗口 16s 可接受 | 已定案（`reports/p5-backup.md` §四） |
| **每日定时备份**（Windows 计划任务 + 产物滚动保留 7 份 + TDengine `taosdump` 演练） | ⏳ **P6 未落地 → 转后续路线 P2**：`docs/p6-gate-closure-2026-10-10.md` §四 已**显式接受**（RPO 持续化未落地）、§六 列为 P2 优先级；原「待 P6 落地」口径**已随 P6 收口作废**。故 **RPO≤24h 仍为条件性结论**（当前仅手动一次性备份，见 §3.1） |
| `backups\` 生产化时应转存独立存储介质 | 待办（`reports/p5-backup.md` §四.5） |

---

## 四、故障排查

| # | 症状 | 排查步骤 | 处置 / 结论 |
|---|---|---|---|
| 1 | 容器不健康 | `docker compose -f <编排> ps` 找到 unhealthy 服务 → 对照部署手册 §一 健康检查定义 → `docker compose -f <编排> logs <服务> --tail 50` | **Nginx unhealthy 为已知现象**：healthcheck 探 `/` 而前端重定向 `/login`，反代功能不受影响（`docs/p4-handover-p5.md` §三）；其余服务 unhealthy 按日志定位 |
| 2 | 端口占用 / 起容器报端口冲突 | `powershell -File scripts\check_ports.ps1 -ShowOwner`（exit 1 = 意外冲突，并打印占用进程） | 11434 为 Ollama **预期占用**非冲突；脚本建议的重映射为端口 +10000，若采纳须同步改 `docker/compose.base.yml` 与 `env/ports.md`（脚本内置提示）；base 栈与 ingest 栈的 1883/6030/6041 互斥属设计约束，勿同时启 |
| 3 | Ollama 无响应（诊断/工具调用挂起） | `curl http://127.0.0.1:11434/api/tags`；`ollama ps` 看模型加载；确认宿主 Ollama 进程存活 | Ollama 为宿主原生进程（不在 compose 内），需单独启动；容器访问宿主依赖 `.wslconfig` `networkingMode=mirrored` 或 `host.docker.internal:11434`，mirrored 被关闭时必须回退后者（`env/ports.md` §二） |
| 4 | `/api/health` 数据源探测失败 | 逐一核对 `MILVUS_HOST/PORT`、`NEO4J_*`、`TDENGINE_*`、`REDIS_*`（默认值见部署手册 §4.1） | **MILVUS_PORT 默认 19531 对准 v2 业务栈**；若只启了 base 栈（19530）须设 `MILVUS_PORT=19530`（`app/api/config.py` 注释）；TDengine 未启动属 Phase 5 基线口径（profile 默认不启） |
| 5 | 检索超时 | 先按 #4 排除连接口径错误 → `curl http://127.0.0.1:8000/metrics` 看检索时延 → 对照基线 | 基线：P95 检索 159.4ms（检索 API 口径 86ms，`README.md` §3.2）；显著劣化时查 Milvus 容器资源（mem_limit 4g）与宿主 24GB 门禁余量 |
| 6 | **已知缺陷（P5 遗留，暂不修复）** | 见下方 6a/6b | 缺陷总台账入口 = `docs/prj-ledger-known-issues.md` |

**6a. TDengine 停止时 `/api/health` 阻塞事件循环（P5 遗留 F-1）**
- 现象：tdengine down 时，health 探测同步阻塞事件循环（约 1s/次），影响同进程其他请求（`docs/p5-handover-p6.md` §五.3；修复路径 = anyio.to_thread / 缩短超时 / 结果缓存）。
- **裁定：暂不修复，阻塞演示才修（用户 Q6 裁定）。**
- 临时规避：演示/压测期间避免在 TDengine 停止状态下高频请求 `/api/health`；需要时序链路时先 `--profile tdengine` 启动。

**6b. PG 每请求短连接、高并发排队（P5 遗留 F-2）**
- 现象：`psycopg_pool` 连接池未替换每请求短连接，50 并发压测出现 0.01% 瞬时建连失败与 u50 排队放大（`docs/p5-handover-p6.md` §五.2）。
- **裁定：暂不修复，阻塞演示才修（用户 Q6 裁定）。**
- 临时规避：压测/演示并发控制在内档（P5 实测 10/20/50 三档 0% 错误的上界内）；出现建连失败时降低并发并重启 uvicorn 进程。

> 其他历史缺陷与遗留（含 P1 项）以 `docs/prj-ledger-known-issues.md` 为唯一台账；改动前同时查 `docs/prj-ledger-risk-register.md`（`README.md` §八.4）。

---

## 五、安全运维

| 项 | 内容 | 来源 |
|---|---|---|
| RBAC 账号 | 种子账号 4 个：`eng_dev` / `rev_dev` / `kb_dev` / `sys_dev`（三角色 + 知识库管理员）；职责分离 = 提交者本人不可审核自己的报告 | `README.md` §4.4、§2.2；`docs/p3-handover-p4.md` §2.2 |
| 审计不可篡改 | `audit_logs`（迁移 `db/migrations/0006_audit_logs.sql`）为 **append-only**：UPDATE/DELETE/TRUNCATE 全拒（M5.3 实测）；备份恢复后触发器 3/3 保留 | `docs/p5-handover-p6.md` §一 M5.3；`reports/p5-backup.md` §一 |
| 云端配置 | `env/cloud.json` 含 API key，**已被 `.gitignore` 排除不入库**；属不可改写区不读写内容 | `docs/prj-spec-document-standard.md` §五 |
| 云端预算 | **340 次/天**（`CLOUD_BUDGET_LIMIT` / `cloud.json` `budget_daily_limit`）；预算熔断 340 实测通过（M5.3） | `app/api/config.py`；`docs/p5-handover-p6.md` §一 M5.3 |
| JWT 密钥 | `JWT_SECRET` 默认值仅限本机开发（启动打警告），**任何外部环境必须环境变量注入** | `app/api/config.py` |
| 接口限流 | 令牌桶限流，超限返回 429（P5 压测 4,548 次 429 精确削峰） | `app/api/main.py`；`docs/p5-handover-p6.md` §一 M5.4 |
| 开发默认凭据 | 本机开发栈含默认口令（MinIO `minioadmin`、base PG/Neo4j `auscult_p0_dev`、v2 PG `root/123456`、Grafana `auscult-dev-grafana`）——**仅限本机开发，接外网/多人前必须全部更换** | `docker/compose.*.yml` 实测 |
| 安全回归 | 八项安全回归脚本 `scripts/test_p5_d12_security.py`（注入检出 10/10 等） | `docs/p5-handover-p6.md` §一 M5.3 |

---

## 六、资源门禁

| 门禁 | 值 | 说明 / 指针 |
|---|---|---|
| 宿主内存门禁 | **峰值 ≤24GB**（32GB × 75%） | P5 压测全窗口实测峰值 **20.73GB**（含监控栈 + TDengine，`docs/p5-handover-p6.md` §一 M5.4） |
| WSL2 配额 | 20GB 内存 / 10 vCPU / swap 8GB（`.wslconfig` 已生效） | `env/env-baseline-v2.md` §三、§六 |
| GPU 显存 | **8GB**（RTX 4060 Laptop，8188 MiB）——最硬约束 | 7B Q4 量化 ≈4.7GB；BGE-M3 向量化改走 CPU（ModelScope 本地加载）；`env/env-baseline-v2.md` §四、§8.1.1 |
| 容器内存限额（compose 实测） | base 栈：etcd 1g / minio 1g / milvus 4g / postgres 2g / redis 2g / neo4j 2g（堆 512m–1g + 页缓存 512m）/ mosquitto 256m / tdengine 2g；monitoring 栈：prometheus / grafana 各 512m；ingest 栈：**mem_limit 未定（【待 V4b 仲裁回填】，`docker/compose.ingest.yml` 注释）——处置：随 Phase 6 D6–D7 编排定稿时回填** | `docker/compose.base.yml`、`docker/compose.monitoring.yml` |
| 全启内存预估 | ≈12G（容器侧），须为宿主 Ollama 与向量模型留余量 | `docker/compose.base.yml` 尾注（**预估**，以实测门禁为准） |

> 环境任何项变化（配额/硬件/镜像 digest）即触发环境基线升版并重估门禁：`env/env-baseline-v2.md` §引用纪律。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | 初始建立（Phase 6 D3 文档收口）：日常运维速查、临时监控栈纪律、备份恢复（RTO/RPO 目标 vs P5 实测 + 复现命令）、故障排查（含两项 P5 遗留"暂不修复，阻塞演示才修"裁定）、安全运维、资源门禁 | 新增本文档 |
| 2026-10-10 | 单人（本人） | **Phase 6 收口后过期口径更正（3 处，均为如实降档 / 转后续路线，未把未做项写成已做）**：① §3.1 TDengine 备份「⏳ **待 P6**」→ **P6 未做、转后续路线 P2**（`docs/p6-gate-closure-2026-10-10.md` §四 显式接受、§六 列 P2「RPO 持续化 + TDengine `taosdump` 演练」），原口径随 P6 收口作废；② §3.4 第 2 条原【待确认】称「反向解包的具体命令随 Phase 6 D6–D7 补档至 `deploy/`（恢复脚本 + 本节回填）」—— **如实标注该处置未兑现**：`deploy/` 落地的是 `up.ps1` / `init.ps1` / `smoke.ps1` / `down.ps1`，**无恢复脚本**，本节亦未回填 → 转后续路线 P2；③ §3.5「每日定时备份」由「待 P6 落地」→ **P6 未落地、转后续路线 P2**，并明确 **RPO≤24h 仍为条件性结论**（当前仅手动一次性备份） | §3.1、§3.4、§3.5、修订记录 |
