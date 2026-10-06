# 自研 Sparkplug B 解码器方案 + 工期估算

> **对应任务**：T1.9 落地裁定 = 需降级（OSS + 自研解码器 ≤2 天）
> **落点**：V3 时序接入的**消费者侧**（替代官方 Sparkplug B 连接器，官方连接器仅随 All-in-One/Enterprise IDMP+taosX 体系）
> **里程碑**：M0.3（D4–D5）
> **关联文档**：`reports/v3-auth.md`（授权定稿 §四.1 / 接入方案 §五–§八 / 量化工时 §三）、`docs/schema-mapping.md`（映射 + 四类边界）、`docs/data-sources-v1.md`（模拟测点）
> **主场景**：离心泵轴承振动异常诊断
> **日期**：2026-09-24
> **判定**：**工期估算 ≈ 1.5~2 人日（在 ≤2 天红线内）→ 判「需降级（有条件通过）」成立，本项目采用**

---

## 〇、方案结论速览

| 项 | 结论 |
|---|---|
| 判定形态 | ⚠️ **需降级 · 有条件通过（本项目采用）** |
| 方案 | **OSS TDengine `tdengine/tsdb` + 自研 Sparkplug B 解码器（消费者）** |
| 解码方式 | 订阅 Mosquitto → 解析 Sparkplug B Protobuf → 按 `schema-mapping.md` 落 TDengine `st_pump_metrics` 超级表 |
| 复用 | 完全复用 `docs/schema-mapping.md` 的映射表 + 四类边界约定，**不重写映射**（P0 资产直接拐弯） |
| 工期估算 | **核心 1.5 人日 + 缓冲 0.5 人日 ≈ 2 人日（≤2 天红线）** |
| 超期回退 | 若 >2 天 → 改判 **No-Go**，切 **MQTT JSON 直写**（放弃 Sparkplug B 语义） |
| 不计入本期 | 生产级运维、监控告警接入、（属后续阶段） |

> **红线**：工期测算全程按 §三 量化口径，**不得把 2 天的口子开成 2 周**。若任一步骤估算 >0.5 人日，需显式标注并复核。

---

## 一、要做什么（定位清楚）

自研解码器的职责 = **在「MQTT 上的 Sparkplug B 二进制报文」与「TDengine 时序库」之间做有损度可控的翻译**。它不承担：

- ❌ Broker 职责（Mosquitto 做，见 `reports/v3-auth.md` §五）；
- ❌ Schema 映射维护（`docs/schema-mapping.md` 已定稿，解码器只**读**它）；
- ❌ 告警规则计算（告警在应用层，见 `reports/v3-auth.md` §八 路线 A）；
- ❌ 流式计算引擎（不引入 taosX 流式计算）。

**它只负责三件事**：订阅 + 解析 + 写入，外加四类边界处置。

---

## 二、组件与数据流

```
 ┌──────────┐  spBv1.0/plant1/+/gw-pump-01/+(PUMP-*)   ┌────────────────────────────┐
 │ Mosquitto│ ──────────────────────────────────────→ │  self_decoder（自研消费者） │
 │   :1883  │                                          └────────────────────────────┘
 └──────────┘                                          │ 精订阅：spBv1.0/plant1/+/gw-pump-01/#（`+` 匹配 message_type，含 NBIRTH/NDATA/NDEATH/DBIRTH/DDATA/DDEATH，STATE 由解码器忽略）
                                                        │         （STATE 忽略）
                                                        ▼
                                        ┌─────────────────────────────────────────┐
                                        │ ① Protobuf 解析（sparkplug_b.proto）      │
                                        │ ② 报文分流：DBIRTH/DDATA/NDEATH/DDEATH…   │
                                        │ ③ metric→列映射（读 schema-mapping.md）  │
                                        │ ④ 四类边界处置（建表/新增/re-birth/离线） │
                                        └─────────────────────────────────────────┘
                                                        │ taospy / taosAdapter REST
                                                        ▼
                                        ┌─────────────────────────────────────────┐
                                        │ TDengine `st_pump_metrics`（超级表）+     │
                                        │ `st_unmapped_metrics`（旁路）+             │
                                        │ `st_device_status`（在线状态）            │
                                        └─────────────────────────────────────────┘
```

**关键组件**：

| 组件 | 选型 | 理由 | 备注 |
|---|---|---|---|
| MQTT 客户端 | `paho-mqtt`（Python） | 成熟、纯标准 MQTT 3.1.1，Sparkplug B 只依赖 3.1.1 | 已随本项目 Python 3.12 栈 |
| Protobuf 解析 | 官方 `sparkplug_b.proto` + `grpcio-tools`（或 `protobuf`）预生成 PB 类 | Sparkplug B 为 Protobuf 编码；**用官方 .proto 而非第三方封装库**，规避第三方库与规范版本漂移 | 版本锁定为 Sparkplug B **规范 3.3.x** 配套 .proto |
| TDengine 写入 | `taospy`（官方 Python 客户端，走 6041） | 原生 `INSERT ... USING ... TAGS()` 语法最贴合 schema-mapping §4.4 | 串行批量写入，避免高频建连接 |
| 配置 | 读 `schema-mapping.md` 的映射表（机器可读子集，见 §七） | 解码器不硬编码映射，P0 资产复用 |

---

## 三、解码器内部模块拆解 + 工期估算

> 工期对齐 `reports/v3-auth.md` §三 量化口径。每项给出「计入/不计入」归属。

### 3.1 模块划分与工时

| # | 模块 | 职责 | 计入项 | 估算 |
|---|---|---|---|---|
| M1 | **proto 工程** | 引入官方 `sparkplug_b.proto`，生成 PB 类，写最小解析 smoke 测试 | 解码器实现（协议解析基础） | 0.25 人日 |
| M2 | **订阅与报文分流** | paho 连接 Mosquitto、精订阅主题、按 message_type 分发给 handler | 解码器实现 | 0.25 人日 |
| M3 | **DBIRTH 处理** | 建表/校验表结构、记录 `bdSeq`、映射校验（schema-mapping §5.1） | 边界处理「建表」 | 0.25 人日 |
| M4 | **DDATA 处理** | 逐 metric 映射写入，含未登记→旁路 + `schema_drift` 告警（schema-mapping §5.2、§5.3 局部写入原则） | 解码器实现 + 边界「新增 metric」 | 0.3 人日 |
| M5 | **NDEATH/DDEATH 处置** | 在线状态翻转、网关级聚合告警（schema-mapping §5.4） | 边界「离线」 | 0.15 人日 |
| M6 | **re-birth / 冲突判定** | `bdSeq` 比对、会话边界、`quality_ok` 标注（schema-mapping §5.3） | 边界「re-birth」 | 0.3 人日 |
| — | **与模拟器联调** | 起 Mosquitto + 自建/现成 Sparkplug B 模拟器灌数，验证 4 类边界 + 异常容错 | 验证（联调 + 异常报文容错） | 0.4 人日 |
| | **合计** | | | **≈ 1.9 人日**（核心 1.5 + 验证 0.4） |

### 3.2 缓冲与红线

| 项 | 说明 |
|---|---|
| 缓冲 | 计入 M1 的 smoke + M6 的冲突判定为高不确定项，已含在单模块内；**不再额外放大**（防口子变大） |
| 超期判据 | 若 M1–M6 实施后实测投入 >2 人日 → **改判 No-Go**，切换 `reports/v3-auth.md` §三 备选（MQTT JSON 直写） |
| 严控点 | M4 的「未登记 metric → 旁路」是环上加码点，若发现难以收敛 → 用最小实现（只写正常列，旁路先落 JSON 日志）占位，不阻塞整条链路 |

### 3.3 不计入项（不占工期）

生产级运维、监控告警接入、多网关水平扩展、Sparkplug B 全 datatype 支持（本项目仅 Double/Float/Boolean，见 schema-mapping §二.4）。

---

## 四、技术选型理由

| 决策 | 选择 | 理由 |
|---|---|---|
| 不用 Sparkplug 第三方封装库而定官方 .proto | 官方 .proto + 编译 | 封装库维护滞后、版本漂移风险高；官方 .proto 是规范本体，可控、可锁定版本 |
| 走 taosAdapter REST 而非直连 taosd | `taospy`（6041） | schema-mapping §4.4 的 `INSERT ... USING ...` 语法经 REST 稳定可达；端口 6041 已测空闲 |
| 精订阅设备级主题 | `spBv1.0/plant1/+/gw-pump-01/#`（`+` 匹配 message_type） | 只收本项目设备，降低误收与带宽；message_type 由解码器按需分发 |
| 无序丢弃，逐 metric 校验 | 局部写入原则 | schema-mapping §5.3：禁止因单个坏 metric 丢整条报文 |

---

## 五、与 schema-mapping 四类边界的对应（验收锚点）

| 边界 | schema-mapping 约定 | 自研解码器落地动作 |
|---|---|---|
| 建表（DBIRTH） | §5.1：`INSERT ... USING ... TAGS()` 自动建子表 | M3：首次 DBIRTH → 自动建 `d_plant1_PUMP-A`；验证 `SHOW TABLES` |
| 新增 metric | §5.2：未知 metric → 旁路 + `schema_drift`，禁止自动 ALTER | M4：未登记 → `st_unmapped_metrics` + 告警；主表 DESCRIBE 不变 |
| re-birth | §5.3：`bdSeq` 递增判定，回退标 `quality_ok=FALSE` | M6：比对 `st_device_status.birth_seq`，写 `reason='rebirth'` |
| 离线 | §5.4：DDEATH/NDEATH 翻转状态，网关级聚合告警，不删数据 | M5：写 `online=FALSE` + 单/聚合告警 |

> **验收标准**：四类边界各观察一个确定行为（不依赖主观判断），任何一类无结论 → 本方案不得判完成（对齐 `reports/v3-auth.md` §6.2 纪律）。

---

## 六、工期估算结论与判定

| 项 | 值 |
|---|---|
| 总工期估算 | **≈ 1.9 人日（≤2 天红线内成立）** |
| 判定 | **需降级（OSS + 自研解码器 ≤2 天）＝ 有条件通过，本项目采用** |
| 超期回退 | 实测投入 >2 人日 → No-Go → MQTT JSON 直写（放弃 Sparkplug B 语义） |

> **量化口径依据**：`reports/v3-auth.md` §三「≤2 天的量化口径」（解码器实现 + 四类边界处理 + 联调验证，不含生产运维），全部落在本方案 §3.1 的 M1–M6 中。

---

## 七、落地前置与待补项

| # | 待补项 | 说明 | 时刻 |
|---|---|---|---|
| 1 | `schema_mapping` 机器可读子集 | **✅ 已完成（2026-09-24）**：`configs/decoder_schema_mapping.json`（含 `st_pump_metrics` 列/TAG/单位映射、`st_unmapped_metrics` 旁路、`st_device_status` 在线、主题消息分发、四类边界处置、`device_id` 校验正则），解码器只读它 | D4 |
| 2 | Sparkplug B 模拟器 | 造 NBIRTH/DBIRTH/DDATA/DDEATH/NDEATH 报文灌数（自建或现成） | D4–D5 |
| 3 | 精确 tag/digest | **✅ 已完成（2026-09-24）**：`tdengine/tsdb:3.3.8.0` 实测 digest `sha256:36e2bf82...d2256bf`（1.68GB）已锁入 `docs/version-lock.md` §二.2.1；解码器 Python 依赖已登记 §二.2.7（protobuf 7.36.2 / grpcio 1.84.0 实测；paho-mqtt 2.1.0 / taospy 2.8.10 / grpcio-tools 1.84.0 待装） | D4（装后 `pip freeze` 复核） |
| 4 | `docker/compose.ingest.yml` | **✅ 已完成（2026-09-24，2026-09-29 方案 A 调整）**：`docker/compose.ingest.yml`（Mosquitto + TDengine`3.3.8.0` 常驻两件套 + 模拟器不进 compose；**2026-09-29 起解码器移出 compose 改本地直跑**），见 §八 | D4–D5 |

---

## 八、Sparkplug B 模拟器方案（待补项 #2）

> **目的**：产生 `NBIRTH / DBIRTH / DDATA / DDEATH / NDEATH` 报文灌数，覆盖 `reports/v3-auth.md` §6.2 四类边界（建表 / 新增 metric / re-birth / 离线）。

### 8.1 方案选择：现成镜像 vs 自建

| 选项 | 可用性 | 是否采用 | 理由 |
|---|---|---|---|
| 现成 Sparkplug B 模拟器镜像 | ⚠️ 生态稀少，无权威官方镜像，镜像版本与 Sparkplug B 规范版本漂移风险 | ❌ **不采用** | 无法锁定规范化源；digest/版本不可控，违背本项目「可复现」纪律 |
| **自建（本项目采用）** | 基于方案 §二 ~四 解码器同源的 Sparkplug B Python 生态 | ✅ **采用** | 与解码器共用 `.proto` 与规范版本，报文可精确编排以覆盖四类边界；轻量、可控、可锁定 |

### 8.2 自建模拟器设计

| 项 | 设计 |
|---|---|
| 形态 | 一个 Python 脚本（复用方案 §四 的 `paho-mqtt` + `.proto`），非容器 | 镜像 |
| 命名 | `scripts/spb_simulator.py`（含 `--selftest` / `--scenario birth,new_metric,rebirth,offline`） |
| 连接 | 连 Mosquitto `1883`，发布到 `spBv1.0/plant1/{DBIRTH|DDATA|DDEATH|NDEATH}/gw-pump-01/{device_id}` |
| 主题/输入 | 复用 `configs/decoder_schema_mapping.json` 的 `group_id=plant1`、`edge_node_id=gw-pump-01`、message_types 分发 |
| 报文清单 | `NBIRTH`（网关）+ `DBIRTH`（设备声明 `device_type` 等 TAG）+ `DDATA`（6 个 normal metric + `metric_quality`）+ `DDEATH`（离线）+ `NDEATH`（网关离线） |
| 边界场景 | `--scenario` 驱动：建表（正常 DDATA）→ 新增 metric（DDATA 里加未知名为 `VIB_BAND_1`）→ re-birth（重发 DBIRTH，bdSeq 递增）→ 离线（DDEATH + 停心跳） |
| 心跳/频率 | 默认 1 Hz 上报周期，心跳间隔对齐 `decoder_schema_mapping.json.offline.heartbeat_timeout`（3.5s） |
| 校验点 | 每个场景结束后打印已发布报文摘要，供解码器侧断言 |

### 8.3 模拟器与解码器、`compose.ingest.yml` 的配合

```
compose.ingest.yml 起： mosquitto :1883   +   tdengine(tsdb:3.3.8.0)     （常驻两件套）
                          ↑                        ↑
spb_simulator.py 发报文          self_decoder 本地直跑订阅 + 写入 st_pump_metrics
本地直跑解码器： .venv\Scripts\python.exe scripts\self_decoder.py \
                     --schema-mapping configs/decoder_schema_mapping.json \
                     --mqtt-host 127.0.0.1 --td-host 127.0.0.1
```

- 模拟器**不进** `compose.ingest.yml`（是验证工具，随 `--scenario` 手动跑），与解码器 `--selftest` 同层；
- `compose.ingest.yml` 只编排**常驻两件套**：Mosquitto、TDengine（**2026-09-29 方案 A**：自研解码器移出 compose，改由本地 /venv python 直跑，连接 127.0.0.1；`Dockerfile.decoder` 保留为弃用形态供审计追溯，详见其文件头注释）。

### 8.4 待补项 #2 状态

| # | 待补项 | 说明 | 时刻 |
|---|---|---|---|
| 2 | **Sparkplug B 模拟器** | **方案已定稿（2026-09-24）**：自建 `scripts/spb_simulator.py`，带 `--selftest` / `--scenario`；报文与边界对齐 §8.2；**已实现（`--selftest` 通过）**，真实灌数填报待 D4 后续 | D4–D5 |

---

## 修订记录

| 日期 | 修订人 | 原因 |
|---|---|---|
| 2026-09-24 | 本人 | 初始建立：承 Q「OSS + 自研解码器」裁定，产出方案与工期估算以闭合 `reports/v3-auth.md` §三 |
| 2026-09-24 | 本人 | **补 #2/#4**：新增 §八 Sparkplug B 模拟器方案（自建 `scripts/spb_simulator.py`）；创建 `docker/compose.ingest.yml`（Mosquitto + TDengine`3.3.8.0` + 自研解码器三件套）；待补项 #1/#3/#4 标 ✅，#2 方案定稿待实现 | §七、§八 |
| 2026-09-24 | 本人 | **编码阶段（U-08）落地**：`scripts/self_decoder.py`（M1–M6，`--selftest` 通过）、`scripts/spb_simulator.py`（`--selftest` 通过）、`docker/Dockerfile.decoder` 实现；`.proto` 落地 `protos/`；订阅主题改为 MQTT 合法通配符 `+/`（原 `{A,B,C}` 非法）；写入通道改为 REST 6041 + `taosrest`（随 taospy 自带）；待补项 #2 标「已实现，真实灌数填报待后续」 | §二、§四、§五、§八.4 |
| 2026-09-29 | 本人 | **方案 A：解码器转本地直跑**：拆除非布 `compose.ingest.yml` 改常驻两件套（Mosquitto + TDengine），自研解码器移出 compose、由本地 /venv python 直跑（连 127.0.0.1 的 1883/6041）；`Dockerfile.decoder` 保留为弃用形态供审计追溯；同步 §7 checklist、§8.3 | §7.4、§8.3、§8.5 |