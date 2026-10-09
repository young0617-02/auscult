# P1 D2 · A2 时序 Schema 落地 + 模拟数据生成器

> **对应任务**：`plan/p1-plan-detailed.md` §四 D2（A2 时序 Schema 落地、Sparkplug B 模拟数据生成器）
> **上游依据**：`docs/p1-spec-data-sources.md` §3.1/§3.2/§3.3 ｜ 映射权威源 `configs/decoder_schema_mapping.json`（镜像 `docs/schema-mapping.md`）
> **交付物**：`configs/tdengine/schema_master.sql`、`scripts/gen_sparkplug.py` ｜ **验证日期** 2026-10-08
> **状态**：✅ 达成（Schema 落地 + 生成器自检通过 + 端到端落库验证）

---

## 一、交付物

| 文件 | 内容 |
|---|---|
| `configs/tdengine/schema_master.sql` | A2 时序 Schema **权威 DDL**：`iot` 库 + 三张超级表 `st_pump_metrics / st_unmapped_metrics / st_device_status`（列类型、TAG、子表命名约定）。**与 `decoder_schema_mapping.json` 保持数据镜像一致**（硬性约束），供人工审计/重建成表。实际建表由解码器 `init_schema()` 幂等完成（D1-A1 已建立，DDL 校验三表就绪）。 |
| `scripts/gen_sparkplug.py` | **批量造数生成器**：网关级 NBIRTH/NDATA/NDEATH + 设备级 DBIRTH/DDATA；振动成分含基频+工频谐波+随机噪声+轴承特征频率（BPFO/BPFI/BSF/FTF）注入，异常段幅值随进度**线性爬升**；固定 seed 可复现；多设备×1Hz×时长可配；QoS1 + PUBACK 计数等待防丢包。 |

## 二、验证

### 2.1 自检（`--selftest`）✅ PASS
- 正常态 vib_rms ≈ 1.3 mm/s；严重态 vib_rms > 4.5 mm/s；
- 严重态峭度抬升（>5.0）、轴承温度抬升（>66°C）；
- DBIRTH 含 `bdSeq / device_type / metric_quality` 且 9 metrics；NBIRTH 含网关指标。

### 2.2 端到端落库（小规模冒烟：3 设备 × 108 点，seed=20260928）
模拟器 → MQTT(1883) → 自研解码器 → TDengine(6041)

| 检项 | 结果 |
|---|---|
| PUBACK | 328/328 全部送达（324 遥测 + 4 生命周期报文） |
| `st_pump_metrics` 近 5min 行数 | **324（全部落库）** |
| 子表命名 | `d_plant1_PUMP-A/B/C`、`s_plant1_PUMP-A/B/C`（subtable 命名规则生效） |
| 异常段数值（PUMP-A） | max vib_rms = **4.66 mm/s（>4.5 触发 high）**、max kurtosis = 6.40、max temp = 76.6°C —— 特征频率注入 + 线性爬升生效 |
| 未登记 metric 旁路 | `u_plant1_PUMP-A` 仅含 **D1 spb_simulator** 遗留的 `VIB_BAND_1`（2 条，09-24 + 10-08），本次 gen 未产生意外旁路 |
| metric 名映射 | `vibration_rms→vib_rms` 等全部命中 `metric_mapping`，无 schema_drift 误报 |

> 说明：`d_plant1_PUMP-A` 行数 7312 为历史累计（D1 起多场景写入）；仅在 TDengine 中无 `DISTINCT`（不支持），故以子表行数判断本次增量。

## 三、与既有工具的边界（避免重复造轮子）

| 工具 | 定位 | 关系 |
|---|---|---|
| `scripts/spb_simulator.py` | 场景化**解码器边界验证**（birth/new_metric/rebirth/offline 等四类边界） | 保留不弃，D1-A1 已用 |
| `scripts/gen_sparkplug.py`（本交付） | **面向批量造数的生产化遥测源**（可复现、参数化、覆盖全消息类型、异常段线性爬升） | 新增，供 A2 之后的 A3 告警引擎、query_sensor、`golden_set` 抽检使用 |

二者共用同一 PB 类、同一 topic/schema，字段级等价（对齐真实数据可替换原则 §3.2-3）。

## 四、局限声明（固定文本，不得删改）

> **局限声明（固定文本，不得删改）**：
> 本阶段所有质量类结论（`Recall@5`、`MRR`、`NDCG@5`、引用正确率、幻觉率、置信度 ECE 等）均**基于模拟数据的初步验证**，语料由项目组自编，其分布、术语密度与真实现场资料存在差异。因此上述指标**仅证明"链路可运行、方案可比较"，不等于现场可用性结论**。Phase 1 取得真实语料后，须以同一评测集与同一流程**重测**并对齐本结论。

## 五、复现命令

```powershell
# 前置：接入栈 + 解码器（D1-A1）
docker compose -f docker/compose.ingest.yml up -d
& .venv\Scripts\python.exe scripts\self_decoder.py --prj-spec-schema-mapping configs/decoder_schema_mapping.json --mqtt-host 127.0.0.1 --td-host 127.0.0.1

# 自检
& .venv\Scripts\python.exe scripts\gen_sparkplug.py --selftest

# 灌数（小规模冒烟）
& .venv\Scripts\python.exe scripts\gen_sparkplug.py --hours 0.03 --alert-start-ratio 0 --alert-duration-min 0.6 --wait-s 60

# 校验落库
& .venv\Scripts\python.exe _query        # 或用 REST 查 iot.st_pump_metrics / d_plant1_PUMP-A
```

> 注意：子表名含设备连字符（如 `d_plant1_PUMP-A`），SQL 查询须以反引号包裹；PowerShell 下反引号是转义符，建议通过 taosrest/脚本查询而非 PowerShell 内联 SQL。

---

## 修订记录

| 日期 | 操作者 | 变更 | 影响文件 |
|---|---|---|---|
| 2026-10-08 | 单人 | 新建：A2 Schema 落地 + 生成器交付与验证 | `configs/tdengine/schema_master.sql`、`scripts/gen_sparkplug.py`、`docs/prj-ledger-version-lock.md` |