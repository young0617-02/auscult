# P1 端口审计（2026-10-08）

> **文档类型**：一次性快照（审计）｜ **命名**：`env/p1-audit-ports-2026-10-08.md`（`docs/prj-spec-document-standard.md` §四 `env/` 例外 + `env/ports.md` 头部「P1 动作」要求）
> **采集时间**：2026-10-08 14:46（+08:00）
> **采集方式**：`scripts/check_ports.ps1 -Ports @(...) -ShowOwner`（Windows 宿主）+ `docker ps` / 实际连接核验
> **状态**：🟡 时点快照（一次性审计，若需复测以当日新采集为准）

## 一、检查范围（P1 实际使用端口）

| 端口 | 组件 | 归属编排 | 说明 |
|---|---|---|---|
| 1883 | Mosquitto MQTT | `compose.ingest.yml` | Sparkplug B 传输 |
| 6030 | TDengine 原生 | `compose.ingest.yml` | — |
| 6041 | TDengine REST | `compose.ingest.yml` | 解码器写入通道（taosrest） |
| 5433 | ParadeDB PG（auscult_v2） | `compose.v2.yml` | 宿主 5927 被其他项目占用改 5433 |
| 19531 | Milvus gRPC | `compose.v2.yml` | 基线 19530 被 kbrag 占用偏移 |
| 9092 | Milvus metrics/healthz | `compose.v2.yml` | 同上偏移 |
| 6379 | Redis | `compose.base.yml` | 告警去重 / checkpoint 候选 |
| 7474 / 7687 | Neo4j HTTP / Bolt | `compose.base.yml` | 三元组图库 |
| 11434 | Ollama（预期占用） | 宿主原生 | 保留 |
| 9763 | Web 应用后端 | — | 本期未起，预占 |
| 19530 / 9091 / 5432 | 基线端口（他项目占用，不使用） | — | 审计参照 |

## 二、实测结果（`check_ports.ps1`）

```
=== Windows host ===
  1883   free      Mosquitto MQTT
  6030   free      TDengine native
  6041   free      TDengine REST
  5433   free      unregistered
  19531  free      unregistered
  9092   free      unregistered
  6379   free      Redis checkpoint
  7474   free      Neo4j HTTP
  7687   free      Neo4j Bolt
  11434  free      Ollama
  9763   free      unregistered
  19530  free      Milvus gRPC
  9091   free      Milvus metrics
  5432   free      PostgreSQL

=== WSL2 (docker-desktop) ===
  distro state: Running
  5433   OCCUPIED   <- 本栈 auscult-v2-pg（预期）
  其余端口 free
```

> 注：14/14 空闲（含预期），无冲突、无需重映射。WSL 侧 5433 为已运行的 `auscult-v2-pg`，属预期占用。

## 三、容器启动后宿主连通性复测（15:03）

> 背景：启动前发现**宿主←容器端口转发失效**（Windows 侧无监听、TCP 直连全部失败，Phase 0 时可用），经 `wsl --shutdown` + 重启 Docker Desktop 修复（详见报告 `reports/p1-report-port-forward-fix-2026-10-08.md`）。

| 端口 | 组件 | 宿主直连（127.0.0.1） | 功能验证 |
|---|---|---|---|
| 1883 | Mosquitto | ✅ | 解码器 MQTT 连接成功 |
| 6030 | TDengine 原生 | ✅ | 容器内 taos 可用 |
| 6041 | TDengine REST | ✅ | `show databases` → `iot` 库存在 |
| 5433 | ParadeDB PG | ✅ | `psql \dt` 六表齐备 |
| 6379 | Redis | ✅ | `redis-cli ping` → PONG |
| 7474 / 7687 | Neo4j | ✅ | HTTP 返回 5.26.31 版本信息 |
| 19531 / 9092 | Milvus | ✅ | `/healthz` → OK |

## 四、结论

- 端口无冲突，无需重映射；宿主直连恢复后可正常推进 D1 及后续。
- 相关基线：`env/env-baseline-v2.md` §十（2026-09-23 口径）与 `env/ports.md`（2026-09-23 快照）**未重采端口**，本文件为 P1 起点的端口事实；后续如有变更，以新采集为准并同步两基线文件。

## 五、复检命令

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check_ports.ps1 -Ports @(1883,6030,6041,5433,19531,9092,6379,7474,7687,11434,9763) -ShowOwner
```
