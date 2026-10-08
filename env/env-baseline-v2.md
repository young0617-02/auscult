# 环境基线 v2 —— 全项目唯一环境基线

> **文件编号**：`env-baseline-v2.md`
> **对应任务**：T1.1（`.wslconfig` 落地）＋ T1.4（组件版本登记）
> **版本**：**v2**（取代 v1；v1 的 WSL2 配额段已作废）
> **采集时间**：2026-09-24（+08:00）｜ **状态复核**：2026-10-08（**环境唯一事实源**；V3 / V4b 实测后镜像清单与 digest 已全部锁定，见 `docs/prj-ledger-version-lock.md` §二.2.1）
> **采集方式**：自动化采集（`scripts/collect_env.ps1` + `docker`/`wsl`/`nvidia-smi`/`ollama` 实测）
> **升版原因**：T1.1 `.wslconfig` 已安装并核验生效，WSL2 配额由 15.51GB → ≈20GB / 10 vCPU。触发升版条件 4（见 §引用纪律）。
> **状态**：M0.1 产出（T1.1 已闭环，live 值已核验）
> **重采核验（2026-09-29）**：`env/hardware.json` 已用修复后的采集脚本重采（`collected_at = 2026-09-29T11:49:36+08:00`，**零警告**），与本基线**逐项一致**——GPU `RTX 4060 Laptop / 8188 MiB / 驱动 616.56 / CC 8.9`、Docker `29.6.2 / Compose 5.3.1 / 19.53 GB / NCPU 10`、WSL2 `live = 10 | Mem 20001`、三模型 layer digest 齐全。
> 重采当时 **Ollama 服务未运行**，故 `toolchain.ollama` 记为 `UNKNOWN`（版本仍以 §四 与 `docs/prj-ledger-version-lock.md` 锁定的 **0.34.2** 为准，不因本次未取到而漂移）。
> 重采前的旧快照（`gpu=null` / `wslconfig_present=false` / Docker `15.51 GB` / `ncpu=20`，属 T1.1 落地前的 v1 口径）已另存为 `env/hardware-v1-2026-09-23.json`，仅供追溯。

---

## ⚠️ 引用纪律（最重要的一条）

**本项目所有实验报告、验证结论、决策文档，引用环境信息时必须写明：**

```
依据环境基线 env-baseline-v2.md（采集于 2026-09-24）
```

**理由**：任何实验结论只在特定版本组合下成立。若本文件升版为 v3，则 v2 下得出的全部结论**必须重新确认或作废**。没有版本号引用的结论视为不可复现。

**升版触发条件**（任一发生即升 v3）：
1. 任一 Docker 镜像 digest 变化
2. 任一模型 digest 变化
3. Ollama / Docker / WSL2 版本变化
4. `.wslconfig` 配额再次变化
5. 硬件变化（加内存、换卡）

> **v1 → v2 变更点**：仅 WSL2 `.wslconfig` 配额段（§三、§六、§七、§十一）发生变化：内存 15.51GB → 20GB、vCPU 20 → 10、`.wslconfig` 不存在 → 已安装生效。其余字段（OS/GPU/磁盘/镜像 digest/模型 digest/端口）与 v1 一致。

---

## 一、操作系统与宿主

| 项 | 实测值 |
|---|---|
| 产品名 | Windows 10 Pro |
| 版本 | 25H2 |
| Build | 26200（10.0.26200.7171） |
| 架构 | x64 |
| 主机名 | <WORKSTATION> |

## 二、CPU

| 项 | 实测值 |
|---|---|
| 型号 | 13th Gen Intel(R) Core(TM) i7-13650HX |
| 逻辑处理器 | 20 |
| 架构 | Intel64 Family 6 Model 183 Stepping 1 |
| 说明 | 6 性能核 + 8 能效核架构（WSL2 侧限 10 核，见 §六） |

## 三、内存

| 项 | 实测值 |
|---|---|
| 物理内存 | **32 GB**（34359738368 bytes） |
| WSL2 设计配额 | 20 GB（62.5%） |
| WSL2 **当前实际**配额 | **20 GB**（`docker info` MemTotal = 20972691456 bytes；`free -m` Mem ≈ 20001 MiB） |
| P0 门禁线（V4 判据） | 峰值 ≤ 24 GB（32 × 75%） |

> **v2 变更**：WSL2 实际配额已从 v1 的 15.51GB 提升至 **≈20GB**，与设计值一致，`.wslconfig` 已生效。20GB 仍 < 24GB 门禁线，V4 判据需在容器内口径下评估（见 `docs/p0-spec-gate-criteria.md`）。

## 四、GPU

| 项 | 实测值 |
|---|---|
| 型号 | NVIDIA GeForce RTX 4060 Laptop GPU |
| 显存总量 | **8188 MiB**（约 8 GB） |
| 采集时显存占用 | 1282 MiB |
| 驱动版本（nvidia-smi） | **616.56** |
| 驱动版本（Windows WMI） | 32.0.16.1656 |
| Compute Capability | **8.9**（Ada Lovelace） |
| 本地 CUDA Toolkit | ❌ 默认路径下未安装 |

> **判读**：8GB 显存是**本项目最硬的约束**。7B 模型 Q4 量化约占 4.7GB，reranker 另需显存 —— **2026-09-29 起 BGE-M3 向量化改走 CPU**（ModelScope 本地加载，不占 GPU，见 §八.1.1），与 V2"纯 CPU"、V1"独占 GPU"计划一致（计划 §1.3、风险 R10）。
>
> WMI 报告的 `AdapterRAM = 4293918720`（约 4GB）是 32 位截断值，**不可用**，一律以 nvidia-smi 的 8188 MiB 为准。

## 五、磁盘

| 盘符 | 已用 | 剩余 | 用途 |
|---|---|---|---|
| C | 106.6 GB | **94.3 GB** | 系统盘，空间紧张 |
| D | 71.2 GB | **429.8 GB** | 项目盘 + Ollama 模型盘（`D:\.ollama`） + swap 文件（`D:\wsl-swap.vhdx`） |
| E | 188.5 GB | 62.5 GB | — |

> **决策**：`.wslconfig` 的 `swapFile`（`D:\wsl-swap.vhdx`）与 Docker 数据盘已规划放 D 盘，避免 C 盘耗尽。

## 六、WSL2（v2：`.wslconfig` 已生效）

| 项 | 实测值 |
|---|---|
| WSL 版本 | 2.7.11.0 |
| 内核版本 | 6.18.33.2-2 |
| WSLg | 1.0.73.2 |
| MSRDC | 1.2.7214 |
| Direct3D | 1.611.1-81528511 |
| 发行版清单 | **仅 `docker-desktop`（v2）** |
| 默认发行版 | docker-desktop |
| **`%UserProfile%\.wslconfig`** | ✅ **已安装（2026-09-24，`memory=20GB / processors=10 / swap=8GB`）** |
| WSL2 实测 vCPU | **10**（`docker info` NCPU=10） |
| WSL2 实测内存总量 | **20001 MiB ≈ 20 GB**（`free -m`） |
| WSL2 实测可用内存 | ≈ 17.5 GB（`free -m` available） |
| Swap | **8192 MiB ≈ 8 GB**（`free -m` Swap） |
| GPU 直通状态 | ✅ **已裁决为「不需要」**（2026-09-24 U-03 / `ISS-008`）：推理改走**宿主原生 Ollama**，容器内 GPU 直通不再是判据前置分支，UNVERIFIED 不阻塞 |

### 6.1 T1.1 `.wslconfig` 已闭环（v2 变更核心）

v1 记录的"`.wslconfig` 从未创建"已解除。2026-09-24 已执行：
`Copy-Item env\wslconfig.proposed → %UserProfile%\.wslconfig` → `wsl --shutdown` → 重启 Docker Desktop 后核验：

| 检查项 | 设计值 | live 核验值 | 判定 |
|---|---|---|---|
| `docker info` MemTotal | 20GB | **20972691456 bytes ≈ 20GB** | ✅ |
| `free -m` Mem | 20GB | **20001 MiB** | ✅ |
| `docker info` NCPU | 10 | **10** | ✅ |
| `free -m` Swap | 8GB | **8192 MiB** | ✅ |

**T1.1 阻塞已解除。** V4b 的 24GB 门禁判据现可在容器内口径下评估（20GB 容器配额 < 24GB 宿主门禁线，须明确口径，见 `docs/p0-spec-gate-criteria.md`）。

> 回滚路径见 `env/wslconfig.bak` §三（删除文件 + `wsl --shutdown`）。

### 6.2 遗留偏差：无通用 Linux 发行版 → GPU 直通未验证

本机只有 `docker-desktop` 工具发行版，其内**没有 `nvidia-smi`**，无法在该发行版内验证 GPU 直通。

**后果**：V4 判据中的"**GPU 可直通**"这一半**当前无法判定**。

**处置**（待用户择机执行）：
```powershell
wsl --install -d Ubuntu-24.04
wsl -d Ubuntu-24.04 -- nvidia-smi
```
> 注：Ollama 跑在 **Windows 原生侧**，走 Windows 驱动，不依赖 WSL2 直通，因此 V1 不受此偏差影响。受影响的只有"WSL2 内跑 CUDA"的计划。

## 七、Docker（v2：配额更新）

| 项 | 实测值 |
|---|---|
| 引擎版本 | **29.6.2** |
| Compose 版本 | **v5.3.1** |
| 平台 | Docker Desktop |
| NCpu | **10**（v1 为 20） |
| MemTotal | **20972691456 bytes ≈ 20 GB**（v1 为 15.51GB） |
| 镜像总数 / 占用 | 8 / 10.25 GB |
| 容器总数 | — |
| 数据卷总数 | — |

### 7.1 镜像 digest 登记（★ 版本锁定的唯一依据，未变）

| 镜像 | Tag | **Digest** | 大小 | 本项目用途 |
|---|---|---|---|---|
| milvusdb/milvus | v3.0.0 | `sha256:49371c30af46b1013e4d3e0b980e691d81376d69cdbe1b372725baf1d7255862` | 3.93 GB | **V2 主路线**（向量库） |
| quay.io/coreos/etcd | v3.5.25 | `sha256:52f17f7e56e4f7239f0320dbfcbcc24721163d7d78ae710b466af3254ccf6366` | 93.8 MB | Milvus 依赖 |
| minio/minio | RELEASE.2024-12-18T13-15-44Z | `sha256:1dce27c494a16bae114774f1cec295493f3613142713130c2d22dd5696be6ad3` | 244 MB | Milvus 依赖 |
| postgres | 18 | `sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280` | 650 MB | **V2 对照路线** + 业务库 |
| redis | 8 | `sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5` | 212 MB | **V5 checkpoint** |
| nacos/nacos-server | latest | `sha256:1c191c30c8cd5ff2a72bf576555dbaa57a616378c55168651a74aefadedf7708` | 2.09 GB | ⚠️ 非本项目（其他项目在用） |
| mysql | 8.4 | `sha256:b3b90af2a6552ae30c266fdb7d5dd55f3afb72404bb78d37fe8a23eb857fd3fb` | 1.12 GB | ⚠️ 非本项目 |
| mongodb/mongodb-atlas-local | 8.0 | `sha256:33de960ef58be32fddba97edaea2dc6976dc10caf11b4e38b32c3c67ade96c91` | 2.02 GB | ⚠️ 非本项目 |

> ✅ **已闭环（2026-09-24 实测回填）**：Neo4j `5-community`（≈1.0 GB，V4b 压测拉取，实测内存 ≈871 MiB）、TDengine `tdengine/tsdb:3.3.8.0`（1.68 GB）、`eclipse-mosquitto:2`（41.8 MB）**三个镜像均已拉取并逐条锁 digest** —— 见 `docs/prj-ledger-version-lock.md` §二.2.1 第 6/7/8 行。**BGE-M3 不在此列**：向量模型经 ModelScope 本地加载（§八.1.1），非 Docker 镜像。**2026-09-29 已删除 Ollama `bge-m3`（1.2GB），Ollama 仅保留 2 个生成模型。**
> ⚠️ `milvusdb/milvus:v3.0.0` 与计划 §二 Q3 的裁决一致（v3.0.0 + 服务端 `FunctionType.BM25`），✅ 无偏差。

## 八、模型（未变）

| 项 | 实测值 |
|---|---|
| Ollama 版本 | **0.34.2** |
| 可升级版本 | 0.34.3（实测检测到更新） |
| API 端点 | `http://127.0.0.1:11434` |
| 模型根目录 | `D:\.ollama\models`（仅 2 个生成模型；**BGE-M3 已迁至 ModelScope §八.1.1**） |
| 已装模型数 | 2（生成模型）；向量模型另计于 §八.1.1 |
| 当前加载模型 | 无（`/api/ps` 返回空） |

### 8.1 模型 digest 登记（★ V1 可复现性的唯一依据）

| 模型 | 模型层 Digest | Manifest config Digest | 大小 |
|---|---|---|---|
| **qwen2.5:7b** | `sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730` | `sha256:2f15b3218f0552c60647ce60ada83632d2c09755b16259b13e3e4458e9ae419d` | 4.68 GB |
| **deepseek-r1:7b** | `sha256:96c415656d377afbff962f6cdb2394ab092ccbcbaab4b82525bc4ca800fe8a49` | `sha256:40fb844194b25e429204e5163fb379ab462978a262b86aadd73d8944445c09fd` | 4.68 GB |

> **V1 报告必须原样引用上表 digest**，否则结论无法复现。
> **裁决（覆盖本行原建议，2026-09-24 U-04 / `ISS-009`）**：**锁定维持 Ollama 0.34.2，不升级 0.34.3 / 0.34.4**，理由 = 已安装运行 + V1 全流程固定同版本以**防行为漂移**；digest 见 `docs/prj-ledger-version-lock.md` §二.2.1 与 §九。**本行原「建议升级到 0.34.3 并重登 digest」作废**（若日后升级，须按纪律 2 变更即升版并重新登记 digest，且 V1 结论须按 §3.1.3 同口径复测）。

### 8.1.1 ModelScope 本地向量模型（BGE-M3，2026-09-29 迁移）

> **2026-09-29：BGE-M3 从 Ollama 迁移到 ModelScope 本地加载**（与 `docs/prj-ledger-version-lock.md` §2.2.1 一致）。原经 Ollama `/v1/embeddings`（blob `sha256:daec91ff…3062c`）加载，现由 sentence-transformers 直接加载本地目录，**已删除 Ollama `bge-m3` 模型（1.2GB）**，Ollama 不再承担向量化。

| 模型 | 路径 | 维度 | 大小 | 用途 |
|---|---|---|---|---|
| **BAAI--bge-m3**（sentence-transformers 格式） | `D:\modelscope\hub\models\BAAI--bge-m3\snapshots\master` | **1024（实测 2026-09-29）** | ~1.7GB | V2 向量化（dense embedding） |

> **调用**：`scripts/run_v2.py` `EmbeddingClient`（默认 `BGE_M3_MODEL_PATH` 常量）；依赖 `sentence-transformers`（`.venv`）。

## 九、运行时与工具链（未变）

| 工具 | 路径 | 版本 |
|---|---|---|
| Python | `D:\Python312\python.exe` | **3.12.8** |
| Node.js | `C:\Program Files\nodejs\node.exe` | **v24.19.0** |
| Git | `C:\Program Files\Git\cmd\git.exe` | **2.45.1.windows.1** |
| Docker | `C:\Program Files\Docker\Docker\resources\bin\docker.exe` | 29.6.2 |
| WSL | `C:\WINDOWS\system32\wsl.exe` | 2.7.11.0 |
| nvidia-smi | `C:\WINDOWS\system32\nvidia-smi.exe` | 随驱动 616.56 |
| Ollama | `<USER_HOME>\AppData\Local\Programs\Ollama\ollama.exe` | 0.34.2 |

## 十、端口基线（未变）

| 端口 | 组件 | 实测 | 处置 |
|---|---|---|---|
| 19530 / 9091 | Milvus | ✅ free | 使用 |
| 7474 / 7687 | Neo4j | ✅ free | 使用 |
| 6030 / 6041 | TDengine | ✅ free | 使用 |
| 5432 | PostgreSQL | ✅ free | 使用 |
| 6379 | Redis | ✅ free | 使用 |
| **11434** | **Ollama** | ⚠️ **OCCUPIED** | 预期占用，保留 |
| 1883 | Mosquitto | ✅ free | 使用 |
| 8000 / 3000 | 后端 / 前端 | ✅ free | 使用 |

**11/12 空闲，无需端口重映射。** 详见 `env/ports.md`。

> 宿主另有其他项目占用 8080/8848/9848（nacos-standalone），与本项目端口基线**无冲突**。

## 十一、基线快照指纹（v2）

```
硬件指纹：   i7-13650HX / 32GB / RTX4060-8188MiB / 驱动616.56
WSL 指纹：   2.7.11.0 / 内核6.18.33.2-2 / 仅docker-desktop / .wslconfig已安装 / 20GB / 10vCPU
Docker 指纹：29.6.2 / Compose v5.3.1 / 8镜像 / MemTotal≈20GB / NCPU=10
Milvus 指纹：v3.0.0 @ sha256:49371c30af46b1013e4d3e0b980e691d81376d69cdbe1b372725baf1d7255862
Redis  指纹：redis:8 @ sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5
PG     指纹：postgres:18 @ sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280
模型 指纹：qwen2.5:7b @ sha256:2bada8a7...93730 / deepseek-r1:7b @ sha256:96c41565...e8a49
采集时间：2026-09-24 +08:00
```

---

## 十二、T1.1 + T1.4 DoD 自检

- [x] `.wslconfig` 已安装并核验生效（20GB / 10vCPU / 8GB swap）
- [x] OS / Build 已登记
- [x] CPU / 内存 / GPU / 显存 已登记（含 compute capability，WSL2 侧 10 核）
- [x] 磁盘各盘剩余空间已登记
- [x] WSL2 版本、内核、发行版、配额已登记（v2：20GB / 10 核）
- [x] Docker / Compose 版本已登记（MemTotal 20GB / NCPU 10）
- [x] **各镜像 digest 已登记**（8 个）
- [x] **各模型 digest 已登记**（2 个，模型层 + manifest 双 digest）
- [x] Python / Node / Git / Ollama 版本已登记
- [x] 端口基线已登记
- [x] 遗留偏差已声明（仅 1 项：GPU 直通未验证）

> ✅ **T1.1 已闭环、环境基线 v2 已落盘。**
> ⚠️ 遗留偏差仅 1 项：GPU 直通 UNVERIFIED（待安装 Ubuntu 后验证）。