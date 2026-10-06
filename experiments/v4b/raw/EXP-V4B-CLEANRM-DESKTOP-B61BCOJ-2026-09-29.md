# 实验记录：EXP-V4B-CLEANRM-<WORKSTATION>-2026-09-29

> V4b 专用干净机重测（升 Pass 前置）真实测量结果
> 对应计划：`experiments/plans/P1-V4B-CLEANRM.md`；判据 `docs/gate-criteria.md` §3.1.5
> 执行机器：`<WORKSTATION>`（本机，关停 CodeBuddy/QQ/微信等非基线应用后作为实测主机）
> **结论：宿主总占用峰值 17.89GB ≤ 24GB → Pass**（真实实测，非估算）

## 一、测量条件

| 项 | 说明 |
|---|---|
| 主机 | <WORKSTATION>，OS 总内存 31.8GB |
| 基线（启动前） | **14.57GB**（关停 CodeBuddy CN/QQ/Weixin 后；含 Trae 对话宿主 ≈2.6GB + msedge ≈0.5GB + Windows OS 基线） |
| 组件 | `docker compose -f docker/compose.base.yml up -d etcd minio milvus postgres redis neo4j`（6 容器全部 healthy） |
| LLM | Ollama 宿主 `qwen2.5:7b` 触发常驻加载（4.7GB） |
| 采样 | 1 分钟 × 10 次，取宿主已用内存峰值 |

> **口径修正说明（诚实声明）**：实测主机为本工作对话宿主，Trae CN（聊天进程宿主）与浏览器为**本职工作必需工具，无法关停**，故基线较文档「仅 OS + Docker」多约 3GB。本次 Pass 因此为**保守/上偏**——纯 OS+Docker 基线只会更低，不影响 Pass 判定有效性。

## 二、实测数据（宿主已用 GB）

| 样本 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| 值 | 17.81 | 17.83 | 17.85 | 17.85 | **17.89** | 17.21 | 17.16 | 17.14 | 17.18 | 17.16 |

- **峰值 = 17.89GB**（样本1-5，全 6 容器 + qwen2.5:7b 常驻期）
- 平均 = 17.51GB
- 样本6-10 略降（7B keep-alive 到期 / 内存压缩）——峰值以样本1-5 为准

## 三、判定（`gate-criteria.md` §3.1.5）

| 口径 B 宿主总占用峰值 | 判据 | 实测 | 判定 |
|---|---|---|---|
| ≤ 24GB | Pass | **17.89GB** | ✅ **Pass** |

**双重校验**：极端补加完整 deepseek-r1:7b（+~4.7GB）→ ≈22.6GB 仍 <24GB，Pass 成立且留有余量。

## 四、结论

V4b 由「中间区间（26.38GB 旧口径）」升为 **Pass（实测 17.89GB）**；M0.5 门禁前置达成 → M0.6 未放行原因收窄为**仅剩 M0.2**（V1 R-2/R-3 工具调用 No-Go 挂起）。

## 五、纪律符合性

- 真实采值、未估算；基线口径偏差已在文上显式声明（不冒充纯干净机）。
- 未覆盖历史实验 `EXP-V4B-ISO-2026-09-28`、未改动旧口径 26.38GB 历史记录。
- 复现命令：见 `experiments/plans/P1-V4B-CLEANRM.md` §三。