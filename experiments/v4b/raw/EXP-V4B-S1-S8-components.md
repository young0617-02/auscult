# V4b 压测 S1–S8 组件实测（2026-09-24）

> 口径 B（宿主总占用）；gpu 决议改走宿主 Ollama；应用后端/前端无运行镜像（Phase 0 未交付，如实标注，不编造）。
> 基础组件栈来自 `docker/compose.base.yml` + `tdengine` profile。

## 组件集与端口（全部 healthy）

| 容器 | 镜像 | 端口 | 状态 |
|---|---|---|---|
| auscult-etcd | quay.io/coreos/etcd:v3.5.25 | 内网 | healthy |
| auscult-minio | minio/minio:RELEASE.2024-12-18T13-15-44Z | 9001 | healthy |
| auscult-milvus | milvusdb/milvus:v3.0.0 | 19530/9091 | healthy |
| auscult-postgres | postgres:18 | 5432 | healthy（PG18 挂载点已修复） |
| auscult-redis | redis:8 | 6379 | healthy |
| auscult-neo4j | neo4j:5-community | 7474/7687 | healthy（新拉取） |
| auscult-mosquitto | eclipse-mosquitto:2 | 1883/9001 | healthy（路径已修复） |
| auscult-tdengine | tdengine/tsdb:3.3.8.0 | 6030/6041 | healthy |

## 容器级资源峰值（docker stats，稳态）

| 容器 | 内存 | CPU% |
|---|---|---|
| etcd | 31.13 MiB | 0.60 |
| minio | 87.60 MiB | 0.00 |
| milvus | 151.2 MiB | 2.78 |
| postgres | 65.25 MiB | 0.02 |
| redis | 8.57 MiB | 0.13 |
| neo4j | 871.1 MiB | 0.97 |
| mosquitto | 4.113 MiB | 0.02 |
| tdengine | 197.1 MiB | 1.41 |
| **容器合计** | **≈1416 MiB（≈1.38 GB）** | — |

## 宿主侧（口径 B）

| 项 | 空载(S0) | 全组件后 | 增量 |
|---|---|---|---|
| Windows 宿主已用 | 19.65 GB | **25.62 GB** | +5.97 GB |
| Windows 宿主总量 | 31.80 GB | 31.80 GB | — |
| 显存 | 983 MiB | **1148 MiB** | +165 MiB |

## 修复记录（V4b 执行中发现的配置缺陷）

1. **PG18 数据目录布局**：`compose.base.yml` postgres 卷挂载点由 `/var/lib/postgresql/data` 改为 `/var/lib/postgresql`（PG18 镜像强制要求），否则 postgres:18 启动即 Exited(1)。
2. **mosquitto 路径**：`./configs/mosquitto.conf` → `../configs/mosquitto.conf`（相对路径以 docker/ 为准）。
3. **redis 容器名冲突**：清理遗留 Exited 的 `auscult-redis` 容器。

> ⚠️ **诚实声明**：neod4j 为全组件栈中新拉镜像（digest 见 version-lock §三）；应用后端/前端（S7/S8 应用层）本阶段**无运行镜像（仅 Dockerfile.decoder），未采集**——不编造数字。