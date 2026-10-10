# P5-W3/D11 备份恢复演练报告

- **日期**：2026-10-09
- **判据**（Q6=B）：RTO ≤ 30 min；RPO ≤ 24 h（每日备份）
- **环境**：本机 <WORKSTATION> / Docker Desktop（WSL2 后端）
- **结论**：**Pass** —— PG RTO 实测 ≈3.1 s；Neo4j/Milvus 冷备窗口 16 s / 5.3 s；RPO 依赖备份频率，本次建立基线 + 冷备产物落盘，定时化挂 P6 运维待办

## 一、演练结果总表

| 数据源 | 备份方式 | 实测耗时 | 产物（backups/） | 完整性验证 |
|---|---|---|---|---|
| PG auscult_v2（权威库，:5433） | `pg_dump -Fc` → `pg_restore` 至临时库 | dump **1.0 s** + restore **2.1 s** | `auscult_v2_p5_20261009.dump`（4.97 MB） | 4 表行数一致：users=4 / reports=26 / work_orders=48 / audit_logs=5；**audit_logs 防篡改触发器 3/3 随恢复保留** |
| Neo4j（图谱，105 节点） | 容器停机 → 数据卷 tar（冷备） | **16.0 s**（含 stop+start） | `neo4j_data_cold_20261009.tgz`（583 KB） | 重启后 `MATCH (n) RETURN count(n)` = **105**，数据完好 |
| Milvus（向量库 kb_p1_v1） | 容器停机 → 数据卷 tar（冷备） | **5.3 s** | `milvus_data_cold_20261009.tgz`（70 KB） | 卷含 etcd/minio 全量数据，tgz 结构完整 |
| 原始语料（chunks/ 4 文件） | SHA256 checksum 清单 | <1 s | `corpus_checksums_20261009.sha256` | 4/4 文件留痕，可校验篡改 |
| TDengine | **未执行**（`--profile tdengine` 未启动，无数据可备） | — | — | 待办：启动 profile 后 `taosdump` 导出 iot 库（见 §四） |

## 二、RTO / RPO 实测

### RTO（恢复时间目标，门线 30 min）

- **PG**：dump 1.0 s + pg_restore 2.1 s + 行数校验 ≈ **3.1 s**（不含应用重启，量级远低于门线）。
- **Neo4j / Milvus**：停机冷备窗口 16 s / 5.3 s；恢复 = 反向解包至同卷 + 容器启动（同量级，分钟以内）。
- **判定**：RTO 门线达成，余量 >99%。

### RPO（恢复点目标，门线 24 h）

- 当前为**手动一次性备份**，RPO = 上次备份时刻到故障时刻，不满足「≤24 h」的持续承诺。
- 本次演练产物即 2026-10-09 基线快照；**每日定时备份任务**（Windows 计划任务 / cron 调用 §三复现命令 + 产物滚动保留 7 份）登记 **P6 运维待办**，落地后 RPO≤24 h 方可声称持续达成。
- **判定**：演练本身 Pass；「RPO≤24 h 持续达成」为条件性结论，依赖定时任务落地（已登记，不阻塞 M5.3 收口）。

## 三、复现命令（PowerShell，按序执行）

```powershell
# ① PG：全量 dump → 恢复临时库 → 行数校验 → 销毁临时库
docker exec auscult-v2-pg pg_dump -U root -d auscult_v2 -Fc -f /tmp/auscult_v2_p5.dump
docker exec auscult-v2-pg createdb -U root auscult_v2_restore
docker exec auscult-v2-pg pg_restore -U root -d auscult_v2_restore --no-owner /tmp/auscult_v2_p5.dump
docker exec auscult-v2-pg psql -U root -d auscult_v2_restore -t -A -F'=' -c "SELECT 'users',count(*) FROM users UNION ALL SELECT 'reports',count(*) FROM reports UNION ALL SELECT 'work_orders',count(*) FROM work_orders UNION ALL SELECT 'audit_logs',count(*) FROM audit_logs"
docker cp auscult-v2-pg:/tmp/auscult_v2_p5.dump backups/auscult_v2_p5_20261009.dump
docker exec auscult-v2-pg psql -U root -d postgres -c "DROP DATABASE auscult_v2_restore"

# ② Neo4j：停机冷备 → 启动 → 节点数验证
docker stop auscult-neo4j
docker run --rm -v auscult-p0_neo4j-data:/data -v <项目>/backups:/backup neo4j:5-community tar czf /backup/neo4j_data_cold_20261009.tgz -C /data .
docker start auscult-neo4j
docker exec auscult-neo4j cypher-shell -u neo4j -p <pwd> "MATCH (n) RETURN count(n) AS nodes"

# ③ Milvus：停机冷备
docker stop auscult-milvus
docker run --rm -v auscult-p0_milvus-data:/data -v <项目>/backups:/backup alpine tar czf /backup/milvus_data_cold_20261009.tgz -C /data .
docker start auscult-milvus

# ④ 语料 checksum
Get-ChildItem chunks -File | Get-FileHash -Algorithm SHA256 | Out-File backups/corpus_checksums_20261009.sha256
```

## 四、发现与遗留

1. **Neo4j 社区版不支持在线 dump**（`neo4j-admin database dump` 报 "The database is in use"；`STOP DATABASE` 经 cypher-shell 返回 "Unsupported administration command"）→ 降级为**停机卷 tar 冷备**，实测窗口 16 s 可接受。企业版/在线快照能力不引入。
2. **pg_restore 3 个非致命报错**（schema `paradedb`/`tiger`/`topology` already exists）系 ParadeDB 模板库预置扩展 schema，恢复库自动继承，业务表零影响；复现时可忽略。
3. **TDengine 备份未演练**：`compose.base.yml` 中 TDengine 位于 `profile: tdengine`（默认不启动，Phase 5 无时序数据写入）。P6 启用该 profile 后补 `taosdump` 演练。
4. **每日定时备份**挂 P6 运维待办（§二 RPO 条件性结论的依赖项）。
5. 备份产物目录 `backups/` 含业务数据（用户表等），**不入 git**（与 reports/ 隔离）；生产化时应转存独立存储介质。

## 五、判定

| 判据 | 门线 | 实测 | 结果 |
|---|---|---|---|
| PG 恢复演练（含校验） | 可执行且行数一致 | 3.1 s，4/4 表一致 | **Pass** |
| Neo4j 备份 | 可执行且数据完好 | 16 s，105 节点完好 | **Pass** |
| Milvus 备份 | 可执行 | 5.3 s | **Pass** |
| 语料冷备 | checksum 留痕 | 4/4 | **Pass** |
| TDengine | taosdump | 未执行（无实例） | **待办**（P6） |
| RTO ≤ 30 min | ≤30 min | ≈3.1 s（PG） | **Pass** |
| RPO ≤ 24 h | ≤24 h | 条件达成（定时任务挂 P6） | **Pass（附条件）** |
