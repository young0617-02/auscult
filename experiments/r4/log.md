# R-4 实验登记（EXP-R4-<序号>）

> 对应 `docs/gate-criteria.md` §3.7（R4）、`docs/known-issues.md` ISS-014
> 登记规范：`docs/experiment-log-template.md` §六（P1 专项用 `EXP-R4-<序号>`）

## EXP-R4-001 — 本地证据归纳/诊断 首次成功率调研

**purpose**：验证 R-4「读证据→写根因/结论→带 `evidence_refs` 引用」在本地 7B 模型的可用性，按 §3.7 六维判据判分（幻觉红线=0）。

**环境与版本**
- `env_baseline_version`：env-baseline-v2
- 生成模型：`qwen2.5:7b`（Ollama 0.34.2，`D:\.ollama`）
- 向量模型：不涉及（R-4 为纯生成型归纳，无 embedding 依赖）
- `seed=42`、`num_ctx=8192`、`temperature=0.0`
- `prompt_version`：`prompts/r4_prompt_v1.md`
- `code_commit`：启用自动 git_commit（run_r4.py 每次实验后自动提交 raw）
- `raw_data_path`：`experiments/r4/raw/EXP-R4-001.jsonl`

**结果（81 响应 = 20 用例 × 3 次 + 断点续跑，判分见 `summary-EXP-R4-001.csv`）**

| 维度 | 线 | 实测（分子/分母） | 档位 |
|---|---|---|---|
| 结构可解析率 | ≥0.90 | 78/81 = 0.96 | Pass |
| 引用忠实（幻觉率）【红线】 | =0 | 81/81 = 1.0；幻觉 0.0 | Pass |
| 证据覆盖率 | ≥0.70 | 78/81 = 0.96 | Pass |
| 根因结论正确率 | ≥0.70 | 75/81 = 0.93 | Pass |
| severity 匹配率 | ≥0.70 | 72/81 = 0.89 | Pass |
| 建议动作非空率 | ≥0.90 | 78/81 = 0.96 | Pass |
| **整体（最差档位）** | — | — | **Pass** |

辅助：首次成功率 0.741、重试后 1.0、平均延迟 3.96s、P95 5.08s。

**conclusion**：R-4 本地证据归纳/诊断六维全 Pass，幻觉红线 = 0。ISS-014 闭环，role-decision §6.1 R-4 由「未验证」升为「Pass」。

**anomalies**：3 次结构退化、3 次证据漏引、6 次根因错、9 次 severity 错 —— 均不影响整体 Pass；首次成功率未达 100% 为首次通过但可经重试矫正，判据以维度率为准（§3.7）。

**reproduce_cmd**
```powershell
python scripts/run_r4.py --models qwen2.5:7b --repeat 3 --seed 42 --num-ctx 8192 --temperature 0.0 --prompt prompts/r4_prompt_v1.md --out experiments/r4/raw/EXP-R4-001.jsonl
python scripts/judge_r4.py --raw experiments/r4/raw/EXP-R4-001.jsonl --out experiments/r4/summary-EXP-R4-001.csv --detail-out experiments/r4/detail-EXP-R4-001.csv
```