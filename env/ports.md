# T1.3 端口检查报告

> **⚠️ 时点声明（2026-10-08 文档同步加注，实测数据未改）**：本表为 **2026-09-23 20:51** 的一次性快照，**晚于 T1.1 `.wslconfig` 安装（2026-09-24）**，因此 `env/env-baseline-v2.md` 引用的环境基线**并未重采端口**。表中「实测状态」与**瞬时 PID 仅供当时的冻结依据**，不得作为今日端口占用结论使用。
> **两处已知过期**：① 6379 Redis 原列「checkpoint」用途 —— V5 已因 B7 切换 **PostgreSQL checkpointer**，Redis 仅作候选留档（见 `docs/p0-decision-checkpoint.md` §2.1）；② 文中 PID（80484 / 109044 等）为当日进程号，**现已失效**。
> **P1 动作**：起容器前先跑 `scripts/check_ports.ps1` **重采**，并按 `docs/prj-spec-document-standard.md` 的新命名登记为 `env/p1-audit-ports-<YYYY-MM-DD>.md`。

> 采集时间：2026-09-23 20:51（+08:00）
> 采集方式：`Get-NetTCPConnection -State Listen`（Windows 宿主）+ WSL2 内 `/dev/tcp` 探活
> 项目根：`<REPO>`

## 一、目标端口实测结果

| 端口 | 归属组件 | 实测状态 | 处置 |
|---|---|---|---|
| 19530 | Milvus gRPC | ✅ free | 直接使用 |
| 9091 | Milvus metrics | ✅ free | 直接使用 |
| 7474 | Neo4j HTTP | ✅ free | 直接使用 |
| 7687 | Neo4j Bolt | ✅ free | 直接使用 |
| 6030 | TDengine 原生连接 | ✅ free | 直接使用 |
| 6041 | TDengine REST (taosAdapter) | ✅ free | 直接使用 |
| 5432 | PostgreSQL / pgvector | ✅ free | 直接使用 |
| 6379 | Redis (checkpoint) | ✅ free | 直接使用 |
| **11434** | **Ollama** | ⚠️ **OCCUPIED** | **预期占用，非冲突**，见下 |
| 1883 | Mosquitto MQTT | ✅ free | 直接使用 |
| 8000 | 应用后端 API | ✅ free | 直接使用 |
| 3000 | 前端 | ✅ free | 直接使用 |

**结论：12 个目标端口中 11 个空闲，无需重映射。唯一占用的 11434 是本项目自己要用的 Ollama，属预期占用。**

## 二、11434 占用详情

```
LocalAddress  LocalPort  OwningProcess
127.0.0.1     11434      80484
```

- 占用者：Ollama 0.34.2（`ollama.exe`，PID 80484）
- 绑定地址：`127.0.0.1`（仅本机，未暴露到局域网，安全）
- 处理：**保留**。容器访问宿主 Ollama 的两种方式：
  1. `.wslconfig` 设 `networkingMode=mirrored` → 容器内可用 `127.0.0.1:11434` 直接访问；
  2. 或容器内用 `host.docker.internal:11434`。
- ⚠️ 注意：若 `.wslconfig` 中 `networkingMode=mirrored` 被关闭，方式 1 失效，必须回退方式 2。

## 三、非本项目占用但需留意的端口

| 端口 | 占用进程 | 组件 | 影响评估 |
|---|---|---|---|
| 8080 | PID 109044 | nacos-standalone 容器 | P0 无影响；但 P4+ 若网关/Nginx 想用 8080 会冲突，**已预留 8000 给后端、3000 给前端** |
| 8848 / 9848 | PID 109044 / 108332 | Nacos 主端口与 gRPC | 与 P0 目标端口无交集，无影响 |
| 443 | PID 77216 | 本机 HTTPS 服务 | 无影响 |

> 说明：Nacos 容器当前已运行 37 分钟，属于**宿主上已有的其他项目**。P0 各验证项启动时不要 `docker system prune` 或停止非本项目容器。

## 四、端口分配基线（冻结，后续所有 compose 必须遵守）

```
# 向量与检索
19530  Milvus gRPC            (milvus-standalone)
9091   Milvus metrics
5432   PostgreSQL + pgvector  (对照路线)

# 图谱
7474   Neo4j HTTP
7687   Neo4j Bolt

# 时序
6030   TDengine 原生
6041   TDengine REST / taosAdapter

# 状态与消息
6379   Redis (LangGraph checkpoint, noeviction + appendonly)
1883   Mosquitto MQTT (Sparkplug B)

# 模型与应用
11434  Ollama (宿主原生，保留占用)
8000   应用后端 API
3000   前端

# 基础设施（Milvus 依赖，不对外暴露，仅内网）
2379   etcd client
9000   MinIO S3 API
9001   MinIO Console（**仅容器内网，不发布到宿主**）
# ⚠️ 宿主侧 9001 实际分配给 Mosquitto WebSocket（docker/compose.base.yml 的 "9001:9001"）；
#    两者不冲突：MinIO Console 只在 auscult-net 内可达，不占用宿主端口。
```

## 五、复检命令

```powershell
# Windows 侧
powershell -File scripts\check_ports.ps1

# WSL2 侧（bash）
for p in 19530 9091 7474 7687 6030 6041 5432 6379 11434 1883 8000 3000; do
  (echo >/dev/tcp/127.0.0.1/$p) >/dev/null 2>&1 && echo "$p OCCUPIED" || echo "$p free"
done
```

> **DoD 校验**：本文件满足 T1.3 要求（冲突项已识别、重映射方案已给出或确认无需重映射）。
> ✅ **T1.3 通过 —— 无需端口重映射。**