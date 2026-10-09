# P2-D1 W2 多路召回编排实现报告

> 来源：`plan/Phase 2 详细开发计划（混合检索）.md` §5.2 W2（P2-D2/D3/D8）+ 约束 P2-R4
> 日期：2026-10-09
> 状态：**实现完成，三路 `--selftest` 0 失败，真实召回三路命中、`degraded_routes=[]`**
> 产物：`configs/retrieval.yml`、`scripts/retrieval_base.py`、`scripts/retrieve_{dense,sparse,graph}.py`、`scripts/retrieval.py`
> 台账：`docs/prj-ledger-version-lock.md` §二.2.15

---

## 一、目标与边界

并行执行 **Dense + Sparse**（进 RRF），**Graph 独立证据通道**（**P2-R4**：图谱不进入 RRF 排序，仅供 W4/W5 组装），统一汇总各候选与降级标记。

| 路由 | 输入 | 后端 | 参数 |
|---|---|---|---|
| Dense | `semantic` | Milvus HNSW(COSINE) + 本地 BGE-M3 | top_k=20；HNSW{M 16, efConstruction 200, ef 64}; dim 1024 |
| Sparse | `keywords` 原文 | Milvus 服务端 BM25（jieba） | top_k=20；bm25 k1=1.2, b=0.75 |
| Graph | `entities` | Neo4j ≤2 跳 + 受控关系 | top_k_paths=5；max_hops=2 |

**边界**：本路只产出召回候选 + 降级标记；融合排序归 W3 RRF，父块回填/证据组装归 W4/W5。

## 二、拓扑确认（关键）

- **Milvus 端点 = 19531**（v2 栈 `auscult-v2-milvus`），collection `kb_p1_v1`。
  `base` 栈的 `auscult-milvus`(19530) 为**空实例**（无 `kb_p1_v1`），已据实修正 `retrieval_base.MILVUS_URI`。
- **Neo4j** 端口 7474，`:Entity` 105 节点；关系 `source_chunk_ids`（数组）承载 chunk 归因。
- **BGE-M3 本地**：复用 `run_v2.EmbeddingClient`（`D:\modelscope\hub\models\BAAI--bge-m3`），dim 1024。

## 三、实测结果

### 自检（三脚本均 0 失败，Milvus/Neo4j 在线断言生效）
| 脚本 | Milvus collection | Neo4j 节点 | 结果 |
|---|---|---|---|
| `retrieve_dense.py` | 存在=True | — | 失败 0 |
| `retrieve_sparse.py` | 存在=True | — | 失败 0 |
| `retrieve_graph.py` | — | 105 | 失败 0 |

### 真实召回（`python scripts/retrieval.py --query "离心泵驱动端振动烈度超标，轴承箱温度偏高，排查什么原因？"`）

| 路由 | 命中数 | 延迟(route) | 头部结果 |
|---|---|---|---|
| Dense | 20 | ~5ms | `manual_*.-5-c0`（手册·振动章）、`criteria_2-1-c0` |
| Sparse | 20 | ~278ms | `criteria_2-1-c0`（居首）、`manual_*-3-c0` |
| Graph | 5 路径 | ~82ms | `criteria_1-1-c0`、`manual_*.-5-c0`…；命中实体 离心泵/驱动端/振动烈度/超标/轴承箱/温度 |

`degraded_routes = []`（三路全部成功）。`total_latency_ms≈15840` 为 CLI 单进程首次 BGE-M3 模型加载，route 内延迟均 <300ms。

## 四、关键实现决策

- **全参数进 `retrieval.yml`**：HNSW/cos/ef、BM25 k1/b、图谱跳数均在配置，供 D11 调参不硬编码。
- **迷你 YAML 解析（无 PyYAML 依赖）**：缩进栈处理嵌套容器 + `_cast_scalar` 剥内联注释 + 数值优先。
- **Dense/Sparse 并行**：`ThreadPoolExecutor(max_workers=3)`；任一失败 → 该路空 + `degraded_routes` 置位，不阻断链路。
- **Graph 独立通道**：hits 带 `route="graph"`，`retrieve_all` 单列 `graph_paths/graph_entities_hit`，**不并入 `candidates`**（P2-R4）。

## 五、修复留痕

1. Milvus 搜索 `output_fields` 误列 `"distance"` → 报 `field distance not exist`。`distance` 为保留字段顶层返回，已从三处 `output_fields` 移除。
2. Graph Cypher `UNWIND rels AS r WHERE …`（变量长路径+UNWIND 后跟 WHERE）→ Neo4j 语法报错，改用 `WITH r WHERE …`。
3. Graph 结果 `data` 为空时 `data[0]` 越界 → 改为遍历全部行并兜底空表。

## 六、局限与后续

- **BGE-M3 模型驻留**：CLI 每次 `--query` 单进程会重载模型（~15s），route 延迟未含编码时长。集成 `retrieve_knowledge`（W6）须**进程内常驻 EmbeddingClient** 以满足 `P95<800ms`。
- W2 未做正式 `Recall@5` 评测（那是 M2.1 汇总门限），本报告仅验证链路与三路命中正确性。
- Sparse 服务端 BM25 已达标（R-V2-2 服务端原生，非客户端自实现）。

## 七、复现命令
```
python scripts/retrieve_dense.py --selftest
python scripts/retrieve_sparse.py --selftest
python scripts/retrieve_graph.py --selftest
python scripts/retrieval.py --selftest
python scripts/retrieval.py --query "离心泵驱动端振动烈度超标，轴承箱温度偏高，排查什么原因？"
```