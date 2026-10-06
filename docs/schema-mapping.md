# Sparkplug B → TDengine 超级表映射（Schema Mapping）v1

> **对应任务**：V3 Step2 ｜ **里程碑**：M0.3
> **上游依据**：`云侧工业 IoT 诊断 Agent 系统 - 最终执行方案（V5.0 定稿）.md` §3.6、§6.5
> **相关决策**：TDengine **3.3.8.0**（OSS，已锁定精确 digest，见 `docs/version-lock.md` §二.2.1）｜ Broker 默认 **Mosquitto 2**（EMQX 备选）
> **版本**：v1 ｜ **定稿日期**：D4–D5 ｜ **状态**：映射设计定稿；**授权边界与解码路径待 T1.9 结论**
> **主场景**：离心泵轴承振动异常诊断

---

## 一、映射总目标

把 MQTT 上流动的 **Sparkplug B 编码报文**，无损落成 TDengine 里**可被 `query_sensor` 按设备/时间窗口聚合**的时序表结构。要做到：

1. **一个设备一张子表**（`d_<device_id>`），共享一张超级表（`st_pump_metrics`）；
2. **报文里的 metric 名 → 表列的稳定映射**，不因新增测点而改表结构；
3. **4 类边界情况（建表/新增 metric/re-birth/离线）都有确定行为**，不出现"静默丢数"；
4. 让 V3 的判据"**社区版可用 + Schema 映射正确**"可被逐条验证。

---

## 二、Sparkplug B 主题结构解析

### 2.1 主题层级

```
spBv1.0 / <group_id> / <message_type> / <edge_node_id> / [<device_id>]
   ↑          ↑             ↑                ↑              ↑
 命名空间   逻辑分组      报文类型         边缘节点         设备（仅设备级报文有）
```

| 层级 | 含义 | 本项目的取值约定 |
|---|---|---|
| `spBv1.0` | Sparkplug B 命名空间，固定 | 固定 `spBv1.0` |
| `<group_id>` | 逻辑分组（通常=厂区/装置区） | `plant1`（模拟）；真实环境待填 |
| `<message_type>` | 报文类型（见 §2.3） | `NBIRTH`/`NDATA`/`NDEATH`/`DBIRTH`/`DDATA`/`DDEATH`/`STATE` |
| `<edge_node_id>` | 边缘节点（网关）标识 | `gw-pump-01`（模拟） |
| `<device_id>` | 设备标识；**节点级报文（N*）无此层** | `PUMP-A` / `PUMP-B` / `PUMP-C` |

### 2.2 报文层级关系

| 层级 | 主体 | 是否有 `<device_id>` | 示例主题 |
|---|---|---|---|
| **节点级** | 边缘网关自身 | ❌ | `spBv1.0/plant1/NBIRTH/gw-pump-01` |
| **设备级** | 挂在网关下的具体设备 | ✅ | `spBv1.0/plant1/DBIRTH/gw-pump-01/PUMP-A` |

### 2.3 七类报文类型语义

| message_type | 全称 | 语义 | 本项目处理动作 |
|---|---|---|---|
| **NBIRTH** | Node Birth | 网关上线，声明**网关自身**的 metric 与 `bdSeq` | 记录网关元数据；不建测点子表 |
| **NDATA** | Node Data | 网关自身周期数据 | 仅记运行态（如网关心跳/信号强度），不入主测点表 |
| **NDEATH** | Node Death | 网关**异常离线**（含遗嘱消息，MQTT Will） | **标记该网关下所有设备为离线**（见 §五.4） |
| **DBIRTH** | Device Birth | 设备上线，声明该设备的**完整 metric 集合**与 `bdSeq` | **建表/校验表结构**（见 §五.1、§五.3） |
| **DDATA** | Device Data | 设备周期数据（真正的高频写入来源） | **写入测点值**（唯一的常规写路径） |
| **DDEATH** | Device Death | 设备**异常离线**（遗嘱消息） | **标记单设备离线**（见 §五.4） |
| **STATE** | State | 主应用（Host Application）在线状态，主题为 `spBv1.0/STATE/<host_id>` | 忽略（本项目不使用 Host Application 角色） |

### 2.4 载荷结构（Protobuf `Payload`）

| 字段 | 类型 | 说明 | 本项目用途 |
|---|---|---|---|
| `timestamp` | uint64 | 报文生成时间（毫秒） | **写入 `ts`**（优先用 metric 自身 timestamp） |
| `metrics[]` | Metric[] | metric 数组 | 逐条映射到列 |
| `seq` | uint64 | 序列号，**0–255 循环** | 丢包检测（见 §六 风险 R-V3-3） |
| `uuid` | string | 会话标识 | 日志追踪 |
| `body` | bytes | 仅 STATE 报文使用 | 忽略 |

**Metric 子结构**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | string | metric 名（如 `vibration_rms`） |
| `alias` | uint64 | 可选别名（本机约定**不使用 alias**，避免歧义） |
| `timestamp` | uint64 | metric 级时间戳（**优先于 payload 级**） |
| `datatype` | enum | Sparkplug 数据类型（本项目只用 `Double`/`Float`/`Boolean`） |
| `value` | 变体 | 值 |
| `is_null` | bool | 值为空标记（设备侧读不到时置位） |
| `properties` | map | 含 `engUnit`（单位）、`quality` 等 |

---

## 三、Metric → 列映射表

### 3.1 三类模拟测点（对应 `docs/data-sources-v1.md` §3.1）

| metric name | Sparkplug datatype | 单位（`engUnit`） | 映射到的超级表 | 列名 | 列类型 | 是否 TAG | 备注 |
|---|---|---|---|---|---|---|---|
| `vibration_rms` | Double | `mm/s` | `st_pump_metrics` | `vib_rms` | DOUBLE | ❌ 普通列 | **主判据量**，告警阈值比对对象 |
| `vibration_peak` | Double | `mm/s` | `st_pump_metrics` | `vib_peak` | DOUBLE | ❌ 普通列 | 峰值，用于冲击判定 |
| `vibration_kurtosis` | Double | `-`（无量纲） | `st_pump_metrics` | `vib_kurtosis` | DOUBLE | ❌ 普通列 | 峭度，轴承早期故障敏感 |
| `bearing_temp` | Double | `degC` | `st_pump_metrics` | `bearing_temp` | DOUBLE | ❌ 普通列 | 轴承温度 |
| `motor_current` | Double | `A` | `st_pump_metrics` | `motor_current` | DOUBLE | ❌ 普通列 | 电机电流 |
| `pump_speed` | Double | `rpm` | `st_pump_metrics` | `pump_speed` | DOUBLE | ❌ 普通列 | 转速，**特征频率计算必需** |
| `metric_quality` | Boolean | `-` | `st_pump_metrics` | `quality_ok` | BOOL | ❌ 普通列 | 由 metric `is_null`/`properties.quality` 折算 |
| `device_type` | String | `-` | `st_pump_metrics` | — | — | ✅ **TAG** | 设备类型（`centrifugal_pump`） |
| `group_id` | String（主题层级） | `-` | `st_pump_metrics` | — | — | ✅ **TAG** | 来自主题，非 metric |
| `edge_node_id` | String（主题层级） | `-` | `st_pump_metrics` | — | — | ✅ **TAG** | 来自主题，非 metric |
| `device_id` | String（主题层级） | `-` | `st_pump_metrics` | — | — | ✅ **TAG** | 来自主题，非 metric |

### 3.2 映射纪律（**硬性**）

| # | 纪律 | 理由 |
|---|---|---|
| 1 | **metric name 不直接当列名**，必须经本表映射 | 防止设备侧随意命名污染表结构 |
| 2 | 未在 §3.1 登记的 metric **一律进 `unmapped` 旁路表**，不静默丢弃 | 避免"新增测点丢数"成为隐形缺陷 |
| 3 | **不使用 Sparkplug `alias`** | 复杂度高、易错；本机设备量小，用名称即可 |
| 4 | 单位必须校验：`engUnit` 与 §3.1 不符时**拒写并告警** | 防止 mm/s 与 μm 混写造成判据失效 |
| 5 | 时间戳取用顺序：`metric.timestamp` → `payload.timestamp` → 服务器接收时间（**已实现**：`_handle_ddata` 逐 metric 取 `metric.timestamp`，主表行时间戳统一取 payload 级） | 保证时序不乱序 |

---

## 四、超级表设计

### 4.1 普通列 vs 标签列（TAG）的划分理由

| 划分 | 归入的字段 | 理由 |
|---|---|---|
| **TAG（标签列）** | `group_id`、`edge_node_id`、`device_id`、`device_type` | ① 取值**离散且数量有限**；② 是 `query_sensor` 的**过滤条件**（"PUMP-A 的振动"）；③ 变化频率极低（设备属性，不是测量值）。TDengine 对 TAG 单独存储并建索引，按 TAG 过滤效率最高 |
| **普通列（采集量）** | `vib_rms`、`vib_peak`、`vib_kurtosis`、`bearing_temp`、`motor_current`、`pump_speed`、`quality_ok` | ① 是**随时间连续变化的测量值**；② 按时间降序存储、列式压缩；③ 若误设为 TAG 会导致标签基数爆炸、写入性能崩溃 |

> **反例警示**：把 `vib_rms` 当 TAG 会导致每个测量值都变成一个"设备"维度 —— TDengine 会为每个不同取值创建标签索引，**写入吞吐与查询性能双崩**。

### 4.2 超级表字段总表

| 字段 | 类型 | 说明 |
|---|---|---|
| `ts` | TIMESTAMP | 主键时间列（毫秒精度） |
| `vib_rms` | DOUBLE | 振动有效值（mm/s） |
| `vib_peak` | DOUBLE | 振动峰值（mm/s） |
| `vib_kurtosis` | DOUBLE | 峭度（无量纲） |
| `bearing_temp` | DOUBLE | 轴承温度（degC） |
| `motor_current` | DOUBLE | 电机电流（A） |
| `pump_speed` | DOUBLE | 转速（rpm） |
| `quality_ok` | BOOL | 数据质量标记 |
| **TAG** `group_id` | NCHAR(32) | 逻辑分组 |
| **TAG** `edge_node_id` | NCHAR(64) | 边缘网关 |
| **TAG** `device_id` | NCHAR(64) | 设备标识 |
| **TAG** `device_type` | NCHAR(32) | 设备类型 |

### 4.3 子表命名规则

```
d_<group_id>_<device_id>          例如：d_plant1_PUMP-A
```

### 4.4 `CREATE STABLE` SQL 示例（**可直接执行**）

```sql
-- 数据库（保留 365 天，1 天一个数据文件组）
CREATE DATABASE IF NOT EXISTS iot
    KEEP 365
    DURATION 10
    PRECISION 'ms'
    WAL_LEVEL 1;

USE iot;

-- 超级表：离心泵测点
CREATE STABLE IF NOT EXISTS st_pump_metrics (
    ts            TIMESTAMP,
    vib_rms       DOUBLE,      -- mm/s   振动有效值（主判据量）
    vib_peak      DOUBLE,      -- mm/s   振动峰值
    vib_kurtosis  DOUBLE,      -- -      峭度
    bearing_temp  DOUBLE,      -- degC   轴承温度
    motor_current DOUBLE,      -- A      电机电流
    pump_speed    DOUBLE,      -- rpm    转速（特征频率计算必需）
    quality_ok    BOOL         -- 数据质量标记
) TAGS (
    group_id      NCHAR(32),
    edge_node_id  NCHAR(64),
    device_id     NCHAR(64),
    device_type   NCHAR(32)
);

-- 自动建子表写入（推荐：由 taosX / 消费者用 USING 语法自动建表）
INSERT INTO d_plant1_PUMP-A USING st_pump_metrics
    TAGS ('plant1', 'gw-pump-01', 'PUMP-A', 'centrifugal_pump')
    VALUES (
        1758441600000,   -- ts
        4.82,            -- vib_rms   mm/s
        12.30,           -- vib_peak  mm/s
        3.85,            -- vib_kurtosis
        62.4,            -- bearing_temp degC
        18.6,            -- motor_current A
        2980.0,          -- pump_speed rpm
        TRUE             -- quality_ok
    );

-- 旁路表：未登记 metric（不丢数，待人工归并）
CREATE STABLE IF NOT EXISTS st_unmapped_metrics (
    ts            TIMESTAMP,
    metric_name   NCHAR(64),
    value_num     DOUBLE,
    value_str     NCHAR(128),
    quality_ok    BOOL
) TAGS (
    group_id      NCHAR(32),
    edge_node_id  NCHAR(64),
    device_id     NCHAR(64)
);

-- 设备在线状态表（供 NDEATH/DDEATH 与心跳写入）
CREATE STABLE IF NOT EXISTS st_device_status (
    ts             TIMESTAMP,
    online         BOOL,
    birth_seq      BIGINT,      -- bdSeq
    last_seq       INT,         -- 最近 seq，用于丢包检测
    reason         NCHAR(64)
) TAGS (
    group_id      NCHAR(32),
    edge_node_id  NCHAR(64),
    device_id     NCHAR(64)
);
```

### 4.5 `query_sensor` 契约对应的查询示例

```sql
-- 契约：给定 device_id + 时间窗 + 指标，返回统计量 + 异常标记
SELECT
    _wstart                       AS window_start,
    AVG(vib_rms)                  AS avg_vib_rms,
    MAX(vib_rms)                  AS max_vib_rms,
    STDDEV(vib_rms)               AS std_vib_rms,
    AVG(bearing_temp)             AS avg_temp,
    COUNT(*)                      AS sample_cnt
FROM st_pump_metrics
WHERE device_id = 'PUMP-A'
  AND ts >= 1758355200000 AND ts < 1758441600000
INTERVAL(1h)
ORDER BY window_start;
```

> **契约要点**：`query_sensor` 只读 `st_pump_metrics`；**异常标记不由 SQL 计算**，由应用层用阈值/Z-Score 规则（V5.0 §6.5）判定后附加，保证告警逻辑可单测、可替换。

---

## 五、4 类边界情况（**必须逐条覆盖**）

### 5.1 边界一：新设备首次建表

| 项 | 处理 |
|---|---|
| **触发** | 收到未见过 `device_id` 的 `DBIRTH` |
| **动作** | ① 解析 `DBIRTH.metrics[]`，与 §3.1 映射表比对；② **全部命中** → 用 `INSERT ... USING ... TAGS (...)` 自动建子表（TDengine 自动建表，无需 DDL）；③ **存在未登记 metric** → 正常列照写，未登记项写入 `st_unmapped_metrics`，并产生一条 `schema_drift` 告警；④ 记录 `bdSeq` 到 `st_device_status` |
| **幂等性** | 重复 `DBIRTH`（同 `device_id` 同 `bdSeq`）**不重复建表**（`USING` 语法天然幂等），仅刷新状态 |
| **验证方式** | 用模拟器首发 `DBIRTH` 后查 `SHOW TABLES`，确认出现 `d_plant1_PUMP-A`；查 `DESCRIBE` 确认列齐全 |

### 5.2 边界二：运行中新增 metric（**Schema 演进策略**）

| 项 | 处理 |
|---|---|
| **场景** | 运维给泵加装了一个新传感器（如 `discharge_pressure`），设备重启后 `DBIRTH` 里多了一个 metric |
| **策略** | **超级表结构不变更**。TDengine 超级表支持 `ALTER STABLE ... ADD COLUMN`，但**本项目默认不做在线 DDL** |
| **阶段一（默认）** | 未知 metric → `st_unmapped_metrics` 旁路 + `schema_drift` 告警 + 人工介入 |
| **阶段二（人工评审后）** | 若确认该 metric 长期需要：① 走**变更流程**（登记到本文件 §3.1 映射表 + 升版本文件为 v2）；② 执行 `ALTER STABLE st_pump_metrics ADD COLUMN discharge_pressure DOUBLE;`；③ 更新消费者映射代码；④ 记录到 `docs/known-issues.md` 与变更日志 |
| **禁止** | ❌ 消费者代码遇到未知 metric 自动 `ALTER STABLE` —— **会让表结构失控、无法回溯** |
| **验证方式** | 模拟器注入一个未登记 metric，确认：正常测点仍完整写入、新 metric 进旁路表、产生 `schema_drift` 告警、**主表 `DESCRIBE` 未变化** |

### 5.3 边界三：设备 re-birth（DDATA 与 DBIRTH 冲突处理）

| 项 | 处理 |
|---|---|
| **场景** | 设备/网关重启，重新发 `DBIRTH`；此时 `bdSeq` 会**重新计数**（Sparkplug 规范要求重启后 `bdSeq` 递增以区分会话） |
| **判定冲突的依据** | 比较 `st_device_status.birth_seq` 与本次 `DBIRTH.bdSeq`；比较主题 `edge_node_id` 是否变化。**当前实现**：解码器以**内存 `DeviceRegistry.birth_seq`** 为基准（同一进程内比对）；以 `st_device_status` 持久化值为权威的路径（`DbWriter.query_last_birth_seq`）属**预留、未接入主链路**，见 `configs/decoder_schema_mapping.json` 的 `rebirth_authority` |
| **处理规则（按优先级）** | ① **同 `device_id` + 同 `bdSeq`** → 视为**重复报文**，忽略，不重置状态；② **同 `device_id` + `bdSeq` 递增** → 视为**正常 re-birth**：更新 `bdSeq`、重置 `seq` 计数、**标记一个"会话边界"时间点**（写入 `st_device_status.reason='rebirth'`）；③ **同 `device_id` + `bdSeq` 回退（变小）** → 视为**异常**（设备侧未持久化 `bdSeq`），记录告警，**仍接受数据但置 `st_device_status.online=FALSE` 且 `reason='rebirth_rollback'`**（该表无 `quality_ok` 列，故以"置离线 + reason 标记"表达"该设备数据不可信"）；④ **`device_id` 相同但 `edge_node_id` 变化** → 视为**设备迁移**，写告警，TAG 随新值更新（TDengine 支持 TAG 在线修改），并在 `known-issues` 记录 |
| **DDATA 与 DBIRTH 的 metric 集合不一致时** | **以最新 `DBIRTH` 为准**（DBIRTH 是"声明"）。`DDATA` 中出现但最新 `DBIRTH` 未声明的 metric → 按 §5.2 处理（旁路 + 告警），**不阻塞整条报文** |
| **局部写入原则** | 一条 `DDATA` 内**逐 metric 校验**：合法 metric 照写，非法 metric 进旁路。**禁止因单个坏 metric 丢弃整条报文** |
| **验证方式** | 模拟器重启一次（bdSeq 递增），确认：数据连续无缺口、`st_device_status` 出现 `rebirth` 记录、旧会话数据未被覆盖 |

### 5.4 边界四：设备离线（NDEATH / DDEATH 处理）

| 项 | 处理 |
|---|---|
| **DDEATH（单设备离线）** | ① 向 `st_device_status` 写入 `online=FALSE, reason='ddeath'`；② 产生 `device_offline` 事件（走 V5.0 §6.5 告警引擎）；③ **不删除任何历史数据**；④ 保持子表存在（避免重建成本与 TAG 抖动） |
| **NDEATH（网关离线，影响面大）** | ① 向 `st_device_status` 写入 `online=FALSE, reason='ndeath'`；② **把该 `edge_node_id` 下所有设备的在册状态批量置离线**（当前实现按解码器内存 `DeviceRegistry.all()` 遍历**本进程已登记**设备；未在本进程登记过的历史设备不回刷，P1 可改为查 `st_device_status`）；③ 产生**聚合告警**（一个网关告警，而非 N 个设备告警），避免告警风暴 |
| **遗嘱消息（MQTT Will）** | Broker 配置 `will` 指向 `spBv1.0/<group>/NDEATH/<node>`（网关）与 `DDEATH` 主题（有能力的设备），确保**异常掉线也能收到离线通知**，不依赖心跳超时 |
| **心跳兜底** | 若设备**未配置 Will**（不可靠设备），用"**超时无数据即离线**"兜底规则：超过 `3 × 上报周期` 无 `DDATA` → 置离线并告警（模拟测点 1Hz，即 **>3s 无数据**触发；真实环境需按实际周期配置）。⚠️ **当前状态：未实现** —— 解码器只处理 `DDEATH`/`NDEATH` 显式离线报文，**没有超时计时器**；已登记为 P1 待办（`docs/known-issues.md` ISS-017） |
| **离线期间的数据** | 一律**不回填**（不猜测缺失值）；`quality_ok` 语义仅描述"该点是否由设备给出"，**不用于插补** |
| **重新上线** | 走 §5.1/§5.3 流程；离线-在线的完整时间线可从 `st_device_status` 还原 |
| **验证方式** | 模拟器发 `DDEATH` → 确认在线状态翻转 + 告警产生 + 历史数据仍可查；再发 `NDEATH` → 确认该网关下多设备被一次性置离线且只产生 1 条聚合告警 |

---

## 六、待验证的风险点清单

| 编号 | 风险点 | 影响 | 验证方式 | 状态 |
|---|---|---|---|---|
| **R-V3-1** | **TDengine 社区版（OSS）是否含 SparkplugB 接入**（`taosX` 解码能力） | **若为商业功能，整条接入路线作废** | **T1.9 首步查证**；产出 `reports/v3-auth.md` | **已定稿（2026-09-24）**：官方连接器仅 All-in-One/Enterprise；**OSS + 自研解码器 ≤2 天**（判需降级·有条件通过） |
| **R-V3-2** | taosX 是否支持**自定义 metric → 列映射**，还是只能原样落库 | 若只能原样，需自研消费者并做映射 | 用模拟器灌数，检查落库列名 | 待 D4–D5 |
| **R-V3-3** | Sparkplug `seq` 为 **0–255 循环**，高频下易误判丢包 | 丢包统计失真 | 用 seq 差值与时间差联合判定；模拟器注入丢包测试 | 待 D4–D5 |
| **R-V3-4** | **Broker 选型反向推翻内存预算**（若必须用 EMQX） | V4b 判据失准，须重算内存 | V3 Step1 定 Broker 后**按最重方案重算** | 待 D4–D5 |
| **R-V3-5** | 中文/特殊字符 `device_id` 导致子表名非法 | 建表失败 | 约定 `device_id` 仅 `[A-Za-z0-9_-]`；消费者侧校验并拒绝非法 ID | ✅ **已实现**（`TopicParser.is_valid_device()` + `handle_bytes` 对 DBIRTH/DDATA/DDEATH 校验；SQL 标识符另加白名单，2026-09-29） |
| **R-V3-6** | TDengine 与 taosX/taosExplorer **版本配套关系** | 组件不兼容 | 以官方配套表确认后再锁定（写入 `docs/version-lock.md`） | ✅ **已闭环**（锁定 `tdengine/tsdb:3.3.8.0@sha256:36e2bf82…`；OSS 无 taosX/连接器，已定稿自研解码器路线，见 `reports/v3-auth.md` §三） |
| **R-V3-7** | 时钟不同步（设备本地时间 vs 服务器）导致乱序写入 | 窗口聚合结果错误 | 统一 NTP；消费侧对**超窗（>10min 偏差）**数据打标并旁路 | 待实现 |
| **R-V3-8** | `quality_ok` 语义被误用于插补缺失值 | 结论失真、幻觉风险 | 在 `query_sensor` 契约中**明确禁止插补**，只返回原始统计 | 契约已声明 |
| **R-V3-9** | 高频写入（1Hz × 3 测点 × 多设备）下的 TDengine WAL/落盘压力 | 影响 V4b 资源实测 | 纳入 V4b 全组件压测矩阵 | 待 D8 |
| **R-V3-10** | 未登记 metric 长期堆积在旁路表无人归并 | 数据资产浪费、schema 漂移无人察觉 | `schema_drift` 告警接入 `known-issues` 跟踪闭环 | 待实现 |

### 6.1 关于 `device_id` 的两套校验口径（**有意并存，非矛盾**）

| 位置 | 正则 | 用途 | 违规处置 |
|---|---|---|---|
| `configs/decoder_schema_mapping.json` → `device_id_validation.regex` | `^[A-Za-z0-9_-]+$` | **解码/入库侧宽松口径**：只拦非法标识符与 SQL 注入面（反引号、空格、引号、分号等），放行网关可能下发的各种合法编号 | 丢弃该报文 + 写 `device_id_invalid` 告警，**不进入子表名与 SQL**（2026-09-29 起在 `handle_bytes` 对 DBIRTH/DDATA/DDEATH 生效） |
| `schemas/tools_v1.json`（`query_sensor` / `get_maintenance_history` / `generate_report`） | `^[A-Z][A-Z0-9-]{2,31}$` | **工具契约侧严格口径**：面向用户的规范化设备编号（大写字母开头 + 数字 + 连字符） | 由参数校验拒绝，返回参数错误 |

两者服务于不同边界（"能不能安全入库" vs "用户查询是否规范"），**不要求取值域相同**。
若需收敛为同一口径，须先升 `schemas/tools_v2.json`（冻结纪律，见 `schemas/tools_v1.json` 的 `change_policy`）并同步本表。

---

## 七、DoD 自查（M0.3 对应项）

- [ ] Sparkplug B 主题结构解析完成，7 类报文语义明确（§二）
- [ ] metric → 列映射表定稿，含单位与 TAG 划分（§三）
- [ ] 超级表设计完成，普通列/TAG 划分理由成文（§四）
- [ ] `CREATE STABLE` SQL 可执行（§4.4）
- [ ] **4 类边界情况逐条给出确定行为**（§五）——建表 / 新增 metric / re-birth / 离线
- [ ] `query_sensor` 聚合契约对应查询示例可用（§4.5）
- [ ] 待验证风险点清单已登记（§六），R-V3-1 已转 `docs/risk-register.md`（R8）
- [ ] 授权结论产出（`reports/v3-auth.md`，D1 起）→ **M0.3 前置**