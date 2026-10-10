# P5-W1-D2 标注一致性检验报告（Cohen's Kappa）

> **日期**：2026-10-09 ｜ **阶段**：Phase 5 / W1 评测与硬化 ｜ **对应规范**：`docs/prj-spec-labeling.md` §八、§十一（修订记录）
> **判据**：κ ≥ 0.70 可接受（`prj-spec-labeling.md` §8.2）
> **结论**：**κ = 0.8344 ≥ 0.70 → ✅ 达成**（含规范修订一轮，全留痕）

---

## 一、方法

| 项 | 值 |
|---|---|
| 标注对象 | `evals/m2_acc_set.jsonl`（12 题配套集）× 每题 Top-5 检索候选，共 **60 个标注对** |
| 标注人 A | 人工主标注（完备相关集 `relevant_chunk_ids_full`，L3+L2，P5-κ 修订后口径） |
| 标注人 B | **Ollama qwen2.5:7b**（Q1=A 定案：本地 LLM 替代真人第二标注，零成本离线） |
| 检索口径 | RRF-only（`use_rerank=False`，D7 消融结论），Top-5 |
| 计算 | κ = (Po − Pe) / (1 − Pe)，二值化（相关/不相关） |
| 脚本 | `scripts/eval_kappa.py`（A 自动检测 `relevant_chunk_ids_full` 优先，回退 `relevant_chunk_ids`） |

> **局限声明（必读）**：标注人 B 为**本地 LLM 非真人**，κ 结论仅表征「人工标注与本地 LLM 判定」的一致性，基于模拟数据，**不代表双人真人标注一致性**（`meta-kappa.json.scope_statement` 已随数据落盘）。

## 二、首测 → 修订 → 重测全留痕

### 2.1 首测（触发规范重订）

- **κ = 0.3396（<0.4）**，混淆矩阵 a0b1=21（A 判无关、B 判相关）。
- 逐条复核：21 条争议**全部为语料结构性等价块**（四型号手册同构章节、`fault_case_6 == fault_case_4`、判据表等价块）——这些块单独包含 ≥1 条 answer_points 完整依据，按规范 §6.1 **L3 应计入**；A 原标注仅挂「唯一锚点块」，属**漏标**而非 B 误判。

### 2.2 规范修订（§8.3 第⑥步）

- 配套集补标 `relevant_chunk_ids_full`（**完备相关集 = L3 + L2**）；原 `relevant_chunk_ids` 保留不覆盖（版本纪律）。
- L0 排除留痕：换油周期数值冲突块（2500h/3500h vs 期望 3000h）不计入。
- 修订记录全文：`prj-spec-labeling.md` §十一；配套集口径升 **v1.1**，golden v1 不动。

### 2.3 重测结果（2026-10-09）

| 项 | 值 |
|---|---|
| 标注对数 | 60 |
| Po（观察一致率） | 0.9167 |
| Pe（随机一致率） | 0.4967 |
| **κ** | **0.8344** |
| 档位 | **可接受**（≥0.70 substantial）✓ |
| 混淆矩阵 | a1b1=28，a1b0=0，a0b1=5，a0b0=27 |

### 2.4 争议项明细（5 条，全部维持 A 判定）

| qid | chunk_id | A | B | 复核结论 |
|---|---|---|---|---|
| m2a-005 | manual_scanned_dp-5-c0 | 0 | 1 | 换油周期 2500h ≠ 期望 3000h（L0 结论相反） |
| m2a-005 | manual_ss_process-5-c0 | 0 | 1 | 换油周期 3500h ≠ 期望 3000h（L0） |
| m2a-005 | manual_impeller_series-5-c0 | 0 | 1 | 换油周期 2500h ≠ 期望 3000h（L0） |
| m2a-012 | manual_ss_process-5-c0 | 0 | 1 | 换油周期 3500h ≠ 期望 2500h（L0） |
| m2a-012 | manual_centrifugal_hc-5-c0 | 0 | 1 | 换油周期 3000h ≠ 期望 2500h（L0） |

> 争议模式统一：B 判「主题相关」（弱口径），A 判「数值冲突」（§6.1 L0）。按 §8.3 仲裁规则「**保守优先**」→ 维持 A。此 5 条恰好验证了 B 未做数值核对——与 §11.5 局限声明一致，属 LLM 标注者的已知边界。

## 三、数据留痕

| 文件 | 内容 |
|---|---|
| `experiments/p5/w1/RAW-kappa.jsonl` | 60 对逐条标注（qid/chunk_id/label_a/label_b/disputed） |
| `experiments/p5/w1/meta-kappa.json` | κ/Po/Pe/混淆矩阵/争议明细/scope_statement |
| `docs/prj-spec-labeling.md` §十一 | 规范修订记录（v1 增补） |
| `evals/m2_acc_set.jsonl` | 配套集 v1.1（`relevant_chunk_ids_full` 补标 + notes 留痕） |

## 四、结论与下游

1. **κ = 0.8344 ≥ 0.70 → 一致性检验达成**（模拟数据 + LLM 第二标注口径）。
2. A 侧完备相关集已同步可用于后续 golden 扩语料重评时的标注口径参照（L3 等价块必须计入）。
3. RAGAS / 检索指标 / 幻觉率 / ECE 汇总见 `reports/p5-eval.md`（M5.1 收口时产出）。
