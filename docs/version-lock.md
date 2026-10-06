# 版本锁定清单（Version Lock）v1

> **对应任务**：T9.1（版本锁定清单）
> **里程碑**：M0.5（D9）；随 `reports/P0-summary.md` 一并过 M0.6
> **上游依据**：`Phase 0 详细开发计划（D1-D10 可执行版）.md` §三 D9（T9.1）、§六.1
> **唯一环境基线**：`env/env-baseline-v2.md` v2（采集于 2026-09-24 +08:00）
> **硬件来源**：`env/hardware.json`（**已于 2026-09-29 重采**，`collected_at = 2026-09-29T11:49:36+08:00`，零警告；重采后与 `env/env-baseline-v2.md` 逐项一致，旧 v1 快照留档为 `env/hardware-v1-2026-09-23.json`）
> **状态**：v1 —— §二 已锁定清单为实测值；**§三 已锁定项含 V5 LangGraph/PG checkpointer 依赖（§二.2.9）**；`docker/compose.base.yml` 依赖其中"待锁定"行
> **版本**：v1 ｜ **制定日期**：2026-09-23
> **项目**：云侧工业 IoT 诊断 Agent 系统 · 主场景：离心泵轴承振动异常诊断
> **项目根**：`<REPO>`

---

## 一、纪律（硬性）

> **纪律 1（digest 唯一性）**：**版本一律以 digest 为准**。禁止只写裸 tag，**禁止写 `latest`**。tag 可被重新推送覆盖，digest 不会。

> **纪律 2（变更即升版）**：**任何组件或模型版本变更 → 必须新开 `experiment_id` 并升版本文件**。变更后不得在原有实验条目上覆盖；原版本下的全部结论随之作废或需重新确认。

> **纪律 3（不一致即作废）**：**报告中出现的组件版本与 digest 与本文件不一致 → 结论作废**。

> **纪律 4（Schema 变更即升版）**：**Schema 变更 → 必须升版为 `tools_v2.json`**。依据 `schemas/tools_v1.json` 的 `change_policy` 字段原文：「本文件一经冻结，任何修改必须升版为 v2 并同步更新 version-lock.md；否则 V1 全部结论作废」。

### 1.1 纪律细则

| # | 规则 | 违反后果 |
|---|---|---|
| 1 | 本文件是**唯一版本权威**。任何报告引用的组件/模型版本必须能在本文件找到对应行，且**逐字一致（含 digest）**。 | 结论作废 |
| 2 | §二 的每一行数据**逐字取自** `env/env-baseline-v2.md` 与 `env/hardware.json`；**不得**在本文件中"改进"或"补全"上游未实测的字段。 | 视为编造实测数字，违反 Phase 0 铁律 |
| 3 | 环境基线升版（`env-baseline-v2.md` → v2）时，本文件必须同步升版，并逐条复核 §二。 | 版本不一致，全部结论不可复现 |
| 4 | 未锁定的组件**不得**出现在任何实验报告中作为"已采用版本"；一律写 `【待 D<天> 实测填入】`。 | 视为过度声称 |
| 5 | 新拉取的镜像/模型**必须立即回填**本文件并锁 digest（基线 §7.1 明示要求）。 | 复现条件不完整 |
| 6 | 本文件在 P0 结束时随 `docs/handover-p1.md` 移交，作为 P1 的版本基线输入。 | — |

---

## 二、已锁定清单（实测）

> **引用纪律**：本章数据引自 **`env/env-baseline-v2.md` v2（2026-09-24 采集）**，与 `env/hardware.json` 一致。
> **环境基线：env-baseline-v2（见 env/env-baseline-v2.md）**

### 2.1 Docker 镜像（8 个，实测 digest）

| # | 组件 | Tag | Digest | 大小 | 用途 | 来源 |
|---|---|---|---|---|---|---|
| 1 | `milvusdb/milvus` | `v3.0.0` | `sha256:49371c30af46b1013e4d3e0b980e691d81376d69cdbe1b372725baf1d7255862` | 3.93 GB | **V2 主路线**（向量库） | `env-baseline-v2.md` §7.1 |
| 2 | `quay.io/coreos/etcd` | `v3.5.25` | `sha256:52f17f7e56e4f7239f0320dbfcbcc24721163d7d78ae710b466af3254ccf6366` | 93.8 MB | Milvus 依赖 | `env-baseline-v2.md` §7.1 |
| 3 | `minio/minio` | `RELEASE.2024-12-18T13-15-44Z` | `sha256:1dce27c494a16bae114774f1cec295493f3613142713130c2d22dd5696be6ad3` | 244 MB | Milvus 依赖 | `env-baseline-v2.md` §7.1 |
| 4 | `postgres` | `18` | `sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280` | 650 MB | **V2 对照路线** + 业务库 | `env-baseline-v2.md` §7.1 |
| 5 | `redis` | `8` | `sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5` | 212 MB | **V5 checkpoint** | `env-baseline-v2.md` §7.1 |
| 6 | `tdengine/tsdb` | `3.3.8.0` | `sha256:36e2bf82f151e8013d39a929aadc41bfcd5c46564866635cee1a02693d2256bf` | 1.68 GB | **V3 时序库（OSS，T1.9 已定稿自研解码器路线）** | **实测 2026-09-24**（`docker images --digests`） |
| 7 | `eclipse-mosquitto` | `2` | `sha256:38c0da4f2ef84284d47b3b3eeea1cb3bdeabe81ee10caf0cd5c5ff61ee3ea408` | 41.8 MB | **V3 时序链路 MQTT Broker（Sparkplug B 传输层）** | **实测 2026-09-24**（D4–D5 拉取） |
| 8 | `neo4j` | `5-community` | `sha256:ab3aafb0020e6fed65bb2b59f7db1fabd7ee0568c4da46f3cc3b8fad77801d61` | 约 1.0 GB | **图谱库（社区版）** | **实测 2026-09-24**（V4b 压测拉取，V4b 内存实测 ≈871MiB） |

> ⚠️ **镜像总数 / 占用**：**8 个（本项目）/ 约 7.8 GB**（仍以 `env-baseline-v2.md` §7.1 为唯一镜像基线；宿主上其他项目镜像如 nacos/mysql/mongodb 已从本表移除，但本机容器仍在，**禁止** `docker system prune` 或停止非本项目容器，见 `docs/risk-register.md` R-V3-7 / R-V4b-8）。
> ⚠️ **BGE-M3 经 ModelScope 本地加载**（`D:\modelscope\hub\models\BAAI--bge-m3`，非 Docker 镜像、非 Ollama 模型，见 §2.2.1）；Neo4j 已在本表第 8 行锁定。D6/D7 新增镜像拉取后必须立即回填本表并锁 digest。
> ✅ `milvusdb/milvus:v3.0.0` 与上游计划 §二 Q3 裁决一致（v3.0.0 + 服务端 `FunctionType.BM25`），无偏差。
> ✅ `tdengine/tsdb:3.3.8.0` 的 tag 与 digest 已实测锁定；其镜像名相对上游 `tdengine/tdengine` 的变更与授权判定见 `reports/v3-auth.md` §〇/§四.1（T1.9 需降级 = OSS + 自研解码器）。

### 2.2 Ollama 生成模型（2 个，实测 digest）

| 模型 | 模型层 Digest | Manifest config Digest | 大小 | 用途 | 来源 |
|---|---|---|---|---|---|
| **`qwen2.5:7b`** | `sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730` | `sha256:2f15b3218f0552c60647ce60ada83632d2c09755b16259b13e3e4458e9ae419d` | 4.68 GB | 候选 A（通用指令模型） | `env-baseline-v2.md` §8.1 |
| **`deepseek-r1:7b`** | `sha256:96c415656d377afbff962f6cdb2394ab092ccbcbaab4b82525bc4ca800fe8a49` | `sha256:40fb844194b25e429204e5163fb379ab462978a262b86aadd73d8944445c09fd` | 4.68 GB | 候选 B（推理模型，含 `think`） | `env-baseline-v2.md` §8.1 |

> **模型根目录**：`D:\.ollama\models`；**API 端点**：`http://127.0.0.1:11434`（实测 OCCUPIED，PID 80484，**预期占用**）。
> **Manifest digest 说明**：上表 manifest config digest 与模型层 digest 均为 `env-baseline-v2.md` §8.1 登记值；**manifest 路径见 `env/hardware.json` 的 `models[].manifest_path`**（如 `D:\.ollama\models\manifests\registry.ollama.ai\library\qwen2.5\7b`）。
> **V1 报告必须原样引用上表 digest**，否则结论无法复现。
> ⚠️ **量化档已登记（2026-09-29 实测）**：`qwen2.5:7b` 与 `deepseek-r1:7b` **均 Q4_K_M**（`ollama show` 实测，对应 `docs/known-issues.md` ISS-012，已拉齐，对比公平性成立）；胜出者 Q8/FP16 复核为 P1 遗留。

### 2.2.1 ModelScope 本地向量模型（BGE-M3，非 Ollama）

> **2026-09-29：BGE-M3 迁移**。原经 Ollama `/v1/embeddings` 加载（blob `sha256:daec91ff…3062c`），现改为 sentence-transformers 直接加载 ModelScope 本地目录，删除 Ollama `bge-m3`（1.2GB）。纯本地推理，不依赖 Ollama，Ollama 仅保留 2 个生成模型。调用入口见 `scripts/run_v2.py` `EmbeddingClient`（默认 `BGE_M3_MODEL_PATH`）。

| 模型 | 路径 | 维度 | 大小 | 用途 | 来源 |
|---|---|---|---|---|---|
| **`BAAI--bge-m3`**（sentence-transformers 格式） | `D:\modelscope\hub\models\BAAI--bge-m3\snapshots\master` | **1024（实测 2026-09-29）** | ~1.7GB（`pytorch_model.bin`） | **V2 向量化模型（dense embedding）** | ModelScope 本地下载 |

> **依赖**：`sentence-transformers`（`.venv`）；**调用**：`EmbeddingClient(model=BGE_M3_MODEL_PATH)`；推理设备默认让框架自选（可用 `--embed-device cuda|cpu` 强制）。

### 2.2.2 ModelScope 本地 reranker 模型（选用 & 锁定，2026-09-29）

> **决策（2026-09-29）**：用户采用本地环境，直接用本地 ModelScope 模型库的 **`BAAI--bge-reranker-v2-m3`**，无需联网拉取。由此锁定 reranker（此前 §三 第 13 行「待锁定」，由 P1 提前到本次选用）。

| 模型 | 路径 | 架构/维度 | 大小 | 用途 |
|---|---|---|---|---|
| **`BAAI--bge-reranker-v2-m3`** | `D:\modelscope\hub\models\BAAI--bge-reranker-v2-m3\snapshots\master` | `XLMRobertaForSequenceClassification`，hidden **1024**，24 层，`torch_dtype` float32 | ≈**2.1GB**（`model.safetensors`） | **V2 reranker（交叉重排，Second-stage re-ranking）** |

> **说明**：同架构（xlm-roberta）与 BGE-M3 向量模型配套，合法对（query, passage）打分做 `Recall@5` 后精排；`sentence-transformers` `CrossEncoder` 直接加载本地目录。**该模型为本地资源，与 Ollama 无关。**

### 2.3 工具链与运行时（实测）

| 工具 | 版本 | 路径 | 来源 |
|---|---|---|---|
| Python | **3.12.8** | `D:\Python312\python.exe` | `env-baseline-v2.md` §九 |
| Node.js | **v24.19.0** | `C:\Program Files\nodejs\node.exe` | `env-baseline-v2.md` §九 |
| Git | **2.45.1.windows.1** | `C:\Program Files\Git\cmd\git.exe` | `env-baseline-v2.md` §九 |
| Ollama | **0.34.2** | `<USER_HOME>\AppData\Local\Programs\Ollama\ollama.exe` | `env-baseline-v2.md` §九 |
| Docker（引擎） | **29.6.2** | `C:\Program Files\Docker\Docker\resources\bin\docker.exe` | `env-baseline-v2.md` §七、§九 |
| Docker Compose | **v5.3.1** | 随 Docker Desktop | `env-baseline-v2.md` §七 |
| WSL2 | **2.7.11.0** | `C:\WINDOWS\system32\wsl.exe` | `env-baseline-v2.md` §六、§九 |
| WSL2 内核 | **6.18.33.2-2** | — | `env-baseline-v2.md` §六 |
| nvidia-smi | 随驱动 **616.56** | `C:\WINDOWS\system32\nvidia-smi.exe` | `env-baseline-v2.md` §九 |

> ✅ **Ollama 版本决策已定（2026-09-24，U-04）**：**锁定维持 0.34.2，不升级 0.34.3/0.34.4**（ISS-009 建议 + 已安装运行、V1 全流程固定同版本防行为漂移）。V1 实测已按此版本开跑。
> ⚠️ **CUDA Toolkit 未安装**（默认路径 `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA` 下无）。Ollama 自带 CUDA 运行时，WSL2 走驱动透传；编译类需求须另装。

### 2.4 硬件（实测）

| 项 | 实测值 | 来源 |
|---|---|---|
| 操作系统 | Windows 10 Pro，25H2，build 26200（`10.0.26200.7171`），x64 | `env-baseline-v2.md` §一 |
| 主机名 | `<WORKSTATION>` | `env-baseline-v2.md` §一 |
| CPU | 13th Gen Intel(R) Core(TM) i7-13650HX | `env-baseline-v2.md` §二 |
| 逻辑处理器 | **20**（6 性能核 + 8 能效核） | `env-baseline-v2.md` §二 |
| 物理内存 | **32 GB**（34359738368 bytes） | `env-baseline-v2.md` §三 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU | `env-baseline-v2.md` §四 |
| 显存总量 | **8188 MiB**（约 8 GB；采集时已用 1282 MiB） | `env-baseline-v2.md` §四 |
| GPU 驱动 | **616.56**（WMI 报 32.0.16.1656） | `env-baseline-v2.md` §四 |
| Compute Capability | **8.9**（Ada Lovelace） | `env-baseline-v2.md` §四 |
| WSL2 设计配额 | memory=20 GB（62.5%）/ processors=10 / swap=8 GB | `env-baseline-v2.md` §三、§六.1 |
| WSL2 **当前实际**配额 | **≈20 GB**（Docker `MemTotal=20972691456 bytes`，NCPU=10） | `env-baseline-v2.md` §三、§七（2026-09-24 核验） |
| `%UserProfile%\.wslconfig` | ✅ **存在并生效**（2026-09-24 已安装核验） | `env-baseline-v2.md` §六 |
| WSL2 发行版 | 仅 `docker-desktop`（Running, v2） | `env-baseline-v2.md` §六 |
| GPU 直通（WSL2 内） | ⚠️ **UNVERIFIED**，但 **已裁决改走宿主原生 Ollama（2026-09-24，U-03）**：推理统一走宿主 `127.0.0.1:11434`（qwen2.5:7b / deepseek-r1:7b / BGE-M3），容器仅承载 DB/存储，不承载模型推理 → **GPU 直通不再阻塞** | `env-baseline-v2.md` §六.2；`docs/known-issues.md` ISS-008 |
| P0 门禁线 | 峰值 ≤ **24 GB**（32 GB × 75%） | `env-baseline-v2.md` §三 |
| 磁盘 C / D / E 剩余 | **94.3 GB** / **429.8 GB** / **62.5 GB** | `env-baseline-v2.md` §五 |

> ⚠️ **WMI 报告的 `AdapterRAM = 4293918720`（约 4 GB）是 32 位截断值，不可用**；一律以 `nvidia-smi` 的 8188 MiB 为准。
> ✅ **`.wslconfig` 已于 2026-09-24 落地**（WSL2 配额 ≈20 GB / 10 vCPU / 8 GB），`env-baseline-v2.md` 已升版为 v2（其 §六 升版触发条件第 4 条已触发并完成）。

### 2.5 实验固定参数（实测/定稿值）

> **来源**：`prompts/tool_call_prompt_v1.md` §三「实验参数（v1 固定值）」。

| 参数 | 固定值 | 理由 | 来源 |
|---|---|---|---|
| `temperature` | **0** | 工具调用是确定性任务，需要可复现 | `tool_call_prompt_v1.md` §三 |
| `seed` | **42** | 固定随机种子，写入实验登记 | `tool_call_prompt_v1.md` §三 |
| `num_ctx` | **8192** | 容纳 Schema + few-shot + 用户问题；过大浪费显存 | `tool_call_prompt_v1.md` §三 |
| `top_p` | **1.0** | 与 `temperature=0` 配套 | `tool_call_prompt_v1.md` §三 |
| `max_tokens` | **1024** | 足够输出工具调用；限制 `think` 无限膨胀 | `tool_call_prompt_v1.md` §三 |
| `stream` | **false** | 便于统计完整 token 数与延迟 | `tool_call_prompt_v1.md` §三 |
| `think` 处理 | **先剥离再判 JSON** | R1 类模型必须如此 | `tool_call_prompt_v1.md` §三 |
| 判分容差（`time_range`） | **±10% 语义等价** | 判分规则 | `schemas/tools_v1.json` `conventions.time_range_equivalence` |
| 重试上限 | **≤3 次**（校验错误回灌，固定策略） | 重试后成功率口径 | `Phase 0 详细开发计划` §三 D2–D3 |

> **纪律**：上述固定值必须由 `scripts/run_v1.py` 的默认值写死并**在运行开始打印**，防止静默漂移。任何改动 → 必须新开 `experiment_id`。

### 2.6 已冻结 Schema

> 当前活动版本 = **v4**（2026-10-06 修正；此前本节误标为 v2）。v1 / v2 / v3 冻结快照保留不删，v5 为负结果快照。

| 版本 | 文件 | `status` | `frozen_at` | 冻结依据 / 变化 |
|---|---|---|---|---|
| **v4（活动）** | `schemas/tools_v4.json` | FROZEN | 2026-09-30 | **V1 复审 v3 · F2**：仅扩写 `query_sensor.sensor_ids` 的 description（内嵌 5 测点目录），**未动结构**；本地 +28.3pp / 云端 +30pp 双向印证 |
| v5（负结果快照，未采纳） | `schemas/tools_v5.json` | RETIRED_NEGATIVE_RESULT | 2026-10-05 | **H3**：仅扩写 `aggregation.description` → 同日对照下全面劣化（参数校验 75%→25%、多工具 75%→33%、格式退化 8→15）、且目标 `v1-007` 仍 0/3；**未采纳**（`experiments/v1/EXP-M02-013-014.md`） |
| v2 | `schemas/tools_v2.json` | FROZEN（快照） | 2026-09-30 | 判分口径复审（P3）：D1–D5 + `conventions` 归一化注释 |
| v3（负结果快照） | `schemas/tools_v3.json` | RETIRED_NEGATIVE_RESULT | 2026-09-30 | **P5 Schema 简化（缩描述 + 可选降级）经 EXP-V1-008 实测为负结果**（对照 EXP-V1-007 双模型整体回退，deepseek 参数校验 87%→60%），**已回退不启用** |
| v1 | `schemas/tools_v1.json` | FROZEN（快照） | 2026-09-23 | T1.6 冻结 |

- 工具数（各版本一致）：**5**（`query_sensor` / `search_knowledge` / `query_graph` / `get_maintenance_history` / `generate_report`）
- `generate_report` 必填（各版本自 v2 起）：`device_id` / `diagnosis_summary` / `evidence_refs` 三项；`severity`/`format`/`recommended_actions`/`idempotency_key` 宽松不参与 V1 正确性判定。
- **version-lock §一 纪律 4 口径**：**Schema 变更 → 必须升版**（v1→v2→v3），快照保留不删，变更原因写入上表。

> ⚠️ **活动版本回退说明**：v3 曾短暂作为活动版（P5 简化），经 EXP-V1-008 实测为负结果后**回退至 v2**。后续任何 Schema 改动 → 升 **v4** 并更新本表，**已完成的 V1 结论需按新版本重跑**。P5 的"减嵌套（time_range 摊平）"仍**押后未做**（可解析率已满分，结构无余量）。

---

### 2.7 V1 提示词版本状态（2026-10-06 新增；**含反泄漏审计结论**）

> **来源**：`reports/v1-refusal-audit-2026-10-06.md` §2（反泄漏审计）、`experiments/v1/EXP-M02-020-022.md`（H11 验证）
> **硬约束（新增）**：任何提示词的 `user:` 示例行**不得**与 `evals/**` 中任何用例的 `input` 逐字或近似重合；
> **每次改动示例后必须重跑重合审计**，零重合方可使用。

| 版本 | 文件 | 状态 | 反泄漏审计（20 主用例 + 5 迁移用例） | 说明 |
|---|---|---|---|---|
| **v1（评测活动）** | `prompts/tool_call_prompt_v1.md` | ✅ **可用于评测** | 逐字 **0** / 近似 0 ｜ 最高相似度 **0.746** | 3 条 few-shot。**当前所有有效结论均基于 v1**（含四臂矩阵 `EXP-M02-016`~`-019`） |
| **v2** | `prompts/tool_call_prompt_v2.md` | ⛔ **禁止用于评测**（含测试集泄漏） | 逐字 **7** ｜ 最高相似度 **1.000** | 8 条 few-shot 中 **7 条与测试用例 `input` 逐字相同** → **`ISS-032` / `R-V1-12`**。**仅作教学稿保留**；其**通用规则（6a/6b/6c）本身是干净的、可复用**，脏的是**示例** |
| **v4（候选，未采纳）** | `prompts/tool_call_prompt_v4.md` | 🧪 **候选，未采纳** | 逐字 **0** / 近似 0 ｜ 最高相似度 **0.746** | = v1 + **最小拒止强化**（规则 6 合并为 6a/6b/6c）+ 1 条**非镜像**示例（齿轮箱越界）。`EXP-M02-009` 实测 **0.85 / 拒止 100% / `4a=0`** → **本项目"拒止强化"归此项** |
| **v5（实验版，未采纳）** | `prompts/tool_call_prompt_v5.md` | ⚠️ **实验版，暂不采纳**（192 行 / sha256 `42923e4f175d`） | 逐字 **0** / 近似 0 ｜ 最高相似度 **0.746** | = v1 + 通用拒止规则 6a/6b/6c + 示例 4（定指拒止，措辞不重合）。**与 v4 设计同源**（独立撰写）。**H11 实测**：✅ 拒止卡点消除（主集无效拒绝 67%→100%、`v1-016` 0/3→3/3）、✅ 规则可迁移（无泄漏迁移集 80%→100%）；**但净分 0.90→0.85**（规则 6b **误伤写工具** `generate_report`，`v1-019` 3/3→0/3）→ **待基于 v4 修 6b 后升 v6 再测**。⚠️ **命名事故**：内容最初误写入 `tool_call_prompt_v3.md`（覆盖历史资产，已恢复）；见 `ISS-033` |

---

## 三、待锁定清单

> **本节必须存在**：`docker/compose.base.yml` 中已明确注释「版本待锁定（`version-lock.md` 中为"待锁定"行）」（Neo4j 段）。
> **纪律**：本节每一行在锁定后，必须**移入 §二**并补齐 digest，同时同步更新「锁定后须同步更新的文件」列所列文件。

| # | 组件 | 当前状态 | 何时锁定 | 锁定后须同步更新的文件 |
|---|---|---|---|---|
| 1 | **TDengine**（`tdengine/tsdb`） | **✅ 已锁定（2026-09-24 实测）**：`3.3.8.0` / `sha256:36e2bf82f151e8013d39a929aadc41bfcd5c46564866635cee1a02693d2256bf` / 1.68 GB，已移入 §二.2.1 第 9 行。镜像名由上游 `tdengine/tdengine` 改为 `tdengine/tsdb`（T1.9 授权已定稿 = 需降级，OSS + 自研解码器） | **✅ 已锁定** | `docs/version-lock.md` §二.2.1；`docker/compose.base.yml`（`tdengine` 段，改精确 tag 已整改）；`reports/v3-auth.md` §十一；`docs/schema-mapping.md`；`docs/risk-register.md` R8 / R-V3-1 |
| 2 | **TDengine taosX**（连接器） | **不采用（已裁决 2026-09-24）**：官方 Sparkplug B 连接器仅随 All-in-One/Enterprise；OSS 镜像 `tdengine/tsdb:3.3.8.0` 实测无 taosX；本项目改走 **OSS + 自研 Sparkplug B 解码器 ≤2 天**（`reports/v3-auth.md` §一–§四、§5.2） | ——（不再锁定官方连接器；解锁自研解码器版本） | `reports/v3-auth.md`；`docs/version-lock.md` §二；`docs/risk-register.md` R8 / R-V3-1 / R-新4；`docs/schema-mapping.md` |
| 3 | **BGE-M3 模型**（向量化） | **✅ 已锁定（2026-09-25 实测）**：经 Ollama `/v1/embeddings`（Ollama 0.34.2），blob `sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c`，1.2GB/bert 566.7M/F16，已移入 §二.2.2 第 3 行 | **✅ 已锁定** | `docs/version-lock.md` §二.2.2；`reports/v2-report.md` §二.2.3、§五；`docs/schema-mapping.md` |
| 4 | **BGE-M3 向量维度** | **✅ 已锁定（2026-09-25 实测）**：**维度 = 1024**（U-05 项3/4 由此锁定） | **✅ 已锁定** | `reports/v2-report.md` §五（参数基线表）；`docs/schema-mapping.md`；P1 建库脚本 |
| 5 | **PostgreSQL + pgvector** | **⚠️ 已重新锁定（2026-09-25 实测）**：V2 改用 **ParadeDB 官方镜像** `paradedb/paradedb@sha256:188591a0bc317beb2c6d6d3f9ef0cb3e859d09ecc15a71dda5e9a027876686cf`（PG 18.6 Debian），宿主端口 **5433**（原 5927，2026-09-28 因被 `smart-doc-db` 占用整改），库 `auscult_v2`；扩展 `vector 0.8.4` + `pg_search 0.25.10`（真 BM25 已由 K-V2-1 闭环，ngram tokenizer）。原 `postgres:18` 行（§二 第 4 行）为业务库基线，**V2 检索实际走 ParadeDB** | **✅ 已锁定（V2 用）** | `docs/version-lock.md` §二；`docker/compose.yml`（PostgreSQL 段）；`reports/v2-report.md` §二.2.3 |
| 6 | **ParadeDB `pg_search`** | **✅ 已锁定（2026-09-25 实测）**：镜像 `paradedb/paradedb@sha256:188591a0bc…686cf`，pg_search **0.25.10**。**真 BM25 悬置未用（`USING bm25` 建索引后 INSERT 报 `No key field defined`，K-V2-1），V2 实际用 `tsvector` 降级**（对标未闭环，结论范围限于「Milvus 原生 BM25 vs PostgreSQL tsvector」） | **✅ 已锁定（版本）／BM25 悬置** | `reports/v2-report.md` §4.3、§九（R-V2-3）；`docs/risk-register.md` R-V2-3 |
| 7 | **Neo4j** | **✅ 已锁定（2026-09-24 实测）**：`neo4j:5-community` / `sha256:ab3aafb0020e6fed65bb2b59f7db1fabd7ee0568c4da46f3cc3b8fad77801d61`，已移入 §二.2.1；选型约束社区版已满足 | **✅ 已锁定** | `docs/version-lock.md` §二.2.1；`docker/compose.base.yml`（neo4j 段，已补 digest）；`reports/v4b-report.md` §5.1；`docs/risk-register.md` R-V4b-1 |
| 8 | **Mosquitto** | **✅ 已锁定（2026-09-24 实测）**：`eclipse-mosquitto:2` / `sha256:38c0da4f2ef84284d47b3b3eeea1cb3bdeabe81ee10caf0cd5c5ff61ee3ea408`（41.8MB），已移入 §二.2.1 | **✅ 已锁定** | `docs/version-lock.md` §二.2.1；`docker/compose.base.yml`（`mosquitto` 段，补 digest）；`reports/v3-auth.md` §5.1；`docs/risk-register.md` R-V3-2 |
| 9 | **EMQX**（Broker 备选） | **待锁定**：仅在 Mosquitto 无法满足时启用；启用前须先做端口检查（`18083` **不在** `env/ports.md` 冻结基线内） | 仅在被选用时锁定 | `docs/version-lock.md` §二；`reports/v3-auth.md` §十一（注释段）；`reports/v4b-report.md` §8.1；`docs/risk-register.md` R9 / R-V3-2 |
| 10 | **云端 baseline 模型**（上界校准） | **✅ 已锁定（2026-09-28 实测 EXP-V1-002）**：provider `openai`（openai_compatible），model **`Qwen/Qwen3.8-27B`**，endpoint `https://api-inference.modelscope.cn/v1/chat/completions`，支持 function calling；上界校准首次成功率 **0.60**（<0.90，判 No-Go 归因「用例/Schema 需复审 + 7B 上界受限」）。连接配置 `env/cloud.json`（含 API key，`.gitignore` 忽略，`is_locked=true`）。仅作上界校准，**不作默认部署**。⚠️ **【2026-10-05 增补声明】本行仅锁定"模型名"，云端模型**不可 digest 化**——实测同一模型名、同一 endpoint、同一请求参数，在 2026-09-30 与 2026-10-05 两次运行结果显著不同（参数 JSON 可解析率 1.0000→0.8431、格式退化 0→8 条），即 **provider 侧版本不可检测、不可固定**。另：该 endpoint 的 `response_format: json_schema`（`strict: true`）**未被强制**，输出形态会在「数组／裸对象／裸 arguments」间漂移。→ **任何云端结论必须标注"依赖 provider 版本、跨日不可比"；任何云端对照必须同日同批完成；跨日云端数据不得用于单变量归因。** 见 `docs/known-issues.md` **ISS-027 / ISS-028**、`docs/risk-register.md` **R-V1-9 / R-V1-10**、`experiments/v1/EXP-M02-013-014.md`** | **✅ 已锁定（2026-09-28，EXP-V1-002 实测后）** | `env/cloud.json`；`docs/role-decision.md` §七；`reports/P0-summary.md` §二 V1 行 |
| 11 | **Ollama：升不升 0.34.3 的决策** | ✅ **已决（2026-09-24）**：**锁定 0.34.2**，不升级（ISS-009）；V1 实测已按 0.34.2 开跑 | 已写入 §二.2.3 版本行；V1 报告记 Ollama 版本 | `reports/v1-report.md` §二.2.1；`docs/role-decision.md` §5.3；`docs/known-issues.md` ISS-009；`docs/risk-register.md` D1-P4 / R-新3 |
| 12 | **Redis checkpointer（LangGraph 集成）** | **✅ 已锁定但**未采用**（2026-09-24）**：`langgraph-checkpoint-redis==0.5.2` 已锁；但候选 A 因 **B7（redis-py↔redis-stack 连接握手被关闭）** 阻塞，V5 弃 Redis、**采用 PostgreSQL checkpointer**（§三 第 12b 行）。根因非"缺 RediSearch" | **✅ 已锁定** | `docs/version-lock.md` §二.2.9（新增）；`reports/v5-report.md` §6.2（B7）；`docs/checkpoint-decision.md` §2.1（采纳 PG）；`docs/known-issues.md`（redis-py 兼容登记） |
| 12b | **PostgreSQL checkpointer（LangGraph，V5 采纳路线）** | **✅ 已锁定（2026-09-24 实测）**：`langgraph==1.2.12` / `langgraph-checkpoint==4.2.0` / `langgraph-checkpoint-postgres==3.1.2` / `langgraph-sdk==0.4.5` / `psycopg==3.3.6` / `psycopg-pool==3.3.3` / `langchain-core==1.6.4`（详见新增 **§二.2.9**）；DB = `auscult_v2`（ParadeDB PG18.6 @5927，root/123456），PostgresSaver 已建 checkpoint 表 | **✅ 已锁定（V5 采用）** | `docs/version-lock.md` §二.2.9；`reports/v5-report.md` §2.2/§6.3；`docs/checkpoint-decision.md` §2.1 |
| 13 | **reranker 模型** | ✅ **已选用 & 锁定（2026-09-29）**：**本地 ModelScope `BAAI--bge-reranker-v2-m3`**（`D:\modelscope\hub\models\BAAI--bge-reranker-v2-m3\snapshots\master`，XLMRoberta re-ranker，hidden 1024，≈2.1GB safetensors），已移入 §二.2.2.2 | ✅ 已锁定（用户选定本地模型） | `docs/version-lock.md` §二.2.2.2；`reports/v4b-report.md` §6.3；`reports/v2-report.md` §1.2 |
| 14 | **Sparkplug B 模拟器**（V3 输入） | ✅ **已实现（2026-09-24）**：自建 `scripts/spb_simulator.py`（带 `--selftest` / `--scenario birth,new_metric,rebirth,offline,ndeath`），四类边界实测通过 | 本脚本无独立 digest，锁定其依赖（§二.2.7，与解码器共用 `.proto`/`paho-mqtt`） | `docs/version-lock.md` §二；`docs/sparkplug-b-decoder.md` §八；`reports/v3-auth.md` §6.2 |
| 15 | **应用后端 / 前端运行时** | ⚠️ **部分处置（2026-09-29）**：后端 Python 依赖锁文件 `requirements.txt` **已落盘**（摘要 §二.2.7/2.8/2.9，逐版本锁定）；**前端 Node 依赖锁文件不适用（Phase 0 无前端工程/无 `package.json`/`node_modules`，前端未开发）**，首版前端锁延至 P1 前端落地时再补。工具链 Python 3.12.8 / Node v24.19.0 已锁定见 §二 | 后端 ✅（已落盘）；前端 ⏳ P1 前端落地时补 | `docs/version-lock.md` §二；`docs/handover-p1.md` |
| 16 | **自研解码器 Dockerfile 基础镜像**（`Dockerfile.decoder` `FROM python:3.12-slim`） | ✅ **弃用，无需锚定 digest（2026-09-29，方案 A）**：解码器改由**本地 /venv python 直跑**（不再构建/运行该镜像），base 镜像 digest 锁定项随弃用消除。`Dockerfile.decoder` 保留（含弃用注释）供审计追溯；若 P1 重新容器化，须先在干净机/网络恢复后 `docker images --digests python` 实测回填再锚定 | ✅ 已消除（弃用） | `docs/version-lock.md` §二.2.7；`docker/Dockerfile.decoder`；`docker/compose.ingest.yml`（变更记录）；`docs/sparkplug-b-decoder.md` §八 |

> ⚠️ **红线提示**：`docker/compose.base.yml` 的 `tdengine` 已由 `tdengine/tdengine:latest` 整改为精确 digest（**2026-09-28**，`tdengine/tsdb:3.3.8.0@sha256:36e2…56bf`）；`neo4j` 已整改为精确 digest（**2026-09-28**）；**`eclipse-mosquitto:2` 已于 2026-09-28 整改为精确 digest**（`compose.base.yml` + `compose.ingest.yml`）；`compose.base.yml` 全部 8 镜像与 `compose.v2.yml` 各镜像均已锚定精确 digest，**纪律 1（禁止裸 tag）已在本项目全部 compose 编排满足**。新增自研解码器 Python 依赖锁定见 **§二.2.7**。

### 2.7 自研 Sparkplug B 解码器（Python 依赖，方案已定稿）

> **来源**：`docs/sparkplug-b-decoder.md`（M1–M6 模块 + 工期 ≈1.9 人日）；映射配置 `configs/decoder_schema_mapping.json`。
> **状态口径（2026-09-24）**：`protobuf`/`grpcio` 为**已实测**；`grpcio-tools`/`paho-mqtt`/`taospy` 均**已装复核**（下表 ✅）；`.proto` 已落地 `protos/sparkplug_b.proto`。全部经 `--selftest`（decoder + simulator）通过。

| # | 组件 | 版本 | 来源/状态 | 用途 |
|---|---|---|---|---|
| 1 | `protobuf` | **7.36.2** | ✅ 本机实测（`python -m pip show protobuf`） | Sparkplug B Protobuf 解析 |
| 2 | `grpcio` | **1.84.0** | ✅ 本机实测（`python -m pip show grpcio`） | 与 `grpcio-tools` 配套（仅编译期） |
| 3 | `grpcio-tools` | **1.84.0** | ✅ **已装复核（2026-09-24）**：`python -m grpc_tools.protoc` 生成 `protos/sparkplug_b_pb2.py`（M1） | 生成 `sparkplug_b.proto` PB 类（仅编译期，容器无需） |
| 4 | `paho-mqtt` | **2.1.0** | ✅ **已装复核（2026-09-24）** | MQTT 订阅（Mosquitto 客户端，M2） |
| 5 | `taospy` | **2.8.10** | ✅ **已装复核（2026-09-24）** | 写入 TDengine `st_pump_metrics` 等。**注意**：原生 `taos.connect`（6030）需 TDengine 客户端库 `libtaos`，本机未装；本项目走 **REST 6041**，用 taospy wheel 内自带的 **`taosrest` 模块**（`taosrest.connect(url=...)`），无需 libtaos |
| 6 | Sparkplug B `.proto` | **Eclipse Sparkplug B 规范配套 .proto**（来源 `eclipse/tahu` master `sparkplug_b/sparkplug_b.proto`，sha256 `4432C5C4...F0B4A19`，license EPL-2.0） | ✅ **已落地（2026-09-24）**：`protos/sparkplug_b.proto` | 协议定义（M1），与模拟器共用 |

> 🔧 **写入通道修正**：方案早期表述为"taospy 官方 Python 客户端走 6041"，落地核验发现其原生 `taos` 连接（6030）依赖 TDengine 客户端库 `libtaos`（本机/容器均未装）。实际采用 **REST 6041 + `taosrest`**（随 `taospy==2.8.10` wheel 分发，无需独立安装、无需 libtaos），与 `docker/compose.ingest.yml` 的 6041 端口映射及 §四 `INSERT ... USING ...` 经 REST 可达的表述吻合。

> ⚠️ **纪律**：以上 Python 包中，凡 `pip` 实际装到的版本与上表不符，**一律以实装版为准**回填本表并锁，不得沿用表内估算。`paho-mqtt`/`taospy`/`grpcio-tools` 安装后须立即执行 `pip freeze` + 解码器 `--selftest` 复核，再写入 `reports/v3-auth.md` 第二段实测。

---

### 2.8 V2 检索方案新增锁定项（2026-09-25 实测）

> 本节登记 V2 混合检索实测的新锁定项，供 `reports/v2-report.md` 与 P1 建库基线引用。

| 项 | 实测值 / 说明 |
|---|---|
| **Python 依赖（项目 `.venv`，uv/3.12）** | `pymilvus==3.0.2`、`psycopg[binary]==3.3.6`、`jieba==0.42.1`（建库脚本 `scripts/v2_pg_build.py`） |
| **BGE-M3 向量维度** | **1024（实测）**；经 Ollama `/v1/embeddings`（Ollama 0.34.2） |
| **Milvus 本实例端口（偏移）** | **19531（gRPC）/ 9092（metrics）** —— 因宿主上 kbrag_milvus 占用 19530/9091 而偏移；独立实例 `auscult-v2-milvus`（`docker/compose.v2.yml`） |
| **PostgreSQL 宿主端口（偏移）** | **5433（2026-09-28 改）** —— 原 5927 又被该项目 `smart-doc-db` 占用，故再偏移；库 `auscult_v2`，root/123456 |
| **PostgreSQL 镜像/扩展** | ParadeDB 官方镜像 `paradedb/paradedb@sha256:188591a0bc…686cf`（PG 18.6 Debian）；`vector 0.8.4`、`pg_search 0.25.10`、`pg_stat_statements`（存在；真 BM25 **已由 K-V2-1 验证可用**） |
| **真 BM25 状态** | **✅ 可用（2026-09-28 K-V2-1 闭环）；对标已闭环（EXP-V2-BM25）**：`USING bm25` + `INSERT` 成功——正当 `key_field`（主键列）+ `tokenizer:{type:'ngram',min_gram:2,max_gram:3,prefix_only:false}`（镜像无 chinese/zhparser）。可用中文子串召回；**对标：sparse `Recall@5`=0.90（vs Milvus 0.92）、hybrid 打平 0.91**（`experiments/v2/raw/EXP-V2-BM25.md`） |
| **RRF k（混合融合）** | **k=60（实测选定）** |
| **`kb_chunks` 表** | 100 行、维度 1024（`scripts/v2_pg_build.py` 建成） |

> ⚠️ **对照对标声明（2026-09-28 更新）**：V2 稀疏路线**真 BM25 对标已闭环（EXP-V2-BM25，ngram vs jieba 口径差异已显式声明）**：ParadeDB 真 BM25 sparse `Recall@5`=0.90（vs Milvus 0.92）、hybrid 打平 0.91；结论范围扩展为『两实现 BM25 对比』，tsvector 降级淘汰（`reports/v2-report.md` §4.3）。

---

### 2.9 V5 LangGraph checkpoint 依赖锁定（2026-09-24 实测）

> **来源**：`reports/v5-report.md`（V5 实测，M0.4）`docs/checkpoint-decision.md`。
> **罕见决策**：V5 原默认候选 A（Redis checkpointer）因 **B7（redis-py↔redis-stack 连接握手被关闭）** 阻塞，经用户批准**采用候选 B（PostgreSQL checkpointer）**。以下为实际锁定与采用的依赖版本。

| # | 组件 | 版本 | 实测 digest / 依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `redis` 镜像 | `8` | `sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5`（§二.2.1 第 5 行） | ⚠️ 锁定但**非 checkpointer 存储**（B7） | 辅助锁/审计（`configs/redis.conf`，`noeviction`+无 TTL） |
| 2 | `redis`(py 客户端) | **6.3.0** | 实测 `importlib.metadata`（8.1.0 已降级） | ⚠️ 已锁；**连线被服务端关闭**（B7 根因，8.1.0/6.3.0 均复现） | go-redis 不涉；redis-py 客户端 |
| 3 | `redisvl` | **0.27.2** | 实测装定 | ✅ 已锁 | 向量检索（V2） |
| 4 | `langgraph` | **1.2.12** | 实测装定 | ✅ 已锁 | 图执行引擎 |
| 5 | `langgraph-checkpoint` | **4.2.0** | 实测装定 | ✅ 已锁 | checkpoint 核心 |
| 6 | `langgraph-checkpoint-postgres` | **3.1.2** | 实测装定 | ✅ **已锁（V5 采纳路线）** | PostgreSQL checkpointer（PostgresSaver） |
| 7 | `langgraph-checkpoint-redis` | **0.5.2** | 实测装定 | ⚠️ **已锁但未采用**（B7 弃 A） | Redis checkpointer（候选 A，放弃） |
| 8 | `langgraph-sdk` | **0.4.5** | 实测装定 | ✅ 已锁 | LangGraph 相关 SDK |
| 9 | `langchain-core` | **1.6.4** | 实测装定 | ✅ 已锁 | LangChain 核心 |
| 10 | `psycopg` | **3.3.6** | 实测装定（与 §二.2.8 一致） | ✅ 已锁 | PG 驱动（含 checkpointer） |
| 11 | `psycopg-pool` | **3.3.3** | 实测装定 | ✅ 已锁 | PG 连接池 |

> **checkpoint 存储数据**：DB = `auscult_v2`（ParadeDB PG18.6 @5927，root/123456）。PostgresSaver 已建检查点表：4 表合计 ≈ **296 KB**（`checkpoints` 29 / `checkpoint_writes` 55 / `checkpoint_blobs` 29 / `checkpoint_migrations` 10），总 DB ≈ 8.66 MB。
> ⚠️ **B7 说明（勿误写）**：根因 = **redis-py 连接握手被 redis-stack 服务端关闭**（"Connection closed by server"，`CLIENT SETINFO` / `on_connect_check_health`；`redis-cli` 正常 PONG）。**不是"缺 RediSearch"**。详见 `reports/v5-report.md` §6.2。

---

## 四、与各报告的交叉引用

> **引用方式统一为**：报告在首部声明环境基线版本号，并在正文引用本文件的**具体小节**；凡本文件为「待锁定」的条目，报告中一律写 `【待 D<天> 实测填入】`，不得填估算值。

| 报告 / 文档 | 引用方式 | 具体引用位置 |
|---|---|---|
| `reports/v1-report.md` | 引用 §二.2.1（模型 digest）、§二.2.3（工具链）、§二.2.5（实验固定参数）、§三 第 10–11 行（云端 baseline 模型、Ollama 升版决策） | §2.1 模型版本与 digest；§2.3 待登记项；§八 R-V1-6 |
| `reports/v2-report.md` | 引用 §二.2.1（Milvus / etcd / MinIO / postgres digest）、§三 第 3–6 行（BGE-M3、pgvector、ParadeDB） | §2.1 已实测事实；§2.3 待登记项；§三.3.1「写入 `docs/version-lock.md`」 |
| `reports/v3-auth.md` | 引用 §三 第 1–2、8、9、14 行（TDengine、taosX、Mosquitto、EMQX、模拟器） | §一「结论写入 `docs/version-lock.md`」；§5.2；§十一 Compose 片段注 |
| `reports/v4b-report.md` | 引用 §二.2.4（硬件与 WSL 配额）、§二.2.1（镜像 digest 基线）、§三 第 3、7、13 行 | §3.6 待登记的组件规模；§7.3 前置阻塞项；§十三 复现命令（`docker images --digests`） |
| `reports/daily/D1-status.md` | 引用 §二.2.3（Ollama 0.34.2 / 0.34.3）、§二.2.1（Milvus digest）、§二.2.2（模型 digest） | §3.6 工具链版本；§四 D1-P4；§五 待办第 6 条 |
| `docs/role-decision.md` | 引用 §二.2.2（两个本地模型 digest 与量化档）、§三 第 10、11 行 | §2.2 候选模型；§5.3 风险三；§六.3 复核记录；§八 下游依赖 |
| `docs/checkpoint-decision.md` | 引用 §二.2.1（`redis:8` digest）、§二.2.9（LangGraph / PG checkpointer 依赖，V5 采纳） | §五.5.3 降级执行清单第 ⑦ 步「同步更新 docs/version-lock.md」｜§2.1 采纳结论 |
| `docs/experiment-log-template.md` | **强制**：`image_model_digests` 字段必须与本文件逐字一致；引用本文件 §一 纪律（不一致即结论作废） | §二.2.1 字段纪律；§五「报告引用纪律」第 2 条「见 `docs/version-lock.md` §纪律」 |
| `docs/known-issues.md` | 引用 §二.2.1（Redis digest）、§三 第 11、12 行（Ollama、checkpointer 版本） | §二 ISS-005 规避手段①、ISS-009 规避手段③；§四「需换方案」后续动作「更新 `docs/version-lock.md`」 |
| `docs/review-lifecycle.md` | 引用 §二.2.1（`redis:8` digest） | §八.8.2 降级路径 L2（存储层降级须同步版本） |
| `docker/compose.base.yml` | **反向依赖**：其 Neo4j 段注释「版本待锁定（`version-lock.md` 中为"待锁定"行）」即指本文件 §三 第 7 行 | `docker/compose.base.yml` 第 148–149 行 |
| `schemas/tools_v1.json` | **反向依赖**：其 `change_policy` 字段要求「同步更新 version-lock.md」 | `schemas/tools_v1.json` `change_policy`；本文件 §一 纪律 4、§二.2.6 |

---

## 五、修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| 2026-09-23 | 单人（本人） | 初始建立：§一 纪律（digest 唯一性 / 变更即升版 / 不一致即作废 / Schema 变更即升版）；§二 已锁定清单（8 镜像 + 2 模型 + 工具链 + 硬件 + 实验固定参数 + 冻结 Schema，数据逐字取自 `env/env-baseline-v2.md` 与 `env/hardware.json`）；§三 待锁定清单（15 行）；§四 交叉引用 | — |
| 2026-09-24 | 单人（本人） | **T1.1 已安装核验**：更新 §二.2.4 的 WSL2 配额为 ≈20GB / 10vCPU / 8GB 与 `docker info` 实测值；`env-baseline-v2.md` 已升版 v2 | §二.2.4；§三 第 1、7 行 |
| 2026-09-24 | 单人（本人） | **T1.9 授权定稿 + 解码器依赖锁定**：TDengine 由 `tdengine/tdengine:latest` 整改为 `tdengine/tsdb:3.3.8.0` 并实测锁定 digest（移入 §二.2.1 第 9 行）；新增 §二.2.7 自研解码器 Python 依赖（protobuf/grpcio 实测，paho-mqtt/taospy/grpcio-tools 待装）；同步红线提示 | §二.2.1、§二.2.7、§三 第 1 行、红线提示 |
| 2026-09-24 | 单人（本人） | **解码器依赖装齐 + 写入通道修正（U-08 编码阶段）**：`grpcio-tools 1.84.0`/`paho-mqtt 2.1.0`/`taospy 2.8.10` 已装并 `--selftest` 通过；`.proto` 落地 `protos/sparkplug_b.proto`（tahu master，sha256 已登记）；原生 `taos` 连接需 `libtaos` 未装，改用 **REST 6041 + 随 taospy 自带的 `taosrest`**，并补充说明 | §二.2.7（替换"待装"标注 + 状态口径） |
| 2026-09-25 | 单人（本人） | **V2 检索锁定项回填**：BGE-M3 锁入 §二.2.2（blob digest、dim1024、Ollama 0.34.2）；§三 第 3–6 行标记已锁定（PostgreSQL/ParadeDB 镜像 digest）；新增 §二.2.8（pymilvus 3.0.2/psycopg 3.3.6/jieba 0.42.1、Milvus 端口 19531/9092、PG 端口 5927、RRF k=60、真 BM25 悬置说明） | §二.2.2、§二.2.8、§三 第 3–6 行 |
| 2026-09-28 | 单人（本人） | **K-V2-1 真 BM25 闭环 + PG 端口再偏移**：§二.2.8「真 BM25 状态」由悬置改 ✅ 可用（ngram tokenizer，`experiments/v2/raw/K-V2-1.md`）；PG 宿主端口 5927→**5433**（5927 被该项目 `smart-doc-db` 占用），`run_v2.py --dsn` 同步改 5433；`docker/compose.v2.yml` 映射同步 | §二.2.8；`scripts/run_v2.py` |
| ~~【待 D4】~~ → **2026-09-29 完成** | 单人（本人） | 将 §三 第 3–9、14 行移入 §二 并补齐 digest（BGE-M3 / pgvector / ParadeDB / Mosquitto / 模拟器）；整改 `docker/compose.base.yml` 的**剩余 1 处裸 tag**（`eclipse-mosquitto:2`；`neo4j` 已于 **2026-09-28** 整改）。**完成注（2026-09-29）**：BGE-M3/ParadeDB/Neo4j/Mosquitto 已于 09-25/09-28 各行锁定；`eclipse-mosquitto:2` 裸 tag 已于 2026-09-29 清零（见下）。**模拟器（第14行）无独立 digest，保持"已实现、锁依赖"** | §二.2.1；§三 |
| ~~【待 D6–D7】~~ → **2026-09-24 完成** | 单人（本人） | **V5 LangGraph checkpoint 依赖锁定（M0.4）**：新增 §二.2.9（langgraph 1.2.12 / checkpoint 4.2.0 / checkpoint-postgres 3.1.2 / checkpoint-redis 0.5.2 / langgraph-sdk 0.4.5 / langchain-core 1.6.4 / redis 6.3.0 / redisvl 0.27.2 / psycopg 3.3.6 / psycopg-pool 3.3.3）；修正 §三 第 12 行为"已锁但未采用（redis-py↔redis-stack B7）"并新增第 12b 行（PG checkpointer 采纳）；§四 更新 checkpoint-decision 交叉引用 | §二.2.9；§三 第 12/12b 行 |
| ~~【待 D8】~~ → **2026-09-29 完成** | 单人（本人） | 锁定 reranker 模型与 digest（§三 第 13 行移入 §二）。**完成注（2026-09-29）**：用户选定**本地** ModelScope `BAAI--bge-reranker-v2-m3`（无需联网），移入 §二.2.2.2 并锁定；§三 第 13 行已改「已选用 & 锁定」 | §二.2.2.2；§三 |
| 2026-09-28 | 单人（本人） | **Neo4j 收尾锁定（b5）**：核对 docker 实测 digest 与 §二.2.1 第 11 行一致（`sha256:ab3aafb…d61`）；§三 第 7 行由「待锁定」改「✅ 已锁定」；`compose.base.yml` neo4j 段补精确 digest（纪律 1）；红线提示同步——仅余 `eclipse-mosquitto:2` 裸 tag 待整改 | §二.2.1、§三 第 7 行、red line；`docker/compose.base.yml` |
| 2026-09-28 | 单人（本人） | **云端 baseline 模型锁定（EXP-V1-002 实测后）**：§三 第 10 行由「待锁定（`<cloud-model>`）」改「✅ 已锁定」——provider `openai` / model `Qwen/Qwen3.8-27B` / modelscope endpoint，上界校准首次成功率 0.60；`env/cloud.json` 置 `is_locked=true`（含 API key，`.gitignore` 忽略） | §三 第 10 行；`env/cloud.json` |
| 2026-09-28 | 单人（本人） | **清理非本项目镜像行（§二.2.1）**：按用户指示移除 `nacos/nacos-server`、`mysql`、`mongodb/mongodb-atlas-local` 三行（原 6–8 行，均为"其他项目在用"），顺延 tdengine/mosquitto/neo4j 为新第 6–8 行；镜像总数由「14 个/约 13.4 GB」更正为本项目 **8 个 / 约 7.8 GB**（表中 8 行求和建议值，非实测）；保留「禁止 prune 非本项目容器」红线并改为引用 R-V3-7 / R-V4b-8 | §二.2.1 表格、镜像总数注释 |
| 2026-09-28 | 单人（本人） | **真 BM25 稀疏对标闭环（EXP-V2-BM25，M0.3 补齐）**：§二.2.8「真 BM25 状态」由"可用"补"对标已闭环"（ParadeDB 真 BM25 sparse `Recall@5`=0.90 vs Milvus 0.92、hybrid 打平 0.91）；对照对标声明更新为"结论范围扩展为两实现 BM25 对比，tsvector 降级淘汰" | §二.2.8；`experiments/v2/raw/EXP-V2-BM25.md` |
| 2026-09-29 | 单人（本人） | **reranker 本地选用 & 锁定（用户选定本地模型）**：§三 第 13 行由「待锁定」改「✅ 已选用 & 锁定」，移入新建 §二.2.2.2；本地 `BAAI--bge-reranker-v2-m3`（`D:\modelscope\hub\models`，XLMRoberta，hidden 1024，≈2.1GB safetensors，纯本地、与 Ollama 无关）；`【待 D8】` 占位行标记完成。**注**：此为模型选用，safetensors 无单一 Docker 级 digest，以「本地路径 + 架构 + 文件大小」作为复现依据 | §二.2.2.2；§三 第 13；§五 |

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
