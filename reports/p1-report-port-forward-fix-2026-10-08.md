# P1 D1 环境故障与修复报告（宿主←容器 端口转发失效）

> **文档类型**：一次性快照（专项实测/故障报告）｜ **状态**：🟡 时点快照（2026-10-08）
> **对应任务**：`plan/p1-plan-detailed.md` §四 D1（A1 骨架 / 环境复用）
> **环境依据**：`env/env-baseline-v2.md`（采集于 2026-09-24）｜ 端口事实见 `env/p1-audit-ports-2026-10-08.md`
> **结论**：故障已修复；D1-A1（MQTT 链路）与 D1 环境复用均达成

---

## 一、症状与证据

D1 启动 `compose.ingest.yml` / `compose.base.yml` / `compose.v2.yml` 后，容器健康、WSL 侧监听齐全，但**宿主无法访问任何已发布端口**：

| 证据 | 结果 |
|---|---|
| WSL（docker-desktop）`netstat -ltn` | 全部 LISTEN：`::1883 / 6030 / 6041 / 5433 / 6379 / 7474 / 7687 / 9092 / 19531` |
| Windows `netstat -ano`（过滤上述端口） | **无任何监听** |
| 宿主 `Test-NetConnection 127.0.0.1` / `192.168.2.129` | 上述端口**全部 False**（含 9 天前创建的 `auscult-v2-pg:5433`） |
| `curl 127.0.0.1:6041`、`:9092` | 超时 |
| 容器内 `curl localhost:9091/healthz`（Milvus） | `OK`（服务本身正常） |

> 判定为**回归**：Phase 0 的 V3 自研解码器曾在宿主以 `127.0.0.1:6041` 直连 TDengine（`reports/p0-report-v3-ingest-license.md` §6.2、`docs/sparkplug-b-decoder.md` §八）。

## 二、根因

- `.wslconfig` 中 `networkingMode=mirrored` 已生效：WSL `eth1` IP `192.168.2.129` 与宿主以太网 IP **完全相同**（mirrored 特征）。
- 在该模式下，Windows↔WSL 边界的端口转发**未建立**（Windows 侧无监听、无 `com.docker.backend` 代理监听），导致宿主→容器全部不通。
- 单纯重启 Docker Desktop **无效**（复测仍全部 False）→ 问题不在 Docker 进程，而在 WSL 镜像网络的建立状态。

## 三、处置

```
wsl --shutdown          # 强制终止 WSL2 VM，重建镜像网络
docker desktop restart  # 重启 Docker Desktop 引擎
# 之后按需重新 up -d 各编排（带 restart: unless-stopped 的会自动恢复）
```

- 未改动任何配置（保留 `networkingMode=mirrored`，满足「容器→宿主 Ollama 11434」需求，见 `env/ports.md` §二）。
- 影响：重启期间**暂停了宿主上其他项目的运行中容器**（已获用户授权）。

## 四、验证（修复后）

| 端口 | 组件 | 宿主直连 | 功能验证 |
|---|---|---|---|
| 1883 | Mosquitto | ✅ | 解码器 MQTT 连接成功并订阅 |
| 6041 | TDengine REST | ✅ | `show databases` → `iot` 存在 |
| 5433 | ParadeDB PG | ✅ | `psql \dt` 六表齐备 |
| 6379 | Redis | ✅ | `ping → PONG` |
| 7474 / 7687 | Neo4j | ✅ | 返回 `neo4j_version 5.26.31` |
| 19531 / 9092 | Milvus | ✅ | `/healthz → OK` |

D1-A1 端到端（模拟器 → MQTT → 解码器 → TDengine）实测通过：

- 4 条 DDATA 写入 `st_pump_metrics`（近 10 分钟计数 = 4，与解码器日志一致）；
- `new_metric`：`VIB_BAND_1` 写入 `st_unmapped_metrics` + `schema_drift` 告警；
- `rebirth`：`st_device_status` 记录 `birth(1001) → rebirth(1002, online=true) → ddeath(1002, online=false)`。

## 五、同期发现并处置的其他 D1 问题

| # | 问题 | 处置 |
|---|---|---|
| 1 | `scripts/self_decoder.py` main() 引用不存在的 `args.schema_mapping`（形参已改名 `--prj-spec-schema-mapping`），致 `--selftest`/启动即 `AttributeError` | 最小修复：改为 `args.prj_spec_schema_mapping`；自检 11 项 PASS |
| 2 | 项目 `.venv`（uv 管理）缺 `paho-mqtt` / `taospy`（解码器运行必需），依赖此前只装在系统 Python `D:\Python312` | 按 `requirements.txt` 锁定版本补装到 `.venv`：`paho-mqtt==2.1.0`、`taospy==2.8.10`、`grpcio-tools==1.84.0` |
| 3 | 补装时 `taospy` 传递约束将 `typing-extensions` 由 4.16.0 降至 4.14.1 | 记为环境漂移（`requirements.txt` 未直接锁该包）；`pydantic 2.13.5` 等关键包导入正常，解码器自检通过 |
| 4 | `compose.ingest.yml` 报孤儿容器 `auscult-ingest-decoder`（方案 A 已移出编排，9 天前残留） | `up -d --remove-orphans` 清理 |

## 六、后续纪律

- **镜像网络健康检查前置于 D1 类启动**：起容器后除 `docker ps` 外，**必须**在宿主侧做一次 `Test-NetConnection`/`curl` 直连核验，避免「容器健康但宿主不通」被漏判。
- 若日后再次出现宿主不通，先按 §三 处置；仍不通再评估将 `networkingMode` 改回 `nat`（届时需改 `env/env-baseline-v2.md` 并复核容器→宿主 Ollama 通道改走 `host.docker.internal`）。
- `typing-extensions` 降版属实装漂移，若后续升版需同步 `docs/prj-ledger-version-lock.md` 与 `requirements.txt`。

---

## 修订记录

| 日期 | 操作者 | 变更 | 影响文件 |
|---|---|---|---|
| 2026-10-08 | 单人（本人） | 新建：记录端口转发失效的发现、根因、处置与验证，及同期 4 项 D1 问题 | `env/p1-audit-ports-2026-10-08.md` |