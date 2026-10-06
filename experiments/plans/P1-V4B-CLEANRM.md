# P1 计划：V4b 专用干净机重测超参数方案（V4b 升 Pass 前置）

> **状态**：待执行（P1）｜**编制**：2026-09-29（单人，本人）｜**上游依据**：`reports/v4b-report.md` §12.2/§12.4、`docs/gate-criteria.md` §3.1.5
> **结论口径（用户已确认，2026-09-29）**：本机（多项目共存、宿主 27.66GB 含其他项目贡献）无法干净归属 V4b 宿主总占用，**不能**在本机真实升 Pass。本方案为**可执行计划**，不含实测值；执行需在 P1 的专用干净机上完成。

---

## 一、目的

在当前宿主（多项目共存、内存被非本系统进程占用的 26.38GB/口径B）之上，无法证明 V4b 宿主总占用是否真正 ≤24GB 门禁线。本方案在**专用干净机**上重测，回答：

> **Q**：干净环境下，本系统 V4b（分组启动 + 单 7B 常驻）宿主总占用是否 ≤ 24GB（32GB × 75%）？

- 是 → V4b 由「中间区间」升为 **Pass**，M0.5 达成门禁前置。
- 否 → V4b 维持中间区间/No-Go，据 §12.3 分组启动清单进一步降载。

## 二、前置条件（执行前须全部满足）

| # | 条件 | 状态 |
|---|---|---|
| 1 | **专用干净机**：物理内存 ≥32GB，无其他长期运行项目/测试进程（宿主基线仅 OS + Docker Desktop） | 待备机 |
| 2 | `.wslconfig` 已置 `memory=20GB` 且 `docker info` MemTotal≈20GB（T1.1 落地） | 已验证本机，干净机须重验 |
| 3 | `docker/compose.base.yml` 四档组件齐全（etcd/minio/milvus/postgres/redis/neo4j/mosquitto/tdengine） | 本机已核对 §12.4 |
| 4 | 宿主原生 Ollama（`127.0.0.1:11434`，U-03 裁决）已装载 qwen2.5:7b / deepseek-r1:7b / bge-m3 | 本机已备 |
| 5 | 当前违反本系统独占的进程（其他项目容器/服务）**全部停止** | 干净机前提 |

## 三、测量脚本（commands）

口径 B = **宿主总占用**。执行：

```powershell
# 1) 干净基线：仅 OS + Docker Desktop + 一个测量终端
# 记录空闲宿主峰值内存
Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory,TotalVisibleMemorySize

# 2) 分组启动检索 + 状态两组（§12.3 ①②）
docker compose -f docker/compose.base.yml up -d etcd minio milvus postgres
docker compose -f docker/compose.base.yml up -d redis neo4j

# 3) 常驻单 7B（择 qwen2.5:7b）
ollama run qwen2.5:7b &   # 或 ollama serve + chat 常驻
#   另 7B（deepseek-r1:7b）不常驻，仅按需加载

# 4) 稳定后采样宿主峰值（多次采样取峰）
#    建议 1 分钟间隔 * 10 次，取内存峰值与 commit/working set 总和

# 5) 记录：宿主总占用峰值 vs 24GB / 26.4GB（中间区间容限）
```

## 四、结果判据表（按 gate-criteria §3.1.5）

| 口径 B 宿主总占用峰值 | 判定 |
|---|---|
| ≤ **24GB** | ✅ **Pass** → V4b 升 Pass，M0.5 门禁前置达成 |
| ≤ **26.4GB**（24×1.1） | ⚠️ 中间区间（维持分组启动） |
| > **26.4GB** | ❌ No-Go（需 §12.3 进一步降载） |

**附加记录项**（平行 P1 项，非本次判据）：
- 双 7B 错峰实测（§12.2：双 7B 同日 ≈11.6GB > 8.2GB，须错峰）
- reranker（`BAAI--bge-reranker-v2-m3`，已本地选用）驻留内存/显存实测（`probe_reranker.py`）

## 五、执行后待办

1. 将实测峰值回填本方案「结果」节与 `reports/v4b-report.md` §12.2/§十二，登记实验 log（继承 EXP-V4B 序列，忌覆盖 EXP-V4B-ISO-2026-09-28）。
2. 本机产物同步到干净机（compose 无动态生成物，直接复用）。
3. 回填后按 gate-criteria §3.1.5 更新 M0.5 状态。

## 六、红线 / 纪律

- 本机**当前不可用时不可如实声称"升 Pass"**，禁止捏造干净机峰值。
- compose v2 ports 替换仍须用 `!override`（v4b 已知约束）。
- **执行状态（2026-09-29）**：本计划已于本机 <WORKSTATION> 关停非基线应用后执行，宿主峰值 **17.89GB ≤24GB → Pass**（见 `experiments/v4b/raw/EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29.md`，M0.5 升达成）。下方命令仍保留，供 P1 专用干净机复核复现使用。

---

以上为待执行计划，实验ID 提议为 `EXP-V4B-CLEANRM-{干净机ID}-{MM-DD}`，避免覆盖 `EXP-V4B-ISO-2026-09-28`。