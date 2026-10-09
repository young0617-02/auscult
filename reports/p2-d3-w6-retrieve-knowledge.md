# P2-D3/D9 W6 `retrieve_knowledge` 工具实现报告

> 来源：`plan/Phase 2 详细开发计划（混合检索）.md` §5.6 W6（P2-D9/D11）
> 日期：2026-10-09
> 状态：**实现完成，`--selftest` 0 失败，真实调用证据包结构完整**
> 产物：`scripts/retrieve_knowledge.py`
> 台账：`docs/prj-ledger-version-lock.md` §二.2.18

---

## 一、职责

把 W1→W5（改写→多路召回→RRF→重排→证据组装）封装为单一可调用工具 `retrieve_knowledge`，
供 R-2/R-3（Phase 2）工具调用链消费；输出对齐 `tools_v1.json` `evidence_refs`（`ref=chunk_id`）与 `graph_hint`。

## 二、关键设计

- **常驻单例** `RetrievalService`：BGE-M3 EmbeddingClient 与 reranker CrossEncoder 各加载一次、跨调用复用；
  子/父块索引懒加载一次。
- **附加式注册** `to_openai_tool()` / `with_tools()`：程序化生成 OpenAI 函数工具、并入既有列表并去重；
  **不修改** `schemas/tools_v1.json`（VI 链路与 llm_adapter self-test 断言恰 5 工具）。
- **可注入**：`retrieve_dense`/`retrieve_all` 增 `embedder=None`、`rerank` 增 `model=None`，支持外部常驻实例。
- **延迟剖面**：`latency{rewrite,recall,fuse,rerank,assemble,total}_ms` 逐段计时。
- **降级**：任一路失败仅置 `degraded`，不抛异常。

## 三、实测

### 真实调用
输入「离心泵驱动端振动烈度超标，轴承箱温度偏高，排查什么原因？」，`degraded=false`、`graph_support=1.0`、
Top-5 证据条目含父块回填 content、channel、graph_hint（图谱命中的块）、`evidence_refs=[...chunk_id]`。

### 延迟剖面（`--repeat 3`，进程内冷→热）
| 调用 | total | rewrite | recall | fuse | rerank | assemble |
|---|---|---|---|---|---|---|
| 冷 #1 | 15.2s | 493ms | 9668ms | ~0 | 5071ms | ~0 |
| 热 #2 | 1.28s | 0ms | 46ms | ~0 | 1230ms | ~0 |
| 热 #3 | 1.24s | 0ms | 36ms | ~0 | 1202ms | ~0 |

**结论**：常驻单例把热 recall 从冷 9.7s 降到 **36-46ms**，收益显著；但**CPU 重排 5 对 ≈1.2s** 主导，
热总延迟 ~1.26s **未达 `P95<800ms`**。与 plan §5.4「CPU 重排延迟上升，记录代价」一致。

## 四、结论与后续
- **功能达成**：W1→W5 级联 + 证据包契约 + 附加式工具注册，全 `--selftest` 0 失败、真实调用正确。
- **P95 差距（已登记，不阻塞 W6）**：热 rerank ≈1.2s 超 `800ms`。待 **D11** 两条路径择一：
  1. **GPU(cuda:0) 重排**（需与常驻 7B 错峰验证）；
  2. **降低重排候选量**（如 Top3 或仅对 RRF 前 3 重排）。
- **W7 工具链接入**：将 `with_tools()` 并入 Phase 2 R-2/R-3 工具 schema，使 `retrieve_knowledge`
  被云端 LLM 工具调用链实际调用（本报告仅封装与单工具冒烟，不涉端到端工具链判分）。

## 五、复现命令
```
python scripts/retrieve_knowledge.py --selftest
python scripts/retrieve_knowledge.py --tool-schema
python scripts/retrieve_knowledge.py --query "<问句>" --top-k 5
python scripts/retrieve_knowledge.py --query "<问句>" --top-k 5 --repeat 3   # 冷/热延迟剖面
```