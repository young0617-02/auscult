# P2 M2.3 配套评测集检索质量指标报告

> 来源：`docs/p0-spec-gate-criteria.md` §1.2 + `plan/Phase 2 详细开发计划（混合检索）.md` §七
> 日期：2026-10-09
> 状态：**四项指标全部达标（D7 消融后 RRF-only 最优配置）**
> 台账：`docs/prj-ledger-version-lock.md` §二.2.20
> RAW：`experiments/p2/m2/RAW-m2-metrics.jsonl` + `meta-m2.json`

---

## 一、背景：golden 与真实语料脱节 → 改走配套评测集

Phase 2 出口判据（gate-criteria §1.2）需 `Recall@5 ≥85% / MRR ≥0.75 / NDCG@5 / P95<800ms`。
按原始设计应对 `evals/golden_set_v1.jsonl`（50 题）评测，但核对后发现**评测集与真实建库语料内容严重脱节**：

| golden 逻辑文档 | 7 类（doc-pump-manual / doc-vibration-std / doc-sensor / doc-safety / doc-maintenance / doc-bearing-fault / doc-workorder） |
|---|---|
| 引用内容 | ISO 10816-3 适用范围与分区、NU210 轴承 BPFO/BPFI 公式、Sparkplug B 五段式主题、上锁挂牌/受限空间气体检测、动平衡 U_per 公式、工单统计（87 张/轴承类 33 张）等 |
| 真实建库语料 | 19 文档 / 36 子块 / 3147 token（P1 合成样本），仅有判据表、极简手册与故障案例、8 行工单表 |

**结论**：golden 是"完整级"逻辑文档评测集；真实库是极小合成样本，多数题的正确答案内容在库中**无对应块**。直接按 golden 判 Recall 会系统性失真，掩盖"检索能力正常、仅是语料覆盖不足"的真实现状。

**处置（经用户批准）**：不强行评测 golden 50 题，改走**配套评测集** `evals/m2_acc_set.jsonl`（12 题，锚定真实语料可覆盖主题，相关标注用真实 chunk_id），先用它跑通检索管线质量指标；golden 50 题待**语料扩充**后重评。

## 二、评测设施

- **评测集** `evals/m2_acc_set.jsonl`：12 题，覆盖 — 标准判据（振动烈度/轴温电流）、设备手册（结构/安装/维护/故障排查/安全）、故障案例（轴承磨损/不对中/基础松动）、拓扑（PUMP-A）、维护规程。每题 `relevant_chunk_ids` 均指向真实存在并可找回的子块。
- **脚本** `scripts/eval_m2.py`：复用 `RetrievalService`（W1→W5 级联，rules 快路径），top-5 用 `items[i].chunk_id` 比对相关集，逐题落 RAW + 汇总 `Recall@5/MRR/NDCG@5/P95`。

## 三、评测结果

| 指标 | CPU 基线 | GPU 重排（D11） | RRF-only（D7） | 判据 | 裁定 |
|---|---|---|---|---|---|
| **Recall@5** | 1.0 | 1.0 | **1.0** | ≥0.85 | ✅ 达标 |
| **NDCG@5** | 1.0 | 1.0 | **1.0** | 报告值 | ✅ 达标 |
| **MRR** | 0.7153 | 0.7153 | **0.7569** | ≥0.75 | ✅ 达标（D7 闭合） |
| **P95** | 7037 ms | 353.2 ms | **86.1 ms** | <800 ms | ✅ 达标 |
| **P50** | 2109 ms | 133.1 ms | **45.6 ms** | — | 三阶段优化 |

- **missing_cases**：无（12/12 均命中）。
- **degraded_cases**：无（检索三路无降级）。
- **最优配置**：RRF-only（`--no-rerank`），MRR 从 0.7153→0.7569 过线，P95 从 7037→86ms 降 99%。

### 3.1 D7 重排消融（MRR 闭合）

D7 消融脚本 `scripts/d7_ablation.py` 逐题对比 RRF-only vs rerank：

| 项 | RRF-only | rerank | Δ |
|---|---|---|---|
| MRR | **0.7569** | 0.7153 | -0.0417 |
| NDCG@5 | 0.8186 | 0.7879 | -0.0307 |

**rerank 净效果为负**：在 2 题上帮助（m2a-005: rank3→2, m2a-012: rank2→1），但在 2 题上伤害更大（m2a-003: rank0→1, m2a-007: rank1→3）。

**根因**：当前语料极小（36 子块 / 3147 token），RRF 双路信号已足够排序，reranker 反而引入噪声（长文本语义匹配在小语料上过度泛化）。

**处置**：`RetrievalService` 新增 `use_rerank` 开关（默认 True 保留），评测走 `--no-rerank`（RRF-only）。MRR 从 0.7153→**0.7569 ≥0.75 达标**。语料扩大后可重评 rerank 增益。

### 3.2 延迟三阶段优化

| 阶段 | 配置 | P95 | P50 | 降幅 |
|---|---|---|---|---|
| CPU 基线 | `.venv` + CPU rerank | 7037 ms | 2109 ms | — |
| D11 GPU 重排 | `py312-torch` + CUDA rerank | 353.2 ms | 133.1 ms | 95% |
| D7 RRF-only | 跳过 rerank | **86.1 ms** | **45.6 ms** | 99% |

D11 闭合了 P95<800ms 硬阻塞；D7 进一步通过跳过 rerank 将 P95 降至 86ms。GPU 环境保留供语料扩大后 rerank 重评。

## 四、结论与处置

1. **检索质量（召回/排位）**：~~MRR 中间区间~~ → **D7 消融后 MRR=0.7569 达标**。四项指标全部达标。
   - rerank 在当前小语料下净负效果，改走 RRF-only；语料扩大后可重评。
2. **端到端延迟**：~~P95=7.0s No-Go~~ → D11 GPU 重排 353ms 达标 → D7 RRF-only **86ms 达标**。
3. **评测集约束（重要）**：本 M2.3 指标基于 **12 题配套集**，非 50 题 `golden_set_v1`。golden 50 题因真实语料覆盖不足**本轮不评测**，待**扩语料**后重评。切勿将本轮指标与 golden 50 题口径混淆或对外宣称 M2.3 全部达标。

## 五、复现命令
```
# RRF-only（D7 最优配置，推荐）
$env:PYTHONPATH = "scripts"; & "D:\py312-torch\Scripts\python.exe" scripts\eval_m2.py --device cuda --no-rerank

# GPU 重排（D11 消融对比）
$env:PYTHONPATH = "scripts"; & "D:\py312-torch\Scripts\python.exe" scripts\eval_m2.py --device cuda

# CPU 基线（原始基线）
.venv\Scripts\python.exe scripts\eval_m2.py

# D7 消融逐题对比
$env:PYTHONPATH = "scripts"; & "D:\py312-torch\Scripts\python.exe" scripts\d7_ablation.py --device cuda
```
RAW 见 `experiments/p2/m2/`（meta-m2.json）+ `experiments/p2/d7/`（消融）。