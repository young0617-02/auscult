# D1 当日状态记录（基线建立 · 硬门禁）

> 日期：D1
> 对应计划：`p0-plan-detailed-d1-d10.md` §三 · D1
> 出口里程碑：**M0.1（约束与基线锁定）**
> 环境数据采集时间：2026-09-23 20:59:50（+08:00）（`env/hardware.json`；端口检查 `env/ports.md` 为 20:51，两者是不同测量）
> 项目根：`<REPO>`

---

## 一、当日目标

产出一份被**所有**验证项引用的**唯一环境基线**，并冻结工具 Schema v1。

- 前置：无
- 出口：**M0.1** —— 环境基线 + Schema v1 + 数据来源清单

---

## 二、逐任务执行表（T1.1–T1.9）

| 任务 | 计划动作 | 实际状态 | 产出物 | 证据 / 缺口 |
|---|---|---|---|---|
| **T1.1** WSL2 / Docker 配置 | 写入 `%UserProfile%\.wslconfig` → `wsl --shutdown` → `docker info` 核对 | ⚠️ **部分完成**（当日口径：方案与备份就绪，**安装动作未执行**） | `env/wslconfig.proposed`、`env/wslconfig.bak` | `env/wslconfig.bak` 实测 `Test-Path "$env:UserProfile\.wslconfig"` → **False**，即该文件**不存在**；缺口 = 复制文件 + `wsl --shutdown` 这一步未做。**后续更新（2026-09-24）**：本缺口已补齐 —— 复制 + `wsl --shutdown` 完成，live 值待重启 Docker 核对；当日事实保留 |
| **T1.2** 硬件采集 | 运行采集脚本，记录 CPU/内存/GPU/磁盘/CUDA/驱动 | ✅ **已完成（实测）** | `env/hardware.json` | 采集时间 **2026-09-23T20:59:50+08:00**（原误记 20:51；20:51 是 T1.3 端口检查的时间，见 `env/ports.md`），采集者 `collect_env.ps1`，宿主 `<WORKSTATION>` |
| **T1.3** 端口检查 | 扫描 12 个目标端口，冲突项记重映射方案 | ✅ **已完成（实测）** | `env/ports.md` | 实测结果：**11/12 空闲，无需重映射**；11434 被宿主 Ollama 占用属预期 |
| **T1.4** 组件版本登记 | `docker images --digests` + `ollama list` + `nvidia-smi`，记录 digest | ✅ **已完成（实测采集）** | `env/env-baseline-v1.md` | 含 **8 个镜像 digest + 2 个模型 digest**；本报告只引用其中已当面核对的部分，完整清单以 `env/env-baseline-v1.md` 为准 |
| **T1.5** 目录初始化 | 按计划 §六 建立工程目录 | ✅ **已完成** | 目录树 | 实测已建成 `configs/ docker/ docs/ env/ evals/ experiments/{v1,v2,v5}/raw/ prompts/ reports/daily/ schemas/ scripts/` |
| **T1.6** Schema v1 冻结 | 编写 5 工具 Pydantic ↔ JSON Schema，落盘并打版本号 | ✅ **已完成** | `schemas/tools_v1.json` | 5 工具已冻结为 v1；后续任何改动**必须升版** |
| **T1.7** 数据来源盘点 | 逐类盘点手册/工单/传感器：名称/格式/体量/获取方式/许可/替代 | ✅ **已完成** | `docs/p1-spec-data-sources.md` | 含**自编模拟数据兜底路线**（应对版权/隐私判定延迟，对应 R15） |
| **T1.8** 实验登记规范 | 定稿模板字段（digest/seed/prompt 版本/num_ctx/temperature/commit） | ✅ **已完成** | `docs/prj-template-experiment-log.md` | 模板可用，D2 起所有实验必须登记 |
| **T1.9** TDengine 授权确认 | 查证社区版（OSS）是否含 SparkplugB 接入；不通过则立即启降级评估 | ❌ **未完成，待查证** | 落点 `reports/p0-report-v3-ingest-license.md` 第一段 | **D1 唯一未闭环项**；详见 `reports/p0-report-v3-ingest-license.md` 的查证清单 |

**状态统计**：已完成 7 项（T1.2/T1.3/T1.4/T1.5/T1.6/T1.7/T1.8）、部分完成 1 项（T1.1）、未完成 1 项（T1.9）。

---

## 三、实测事实与证据

### 3.1 操作系统与主机

| 项 | 实测值 |
|---|---|
| 主机名 | `<WORKSTATION>` |
| OS | Windows 10 Pro，25H2，build 26200（`10.0.26200.7171`），x64 |

### 3.2 计算资源

| 项 | 实测值 | 说明 |
|---|---|---|
| CPU | 13th Gen Intel Core i7-13650HX | Intel64 Family 6 Model 183 Stepping 1；6P+8E，**20 逻辑核** |
| 物理内存 | **32GB**（34359738368 bytes） | WSL2 设计配额 20GB = 62.5% |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU | 驱动 **616.56**（WMI 报 32.0.16.1656）；compute capability **8.9** |
| 显存 | 总量 8188 MiB ≈ 8GB；采集时已用 **1282 MiB** | WMI `AdapterRAM` 报 ~4GB 为 32 位截断，以 `nvidia-smi` 为准 |
| CUDA Toolkit | 默认路径下**未安装** | Ollama 自带 CUDA 运行时，WSL2 走驱动透传；编译类需求须另装 |

### 3.3 磁盘

| 盘 | 已用 | 剩余 | 备注 |
|---|---|---|---|
| C | 106.6GB | **94.3GB** | 系统盘，偏紧 → `.wslconfig` 的 `swapFile` 建议落 D 盘 |
| D | 71.2GB | **429.8GB** | 项目盘 + Ollama 模型盘（`D:\.ollama\models`） |
| E | — | **62.5GB** | — |

### 3.4 WSL2 与 Docker 现状（**本阶段最关键的实测发现**）

| 项 | 实测值 | 来源 |
|---|---|---|
| WSL 版本 | 2.7.11.0 | `wsl --version` |
| WSL 内核 | **6.18.33.2-2** | `wsl --version` |
| WSLg / msrdc | 1.0.73.2 / 1.2.7214 | `wsl --version` |
| `%UserProfile%\.wslconfig` | **不存在** | `Test-Path` → False |
| WSL2 发行版 | **仅 `docker-desktop`（工具发行版，默认，Running）** | `wsl -l -v` |
| WSL2 实际 vCPU | 20 | `wsl -d docker-desktop -- nproc` |
| WSL2 内存总量 | 15885 MiB ≈ **15.51GB** | `free -m` |
| WSL2 可用内存 | 13328 MiB ≈ 13.02GB | `free -m` |
| Docker 引擎内存上限 | **16656285696 bytes = 15.51GB**（NCPU=20） | `docker info` |
| Docker / Compose | 29.6.2 / v5.3.1 | `docker info` / `docker compose version` |
| 镜像总数 / 占用 | 8 个 / 10.25GB | `docker images` |
| 容器总数 / 卷总数 | 15 / 21 | `docker info` |

**结论**：15.51GB = 32GB 的 **50%**，即 Docker Desktop 的默认分配策略在生效，说明 `.wslconfig` 从未创建过。设计值 `memory=20GB / processors=10 / swap=8GB` 目前**未落地**。

> ⚠️ **这是一条硬结论**：在 T1.1 安装动作完成前，**V4b（D8）的 24GB 门禁判据不成立**，压测结论无效。列为 P0 首要阻塞项。

### 3.5 GPU 直通状态

| 项 | 状态 |
|---|---|
| WSL2 内 GPU 直通 | **UNVERIFIED（未验证）** |
| 原因 | 本机只有 `docker-desktop` 工具发行版，**其内无 `nvidia-smi`**；没有通用 Linux 发行版可供验证 |
| 解除条件 | 安装通用发行版（如 Ubuntu）后，在发行版内执行 `nvidia-smi` 验证 |

### 3.6 工具链版本

| 工具 | 版本 | 路径 |
|---|---|---|
| Python | 3.12.8 | `D:\Python312\python.exe` |
| Node | v24.19.0 | `C:\Program Files\nodejs\node.exe` |
| Git | 2.45.1.windows.1 | `C:\Program Files\Git\cmd\git.exe` |
| Ollama | **0.34.2**（有 0.34.3 可升级） | `<USER_HOME>\AppData\Local\Programs\Ollama\ollama.exe`，API `http://127.0.0.1:11434` |
| Milvus 镜像 | `milvusdb/milvus:v3.0.0` | digest `sha256:49371c30af46b1013e4d3e0b980e691d81376d69cdbe1b372725baf1d7255862` |

**模型 digest（实测）**：

| 模型 | 模型层 digest |
|---|---|
| `qwen2.5:7b` | `sha256:2bada8a7450677000f678be90653b85d364de7db25eb5ea54136ada5f3933730` |
| `deepseek-r1:7b` | `sha256:96c415656d377afbff962f6cdb2394ab092ccbcbaab4b82525bc4ca800fe8a49` |

> **T1.4 待办**：计划建议 V1 开跑前把 Ollama 升到 **0.34.3**，避免版本漂移；若升级，必须重新登记 digest 并同步 `docs/prj-ledger-version-lock.md`。

### 3.7 端口实测

| 端口 | 组件 | 实测 |
|---|---|---|
| 19530 / 9091 | Milvus gRPC / metrics | ✅ free |
| 7474 / 7687 | Neo4j HTTP / Bolt | ✅ free |
| 6030 / 6041 | TDengine 原生 / REST | ✅ free |
| 5432 | PostgreSQL + pgvector | ✅ free |
| 6379 | Redis checkpoint | ✅ free |
| **11434** | **Ollama** | ⚠️ **OCCUPIED**（PID 80484，绑 `127.0.0.1`，**预期占用，非冲突**） |
| 1883 | Mosquitto MQTT | ✅ free |
| 8000 / 3000 | 后端 API / 前端 | ✅ free |

**11/12 空闲，无需重映射。** 端口分配基线已在 `env/ports.md` §四 冻结，后续所有 compose 必须遵守。

**非本项目占用（仅留意，不处理）**：`nacos-standalone` 容器占 8080/8848/9848，属宿主上其他项目；`443` 被本机 HTTPS 服务占用。P0 各验证项启动时**不要** `docker system prune` 或停止非本项目容器。

---

## 四、发现的问题与风险

| 编号 | 问题 | 影响 | 处置 | 关联风险 |
|---|---|---|---|---|
| D1-P1 | **`.wslconfig` 从未安装**，Docker 仅 15.51GB（默认 50%） | V4b 24GB 门禁判据不成立；全组件压测无法得出有效结论 | 安装动作待用户执行（会中断 WSL2 与正在运行的 nacos 容器）→ 见 `env/wslconfig.proposed`；回滚路径见 `env/wslconfig.bak` §三 | **R2、R3、R9** |
| D1-P2 | **GPU 直通未验证**（无通用 Linux 发行版，工具发行版内无 `nvidia-smi`） | V4 判据中"GPU 可直通"一半无法判定 | 安装 Ubuntu 发行版后执行 `nvidia-smi` 验证；在此期间 GPU 直通结论保持 UNVERIFIED | **R2、R10** |
| D1-P3 | **T1.9 TDengine 授权未查证** | 时序接入路线可能整体作废（唯一不可控外部依赖） | 按 `reports/p0-report-v3-ingest-license.md` 的查证清单（官方文档 / license 文件 / 社区商务口径）执行；**不通过即立即启降级评估**（自研解码器 ≤2 天） | **R8、R15** |
| D1-P4 | Ollama 0.34.2，存在 0.34.3 可升级 | 若在 V1 中途升级会造成版本漂移、结论失效 | 在 V1 开跑**之前**决定升/不升，并把最终版本与 digest 写进 `docs/prj-ledger-version-lock.md` | **R7** |
| D1-P5 | C 盘剩余仅 94.3GB | 镜像/模型/交换文件堆积可能撑爆系统盘 | 交换文件已规划落 D 盘（`D:\wsl-swap.vhdx`）；模型盘已在 D 盘 | R15 |

> 建议：D1-P1 / D1-P2 / D1-P3 均应登记进 `docs/prj-ledger-risk-register.md`（R2、R8、R10 的实例化）。

---

## 五、次日（D2）待办与阻塞

### 5.1 待办

1. **【最高优先】解除 D1-P1**：由用户择机执行 `.wslconfig` 安装：
   ```powershell
   Copy-Item <REPO>\env\wslconfig.proposed "$env:UserProfile\.wslconfig" -Force
   wsl --shutdown
   ```
   然后重启 Docker Desktop，核对：
   ```powershell
   docker info --format '{{.MemTotal}} {{.NCPU}}'   # 期望 ≈ 20GB / 10
   ```
   > ⚠️ 会在执行瞬间停掉 `nacos-standalone` 等所有容器，需自行选择时机。
2. **解除 D1-P3**：按 `reports/p0-report-v3-ingest-license.md` 第一段的查证清单落地 TDengine 授权结论（可用 / 需降级 / No-Go）。
3. **D2 上午按计划推进 V1 准备（不占 GPU）**：20 条用例（`evals/v1_cases.jsonl`，难度分层 + 5 类型，对齐"离心泵轴承振动"主场景）、自动判分器（`scripts/judge_tools.py`）、统一适配层（`scripts/llm_adapter.py`，统一剥离 `think`）、落盘与断点续跑（`scripts/run_v1.py`）。
4. **并行推进 V7**：50 条种子评测集 + 标注规范 v1。
5. **D2 开工前自检**（计划 §八 通用规则）：今日 V 项判据是否已定稿 → V1 判据已在 `reports/p0-report-v1-tool-call.md` 定稿；实验登记模板是否可用 → ✅（T1.8）。
6. 决定 Ollama 是否升级到 0.34.3，并同步 digest。

### 5.2 阻塞项

| 阻塞项 | 卡住的下游结论 | 解除需要什么 |
|---|---|---|
| D1-P1 `.wslconfig` 未安装 | **V4b 全组件压测（D8）**、M0.5 的资源实测结论 | 用户执行安装 + `wsl --shutdown`（会中断 WSL2） |
| D1-P2 GPU 直通未验证 | **V4 判据中"GPU 可直通"分支**，V1 的 GPU 可用性结论 | 安装通用 Linux 发行版后验证 `nvidia-smi` |
| D1-P3 TDengine 授权未查证 | **V3 接入方案（D4–D5）**、M0.3 的时序路线结论 | 完成查证；不通过则启动自研解码器降级评估（≤2 天） |

---

## 六、M0.1 判定

| M0.1 通过条件 | 达成情况 |
|---|---|
| `env-baseline-v1.md` 字段完整（OS/Docker/WSL2/GPU/CUDA/Python/Node/各镜像与模型 digest） | ✅ 已完成采集（8 镜像 + 2 模型 digest）；但 **WSL2 段落记录的是"未配置状态"**，T1.1 落地后须升版 |
| `schemas/tools_v1.json` 落盘并标注 v1 | ✅ 已完成（5 工具冻结） |
| `p1-spec-data-sources.md` 含兜底路线（默认自编模拟数据） | ✅ 已完成 |
| `prj-template-experiment-log.md` 可用 | ✅ 已完成 |
| TDengine 授权结论已出（可用 / 需降级） | ❌ **未出**，T1.9 待查证 → ✅ **已闭环（2026-09-24，见 `reports/p0-report-v3-ingest-license.md`）：需降级（OSS + 自研解码器 ≤2 天），授权不阻塞** |
| （T1.1）`.wslconfig` 生效、`docker info` 确认内存上限 | ⚠️ **部分完成**：方案与回滚就绪，安装动作未执行 → ✅ **已闭环（2026-09-24）：安装并核验 ≈20GB/10vCPU（ISS-007，见 `env/env-baseline-v2.md`）** |

### 判定结论

> **M0.1 = 条件通过（Conditional Pass，本快照,2026-09-24 采集当下）**
>
> **采集时条件（两个缺口，均已随后闭环）**：
> 1. **T1.1 安装动作未执行** —— `%UserProfile%\.wslconfig` 实测不存在，Docker 仍为 15.51GB；须完成安装并用 `docker info` 核对至 ≈20GB / 10 vCPU。→ **已于 2026-09-24 安装核验 ≈20GB/10 vCPU 闭环（ISS-007）**。
> 2. **T1.9 授权结论未出** —— TDengine 社区版 Sparkplug B 接入边界待查证；不通过即启动降级评估。→ **已于 2026-09-24 定稿 = 需降级（OSS + 自研解码器 ≤2 天），授权不阻塞**。
>
> 除上述两项外，M0.1 其余条件（环境基线字段、Schema v1 冻结、数据来源清单含兜底、实验登记模板）**均已就绪**。
>
> ⚠️ 依据"顺序不可跳"铁律：**T1.1 未落地前，V4b 压测与 24GB 门禁判据均不具备有效性**，不得据此下任何放行结论。—— 两个缺口均已闭环，**本段为采集当下快照**；M0.1 最终结论由 `reports/p0-gate-review.md` §5.2 裁决为「✅ 达成（2026-09-29）」，此历史快照不追改。

---

## 修订记录

| 日期 | 修订人 | 原因 | 影响范围 |
|---|---|---|---|
| D1 | 单人（本人） | 初始建立 | — |
| 2026-09-29 | 单人（本人） | **M0.1 收尾追认**：§六 两个缺口（T1.1 `.wslconfig`、T1.9 授权）均已随后闭环（2026-09-24）；原「条件通过」判定为采集当下快照，**不追改历史**；M0.1 最终结论由 `reports/p0-gate-review.md` §5.2 裁决为「✅ 达成（2026-09-29）」。本文补追认标注与修订记录，保证可追溯 | §六 |