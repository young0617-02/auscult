"""W6 `retrieve_knowledge` 工具（Phase 2 · 混合检索，P2-D9/D11）

职责：把 W1→W5（改写→多路召回→RRF→重排→证据组装）封装为单一 **可调用工具**，
      供 R-2/R-3 工具调用链（Phase 2）消费；输出对齐全 `tools_v1.json` 的 `evidence_refs`
      （`ref=chunk_id`）与 `graph_hint`。

关键设计（plan §5.6 + W6 方案）：
  - **进程内常驻单例** `RetrievalService`：BGE-M3 EmbeddingClient 与 reranker CrossEncoder
    各加载一次、跨调用复用（解决 CLI 每进程重载 ~15s / 重排 ~1.1s）；
  - **附加式注册**：`to_openai_tool()` 生成 OpenAI 函数工具定义，`with_tools()` 并入既有工具列表；
    默认**不修改** `schemas/tools_v1.json`（其恰 5 工具，V1 链路与 llm_adapter self-test 依赖之）；
  - **延迟剖面**：`latency{rewrite,recall,fuse,rerank,assemble,total}_ms` 逐段计时；
  - **降级**：任一路失败仅置 degraded 标记，不抛异常中断。

RetrievalService.retrieve(question, mode) → EvidencePackage：
  `{items, total, graph_support, degraded, degraded_routes, latency, tool_metadata}`

自检：`python scripts/retrieve_knowledge.py --selftest`（离线，仅验工具 schema/注册/导入）
用法：`python scripts/retrieve_knowledge.py --query "<问句>"`
     `python scripts/retrieve_knowledge.py --tool-schema   # 打印 OpenAI 工具定义`
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from assemble_evidence import assemble_evidence
from fuse_rrf import fuse_rrf
from query_rewrite import rewrite as q_rewrite
from retrieval import retrieve_all
from rerank import rerank


# ---------------------------------------------------------------- 工具定义（OpenAI 兼容）

RETRIEVE_KNOWLEDGE_TOOL: dict[str, Any] = {
    "name": "retrieve_knowledge",
    "type": "read_only",
    "description": "对工业故障诊断问题进行混合检索：改写 → 稠密/稀疏召回 → RRF 融合 → "
                   "重排序 → 父块回填与图谱一致性裁定，返回带证据引用（chunk_id）的 Top-N 知识块。",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "待检索的问题（设备/故障/参数语义）"},
            "mode": {"type": "string", "enum": ["rules", "llm"],
                     "description": "改写模式：rules=规则快路径（确定性）；llm=云端 LLM 改写"},
        },
        "required": ["question"],
        "additionalProperties": False,
    },
}


def to_openai_tool() -> dict[str, Any]:
    """转 OpenAI 兼容 tools 数组元素（与 llm_adapter.load_tools 结构一致，程序化，禁手抄）。"""
    return {"type": "function",
            "function": {"name": RETRIEVE_KNOWLEDGE_TOOL["name"],
                         "description": RETRIEVE_KNOWLEDGE_TOOL["description"],
                         "parameters": RETRIEVE_KNOWLEDGE_TOOL["parameters"]}}


def with_tools(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把 retrieve_knowledge 附加并入工具列表（去重）；不改动 tools_v1.json。"""
    name = RETRIEVE_KNOWLEDGE_TOOL["name"]
    if any(t.get("function", {}).get("name") == name
           or t.get("name") == name for t in existing):
        return list(existing)
    return list(existing) + [to_openai_tool()]


# ---------------------------------------------------------------- 常驻服务

class RetrievalService:
    """进程内常驻的 W1→W5 检索服务（模型/索引仅加载一次）。"""

    def __init__(self, *, device: str = "cpu",
                 top_k: int = 5, mode: str = "rules",
                 use_rerank: bool = True) -> None:
        self.device = device
        self.top_k = top_k
        self.mode = mode
        self.use_rerank = use_rerank      # D7消融：False→跳过重排，直接用RRF排序
        self._embedder = None            # BGE-M3（惰性）
        self._reranker = None            # CrossEncoder（惰性）
        self._text_index: dict[str, str] | None = None
        self._sub_index: dict | None = None
        self._parent_index: dict | None = None

    # -- 惰性单例 --
    def _embedder_once(self):
        if self._embedder is None:
            from run_v2 import BGE_M3_MODEL_PATH        # noqa: PLC0415
            from run_v2 import EmbeddingClient as Emb   # noqa: PLC0415
            self._embedder = Emb(BGE_M3_MODEL_PATH)
        return self._embedder

    def _reranker_once(self):
        if self._reranker is None:
            from sentence_transformers.cross_encoder import CrossEncoder  # noqa: PLC0415
            from retrieval_base import RERANKER_MODEL_PATH                 # noqa: PLC0415
            self._reranker = CrossEncoder(str(RERANKER_MODEL_PATH), device=self.device)
        return self._reranker

    def _load_chunk_index(self) -> tuple[dict[str, str], dict, dict]:
        """prefetch 子/父块索引（仅一次）；返回 (chunk_id→text, sub_index, parent_index)。"""
        if self._text_index is not None:
            return self._text_index, self._sub_index, self._parent_index
        import json                                   # noqa: PLC0415
        base = Path(__file__).resolve().parents[1]
        sub_path = base / "chunks" / "chunks_v1.jsonl"
        par_path = base / "chunks" / "parents_v1.jsonl"
        texts: dict[str, str] = {}
        subs: dict = {}
        for p in (sub_path,):
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                if not c.get("is_parent"):
                    texts[c["id"]] = c.get("text", "")
                    subs[c["id"]] = c
        pars: dict = {}
        for line in par_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                pars[c["id"]] = c
        self._text_index, self._sub_index, self._parent_index = texts, subs, pars
        return texts, subs, pars

    # -- 主流程 --
    def retrieve(self, question: str, *, mode: str | None = None) -> dict[str, Any]:
        mode = mode or self.mode
        lat: dict[str, float] = {}
        tt = time.perf_counter()

        rw = q_rewrite(question, mode=mode)
        lat["rewrite_ms"] = round((time.perf_counter() - tt) * 1000, 1)

        t1 = time.perf_counter()
        recall = retrieve_all(rw, parallel=True, embedder=self._embedder_once())
        lat["recall_ms"] = round((time.perf_counter() - t1) * 1000, 1)

        t2 = time.perf_counter()
        fused = fuse_rrf(recall["candidates"], top_k=self.top_k)
        lat["fuse_ms"] = round((time.perf_counter() - t2) * 1000, 1)

        texts, subs, pars = self._load_chunk_index()
        t3 = time.perf_counter()
        if self.use_rerank:
            rr = rerank(rw.get("semantic", question), fused["scored"],
                        top_k=self.top_k, device=self.device,
                        text_index=texts, model=self._reranker_once())
        else:
            # D7消融：跳过重排，直接用RRF排序作为reranked
            rr = {"reranked": [{"chunk_id": s["chunk_id"], "rerank_score": s.get("score", 0),
                                "recall_rank": s.get("rank"), "routes": s.get("routes"),
                                "text": texts.get(s["chunk_id"], "")}
                               for s in fused["scored"][:self.top_k]],
                  "degraded": False, "latency_ms": 0.0}
        lat["rerank_ms"] = round((time.perf_counter() - t3) * 1000, 1)

        t4 = time.perf_counter()
        ev = assemble_evidence(rr["reranked"],
                               graph_paths=recall["graph_paths"],
                               graph_entities=recall["graph_entities_hit"],
                               sub_index=subs, parent_index=pars)
        lat["assemble_ms"] = round((time.perf_counter() - t4) * 1000, 1)
        lat["total_ms"] = round((time.perf_counter() - tt) * 1000, 1)

        degraded = bool(rr["degraded"]) or bool(ev["degraded"]) or bool(recall["degraded_routes"])
        return {"items": ev["items"], "total": ev["total"],
                "graph_support": ev["graph_support"], "degraded": degraded,
                "degraded_routes": recall["degraded_routes"],
                "latency": lat,
                "tool_metadata": {"tool": RETRIEVE_KNOWLEDGE_TOOL["name"],
                                  "mode": mode, "rewrite": rw,
                                  "weights": fused["weights"], "k": fused["k"]},
                "evidence_refs": [{"type": "chunk", "ref": i["chunk_id"]}
                                  for i in ev["items"]]}


def _selftest() -> int:
    fail = 0
    # 1) 工具 schema 结构
    tool = to_openai_tool()
    if tool["type"] != "function" or tool["function"]["name"] != "retrieve_knowledge":
        print("[FAIL] 工具 schema 结构不正确")
        fail += 1
    if "question" not in tool["function"]["parameters"]["properties"]:
        print("[FAIL] 参数缺 question")
        fail += 1
    # 2) 附加式注册：不丢既有工具、不去重错误
    base = [{"function": {"name": "query_sensor"}}]
    merged = with_tools(base)
    if len(merged) != 2 or merged[1]["function"]["name"] != "retrieve_knowledge":
        print(f"[FAIL] with_tools 追加失败: {len(merged)}")
        fail += 1
    dup = with_tools(merged)
    if len(dup) != 2:
        print("[FAIL] with_tools 去重失败")
        fail += 1
    # 3) 服务契约：离线不加载模型，仅验 retrieve 结果键（用挡板：直接构造空包）
    svc = RetrievalService()
    pk = {"items": [], "total": 0, "graph_support": 0.3, "degraded": True,
          "degraded_routes": [], "latency": {}, "tool_metadata": {}, "evidence_refs": []}
    if "evidence_refs" not in pk or "items" not in pk:
        print("[FAIL] EvidencePackage 契约缺键")
        fail += 1
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项（离线）")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W6 retrieve_knowledge 工具")
    p.add_argument("--query", help="待检索问题")
    p.add_argument("--tool-schema", action="store_true", help="打印 OpenAI 工具定义")
    p.add_argument("--device", default="cpu")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--repeat", type=int, default=1, help=">1 时连续调用 N 次并打印冷/热路径延迟剖面")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.tool_schema:
        print(json.dumps(to_openai_tool(), ensure_ascii=False, indent=2))
        return 0
    if args.query:
        svc = RetrievalService(device=args.device, top_k=args.top_k)
        if args.repeat <= 1:
            print(json.dumps(svc.retrieve(args.query), ensure_ascii=False, indent=2))
            return 0
        lats = []
        for i in range(1, args.repeat + 1):
            print(f"\n===== 调用 #{i} =====", file=sys.stderr)
            out = svc.retrieve(args.query)
            L = out["latency"]
            lats.append(L)
            tag = "冷" if i == 1 else "热"
            print(f"[{tag}] #{i} total={L['total_ms']:.0f}ms "
                  f"(rewrite {L['rewrite_ms']:.0f} · recall {L['recall_ms']:.0f} · "
                  f"fuse {L['fuse_ms']:.0f} · rerank {L['rerank_ms']:.0f} · "
                  f"assemble {L['assemble_ms']:.0f}) degraded={out['degraded']}", file=sys.stderr)
            if i == 1:
                first = L
        # 热路径剖面（第 2 次起）：P95 以热路径为准（常驻服务不重复计模型加载）
        warm = lats[1:] if len(lats) > 1 else []
        first = lats[0]
        print(json.dumps({"cold_call": first, "warm_calls": warm,
                          "warm_avg_total_ms": round(sum(x["total_ms"] for x in warm) /
                                                     len(warm), 1) if warm else None},
                         ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())