# P5-W1 评测体系硬化汇总报告（M5.1）

> **日期**：2026-10-09 ｜ **阶段**：Phase 5 / W1（D1–D5） ｜ **出口**：**M5.1 全量指标报告 + Kappa 结论**
> **评测口径**：`evals/m2_acc_set.jsonl`（12 题配套集，P5-κ 修订 v1.1）｜ RRF-only（D7 消融结论）｜ 全本地（Ollama qwen2.5:7b + deepseek-r1:7b + BGE-M3）
> **总声明**：所有指标基于**模拟数据**（模拟语料 + 本地 7B 生成/判定），仅作本地验证初步结论，不代表生产级评测结果；golden 50 题待扩语料后重评（Phase 2 收口约束维持）。

---

## 一、§7.1 十二项指标对照表

| # | 指标 | 判据 | 实测 | 判定 | 数据源 |
|---|---|---|---|---|---|
| 1 | Recall@5 | ≥ 85% | **1.0** | ✅ | D3（`experiments/p2/m2/meta-m2.json`） |
| 2 | MRR | ≥ 0.75 | **0.7986** | ✅ | D3 同上 |
| 3 | NDCG@5 | 报告值 | **1.0** | — | D3 同上 |
| 4 | 引用正确率 | ≥ 90% | **0.9861**（context_precision 代理口径） | ✅* | D1 RAGAS |
| 5 | 幻觉率 | ≤ 10% | **0.0**（A=10/B=2/C=0） | ✅ | D4（`meta-hallucination.json`） |
| 6 | 工具调用首次成功率 | ≥ 90% | **1.0**（12/12） | ✅ | D5（检索执行口径） |
| 7 | P95 检索 | < 800ms | **159.4ms**（eval_m2）/ 111.7ms（RAGAS RAW） | ✅ | D3 / D5 |
| 8 | P95 端到端（本地路径） | < 3s | **9248.8ms** | ❌ | D5（处置见 §四） |
| 9 | 置信度 ECE | ≤ 0.10 | **0.0**（acc=0.75） | ✅* | D5（局限见 §三.3） |
| 10 | 高风险审核覆盖率 | 100% | D16 自测 8/8（`always_interrupt_when_high`） | ✅* | W4-D12 正式回归待做 |
| 11 | Cohen's Kappa | ≥ 0.7 | **0.8344** | ✅ | D2（`reports/p5-kappa.md`） |
| 12 | 资源峰值 | ≤ 24GB | 待测 | ☐ | W5-D14 压测 |

> ✅* = 达成但带口径局限声明（见对应小节）。#4/#10/#12 属 W2–W5 正式回归范围，W1 先以现有证据收口。

## 二、分项结果

### 2.1 D1 RAGAS（judge = 本地 qwen2.5:7b，Q3=A）

| 指标 | 值 |
|---|---|
| faithfulness | 0.9375 |
| answer_relevancy | 0.8754 |
| context_precision | 0.9861 |
| context_recall | 1.0 |

留痕：`experiments/p5/w1/RAW-ragas.jsonl` + `meta-ragas.json`（465.2s，12 题 × 4 指标，judge/embeddings 全本地）。

### 2.2 D2 标注一致性（Cohen's Kappa）

- **κ = 0.8344 ≥ 0.70 可接受**（Po=0.9167 / Pe=0.4967；a1b1=28，a1b0=0，a0b1=5，a0b0=27）。
- 首测 0.3396 触发标注规范修订（等价块 L3 补标 `relevant_chunk_ids_full`），重测达成；全过程留痕。
- **局限**：标注人 B 为本地 LLM 非真人，不代表双人真人标注一致性。
- 详见 `reports/p5-kappa.md`；规范修订记录 `docs/prj-spec-labeling.md` §十一。

### 2.3 D3 检索指标复测（RRF-only）

- Recall@5=1.0 / MRR=0.7986 / NDCG@5=1.0 / P50=120ms / P95=159.4ms（12 题，`--no-rerank`）。
- 留痕：`experiments/p2/m2/RAW-m2-metrics.jsonl` + `meta-m2.json`（2026-10-09 23:04 复测）。

### 2.4 D4 幻觉率（3 级评分）

- **幻觉率 = 0.0%（判据 ≤10% Pass）**；B 级警告 2 条（m2a-005/012），根因均为**语料换油周期数值冲突**（2500h/3000h/3500h 跨型号并存），非模型编造。
- 复核策略：首判 C 触发逐句核对式二次判定（本轮无需触发）。
- 详见 `reports/p5-hallucination.md`。

### 2.5 D5 端到端指标 + ECE

| 项 | 实测 | 判据 | 判定 |
|---|---|---|---|
| P95 检索 | 111.7ms（RAGAS RAW 口径） | <800ms | ✅ |
| P95 端到端（本地） | **9248.8ms** | <3s | ❌ |
| 工具首次成功率 | 1.0（12/12，检索执行口径：非降级且 ≥1 命中） | ≥90% | ✅ |
| ECE（5 桶，n=12） | 0.0（acc=0.75） | ≤0.10 | ✅* |

**ECE 局限（必须声明）**：生成模型自评置信度**恒为 0.75（零方差）**，恰与实测准确率 0.75 相等 → ECE=0 属**巧合性校准，无区分度**。正确性判定 12 题中 9 对 3 错（m2a-003 生成不完整；m2a-005/012 语料数值冲突同源）。**后续动作**：D8 校准框架（Platt scaling）需先解决自评置信度无方差问题（改用 logit 置信度或多采样一致性），列入 P6 候选。

**引用正确率口径声明**：W1 以 RAGAS context_precision（0.9861）作代理；严格口径（诊断链路 RootCause.citations 抽检）随 W4 安全回归补测。

## 三、P95 端到端未达标处置（§7.2 中间区间条款）

| 项 | 内容 |
|---|---|
| 实测 | P50=1539.6ms（<3s ✓），P95=**9248.8ms**（>3s ✗），均值 4.4s |
| 瓶颈归因 | 生成阶段占 95%+（qwen2.5:7b 自由文本 200 字生成 1.5–9s 波动）；检索 P95 仅 159.4ms。同链路 JSON 短输出实测 1.1–3.1s（`RAW-e2e.jsonl` gen_latency），证明**输出长度/格式是首要变量** |
| 处置（§7.2「3–4s 中间区间」超出，按超限记录） | ① 已有约束：回答限 200 字；② 优化路径（P6 候选）：流式输出（首 token P95 达标口径）、max_tokens 收紧、结构化输出（JSON 格式实测提速 3–5 倍）、高频问答缓存 |
| 口径澄清 | 「P95 端到端（本地路径）<3s」在 Phase 2 D11 收口的检索 API P95=86ms 已达成；本处为**知识问答含生成全链路**口径，两者分列不混用 |

## 四、数据留痕清单

| 文件 | 内容 |
|---|---|
| `experiments/p5/w1/RAW-ragas.jsonl` + `meta-ragas.json` | D1 RAGAS 逐题 + 汇总 |
| `experiments/p5/w1/RAW-kappa.jsonl` + `meta-kappa.json` | D2 κ 60 对标注 |
| `experiments/p2/m2/RAW-m2-metrics.jsonl` + `meta-m2.json` | D3 检索复测 |
| `experiments/p5/w1/RAW-hallucination.jsonl` + `meta-hallucination.json` | D4 幻觉评分 |
| `experiments/p5/w1/RAW-e2e.jsonl` + `meta-e2e.json` | D5 延迟/ECE 逐题 |
| `scripts/eval_ragas.py` / `eval_kappa.py` / `eval_hallucination.py` / `eval_e2e.py` | 四个可复跑评测脚本 |
| `reports/p5-kappa.md` / `reports/p5-hallucination.md` | D2/D4 单项报告 |

## 五、结论

1. **M5.1 达成**：全量指标报告 + Kappa 结论（κ=0.8344）已产出；十二项中 8 项实测达标、1 项未达标（P95 端到端，处置与优化路径已记录）、1 项代理口径（引用正确率）、1 项引用既有证据（高风险审核）、1 项待 W5。
2. W2 起转入可观测性硬化（Prometheus/Grafana/日志/告警）。
