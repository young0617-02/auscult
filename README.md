# 云侧工业 IoT 诊断 Agent 系统（auscult）

> 主场景：**离心泵驱动端轴承振动异常诊断**
> 当前阶段：**Phase 0（技术验证与范围锁定）已收口，M0.6 门禁未放行**；Phase 1 计划就绪待启动
> 环境唯一事实源：`env/env-baseline-v2.md` ｜ 版本唯一事实源：`docs/version-lock.md`

## 这是什么

一个**云侧、本地优先**的工业设备智能诊断 Agent：把「时序遥测 + 设备知识 + 图谱关系 + 维修历史」四类证据汇聚给 LLM，
自动完成 **告警 → 诊断推理 → 证据引用 → 报告生成 → 高风险人工审核** 的闭环。

核心设计取向（详见 `docs/scope-mvp.md`）：

- **证据驱动**：每条结论必须带 `EvidenceItem`，无来源不出结论；
- **本地优先**：LLM 推理走宿主 Ollama（`127.0.0.1:11434`），容器只承载 DB / 存储；
- **判据前置**：任何验证项开跑前，Pass / 中间区间 / No-Go 必须先定稿；
- **降级必带代价**：替代方案必须标注对 `Recall@5` 与 `P95` 的影响；
- **不编造数字**：未实测项写 `【待实测填入】`；
- **可复现**：组件 / 模型一律 digest 锁定，模拟数据固定 seed + `synthetic: true`。

## 当前状态速览

| 验证项 | 判定 | 关键数字 |
|---|---|---|
| V1 LLM 工具调用 | **No-Go**（M0.2 挂起；P5/P6/P7 处置后仍 No-Go） | 约束解码首次 qwen 0.35 / ds 0.45；P6 拆步多工具 qwen 40%→20%、ds 13.3%→0%（负结果）；P7 混合形态（R-2/R-3 上云，EXP-M02-001）云端 27B 首次 0.60、多工具用例级 50%、参数值正确率 0.5882 → 处置链①②③④全执行仍 No-Go |
| V2 混合检索 | **Pass** | 混合 `Recall@5` 0.91 |
| V3 时序接入 | **封板定稿**（决策3，2026-09-29） | 四类边界 4/4；聚合 P95 ≈26.2 ms；解码器吞吐 P1 |
| V4a 环境采集 | **Pass** | env 三件套 |
| V4b 资源实测 | **Pass**（2026-09-29 干净机重测） | 宿主峰值 17.89 GB ≤ 24 GB 门禁（历史 26.38GB 中间区间口径保留） |
| V5 checkpoint | **Pass**（M0.4 达成） | 重复落库 0 次；296 KB/thread |
| V6 / V7 数据 / 评测集 | **结构 Pass** | 模拟数据兜底；单人标注 |

> 完整全景：`reports/project-summary-2026-09-29.md`（最新）与 `reports/project-overview.md`（2026-09-28，较早）。

## 目录结构

```
auscult/
├─ .gitignore     忽略 env/cloud.json（含 API key）、__pycache__/、*.pyc、.venv/
├─ README.md      本文件
├─ CHANGELOG.md   变更日志（以验证项 / 里程碑为粒度）
├─ requirements.txt  Python 依赖锁（版本唯一来源 docs/version-lock.md）
├─ plan/          7 份阶段开发计划（Phase 0 D1–D10 / 任务总结 / Phase 1 / M02 混合形态 / V1 schema v2 复审 / V1 破局路径方案对比 / H15 拒止前置门架构解耦设计）
├─ docs/          15 份治理与规范文档（范围/判据/风险/版本/缺陷/移交…）
├─ reports/       12 份报告 + daily/（README + D1-status）：
│                 v1-report / v1-review-v2 / v1-review-v3 / v2-report / v3-auth / v4b-report / v5-report
│                 P0-summary / project-overview / project-summary-2026-09-29 / status-audit-2026-09-30
├─ schemas/       tools_v1.json（FROZEN，5 工具）/ tools_v2.json / tools_v3.json / tools_v4.json（当前基线）
│                 tools_v5.json（H3 实验版，❌ 实测否决、未采纳，保留供审计）
├─ protos/        sparkplug_b.proto + 生成的 PB 类（sparkplug_b_pb2.py、__init__.py）
├─ configs/       decoder_schema_mapping.json / mosquitto.conf / redis.conf
├─ docker/        compose.base.yml / compose.ingest.yml / compose.v2.yml / compose.v4b-iso.yml / Dockerfile.decoder
├─ scripts/       18 个 Python 执行器 + 2 个 PowerShell（其中 12 个含 --selftest）
├─ tests/         回归测试（pytest，119 用例；离线运行，见 ISS-030 / ISS-031）
├─ evals/         golden_set_v1(50) / v1_cases(20) / v2_cases(25) / v3_cases(25) / r4_cases(20) / corpora_v1/corpus_100
├─ experiments/   v1 / v2 / v3 / v4b / v5 / r4 原始实测数据（raw/，只增不改）+ plans/（P1 专项计划）
├─ env/           env-baseline-v2.md（+v1 留档）/ hardware.json（+v1 留档）/ ports.md / cloud.json
│                 / wslconfig.proposed / wslconfig.bak
└─ prompts/       tool_call_prompt_v1.md（**评测活动版本**）/ v2.md（⛔ 含测试集泄漏，禁用于评测）/ 
                  v3.md（未采纳，备查）/ v4.md（候选未采纳）/ v5.md（实验版未采纳）/
                  tool_call_step_prompt_v1.md / r4_prompt_v1.md
```

> **整理说明（2026-09-30）**：已清理字节码缓存与空目录、修正 1 处误命名数据文件、移除 1 个零引用的字节相同副本。
> 详细前后对比见 `reports/status-audit-2026-09-30.md`。

## 快速开始

```powershell
# 1) 依赖（版本见 requirements.txt，来源 docs/version-lock.md）
uv pip install -r requirements.txt

# 2) 离线自检（不联网、不需容器；18 个脚本中 12 个已覆盖，全部应 exit 0）
foreach ($s in 'llm_adapter','judge_tools','gbnf_grammar','param_normalizer','run_v1',
               'run_cloud_baseline','run_v2','self_decoder','spb_simulator','run_v5',
               'run_r4','judge_r4') {
    python "scripts/$s.py" --selftest
}

# 3) 回归测试（离线、秒级；119 用例：llm_adapter / judge_tools / param_normalizer / run_v5 /
#    run_v1 / 用例集完整性。防「已修复缺陷复发」，见 docs/known-issues.md ISS-030 / ISS-031）
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

## 迭代纪律（改动前必读）

1. **Schema 冻结**：`schemas/tools_v1.json` 的 `change_policy` 要求任何修改必须升版为 `tools_v2.json`，
   否则 V1 全部结论作废；同时同步 `docs/version-lock.md` §2.6。
2. **组件 / 模型**：只写 digest，禁止裸 tag 与 `latest`（纪律 1）；变更即升版（纪律 2）。
3. **实验登记**：按 `docs/experiment-log-template.md` 记录 `experiment_id` / digest / seed / prompt 版本 / commit，
   原始数据落 `experiments/**/raw/`（只增不改）。
4. **已知缺陷**：改动前先查 `docs/known-issues.md`（ISS-001 – ISS-018）与 `docs/risk-register.md`。
5. **变更记录**：见 `CHANGELOG.md`。

## 明确不做（Won't）

多租户｜模型微调（预留 LoRA 接口）｜复杂 GraphRAG 多跳（>2 跳）｜移动端｜
真实 Modbus / OPC UA 直连（预留边缘网关转 MQTT 接口）｜
**自动执行维修动作（永久安全刚性）**。
