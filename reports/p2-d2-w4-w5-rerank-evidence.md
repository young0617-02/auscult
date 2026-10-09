# P2-D2/D10 W4 重排 + W5 证据组装实现报告

> 来源：`plan/Phase 2 详细开发计划（混合检索）.md` §5.4（W4）/ §5.5（W5）
> 日期：2026-10-09
> 状态：**实现完成，probe/rerank/assemble 三脚本均 0 失败；端到端 W2→W5 贯通、degraded=false**
> 产物：`scripts/rerank.py`、`scripts/assemble_evidence.py`、`scripts/probe_reranker.py`、`chunks/parents_v1.jsonl`
> 台账：`docs/prj-ledger-version-lock.md` §二.2.17

---

## 一、W4 重排（P2-D6）

把 W3 `fuse_rrf.scored` 用本地 **BGE-reranker-v2-m3** 复排 → Top-5。

### 探针实测（闭环 P1 待办「probe_reranker 实测」）
| 项 | 结果 |
|---|---|
| 模型 | `BAAI--bge-reranker-v2-m3`（XLMRoberta，1024 隐维，fp32） |
| 加载（CPU） | 4.57s |
| 参数量 | ≈567.8M（≈2.27GB safetensors） |
| 编码 | ≈54ms/对 @batch16（32 对 ~1.7s） |
| 设备 | **CPU 默认**（避免与常驻 7B 争 GPU，plan §5.4 / R10 错峰） |
| 留痕 | `experiments/p2/w4/probe_reranker.json` |

### 端到端结果
输入「离心泵驱动端振动烈度超标，轴承箱温度偏高，排查什么原因？」，`degraded=false`、Top5 重排：

| rank | chunk_id | rerank_score | 说明 |
|---|---|---|---|
| 1 | `manual_scanned_dp-5-c0` | 0.482 | 手册·运行章节（高相关度） |
| 2 | `manual_impeller_series-5-c0` | 0.472 | ↑ |
| 3 | `manual_centrifugal_hc-5-c0` | 0.461 | ↑ |
| 4 | `manual_ss_process-5-c0` | 0.433 | ↑ |
| 5 | `criteria_2-1-c0` | 0.148 | 标准判据表（RRF#1 重排后降至尾，语义相关度合理） |

> 重排显著区分「运行维护章节（支撑原因排查）」与「判据速查表」，符合预期。

## 二、W5 证据组装（P2-D7/D10）

对重排 Top5 做**父块回填**、**图谱冲突裁定**，组装为对齐 plan §5.5 的 `EvidenceItem`。

- **父块回填**：`chunks_v1.jsonl`（子块含 parent_id）→ 新增 `chunks/parents_v1.jsonl`（58 父块，
  与 `_chunk_summary.json` `parent_total=58` 一致）→ `content` 取父块完整上下文，引用粒度仍为子块
  `chunk_id`（含 page/section）。
- **冲突裁定**：文档证据为主；文档 chunk 在图谱路径集内 → `graph_hint` 标注 + `graph_support=1`；
  否则 `graph_support=0.3`（不否决，仅降权）。
- 实测定点：`manual_impeller_series-5-c0` 等 → `graph_hint="图谱命中:离心泵、驱动端、…温度"`，
  聚合 `graph_support=1.0`、`degraded=false`、`total=5`。

EvidenceItem 字段：`{chunk_id, doc_id, content, source, page, score, channel, graph_hint}`，
与 `tools_v1.json` `evidence_refs.ref(=chunk_id)` 兼容，W6 `retrieve_knowledge` 可直接消费。

## 三、关键决策
- 重排**默认 CPU + 失败降级**：模型加载/推理异常 → 返回 RRF 原序并置 `degraded=true`（不丢候选）。
- 重排保留 `recall_rank`/`routes`，便于 W5 溯源与 D11 调参。
- 父块映射一次性生成（`chunks/parents_v1.jsonl`），避免 assemble 时重复分块。

## 四、局限与后续
- **P95 风险**：CPU 重排 Top5 ≈1.1s，叠加召回 ≈300ms 对 `P95<800ms` 预算偏紧；
  plan §5.4 已注明「CPU 重排延迟上升，记录代价」。归 W6 集成 + 待 **GPU(cuda:0) 重测**，暂不作 W4 阻塞。
- **重排消融（D7）**：'有/无 reranker' 的 `Recall@5` 增益对比尚未做，归 W7 评测批次。
- 图谱 `graph_hint` 当前为「命中实体」线索，未含具体关系路径；如需 `bearing_wear-CAUSES->temperature_rise`
  级联路径，需扩展 W2 图谱通道返回值（记录为后续增强项）。

## 五、复现命令
```
python scripts/probe_reranker.py --batch-sizes 8 16
python scripts/rerank.py --selftest
python scripts/assemble_evidence.py --selftest
# 全链（示例）：
python scripts/retrieval.py --query "<问句>" > /tmp/a.json
python scripts/fuse_rrf.py --candidates /tmp/a.json > /tmp/b.json
python scripts/rerank.py --query "<问句>" --scored /tmp/b.json > /tmp/c.json
python scripts/assemble_evidence.py --reranked /tmp/c.json --graph /tmp/a.json
```