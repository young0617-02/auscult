# P2-D1 W3 RRF 融合实现报告

> 来源：`plan/Phase 2 详细开发计划（混合检索）.md` §5.3 W3（P2-D4）
> 日期：2026-10-09
> 状态：**实现完成，`--selftest` 0 失败，真实融合 top5 排序正确**
> 产物：`scripts/fuse_rrf.py`；`configs/retrieval.yml::rrf`
> 台账：`docs/prj-ledger-version-lock.md` §二.2.16

---

## 一、目标与边界

把 W2 `retrieval_all.candidates`（Dense+Sparse，各带 route 与路内 rank）融合为单列 `top_k=5`
供 W4 父块回填消费。

| 项 | 值 | 依据 |
|---|---|---|
| 融合式 | 加权 RRF | plan §5.3 |
| `k` | 60 | 与 V2 基准 `run_v2.RRF_K` 一致 |
| 权重 | dense 0.6 / sparse 0.4 | plan §5.3 |
| `top_k` | 5 | plan §5.3 |
| 图谱 | **不参与** | P2-R4（仅消费 candidates，不含 graph） |

**边界**：只做两路（dense/sparse）融合排序；图谱证据、父块回填、证据组装归 W4/W5。

## 二、算法

```
score(chunk) = Σ_{route∈{dense,sparse}} w_route * 1/(k + rank_route)
```

其中 `rank_route` 为该 chunk 在对应路内的排名（1..top_k_route）。同一 chunk 跨路命中时对每路贡献累加，
并按 `route` 保留单路 `{route, rank, w, contribution}` 留痕以支持归因。图谱候选不进入本融合。

## 三、实测结果

### 自检（`python scripts/fuse_rrf.py --selftest`）—— 0 失败
覆盖：双路均 rank=1 的 chunk 居首、加权累加正确性、双路贡献留痕、配置驱动、`top_k` 截断。

### 真实融合（编排召回落盘 candidates → fuse_rrf）
输入示例 query："离心泵驱动端振动烈度超标，轴承箱温度偏高，排查什么原因？"

| rank | chunk_id | score | 贡献（dense/sparse） |
|---|---|---|---|
| 1 | `criteria_2-1-c0` | 0.015788 | sparse rank1 + dense rank5 |
| 2 | `manual_impeller_series-5-c0` | 0.015648 | dense rank2 + sparse rank7 |
| 3 | `manual_scanned_dp-5-c0` | 0.015633 | dense rank1 + sparse rank9 |
| 4 | `manual_centrifugal_hc-5-c0` | 0.015584 | dense rank3 + sparse rank6 |
| 5 | `manual_ss_process-5-c0` | 0.015257 | dense rank4 + sparse rank8 |

融合排序符合加权 RRF 语义：`criteria_2-1-c0` 因 sparse 居首（高权重 rank1）挤下手册通用块升至第 1，
体现「多点命中跨路共识」优于单路高分。

## 四、关键实现决策
- **全参数进 `retrieval.yml::rrf`**：k / top_k / weights 均集中，供 D11 调参不硬编码。
- **保留每路贡献留痕**：`scored[].routes` 输出各 chunk 的路内 rank、权重与单路贡献，便于 W4 证据溯源与调试。
- **图谱严格隔离**（P2-R4）：函数只读 `candidates`（dense+sparse），不引入 graph 命中，避免污染 RRF 排序。

## 五、局限与后续
- 未做正式 `Recall@5` 评测（归属 M2.1 汇总门限）；本报告验证融合逻辑与排序正确性。
- 权重 0.6/0.4 为计划初值；D11 调参若需改，仅改 `retrieval.yml` 即可复算。

## 六、复现命令
```
python scripts/fuse_rrf.py --selftest
python scripts/retrieval.py --query "离心泵驱动端振动烈度超标，轴承箱温度偏高，排查什么原因？" > /tmp/c.json
python scripts/fuse_rrf.py --candidates /tmp/c.json
```