# P2-D3 W7 `retrieve_knowledge` 工具链接入 R-2/R-3 评测报告

> 来源：`plan/Phase 2 详细开发计划（混合检索）.md` §三 WBS W6 + `docs/p0-spec-gate-criteria.md` §3.1.1
> 日期：2026-10-09
> 状态：**云端全量 16/16 Pass（单工具 100% ≥85%）**
> 产物：`schemas/tools_p2_retrieve.json` / `evals/v2_retrieve_cases.jsonl` / `scripts/run_v2_tools.py` / `judge_tools` 语义匹配扩充
> 台账：`docs/prj-ledger-version-lock.md` §二.2.19
> RAW：`experiments/p2/w7/RAW-v2-tools.jsonl` + `.meta.json`

---

## 一、目标

把 W6 封装的 `retrieve_knowledge` 工具**接入 Phase 2 R-2/R-3 工具调用链**，用云端 LLM（Qwen/Qwen3.8-27B）验证：
模型能否在纯检索问题上**规划出对、参数抽取出对**的 `retrieve_knowledge` 调用，并按 `gate-criteria §3.1.1` 判据（单工具 ≥85%）判定 Pass/中间/No-Go。

## 二、评测设施

### 2.1 用例集 `evals/v2_retrieve_cases.jsonl`
- 16 条**纯检索用例**，字段镜像 V1（case_id / type / input / expected_tool_calls / expect_reject 等）。
- 预期工具一律 `retrieve_knowledge`；必填参数 `question` 给出语义关键词；`mode` 可选（缺省=默认），不参与正确性比对。

### 2.2 运行入口 `scripts/run_v2_tools.py`
- 镜像 `run_v1` 流程：`load_tool_schemas(tools_p2_retrieve.json)` → `llm_adapter.chat` → `judge_record` → `judge_verdict_tiered`。
- `TOOLS_P2_PATH` 指向 `schemas/tools_p2_retrieve.json`（隔离于 V1 5 工具基线）。
- 落盘 `experiments/p2/w7/RAW-v2-tools.jsonl` + `.meta.json`。

### 2.3 判据修复（关键）
- **问题**：初版 2 条冒烟工具名全对，但 `FAIL_PARAM_VALUE`——定位为**判据缺口**而非模型能力：
  `judge_tools` 仅对 `search_knowledge.query` 做语义匹配，而 `retrieve_knowledge.question` 走逐字比较，几乎必差。
- **修复（用户批准方案 1）**：`compare_arguments` 对 `("retrieve_knowledge","question")`
  复用既有 `_query_semantic_match`（关键概念命中 + bigram 交叠），对齐 V1 R-2/R-3 语义口径（[judge_tools.py](file:///<REPO>/scripts/judge_tools.py#L462-L467)）。

## 三、评测结果

### 3.1 总体
| 项 | 值 |
|---|---|
| 模型 | Qwen/Qwen3.8-27B（云端，约束解码） |
| 用例数 | 16（全部单工具 · 纯检索） |
| judged_success | **16/16（100%）** |
| `judge_verdict_tiered` | **Pass**（单工具 100% ≥85%） |

### 3.2 逐条抽样
| case_id | input 摘要 | 模型 tool_call | 判定 |
|---|---|---|---|
| p2-rk-001 | 离心泵振动烈度报警/停机值 | `{"question":"离心泵振动烈度报警值与停机值标准阈值","mode":"rules"}` | ✅ |
| p2-rk-002 | 轴承温度报警/高温阈值 | `{"question":"…轴承温度报警值…高温故障阈值","mode":"rules"}` | ✅ |
| p2-rk-003 | 汽蚀原因与判断 | `{"question":"离心泵汽蚀…如何判断…","mode":"llm"}` | ✅ |
| … | （余 13 条同口径） | 均为 `retrieve_knowledge` + 语义匹配 question | ✅ |

## 四、资产还原（越权审查与纠正留痕）

实现过程中，一次子代理操作**越权覆盖了既有受控 V1 资产**，已审查并完整还原：

| 越权操作 | 纠正动作 |
|---|---|
| 覆盖 `schemas/tools_v2.json`（V1 5 工具基线，也是 judge 原默认 `SCHEMA_PATH`） | `git checkout` 还原；git status 无该文件 M 行 |
| 二次越权新建 `schemas/judge_v1.json` 并改 judge 默认 | 已删除；`judge_tools.py` `SCHEMA_PATH` 默认回 `tools_v2.json`（L67） |
| run_v2 引用旧 `TOOLS_V2_PATH` | 改 `TOOLS_P2_PATH` → `schemas/tools_p2_retrieve.json` |

**隔离原则（本次确立）**：Phase 2 工具 schema 独立于 V1 5 工具基线，置于新文件 `tools_p2_retrieve.json`，后续新增工具 schema 照此隔离，不再触碰受控 V1 资产。

## 五、结论与后续

- **达成**：`retrieve_knowledge` 工具已通过工具链接入 R-2/R-3 判据线（16/16 Pass，单工具 100% ≥85%），纯检索规划+参数抽取能力成立。
- **说明**：本次判据对象为**工具调用（规划 + 参数抽取）**，非检索 Recall/MRR（属 P2 检索管线指标，另由 M 里程碑评测）；判分口径沿用 V1 工具链判定，无数据档位放宽。
- **待办（沿袭，不属 W7）**：热 rerank ≈1.2s 超 `P95<800ms` → P2 待 D11（GPU 重排 / 降候选量）。

## 六、复现命令
```
.venv\Scripts\python.exe scripts\run_v2_tools.py --selftest
.venv\Scripts\python.exe scripts\run_v2_tools.py --schema schemas/tools_p2_retrieve.json   # 云端全量
.venv\Scripts\python.exe scripts\judge_tools.py --selftest
```