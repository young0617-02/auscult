# P1-D8–D9 · B6 一致性报告（Outbox + 补偿队列 + 对账）

> 来源：`plan/p1-plan-detailed.md` §四 D8–D9 · §5.9（B6 Outbox/对账，§1.2 出口判据：失败注入下对账零差异、补偿队列可自愈）
> 目标库：`postgresql://root:123456@127.0.0.1:5433/auscult_v2`（ParadeDB PG 18 @ 宿主 5433，权威源；端口审计见 `env/p1-audit-ports-2026-10-08.md`）
> 可重建索引：Milvus `kb_p1_v1`（URI `http://127.0.0.1:19531`）、Neo4j（Bolt 7687 / HTTP 7474）
> 脚本：`scripts/load_meta.py`（outbox 幂等补写）、`scripts/outbox_worker.py`（消费队列）、`scripts/reconcile.py`（对账）
> 日期：2026-10-08

## 一、范围

以 PostgreSQL 为唯一权威源，通过 Outbox 表统一编排对 Milvus（稠密检索索引）与 Neo4j（三元组图谱）的写入一致性与自愈。

| 组件 | 角色 |
|---|---|
| `outbox` 表 | 写 PG 成功即写发布票据（milvus/neo4j 各一）；`pending→done/failed` 状态 + `retry_count` 退避 |
| `outbox_worker.py` | 消费 pending：milvus 核查缺失用 BGE-M3 补齐；neo4j 核查存在性（缺失不补，仅记录） |
| `reconcile.py` | PG vs Milvus/Neo4j 三侧对账；`--fix` 补 outbox；`--fault-inject`（默认预演，`--apply` 才真删） |

## 二、实现要点

- `load_meta.py.build_outbox_rows` / `write_outbox_idempotent`：每 chunk 写 2 条（`milvus/upsert` + `neo4j/verify`），先查后插防重复。
- `outbox_worker.py`：milvus 按键核查缺失→本地 BGE-M3 补齐；neo4j 跑 `MATCH ()-[r {source_chunk_id}]->() RETURN count(r)` 核查存在性。成功→`done`；失败→`retry_count+1` + `last_error`，达上限(10)→`failed`。幂等动作支持自愈重做。
- `reconcile.py`：PG `doc_chunks.chunk_id` 权威源 vs Milvus 集合与 Neo4j 关系的 `source_chunk_id`。
- **修复（本次演练引入）**：`_insert_outbox_if_missing` 原仅判「行存在」即跳过；但 fault-inject 删除后旧 `done` 行仍占位，导致无法重新入队自愈。已改为：已有 `pending` 行→跳过；已有 `done/failed` 行但对账仍判缺失→**重置为 pending**；无行→插入。据此支持「注入→fix→worker→归零」闭环且保持幂等可重跑。同时修复 `_chunk_meta` 中 doc_id 为 PG uuid 类型无法 `json.dumps` 的问题（转 `str`）。

## 三、演练结果

### 基线对账（只读）

```
PG=36 / Milvus=36 / Neo4j(有关系的chunk)=22
[✔ 零] PG 有、Milvus 缺
[✘ 14] PG 有、Neo4j 缺   ← fault_case_4-1-c0 / manual_*.c0 等 14 块
[✔ 零] Milvus 有、PG 无（多余）
[✔ 零] Neo4j 有、PG 无（多余）
```

### 步骤 1：补写 14 块 Neo4j verify outbox

- `reconcile.py --fix`：补写 0 条（verify outbox 于 load_meta 时已存在，幂等跳过）。
- `outbox_worker.py --limit 1000`：处理 14 条，OK=0 失败=14——**Neo4j 图中确无这 14 块的关系**（B4 抽取该 14 块有效三元组=0，`source_chunk_id` 无落库），worker 幂等失败登记 `last_error`，非 outbox 机制能补齐，属**数据层缺口**。

### 步骤 2：fault-inject `criteria_1-1-c0` 闭环演练

| 阶段 | 命令 | 结果 |
|---|---|---|
| 注入 | `reconcile.py --fault-inject milvus --chunk-id criteria_1-1-c0 --apply` | 真删该块（`delete_count:1`）；对账 PG 有/Milvus 缺 1 |
| 自愈 | `reconcile.py --fix` + `outbox_worker.py --limit 1000` | fix 重置该块为 pending（补写 1 条）；worker `milvus:criteria_1-1-c0 补增`（BGE-M3 向量化补回） |
| 复检 | `reconcile.py` | **Milvus 归零（PG=Milvus=36）**；Neo4j 仍缺 14（数据层缺口） |

## 四、结论

- **Milvus 补偿队列自愈闭环达成**：故障注入→对账检出→fix 重置 pending→worker BGE 补回→复检归零，满足 §1.2「失败注入下对账零差异、补偿队列可自愈」出口判据（Milvus 侧）。
- **Neo4j 14 块缺关系为非机制缺口**：`verify` 只核查存在性，不补数据；14 块属 B4 抽取未产出关系（多为 `fault_case_*` 与 `manual_impeller_series`/`manual_scanned` 等有向关系稀疏子块），需 B4「处置为」补链专项解决，非 B6 对账能消除。

## 五、B4 补链专项结果（2026-10-08，闭链接续）

> 背景：B6 初判 Neo4j 缺 14 块。专项后经诊断，14 缺块实分 3 类性质，分治后**对账归零**。

| 类别 | 缺块 | 根因 | 处置 | 结果 |
|---|---|---|---|---|
| A 真缺（4块） | manual_centrifugal_hc-4 / manual_impeller_series-2 / manual_scanned_dp-2 / manual_ss_process-2 | v2 抽取 n_valid=0，原文为「安全须知/安装要求」纯操作性文本，**合法判定无可抽三元组**（非失败） | 忠实处置，不入图强行造关系；纳入对账与 worker 豁免清单 | 不属缺口 |
| B 关系已在图、source 归到他块（7块） | manual_impeller_series-5/6 / manual_scanned_dp-6 / manual_ss_process-5/6/7 | import 以 `rid=head\|关系\|tail` MERGE 去重，source_chunk_id 只写首个块，同知识被归到他块 → reconcile 按 source 判缺伪报 | import 支持**关系多 source 数组** `source_chunk_ids`（ON CREATE 置 `[$cid]`、ON MATCH 去重累加），reconcile/worker CQL 同时识别单值 + 数组 | 补 source 归因，31 条多 source 关系 |
| C 全「处置为」→ 未入图（3块+1） | fault_case_4 / workorders_A/B/E | v2 只抽到处置为，按 B4 决策「处置为」不入结构图 → source 无归属 | 本次一并入库（映射 `处置为:HANDLED_BY`），全量重导入不排除 | 33 条 HANDLED_BY 关系入库，source 归零 |

**专项代码改动**（3 脚本）：
- [extract_triples.py](file:///<REPO>/scripts/extract_triples.py) `import_neo4j`：关系 source 由单值改数组 `source_chunk_ids` + `source_count`，支持一关系多 source；保留 `source_chunk_id` 兼容旧查询。
- [reconcile.py](file:///<REPO>/scripts/reconcile.py) `neo4j_chunk_ids`：同时读 `source_chunk_id` 与 `source_chunk_ids`；新增 `KNOWLEDGE_NO_RELATION_CHUNKS` 豁免 A 类。
- [outbox_worker.py](file:///<REPO>/scripts/outbox_worker.py) `_consume_neo4j`：CQL 兼容数组；同豁免清单，避免 A 类 verify 无限重试。

**专项后终态**：reconcile **对账零差异**；Neo4j 127 系（含 HANDLED_BY 33）、31 条多 source 归因、105 节点、约束 `triple_entity_id` 就绪；outbox pending 清零；三脚本 selftest 全绿。

## 六、局限声明

> **局限声明**：本报告所有结论仅针对本次实验环境与合成模拟语料有效。对账以 PostgreSQL `doc_chunks.chunk_id` 为主键口径，Neo4j 以关系的 `source_chunk_id`/`source_chunk_ids` 属性存在性为准，经过 B4 补链专项后**对账零差异**；但本报告仅核验 chunk 覆盖，**不核验关系语义/结构正确性**（三元组准确率由 B4 人工复核与 D9 判定负责）。A 类 4 块（安全须知/安装要求）被判定「无可抽三元组」而豁免，属忠实于原文的取舍（词表规则 9），非机制跳过。`--fault-inject --apply` 为真实（破坏性）写操作，本次仅对单一指定 chunk `criteria_1-1-c0`（Milvus）执行并已由 worker 补回；其余块未做真实删除演练，重跑需显式指定。B4 v2 词表（11 关系）与 neo4j_relation_map 的 ASCII slug 映射不变。

## 七、产物清单

- `scripts/outbox_worker.py`（新建；B4 补链后兼容 `source_chunk_ids` + A 类豁免）
- `scripts/reconcile.py`（新建；修复 `_insert_outbox_if_missing` 自愈语义 + `_chunk_meta` doc_id 序列化；补链后兼容数组 + 豁免清单）
- `scripts/load_meta.py`（B6 补写 outbox 幂等）
- `scripts/extract_triples.py`（import 关系多 source 数组改造）
- PG `auscult_v2.outbox`：基线 72 条（36×2）；B4 补链后 pending **清零**，关系存在性核查全部通过/豁免
- Neo4j：127 条关系（含 HANDLED_BY 33）、31 条多 source 归因、105 节点、约束 `triple_entity_id`

## 八、下一步

1. ✅ **B4「处置为」补链专项**（已完成）：14 缺关系块已分治闭环，reconcile 对账零差异；
2. **D9 质量门槛判定**（B1–B6 总计件是否达标放行，逐项过 §七判据）；
3. 版本台账补记：B4–B6 脚本并入 `docs/prj-ledger-version-lock.md`。