# 环境基线 v1 —— 全项目唯一环境基线

> **⚠️ 已被 v2 取代**：本项目现以 **`env/env-baseline-v2.md`（采集于 2026-09-24）** 为唯一环境基线。本 v1 文件保留作历史留档。
> **升版触发**：T1.1 `.wslconfig` 已安装生效，WSL2 配额 15.51GB → 20GB / 10 vCPU（触发升版条件 4）。
> **v1 下 WSL2 配额相关结论已作废**，引用一律改用 v2。

> **文件编号**：`env-baseline-v1.md`
> **对应任务**：T1.4（组件版本登记）
> **版本**：**v1**
> **采集时间**：2026-09-23 20:51（+08:00）
> **采集方式**：自动化采集（`scripts/collect_env.ps1` + `docker`/`wsl`/`nvidia-smi`/`ollama` 实测）
> **状态**：M0.1 产出

---

## ⚠️ 引用纪律（最重要的一条）

**本项目所有实验报告、验证结论、决策文档，引用环境信息时必须写明：**

```
依据环境基线 env-baseline-v1.md（采集于 2026-09-23 20:51）
```

**理由**：任何实验结论只在特定版本组合下成立。若本文件升版为 v2，则 v1 下得出的全部结论**必须重新确认或作废**。没有版本号引用的结论视为不可复现。

**升版触发条件**（任一发生即升 v2）：
1. 任一 Docker 镜像 digest 变化
2. 任一模型 digest 变化
3. Ollama / Docker / WSL2 版本变化
4. `.wslconfig` 落地导致 WSL2 配额变化（**本文件已知即将触发，见 §6**）
5. 硬件变化（加内存、换卡）

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
| 说明 | 6 性能核 + 8 能效核架构 |

## 三、内存

| 项 | 实测值 |
|---|---|
| 物理内存 | **32 GB**（34359738368 bytes） |
| WSL2 设计配额 | 20 GB（62.5%） |
| WSL2 **当前实际**配额 | **15.51 GB**（见 §6 偏差声明） |
| P0 门禁线（V4 判据） | 峰值 ≤ 24 GB（32 × 75%） |

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

> **判读**：8GB 显存是**本项目最硬的约束**。7B 模型 Q4 量化约占 4.7GB，BGE-M3 约占 1–2GB，reranker 另需显存 —— 三者**无法同时常驻**。这直接决定 V1 必须"独占 GPU"、V2 必须"纯 CPU"（计划 §1.3、风险 R10）。
>
> WMI 报告的 `AdapterRAM = 4293918720`（约 4GB）是 32 位截断值，**不可用**，一律以 nvidia-smi 的 8188 MiB 为准。

## 五、磁盘

| 盘符 | 已用 | 剩余 | 用途 |
|---|---|---|---|
| C | 106.6 GB | **94.3 GB** | 系统盘，空间紧张 |
| D | 71.2 GB | **429.8 GB** | 项目盘 + Ollama 模型盘（`D:\.ollama`） |
| E | 188.5 GB | 62.5 GB | — |

> **决策**：`.wslconfig` 的 `swapFile` 与 Docker 数据盘应放 D 盘，避免 C 盘耗尽。

## 六、WSL2 —— 本文件最关键的偏差声明

| 项 | 实测值 |
|---|---|
| WSL 版本 | 2.7.11.0 |
| 内核版本 | 6.18.33.2-2 |
| WSLg | 1.0.73.2 |
| MSRDC | 1.2.7214 |
| Direct3D | 1.611.1-81528511 |
| 发行版清单 | **仅 `docker-desktop`（Running, v2）** |
| 默认发行版 | docker-desktop |
| **`%UserProfile%\.wslconfig`** | ❌ **不存在** |
| WSL2 实测 vCPU | 20 |
| WSL2 实测内存总量 | 15885 MiB ≈ **15.51 GB** |
| WSL2 实测可用内存 | 13328 MiB ≈ 13.02 GB |
| GPU 直通状态 | ⚠️ **未验证** |

### 6.1 偏差 1：`.wslconfig` 从未创建（★ P0 首要阻塞项）

计划 §二 Q2 已裁决配置为 `memory=20GB / processors=10 / swap=8GB`，但实测该文件**不存在**。

**后果**：
- Docker 引擎当前内存上限仅 **15.51 GB**，恰好是 32GB 的 50%（Docker Desktop 默认策略）
- **15.51 GB < 24 GB 门禁线**，余量缺口 8.49 GB
- 因此：**V4b（D8）压测结论在 T1.1 落地前不具备有效性**，即使压测通过也不能判定 Pass

**处置**：已产出 `env/wslconfig.proposed`（可直接安装）+ `env/wslconfig.bak`（回滚说明）。安装需执行 `wsl --shutdown`，会中断正在运行的 `nacos-standalone` 容器，**待用户选择时机执行**。

### 6.2 偏差 2：无通用 Linux 发行版 → GPU 直通未验证

本机只有 `docker-desktop` 工具发行版，其内**没有 `nvidia-smi`**，因此无法在该发行版内验证 GPU 直通。

**后果**：
- V4 判据中的"**GPU 可直通**"这一半**当前无法判定**
- 若后续需要 WSL2 内原生跑 CUDA（如自建 embedding 服务），必须先安装 Ubuntu

**处置**（D1 收尾/D2 前完成）：
```powershell
wsl --install -d Ubuntu-24.04
# 安装后验证：
wsl -d Ubuntu-24.04 -- nvidia-smi
```
> 注：Ollama 跑在 **Windows 原生侧**，走 Windows 驱动，不依赖 WSL2 直通，因此 V1 不受此偏差影响。受影响的只有"WSL2 内跑 CUDA"的计划。

## 七、Docker

| 项 | 实测值 |
|---|---|
| 引擎版本 | **29.6.2** |
| Compose 版本 | **v5.3.1** |
| 平台 | Docker Desktop |
| NCpu | 20 |
| MemTotal | 16656285696 bytes = **15.51 GB** |
| 镜像总数 / 占用 | 8 / 10.25 GB |
| 容器总数 | 15（1 个运行中） |
| 数据卷总数 | 21 |

### 7.1 镜像 digest 登记（★ 版本锁定的唯一依据）

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

> ⚠️ **注意**：本机镜像中**没有** Neo4j、TDengine、Mosquitto、BGE-M3。这些需在 D4/D6 拉取，**拉取后必须立即回填本表并锁 digest**。
> ⚠️ `milvusdb/milvus:v3.0.0` 与计划 §二 Q3 的裁决一致（v3.0.0 + 服务端 `FunctionType.BM25`），✅ 无偏差。

## 八、模型

| 项 | 实测值 |
|---|---|
| Ollama 版本 | **0.34.2** |
| 可升级版本 | 0.34.3（实测检测到更新） |
| API 端点 | `http://127.0.0.1:11434` |
| 模型根目录 | `D:\.ollama\models` |
| 已装模型数 | 2 |
| 当前加载模型 | 无（`/api/ps` 返回空） |

### 8.1 模型 digest 登记（★ V1 可复现性的唯一依据）

| 模型 | 模型层 Digest | Manifest config Digest | 大小 |
|---|---|---|---|
| **qwen2.5:7b** | `sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730` | `sha256:2f15b3218f0552c60647ce60ada83632d2c09755b16259b13e3e4458e9ae419d` | 4.68 GB |
| **deepseek-r1:7b** | `sha256:96c415656d377afbff962f6cdb2394ab092ccbcbaab4b82525bc4ca800fe8a49` | `sha256:40fb844194b25e429204e5163fb379ab462978a262b86aadd73d8944445c09fd` | 4.68 GB |

> **V1 报告必须原样引用上表 digest**，否则结论无法复现。
> **建议**：V1 开跑前先 `ollama pull` 升级到 0.34.3 并重新登记 digest，避免验证中途版本漂移（已在 prj-ledger-risk-register 登记）。

## 九、运行时与工具链

| 工具 | 路径 | 版本 |
|---|---|---|
| Python | `D:\Python312\python.exe` | **3.12.8** |
| Node.js | `C:\Program Files\nodejs\node.exe` | **v24.19.0** |
| Git | `C:\Program Files\Git\cmd\git.exe` | **2.45.1.windows.1** |
| Docker | `C:\Program Files\Docker\Docker\resources\bin\docker.exe` | 29.6.2 |
| WSL | `C:\WINDOWS\system32\wsl.exe` | 2.7.11.0 |
| nvidia-smi | `C:\WINDOWS\system32\nvidia-smi.exe` | 随驱动 616.56 |
| Ollama | `<USER_HOME>\AppData\Local\Programs\Ollama\ollama.exe` | 0.34.2 |

## 十、端口基线

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

## 十一、基线快照指纹

为便于校验本文件是否被篡改或与实际不符，记录关键指纹：

```
硬件指纹：   i7-13650HX / 32GB / RTX4060-8188MiB / 驱动616.56
WSL 指纹：   2.7.11.0 / 内核6.18.33.2-2 / 仅docker-desktop / 无.wslconfig / 15.51GB
Docker 指纹：29.6.2 / Compose v5.3.1 / 8镜像
Milvus 指纹：v3.0.0 @ sha256:49371c30af46b1013e4d3e0b980e691d81376d69cdbe1b372725baf1d7255862
Redis  指纹：redis:8 @ sha256:298e5b3bc566bade82f46ad5511777a4a07a294097ce16ada2f6a42be5239df5
PG     指纹：postgres:18 @ sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280
模型 指纹：qwen2.5:7b @ sha256:2bada8a7...93730 / deepseek-r1:7b @ sha256:96c41565...e8a49
采集时间：2026-09-23 20:51 +08:00
```

---

## 十二、T1.4 DoD 自检

- [x] OS / Build 已登记
- [x] CPU / 内存 / GPU / 显存 已登记（含 compute capability）
- [x] 磁盘各盘剩余空间已登记
- [x] WSL2 版本、内核、发行版、配额已登记
- [x] Docker / Compose 版本已登记
- [x] **各镜像 digest 已登记**（8 个）
- [x] **各模型 digest 已登记**（2 个，模型层 + manifest 双 digest）
- [x] Python / Node / Git / Ollama 版本已登记
- [x] 端口基线已登记
- [x] 与上游计划的偏差已显式声明（2 项：`.wslconfig` 未落地、GPU 直通未验证）

> ✅ **T1.4 通过 —— 环境基线 v1 已落盘，字段完整。**
> ⚠️ 但本文件**即将升版为 v2**：`.wslconfig` 落地后 WSL2 配额会从 15.51GB 变为 ≈20GB，届时必须重新采集并升版。