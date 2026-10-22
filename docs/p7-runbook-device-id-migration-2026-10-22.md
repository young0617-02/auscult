# Runbook · 设备编号数据层统一迁移（ISS-056 候选①）

> 2026-10-22 · 配套代码：`app/device_ids.py`、`scripts/migrate_device_ids.py`、`tests/test_device_id_migration.py`
> 状态：**真机迁移已执行完毕，查询口径默认已翻转为 `canonical`**（342 passed）。本文件保留为执行/回滚手册：
> 迁移前默认值是 `legacy`（保证零行为变化），迁移后默认值与库内形态一致，**未迁移的旧库必须显式
> 设 `AUSCULT_DEVICE_ID_SCHEME=legacy`**，否则查询会打到已不存在的短编号（实测"设备不存在"）。

## 一、为什么做

产品层用规范编号 `PUMP-A-01`，数据层（TDengine 子表 TAG、PG `alerts`、灌数脚本）用短编号 `PUMP-A`。
候选②（工具层 `DEVICE_ALIAS_MAP` 垫片）只是让查询"查得到"，垫片本身仍是第二套口径；
候选①把**存量数据原地改写成规范编号**，让两层同口径，垫片退化为纯兼容层。

不采用"清库重灌"：会丢历史时序、破坏已锁定实验（EXP-P7-GATE*/V1 判据）的可复现性。
TAG / 子表名 / 实体名都可原地改写；需要重灌的只有 Redis 去重键，而其 TTL=5min，迁移窗口后自然过期。

## 二、影响面

| 侧 | 对象 | 迁移动作 | 预期 |
|---|---|---|---|
| TDengine | TDengine 子表 `d_{group}_{device}` | `SET TAG device_id` + `RENAME` 子表名 | 3 张子表（PUMP-A/B/C）→ 规范编号 |
| PG | `alerts.device_id` | `UPDATE`（保留 `alarm_id`，幂等键不变） | 历史告警全量改名 |
| PG | `work_orders.device_id` | 同上（尝试） | **预期 0 行**：源数据是图纸/台账口径（`A 0泵`、客户号），无产品编号可迁 |
| Neo4j | `Entity.name` | `SET e.name` | 若实体以设备编号命名则迁移；语料实体多为部件/现象，可能 0 个 |
| 灌数端 | `v3_ingest_direct` / `gen_sparkplug` / `spb_simulator` | 默认值已改规范编号 | 迁移后新数据天然同口径 |
| 查询端 | `query_sensor` / `query_graph` / `get_maintenance_history` | 经 `storage_id()`，由 `AUSCULT_DEVICE_ID_SCHEME` 决定 | 默认 `canonical`（迁移后）；连旧库需显式 `legacy` |

## 三、执行前检查

1. docker 栈在线：`curl 127.0.0.1:6041/rest/sql`（TDengine）、`7474`（Neo4j）、PG `5433` 可连；
2. 备份：`pg_dump` 至少覆盖 `alerts`/`work_orders`；TDengine 建议 `taosdump` 或确认演示数据可重建；
3. 停写：迁移期间不要让 decoder / 灌数脚本继续写入（否则新旧子表并存）；
4. 记录当前分布：`python scripts/migrate_device_ids.py --verify`（应显示全部 legacy 编号）。

## 四、执行步骤

```powershell
# 1) dry-run 看计划（不写库）
.venv\Scripts\python.exe scripts\migrate_device_ids.py

# 2) 逐侧执行，建议先 TDengine 再 PG、最后 Neo4j
.venv\Scripts\python.exe scripts\migrate_device_ids.py --target td --apply
.venv\Scripts\python.exe scripts\migrate_device_ids.py --target pg --apply
.venv\Scripts\python.exe scripts\migrate_device_ids.py --target neo4j --apply

# 3) 查询口径：默认已是 canonical，无需设置；仅连未迁移旧库时显式 legacy
#    $env:AUSCULT_DEVICE_ID_SCHEME = "legacy"
# 重启 API 生效

# 4) 核对 + 回归
.venv\Scripts\python.exe scripts\migrate_device_ids.py --verify     # 期望 ok=True
.venv\Scripts\python.exe -m pytest tests -q                          # 期望 342 passed
```

## 五、回滚

```powershell
# 1) 查询端口径先切回 legacy（零停机，立刻恢复旧行为）
$env:AUSCULT_DEVICE_ID_SCHEME = "legacy"

# 2) 数据侧反向执行（canonical → legacy）
.venv\Scripts\python.exe scripts\migrate_device_ids.py --revert --apply
```

## 六、已知限制（真机执行后复核）

1. **TDengine 不发 `RENAME`（2026-10-22 真机确认）**：TDengine 3.3.8.0 下 `ALTER TABLE ...
   SET TAG` 可用、`RENAME` 语法不通**且无必要**——查询按 TAG 过滤（`device_id=`），子表名只是内部标识。
   实测结果：三张历史子表 `d_plant1_PUMP-A/B/C` 的 TAG 已改为 `PUMP-A-01/B-01/C-01`，行数
   12919/4314/4083 原样保留；子表名仍是短编号形态，**不影响查询**（`SELECT tbname, device_id`
   已核对名实一致性）。
2. **`work_orders` 无迁移对象**：源数据无产品编号；工单侧继续依赖"空结果回灌库里真实编号样本"
   （`get_maintenance_history` 的 `known_device_ids`），根治需重做台账解析映射（另立项）。
   真机实测：`get_maintenance_history(PUMP-A-01)` → `work_orders=[]` +
   `known_device_ids=[A 0泵, A 1泵, …]`（台账口径原样回灌，符合预期）。
3. **图谱侧无设备编号实体**：`--verify` 的 `neo4j` 为空、`query_graph(PUMP-A)` 归一为
   `PUMP-A-01` 后 `entities_hit=["故障"]`、`hits=[]`——归一链路本身正常，但图谱实体是部件/现象口径，
   设备关系查询必然空。根治 = 实体对齐（另立项，与工单台账解析同类）。
4. `alarms`/`audit_logs` 中若存有设备号文本（非 `device_id` 列），不在本次迁移范围。
5. **残留空子表** `d_plant1_PUMP-A-01`（0 行）→ **已处置（2026-10-22）**：删除前复核
   `count(*)=0` 后执行 `DROP TABLE iot.d_plant1_PUMP-A-01`，`SHOW iot.TABLES` 剩 6 张
   （`s_plant1_*` 3 张 + `d_plant1_PUMP-A/B/C` 3 张），不再有"同 TAG 双子表"分叉风险。

## 七、验收清单（2026-10-22 真机执行结果）

- [x] `--verify` 三侧 `sides_reached=3` 且 `off_scheme` 全空 → `ok=true`，`scheme=canonical`
- [x] `SELECT DISTINCT device_id FROM alerts` 全为 `PUMP-A-01/B-01/C-01` → 实测 `[('PUMP-A-01', 1)]`
- [x] TDengine TAG 口径一致 → `SELECT tbname, device_id`：`d_plant1_PUMP-A→PUMP-A-01`（12919 行）、
      `-B→PUMP-B-01`（4314）、`-C→PUMP-C-01`（4083）；**子表名保留历史形态**（见六.1，非阻塞项）
- [x] 报告读取出口统一展示口径：`GET /api/reports[/{id}]` 经 `canonicalize_ids()` 归一
      （库内历史 payload 仍存 `PUMP-A`，API 返回 `PUMP-A-01`；实测 `RPT-fa1b64066214ba3f`）。
      库内证据不改写，"历史事实 vs 展示口径"分离。
- [x] 全量 `pytest tests -q` → **363 passed**；`verify_query_sensor.py` 三设备按 TAG 命中
      （PUMP-A/B/C-01 各 48–52 窗口，P95≈30.4ms）；`query_sensor(PUMP-A-01, vib_rms, 全窗)` → 12919 行

## 八、映射退场（什么时候可以删兼容层）

判据（2026-10-22 定稿，**当前不删**）：

1. `auscult_device_id_scheme_mismatch_total{direction}` 连续 **7 天为 0**——两类方向都没打点，
   说明没有任何调用方还在传"非库内形态"的编号；
2. `migrate_device_ids.py --verify` 的 `off_scheme` 三侧恒空；
3. 灌数端 / 前端 / 报表脚本已确认只产出规范编号。

满足后可删 `CANONICAL_TO_LEGACY`/`LEGACY_TO_CANONICAL`、`storage_id()` 两跳、`tool_registry._storage_id()`
包装与 `DEVICE_ALIAS_MAP`。在此之前直接删 = 历史调用方静默查空（`empty_reason=device_not_found`）。
