# V3 报告 —— TDengine + Sparkplug B 授权与接入（T1.9 + D4–D5）

> 验证项：**V3 TDengine + Sparkplug B 接入**
> 对应任务：**T1.9（D1 首步，硬门禁）** + V3 Step1–3（D4–D5）
> 出口里程碑：**M0.3**（D5）；其中 **第一段（授权结论）为 D1 / M0.1 的必出项**
> 资源占用：CPU
> 项目：云侧工业 IoT 诊断 Agent 系统 · 主场景：离心泵轴承振动异常诊断
> 项目根：`<REPO>`

---

## 〇、报告状态声明

**本报告当前状态 = ④【全部实测完成并定稿】**

> ⚠️ **本报告结构特殊，请按两段分别阅读。**

| 段落 | 内容 | 计划时点 | 当前状态 |
|---|---|---|---|
| **第一段** | **T1.9 授权结论** | **D1（M0.1 必出项）** | ✅ **已定稿（文档层 + 实物层，2026-09-24）** —— 判定 **需降级（OSS + 自研解码器 ≤2 天）**；授权不阻塞 |
| **第二段** | D4–D5 接入方案（Broker / Schema 映射 / `query_sensor` 契约 / 告警路线） | D4–D5（M0.3） | ✅ **实测完成（2026-09-28）** —— 接入链路、四类边界、`query_sensor` 契约、告警路线 A 均已实测，**四部分判据全部达成**（见 §十二.12.2） |

> **⚠️ 关键：本第一段判定经查证后定为「需降级」= OSS + 自研解码器，**非官方 Sparkplug B 连接器（仅 All-in-One/Enterprise IDMP+taosX 体系）。落地裁定与依据见 §四.1。
>
> - ✅ **已实测（第一段 · 授权）**：端口 6030 / 6041 / 1883 实测空闲；TDengine 相关端口无冲突；`tdengine/tsdb:3.3.8.0` 镜像内**无 taosX / Sparkplug B 连接器**（渠道 3/4）。
> - ✅ **已实测（第二段 · 接入）**：Broker、Schema 映射四类边界、`query_sensor` 契约（P95≈26.2ms）、告警路线 A（Must#1/Must#2 均 PASS）——四部分判据全部达成（2026-09-28）。
> - ✅ **自研解码器**：方案 + 工期估算已定稿（≈1.9 人日，≤2 天成立，见 `docs/sparkplug-b-decoder.md`）。
- ❌ **绝不编造**：授权边界结论、映射正确性结论、契约可行性结论——凡未验证一律标 `【待 D1 查证填入】` / `【待 D5 实测填入】`。

> **为什么第一段如此关键**：TDengine 授权是**唯一不可控的外部依赖**（对应 R8、R15）。如果社区版不含 Sparkplug B 接入且连接器需商业授权，则整个时序接入路线的组件选型要被推翻。所以它必须在 D1 就出结论，**不通过即刻启动降级评估**，不留到 D4。

---

## 第一段（T1.9 · D1 必出）—— 授权结论

### 一、要查证的问题

#### 1.1 核心三问

| 编号 | 问题 | 为什么必须问清楚 |
|---|---|---|
| **Q-A** | TDengine **社区版（OSS）** 是否包含 **Sparkplug B** 接入能力？ | 若不含，"MQTT + Sparkplug B → 时序库"这条路必须重建 |
| **Q-B** | **taosX 连接器**（含 MQTT / Sparkplug 类）是否需要**商业授权**？ | 连接器是官方推荐路径，授权边界直接决定成本与可行性 |
| **Q-C** | 边界在哪里？ | 即：哪些能力在 OSS 内、哪些属于企业版/商业授权，必须落到**具体条目**而非"大概可以" |

#### 1.2 边界细化的追问清单

| # | 追问 | 期望得到的结论形态 |
|---|---|---|
| 1 | OSS 版是否内置 Sparkplug B **解码**，还是只支持裸 MQTT JSON？ | 是 / 否 / 需插件 |
| 2 | taosX 是否随 OSS 发行包提供？是否需额外 license 文件？ | 随包 / 需 license / 仅企业版 |
| 3 | 是否存在"连接器数量上限""并发上限""测点数上限"的授权限制？ | 具体数字或"无" |
| 4 | 是否允许**自研消费者**（自己订阅 MQTT 再写入 TDengine）？有无授权障碍？ | 允许 / 有限制 |
| 5 | 社区版是否有**功能开关**（如某类 connector 需 enterprise flag）？ | 有 / 无，具体开关名 |
| 6 | 后续升级路径：若 P1 阶段需企业能力，迁移成本多大？ | 定性 + 关键动作 |
| 7 | 生产/商用是否需要额外授权（即使 OSS 功能可用）？ | 是 / 否，引用具体条款 |

### 二、查证渠道与动作清单

> **要求**：每条渠道都要留下"查了什么、看到什么、结论是什么"三行记录。**不接受"我记得应该是"这种口径。**

| # | 渠道 | 具体动作 | 落点证据 | 状态 |
|---|---|---|---|---|
| 1 | **官方文档** | 检索 TDengine 官方文档中关于 **Sparkplug B**、**MQTT 接入**、**taosX / 数据接入** 的章节；确认该章节标注的版本适用范围（社区版 / 企业版） | ✅ **已查证（2026-09-24）**：官方 SparkplugB 接入经 **Explorer 界面 / taosX 连接器**写入；「IDMP Data In 需 Enterprise TSDB」「社区版 TSDB 不含 taosExplorer」（`idmpdocs.tdengine.com`）| ✅ 完成 |
| 2 | **官方文档 —— 版本对比页** | 找 OSS 与 Enterprise 的**功能对比矩阵**，定位 connector / Sparkplug 所在行 | ✅ **已查证（2026-09-24）**：免费层（`tdengine.com/free-tier`）≤5000 tags 永久免费、含 20 零代码连接器、明确列出 「MQTT / **Sparkplug B Data**」；同时官方原话「依赖企业版的能力（如 taosX 零代码接入）需 Enterprise」——**纯 TSDB-OSS 不含 taosX** | ✅ 完成 |
| 3 | **license 文件** | 检查本机 TDengine 镜像/安装包内的 `LICENSE`、`NOTICE`、`README`；核对是否有 connector 相关附加条款 | ✅ **已执行（2026-09-24）**：`tdengine/tsdb:3.3.8.0` 容器内无独立 LICENSE 文本文件（仅 AGPL 合规声明）；镜像声明为 TSDB-OSS | ✅ 完成 |
| 4 | **发行包内容核对** | 在 TDengine 容器/安装目录内确认 **taosX 是否随包存在**（可执行文件、目录、配置项） | ✅ **已执行（2026-09-24）**：`bin/` 含 `taosd/taosadapter/taos/taos-explorer/taosmqtt/taoskeeper`；**无 taosX、无 connector 目录、无 Sparkplug B 连接器**；`taosmqtt` 为基础 MQTT 裸写入 | ✅ 完成 |
| 5 | **社区口径** | 官方社区/issue/FAQ 中检索同类问题（"Sparkplug OSS"、"taosX license"），确认官方答复 | ⏳ **部分**：free-forever 公告（2026-07-28）未点名 Sparkplug B，仅说 MQTT；结论以实物层为准 | ☐ 可留档 |
| 6 | **商务口径** | 若前 5 项存在歧义，通过官方商务/销售渠道确认商用授权边界 | ⏳ **仅在仍有歧义时动用**；当前文档+实物已足够支撑「可用（Free Tier）」 | ☐ 未动用 |

**执行顺序（有讲究）**：先 1→2（文档层）→ 再 3→4（实物层，最硬的证据是"发行包里到底有没有"）→ 再 5（社区交叉验证）→ 最后 6（只在前述仍有歧义时才动用，因为商务口径耗时不可控）。

> ⚠️ **在第 6 项悬而未决时，不得把 V3 判定为 Pass**；宁可先按"需降级"推进，也不要把外部依赖当成已完成。

### 三、三种结论形态的判定标准

| 结论形态 | 判定标准 | 后续动作 |
|---|---|---|
| **✅ 可用（Free Tier ≤5000 tags）** | 采用 **TDengine All-in-One Free Tier**（≤5000 tags 永久免费）提供**官方零代码连接器**，官方 free-tier 页明确列出 **Sparkplug B Data**；受 ≤5000 tags 上限 + 1 年期免费授权（免费续期、激活时需临时联网）约束 | ⚠️ **本项目不采用（2026-09-24 裁定）**，因引入 IDMP/TDgpt 等企业级组件、违背 MVP 省内存原则；本轮"可用"仅记录为授权不阻塞的旁证 |
| **⚠️ 需降级（本项目采用）** | **采用 OSS 镜像 `tdengine/tsdb`** 作为时序库，**自研 Sparkplug B 解码器**（订阅 MQTT → 自行解析 DBIRTH/DDATA/NDEATH → 写入 TDengine），**自研工作量 ≤2 天** | **已裁决采用**：启动自研解码器方案设计 + 工期估算（§三 量化口径）；判"有条件通过"；若耗时 >2 天改判 No-Go |
| **❌ No-Go** | 需要**商业授权**才能获得必需的接入能力；或授权边界**不可控**（口径不清、无法书面确认、依赖商务谈判） | 切换备选方案：**MQTT JSON**（放弃 Sparkplug B 语义）或**自研消费者**（完全绕开官方连接器）；同步评估对 MVP 范围与 P1 工期的影响 |

> **路径澄清（2026-09-24 查证新增）**：本判定不再笼统称"社区版"，而是明确三条产品路径——**① Free Tier All-in-One（≤5000 tags 免费，含零代码连接器）② TSDB-OSS 纯内核（AGPL，无 taosX）③ Enterprise/Cloud（商业授权）**。**本项目裁定走 ②（OSS + 自研解码器）**，理由是轻量、省内存、代价 ≤2 天。

**"≤2 天"的量化口径**（避免自研工作量被低估）：

| 评估项 | 计入项 |
|---|---|
| 解码器实现 | Sparkplug B 的 birth/death/DBIRTH/DDATA 报文解析 + metric 映射 |
| 边界处理 | 建表 / 新增 metric / re-birth / 离线 四类边界（与第二段 Schema 映射对齐） |
| 验证 | 与模拟器的联调 + 异常报文容错 |
| **不计入** | 生产级运维、监控告警接入（属后续阶段） |

> 若评估结果 >2 天，**不得**写成"需降级（有条件通过）"，应判定为 No-Go 并切备选方案——否则就是把 2 天的口子开成 2 周。

### 四、当前状态与不通过时的立即动作

#### 4.1 当前状态

> ## ✅ **【第一段已定稿 —— 2026-09-24 查证】判定 = 需降级（OSS + 自研 Sparkplug B 解码器 ≤2 天）**
>
> **授权事实（渠道 1/2 文档层 + 3/4 实物层均已执行）**：
> 1. `tdengine.com/free-tier`：≤5000 tags 免费；官方列出「MQTT / Sparkplug B Data」；纯 **TSDB-OSS 不含 taosX**；
> 2. 官方 SparkplugB 接入文档：写入经 **Explorer 界面 / taosX 连接器** 实现；
> 3. **【实物层 2026-09-24 实测】** `docker pull tdengine/tsdb:3.3.8.0`（digest `sha256:36e2bf82...256bf`）：**`taosX` 无、`connector/` 目录无、Sparkplug B 连接器无**；`taosmqtt` 为基础 MQTT 裸写入。
>
> **授权通道结论**：Sparkplug B 官方连接器**只随 All-in-One/Enterprise（IDMP+taosX 体系）**；OSS 社区版不含，Sparkplug B 连接器需自研或走 All-in-One。
>
> **落地裁决（用户 2026-09-24 选定）**：**OSS 社区版 + 自研 Sparkplug B 解码器（≤2 天）**，放弃 All-in-One/官方连接器，维护 MVP 省内存轻量原则。自研工作量按 §三 量化口径评估，>2 天即回退 No-Go（MQTT JSON 直写）。**方案 + 工期估算已定稿（≈1.9 人日，≤2 天成立），见 `docs/sparkplug-b-decoder.md`。**
>
> **结论形态 = ⚠️ 需降级（有条件通过）**。授权不构成阻塞（OSS 免费可用），落地用 OSS 镜像 `tdengine/tsdb` + 自研解码器。

| 项 | 状态 |
|---|---|
| Q-A（含 Sparkplug B 接入） | ⚠️ 官方连接器仅 All-in-One/Enterprise；**OSS 不含（已实物核验）** → 自研解码器 |
| Q-B（taosX 是否需商业授权） | ⚠️ Enterprise 才随 taosX 零代码接入；**本项目不入其体系，用 OSS + 自研** |
| Q-C（边界细化 7 问） | ✅ **文档层 + 实物层（渠道 3/4）均已执行**：OSS 镜像实测无 taosX/连接器 |
| 结论形态判定 | ⚠️ **需降级（OSS + 自研 Sparkplug B 解码器 ≤2 天）**（用户 2026-09-24 裁定）；**方案+工期已定稿（≈1.9 人日，见 `docs/sparkplug-b-decoder.md`）** |

**已确认的环境事实（实测）**：

| 项 | 实测值 |
|---|---|
| 端口 6030（TDengine 原生连接） | ✅ **free** |
| 端口 6041（TDengine REST / taosAdapter） | ✅ **free** |
| 端口 1883（Mosquitto MQTT） | ✅ **free** |
| 端口冲突 | **无**，无需重映射 |
| 来源 | `env/ports.md`（2026-09-23 实测） |

> ⚠️ 注意：端口空闲说明"放得下"，**不等于**"授权可用"。这两件事必须分开陈述。

#### 4.2 不通过时立即启动的动作（**触发条件已定义**）

一旦查证结果为"需降级"或"No-Go"，**当天**执行以下动作，不得顺延：

| 步骤 | 动作 | 产出 |
|---|---|---|
| 1 | **冻结结论**：写下结论形态 + 依据（文档/发行包/license 证据） | 本报告 §一–§三 填写完毕 |
| 2 | **启动降级评估**：给出 MQTT JSON 与自研 Sparkplug B 解码器两条备选路线的方案骨架与工期估算 | 方案对比表（含工期） |
| 3 | **评估影响面**：对 MVP 范围（`docs/scope-mvp.md`）、P1 工期、Schema 映射复杂度的影响 | 影响清单 |
| 4 | **登记风险**：在 `docs/risk-register.md` 中把 R8（连接器商业授权）从"潜在"升级为"已触发"，并给出应对与剩余风险 | 风险登记更新 |
| 5 | **通知下游**：V3 第二段的 Schema 映射与 `query_sensor` 契约**须按备选路线重做**，不得沿用原假设 | 本报告第二段标注"已按备选路线修订" |

> **纪律**：这条路径**不是**"先做别的、回头再说"。授权是唯一可能推翻时序路线的外部依赖，拖一天就多一天在错误假设上做设计。

---

## 第二段（D4–D5）—— 接入方案

> 状态：⏳ **设计已定稿，实测待执行**。
> ⚠️ **前置依赖**：本段的 Schema 映射与契约设计以"Sparkplug B 可用"为假设。若第一段结论为"需降级"或"No-Go"，本段必须按备选路线修订并重新标注版本。

### 五、Step1 —— Broker 选型与连接器授权结论

#### 5.1 Broker 选型

| 选项 | 定位 | 选型理由 | 状态 |
|---|---|---|---|
| **Mosquitto** | **默认** | 轻量、资源占用小、Sparkplug B 只依赖 MQTT 3.1.1 标准能力；符合"先省内存"的总原则 | ✅ **默认选定** |
| **EMQX** | **备选** | 功能更全（集群、规则引擎、内置连接器），但资源占用显著更高 | ⏳ 仅在 Mosquitto 无法满足时启用 |

**选型判据（已定稿）**：

| 判据 | 说明 |
|---|---|
| 内存占用是首要判据 | 受 V4b 内存档约束（当前 Docker 上限仅 15.51GB，`.wslconfig` 未落地） |
| Sparkplug B 语义由谁承担 | Mosquitto 只做 MQTT 传输；Sparkplug B 的 topic/metric 语义由**写入侧的消费者/连接器**承担 |
| 是否需要规则引擎 | P0 阶段不需要；若 P1 需要，再评估 EMQX |
| QoS / 保留消息 | 两者都满足；不作为区分因素 |

**实测记录**：

| 项 | 期望 | 实测结果 |
|---|---|---|
| Mosquitto 启动成功 | 容器健康，1883 监听 | ✅ **实测通过（2026-09-24）**：`eclipse-mosquitto:2` 启动、healthcheck 通过、`netstat` 确认 1883 监听；解码器已订阅 `spBv1.0/plant1/+/gw-pump-01/#` |
| Mosquitto 常驻内存 | 【待 D5 实测填入】 | ✅ **实测（2026-09-24）**：**3.7 MiB**（`docker stats`，空闲态） |
| EMQX 对照（可选） | 内存对照值 | ⏳ 未做（Mosquitto 已满足 P0；EMQX 仅在需反向推翻内存预算时再对照） |

> ⚠️ **R9 联动警告**：Broker 选型**可能反向推翻内存预算**。EMQX 一旦启用，须**按最重方案重算** V4b 的内存档与分组策略，并同步 `reports/v4b-report.md`。

#### 5.2 连接器授权结论（第二段口径）

| 项 | 结论 |
|---|---|
| 采用哪种接入路径 | ✅ T1.9 已定稿 = **需降级（OSS + 自研解码器 ≤2 天）**；落地为自研调用 Sparkplug B 消费者 `scripts/self_decoder.py`（详细 `docs/sparkplug-b-decoder.md`） |
| 授权依据 | ✅ **第一段结论**：官方连接器仅随 All-in-One/Enterprise；本项目用 `tdengine/tsdb:3.3.8.0` + 自研解码器（T1.9 有条件通过，见 `docs/version-lock.md` §二.2.1 与 `docs/sparkplug-b-decoder.md` §六） |
| 资源占用 | ✅ **实测（2026-09-24）**：TDengine 219 MiB + Mosquitto 3.7 MiB + 解码器 25.5 MiB（§九） |

---

### 六、Step2 —— Schema 映射

**落点**：`docs/schema-mapping.md`（本报告只给结论与边界覆盖情况）

#### 6.1 映射方向

```
Sparkplug B topic / metric  →  TDengine 超级表 / 列
```

| Sparkplug B 概念 | TDengine 对应 | 映射规则 |
|---|---|---|
| `group_id` / `edge_node_id` | **标签**（每超级表 `TAGS(group_id, edge_node_id, device_id,…)`） | 子表按 `subtable_naming` 划分（数据 `d_{group}_{dev}` / 状态 `s_…` / 旁路 `u_…`，互斥） |
| `device_id` | **标签** + 参与子表命名 | `subtable_naming` 模板代入；合法正则 `^[A-Za-z0-9_-]+$` |
| `metric.name`（如振动/温度/电流） | **固定列**；未登记 metric → **旁路列**（`st_unmapped_metrics`） | 固定列见 `st_pump_metrics`（vib_rms/vib_peak/vib_kurtosis/bearing_temp/motor_current/pump_speed/quality_ok）；动态/未知行阻塞整条报文（局部写入） |
| `timestamp` | TDengine 主时间戳列 | `PRECISION 'ms'`；报文/服务器接收时间优先级见配置 |
| `metric.datatype` | 列类型 | 仅允许 Double/Float/Boolean 入主表，其余旁路 + 告警 |
| `bdSeq` / `seq` | **入库**（`st_device_status.birth_seq/last_seq`） | 用于 re-birth 冲突判定（§6.2 边界 3）与丢包检测 |

**模拟测点（本项输入）**：振动、温度、电流 三类 → 已落 `st_pump_metrics`（6 测点列 + `device_type` 标签），2026-09-24 模拟器灌数 5 行实测。

#### 6.2 四类边界覆盖（**必须逐条给出结论**）

| # | 边界场景 | 期望行为 | 结论 | 验证方式 |
|---|---|---|---|---|
| 1 | **建表**（首次 DBIRTH） | 自动建超级表/子表，或按预定义模板建表 | ✅ **实测通过（2026-09-24）**：首次 DBIRTH（bdSeq=1001）自动建 3 超级表（`st_pump_metrics`/`st_unmapped_metrics`/`st_device_status`）+ 每设备 3 个子表 `d/s/u_plant1_PUMP-A`（数据/状态/旁路命名互斥），`SHOW STABLES`/`SHOW TABLES` 核验 | 模拟器发 DBIRTH |
| 2 | **新增 metric**（设备上报新测点） | 能扩展列/标签而不破坏历史数据 | ✅ **实测通过（2026-09-24）**：DDATA 内新增未知 metric `VIB_BAND_1=0.77` → 写入 `st_unmapped_metrics`（`quality_ok=false`）+ `schema_drift` 告警，**不自动 ALTER 主表**，主表 `st_pump_metrics` DESCRIBE 无新列、历史数据未破坏 | 模拟器在 DDATA 中新增 metric |
| 3 | **re-birth**（设备重启后重发 DBIRTH） | 幂等：不重复建表、不产生重复列、状态可恢复 | ✅ **实测通过（2026-09-24）**：重发 DBIRTH bdSeq 1001→1002→1003，`st_device_status` 记录 `reason='rebirth'`，未重复建表/未丢历史；同 bdSeq 重复报文按 duplicate 忽略 | 模拟器重启后重发 DBIRTH |
| 4 | **离线**（NDEATH / 心跳超时） | 状态正确标记，不产生幽灵数据 | ✅ **实测通过（2026-09-24）**：DDEATH → `online=false reason='ddeath'`；NDEATH → 该网关下设备批量 `online=false reason='ndeath'`+聚合告警；数据保留不回填（no_backfill） | 模拟器发 NDEATH + 停止心跳 |

> 四类边界是 Sparkplug B 接入最容易"看起来通了、实际会在生产炸掉"的地方。**任何一类没有结论，Step2 不得判定完成。**

#### 6.3 Schema 映射结论

| 项 | 结论 |
|---|---|
| 映射正确性 | ✅ **实测通过（2026-09-24）**：JSON 映射 `vibration_rms→vib_rms(Double)`、`metric_quality→quality_ok(Bool)`、`device_type→device_type tag` 一一对应，`st_pump_metrics` 5 行数据列值/标签与报文字号核验一致；未登记 metric 正确旁路 |
| 覆盖的边界 | ✅ **4/4**（建表 / 新增 metric / re-birth / 离线，见上表结论） |
| 未覆盖/已知缺口 | ✅ **已确认缺口（2026-09-28 收口）**：① 心跳超时自动离线（本实测用 DDEATH/NDEATH 显式触发，未做>3s 无数据自动判定——纳入 P1）；② Sparkplug B 全 datatype（本项目仅 Double/Float/Boolean/String，见 schema-mapping §二.4）；③ alias 压缩、NCMD/DCMD 命令下行；④ `db` 库外生产级运维；⑤ 解码器 REST 逐条写入吞吐瓶颈（~80ms/条，P1 需批量写入优化，见 §十二.12.2） |
| 落盘文件 | `docs/schema-mapping.md`；`configs/decoder_schema_mapping.json`（解码器只读） |

---

### 七、Step3 —— `query_sensor` 聚合契约验证

#### 7.1 契约要素

| 要素 | 约定 | 验证结论 |
|---|---|---|
| 时间范围（`time_range`） | 与 V1 的 `time_range` ±10% 语义等价口径**保持一致**（避免工具层两套语义） | ✅ **可行（2026-09-24）**：TDengine 主时间戳（`PRECISION 'ms'`）可直接按 `ts >= 'start' AND ts < 'end'` 过滤，与 V1 语义兼容（粒度换算待 D5 全量核）。聚合实测 `INTERVAL(5m) PARTITION BY tbname` 正常返回 |
| 聚合粒度（窗口） | 【待 D5 填入：如 1min / 5min / 1h】 | ✅ **实测（2026-09-28）**：`INTERVAL(5m)` 返回 25 窗口/设备（2h 数据）；窗口取值 `1m/5m/15m/1h/1d` 由 `window` 参数映射生成 |
| 聚合函数 | 【待 D5 填入：avg / max / min / stddev / count】 | ✅ **实测（2026-09-28）**：`avg`/`max`/`min` 聚合返回窗口化统计（`window_start`+各测点聚合+`sample_cnt`）；`count_over_limit` 返回各窗口超限计数 `over_cnt`；`trend`/`raw` 均已实现（raw 返回点级原值） |
| 测点选择 | 按测点名 / 按设备 | ✅ **可行**：列名即测点名；设备经标签 `device_id`/子表 `PARTITION BY tbname` 过滤 |
| 返回形状 | 是否含样本数、是否含单位、缺失值表示 | ✅ **可行**：返回含 `_wstart`/聚合值/`count`（样本数）；单位在配置（unit 字段）与 schema-mapping 中，未在返回中内嵌；缺失值返回 NULL/空集 |
| 空结果处理 | 返回空 vs 报错 vs 返回零值 | ✅ **可行**：TDengine 无命中返回空集（非报错） |
| 大窗口保护 | 是否限制返回点数/降采样 | ✅ **定稿（2026-09-28）**：`INTERVAL` 按窗口数返回（每窗口 1 行），天然受窗口粒度约束；**超额由契约层 `limit`（默认 500 点）截断**，超过则按 `window_start` 升序取前 N 行，避免返回点数爆炸 |
| **与 Tool Schema v1 的一致性** | 返回结构必须能被 V1 的工具契约消费 | ✅ **可行（聚合可行）**：返回为列式记录，可序列化为 V1 消费的形状；跨项一致性见 §7 下方警示 |

#### 7.2 契约可行性结论

| 项 | 结论 |
|---|---|
| `query_sensor` 聚合契约是否可行 | ✅ **可行（2026-09-28 全量复测）**：分设备 `INTERVAL(5m)` 聚合返回 25 窗口、正确含样本数（`sample_cnt≈235`/窗口）；`count_over_limit` 对 PUMP-A 超限段精确返回非零 `over_cnt` |
| 与 `schemas/tools_v1.json` 的字段一致性 | ✅ **逐字段核对完成（2026-09-28）**：`device_id`/`time_range`(required) 映射 `WHERE`，`sensor_ids`→列选择，`aggregation`(avg/max/min/trend/count_over_limit/raw)→对应窗口聚合，`window`(1m/5m/15m/1h/1d)→`INTERVAL`，`limit`→契约层截断（见 §7.1 大窗口保护） |
| 性能（单次聚合 P95） | ✅ **实测（2026-09-28，全量 21600 点 = 3 设备×2h×1Hz）**：`avg` 聚合 P95≈**26.2ms** / med≈24.8ms（N=30）；`count_over_limit` P95≈27.7ms（N=10）。⚠️ 对比 09-24 小数据量 10.2ms，全量灌数后仍保持低延迟（15-27ms 量级），判定**性能可接受**。明细 `experiments/v3/raw/EXP-V3-QS.jsonl` |
| 缺口与变通方案 | 见 §6.3 未覆盖/已知缺口 |

> ⚠️ **跨项一致性要求**：`query_sensor` 的时间语义必须与 `reports/v1-report.md` 中 V1 的 `time_range` ±10% 判定口径统一，否则会出现"工具调用判分通过、但契约层语义错位"的隐蔽缺陷。

---

### 八、告警生成路线对比与选型

#### 8.1 两条路线对比

| 维度 | **路线 A：阈值 + 滑动窗口** | **路线 B：流式处理** |
|---|---|---|
| 实现方式 | 在查询/写入侧按固定窗口计算阈值越界 | 独立流处理组件（如 taosX 流计算 / 外部流引擎）持续消费 |
| 组件数量 | 少（无新增常驻组件） | 多（新增常驻流处理组件） |
| 内存占用 | 低 | 高 |
| 延迟 | 秒级–分钟级（取决于窗口） | 亚秒级–秒级 |
| 复杂规则（多测点联动、频域特征） | 表达力弱 | 表达力强 |
| 运维复杂度 | 低 | 中–高 |
| 与 checkpoint 审核链路的耦合 | 松（触发后走既有流程） | 需定义触发→审核的接口 |
| 对 MVP 的适配度 | 足够（P0 主场景是阈值型异常：振动烈度超限） | 超出 P0 需要 |

#### 8.2 选型结论（**已定稿倾向，待实测确认**）

| 项 | 结论 |
|---|---|
| **P0/P1 暂定路线** | **路线 A（阈值 + 滑动窗口）** —— 理由是组件少、内存占用低，符合"先省内存"原则 |
| 触发条件（升级到路线 B） | 当需要多测点联动 / 频域特征 / 亚秒级告警时重新评估 |
| 实测确认项 | ✅ **已实测（2026-09-28）**：路线 A「阈值 + 滑动窗口」实现 `scripts/run_v3_alert.py`，全量 21600 点数据实测 **Must#1/Must#2 均 PASS**——PUMP-A 精确定位 1 条告警（跨度 25min = 5 个 5min 窗口，max_window_avg=5.57，`recovered=true`），PUMP-B/C 误报 0。明细 `experiments/v3/raw/EXP-V3-ALERT.jsonl` |
| **若改选路线 B 的代价标注（强制）** | ⏳ **未触发**（当前维持路线 A，P0 主场景为阈值型异常，路线 A 足够）；若改选须显式标注：新增流处理组件的内存占用、对 V4b 内存档的影响、对 P95 告警延迟的影响 |

> **纪律：降级/升级路线必带代价。** 任何"换路线但宣称指标不变"的写法都不允许出现在本报告中。

---

### 九、资源占用

| 项 | 说明 | 实测值 |
|---|---|---|
| CPU | CPU 路线，不使用 GPU | — |
| TDengine（taosd）常驻内存 | ✅ **实测（2026-09-24，`docker stats`）** | **219 MiB**（空闲态，含 server+worker） |
| taosAdapter 常驻内存 | ✅ **实测**（taosAdapter 内含 taosd 镜像进程） | 含于上项；`6041` 端口由 taosAdapter 提供 |
| Broker（Mosquitto）常驻内存 | ✅ **实测（2026-09-24）** | **3.7 MiB** |
| 自研解码器（self_decoder）常驻内存 | ✅ **实测（2026-09-24）** | **25.5 MiB** |
| 磁盘 | D 盘剩余 429.8GB（实测），时序数据可落此 | — |
| 端口 | 6030 / 6041 / 1883 **实测空闲**（起编排前核验无冲突） | ✅ 无冲突 |
| **约束前提** | Docker 可用内存 **19.5 GiB**（`docker stats` 时容器总内存上限），`.wslconfig` 已落地 20GB/10vCPU 基线生效 | ⚠️ 内存结论须带此前提 |

> 本项内存实测值必须回流至 `reports/v4b-report.md` 的 **T8.5 联合仲裁**（顺序：先定内存档 → 再定向量库与图谱 → **最后定 Broker 与 LLM 驻留**）。

---

### 十、关键风险与处置

| 编号 | 风险 | 优先级 | 影响 | 处置 |
|---|---|---|---|---|
| **R-V3-1** | **授权边界**（对应 R8） | **最高** | 时序路线可能整体作废 | **T1.9 放 D1 首步**，不通过即刻启动降级评估；**结论未出前不得判 Pass**；查证渠道见 §二 |
| **R-V3-2** | **Broker 选型反向推翻内存预算**（对应 R9） | 高 | V4b 的 24GB 判据失准、分组策略失效 | Broker 定后**按最重方案重算**内存档；实测值回流 V4b 联合仲裁；启用 EMQX 必须重算 |
| R-V3-3 | Sparkplug B 边界处理遗漏 | 高 | 生产环境建表爆炸 / 重复列 / 幽灵数据 | §6.2 四类边界**逐条给结论**，缺一不得判定完成 |
| R-V3-4 | 时间语义不一致 | 中 | 工具层与契约层语义错位，隐蔽缺陷 | §7.1 强制与 V1 的 `time_range` ±10% 口径统一 |
| R-V3-5 | 授权结论悬而未决被当成"已完成" | 中 | 在错误假设上继续设计，返工 | 结论形态必须**三选一**明确写出；"待确认"不得进入 M0.3 判定 |
| R-V3-6 | 自研解码器工期低估 | 中 | "≤2 天"变 2 周 | §三 给出"≤2 天"的量化口径；超出即判 No-Go 切备选 |
| R-V3-7 | 与已有容器相互影响 | 低 | 误停其他项目容器 | 实测已有 `nacos-standalone`（8080/8848/9848）在跑；**禁止** `docker system prune` 或停止非本项目容器 |

---

### 十一、附：Docker Compose 片段

> 端口严格使用 **6030 / 6041 / 1883**（与 `env/ports.md` §四 冻结的分配基线一致）。
> ⚠️ **落地选型（2026-09-24）**：采用 **OSS 社区版 + 自研 Sparkplug B 解码器**。`tdengine/tsdb:3.3.8.0`、`eclipse-mosquitto:2` digest 均已实测锁入 `docs/version-lock.md` §二.2.1。
> ✅ **本片段已由实际编排取代**：以 `docker/compose.ingest.yml` 为准（Mosquitto + TDengine **常驻两件套**；**2026-09-29 方案 A 起自研解码器移出 compose，改由本地 /venv python 直跑**，连 127.0.0.1 的 1883/6041，见 `docs/sparkplug-b-decoder.md` §八）。解码器 `6041` 写入走 `tsdb` 镜像自带的 taosAdapter（**无需单独 `taosadapter` 容器**）；`spb-simulator` 为**自建脚本**（`scripts/spb_simulator.py`，验证工具，**不进 compose**，见 `docs/sparkplug-b-decoder.md` §八）。

```yaml
# docker/compose.v3.yml —— V3 时序接入片段（设计稿，待选型定稿后确认）
# 端口基线来源：env/ports.md §四（已冻结）
# 说明：本片段只覆盖时序链路；Milvus/PG/Neo4j/Redis 见 compose.base.yml
name: auscult-v3

services:
  # ── TDengine 时序库 ──────────────────────────────────────
  tdengine:
    image: tdengine/tsdb:【选型定稿后填入 tag】        # 社区版 3.3.7.0 起改名；须记录 digest 到 docs/version-lock.md
    container_name: tdengine
    hostname: tdengine
    ports:
      - "6030:6030"        # 原生连接（taosd）
      - "6041:6041"        # REST / taosAdapter
    environment:
      TZ: Asia/Shanghai
    volumes:
      - tdengine-data:/var/lib/taos
      - tdengine-log:/var/log/taos
    restart: unless-stopped
    # ⚠️ 内存限制须与 V4b 联合仲裁结果一致；当前 Docker 上限仅 15.51GB
    # mem_limit: 【待 D8 填入】
    healthcheck:
      test: ["CMD", "taos", "-s", "select server_version()"]
      interval: 30s
      timeout: 10s
      retries: 5

  # ── taosAdapter：把 REST / 连接器入口暴露出来 ─────────────
  # 说明：若 T1.9 结论为"需降级/No-Go"，本服务与 mqtt-bridge 须整体替换为自研消费者
  taosadapter:
    image: tdengine/taosadapter:【待 D4 填入 tag】     # 须记录 digest
    container_name: taosadapter
    depends_on:
      tdengine:
        condition: service_healthy
    ports:
      - "6041:6041"        # 若与 tdengine 同容器暴露，须去重并同步修订本片段
    environment:
      TAOS_HOST: tdengine
    restart: unless-stopped

  # ── MQTT Broker：Mosquitto（默认选型） ───────────────────
  mosquitto:
    image: eclipse-mosquitto:【待 D4 填入 tag】        # 须记录 digest
    container_name: mosquitto
    ports:
      - "1883:1883"        # MQTT（Sparkplug B 传输层）
    volumes:
      - ../configs/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - mosquitto-data:/mosquitto/data
      - mosquitto-log:/mosquitto/log
    restart: unless-stopped
    # mem_limit: 【待 D8 填入】

  # ── Sparkplug B 模拟器（V3 输入） ────────────────────────
  # 用于产生 DBIRTH / DDATA / NDEATH，覆盖 §6.2 四类边界
  spb-simulator:
    image: 【待 D4 填入：模拟器镜像，或自建】           # 须记录 digest
    container_name: spb-simulator
    depends_on:
      - mosquitto
    environment:
      MQTT_HOST: mosquitto
      MQTT_PORT: "1883"
      GROUP_ID: 【待 D4 填入】
      EDGE_NODE_ID: 【待 D4 填入】
      METRICS: vibration,temperature,current
    restart: "no"

volumes:
  tdengine-data:
  tdengine-log:
  mosquitto-data:
  mosquitto-log:

# ── EMQX（备选，仅在 Mosquitto 不满足时启用） ──────────────
# 启用前必须：① 重算 V4b 内存档（R9）② 记录 digest ③ 标注对 P95 与内存的代价
#
#  emqx:
#    image: emqx/emqx:【待 D4 填入 tag】
#    container_name: emqx
#    ports:
#      - "1883:1883"
#      - "18083:18083"     # ⚠️ 18083 不在 env/ports.md 冻结基线内，启用前须先做端口检查
#    restart: unless-stopped
```

**启动与核对命令**：

```bash
docker compose -f docker/compose.v3.yml up -d
docker compose -f docker/compose.v3.yml ps
docker logs tdengine --tail 50
# 核对端口（与 env/ports.md 基线一致）
powershell -File scripts\check_ports.ps1
```

---

### 十二、判据与判定

#### 12.1 判据（逐字采用上游计划）

| 判定 | 条件 |
|---|---|
| **Pass** | **社区版可用且映射正确** |
| **中间区间** | **需自研解码 ≤2 天 → 有条件通过** |
| **No-Go** | **商业授权/不可控 → MQTT JSON 或自研消费者** |

**中间区间处置要求（强制）**：

| 步骤 | 动作 | 必填代价标注 |
|---|---|---|
| ① | 给出自研解码器方案 + 工期估算（按 §三 的量化口径） | 工期数字 |
| ② | 明确"≤2 天"是否成立 | 若 >2 天 → 改判 No-Go，不得写入"有条件通过" |
| ③ | 评估对 Schema 映射复杂度与 `query_sensor` 契约的影响 | 受影响条目清单 |
| ④ | 处置动作写入 `reports/P0-summary.md` 中间区间处置记录 | **中间区间 ≠ 通过** |

#### 12.2 判定

| 段落 | 判定 | 说明 |
|---|---|---|
| **第一段（T1.9 · D1）** | ⚠️ **需降级（有条件通过）** | 判定 **OSS + 自研 Sparkplug B 解码器（≤2 天）**，用户 2026-09-24 裁定；`M0.1` 的「T1.9 授权未查证」阻塞**解除**（授权不构成阻塞，OSS 免费可用）；渠道 3/4 实物核验已执行 |
| **第二段（D4–D5 · M0.3）** | ✅ **达成** | 接入方案四部分**全部实测通过（2026-09-28）**：① Broker（Mosquitto）实测；② Schema 映射四类边界 4/4；③ `query_sensor` 契约（P95≈26.2ms）；④ 告警路线 A（Must#1/Must#2 均 PASS）。中间区间处置已按自研解码器路径闭环 |

> **M0.3（V2 + V3 完成 · D5）= V3 部分已达成。**
> V3 的通过条件为"时序接入决策 + Schema 映射表 + `query_sensor` 契约 + 告警路线"，**4/4 就绪并实测通过（2026-09-28）**：
>
> | V3 判据 | 结论 |
> |---|---|
> | 时序接入决策 | ✅ 自研解码器（OSS + `self_decoder.py`）端到端接入实测通过，四类边界 4/4 落库确认 |
> | Schema 映射表 | ✅ 映射正确性实测通过（§6.1–§6.3），`decoder_schema_mapping.json` 与 `schema-mapping.md` 镜像一致 |
> | `query_sensor` 契约 | ✅ 可行（P95≈26.2ms，字段逐字段与 `tools_v1.json` 核对完成，§7.2） |
> | 告警路线 | ✅ 路线 A（阈值+滑动窗口）Must#1/Must#2 均 PASS（§8.2） |
>
> **关键前置（已解除）**：第一段的授权结论已完成（需降级：OSS + 自研解码器 ≤2 天），中间区间处置（§十二.1）已闭环——自研方案 + 工期估算（≈1.9 人日）定稿并入 `docs/sparkplug-b-decoder.md`。
>
> **收口说明（2026-09-28）**：受解码器 REST 逐条写入 ~80ms/条 吞吐限制，全量灌数（21600 点 = 3 设备×2h×1Hz）与 `query_sensor` P95 / 告警验证改由**直写 TDengine 构造标准数据集**（`scripts/v3_ingest_direct.py`，语义与模拟器一致）完成；端到端接入链路（含四类边界）由模拟器 → 解码器 → TDengine 实测通过。V3 判定**达成**。
>
> ⚠️ **仍属"有条件通过"的回溯点**：实际生产吞吐瓶颈在解码器 REST 逐条写入（~80ms/条），P1 需评估批量写入（`INSERT ... multi values` / `taosrest.execute` 批处理）或参数化写入以消除该瓶颈；V3 判据达成不隐含该瓶颈已消除。

---

### 十三、复现命令

```bash
# ── 第一段（T1.9）：授权边界查证辅助（已执行：go OSS 自研分支） ──
# 实物核验已用 tdengine/tsdb:3.3.8.0（digest sha256:36e2bf82...256bf，无 taosX/连接器）
docker pull tdengine/tsdb:【tag】            # 社区版 3.3.7.0 起改名 tdengine/tsdb
docker run --rm --entrypoint sh tdengine/tsdb:【tag】 -c "ls -la /usr/local/taos/bin; ls -la /usr/local/taos/connector 2>/dev/null"
# 版本确认 + digest 登记
docker run --rm tdengine/tsdb:【tag】 taos -s "select server_version()"
docker inspect --format='{{index .RepoDigests 0}}' tdengine/tsdb:【tag】

# ── 第二段（D4–D5）：接入方案验证（已执行 2026-09-28）────────
# 注意：2026-09-29 方案 A 起 compose.ingest.yml 只起常驻两件套（mosquitto + tdengine）；
#       自研解码器不再经 compose，需本地 /venv python 单独直跑。
docker compose -f docker/compose.ingest.yml up -d

# 端到端接入 + Schema 映射四类边界验证（模拟器 → 解码器 → TDengine）
# 解码器本地直跑（连 127.0.0.1 的 1883/6041）：
.venv\Scripts\python.exe scripts\self_decoder.py \
    --schema-mapping configs/decoder_schema_mapping.json \
    --mqtt-host 127.0.0.1 --td-host 127.0.0.1
# （另开终端）模拟器发报文：
python scripts/spb_simulator.py --scenario birth,new_metric,rebirth,offline

# query_sensor 聚合契约验证（P95 复测）
python scripts/verify_query_sensor.py --aggregation avg --window 5m --n 30
python scripts/verify_query_sensor.py --aggregation count_over_limit --window 5m --metric vib_rms --threshold 4.5

# 告警路线 A（阈值 + 滑动窗口）验证
python scripts/run_v3_alert.py --threshold 4.5 --window-min 5 --must-windows 3

# 直写 TDengine 构造标准数据集（全量灌数 21600 点，绕开解码器 REST 逐条写入瓶颈）
python scripts/v3_ingest_direct.py --hours 2 --devices PUMP-A,PUMP-B,PUMP-C   # 告警设备固定为 --devices 首个（脚本无 --alert-device 参数）

# 端口复核（与 env/ports.md 基线一致）
powershell -File scripts\check_ports.ps1

# ── 原始数据落盘 ────────────────────────────────────────
# experiments/v3/raw/EXP-V3-QS.jsonl    （query_sensor 契约 + P95 明细）
# experiments/v3/raw/EXP-V3-ALERT.jsonl （告警路线 A 明细）
# 实验登记按 docs/experiment-log-template.md
```

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| D1（计划） | 单人（本人） | 初始建立：第一段（T1.9）查证清单与三种结论判定标准定稿；第二段接入方案设计定稿 | — |
| 2026-09-24 | 本人 | **第一段授权结论定稿（文档层 + 实物层）**：渠道 3/4 实测 `tdengine/tsdb:3.3.8.0` 确认 OSS 无 taosX/连接器；**落地选型裁定为 OSS + 自研解码器**，判**需降级（有条件通过）**；镜像名 3.3.7.0 起变更 | §〇、§一–§四、§十一、§十二.12.2、§十三 |
| 2026-09-28 | 本人 | **第二段接入实测完成并定稿（V3 收口）**：端到端接入链路 + Schema 映射四类边界 4/4 实测通过（模拟器→解码器→TDengine）；`query_sensor` 契约实测可行 + P95 全量复测（≈26.2ms）+ 字段逐字段与 `tools_v1.json` 核对；告警路线 A（阈值+滑动窗口）Must#1/Must#2 均 PASS；受解码器 REST 逐条写入瓶颈，全量灌数 + P95 / 告警验证改由直写 TDengine 构造标准数据集（`v3_ingest_direct.py`）。**第二段判定由「未达成」升为「达成」**；自研解码器方案 + 工期估算（≈1.9 人日）已定稿 | §〇、§五–§九、§十二.12.2、§十三、修订记录 |
| 【若实物复核推翻判定】 | — | 按备选路线（MQTT JSON / 自研消费者）修订第二段 Schema 映射与契约 | §六、§七、§十一 |