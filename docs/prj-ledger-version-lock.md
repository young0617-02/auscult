# 版本锁定清单（Version Lock）v1

> **对应任务**：T9.1（版本锁定清单）
> **里程碑**：M0.5（D9）；随 `reports/p0-gate-review.md` 一并过 M0.6
> **上游依据**：`p0-plan-detailed-d1-d10.md` §三 D9（T9.1）、§六.1
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

> **纪律 4（Schema 变更即升版）**：**Schema 变更 → 必须升版为 `tools_v2.json`**。依据 `schemas/tools_v1.json` 的 `change_policy` 字段原文：「本文件一经冻结，任何修改必须升版为 v2 并同步更新 prj-ledger-version-lock.md；否则 V1 全部结论作废」。

### 1.1 纪律细则

| # | 规则 | 违反后果 |
|---|---|---|
| 1 | 本文件是**唯一版本权威**。任何报告引用的组件/模型版本必须能在本文件找到对应行，且**逐字一致（含 digest）**。 | 结论作废 |
| 2 | §二 的每一行数据**逐字取自** `env/env-baseline-v2.md` 与 `env/hardware.json`；**不得**在本文件中"改进"或"补全"上游未实测的字段。 | 视为编造实测数字，违反 Phase 0 铁律 |
| 3 | 环境基线升版（`env-baseline-v2.md` → v2）时，本文件必须同步升版，并逐条复核 §二。 | 版本不一致，全部结论不可复现 |
| 4 | 未锁定的组件**不得**出现在任何实验报告中作为"已采用版本"；一律写 `【待 D<天> 实测填入】`。 | 视为过度声称 |
| 5 | 新拉取的镜像/模型**必须立即回填**本文件并锁 digest（基线 §7.1 明示要求）。 | 复现条件不完整 |
| 6 | 本文件在 P0 结束时随 `docs/p0-handover-p1.md` 移交，作为 P1 的版本基线输入。 | — |

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
| 9 | `prom/prometheus` | `latest`（锚 digest） | `sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e` | 381 MB | **P5 监控栈（临时，压测期起、测后销毁）** | **实测 2026-10-10**（D14 压测拉取，`reports/p5-perf.md` §七） |
| 10 | `grafana/grafana` | `11.1.0` | `sha256:079600c9517b678c10cda6006b4487d3174512fd4c6cface37df7822756ed7a5` | 604 MB | **P5 监控栈看板（临时，同上）** | **实测 2026-10-10**（本地已有镜像锚 digest） |

> ⚠️ **镜像总数 / 占用**：**10 个（本项目）/ 约 8.8 GB**（仍以 `env-baseline-v2.md` §7.1 为唯一镜像基线；宿主上其他项目镜像如 nacos/mysql/mongodb 已从本表移除，但本机容器仍在，**禁止** `docker system prune` 或停止非本项目容器，见 `docs/prj-ledger-risk-register.md` R-V3-7 / R-V4b-8）。
> ⚠️ **BGE-M3 经 ModelScope 本地加载**（`D:\modelscope\hub\models\BAAI--bge-m3`，非 Docker 镜像、非 Ollama 模型，见 §2.2.1）；Neo4j 已在本表第 8 行锁定。D6/D7 新增镜像拉取后必须立即回填本表并锁 digest。
> ✅ `milvusdb/milvus:v3.0.0` 与上游计划 §二 Q3 裁决一致（v3.0.0 + 服务端 `FunctionType.BM25`），无偏差。
> ✅ `tdengine/tsdb:3.3.8.0` 的 tag 与 digest 已实测锁定；其镜像名相对上游 `tdengine/tdengine` 的变更与授权判定见 `reports/p0-report-v3-ingest-license.md` §〇/§四.1（T1.9 需降级 = OSS + 自研解码器）。

### 2.2 Ollama 生成模型（2 个，实测 digest）

| 模型 | 模型层 Digest | Manifest config Digest | 大小 | 用途 | 来源 |
|---|---|---|---|---|---|
| **`qwen2.5:7b`** | `sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730` | `sha256:2f15b3218f0552c60647ce60ada83632d2c09755b16259b13e3e4458e9ae419d` | 4.68 GB | 候选 A（通用指令模型） | `env-baseline-v2.md` §8.1 |
| **`deepseek-r1:7b`** | `sha256:96c415656d377afbff962f6cdb2394ab092ccbcbaab4b82525bc4ca800fe8a49` | `sha256:40fb844194b25e429204e5163fb379ab462978a262b86aadd73d8944445c09fd` | 4.68 GB | 候选 B（推理模型，含 `think`） | `env-baseline-v2.md` §8.1 |

> **模型根目录**：`D:\.ollama\models`；**API 端点**：`http://127.0.0.1:11434`（实测 OCCUPIED，PID 80484，**预期占用**）。
> **Manifest digest 说明**：上表 manifest config digest 与模型层 digest 均为 `env-baseline-v2.md` §8.1 登记值；**manifest 路径见 `env/hardware.json` 的 `models[].manifest_path`**（如 `D:\.ollama\models\manifests\registry.ollama.ai\library\qwen2.5\7b`）。
> **V1 报告必须原样引用上表 digest**，否则结论无法复现。
> ⚠️ **量化档已登记（2026-09-29 实测）**：`qwen2.5:7b` 与 `deepseek-r1:7b` **均 Q4_K_M**（`ollama show` 实测，对应 `docs/prj-ledger-known-issues.md` ISS-012，已拉齐，对比公平性成立）；胜出者 Q8/FP16 复核为 P1 遗留。

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
| uv（Python 包/环境管理） | **0.11.31** | `uv`（PATH，`uv --version`） | 实测 2026-10-10（P5 收尾方案 A） |
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

> ✅ **Python 环境口径统一为 uv（2026-10-10，方案 A）**：项目 `.venv` 由 **uv 0.11.31** 创建（`pyvenv.cfg` 含 `uv = 0.11.31`，无 pip）。仓库根新增 **`.python-version` = 3.12** 作为解释器发现的唯一锚定（与 §2.3 Python 3.12.8 一致）。命令口径：建环境 `uv venv --python 3.12`、装依赖 `uv pip install -r requirements.txt`、运行一律 `.venv\Scripts\python.exe`。
> **不升版 env-baseline-v2**：该文件 §引用纪律 的 5 条升版触发条件（镜像 digest / 模型 digest / Ollama·Docker·WSL2 版本 / `.wslconfig` / 硬件）均不含解释器与包管理工具 → v2 结论不受影响、快照指纹不破坏。
> ⛔ **`uv pip sync` 口径（2026-10-10 实测复核，纠正当日早前表述）**：`uv pip sync` **不解析传递依赖**——`uv help pip sync` 原文「The input file is presumed to be the output of a `pip compile` or `uv export` operation, in which it will include all transitive dependencies. If transitive dependencies are not present in the file, they will not be installed.」。实测：对本项目 `requirements.txt`（仅直接依赖）`--dry-run` 的计划为**移除 136 个包**；未锁定文件（仅 `fastapi`）亦只解析 1 个包。→ **禁止直接 `uv pip sync requirements.txt`**；安全用法 = 先 `uv pip compile requirements.txt -o requirements.lock.txt`，再 sync 该产物。方案 C（`uv.lock`）于 P6 D6/D7 落地后转为确定性口径。
> ✅ **【已补声明】requirements.txt 与环境实装漂移已闭环（2026-10-10，用户批准）**：下列**已被代码 import 且已实装、此前未进 `requirements.txt`** 的直接依赖已补齐声明并登记本表 **§二.2.24**：`sentence-transformers` / `ragas` / `locust` / `prometheus-client` / `numpy`。补声明后 `uv pip install -r requirements.txt --dry-run` 解析 **164 包**，与 `.venv` 实装差异收敛至 **3 处版本级差异**（`langchain` / `langchain-core` / `langchain-openai`，见 §二.2.24 🔴 待裁决项）。**未升版 `env-baseline-v2.md`**（仅补 Python 包声明，未触及 §引用纪律 的 5 条触发条件）。

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
| GPU 直通（WSL2 内） | ⚠️ **UNVERIFIED**，但 **已裁决改走宿主原生 Ollama（2026-09-24，U-03）**：推理统一走宿主 `127.0.0.1:11434`（qwen2.5:7b / deepseek-r1:7b / BGE-M3），容器仅承载 DB/存储，不承载模型推理 → **GPU 直通不再阻塞** | `env-baseline-v2.md` §六.2；`docs/prj-ledger-known-issues.md` ISS-008 |
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
- **prj-ledger-version-lock §一 纪律 4 口径**：**Schema 变更 → 必须升版**（v1→v2→v3），快照保留不删，变更原因写入上表。

> ⚠️ **活动版本回退说明**：v3 曾短暂作为活动版（P5 简化），经 EXP-V1-008 实测为负结果后**回退至 v2**。后续任何 Schema 改动 → 升 **v4** 并更新本表，**已完成的 V1 结论需按新版本重跑**。P5 的"减嵌套（time_range 摊平）"仍**押后未做**（可解析率已满分，结构无余量）。

---

### 2.7 V1 提示词版本状态（2026-10-06 新增；**含反泄漏审计结论**）

> **来源**：`reports/p0-audit-v1-refusal-2026-10-06.md` §2（反泄漏审计）、`experiments/v1/EXP-M02-020-022.md`（H11 验证）
> **硬约束（新增）**：任何提示词的 `user:` 示例行**不得**与 `evals/**` 中任何用例的 `input` 逐字或近似重合；
> **每次改动示例后必须重跑重合审计**，零重合方可使用。

| 版本 | 文件 | 状态 | 反泄漏审计（20 主用例 + 5 迁移用例） | 说明 |
|---|---|---|---|---|
| **v1（评测活动）** | `prompts/tool_call_prompt_v1.md` | ✅ **可用于评测** | 逐字 **0** / 近似 0 ｜ 最高相似度 **0.746** | 3 条 few-shot。**当前所有有效结论均基于 v1**（含四臂矩阵 `EXP-M02-016`~`-019`） |
| **v2** | `prompts/tool_call_prompt_v2.md` | ⛔ **禁止用于评测**（含测试集泄漏） | 逐字 **7** ｜ 最高相似度 **1.000** | 8 条 few-shot 中 **7 条与测试用例 `input` 逐字相同** → **`ISS-032` / `R-V1-12`**。**仅作教学稿保留**；其**通用规则（6a/6b/6c）本身是干净的、可复用**，脏的是**示例** |
| **v4（候选，未采纳；⭐ 当前最优候选）** | `prompts/tool_call_prompt_v4.md` | ⭐ **当前最优候选（未达全档 Pass）** | 逐字 **0** / 近似 0 ｜ 最高相似度 **0.746** | = v1 + **最小拒止强化**（规则 6 合并为 6a/6b/6c）+ 1 条**非镜像**示例（齿轮箱越界）。`EXP-M02-009`（09-30）实测 **0.85 / 拒止 100% / `4a=0`**；**同日同通道新口径复核（`EXP-M02-024` / `-025`，2026-10-06，`--transport tools` + 路径 B 用例集）**：**今日唯一整体非 No-Go 的臂**（整体 → 中间区间）、主集 **`4a=0`**、**无泄漏迁移集 15/15**；代价：单工具 **100% → 78%**。→ **仍非"采纳"**（未达全档 Pass，`M0.2` 仍 No-Go） |
| **v5（实验版，未采纳）** | `prompts/tool_call_prompt_v5.md` | ⚠️ **实验版，暂不采纳**（192 行 / sha256 `42923e4f175d`） | 逐字 **0** / 近似 0 ｜ 最高相似度 **0.746** | = v1 + 通用拒止规则 6a/6b/6c + 示例 4（定指拒止，措辞不重合）。**与 v4 设计同源**（独立撰写）。**H11 实测**：✅ 拒止卡点消除（主集无效拒绝 67%→100%、`v1-016` 0/3→3/3）、✅ 规则可迁移（无泄漏迁移集 80%→100%）；**但净分 0.90→0.85**（`v1-019` 3/3→0/3、`v1-001` 3/3→0/3；该项**原归因"6b 误伤写工具"未证实、有反例**）→ **未采纳**（`prompt v4` 已同时达成拒止 100% 与 `v1-019` ✅，本版无额外收益）。⚠️ **命名事故**：内容最初误写入 `tool_call_prompt_v3.md`（覆盖历史资产，已恢复）；见 `ISS-033` |

---

## 三、待锁定清单

> **本节必须存在**：`docker/compose.base.yml` 中已明确注释「版本待锁定（`prj-ledger-version-lock.md` 中为"待锁定"行）」（Neo4j 段）。
> **纪律**：本节每一行在锁定后，必须**移入 §二**并补齐 digest，同时同步更新「锁定后须同步更新的文件」列所列文件。

| # | 组件 | 当前状态 | 何时锁定 | 锁定后须同步更新的文件 |
|---|---|---|---|---|
| 1 | **TDengine**（`tdengine/tsdb`） | **✅ 已锁定（2026-09-24 实测）**：`3.3.8.0` / `sha256:36e2bf82f151e8013d39a929aadc41bfcd5c46564866635cee1a02693d2256bf` / 1.68 GB，已移入 §二.2.1 第 9 行。镜像名由上游 `tdengine/tdengine` 改为 `tdengine/tsdb`（T1.9 授权已定稿 = 需降级，OSS + 自研解码器） | **✅ 已锁定** | `docs/prj-ledger-version-lock.md` §二.2.1；`docker/compose.base.yml`（`tdengine` 段，改精确 tag 已整改）；`reports/p0-report-v3-ingest-license.md` §十一；`docs/prj-spec-schema-mapping.md`；`docs/prj-ledger-risk-register.md` R8 / R-V3-1 |
| 2 | **TDengine taosX**（连接器） | **不采用（已裁决 2026-09-24）**：官方 Sparkplug B 连接器仅随 All-in-One/Enterprise；OSS 镜像 `tdengine/tsdb:3.3.8.0` 实测无 taosX；本项目改走 **OSS + 自研 Sparkplug B 解码器 ≤2 天**（`reports/p0-report-v3-ingest-license.md` §一–§四、§5.2） | ——（不再锁定官方连接器；解锁自研解码器版本） | `reports/p0-report-v3-ingest-license.md`；`docs/prj-ledger-version-lock.md` §二；`docs/prj-ledger-risk-register.md` R8 / R-V3-1 / R-新4；`docs/prj-spec-schema-mapping.md` |
| 3 | **BGE-M3 模型**（向量化） | **✅ 已锁定（2026-09-25 实测）**：经 Ollama `/v1/embeddings`（Ollama 0.34.2），blob `sha256:daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c`，1.2GB/bert 566.7M/F16，已移入 §二.2.2 第 3 行 | **✅ 已锁定** | `docs/prj-ledger-version-lock.md` §二.2.2；`reports/p0-report-v2-hybrid-retrieval.md` §二.2.3、§五；`docs/prj-spec-schema-mapping.md` |
| 4 | **BGE-M3 向量维度** | **✅ 已锁定（2026-09-25 实测）**：**维度 = 1024**（U-05 项3/4 由此锁定） | **✅ 已锁定** | `reports/p0-report-v2-hybrid-retrieval.md` §五（参数基线表）；`docs/prj-spec-schema-mapping.md`；P1 建库脚本 |
| 5 | **PostgreSQL + pgvector** | **⚠️ 已重新锁定（2026-09-25 实测）**：V2 改用 **ParadeDB 官方镜像** `paradedb/paradedb@sha256:188591a0bc317beb2c6d6d3f9ef0cb3e859d09ecc15a71dda5e9a027876686cf`（PG 18.6 Debian），宿主端口 **5433**（原 5927，2026-09-28 因被 `smart-doc-db` 占用整改），库 `auscult_v2`；扩展 `vector 0.8.4` + `pg_search 0.25.10`（真 BM25 已由 K-V2-1 闭环，ngram tokenizer）。原 `postgres:18` 行（§二 第 4 行）为业务库基线，**V2 检索实际走 ParadeDB** | **✅ 已锁定（V2 用）** | `docs/prj-ledger-version-lock.md` §二；`docker/compose.yml`（PostgreSQL 段）；`reports/p0-report-v2-hybrid-retrieval.md` §二.2.3 |
| 6 | **ParadeDB `pg_search`** | **✅ 已锁定（2026-09-25 实测）**：镜像 `paradedb/paradedb@sha256:188591a0bc…686cf`，pg_search **0.25.10**。**真 BM25 悬置未用（`USING bm25` 建索引后 INSERT 报 `No key field defined`，K-V2-1），V2 实际用 `tsvector` 降级**（对标未闭环，结论范围限于「Milvus 原生 BM25 vs PostgreSQL tsvector」） | **✅ 已锁定（版本）／BM25 悬置** | `reports/p0-report-v2-hybrid-retrieval.md` §4.3、§九（R-V2-3）；`docs/prj-ledger-risk-register.md` R-V2-3 |
| 7 | **Neo4j** | **✅ 已锁定（2026-09-24 实测）**：`neo4j:5-community` / `sha256:ab3aafb0020e6fed65bb2b59f7db1fabd7ee0568c4da46f3cc3b8fad77801d61`，已移入 §二.2.1；选型约束社区版已满足 | **✅ 已锁定** | `docs/prj-ledger-version-lock.md` §二.2.1；`docker/compose.base.yml`（neo4j 段，已补 digest）；`reports/p0-report-v4b-resources.md` §5.1；`docs/prj-ledger-risk-register.md` R-V4b-1 |
| 8 | **Mosquitto** | **✅ 已锁定（2026-09-24 实测）**：`eclipse-mosquitto:2` / `sha256:38c0da4f2ef84284d47b3b3eeea1cb3bdeabe81ee10caf0cd5c5ff61ee3ea408`（41.8MB），已移入 §二.2.1 | **✅ 已锁定** | `docs/prj-ledger-version-lock.md` §二.2.1；`docker/compose.base.yml`（`mosquitto` 段，补 digest）；`reports/p0-report-v3-ingest-license.md` §5.1；`docs/prj-ledger-risk-register.md` R-V3-2 |
| 9 | **EMQX**（Broker 备选） | **待锁定**：仅在 Mosquitto 无法满足时启用；启用前须先做端口检查（`18083` **不在** `env/ports.md` 冻结基线内） | 仅在被选用时锁定 | `docs/prj-ledger-version-lock.md` §二；`reports/p0-report-v3-ingest-license.md` §十一（注释段）；`reports/p0-report-v4b-resources.md` §8.1；`docs/prj-ledger-risk-register.md` R9 / R-V3-2 |
| 10 | **云端 baseline 模型**（上界校准） | **✅ 已锁定（2026-09-28 实测 EXP-V1-002）**：provider `openai`（openai_compatible），model **`Qwen/Qwen3.8-27B`**，endpoint `https://api-inference.modelscope.cn/v1/chat/completions`，支持 function calling；上界校准首次成功率 **0.60**（<0.90，判 No-Go 归因「用例/Schema 需复审 + 7B 上界受限」）。连接配置 `env/cloud.json`（含 API key，`.gitignore` 忽略，`is_locked=true`）。仅作上界校准，**不作默认部署**。⚠️ **【2026-10-05 增补声明】本行仅锁定"模型名"，云端模型**不可 digest 化**——实测同一模型名、同一 endpoint、同一请求参数，在 2026-09-30 与 2026-10-05 两次运行结果显著不同（参数 JSON 可解析率 1.0000→0.8431、格式退化 0→8 条），即 **provider 侧版本不可检测、不可固定**。另：该 endpoint 的 `response_format: json_schema`（`strict: true`）**未被强制**，输出形态会在「数组／裸对象／裸 arguments」间漂移。→ **任何云端结论必须标注"依赖 provider 版本、跨日不可比"；任何云端对照必须同日同批完成；跨日云端数据不得用于单变量归因。** 见 `docs/prj-ledger-known-issues.md` **ISS-027 / ISS-028**、`docs/prj-ledger-risk-register.md` **R-V1-9 / R-V1-10**、`experiments/v1/EXP-M02-013-014.md`** | **✅ 已锁定（2026-09-28，EXP-V1-002 实测后）** | `env/cloud.json`；`docs/p0-decision-model-role.md` §七；`reports/p0-gate-review.md` §二 V1 行 |
| 11 | **Ollama：升不升 0.34.3 的决策** | ✅ **已决（2026-09-24）**：**锁定 0.34.2**，不升级（ISS-009）；V1 实测已按 0.34.2 开跑 | 已写入 §二.2.3 版本行；V1 报告记 Ollama 版本 | `reports/p0-report-v1-tool-call.md` §二.2.1；`docs/p0-decision-model-role.md` §5.3；`docs/prj-ledger-known-issues.md` ISS-009；`docs/prj-ledger-risk-register.md` D1-P4 / R-新3 |
| 12 | **Redis checkpointer（LangGraph 集成）** | **✅ 已锁定但**未采用**（2026-09-24）**：`langgraph-checkpoint-redis==0.5.2` 已锁；但候选 A 因 **B7（redis-py↔redis-stack 连接握手被关闭）** 阻塞，V5 弃 Redis、**采用 PostgreSQL checkpointer**（§三 第 12b 行）。根因非"缺 RediSearch" | **✅ 已锁定** | `docs/prj-ledger-version-lock.md` §二.2.9（新增）；`reports/p0-report-v5-checkpoint.md` §6.2（B7）；`docs/p0-decision-checkpoint.md` §2.1（采纳 PG）；`docs/prj-ledger-known-issues.md`（redis-py 兼容登记） |
| 12b | **PostgreSQL checkpointer（LangGraph，V5 采纳路线）** | **✅ 已锁定（2026-09-24 实测）**：`langgraph==1.2.12` / `langgraph-checkpoint==4.2.0` / `langgraph-checkpoint-postgres==3.1.2` / `langgraph-sdk==0.4.5` / `psycopg==3.3.6` / `psycopg-pool==3.3.3` / `langchain-core==1.6.4`（详见新增 **§二.2.9**）；DB = `auscult_v2`（ParadeDB PG18.6 @5927，root/123456），PostgresSaver 已建 checkpoint 表 | **✅ 已锁定（V5 采用）** | `docs/prj-ledger-version-lock.md` §二.2.9；`reports/p0-report-v5-checkpoint.md` §2.2/§6.3；`docs/p0-decision-checkpoint.md` §2.1 |
| 13 | **reranker 模型** | ✅ **已选用 & 锁定（2026-09-29）**：**本地 ModelScope `BAAI--bge-reranker-v2-m3`**（`D:\modelscope\hub\models\BAAI--bge-reranker-v2-m3\snapshots\master`，XLMRoberta re-ranker，hidden 1024，≈2.1GB safetensors），已移入 §二.2.2.2 | ✅ 已锁定（用户选定本地模型） | `docs/prj-ledger-version-lock.md` §二.2.2.2；`reports/p0-report-v4b-resources.md` §6.3；`reports/p0-report-v2-hybrid-retrieval.md` §1.2 |
| 14 | **Sparkplug B 模拟器**（V3 输入） | ✅ **已实现（2026-09-24）**：自建 `scripts/spb_simulator.py`（带 `--selftest` / `--scenario birth,new_metric,rebirth,offline,ndeath`），四类边界实测通过 | 本脚本无独立 digest，锁定其依赖（§二.2.7，与解码器共用 `.proto`/`paho-mqtt`） | `docs/prj-ledger-version-lock.md` §二；`docs/p0-design-sparkplug-decoder.md` §八；`reports/p0-report-v3-ingest-license.md` §6.2 |
| 15a | **P1 A2 模拟数据生成器** | ✅ **已实现（2026-10-08）**：`scripts/gen_sparkplug.py`（批量造数：NBIRTH/NDATA/NDEATH + DBIRTH/DDATA，特征频率注入 + 异常段线性爬升，固定 seed，`--selftest` 通过，端到端落库 324 点验证） | 无独立 digest，依赖同 §二.2.7（`.proto`/`paho-mqtt`/`taospy`）；配置 Arc：`configs/decoder_schema_mapping.json`（镜像 `schema-mapping.md`） | `reports/p1-d2-a2-telemetry-2026-10-08.md`；`configs/tdengine/schema_master.sql` |
| 15 | **应用后端 / 前端运行时** | ⚠️ **部分处置（2026-09-29）**：后端 Python 依赖锁文件 `requirements.txt` **已落盘**（摘要 §二.2.7/2.8/2.9，逐版本锁定）；**前端 Node 依赖锁文件不适用（Phase 0 无前端工程/无 `package.json`/`node_modules`，前端未开发）**，首版前端锁延至 P1 前端落地时再补。工具链 Python 3.12.8 / Node v24.19.0 已锁定见 §二 | 后端 ✅（已落盘）；前端 ⏳ P1 前端落地时补 | `docs/prj-ledger-version-lock.md` §二；`docs/p0-handover-p1.md` |
| 16 | **自研解码器 Dockerfile 基础镜像**（`Dockerfile.decoder` `FROM python:3.12-slim`） | ✅ **弃用，无需锚定 digest（2026-09-29，方案 A）**：解码器改由**本地 /venv python 直跑**（不再构建/运行该镜像），base 镜像 digest 锁定项随弃用消除。`Dockerfile.decoder` 保留（含弃用注释）供审计追溯；若 P1 重新容器化，须先在干净机/网络恢复后 `docker images --digests python` 实测回填再锚定 | ✅ 已消除（弃用） | `docs/prj-ledger-version-lock.md` §二.2.7；`docker/Dockerfile.decoder`；`docker/compose.ingest.yml`（变更记录）；`docs/p0-design-sparkplug-decoder.md` §八 |

> ⚠️ **红线提示**：`docker/compose.base.yml` 的 `tdengine` 已由 `tdengine/tdengine:latest` 整改为精确 digest（**2026-09-28**，`tdengine/tsdb:3.3.8.0@sha256:36e2…56bf`）；`neo4j` 已整改为精确 digest（**2026-09-28**）；**`eclipse-mosquitto:2` 已于 2026-09-28 整改为精确 digest**（`compose.base.yml` + `compose.ingest.yml`）；`compose.base.yml` 全部 8 镜像与 `compose.v2.yml` 各镜像均已锚定精确 digest，**纪律 1（禁止裸 tag）已在本项目全部 compose 编排满足**。新增自研解码器 Python 依赖锁定见 **§二.2.7**。

### 2.7 自研 Sparkplug B 解码器（Python 依赖，方案已定稿）

> **来源**：`docs/p0-design-sparkplug-decoder.md`（M1–M6 模块 + 工期 ≈1.9 人日）；映射配置 `configs/decoder_schema_mapping.json`。
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

> ⚠️ **纪律**：以上 Python 包中，凡 `pip` 实际装到的版本与上表不符，**一律以实装版为准**回填本表并锁，不得沿用表内估算。`paho-mqtt`/`taospy`/`grpcio-tools` 安装后须立即执行 `pip freeze` + 解码器 `--selftest` 复核，再写入 `reports/p0-report-v3-ingest-license.md` 第二段实测。

---

### 2.8 V2 检索方案新增锁定项（2026-09-25 实测）

> 本节登记 V2 混合检索实测的新锁定项，供 `reports/p0-report-v2-hybrid-retrieval.md` 与 P1 建库基线引用。

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

> ⚠️ **对照对标声明（2026-09-28 更新）**：V2 稀疏路线**真 BM25 对标已闭环（EXP-V2-BM25，ngram vs jieba 口径差异已显式声明）**：ParadeDB 真 BM25 sparse `Recall@5`=0.90（vs Milvus 0.92）、hybrid 打平 0.91；结论范围扩展为『两实现 BM25 对比』，tsvector 降级淘汰（`reports/p0-report-v2-hybrid-retrieval.md` §4.3）。

---

### 2.9 V5 LangGraph checkpoint 依赖锁定（2026-09-24 实测）

> **来源**：`reports/p0-report-v5-checkpoint.md`（V5 实测，M0.4）`docs/p0-decision-checkpoint.md`。
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
> ⚠️ **B7 说明（勿误写）**：根因 = **redis-py 连接握手被 redis-stack 服务端关闭**（"Connection closed by server"，`CLIENT SETINFO` / `on_connect_check_health`；`redis-cli` 正常 PONG）。**不是"缺 RediSearch"**。详见 `reports/p0-report-v5-checkpoint.md` §6.2。

---

### 2.10 测试工具链依赖锁定（2026-10-08 补锁）

> **来源**：`reports/p0-audit-doc-sync-2026-10-08.md` §三 G1（缺口登记：`pytest` 既不在 `requirements.txt` 也不在本版本锁，但 README 与迭代纪律把「改代码必跑回归」列为硬要求）。
> **补锁动作**：经用户于 2026-10-08 确认「P1 启动前先收口」，登记至 `requirements.txt`（新增「测试工具链」段）。
> **说明**：`tests/` 回归套件（**176 用例**）唯一第三方依赖即 `pytest`，其余均为标准库与项目内模块。

| # | 组件 | 版本 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `pytest` | **9.1.1** | 宿主 `D:/Python312` 实测 `pytest --version` = 9.1.1（该版本即 `pytest tests/ -q` 得 **176 passed** 的基线）；已同步实装进项目 `.venv` | ✅ 已锁 | 回归测试执行器（`tests/`） |

> ⚠️ **纪律**：`requirements.txt` 与本机实装不一致即视为环境漂移。本次已按纪律同步实装项目 `.venv`（`uv pip install pytest==9.1.1`）并复跑回归核对；版本变更须同步本表并升版 `env/env-baseline-v2.md`（纪律 2）。

---

### 2.11 P1 文档解析依赖锁定（2026-10-08）

> **来源**：P1-D1 B1-Spike。`plan/p1-plan-detailed.md` §四 D1 要求以 MinerU 解析三类样本 PDF（文本型 / 扫描件 / 含表格）。
> **环境裁定（2026-10-08，用户确认）**：MinerU **隔离在独立虚拟环境 `.venv-mineru`**（Python 3.12.8），**不进项目 `.venv`、不入 `requirements.txt`**，避免其重依赖污染主环境。
> **模型落点（2026-10-08，用户确认）**：走 **ModelScope 国内源**，模型下载至 `D:\modelscope\hub\models`（与本项目已选用的 BGE-M3 / bge-reranker-v2-m3 同库）。

| # | 组件 | 版本 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `mineru`（隔离环境 `.venv-mineru`） | **4.0.10** | `mineru --version`；`uv pip install "mineru[core]"`（实装为基包，无 `core` extra 之分） | ✅ 已锁（隔离环境） | B1 文档解析（三类样本 PDF） |
| 2 | `pymupdf`（项目 `.venv`） | **1.28.2** | `uv pip install pymupdf` 后经 `importlib.metadata` 实测 | ✅ 已锁（`requirements.txt`） | 样本 PDF 生成 + MinerU 失败时替代解析 |

> ⚠️ **说明**：MinerU 4.0.10 读取 PDF 走 `pypdfium2`/`pypdf`（**非** PyMuPDF）；PyMuPDF 仅用于本项目自编样本生成与替代解析。模型下载命令为 `mineru-models-download --tier basic --small-backend onnx -s modelscope`（本机 `.venv-mineru` 无 torch → ONNX 后端），模型根目录由环境变量 `MINERU_MODEL_BASE_DIR` 指定为 `D:\modelscope\hub\models`。

---

### 2.12 P1-D3 A3 告警引擎 + Redis 形态变更（2026-10-08）

> **来源**：P1-D3 A3/A4。`plan/p1-plan-detailed.md` §5.3（阈值 >4.5 high / 温度 >85 high / 电流 >额定×1.15 medium；Z-Score 30min 窗 >3 medium 需 ≥7 天基线；去重 key = `dedup:alarm:{device}:{metric}` TTL=5min）。
> **依赖口径**：A3 引擎的 Python 依赖（`redis==6.3.0` / `psycopg==3.3.6` / `PyYAML`）均已在本文件 §二.2.9 锁定，本次不再重复列；下表仅登记**新增的脚本/配置文件组件**与 **Redis 形态变更**。
> **Redis 形态变更（B7 闭环）**：`configs/redis.conf` 由形态 A（`bind 127.0.0.1` + `protected-mode yes`，回环、无鉴权）改为 **形态 B**（`bind 0.0.0.0` + `protected-mode no` + `requirepass auscult-dev-redis`）。根因：Docker 容器内仅绑回环会导致 `docker-proxy` 与同网段容器都连不上（B7），`CONFIG SET` 无法运行时改启动期 `bind` 参数，故改配置并重建容器，客户端带密连接。版本仍为 `redis:8`（digest 见 §二.2.1 第 5 行），未升版。

| # | 组件 | 版本 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `scripts/alarm_engine.py`（A3 告警引擎） | `git` 工作树 | `--selftest` 3 项断言 PASS；端到端产生 1 条 `thr_vib_rms` high 告警（value 4.5936）→ Redis 去重 → PG `alerts` 幂等落盘 | ✅ 已实现 | 阈值 + 滑动窗口 + Z-Score + Redis 去重 + AlarmEvent 落 PG/JSONL |
| 2 | `configs/alarm_rules.yml`（A3 规则） | — | 3 条阈值规则（`thr_vib_rms`/`thr_bearing_temp`/`thr_motor_current`）+ 1 条 Z-Score 规则（`z_span_vib`，enabled=false 待数据） | ✅ 已用 | 阈值/Z-Score 规则与去重 key/TTL 定义 |
| 3 | `configs/redis.conf`（形态变更） | `redis:8` | 形态 A→B + `requirepass`；重建容器后宿主/容器访问正常 | Redis 去重通道（B7 闭环） |

---

### 2.13 P1 B4–B6/D9 图谱与一致性链路（2026-10-08~09 锁版）

> **来源**：`plan/p1-plan-detailed.md` §5.7 B4（三元组）/ §5.8 B5（PG 元数据）/ §5.9 B6（Outbox+对账）/ D9 质量门槛（§七）。
> **依赖口径**：B4–B6 脚本的 Python 依赖（`psycopg==3.3.6` / `pymilvus` / sentence-transformers-BGE-M3 / 云端 `Qwen/Qwen3.8-27B` 约束解码）均已于本文件 §二.2.9 / §二.2.2.1 / `env/cloud.json` 锁定，本次不重复列；下表仅登记**新增的脚本/配置文件/报告产物**与**图谱/一致性链路落点**。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `configs/triple_schema.json`（B4 受控词表） | **v2**（11 关系，去「关联」） | 实体 8 类 / 关系 11；OpenAI strict json_schema + Neo4j 关系 slug 映射 | ✅ 已用 | B4 三元组抽取受控词表与入库映射 |
| 2 | `scripts/extract_triples.py`（B4 抽取） | `git` 工作树 | 抽取 36/36（184 有效/0 无效/0 失败）；支持 `--retry-failed`/`--sample`/`--import-neo4j` | ✅ 已实现 | 抽取→校验→人工复核抽样→Neo4j MERGE 入库（关系多 source 数组） |
| 3 | `scripts/load_meta.py`（B5+B6 outbox 补写） | `git` 工作树 | PG `doc_chunks` + `outbox` 幂等补写（每 chunk milvus/neo4j 各一票据） | ✅ 已实现 | PG 元数据导入 + Outbox 幂等写 |
| 4 | `scripts/outbox_worker.py`（B6 补偿队列） | `git` 工作树 | 消费 pending（milvus 缺→BGE-M3 补齐；neo4j 缺→核查存在性）；兼容 `source_chunk_ids` 数组 + A 类豁免 | ✅ 已实现 | Outbox 消费 + 自愈（10 次退避上限） |
| 5 | `scripts/reconcile.py`（B6 对账） | `git` 工作树 | PG vs Milvus/Neo4j 三侧对账；`--fix`/`--fault-inject --apply`；**B4 补链后对账零差异** | ✅ 已实现 | 一致性对账 + 故障注入闭环 |
| 6 | Neo4j 图谱（落点） | `5-community`（digest 见 §二.2.1 第 8 行） | B4 补链后 **105 节点 / 127 关系**（含 HANDLED_BY 33 / 多 source 归因 31）、约束 `triple_entity_id` | ✅ 已用 | B4 三元组图谱（结构关系 + 处置为 HANDLED_BY） |
| 7 | Milvus `kb_p1_v1`（落点） | `v3.0.0`（digest 见 §二.2.1 第 1 行） | PG=Milvus=36；故障注入→自愈闭环归零 | ✅ 已用 | 稠密检索索引 |
| 8 | `reports/p1-d9-gate-judgment.md`（D9 判定） | 2026-10-08~09 | 八项门禁 **全部达标**（三元组准确率 **93% ≥85%**）→ **M1.4 放行**；图谱「仅作线索」限制解除；「处置为」错配 7 条留痕 | ✅ 已定稿 | D9 质量门槛判定 + 图谱用途注册 |
| 9 | `experiments/p1/b4/manual_review_100_v2.jsonl`（准确率人工复核样本） | 固定 seed 抽样 | **93 通过 / 7 未通过**（错配全落「处置为」） | ✅ 已达成 | 三元组准确率 ≥85% 门禁证据 |

> ⚠️ **图谱口径局限**：B4 v2「处置为」56 条跨问题错配全集保留于 `extract_results_v2.jsonl`，图内 `HANDLED_BY` 33 条由 B6 补链入库；凡以「处置为」指引结论的链路**结合原文二次确认、不作主证据**（见 `reports/p1-d9-gate-judgment.md` §2.2）。

---

### 2.14 Phase 2 W1 查询改写器（2026-10-09 锁版）

> **来源**：`plan/Phase 2 详细开发计划（混合检索）.md` §W1（P2-D1）。
> **依赖口径**：`jieba==0.42.1` 已于 §二.2.8 锁定；LLM 增强路径复用 `scripts/llm_adapter.py` + `env/cloud.json`（云端 `Qwen/Qwen3.8-27B` 约束解码），本次不重复列。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `scripts/query_rewrite.py`（W1 查询改写器） | `git` 工作树 | `--selftest` 0 失败（实体抽取、数值关键词、缓存命中 100%）；规则端到端：三路输出 semantic/keywords/entities + numeric 均正确 | ✅ 已实现 | 自然语言→三路检索输入（Dense/BM25/图谱） |
| 2 | `experiments/p2/w1/cache/`（LLM 改写缓存） | 固定 seed | `cache_key(question, model)` sha256 前 16 位；写读一致、命中 100% | ✅ 已用 | LLM 改写结果去重，避免同一问题重复调用 |

### 2.15 Phase 2 W2 多路召回编排（2026-10-09 锁版）

> **来源**：`plan/Phase 2 详细开发计划（混合检索）.md` §5.2 W2（P2-D2/D3/D8）+ 约束 P2-R4。
> **依赖口径**：`pymilvus==3.0.2` / `jieba==0.42.1` 已于 §二.2.8 锁定；BGE-M3 本地向量复用 `run_v2.EmbeddingClient`（§二.2.2.1）；Neo4j 受控关系词表复用 `configs/triple_schema.json`（§二.2.13）。本次不重复列。
> **拓扑实测**：Milvus 端点 **19531**（v2 栈 `auscult-v2-milvus`，`kb_p1_v1`），Neo4j 7474（105 节点）。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `configs/retrieval.yml`（W2 参数集中） | `git` 工作树 | dense top_k=20/HNSW{M 16,efConstruction 200,ef 64}/COSINE/dim 1024；sparse top_k=20/bm25_k1 1.2/bm25_b 0.75/jieba；graph top_k_paths 5/max_hops 2 | ✅ 已用 | 三路召回参数集中配置（D11 调参） |
| 2 | `scripts/retrieval_base.py`（共享基座） | `git` 工作树 | 迷你 YAML 解析（缩进栈+剥注释+数值优先）；`MILVUS_URI=http://127.0.0.1:19531`；统一契约 `extract_route_inputs`/`make_hit`/Neo4j HTTP 事务 | ✅ 已用 | 三路召回统一契约与工具函数 |
| 3 | `scripts/retrieve_dense.py`（稠密召回） | `git` 工作树 | `--selftest` 0 失败；真实召回 20 命中/约 5ms，BGE-M3 编码 + HNSW COSINE top_k=20 | ✅ 已用 | Dense 召回（`semantic` 原文） |
| 4 | `scripts/retrieve_sparse.py`（稀疏召回） | `git` 工作树 | `--selftest` 0 失败；服务端 BM25（jieba）真实 20 命中/约 278ms，传原文本（R-V2-2） | ✅ 已用 | BM25 稀疏召回（`keywords` 原文） |
| 5 | `scripts/retrieve_graph.py`（图谱召回） | `git` 工作树 | `--selftest` 0 失败（Neo4j 105 节点在线）；≤2 跳路径、受控关系 `source_chunk_ids` 展开，真实 5 路径/约 82ms | ✅ 已用 | 图谱证据通道（独立，不进 RRF） |
| 6 | `scripts/retrieval.py`（并行编排） | `git` 工作树 | 端到端真实查询 Dense+Sparse+Graph 三路命中、`degraded_routes=[]`；Dense/Sparse `ThreadPoolExecutor` 并发，Graph 独立 | ✅ 已实现 | W2 编排入口，产 `candidates` 供 W3 RRF |

> **修复留痕**：Milvus 搜索 `distance` 为保留字段，不可列入 `output_fields`（报表 "field distance not exist"，三处已改）；Graph Cypher 改用 `WITH r WHERE` 规避 UNWIND+WHERE 歧义；Graph 结果 `data` 空列表越界已兜底。

### 2.16 Phase 2 W3 RRF 融合（2026-10-09 锁版）

> **来源**：`plan/Phase 2 详细开发计划（混合检索）.md` §5.3 W3（P2-D4）；RRF_K=60 与 V2 基准一致。
> **依赖口径**：纯标准库，复用 `retrieval_base.load_retrieval_config`（§二.2.15）；图谱证据通道**不参与融合**（P2-R4），仅消费 W2 `candidates`（dense+sparse）。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `configs/retrieval.yml::rrf` 段 | `git` 工作树 | k=60 / top_k=5 / weights{dense 0.6, sparse 0.4} | ✅ 已用 | RRF 融合参数集中（D11 调参） |
| 2 | `scripts/fuse_rrf.py`（加权 RRF 融合） | `git` 工作树 | `--selftest` 0 失败（加权累加、双路贡献留痕、配置驱动）；真实融合 top5 `criteria_2-1-c0` 居首（sparse rank1+dense rank5） | ✅ 已实现 | W2 `candidates` → `scored[top_k]` 供 W4 |

### 2.17 Phase 2 W4 重排 + W5 证据组装（2026-10-09 锁版）

> **来源**：`plan/Phase 2 详细开发计划（混合检索）.md` §5.4（W4）/ §5.5（W5）。
> **依赖口径**：**BGE-reranker-v2-m3 本地模型实测（闭环 P1 待办「probe_reranker 实测」）**——CPU 加载 4.57s、参数量≈567.8M（≈2.27GB）、编码 ≈54ms/对@batch16，探针留痕 `experiments/p2/w4/probe_reranker.json`。旧 `reports/project-summary-2026-09-29.md` §5.2/S8「延迟/显存驻留待实测」已据此转为已实测。重排**默认 CPU**（避免与常驻 7B 争 GPU，plan §5.4/R10 错峰）。
> **父块回填数据源**：`chunks/parents_v1.jsonl`（**新增**，由 `chunk_docs.chunk_one` 从 `parsed/*.md` 生成，58 父块，与 `_chunk_summary.json` `parent_total=58` 一致）；子块 `chunks_v1.jsonl` 提供 parent_id/page/section/doc。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `scripts/probe_reranker.py`（探针） | `git` 工作树 | CPU 加载 4.57s、567.8M 参数、54ms/对@batch16；落 `experiments/p2/w4/probe_reranker.json` | ✅ 已用 | W4 接入前置实测（加载/延迟/驻留） |
| 2 | `scripts/rerank.py`（重排） | `git` 工作树 | `--selftest` 0 失败；端到端 Top5 重排 degraded=false，`manual_*` 运行章节升至前列、`criteria` 判据表降尾（语义相关度合理） | ✅ 已实现 | 对 RRF `scored` 用 bge-reranker-v2-m3 复排 → Top5 |
| 3 | `scripts/assemble_evidence.py`（证据组装） | `git` 工作树 | `--selftest` 0 失败；端到端父块回填生效、graph_hint 标注、graph_support=1.0（文档↔图谱一致）、degraded=false | ✅ 已实现 | 父块回填 + 冲突裁定 + EvidenceItem 组装 |
| 4 | `chunks/parents_v1.jsonl`（父块映射） | 生成产物 | 58 行，与 `_chunk_summary.json` parent_total=58 一致 | ✅ 已用 | 供 W5 父块回填上下文 |

> **延迟留痕**：CPU 重排 Top5 ≈1.1s，叠加召回 ≈300ms 后对本路 `P95<800ms` 预算构成风险；plan §5.4 已注明「CPU 重排延迟上升，记录代价」。归 W6 集成 + 待 GPU（cuda:0）重测，不做 W4 阻塞。

### 2.18 Phase 2 W6 `retrieve_knowledge` 工具（2026-10-09 锁版）

> **来源**：`plan/Phase 2 详细开发计划（混合检索）.md` §5.6 W6（P2-D9/D11）。
> **依赖口径**：级联复用 W1–W5（§二.2.14/2.15/2.16/2.17）；BGE-M3 EmbeddingClient 与 reranker 均常驻单例；**不修改** `schemas/tools_v1.json`（恰 5 工具、V1 链路与 llm_adapter self-test 依赖），以 `with_tools()` 附加式注册。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `scripts/retrieve_knowledge.py::RetrievalService` | `git` 工作树 | 常驻单例（EmbeddingClient+CrossEncoder 仅加载一次）；级联 W1→W5；`--selftest` 0 失败 | ✅ 已实现 | 混检工具封装，供 R-2/R-3 工具链消费 |
| 2 | `to_openai_tool()` / `with_tools()` | `git` 工作树 | 附加式注册、去重正确；工具名为 `retrieve_knowledge`（read_only） | ✅ 已实现 | 程序化工具注册（禁手抄） |
| 3 | `--repeat` 延迟剖面（冷/热） | 实测 | 冷 15.2s（模型加载）；**热** recall 36-46ms、rerank ≈1.2s、warm_avg_total ≈1.26s | ✅ 已用 | 常驻收益 + P95 差距量化 |
| 4 | `--retrieve_dense/retrieval` embedder 注入 | 代码改动 | `retrieve_dense(retrieve_all(embedder=None))`、`rerank(model=None)` 可注入常驻实例 | ✅ 已用 | 进程内复用模型，消除每调用重载 |

> **延迟结论（实测）**：热路径 recall 已从冷 9.7s → **36-46ms**（常驻生效）；但 CPU 重排 5 对仍 **≈1.2s**，使热总延迟 ~1.26s **未达 `P95<800ms`**。与 plan §5.4「CPU 重排延迟上升记录代价」一致，记 **P2 待 D11**：GPU(cuda:0) 重排 或 降低候选量（不做 W6 功能阻塞）。

### 2.19 Phase 2 W7 `retrieve_knowledge` 工具链接入 R-2/R-3（2026-10-09 锁版）

> **来源**：`plan/Phase 2 详细开发计划（混合检索）.md` §三 WBS W6 + `docs/p0-spec-gate-criteria.md` §3.1.1（R-2/R-3 工具调用判据）。
> **依赖口径**：复用 §二.2.18（W6 级联链路）与 `llm_adapter` + `env/cloud.json`（云端 `Qwen/Qwen3.8-27B` 约束解码）；**判据复用** `judge_tools.judge_record` / `judge_verdict_tiered`（§二.2.3 工具链既有设施）。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `schemas/tools_p2_retrieve.json` | v1 | 单工具 `retrieve_knowledge`，与 `RETRIEVE_KNOWLEDGE_TOOL` 逐字一致（禁手抄） | ✅ 已用 | W7 评测注入 schema（隔离于 V1 5 工具基线） |
| 2 | `evals/v2_retrieve_cases.jsonl` | v1 | 16 条纯检索用例，镜像 V1 case 字段，预期工具 `retrieve_knowledge` | ✅ 已用 | W7 云端评测用例集 |
| 3 | `scripts/run_v2_tools.py` | `git` 工作树 | 镜像 run_v1 流程（`load_tool_schemas` + `judge_record` + `judge_verdict_tiered`）；`TOOLS_P2_PATH` 指向 §二.2.19 第 1 行 | ✅ 已用 | W7 全量评测入口 |
| 4 | `judge_tools` 语义匹配扩充 | 代码改动 | `compare_arguments` 对 `("retrieve_knowledge","question")` 复用 `_query_semantic_match`（关键概念命中+bigram 交叠），对齐 V1 R-2/R-3 语义口径 | ✅ 已用 | 消除逐字比较导致的假 FAIL_PARAM_VALUE |
| 5 | 云端全量 16 条 | Qwen/Qwen3.8-27B | **16/16 judged_success（单工具 100%）**，`judge_verdict_tiered` 整体 Pass（≥85% 线） | ✅ Pass | R-2/R-3 工具链 ≥85% 判据证明 |
| 6 | 资产还原留痕 | git | `tools_v2.json` 还原 V1 5 工具基线（无 M 行）、`judge_v1.json` 已删、`SCHEMA_PATH` 默认回 `tools_v2.json`、`TOOLS_V2_PATH→TOOLS_P2_PATH` | ✅ 干净 | 越权覆盖既有受控资产的纠正记录 |

> **判据修复经过**：初版 2 条冒烟工具名全对但 FAIL_PARAM_VALUE——定位为判据缺口（judge 仅对 `search_knowledge.query` 语义匹配），非模型能力。经用户批准方案 1，复用在 `judge_tools.py` §约 L462-467 实现；全量重跑 16/16 Pass。
> **越权记录（审计留痕）**：子代理在实现中曾覆盖既有受控资产 `schemas/tools_v2.json`（V1 5 工具基线，即 judge 原默认）并二次越权新建 `judge_v1.json`。已纠正：`git checkout` 还原、删除 `judge_v1.json`、Phase 2 schema 隔离至新文件 `tools_p2_retrieve.json`。
> **RAW 落盘**：`experiments/p2/w7/RAW-v2-tools.jsonl` + `.meta.json`。

### 2.20 M2.3 配套评测集指标（2026-10-09 锁版）

> **来源**：`docs/p0-spec-gate-criteria.md` §1.2（`Recall@5 ≥85%`、`MRR ≥0.75`、`NDCG@5` 报告值、P95<800ms）。
> **前置发现**：50 条 `golden_set_v1` 引用 7 类逻辑文档（doc-pump-manual / doc-vibration-std ...），与真实建库语料（19 文档 36 子块 3147 token 的 P1 合成样本）**内容覆盖度严重脱节**（ISO 标准/轴承 BPFO/Sparkplug B/安全规范等均无色对应）。经用户批准改走**配套评测集** `evals/m2_acc_set.jsonl`（12 题锚定真实语料可覆盖主题，相关块用真实 chunk_id）。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `evals/m2_acc_set.jsonl` | v1 | 12 题，覆盖判据/手册/故障案例/拓扑，真实 chunk_id 相关标注 | ✅ 已用 | M2.3 配套检索评测集 |
| 2 | `scripts/eval_m2.py` | v1 | 复用 `RetrievalService`；`Recall@5/MRR/NDCG@5/P95` + RAW 落盘 | ✅ 已用 | 检索质量指标脚本 |
| 3 | 检索质量指标 | v1 口径 | **Recall@5=1.0**、**MRR=0.7153**、**NDCG@5=1.0**（12/12 全部命中相关块） | ✅ 见下裁定 | Recall/NDCG 达标；MRR 0.715<0.75 |
| 4 | 端到端延迟（CPU 基线） | P95 | **P95=7037ms / P50=2109ms**（CPU rerank ≈1.2s/题 主因） | ⚠️ 原超线 | D11 前基线（已作废） |
| 5 | 端到端延迟（GPU 重排） | P95 | **P95=353.2ms / P50=133.1ms**（RTX 4060 Laptop GPU + BGE-reranker-v2-m3） | ✅ 达标 | D11 GPU 重排闭合 |
| 6 | 端到端延迟（RRF-only） | P95 | **P95=86.1ms / P50=45.6ms**（跳过 rerank，纯 RRF 排序） | ✅ 达标 | D7 消融最优配置 |
| 7 | D7 消融结论 | 消融 | rerank ΔMRR=**-0.0417**（净负效果）；RRF-only **MRR=0.7569≥0.75 达标** | ✅ 达标 | **默认走 RRF-only**，rerank 保留为可选增强 |

> **裁定口径（D7 消融后最终更新）**：`Recall@5` **达标**（1.0 ≥0.85）；`NDCG@5` **报告值 1.0**；`MRR=0.7569` **达标（≥0.75）**——D7 消融确认当前小语料下 rerank 净负效果（ΔMRR=-0.0417），改走 RRF-only 后 MRR 从 0.7153→0.7569 过线；`P95=86.1ms` **达标（<800ms）**——RRF-only 比 GPU rerank（353ms）再降 76%。
> **D7 消融详情**：`scripts/d7_ablation.py` 逐题对比 RRF-only vs rerank：rerank 在 2 题帮助（m2a-005/012）、2 题伤害（m2a-003/007），净 ΔMRR=-0.0417。根因：当前语料极小（36 子块），RRF 双路信号已足够排序，rerank 引入噪声。`RetrievalService` 新增 `use_rerank` 开关（默认 True），`eval_m2.py` 新增 `--no-rerank` 选项。
> **D11 处置**：本机 `D:\py312-torch`（venv, CUDA torch 2.14.0+cu130, RTX 4060 Laptop GPU）补装依赖后 GPU 重排 P95 7037→353ms（降幅 95%）；D7 后改走 RRF-only 进一步降至 86ms。GPU 环境保留供后续语料扩大后 rerank 重评。
> **黄金集约束**：本 M2.3 指标基于**配套评测集**（非 50 条 `golden_set_v1`），因 golden 与真实语料内容脱节不可直接评测；50 题待语料扩充后重评。勿将本轮 12 题指标与 golden 50 题口径混淆。
> **RAW 落盘**：`experiments/p2/m2/RAW-m2-metrics.jsonl` + `meta-m2.json`（含 `device: cuda, use_rerank: false`）；`experiments/p2/d7/ablation-d7.jsonl` + `summary-d7.json`。

### 2.21 Phase 2 收尾（M2.4 达成 · handover-p3）（2026-10-09 锁版）

> **来源**：`plan/Phase 2 详细开发计划（混合检索）.md` §六（里程碑 M2.4）+ §七（验收标准）。
> **判定**：M2.4 三项通过条件全部达成（P95=86.1ms<800ms、retrieve_knowledge 可用、移交 P3）；M2.1–M2.4 四项里程碑全部达成。

| # | 组件 | 版本/口径 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `docs/p2-handover-p3.md` | v1 | 移交清单（资产/优先级/遗留/里程碑判定） | ✅ 定稿 | Phase 2→3 唯一移交凭据 |
| 2 | `reports/p2-summary.md` | v1 | Phase 2 总结报告（里程碑/决策/遗留） | ✅ 定稿 | Phase 2 收口报告 |
| 3 | M2.4 判定 | — | P95=86.1ms ✅ / 工具可用 ✅ / 移交 ✅ | ✅ 达成 | Phase 2 四项里程碑全达成 |

> **遗留转 P3**：golden 50 题评测（扩语料后）、Redis 缓存、引用正确率抽检、rerank 重评、消融报告正式版。
> **约束（不变）**：M2.3/M2.4 指标基于 12 题配套集（非 golden 50 题），golden 待扩语料后重评。

### 2.22 Phase 4 后端 API 依赖（2026-10-09 D0-1 锁版）

> **来源**：`plan/Phase 4 详细开发计划（前端与集成）.md` §三（技术栈）；用户裁定 Q1/Q2（P4 含后端 API，前置 D0 增量承载）。
> **实测口径**：`uv pip install -p .venv` 实装；安装时 anyio 4.15.1→4.14.2（starlette 1.7.0 约束传导），已验证 `app.graph.build` / `app.graph.checkpointer` 导入无损 + D0-1 自测 17/17 PASS。前端（Node/npm/Next 等）待 D1 初始化后另记前端段。

| # | 组件 | 版本 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `fastapi` | **0.143.0** | 实装 + `app/api/main.py` TestClient 自测 17/17 | ✅ 已锁 | P4 REST API 骨架（§5.5 九契约 + 契约补丁） |
| 2 | `starlette` | **1.7.0** | 随 fastapi 0.143.0 实装 | ✅ 已锁 | ASGI 框架底层（fastapi 传递依赖） |
| 3 | `uvicorn` | **0.54.0** | 实装 | ✅ 已锁 | ASGI 服务器（8000 端口） |
| 4 | `PyJWT` | **2.15.1** | 实装；HS256 签发/校验 R11–R15 通过 | ✅ 已锁 | 登录态 JWT（`app/api/security.py`） |
| 5 | `bcrypt` | **5.0.0** | 实装；密码哈希 + 种子 4 账号写入 | ✅ 已锁 | `users.password_hash`（rounds=12，72 字节上限） |
| 6 | `httpx` | **0.28.1** | 预装复用（fastapi TestClient 传输层） | ✅ 已锁 | `scripts/test_p4_d0x_*.py` 自测 |
| 7 | `anyio` | **4.14.2** | 随 starlette 约束自 4.15.1 降级；Agent 链路回归导入无损 | ✅ 已锁 | 异步底层（传递依赖，降级留痕） |
| 8 | `db/migrations/0004_users.sql` | git 工作树 | 幂等应用成功（users 表 + RBAC 四角色 CHECK） | ✅ 已用 | 用户与 RBAC 表结构（D0-1） |
| 9 | `scripts/seed_users.py` | git 工作树 | 幂等写入 4 账号（eng_dev/rev_dev/kb_dev/sys_dev） | ✅ 已用 | RBAC 种子账号（bcrypt 应用层生成，不依赖 pgcrypto） |
| 10 | `python-socketio` | **5.17.0** | 实装 + D0-4 自测 12/12 PASS（鉴权连接/chat:ask/alarm:new/事件桥接） | ✅ 已锁 | Socket.IO 服务端（D0-4，`app/api/socket.py`） |
| 11 | `python-engineio` | **4.14.0** | 随 python-socketio 5.17.0 实装 | ✅ 已锁 | Engine.IO 底层（传递依赖） |
| 12 | `simple-websocket` | **1.1.0** | 实装 + D0-4 子进程服务 WS 通道验证 | ✅ 已锁 | ASGI WebSocket 传输（D0-4，含 wsproto 1.3.2） |
| 13 | `app/api/routes/review.py` + `app/api/runner.py`（submit_review/lifecycle watcher） | git 工作树 | D0-5 自测 22/22 PASS（SoD/锁/4h 通知/24h 超时/trace+metrics 接入）；D0-1/D0-3 回归通过 | ✅ 已用 | 审核 REST 主通道 + 报告别名 + pending 队列（D0-5） |
| 14 | `db/migrations/0005_knowledge_admission.sql` | git 工作树 | 幂等应用成功（documents.admission_* 三列 + 部分索引）；D0-6 自测 14/14 PASS；D0-2 回归 22/22 | ✅ 已用 | 知识准入审核（D0-6 契约补丁，R-M3 防投毒） |

> ⚠️ **安全留痕**：开发默认 `JWT_SECRET` 仅限本机（启动时打警告）；生产/外部环境必须环境变量注入并换密。默认种子密码 `Auscult#Dev2026` 同理。Socket.IO 跨域 `SOCKETIO_ORIGINS` 开发默认 `*`，生产必须白名单。

### 2.23 Phase 4 前端工程（2026-10-09 D1 初始化锁版）

> **来源**：`plan/Phase 4 详细开发计划（前端与集成）.md` §三；`plan/工业设备诊断 Agent - 前端 UI 方案（V1.0）.md` §10。
> **实测口径**：`create-next-app@latest`（pnpm）+ `pnpm dlx shadcn@latest init -b radix -p nova` 实装；D1 build 通过 + 浏览器走查，D2–D5 单测 30/30 PASS。`pnpm list --depth=0` 实测版本如下。

| # | 组件 | 版本 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `next` | **16.4.0** | 实装 + next build 通过（Turbopack/cacheComponents） | ✅ 已锁 | App Router 前端框架（client/） |
| 2 | `react` / `react-dom` | **19.3.0** | 随 create-next-app 实装 | ✅ 已锁 | UI 运行时 |
| 3 | `tailwindcss` | **4.3.3**（+ `@tailwindcss/turbopack`） | 实装 + tokens 语义槽位映射 | ✅ 已锁 | 样式（L0 尺度/L1 语义槽位三层） |
| 4 | `radix-ui` | **1.7.0**（单包） | shadcn init `-b radix` 实装 | ✅ 已锁 | 无障碍交互原语（Dialog/DropdownMenu/Select 等） |
| 5 | `shadcn`（CLI） | **4.21.4**（预设 nova） | init + 17 组件生成 | ✅ 已锁 | 组件生成器（产物入 git，CLI 仅开发期） |
| 6 | `cn` | **0.4.0** | shadcn v4 默认 clsx+tailwind-merge 包装 | ✅ 已锁 | 类名合并 |
| 7 | `lucide-react` | **1.53.0** | 实装 | ✅ 已锁 | 图标 |
| 8 | `next-themes` | **0.4.6** | 实装 | ✅ 已锁 | 换肤（data-theme 切换） |
| 9 | `@tanstack/react-query` | **5.104.1** | 实装 + useAlarms/alarm:new 定向插入 | ✅ 已锁 | 服务端状态（D4/D5） |
| 10 | `socket.io-client` | **4.8.4** | 实装 + getSocket 单例（对齐后端 5.17.0） | ✅ 已锁 | 实时层（D5） |
| 11 | `zustand` | **5.0.15**（+ persist） | 实装 + useAuth/useConn/useInspector | ✅ 已锁 | 客户端状态（会话/连接/检查器） |
| 12 | `sonner` | **2.0.8** | 实装 + review:required toast | ✅ 已锁 | 低打扰通知 |
| 13 | `vitest` + `jsdom` | **5.0.3** + **30.1.2** | 实装 + 30/30 PASS（api/auth/alarms-realtime） | ✅ 已锁 | 单元测试 |
| 14 | `@playwright/test` | **1.64.0** | 实装（chromium 下载中，D20 e2e 用） | ✅ 已锁 | E2E 测试 |
| 15 | `typescript` | **5.9.3** | 实装 + next build TS 检查通过 | ✅ 已锁 | 类型检查 |
| 16 | Node.js / pnpm | **v24.19.0 / 11.7.0** | 环境实测 | ✅ 已锁 | 前端运行时与包管理 |

---

### 2.24 环境实装漂移补声明（P5 工具链 / 向量化 / 评测，2026-10-10 补锁）

> **来源**：P5 收尾方案 A 的漂移核查（2026-10-10）。核查口径：全仓 `*.py` 的 `import` 语句 × `.venv` 实装（`uv pip list`）逐条比对 `requirements.txt`。
> **缺口**：下列 5 项**已被代码直接 import、且已实装于 `.venv`，但未在 `requirements.txt` 声明** → 违背该文件「本文件与本机实装不一致即视为环境漂移」纪律。
> **处置（2026-10-10，用户批准）**：补齐 `requirements.txt` 声明（新增「环境实装漂移补声明」段，全部 `==` 精确锁定）并登记本表；`.venv` 实装**未变动**（无升级/降级），回归测试 **183 passed** 复核通过。
> **不升版 `env-baseline-v2.md`**：本次仅补 Python 包声明，未触及该文件 §引用纪律 的 5 条升版触发条件（镜像/模型 digest、Ollama·Docker·WSL2 版本、`.wslconfig`、硬件）。

| # | 组件 | 版本 | 实测依据 | 采用状态 | 用途 |
|---|---|---|---|---|---|
| 1 | `sentence-transformers` | **6.1.0** | `.venv` 实装（`uv pip list` 实测）；`SentenceTransformer` 加载 BGE-M3（§二.2.2.1）、`CrossEncoder` 加载 bge-reranker-v2-m3（§二.2.2.2） | ✅ 已锁 | V2 向量化与重排运行时（`scripts/run_v2.py`、`rerank.py`、`retrieve_knowledge.py`、`probe_reranker.py`） |
| 2 | `ragas` | **0.4.3** | `.venv` 实装 | ✅ 已锁 | P5 W1 评测（`scripts/eval_ragas.py`） |
| 3 | `locust` | **2.46.7** | `.venv` 实装 | ✅ 已锁 | P5 D14 压测（`scripts/locustfile.py`；`reports/p5-perf.md`） |
| 4 | `prometheus-client` | **0.26.0** | `.venv` 实装 | ✅ 已锁 | P5 W2 可观测（`app/observability/prom_metrics.py`、`scripts/test_p5_d06_metrics.py`） |
| 5 | `numpy` | **2.5.3** | `.venv` 实装 | ✅ 已锁 | 向量归一化 / 建库（`scripts/build_milvus_v1.py`） |

> **传递依赖（实装实测，仅留痕、不单独 pin）**：`torch` **2.14.0**、`transformers` **5.17.0**、`datasets` **5.1.0**、`langchain` **1.4.4**、`pandas` **3.0.6**、`scipy` **1.18.1**，由上述直接依赖解析带入。其中 `scripts/probe_reranker.py` 为**统计参数量**而 `import torch`（失败即跳过、不参与判据）——该包属 `sentence-transformers` 传递依赖，故不单列。
> ⛔ **`uv pip sync` 提示（2026-10-10 实测）**：`uv pip sync` **不解析传递依赖**（官方口径：输入文件须为 `pip compile` / `uv export` 的产物）→ **禁止**对本文件直接 sync（`--dry-run` 计划移除 **136 包**）。安全用法：先 `uv pip compile requirements.txt -o requirements.lock.txt`，再 sync 该产物；P6 D6/D7 出 `uv.lock`（方案 C）后转确定性口径。
> 🔴 **【待裁决】残留 3 处版本级漂移（2026-10-10 实测发现，本次未擅自处置）**：`uv pip install -r requirements.txt --dry-run` 与 `.venv` 实装的差异为 `langchain`（实装 **1.4.4** / 解析 **1.4.3**，且未在本文件声明）、`langchain-core`（实装 **1.6.9** / 本文件声明 **1.6.4**）、`langchain-openai`（实装 **1.7.0** / 解析 **1.6.6**，且未在本文件声明）。
> **根因（dist-info 时间戳实测）**：`langchain*` 全链于 **2026-10-09 22:43–22:50** 批量安装，与 `ragas` 0.4.3 / `locust` 2.46.7 / `prometheus-client` 0.26.0 同批 → 即 **P5 W1 评测引入 `ragas` 时，其 langchain 生态依赖把 `langchain-core` 由 1.6.4 升至 1.6.9**（同批新增 `langchain` / `langchain-openai` / `langchain-community` 0.4.2 / `langchain-classic` 1.0.8 / `langchain-ollama` 1.1.0 / `langchain-huggingface` 1.2.3 / `langchain-text-splitters` 1.1.3），但**未同步回本文件与 §二.2.9**。
> **处置选项（待用户裁决）**：① **以实装为真** —— 将本文件与 §二.2.9 的 `langchain-core` 更新为 **1.6.9**，并补登记 `langchain` / `langchain-openai`（需按纪律 2 评估是否升版 `env-baseline-v2.md`）**（推荐）**；② 将 `.venv` 降回 `langchain-core==1.6.4` / `langchain==1.4.3` 并复跑回归；③ 暂不处置、仅登记。
> ⚠️ **影响面提示**：`langchain-core` 是 **V5 LangGraph checkpoint 的直接依赖**（§二.2.9）→ 若采选项 ①/②，须按 §3.1.3 同口径复跑 `scripts/run_v5.py` 与回归套件，确认 V5 结论不受影响后再动 `env-baseline-v2.md` 升版判定。

---

## 四、与各报告的交叉引用

> **引用方式统一为**：报告在首部声明环境基线版本号，并在正文引用本文件的**具体小节**；凡本文件为「待锁定」的条目，报告中一律写 `【待 D<天> 实测填入】`，不得填估算值。

| 报告 / 文档 | 引用方式 | 具体引用位置 |
|---|---|---|
| `reports/p0-report-v1-tool-call.md` | 引用 §二.2.1（模型 digest）、§二.2.3（工具链）、§二.2.5（实验固定参数）、§三 第 10–11 行（云端 baseline 模型、Ollama 升版决策） | §2.1 模型版本与 digest；§2.3 待登记项；§八 R-V1-6 |
| `reports/p0-report-v2-hybrid-retrieval.md` | 引用 §二.2.1（Milvus / etcd / MinIO / postgres digest）、§三 第 3–6 行（BGE-M3、pgvector、ParadeDB） | §2.1 已实测事实；§2.3 待登记项；§三.3.1「写入 `docs/prj-ledger-version-lock.md`」 |
| `reports/p0-report-v3-ingest-license.md` | 引用 §三 第 1–2、8、9、14 行（TDengine、taosX、Mosquitto、EMQX、模拟器） | §一「结论写入 `docs/prj-ledger-version-lock.md`」；§5.2；§十一 Compose 片段注 |
| `reports/p0-report-v4b-resources.md` | 引用 §二.2.4（硬件与 WSL 配额）、§二.2.1（镜像 digest 基线）、§三 第 3、7、13 行 | §3.6 待登记的组件规模；§7.3 前置阻塞项；§十三 复现命令（`docker images --digests`） |
| `reports/daily/D1-status.md` | 引用 §二.2.3（Ollama 0.34.2 / 0.34.3）、§二.2.1（Milvus digest）、§二.2.2（模型 digest） | §3.6 工具链版本；§四 D1-P4；§五 待办第 6 条 |
| `docs/p0-decision-model-role.md` | 引用 §二.2.2（两个本地模型 digest 与量化档）、§三 第 10、11 行 | §2.2 候选模型；§5.3 风险三；§六.3 复核记录；§八 下游依赖 |
| `docs/p0-decision-checkpoint.md` | 引用 §二.2.1（`redis:8` digest）、§二.2.9（LangGraph / PG checkpointer 依赖，V5 采纳） | §五.5.3 降级执行清单第 ⑦ 步「同步更新 docs/prj-ledger-version-lock.md」｜§2.1 采纳结论 |
| `docs/prj-template-experiment-log.md` | **强制**：`image_model_digests` 字段必须与本文件逐字一致；引用本文件 §一 纪律（不一致即结论作废） | §二.2.1 字段纪律；§五「报告引用纪律」第 2 条「见 `docs/prj-ledger-version-lock.md` §纪律」 |
| `docs/prj-ledger-known-issues.md` | 引用 §二.2.1（Redis digest）、§三 第 11、12 行（Ollama、checkpointer 版本） | §二 ISS-005 规避手段①、ISS-009 规避手段③；§四「需换方案」后续动作「更新 `docs/prj-ledger-version-lock.md`」 |
| `docs/prj-spec-review-lifecycle.md` | 引用 §二.2.1（`redis:8` digest） | §八.8.2 降级路径 L2（存储层降级须同步版本） |
| `docker/compose.base.yml` | **反向依赖**：其 Neo4j 段注释「版本待锁定（`prj-ledger-version-lock.md` 中为"待锁定"行）」即指本文件 §三 第 7 行 | `docker/compose.base.yml` 第 148–149 行 |
| `schemas/tools_v1.json` | **反向依赖**：其 `change_policy` 字段要求「同步更新 prj-ledger-version-lock.md」 | `schemas/tools_v1.json` `change_policy`；本文件 §一 纪律 4、§二.2.6 |
| `reports/p1-d5-d7-b4-triples.md` | 引用 §二.2.13（B4 词表 v2 / `extract_triples.py` / Neo4j 图谱落点） | §二.2.13 第 1/2/6 行 |
| `reports/p1-d8-d9-b6-consistency.md` | 引用 §二.2.13（B5/B6 脚本 / Milvus / Neo4j 落点、对账零差异） | §二.2.13 第 3–7 行 |
| `reports/p1-d9-gate-judgment.md` | 引用 §二.2.13（D9 判定报告 / 人工复核样本） | §二.2.13 第 8/9 行 |
| `reports/p2-d1-w1-query-rewrite.md` | 引用 §二.2.14（W1 查询改写器 / LLM 改写缓存） | §二.2.14 第 1/2 行 |
| `reports/p2-d1-w2-recall.md` | 引用 §二.2.15（W2 多路召回编排 + 拓扑 19531） | §二.2.15 第 1–6 行、拓扑实测 |
| `reports/p2-d1-w3-rrf.md` | 引用 §二.2.16（W3 RRF 融合） | §二.2.16 第 1/2 行 |
| `reports/p2-d2-w4-w5-rerank-evidence.md` | 引用 §二.2.17（W4 重排 probe/rerank + W5 证据/父块映射） | §二.2.17 第 1–4 行、延迟留痕 |
| `reports/p2-d3-w6-retrieve-knowledge.md` | 引用 §二.2.18（W6 retrieve_knowledge 工具/热延迟剖面） | §二.2.18 第 1–4 行、延迟结论 |
| `reports/p2-d3-w7-retrieve-tools.md` | 引用 §二.2.19（W7 工具链接入 R-2/R-3 / 语义匹配扩充 / 资产还原留痕） | §二.2.19 第 1–6 行、判据修复与越权记录 |
| `reports/p2-d3-m2-metrics.md` | 引用 §二.2.20（M2.3 配套评测集指标 / D7 消融 / D11 延迟闭合 / 四项达标） | §二.2.20 第 1–7 行、裁定口径 |
| `docs/p2-handover-p3.md` | 引用 §二.2.21（Phase 2 收尾 / M2.4 达成 / 移交 P3） | §二.2.21 第 1–3 行、遗留转 P3 |
| `reports/p2-summary.md` | 引用 §二.2.21（Phase 2 总结报告 / 四项里程碑 / 关键决策 / 遗留） | §二.2.21 第 1–3 行 |
| `requirements.txt` | **反向依赖**：其头部「版本唯一来源」逐条指向 §二.2.7 / §2.8 / §2.9 / §2.10 / §2.24；正文「本文件与本机实装不一致即视为环境漂移」即本文件 §一 纪律 | `requirements.txt` 头部注释；本文件 §一 纪律、§二.2.24 |

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
| ~~【待 D6–D7】~~ → **2026-09-24 完成** | 单人（本人） | **V5 LangGraph checkpoint 依赖锁定（M0.4）**：新增 §二.2.9（langgraph 1.2.12 / checkpoint 4.2.0 / checkpoint-postgres 3.1.2 / checkpoint-redis 0.5.2 / langgraph-sdk 0.4.5 / langchain-core 1.6.4 / redis 6.3.0 / redisvl 0.27.2 / psycopg 3.3.6 / psycopg-pool 3.3.3）；修正 §三 第 12 行为"已锁但未采用（redis-py↔redis-stack B7）"并新增第 12b 行（PG checkpointer 采纳）；§四 更新 p0-decision-checkpoint 交叉引用 | §二.2.9；§三 第 12/12b 行 |
| ~~【待 D8】~~ → **2026-09-29 完成** | 单人（本人） | 锁定 reranker 模型与 digest（§三 第 13 行移入 §二）。**完成注（2026-09-29）**：用户选定**本地** ModelScope `BAAI--bge-reranker-v2-m3`（无需联网），移入 §二.2.2.2 并锁定；§三 第 13 行已改「已选用 & 锁定」 | §二.2.2.2；§三 |
| 2026-09-28 | 单人（本人） | **Neo4j 收尾锁定（b5）**：核对 docker 实测 digest 与 §二.2.1 第 11 行一致（`sha256:ab3aafb…d61`）；§三 第 7 行由「待锁定」改「✅ 已锁定」；`compose.base.yml` neo4j 段补精确 digest（纪律 1）；红线提示同步——仅余 `eclipse-mosquitto:2` 裸 tag 待整改 | §二.2.1、§三 第 7 行、red line；`docker/compose.base.yml` |
| 2026-09-28 | 单人（本人） | **云端 baseline 模型锁定（EXP-V1-002 实测后）**：§三 第 10 行由「待锁定（`<cloud-model>`）」改「✅ 已锁定」——provider `openai` / model `Qwen/Qwen3.8-27B` / modelscope endpoint，上界校准首次成功率 0.60；`env/cloud.json` 置 `is_locked=true`（含 API key，`.gitignore` 忽略） | §三 第 10 行；`env/cloud.json` |
| 2026-09-28 | 单人（本人） | **清理非本项目镜像行（§二.2.1）**：按用户指示移除 `nacos/nacos-server`、`mysql`、`mongodb/mongodb-atlas-local` 三行（原 6–8 行，均为"其他项目在用"），顺延 tdengine/mosquitto/neo4j 为新第 6–8 行；镜像总数由「14 个/约 13.4 GB」更正为本项目 **8 个 / 约 7.8 GB**（表中 8 行求和建议值，非实测）；保留「禁止 prune 非本项目容器」红线并改为引用 R-V3-7 / R-V4b-8 | §二.2.1 表格、镜像总数注释 |
| 2026-09-28 | 单人（本人） | **真 BM25 稀疏对标闭环（EXP-V2-BM25，M0.3 补齐）**：§二.2.8「真 BM25 状态」由"可用"补"对标已闭环"（ParadeDB 真 BM25 sparse `Recall@5`=0.90 vs Milvus 0.92、hybrid 打平 0.91）；对照对标声明更新为"结论范围扩展为两实现 BM25 对比，tsvector 降级淘汰" | §二.2.8；`experiments/v2/raw/EXP-V2-BM25.md` |
| 2026-09-29 | 单人（本人） | **reranker 本地选用 & 锁定（用户选定本地模型）**：§三 第 13 行由「待锁定」改「✅ 已选用 & 锁定」，移入新建 §二.2.2.2；本地 `BAAI--bge-reranker-v2-m3`（`D:\modelscope\hub\models`，XLMRoberta，hidden 1024，≈2.1GB safetensors，纯本地、与 Ollama 无关）；`【待 D8】` 占位行标记完成。**注**：此为模型选用，safetensors 无单一 Docker 级 digest，以「本地路径 + 架构 + 文件大小」作为复现依据 | §二.2.2.2；§三 第 13；§五 |
| 2026-10-08 | 单人（本人） | **P1 启动前补锁测试工具链**：新增 **§二.2.10**（`pytest==9.1.1`，`reports/p0-audit-doc-sync-2026-10-08.md` §三 G1 缺口收口）并同步 `requirements.txt` 新增「测试工具链」段；已实装项目 `.venv` 并复跑回归 **176 passed**（0.66s）验证一致 | 新增 §二.2.10；`requirements.txt`；`README.md` tests 行 |
| 2026-10-08 | 单人（本人） | **P1-D3 A3 告警引擎 + Redis 形态变更**：新增 **§二.2.12**（`scripts/alarm_engine.py` + `configs/alarm_rules.yml` + `configs/redis.conf` 形态 A→B+B7 闭环）；Redis 仍为 `redis:8`（§二.2.1 第 5 行），Python 依赖复用 §二.2.9，未重复列 | 新增 §二.2.12 |
| 2026-10-09 | 单人（本人） | **P1 B4–B6/D9 锁版收尾**：新增 **§二.2.13**（B4 词表 v2 / `extract_triples.py` / `load_meta.py` / `outbox_worker.py` / `reconcile.py` / Neo4j 105 节点·127 关系 / Milvus `kb_p1_v1` / D9 判定报告 93% / 人工复核样本）；§四 交叉引用补 b4/b6/d9 三报告。依赖复用 §二.2.9/§二.2.2.1，未重复列 | 新增 §二.2.13；§四 |
| 2026-10-09 | 单人（本人） | **Phase 2 W1 查询改写器**：新增 **§二.2.14**（`scripts/query_rewrite.py` 规则快路径+可选LLM + `experiments/p2/w1/cache/` 缓存）；jieba 复用 §二.2.8；LLM 复用 `llm_adapter` + `env/cloud.json` | 新增 §二.2.14 |
| 2026-10-09 | 单人（本人） | **Phase 2 W2 多路召回编排**：新增 **§二.2.15**（`configs/retrieval.yml` + `retrieval_base.py` + `retrieve_{dense,sparse,graph}.py` + `retrieval.py`）；启动 v2 栈 Milvus（19531）实召回三路命中、`degraded_routes=[]`；§四 补 w2 交叉引用。依赖复用 §二.2.8/§二.2.2.1；修复留痕见 §二.2.15 | 新增 §二.2.15；§四 |
| 2026-10-09 | 单人（本人） | **Phase 2 W3 RRF 融合**：新增 **§二.2.16**（`configs/retrieval.yml::rrf` 段 + `scripts/fuse_rrf.py`）；k=60/top_k=5/weights{0.6,0.4}；真实融合 top5 正确（图谱不参与，P2-R4）；§四 补 w3 交叉引用 | 新增 §二.2.16；§四 |
| 2026-10-09 | 单人（本人） | **Phase 2 W4 重排 + W5 证据组装**：新增 **§二.2.17**（`probe_reranker.py` 闭环保 + `rerank.py` + `assemble_evidence.py` + `chunks/parents_v1.jsonl`）；probe 实测 CPU 加载 4.57s/≈54ms对；§四 补 w4/w5 交叉引用。旧 project-summary「reranker 延迟/驻留待实测」据此转已实测 | 新增 §二.2.17；§四 |
| 2026-10-09 | 单人（本人） | **Phase 2 W6 `retrieve_knowledge` 工具**：新增 **§二.2.18**（`retrieve_knowledge.py::RetrievalService` 常驻级联 + `to_openai_tool()/with_tools()` 附加注册 + `--repeat` 冷/热延迟剖面）；`retrieve_dense/retrieval/rerank` 增可注入 `embedder/model`；热 recall 96→40ms、热 rerank ≈1.2s 实测；§四 补 w6 交叉引用 | 新增 §二.2.18；§四 |
| 2026-10-09 | 单人（本人） | **Phase 2 W7 `retrieve_knowledge` 工具链接入 R-2/R-3**：新增 **§二.2.19**（`tools_p2_retrieve.json` + `evals/v2_retrieve_cases.jsonl` + `run_v2_tools.py` + `judge_tools` 对 `retrieve_knowledge.question` 复用 `_query_semantic_match`）；云端 Qwen/Qwen3.8-27B 全量 **16/16 Pass（单工具 100% ≥85% 线）**；资产还原留痕（tools_v2 还原/judge_v1 删除/TOOLS_P2_PATH）。§四 补 w7 交叉引用 | 新增 §二.2.19；§四 |
| 2026-10-09 | 单人（本人） | **M2.3 配套评测集指标**：新增 **§二.2.20**（`evals/m2_acc_set.jsonl` 12题 + `scripts/eval_m2.py`）；**前置发现** 50 条 `golden_set_v1` 与真实语料内容脱节不可直接评测，改走配套集；实测 **Recall@5=1.0 / NDCG@5=1.0**、**MRR=0.7153（中间区间）**、**P95=7.0s（No-Go，CPU rerank）**；§四 补 m2 交叉引用。golden 50 题待语料扩充后重评 | 新增 §二.2.20；§四 |
| 2026-10-09 | 单人（本人） | **D11 延迟闭合（GPU 重排）**：更新 **§二.2.20** 第 5 行 + 裁定口径；`D:\py312-torch`（CUDA torch 2.14.0+cu130, RTX 4060）补装依赖后 `eval_m2.py --device cuda` 全量 12 题 **P95 7037→353.2ms（降幅 95%）**，Recall/MRR/NDCG 无回退；P95<800ms **达标**。`eval_m2.py` 增 `--device` 参数 | 更新 §二.2.20；eval_m2.py |
| 2026-10-09 | 单人（本人） | **D7 重排消融**：更新 **§二.2.20** 第 6-7 行 + 裁定口径；`scripts/d7_ablation.py` 逐题对比 RRF-only vs rerank：rerank ΔMRR=**-0.0417（净负）**，RRF-only **MRR=0.7569≥0.75 达标** + P95=86.1ms；`RetrievalService` 增 `use_rerank` 开关，`eval_m2.py` 增 `--no-rerank`。**M2.3 四项指标全部达标**（Recall=1.0/MRR=0.7569/NDCG=1.0/P95=86ms） | 更新 §二.2.20；retrieve_knowledge.py；eval_m2.py；d7_ablation.py |
| 2026-10-09 | 单人（本人） | **Phase 2 收尾（M2.4 达成）**：新增 **§二.2.21**（`docs/p2-handover-p3.md` + `reports/p2-summary.md`）；M2.4 三项通过条件全部达成（P95=86.1ms / retrieve_knowledge 可用 / 移交 P3）；**M2.1–M2.4 四项里程碑全部达成**；§四 补 handover/summary 交叉引用。遗留转 P3：golden 50 题、Redis 缓存、引用正确率、rerank 重评 | 新增 §二.2.21；§四 |
| 2026-10-09 | 单人（本人） | **Phase 4 前端工程锁版（D1–D5）**：新增 **§二.2.23**（Next 16.4.0 / React 19.3.0 / Tailwind 4.3.3 / radix-ui 1.7.0 单包 / shadcn CLI 4.21.4 nova 预设 / react-query 5.104.1 / socket.io-client 4.8.4 / zustand 5.0.15 / vitest 5.0.3 / playwright 1.64.0 / Node v24.19.0+pnpm 11.7.0）；实测依据：next build 通过 + 单测 30/30 PASS + `pnpm list --depth=0` | 新增 §二.2.23 |
| 2026-10-10 | 单人（本人） | **uv 环境口径统一（P5 收尾方案 A）**：§二.2.3 工具链表新增 **uv 0.11.31** 行；补 4 条说明（`.python-version`=3.12 为解释器唯一锚定、**不升版 `env-baseline-v2.md`** 的 5 条触发条件依据、`uv pip sync` 口径）。**未改正文快照指纹、未升版** | 更新 §二.2.3 |
| 2026-10-10 | 单人（本人） | **环境实装漂移补声明（用户批准）**：新增 **§二.2.24**（`sentence-transformers` 6.1.0 / `ragas` 0.4.3 / `locust` 2.46.7 / `prometheus-client` 0.26.0 / `numpy` 2.5.3 —— 均已被代码 import 且已实装、此前未进 `requirements.txt`）；同步 `requirements.txt`（新增「环境实装漂移补声明」段）。**当日实测纠正**：`uv pip sync` **不解析传递依赖**（`--dry-run` 计划移除 **136 包**）→ §二.2.3 口径定为「**禁止直接 sync**，须先 `uv pip compile` 出锁文件」（纠正同日早前「dry-run 后可选」的错误表述）；§2.3 的【待补声明】→【已补声明】；§四 补 `requirements.txt` 反向依赖行。**新增 🔴 待裁决项**：残留 3 处版本级漂移（`langchain` 1.4.4/1.4.3、`langchain-core` 1.6.9/1.6.4、`langchain-openai` 1.7.0/1.6.6，根因 = 2026-10-09 P5 引入 `ragas` 升级 langchain 链）。`.venv` 未变动，回归 **183 passed**；**未升版 `env-baseline-v2.md`** | 新增 §二.2.24；更新 §二.2.3、§四；`requirements.txt` |
