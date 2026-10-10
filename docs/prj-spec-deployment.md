# 部署手册（Deployment Guide）

> **层级**：项目级长期有效 ｜ **对应里程碑**：`M6.1`（Phase 6 D3 文档收口） ｜ **状态**：🟢 活动
> **最近更新**：2026-10-10 ｜ **命名依据**：`docs/prj-spec-document-standard.md` §二/§三
> **上游依据**：`README.md` §四/§五 ｜ `plan/Phase 6 详细开发计划（收敛与交付）.md` §四 D3、§5.1 ｜ `env/env-baseline-v2.md` ｜ `env/ports.md` ｜ `docker/compose.*.yml`（逐文件实测） ｜ `docs/p5-handover-p6.md`
> **配套文档**：运维手册 `docs/prj-spec-operations.md`（日常运维 / 监控 / 备份恢复 / 故障排查）
> **版本纪律**：本文档不抄写组件版本号与镜像 digest，唯一事实源 = `docs/prj-ledger-version-lock.md`

---

## 一、部署形态总览

**形态**：单机 Windows 宿主 + Docker Desktop（WSL2 后端）承载全部容器；LLM 推理走**宿主原生 Ollama**（`127.0.0.1:11434`），容器只承载 DB / 存储（`README.md` §一/§二；裁决依据 `docs/prj-ledger-known-issues.md` ISS-008）。自研 Sparkplug B 解码器亦为**本地 Python 直跑**，不入 compose（`docker/compose.ingest.yml` 文件头变更记录，2026-09-29 方案 A）。

### 1.1 服务与端口总表（从 compose 文件逐项实测）

**`docker/compose.base.yml`**（project：`auscult-p0`，基础组件栈）：

| 服务 | 容器名 | 宿主端口 | 健康检查（healthcheck test 摘要） |
|---|---|---|---|
| etcd | `auscult-etcd` | 无（内网 2379） | `etcdctl endpoint health`（30s） |
| minio | `auscult-minio` | 无（内网 9000/9001） | `curl http://localhost:9000/minio/health/live`（30s） |
| milvus | `auscult-milvus` | **19530**（gRPC）/ **9091**（metrics） | `curl http://localhost:9091/healthz`（30s，start_period 90s） |
| postgres | `auscult-postgres` | **5432**（用户 `auscult`） | `pg_isready -U auscult`（10s） |
| redis | `auscult-redis` | **6379** | `redis-cli ping`（10s） |
| neo4j | `auscult-neo4j` | **7474**（HTTP）/ **7687**（Bolt） | `wget -qO- http://localhost:7474`（30s） |
| mosquitto | `auscult-mosquitto` | **1883**（MQTT）/ **9001**（WebSocket） | `mosquitto_sub -t '$SYS/#' -C 1 -W 3`（30s） |
| tdengine | `auscult-tdengine` | **6030** / **6041** | `taos -s 'show databases'`（30s）；**profile `tdengine`，默认不启** |

**`docker/compose.v2.yml`**（业务库栈：`auscult_v2`@5433 + v2 检索 Milvus）：

| 服务 | 容器名 | 宿主端口 | 健康检查 |
|---|---|---|---|
| etcd | `auscult-v2-etcd` | 无（内网） | `etcdctl endpoint health`（5s） |
| minio | `auscult-v2-minio` | 无（内网） | `curl /minio/health/live`（5s） |
| milvus | `auscult-v2-milvus` | **19531**→容器 19530 / **9092**→容器 9091 | **无 healthcheck**（实测如实记录） |
| pg | `auscult-v2-pg`（ParadeDB 镜像：PG18 + pgvector + pg_search） | **5433**→容器 5432（`root`/`123456`，库 `auscult_v2`） | `pg_isready -U root -d auscult_v2`（5s） |

> 业务栈端口偏移原因：基线 19530/9091/5432 已被宿主其他项目占用，详见 `docker/compose.v2.yml` 文件头注释。后端默认连接口径即本栈（`app/api/config.py`：PG 默认 `5433/auscult_v2`、Milvus 默认 `19531`）。

**`docker/compose.ingest.yml`**（project：`auscult-ingest`，时序两件套）：

| 服务 | 容器名 | 宿主端口 | 健康检查 |
|---|---|---|---|
| mosquitto | `auscult-ingest-mosquitto` | **1883** | 同 base（30s） |
| tdengine | `auscult-ingest-tdengine` | **6030** / **6041** | 同 base（30s） |

> ⚠️ **端口冲突**：本编排与 `compose.base.yml` 第 3 组（mosquitto + tdengine）占用相同端口（1883/6030/6041），**二者不得同时启动**（`docker/compose.ingest.yml` 文件尾警示）。

**`docker/compose.nginx.yml`**（project：`auscult-nginx`，单入口反代，可选）：

| 服务 | 容器名 | 宿主端口 | 健康检查 |
|---|---|---|---|
| nginx | `auscult-nginx` | **9763**→容器 80 | `wget -qO- http://localhost/`；**已知**：报 unhealthy 系前端 `/` 重定向 `/login` 所致，不影响反代功能（`docs/p4-handover-p5.md` §三） |

**`docker/compose.monitoring.yml`**（**临时监控栈**，仅压测期启用）：

| 服务 | 容器名 | 宿主端口 | 健康检查 |
|---|---|---|---|
| prometheus | `kee-prometheus` | **9091**→容器 9090 | `wget --spider http://localhost:9090/-/healthy`（15s） |
| grafana | `kee-grafana` | **3001**→容器 3000 | `wget --spider http://localhost:3000/api/health`（15s） |

> 纪律：仅压测/观测期临时起、测后 `down -v` 销毁，护 24GB 宿主门禁；详见 `docs/prj-spec-operations.md` §二。
> ⚠️ prometheus 宿主端口 9091 与 `compose.base.yml` 的 milvus metrics（9091）冲突；与 v2 业务栈 milvus metrics（9092）不冲突（Phase 5 压测基线即 v2 栈口径，见 `docs/p5-handover-p6.md` §六）。

**宿主原生进程（非容器）**：

| 进程 | 端口 | 健康检查 |
|---|---|---|
| Ollama | **11434**（仅绑 127.0.0.1） | `curl http://127.0.0.1:11434/api/tags` |
| 后端 uvicorn（FastAPI + Socket.IO） | **8000** | `curl http://127.0.0.1:8000/api/health` |
| 前端 Next.js dev server | **3000** | 浏览器访问 / `curl http://127.0.0.1:3000` |
| 自研解码器（按需） | 无监听端口 | `scripts/self_decoder.py --selftest`（`docker/compose.ingest.yml` 尾注） |

另存在 `docker/compose.v4b-iso.yml`：V4b 资源实测用一次性 override（PG→15432、Redis→16379），**非部署路径**，不在本手册展开。

### 1.2 端口基线

冻结基线与复检命令见 `env/ports.md`（2026-09-23 快照，文件头附时点声明）；实测偏移项（19531/9092/5433）见 `docker/compose.v2.yml`。起容器前须重采：`powershell -File scripts\check_ports.ps1 -ShowOwner`。

---

## 二、前置条件

各项实测值与指纹的**唯一事实源** = `env/env-baseline-v2.md`（采集 2026-09-24，重采核验 2026-09-29）。

| 项 | 要求 | 指针 |
|---|---|---|
| OS | Windows 10/11 x64 + WSL2 | `env/env-baseline-v2.md` §一 |
| WSL2 配额 | `.wslconfig`：内存 20GB / 10 vCPU / swap 8GB（未落地前**不得全启**，否则撞 Docker 内存上限） | `env/env-baseline-v2.md` §六；模板 `env/wslconfig.proposed` |
| 物理内存 | 32GB（门禁线 = 峰值 ≤24GB） | `env/env-baseline-v2.md` §三 |
| GPU | 8GB 显存（推理走宿主 Ollama，**不依赖 WSL2 GPU 直通**） | `env/env-baseline-v2.md` §四、§6.2 |
| Python | **3.12**（仓库根 `.python-version` 锚定）+ `uv` | `env/env-baseline-v2.md` §九 |
| Node.js | 24.x + `pnpm` 11.x（`client/package.json` `packageManager` 锚定） | `README.md` §4.1 |
| Ollama | 0.34.2 + 模型 `qwen2.5:7b`、`deepseek-r1:7b`（版本锁定不升级，ISS-009 裁决） | `env/env-baseline-v2.md` §八；`docs/prj-ledger-version-lock.md` |
| Docker | Docker Desktop（引擎 29.6.x / Compose v5.3.x 量级） | `env/env-baseline-v2.md` §七 |
| 磁盘 | 模型根目录与 swap 已规划放 D 盘，避免 C 盘耗尽 | `env/env-baseline-v2.md` §五 |

环境预检命令（幂等，可重复执行）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\collect_env.ps1     # 硬件/工具链快照 → env/hardware.json
powershell -File scripts\check_ports.ps1 -ShowOwner                  # 12 个冻结端口占用检查（exit 0=无意外冲突）
```

---

## 三、首次部署步骤

> 每步附验证命令；全部命令在仓库根目录、PowerShell 下执行。

### 步骤 1：获取代码

```powershell
git clone <仓库地址> <REPO>
cd <REPO>
```

验证：`git log --oneline -1` 能看到最新提交。

### 步骤 2：Python 虚拟环境与依赖

```powershell
uv venv --python 3.12                     # 建 .venv；解释器锚定 = 仓库根 .python-version
uv pip install -r requirements.txt        # 安装/补齐依赖
```

> ⛔ **勿直接 `uv pip sync requirements.txt`** —— sync 不解析传递依赖，会移除大量包（须先用 `uv pip compile` 生成 lock，Phase 6 D6/D7 方案 C 处理）。之后一律用 `.venv\Scripts\python.exe` 运行（`README.md` §4.2）。

验证：`.venv\Scripts\python.exe --version` 输出 3.12.x。

### 步骤 3：Ollama 就绪确认（宿主）

```powershell
ollama --version                          # 应为 0.34.2（锁定值，见 env/env-baseline-v2.md §八）
ollama list                               # 应含 qwen2.5:7b 与 deepseek-r1:7b
curl http://127.0.0.1:11434/api/tags
```

模型 digest 与根目录（`D:\.ollama\models`）见 `env/env-baseline-v2.md` §8.1；BGE-M3 向量模型走 ModelScope 本地加载（§8.1.1），不经 Ollama。

### 步骤 4：启动基础设施（compose 顺序）

**4a. 基础组件栈先行**（内存紧张时可按分组启动策略分批，见 `docker/compose.base.yml` 尾注）：

```powershell
docker compose -f docker/compose.base.yml up -d
# 需要时序链路时追加（默认 profile 不启）：
docker compose -f docker/compose.base.yml --profile tdengine up -d
```

**4b. 业务库栈**（`auscult_v2`@5433 + v2 Milvus@19531 —— 后端与迁移的默认口径）：

```powershell
docker compose -f docker/compose.v2.yml up -d
```

**4c. 时序接入栈（可选，仅 V3 链路需要）**：

```powershell
docker compose -f docker/compose.ingest.yml up -d
```

> ⚠️ `compose.ingest.yml` 与 `compose.base.yml --profile tdengine`（第 3 组 mosquitto + tdengine）**端口冲突，不得同时启动**。

验证：

```powershell
docker compose -f docker/compose.base.yml ps    # etcd/minio/milvus/postgres/redis/neo4j 应 healthy
docker compose -f docker/compose.v2.yml ps      # auscult-v2-pg 应 healthy
powershell -File scripts\check_ports.ps1 -ShowOwner
```

### 步骤 5：数据库初始化（迁移 + RBAC 种子）

在 `auscult_v2`（`127.0.0.1:5433`，`root`/`123456`）按序号执行迁移：`db/migrations/` 现存 **0001_init / 0003_reports / 0004_users / 0005_knowledge_admission / 0006_audit_logs**（**无 0002，编号跳过属仓库现状**）。

```powershell
# RBAC 种子账号（eng_dev / rev_dev / kb_dev / sys_dev），幂等：
.venv\Scripts\python.exe scripts/seed_users.py
```

> ⚠️ **口径更新（2026-10-10，`M6.2` 达成后核）**：原【待确认】为「迁移的单条执行命令未固化」—— 该诉求已由 **`deploy/init.ps1` 一键化覆盖**（实测幂等：PG 迁移 NOTICE 跳过、不中断；见 §八），**但单条迁移命令本身仍未在 `README.md` §4.4 逐条列出**（仍写"按序号执行"）。**如实保留此缺口**，不因一键化而声称已固化；手动排障仍按本节与 `README.md` §4.4 执行。

验证：`seed_users.py` 输出四个种子账号创建/已存在；`docker exec auscult-v2-pg psql -U root -d auscult_v2 -c "\dt"` 能看到业务表。

### 步骤 6：启动后端

```powershell
.venv\Scripts\python.exe -m uvicorn app.api.main:socket_app --host 127.0.0.1 --port 8000
```

- `/socket.io` 由同一 ASGI 应用接管（`app/api/main.py`）；
- 需经 Nginx 容器回源时将 `--host` 改为 `0.0.0.0`（容器经 `host.docker.internal` 回源；`docs/p4-handover-p5.md` §一 D19，含防火墙放行说明）。

验证：`curl http://127.0.0.1:8000/api/health`；`curl http://127.0.0.1:8000/api` 返回统一包络。

### 步骤 7：启动前端

```powershell
cd client
pnpm install
pnpm dev          # http://localhost:3000
```

验证：浏览器打开 `http://localhost:3000` 出现登录页。

### 步骤 8：Nginx 单入口（可选）

```powershell
docker compose -f docker/compose.nginx.yml up -d      # http://127.0.0.1:9763
```

反代规则：`/` → Next.js:3000 ｜ `/api` → FastAPI:8000 ｜ `/socket.io` → WS 透传（`docs/p4-handover-p5.md` §一 D19）。

验证：`curl http://127.0.0.1:9763/api/health` 返回 200。入口建议用 `127.0.0.1`（部分环境 `localhost` 首跳解析异常致超时，`docs/p4-handover-p5.md` §三）。HTTPS/443 为部署期预留，本期仅 HTTP（`docs/p4-handover-p5.md` §三）。

### 步骤 9：离线自检与回归

```powershell
.venv\Scripts\python.exe scripts/llm_adapter.py --selftest
.venv\Scripts\python.exe scripts/gate_rules.py --selftest
.venv\Scripts\python.exe -m pytest tests/ -q
```

- `scripts/` 下 36 个脚本含 `--selftest`，全部应 exit 0（`README.md` §4.8）；
- ⚠️ 已知残留：`pytest` 未登记进 `requirements.txt`，`.venv` 内可能无 pytest，全量回归实跑于宿主 Python 3.12（`docs/prj-ledger-known-issues.md` §五 残留行）。

---

## 四、环境变量与配置

### 4.1 后端环境变量（实测自 `app/api/config.py`，共 14 个；`app/api/main.py` 未新增）

| 变量 | 默认值 | 用途 |
|---|---|---|
| `API_PG_URL` | 无（回退 `LANGGRAPH_PG_URL`，再回退 `postgresql://root:123456@127.0.0.1:5433/auscult_v2`） | API 层 PG 连接串，与 checkpointer 同源 |
| `LANGGRAPH_PG_URL` | 无 | LangGraph PG 连接串；`API_PG_URL` 未设时的回退 |
| `JWT_SECRET` | `<REDACTED_DEV_SECRET>` | JWT 签名密钥；**生产必须环境变量注入**，开发默认值启动时打警告 |
| `JWT_EXPIRE_MINUTES` | `480`（8h，一个班次） | JWT 有效期 |
| `HEALTH_TIMEOUT_S` | `1.0` | `/api/health` 数据源探测超时（秒） |
| `MILVUS_HOST` | `127.0.0.1` | Milvus 地址（health 探测用） |
| `MILVUS_PORT` | `19531`（**v2 业务栈口径**；基线 19530 被占） | Milvus gRPC 端口——**若用 base 栈须设为 19530** |
| `NEO4J_HOST` | `127.0.0.1` | Neo4j 地址 |
| `NEO4J_PORT` | `7687` | Neo4j Bolt 端口 |
| `TDENGINE_HOST` | `127.0.0.1` | TDengine 地址 |
| `TDENGINE_PORT` | `6041` | TDengine REST（taosAdapter）端口 |
| `REDIS_HOST` | `127.0.0.1` | Redis 地址 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `CLOUD_BUDGET_LIMIT` | `340` | 云端调用预算（次/天）；若 `env/cloud.json` 存在且含 `budget_daily_limit` 则被覆盖 |

> JWT 算法 `HS256` 为代码常量，非环境变量。

### 4.2 临时监控栈注入变量（实测自 `docker/compose.monitoring.yml`，共 3 个）

| 变量 | 默认值 | 用途 |
|---|---|---|
| `PROMETHEUS_IMAGE` | 无（`:?` 强制必填） | Prometheus 镜像，**必须 `prom/prometheus@sha256:<digest>` 形式**（禁裸 tag） |
| `GRAFANA_IMAGE` | 无（`:?` 强制必填） | Grafana 镜像，**必须 `grafana/grafana@sha256:<digest>` 形式** |
| `GRAFANA_ADMIN_PASSWORD` | `auscult-dev-grafana` | Grafana 管理员密码（本机开发临时栈） |

### 4.3 配置文件清单

| 文件 | 用途 | 纪律 |
|---|---|---|
| `env/cloud.json` | 云端兜底模型与预算（`budget_daily_limit` 覆盖 `CLOUD_BUDGET_LIMIT`） | **含 API key，已被 `.gitignore` 排除，不入库**；属不可改写区，不读写内容（`docs/prj-spec-document-standard.md` §五） |
| `configs/redis.conf` | Redis 持久化策略（appendonly + noeviction，V5 checkpoint 依赖） | 由 `compose.base.yml` 只读挂载 |
| `configs/mosquitto.conf` | MQTT Broker 配置 | 由 base / ingest 两编排只读挂载 |
| `configs/nginx/nginx.conf` | Nginx 反代规则 | 由 `compose.nginx.yml` 只读挂载 |
| `configs/risk_rules.yml` | 高风险关键词 + 审核策略 | `docs/p3-handover-p4.md` §1.6 |
| `configs/logging.yml` | 结构化 JSON 日志配置 | `docs/p5-handover-p6.md` §一 M5.2 |
| `monitoring/prometheus.yml`、`monitoring/alerts.yml`、`monitoring/grafana/**` | 临时监控栈配置（抓取/告警/面板） | 仅压测期使用 |
| `%UserProfile%\.wslconfig` | WSL2 配额 | 模板 `env/wslconfig.proposed`；回滚见 `env/wslconfig.bak` |

---

## 五、镜像与版本纪律

**纪律**（`README.md` §八.2）：组件/模型只写 digest，**禁止裸 tag 与 `latest`**；变更即升版并重登 digest。版本号与 digest 唯一事实源 = `docs/prj-ledger-version-lock.md`（本表不抄写 digest 值）。

### 5.1 逐镜像 compose 实测状态

| 镜像（repo:tag） | 出现的编排 | digest 锚定 |
|---|---|---|
| `quay.io/coreos/etcd:v3.5.25` | base、v2 | ✅ 已锚定 |
| `minio/minio:RELEASE.2024-12-18T13-15-44Z` | base、v2 | ✅ 已锚定 |
| `milvusdb/milvus:v3.0.0` | base、v2 | ✅ 已锚定 |
| `postgres:18` | base | ✅ 已锚定 |
| `paradedb/paradedb`（digest-only 引用，无 tag） | v2 | ✅ 已锚定 |
| `redis:8` | base | ✅ 已锚定 |
| `neo4j:5-community` | base | ✅ 已锚定 |
| `eclipse-mosquitto:2` | base、ingest | ✅ 已锚定 |
| `tdengine/tsdb:3.3.8.0` | base（profile）、ingest | ✅ 已锚定 |
| `nginx:1.27-alpine` | nginx | ✅ 已锚定 |
| `prom/prometheus`（经变量注入） | monitoring | ✅ 强制合规：`:?` 变量要求 digest 形式，否则拒绝启动 |
| `grafana/grafana`（经变量注入） | monitoring | ✅ 强制合规：同上 |

**实测结论**：仓库 6 份 compose 文件中**未发现裸 tag**；monitoring 栈两镜像采用"环境变量强制 digest 注入"设计，未按 digest 提供时启动即报错。prom/grafana digest 已登记 `docs/prj-ledger-version-lock.md` §二.2.1 第 9/10 行（`docs/p5-handover-p6.md` §六）。

### 5.2 其他版本纪律

- 模型（qwen2.5:7b / deepseek-r1:7b / BGE-M3）digest 见 `env/env-baseline-v2.md` §8.1/§8.1.1 与 `docs/prj-ledger-version-lock.md`；
- Ollama 锁定 0.34.2 不升级（ISS-009 裁决，`docs/prj-ledger-known-issues.md`）；
- `Dockerfile.decoder` 保留（含弃用注释）供审计追溯，不再由 compose 构建（`docker/compose.ingest.yml` 变更记录 2026-09-29）；
- 任一镜像 digest 变化即触发环境基线升版（`env/env-baseline-v2.md` §引用纪律 升版触发条件 1）。

---

## 六、健康检查与启动验证

| 检查对象 | 方式 | 期望 |
|---|---|---|
| 后端进程 | `curl http://127.0.0.1:8000/api/health` | 200（含数据源探测：MILVUS/NEO4J/TDENGINE/REDIS，超时 `HEALTH_TIMEOUT_S`） |
| 后端包络 | `curl http://127.0.0.1:8000/api` | 统一成功包络（`app/api/main.py`） |
| Prometheus 抓取端点 | `curl http://127.0.0.1:8000/metrics` | 裸 exposition 格式（无统一包络） |
| Ollama | `curl http://127.0.0.1:11434/api/tags` | 模型清单返回 |
| 容器健康 | `docker compose -f <编排> ps` | 全部 `healthy`（§一 表；v2 milvus 无 healthcheck，属实测现状） |
| Nginx 链路 | `curl http://127.0.0.1:9763/api/health` | 200（`docs/p4-handover-p5.md` §一 D19 已验证） |
| Nginx 容器标绿 | `docker ps` | 可能显示 unhealthy —— 已知现象（`/` 重定向 `/login`），不影响反代（`docs/p4-handover-p5.md` §三） |

> ⚠️ **已知缺陷影响**：TDengine 停止时 `/api/health` 的同步探测会阻塞事件循环（P5 遗留 F-1，暂不修复）。处置见 `docs/prj-spec-operations.md` §四。

**冒烟基线**：

- 离线自检 + 全量回归：`README.md` §4.8（步骤 9 的三条命令）；
- 端到端 E2E：Playwright 9/9（m41+m42+m43，`docs/p4-handover-p5.md` §一 D20）；
- 一键冒烟脚本 `deploy\smoke.ps1` **待 D6–D7 落地**（见 §八）。

---

## 七、升级与回滚

### 7.1 代码升级流程

```powershell
git pull
uv pip install -r requirements.txt          # 依赖有变时
.venv\Scripts\python.exe -m pytest tests/ -q  # 全量回归必过（防已修复缺陷复发）
# 若 db/migrations/ 有新文件：在 auscult_v2 按序号补执行增量迁移
# 重启后端 uvicorn 进程；前端 pnpm install（如有依赖变更）+ pnpm dev / next build
```

### 7.2 镜像升级流程

1. 在对应 `docker/compose.*.yml` 中将镜像改为新的 `repo:tag@sha256:<digest>`（**禁裸 tag**）；
2. 重登 `docs/prj-ledger-version-lock.md`（变更即升版），并核对 `env/env-baseline-v2.md` 升版触发条件；
3. `docker compose -f <编排> up -d` 滚动替换；
4. 跑 §六 健康检查 + 全量回归。

### 7.3 数据卷纪律

| 编排 | named volumes（实测） |
|---|---|
| `compose.base.yml` | milvus-etcd-data / milvus-minio-data / milvus-data / pg-data / redis-data / neo4j-data / tdengine-data / mosquitto-data（共 8 个） |
| `compose.v2.yml` | etd-data / minio-data / milvus-data / pg-data（共 4 个） |
| `compose.ingest.yml` | tdengine-data / tdengine-log / mosquitto-data（共 3 个） |

- **换镜像不清卷**：`up -d` 替换容器时数据卷原样保留；
- ⚠️ `down -v` 会**删除卷**，仅用于临时栈销毁或明确重建场景；PG18 数据目录挂载点必须为 `/var/lib/postgresql`（`docker/compose.base.yml` 注释，PG18 布局变更）。

### 7.4 回滚

- **代码回滚**：回退到既有 git tag / commit（交付封版点由 Phase 6 D10 确立，`plan/Phase 6 详细开发计划（收敛与交付）.md` §四），重跑 §7.1 流程；
- **镜像回滚**：将 compose 中 digest 回退为 `docs/prj-ledger-version-lock.md` 历史行记录的旧 digest，`up -d`；
- **数据回滚**：涉及已执行迁移或数据损坏时，结合 `backups\` 备份产物恢复（步骤与实测基线见 `docs/prj-spec-operations.md` §三）。

---

## 八、一键启动（✅ 已落地，`M6.2` 达成）

> ✅ **状态声明（2026-10-10 更正）**：`deploy/` 目录**已落地并封版**，本节为**可用交付物的操作说明**。原声明「`deploy\` 目录当前不存在，本章为目标行为定义（规划），不构成可用交付物」**已过期作废**。
> **实测证据**：8 容器 up、7 个基建 healthy、`deploy/smoke.ps1` **6/6 PASS** → **`M6.2` 达成**。

Phase 6 D6–D7 已将本文 §三 的手动步骤固化为交付包（`README.md` §五）：

| 脚本 | 行为（已落地） |
|---|---|
| `deploy\up.ps1` | 一键启动：compose 全服务（healthcheck + 依赖顺序 + 资源限额）+ 等待健康 |
| `deploy\init.ps1` | 一键初始化：迁表 / 建库 / 建图谱 / 导入语料与演示数据（**幂等**，实测 PG 迁移 NOTICE 跳过、不中断）—— 已覆盖 §三 步骤 5 的迁移与种子（该处【待确认】见 §三 的口径更新） |
| `deploy\smoke.ps1` | 一键冒烟：健康检查 + Playwright E2E（F1–F11 子集） |
| `deploy\down.ps1` | 一键停止（可选 `-v` 清卷） |

配套：`deploy/docker-compose.yml`（含 `.env.example`、镜像 **digest** 清单，禁止裸 tag）与 `deploy/images.digest.md`；版本沿用 `docs/prj-ledger-version-lock.md`（不另建重复文件）。

**验收判据 = `M6.2`**：**干净环境**（全新 clone + 空数据卷 + 仅按交付文档操作）一键启动并冒烟通过（`README.md` §五；`plan/Phase 6 详细开发计划（收敛与交付）.md` §四 D6–D7）—— ✅ **已达成（2026-10-10 实测）**。

> 口径差异说明：原计划 D7 另含 `Makefile`（`make up/demo/down`，`plan/Phase 6 详细开发计划（收敛与交付）.md` §四）；`README.md` D1 收口版定稿为上述 PowerShell 四脚本，以 README 为准（**既定决策弃用 Makefile**）。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-10-10 | 单人（本人） | 初始建立（Phase 6 D3 文档收口）：部署形态总览（compose 逐文件实测）、前置条件、首次部署步骤、环境变量清单（config.py 14 项实测）、镜像 digest 纪律（实测无裸 tag）、健康检查、升级回滚、一键启动规划段 | 新增本文档 |
| 2026-10-10 | 单人（本人） | **收口后过期口径更正（D6–D7 已落地）**：① §八 标题「规划中，待 D6–D7 落地」→ **「已落地，`M6.2` 达成」**；② §八 状态声明原写「`deploy\` 目录**当前不存在**、本章为规划、**不构成可用交付物**」—— 与 `deploy/` 已封版（7 个文件，M6.2 实测 8 容器 up / 7 基建 healthy / smoke 6/6 PASS）**直接矛盾**，已更正为可用交付物说明并标注原声明作废；③ 四脚本表改「行为（已落地）」并补 `images.digest.md`；④ 验收判据标注 **已达成**；⑤ §三 步骤 5 的【待确认】改为口径更新：**一键化诉求已由 `init.ps1` 覆盖，但单条迁移命令仍未在 `README.md` §4.4 逐条列出 —— 如实保留该缺口**，不因一键化而声称已固化 | §三 步骤 5、§八、修订记录 |
