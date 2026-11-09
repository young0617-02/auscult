# 干净环境演练留档（全新目录 + 全新空卷）· 2026-10-22

> **对应验收项**：`plan/Phase 6 详细开发计划（收敛与交付）.md` §7.3 第 1 项「干净环境 `docker compose up` 一键启动，全服务健康」
> **判定**：✅ **通过**（此前记 `[~]`，原因是"无演练留档"而非"起不来"）
> **演练包**：`dist/auscult-v1.0.0.zip`（v1.0.0 交付包，`sha256=7986af94…647680`，3,112,006 B）
> **代码基线**：git `0872c69`（tag `v1.0.0`，工作区干净）
> **环境**：Windows 11 专业版 26200 · Docker 29.6.2 · Compose v5.3.1（WSL2 后端）

---

## 一、为什么要单独设计这次演练

§7.3 第 1 项长期记 `[~]`，历史上被解释为"该场景曾 100% 崩（ISS-044/057）"。本次实测发现**另有一层容易被忽略的口径问题**：

`deploy/docker-compose.yml` 顶部写死了 `name: auscult-deploy`，命名卷因此固定为 `auscult-deploy_pg-data` 等 8 个。**这意味着"解压到全新目录"并不等于"空卷"** —— 新目录起的栈仍会挂上宿主上那套已有数据的卷，看起来一次性启动成功，其实从未验证过"零数据引导"。真要做到空卷，只有两条路：

| 路线 | 代价 | 结论 |
|---|---|---|
| `down -v` 销毁原卷 | 直接丢 23 MB 生产形态库（18 表 / 2319 条审计 / 32 份报告）+ Milvus/Neo4j/TDengine 数据 | ❌ 不可接受（会破坏已锁定实验基线） |
| `-p` / `COMPOSE_PROJECT_NAME` 换项目名 | 新建 8 个同名空卷，原卷零接触 | ✅ **本次采用** |

实测验证了优先级（`docker compose config` 输出 `name` 字段）：

```text
-p auscult-clean            → name = auscult-clean     （覆盖 compose 内 name:）
COMPOSE_PROJECT_NAME=...    → name = auscult-clean     （同样覆盖，供 up.ps1 继承）
不带任何覆盖                 → name = auscult-deploy    （回落到文件内 name:）
```

因此本次演练用**交付包自带脚本 + `COMPOSE_PROJECT_NAME=auscult-clean`**：既走真实的一键入口，又保证是真空卷。

---

## 二、执行步骤与原始证据

### 2.1 基线（演练前，`18:52:50`）

```text
db_size=23 MB  tables=18
audit_logs=2319  checkpoint_writes=1021  checkpoint_blobs=494  checkpoints=348  reports=20(n_live_tup 估算)
原栈：auscult-deploy running(9)，8 基建 healthy + nginx unhealthy（依赖宿主后端，既有现象）
原卷：auscult-deploy_* 共 8 个
```

### 2.2 全新目录（`18:53`）

```text
drill dir = <USER_HOME>\AppData\Local\Temp\auscult-clean-drill-2026-10-22
files = 557（556 + PACKAGE-MANIFEST.txt）  size = 6.5 MB
解压来源 = dist\auscult-v1.0.0.zip（未做任何手工补文件）
```

### 2.3 停原栈（保留卷）

```text
powershell -File deploy\down.ps1   → exit 0，8 容器 Removed，8 个 auscult-deploy_* 卷全部保留
⚠ 残留：auscult-tdengine 仍 Up（down.ps1 未带 --profile tdengine）→ 见 §四.2（ISS-063）
   补跑 docker compose --profile tdengine down 后容器与网络才彻底释放
```

### 2.4 创建演练栈并核验"真·空卷"（起栈前）

```text
docker compose -p auscult-clean --profile tdengine create
  → 新建 8 卷：auscult-clean_{milvus-data,milvus-etcd-data,milvus-minio-data,mosquitto-data,neo4j-data,pg-data,redis-data,tdengine-data}
docker inspect auscult-pg → volume auscult-clean_pg-data -> /var/lib/postgresql   （未挂原卷）
新建卷体积：空（docker system df 无 Size）
```

### 2.5 一键启动（`18:55:01`）

第一次执行被**守卫拦下**（这正是 ISS-057 修复后的设计行为）：

```text
=== auscult deploy: up ===
[INFO] No .env found; using code defaults (app/api/config.py)
[FAIL] 端口 1883 已被非 docker 进程占用：mosquitto(2880)
       compose 的 MQTT 端口映射会**静默失败**（ISS-057）→ 灌数走宿主 broker，数据只落 ~12%。
up exit=1
```

宿主 `mosquitto.exe`（PID 2880，属另一项目 Palpation，命令行 `-c C:/mosquitto/mosquitto_custom.conf -v`）占用 1883。**临时停止该进程**（演练后按原命令行恢复，见 §五）后重跑：

```text
[OK] 端口 1883 空闲（MQTT 映射可正常建立）
[STEP 1/2] Pulling images...   9 个 @sha256 镜像全部 Pulled（digest 校验通过）
[STEP 2/2] Starting services... 9 容器 Started
up exit=0
```

### 2.6 健康检查收敛（起栈后 11 s）

```text
[  0s] etcd=healthy | milvus=starting | minio=healthy | mosquitto=healthy | neo4j=healthy | nginx=starting | postgres=healthy | redis=healthy | tdengine=healthy
[ 11s] etcd=healthy | milvus=healthy  | minio=healthy | mosquitto=healthy | neo4j=healthy | nginx=starting | postgres=healthy | redis=healthy | tdengine=healthy
[DONE] 全部基建 healthy，耗时 11s
```

`nginx` 保持 unhealthy/starting：其 healthcheck 回源宿主 `Next.js:3000` / `FastAPI:8000`，本次只起基建、未起宿主后端进程，与 `smoke.ps1` 的既有口径（nginx 排除出本项计数）一致。

### 2.7 冒烟（`18:55:57`，空卷）

```text
[1/6] [PASS] All infra services healthy (nginx excluded - backend dependent)
[2/6] [PASS] PG connected, 5 tables in public schema      ← 空库：仅 initdb 默认表
[3/6] [PASS] Milvus healthz OK (metrics port 9092)
[4/6] [PASS] Redis PONG
[5/6] [PASS] Neo4j HTTP reachable
[6/6] [PASS] Nginx reachable (502 expected - no backend running)
=== SMOKE RESULT: 6 passed, 0 failed ===
[OK] M6.2 smoke gate passed.
```

### 2.8 追加验证：空库能否从交付包内的迁移文件引导出 schema

`deploy/init.ps1` 的 Milvus / Neo4j / 元数据三步依赖 `.venv`（包内**刻意不含** `.venv`），故本次只取其第 1 步（PG 迁移）在空卷上实跑，验证「包内迁移文件是可引导的」：

```text
migrations copied from package（db/migrations，6 个文件）
空库迁移前：5 表
0001_init.sql                  exit=0
0003_reports.sql               exit=0
0004_users.sql                 exit=0
0005_knowledge_admission.sql   exit=0
0006_audit_logs.sql            exit=0
0007_alerts_auto_trigger.sql   exit=0
迁移后：14 表
业务表 9：alerts / audit_logs / doc_chunks / documents / knowledge_versions / outbox / reports / users / work_orders
扩展视图 5：geography_columns / geometry_columns / spatial_ref_sys / pg_stat_statements / pg_stat_statements_info
```

**与原栈 18 表的差异已核对**：差集为 `checkpoints / checkpoint_writes / checkpoint_blobs / checkpoint_migrations`，即 **LangGraph checkpointer 在 app 启动时 `setup()` 自建**的 4 张表，**不是迁移集缺口**。

---

## 三、结论

| 判据 | 结果 |
|---|---|
| 全新目录（未经过手工修补的交付包） | ✅ 557 文件 / 6.5 MB，仅解压 |
| 清空卷（8 个命名卷全新空卷） | ✅ `auscult-clean_*`，`docker inspect` 确认未挂原卷 |
| 一键启动入口 | ✅ `deploy\up.ps1`（交付包内原样），exit 0 |
| 镜像 digest 校验 | ✅ 9/9 Pulled（版本锁口径成立） |
| 全服务健康 | ✅ 8 基建全 healthy，收敛 11 s（nginx 依赖宿主后端，按既有口径排除） |
| 冒烟 | ✅ **6/6 PASS**（空卷） |
| schema 可引导 | ✅ 包内 6 个迁移 0 失败，5 → 14 表 |

---

## 四、演练中暴露的问题

### 4.1 ISS-057 守卫按设计生效（非新缺陷）

起栈前 1883 被宿主 `mosquitto.exe` 占用 → `up.ps1` 立即 `exit 1` 并打印 PID/处置命令，**这正是 2026-10-21 修复的预期行为**。未装该守卫时表现为 "上得去但 1883 无宿主映射"；本次演练后原栈 `docker port auscult-mosquitto` 仍只剩 `9001`，说明该冲突在宿主侧**依然存在**（Palpation 项目与本项目争 1883），需二选一：停宿主 broker，或给交付栈换宿主端口。

### 4.2 ISS-063（新登记）：`down.ps1` 未带 `--profile tdengine` → tdengine 容器与网络残留

`up.ps1` 自 2026-10-14 起默认带 `--profile tdengine` 起栈，但 `down.ps1` 调用 `docker compose down` 时**未带该 profile**，导致：

```text
$ .\deploy\down.ps1
Container auscult-tdengine ... (未出现)
Network auscult-deploy_auscult-net Removing
Network auscult-deploy_auscult-net Resource is still in use     ← tdengine 仍占用网络
[OK] Services stopped.                                          ← 但退出码 0，静默"半停"
```

影响：`down` 后 tdengine 继续占 6030/6041 与 `auscult-net`，重起栈前若换过 compose 配置易出现"网络仍在使用"的迷惑报错；脚本仍报 `[OK]` 属静默偏航。**已在本次一并修复**（`down.ps1` 两条路径均补 `--profile tdengine`）。

修复后复验（同日，原栈在线时执行）：

```text
$ .\deploy\down.ps1
 Container auscult-tdengine Stopping / Stopped / Removing / Removed     ← 修复前该容器根本不在 down 选中集
 Network auscult-deploy_auscult-net Removing / Removed                 ← 无 "Resource is still in use"
[OK] Services stopped.        exit 0
docker ps -a | grep auscult → 空；docker network ls → 无 auscult-deploy_auscult-net
```

### 4.3 干净环境的 Python 侧初始化未覆盖（如实记录）

交付包按"宁可少打，不可泄漏"排除 `.venv`，因此 `init.ps1` 的 Milvus 建库 / Neo4j 导入 / B5 元数据 / 对账四步在新机器上必须先 `uv venv --python 3.12 && uv pip install -r requirements.txt`。本次未做该 bootstrap（需外网拉依赖），**留档口径**：§7.3 第 1 项判据是"基础设施一键启动 + 全服务健康"，不包含应用侧数据灌注；应用侧复现由 `deploy/init.ps1` + README §五 承担，已在历史轮次实跑过。

---

## 五、环境恢复（原状核验）

| 项 | 处置 | 核验 |
|---|---|---|
| 演练栈 | `docker compose -p auscult-clean --profile tdengine down -v` | 8 个 `auscult-clean_*` 卷全部 Removed，容器/网络零残留 |
| 原数据卷 | 全程未挂载、未删除 | `auscult-deploy_*` 8 卷仍在 |
| 原栈 | `docker compose --profile tdengine up -d` 重起 | 20 s 全基建 healthy |
| 原栈数据 | 只读核验 | `db=23 MB / tables=18 / audit_logs=2319 / reports=32`，与基线一致（基线 `reports=20` 取自 `pg_stat_user_tables.n_live_tup` 估算值，精确 `count(*)` 为 32，非演练造成） |
| 宿主 mosquitto（Palpation） | `mosquitto.exe -c C:/mosquitto/mosquitto_custom.conf -v` 原命令行重启 | 进程恢复（PID 25140），1883 重新由宿主持有 → 交付栈 1883 映射恢复为"缺失"（**演练前既有状态**，非本次引入） |
| 演练目录 | `%TEMP%\auscult-clean-drill-2026-10-22` | 已删除 |

---

## 六、复现命令（可直接照抄）

```powershell
# 0) 前置：宿主 1883 必须空闲（否则 up.ps1 会按 ISS-057 fail-fast）
$drill = Join-Path $env:TEMP 'auscult-clean-drill-2026-10-22'
Expand-Archive dist\auscult-v1.0.0.zip -DestinationPath $drill -Force

# 1) 停原栈（保留卷）；注意需补 profile 才能连 tdengine 一起停
powershell -File deploy\down.ps1
docker compose -f deploy\docker-compose.yml --profile tdengine down

# 2) 用独立项目名 = 全新空卷起栈（等价于"清空卷"且不动原数据）
$env:COMPOSE_PROJECT_NAME = 'auscult-clean'
powershell -File "$drill\deploy\up.ps1"

# 3) 冒烟
powershell -File "$drill\deploy\smoke.ps1"

# 4) 清理演练环境并恢复原栈
docker compose -p auscult-clean -f "$drill\deploy\docker-compose.yml" --profile tdengine down -v
Remove-Item Env:COMPOSE_PROJECT_NAME
docker compose -f deploy\docker-compose.yml --profile tdengine up -d
```

---

## 七、留档清单

- 本文档：`docs/p6-clean-env-drill-2026-10-22.md`
- 回填：`plan/Phase 6` §7.3 第 1 项 → `[x]`（合计 `[x]` 8 · `[~]` 0）
- 缺陷：`docs/prj-ledger-known-issues.md` 新增 **ISS-063**（`down.ps1` 缺 profile）
- 修复：`deploy/down.ps1`（两条路径补 `--profile tdengine`）
- 变更日志：`CHANGELOG.md` 同日条目
