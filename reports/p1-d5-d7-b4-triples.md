# P1-D5–D7 · B4 三元组抽取报告（终态 · v2）

> 来源：`plan/p1-plan-detailed.md` §5.7 B4
> 关联交付：受控词表 `configs/triple_schema.json`（v2）、抽取脚本 `scripts/extract_triples.py`、v1 基线 `experiments/p1/b4/extract_results.jsonl`、v2 终态 `experiments/p1/b4/extract_results_v2.jsonl`、Neo4j 图（91 节点 / 94 关系）
> 抽取基座：云端 `Qwen/Qwen3.8-27B` + `LLMAdapter` 约束解码（OpenAI `response_format: json_schema`）
> 日期：2026-10-08

## 一、目标与判据

从 B2 分块的 **36 子块** 抽取「实体-关系-实体」三元组，经受控词表 + 人工抽查质量把关后，全量 MERGE 入库 Neo4j。

## 二、迭代历程

| 版本 | 词表 | 结果 | 结论 |
|---|---|---|---|
| v1 | 9 关系（含泛「关联」） | 245 三元组 | 分层抽查发现「关联」75 条信息量低、「处置为」跨问题错配 → **不达质量线，重抽** |
| v2 | 11 关系（**去「关联」**，新增驱动/构成/阈值） | 184 三元组（36/36，0 失败 0 无效） | 核心结构关系优质；「处置为」仍存跨问题错配 → **结构关系入库，「处置为」独立专题** |

## 三、v2 方法与受控词表

- `configs/triple_schema.json` v2：实体类型 8（设备/测点/部件/故障/参数/标准值/处置/部位）、关系类型 11（监测/安装于/连接/驱动/构成/导致/表征/超限/阈值/处置为/位于）；含 OpenAI strict json_schema + Neo4j 关系 slug 映射。
- 提示词加严：rule 7「处置为」须原文同句/紧邻对应；rule 8 优先具体关系、**禁用「关联」类通用兜底**。
- 首跑受网络中断干扰（19 块 `getaddrinfo` DNS 失败）→ 网络恢复后 `--retry-failed` 增量补偿，终态 36/36 完成。

## 四、v2 抽取统计

| 指标 | 值 |
|---|---|
| 子块 | 36 / 36（100%） |
| 三元组 | **184**（0 校验无效 / 0 失败） |
| 单块延迟 | 均值 ~40s / 高值 ~100s；网络异常最长重试 ~52min（补偿完成） |

### 关系分布（v2）

表征 58 · 处置为 56 · 阈值 28 · 构成 22 · 驱动 5 · 导致 4 · 连接 4 · 超限 3 · 安装于 2 · 位于 1 · 监测 1（**「关联」= 0**）

## 五、Neo4j 入库（结构关系）

- **入库集**：v2 全量中**排除「处置为」**的关系（用户裁定：结构关系入库 + 处置专题）。
- 方式：`--import-neo4j --exclude-relations 处置为` → 128 条提交，按 `rid=类型:头|关系|类型:尾` MERGE 去重后 **91 节点 / 94 关系**。
- 图模式：`Entity(id, name, type)`，`id` 唯一约束；关系类型用 ASCII slug（`CHARACTERIZES/COMPOSES/THRESHOLDS/DRIVES/CONNECTS/CAUSES/EXCEEDS/INSTALLED_ON/LOCATED_AT/MONITORS`），属性 `source_chunk_id`/`confidence`/`rid`。
- **验证（Cypher 已通过）**：
  - `电机 -DRIVES-> 叶轮`
  - `HC-200 / IMP-150 / DP-125 -COMPOSES-> 泵壳/叶轮/轴/机械密封/轴承箱`
  - `振动烈度 -THRESHOLDS-> 1.8/4.5/11.2/28.0`；`驱动端/非驱动端轴承温度 -THRESHOLDS-> ≤70℃/＞85℃`
  - 关系统计口径与入库一致（CHARACTERIZES 39 / COMPOSES 22 / THRESHOLDS 16 / …）

## 六、「处置为」专项（待办，未入图）

v2 中 **56 条「处置为」** 因多问题工单跨行错配（如 `密封渗漏→动平衡校正`、`轴承温度异常→清理过滤器`）**未随结构关系入库**，单列为 B4 后续专项：
- 处置为跨问题错配属「词玻共现」问题，非词表缺类；修法为按问题逐条拆分（每条「故障→处置」独立提示）重抽，或抽检人工标注后仅入高置信子集。
- 决议内容、精简后再并入图谱。

## 七、局限声明

> **局限声明**：本报告所有结论仅针对本次实验环境（云端 `Qwen/Qwen3.8-27B` 约束解码、合成模拟语料、受控词表 v2）有效，不代表任意语料/任意外部模型的抽取质量。三元组经受控词表约束、脚本校验与结构关系分层抽查把关，但**未做逐条人工复核**；「处置为」关系因跨问题错配未入库。关系/实体类型划分受当前词表限制，词表扩展后结论可能变化。图内仅为结构关系子集，`source_chunk_id` 在多源合并（rid 去重）时仅保留首条来源。抽取与入库依赖 `Neo4j` 与云端模型服务可用性，API 临时中断需重试补偿（本次 v2 曾受 DNS 中断影响）。

## 八、产物清单

- `configs/triple_schema.json`（v2 词表 + schema + Neo4j 映射）
- `scripts/extract_triples.py`（抽取 / --retry-failed / --sample / --import-neo4j --exclude-relations）
- `experiments/p1/b4/extract_results.jsonl`（v1 基线）、`extract_results_v2.jsonl`（v2 终态）
- `experiments/p1/b4/manual_review_100_v1.jsonl`（v1 复核样本，归档）
- Neo4j 图：91 节点 / 94 关系

## 九、下一步

1. 【B4 专项·待办】「处置为」56 条单独重抽/抽检后并入图谱；
2. `python scripts/extract_triples.py --import-neo4j --exclude-relations 处置为`（如需重入库结构关系）；
3. 进入 B5（PG 元数据 + 工单导入）。