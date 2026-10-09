-- =============================================================
-- A2 时序 Schema 权威 DDL —— 自研 Sparkplug B 解码器写入目标
-- -------------------------------------------------------------
-- 上游依据：  plan/p1-plan-detailed.md §四 D2（A2）、§5.2
-- 权威源：    configs/decoder_schema_mapping.json（唯一机器可读映射真相）
--            本文与 decoder_schema_mapping.json 保持数据镜像一致（项目硬性约束）
-- 目标实例：  TDengine OSS 3.3.8.0（REST 6041），库 iot
-- 幂等：      CREATE ... IF NOT EXISTS，可重复执行
-- 建表常态：  实际建表由解码器 `init_schema()` 启动时幂等完成（INSERT...USING...TAGS 自动建子表）
--            本文为【人工审计/重建成表】用权威 SQL，两者 schema 必须一致
--
-- 用法（容器内 taos，或 root:taosdata 经 REST 6041）：
--   docker exec -i auscult-ingest-tdengine taos < configs/tdengine/schema_master.sql
-- =============================================================

CREATE DATABASE IF NOT EXISTS iot KEEP 365 DURATION 10 PRECISION 'ms' WAL_LEVEL 1;

-- ---------------- 超级表 1：设备遥测（主判据量） ----------------
-- 普通列：随时间连续变化的测量值（列式存储、时间降序）
-- TAG：device_id 负责人筛选；device_model 可区分型号
-- 注意：vib_rms 等测量值【不得】设为 TAG（会导致标签基数爆炸、写入性能崩溃）
CREATE STABLE IF NOT EXISTS st_pump_metrics (
    ts            TIMESTAMP,   -- 主时间列（精度 ms）
    vib_rms       DOUBLE,      -- 振动有效值 mm/s（主判据量，告警阈值比对对象）
    vib_peak      DOUBLE,      -- 振动峰值 mm/s（冲击判定）
    vib_kurtosis  DOUBLE,      -- 峭度，无量纲（轴承早期故障敏感）
    bearing_temp  DOUBLE,      -- 轴承温度 degC
    motor_current DOUBLE,      -- 电机电流 A
    pump_speed    DOUBLE,      -- 转速 rpm（特征频率计算必需）
    quality_ok    BOOL         -- 数据质量标记（metric_quality 折算）
) TAGS (
    group_id     NCHAR(32),
    edge_node_id NCHAR(64),
    device_id    NCHAR(64),
    device_type  NCHAR(32)
);

-- ---------------- 超级表 2：未登记 metric 旁路（不静默丢弃） ----------------
CREATE STABLE IF NOT EXISTS st_unmapped_metrics (
    ts          TIMESTAMP,
    metric_name NCHAR(64),
    value_num   DOUBLE,
    value_str   NCHAR(128),
    quality_ok  BOOL
) TAGS (
    group_id     NCHAR(32),
    edge_node_id NCHAR(64),
    device_id    NCHAR(64)
);

-- ---------------- 超级表 3：设备在线/离线状态 ----------------
CREATE STABLE IF NOT EXISTS st_device_status (
    ts        TIMESTAMP,
    online    BOOL,
    birth_seq BIGINT,   -- bdSeq
    last_seq  INT,      -- 最近 seq（丢包检测）
    reason    NCHAR(64)
) TAGS (
    group_id     NCHAR(32),
    edge_node_id NCHAR(64),
    device_id    NCHAR(64)
);

-- ---------------- 子表命名约定 ----------------
-- d_{group_id}_{device_id}  遥测子表（st_pump_metrics）
-- u_{group_id}_{device_id}  未登记旁路子表（st_unmapped_metrics）
-- s_{group_id}_{device_id}  在线状态子表（st_device_status）
-- TDengine 要求子表名全局唯一，故三表互斥前缀，不能跨超级表同名。