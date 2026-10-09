# 云侧工业 IoT 诊断 Agent 系统（auscult）

> 主场景：**离心泵驱动端轴承振动异常诊断**
> 当前阶段：**Phase 0（技术验证与范围锁定）已完成，M0.6 门禁已放行（2026-10-08）**；Phase 1 计划就绪，可启动
> 环境唯一事实源：`env/env-baseline-v2.md` ｜ 版本唯一事实源：`docs/prj-ledger-version-lock.md`

## 这是什么

一个**云侧、本地优先**的工业设备智能诊断 Agent：把「时序遥测 + 设备知识 + 图谱关系 + 维修历史」四类证据汇聚给 LLM，
自动完成 **告警 → 诊断推理 → 证据引用 → 报告生成 → 高风险人工审核** 的闭环。

核心设计取向（详见 `docs/p0-spec-scope-mvp.md`）：

- **证据驱动**：每条结论必须带 `EvidenceItem`，无来源不出结论；
- **本地优先**：LLM 推理走宿主 Ollama（`127.0.0.1:11434`），容器只承载 DB / 存储；
- **判据前置**：任何验证项开跑前，Pass / 中间区间 / No-Go 必须先定稿；
- **降级必带代价**：替代方案必须标注对 `Recall@5` 与 `P95` 的影响；
- **不编造数字**：未实测项写 `【待实测填入】`；
- **可复现**：组件 / 模型一律 digest 锁定，模拟数据固定 seed + `synthetic: true`。

## 当前状态速览

| 验证项 | 判定 | 关键数字 |
|---|---|---|
| V1 LLM 工具调用 | **Pass**（M0.2 达成；2026-10-08 H22 同日多轮聚合口径裁定） | 3 轮同日聚合（225 样本）：单工具 **92.6%** / 参数校验 100% / 多工具 **75.0%** / 多轮 100% / 拒止 100% / 澄清 100% → **整体 Pass**（合并首次成功率 **0.9422**）；⚠️ 残余风险：单轮口径仍不稳、多工具档余量 5.0pp、结论依赖 provider 版本（`ISS-028`） |
| V2 混合检索 | **Pass** | 混合 `Recall@5` 0.91 |
| V3 时序接入 | **封板定稿**（决策3，2026-09-29） | 四类边界 4/4；聚合 P95 ≈26.2 ms；解码器吞吐 P1 |
| V4a 环境采集 | **Pass** | env 三件套 |
| V4b 资源实测 | **Pass**（2026-09-29 干净机重测） | 宿主峰值 17.89 GB ≤ 24 GB 门禁（历史 26.38GB 中间区间口径保留） |
| V5 checkpoint | **Pass**（M0.4 达成） | 重复落库 0 次；296 KB/thread |
| V6 / V7 数据 / 评测集 | **结构 Pass** | 模拟数据兜底；单人标注 |

> **过闸裁决（今日权威）**：`reports/p0-gate-m02-verdict-2026-10-08.md` ｜ 门禁合集与决策：`reports/p0-gate-review.md`（决策34）
> 历史全景快照（🟡 均已被取代，仅供审计）：`reports/p0-summary-project-2026-09-29.md`、`reports/p0-summary-project-2026-09-28.md`、`reports/p0-audit-status-2026-10-07.md`

## 目录结构

```
auscult/
├─ .gitignore     忽略 env/cloud.json（含 API key）、__pycache__/、*.pyc、.venv/
├─ README.md      本文件
├─ CHANGELOG.md   变更日志（以验证项 / 里程碑为粒度）
├─ requirements.txt  Python 依赖锁（版本唯一来源 docs/prj-ledger-version-lock.md）
├─ plan/          7 份（命名规则见 docs/prj-spec-document-standard.md）
│                 🟢 唯一待执行：p1-plan-detailed.md（Phase 1 数据接入与知识库构建，2026-10-08 已生效）
│                 🟡 已终结留档：p0-plan-detailed-d1-d10 / p1-plan-v4b-cleanrm（已兑现）/
│                            p0-design-m02-hybrid-form / p0-design-v1-breakthrough-paths /
│                            p0-design-refusal-gate-decoupling（已落地为代码）/ p0-review-schema-v2
├─ docs/          16 份治理与规范文档（判据/台账/版本锁/范围/移交/决策/模板/**命名规范**…）
│                 🟢 活文档：p0-spec-gate-criteria ｜ prj-ledger-{known-issues,risk-register,version-lock}
│                            prj-spec-{labeling,review-lifecycle,schema-mapping,document-standard}
│                            prj-template-experiment-log ｜ p0-spec-scope-mvp ｜ p0-checklist-daily ｜ p0-handover-p1
│                 🟡 时点记录：p0-decision-model-role（分工决策，含 No-Go 时点表述）
├─ reports/       25 份 + daily/（README + D1-status）——索引与逐项状态见 reports/README.md §一
│                 ★ 权威：p0-gate-m02-verdict-2026-10-08（过闸裁决）、p0-gate-review（门禁合集·决策34）
│                 五项验证：p0-report-v1-tool-call 🟡 / v2-hybrid-retrieval / v3-ingest-license / v4b-resources / v5-checkpoint
│                 V1 口径复审：p0-review-v1-criteria-r2 / r3 / r4（**rN = 文件序号，不等于复审轮次**）
│                 专项与分析：p0-report-v1-cases-revision-2026-10-05 / p0-analysis-iss036-tier-split-2026-10-06 /
│                            p0-audit-v1-refusal-2026-10-06 / p0-audit-v1-single-tool-tier-2026-10-07
│                 状态审计：p0-audit-status-2026-09-30 / -10-05 / -10-07 / p0-audit-doc-sync-2026-10-08
│                 工程侧：p0-report-regression-suite-2026-10-06 / p0-report-vcs-baseline-2026-10-06
│                 总结快照：p0-summary-project-2026-09-28 / -09-29 / p0-summary-phase0-2026-09-30
│                 收尾留档：p0-gate-closeout-2026-10-07（🟡 当时判「M0.6 不放行」，已被 10-08 取代）
├─ schemas/       **tools_v4.json（当前基线，含测点目录）** ｜ tools_v1.json（FROZEN，5 工具）
│                 tools_v2.json / tools_v3.json（留档）｜ tools_v5.json（H3 实验版，❌ 否决未采纳）
├─ protos/        sparkplug_b.proto + 生成的 PB 类（sparkplug_b_pb2.py、__init__.py）
├─ configs/       decoder_schema_mapping.json / mosquitto.conf / redis.conf
├─ docker/        compose.base.yml / compose.ingest.yml / compose.v2.yml / compose.v4b-iso.yml / Dockerfile.decoder
├─ scripts/       22 个 Python 执行器 + 2 个 PowerShell（其中 16 个含 --selftest）
├─ tests/         回归测试（pytest，**176 用例 / 8 个 test_*.py**；离线运行，见 ISS-030 / ISS-031 / ISS-037）
│                 ✅ pytest 已锁 `9.1.1`（requirements.txt + 版本锁 §二.2.10，2026-10-08 补锁）
├─ evals/         golden_set_v1(50) / v1_cases(20，ISS-029 修订版) / v2_cases(25) / v3_cases(25) / r4_cases(20) /
│                 v1_refusal_transfer_v1(无泄漏迁移集) / v1_adversarial_v1(自建对抗集) / probe-v1-004 / corpora_v1/corpus_100
│                 原件归档：v1_cases-pre-2026-10-05 / -10-06、v1_refusal_transfer_v1-pre-2026-10-06
├─ experiments/   v1 / v2 / v3 / v4b / v5 / r4 原始实测数据（raw/ 135 文件，只增不改、**文档整理亦不改写**）
│                 + **30 份 EXP-*.md 实验登记**（另有 7 份记录位于 `raw/` 内、随原始数据留档；原 `plans/` 已迁至 `plan/p1-plan-v4b-cleanrm.md`）
├─ env/           env-baseline-v2.md（+v1 留档）/ hardware.json（+v1 留档）/ ports.md / cloud.json
│                 / wslconfig.proposed / wslconfig.bak
├─ archive/       非项目技术产物归档（personal/ 3 份求职素材，2026-10-08 自 reports/ 移出）—— 见 archive/README.md
└─ prompts/       tool_call_prompt_v1.md（**评测活动版本**）/ v2.md（⛔ 含测试集泄漏，禁用于评测）/ 
                  v3.md（未采纳，备查）/ v4.md（⭐ 当前最优候选）/ v5.md（实验版未采纳）/ refusal_gate_v1.md（H15 前置门，**零示例**）/
                  tool_call_step_prompt_v1.md / r4_prompt_v1.md
```

> **整理说明（2026-09-30）**：清理字节码缓存与空目录、修正 1 处误命名数据文件、移除 1 个零引用的字节相同副本 → `reports/p0-audit-status-2026-09-30.md`。
> **整理说明（2026-10-08）**：**全量文档同步与命名规范落地** —— 48 份文件改名/搬运、约 1737 处引用改写、22 份历史文档加「历史留痕」横幅、活文档的过期判定与计数逐一更正；
> 命名规则与旧名→新名映射的唯一入口 = **`docs/prj-spec-document-standard.md`**；核查结果与残留清单见 `reports/p0-audit-doc-sync-2026-10-08.md`。

## 快速开始

```powershell
# 1) 依赖（版本见 requirements.txt，来源 docs/prj-ledger-version-lock.md）
uv pip install -r requirements.txt

# 2) 离线自检（不联网、不需容器；22 个 Python 脚本中 **16 个**含 --selftest，全部应 exit 0）
foreach ($s in 'llm_adapter','judge_tools','gbnf_grammar','param_normalizer','run_v1',
               'run_cloud_baseline','run_v2','self_decoder','spb_simulator','run_v5',
               'run_r4','judge_r4','gate_rules','refusal_gate','run_e2e','aggregate_runs') {
    python "scripts/$s.py" --selftest
}

# 3) 回归测试（离线、秒级；**176 用例**：llm_adapter / judge_tools / param_normalizer / run_v5 / run_v1 /
#    gate_rules / refusal_gate / run_e2e / aggregate_runs / 用例集完整性。
#    防「已修复缺陷复发」，见 docs/prj-ledger-known-issues.md ISS-030 / ISS-031 / ISS-037）
#    注意：需 pytest（当前未登记进 requirements.txt，本机实跑于宿主 Python 3.12）
python -m pytest tests/ -q

# 4) 基础设施（注意：compose.base.yml 与 compose.ingest.yml 端口冲突，不得同时启动）
docker compose -f docker/compose.base.yml up -d          # Milvus/PG/Redis/Neo4j/(tdengine profile)
docker compose -f docker/compose.ingest.yml up -d        # Mosquitto + TDengine + 自研解码器

# 5) V3 时序链路（模拟器是验证工具，不进 compose）
python scripts/spb_simulator.py --scenario birth,new_metric,rebirth,offline
python scripts/run_v3_alert.py --threshold 4.5 --window-min 5 --must-windows 3
```

## 常用入口

| 目的 | 命令 |
|---|---|
| 回归测试（改代码后必跑） | `python -m pytest tests/ -q` |
| V1 工具调用评测 | `python scripts/run_v1.py --constrain --tag constrained-decoding ...` |
| V1 判分 | `python scripts/judge_tools.py --raw experiments/v1/raw/EXP-V1-003.jsonl --out experiments/v1/summary-EXP-V1-003.csv` |
| 云端上界校准 | `python scripts/run_cloud_baseline.py --constrain` |
| V2 混合检索对比 | `python scripts/run_v2.py --routes milvus,pgvector --dsn postgresql://root:123456@127.0.0.1:5433/auscult_v2` |
| V5 checkpoint 验证 | `python scripts/run_v5.py --step t5.3 --resume <thread_id> --checkpointer postgres` |
| R-4 证据归纳执行 | `python scripts/run_r4.py` |
| R-4 证据归纳判分 | `python scripts/judge_r4.py --raw experiments/r4/raw/EXP-R4-001.jsonl --out experiments/r4/summary-EXP-R4-001.csv` |
| **M0.2 权威入口**：端到端（规则门 → 云端工具调用） | `python scripts/run_e2e.py --cases evals/v1_cases.jsonl --cases evals/v1_refusal_transfer_v1.jsonl --repeat 3 --out <raw.jsonl>` |
| 同日多轮聚合裁决（§3.1.3） | `python scripts/aggregate_runs.py --raw R1.jsonl --raw R2.jsonl --raw R3.jsonl` |
| 纯规则前置门（H18b，零 LLM 调用） | `python scripts/gate_rules.py --selftest` / 由 `run_e2e.py` 内置调用 |
| 本地 7B 前置门（R-1，H15 原方案） | `python scripts/refusal_gate.py --models qwen2.5:7b --cases evals/v1_cases.jsonl --repeat 3 --out experiments/v1/raw/EXP-M02-026.jsonl` |

## 迭代纪律（改动前必读）

1. **Schema 冻结**：`schemas/tools_v1.json` 的 `change_policy` 要求任何修改必须升版为 `tools_v2.json`，
   否则 V1 全部结论作废；同时同步 `docs/prj-ledger-version-lock.md` §2.6。
2. **组件 / 模型**：只写 digest，禁止裸 tag 与 `latest`（纪律 1）；变更即升版（纪律 2）。
3. **实验登记**：按 `docs/prj-template-experiment-log.md` 记录 `experiment_id` / digest / seed / prompt 版本 / commit，
   原始数据落 `experiments/**/raw/`（只增不改）。
4. **已知缺陷**：改动前先查 `docs/prj-ledger-known-issues.md`（**ISS-001 – ISS-037**）与 `docs/prj-ledger-risk-register.md`。
5. **变更记录**：见 `CHANGELOG.md`。
6. **文档命名**：新增/改名文档按 `docs/prj-spec-document-standard.md`（`<阶段>-<类型>-<主题>[-<日期>]`，ASCII kebab），并同步登记 `reports/README.md` §一 与本文件目录结构；`prompts/`、`schemas/`、`evals/`、`experiments/**/raw/` 为**不可改写区**（冻结实验输入）。

## 明确不做（Won't）

多租户｜模型微调（预留 LoRA 接口）｜复杂 GraphRAG 多跳（>2 跳）｜移动端｜
真实 Modbus / OPC UA 直连（预留边缘网关转 MQTT 接口）｜
**自动执行维修动作（永久安全刚性）**。
