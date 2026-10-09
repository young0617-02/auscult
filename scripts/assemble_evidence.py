"""W5 证据组装 + 父块回填 + 冲突裁定（Phase 2 · 混合检索，P2-D7/D10）

职责：把 W4 重排结果（Top-5 文档证据）**依据 parent_id 回填父块上下文**，并并入图谱线索
      （W2 的 graph 独立通道，P2-R4），最终组装为对齐 plan §5.5 / `tools_v1.json` 的
      `EvidenceItem` 列表，供 W6 `retrieve_knowledge` 直接消费。

裁定规则（plan §5.5）：
  - 文档证据 = 主证据；图谱路径 = 线索（`graph_hint`），不改变排序；
  - 文档↔图谱一致（文档 chunk 落在图谱路径集）→ `graph_support=1`；
  - 图谱无路径或未覆盖 → `graph_support=0.3`（不否决，仅降权）。

父块回填：
  `chunks_v1.jsonl`（子块，含 parent_id/page/section/doc）→ `chunks/parents_v1.jsonl`（父块 text）；
  命中子块 → `content` 取父块上下文（完整段落），引用粒度仍为子块 `chunk_id`（含 page/section）。

输出：`{items: [EvidenceItem], total, graph_support, degraded}`
  EvidenceItem: `{chunk_id, doc_id, content, source, page, score, channel, graph_hint}`

自检：`python scripts/assemble_evidence.py --selftest`（离线，用注入 dict）
用法：`python scripts/assemble_evidence.py --reranked <rerank.json> --graph <retrieval.json> [--query ...]`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from retrieval_base import PROJECT_ROOT

SUB_PATH = PROJECT_ROOT / "chunks" / "chunks_v1.jsonl"     # 子块（命中粒度）
PARENT_PATH = PROJECT_ROOT / "chunks" / "parents_v1.jsonl" # 父块（回填上下文）


def _load(path: Path, key: str) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        idx[c[key]] = c
    return idx


def assemble_evidence(reranked: list[dict[str, Any]], *, graph_paths: list[dict[str, Any]],
                      graph_entities: list[str] | None = None,
                      sub_index: dict | None = None, parent_index: dict | None = None) -> dict[str, Any]:
    """组装证据条目。

    Args:
      reranked: `rerank.reranked`，每条含 `{chunk_id, rerank_score, routes}`
      graph_paths: `retrieval_all.graph_paths`（[{'chunk_id', ...}]；图谱独立通道）
      graph_entities: `retrieval_all.graph_entities_hit`
      sub_index / parent_index: 子块/父块索引（None → 读默认文件）
    Returns:
      {items: [EvidenceItem], total, graph_support, degraded}
    """
    subs = sub_index if sub_index is not None else _load(SUB_PATH, "id")
    pars = parent_index if parent_index is not None else _load(PARENT_PATH, "id")
    graph_cids = {g["chunk_id"] for g in (graph_paths or []) if g.get("chunk_id")}

    items: list[dict[str, Any]] = []
    for r in reranked:
        cid = r["chunk_id"]
        sub = subs.get(cid, {})
        pid = sub.get("parent_id")
        parent_text = (pars.get(pid, {}).get("text", "") if pid else "") or sub.get("text", "")
        channel = "+".join(sorted({rt.get("route", "") for rt in r.get("routes", []) if rt.get("route")})) \
            or "dense"
        overlap = cid in graph_cids
        graph_hint = None
        if overlap:
            hit_ent = "、".join(graph_entities or [])
            graph_hint = f"图谱命中:{hit_ent}" if hit_ent else "图谱命中"
        items.append({
            "chunk_id": cid,
            "doc_id": sub.get("doc_id"),
            "content": parent_text,
            "source": f"{sub.get('doc_type', '')}:{sub.get('doc_id', cid)}",
            "page": sub.get("page"),
            "score": r.get("rerank_score"),
            "channel": channel,
            "graph_hint": graph_hint,
        })

    # 冲突裁定：文档证据为主；一致率 → graph_support
    if graph_paths:
        hit = sum(1 for it in items if it["chunk_id"] in graph_cids)
        graph_support = round(hit / len(items), 3) if items else 0.3
        # 有任意文档证据与图谱一致 → 1（支持提升）；否则 0.3（不否决仅降权）
        graph_support = 1.0 if graph_support > 0 else 0.3
    else:
        graph_support = 0.3
    return {"items": items, "total": len(items),
            "graph_support": graph_support, "degraded": not items}


def _selftest() -> int:
    fail = 0
    subs = {"a1c0": {"id": "a1c0", "parent_id": "a1", "doc_id": "d", "doc_type": "标准判据",
                     "section": "要点", "page": 1, "text": "子文本"},
            "b1c0": {"id": "b1c0", "parent_id": "b1", "doc_id": "d", "doc_type": "标准判据",
                     "section": "要点", "page": 2, "text": "子文本B"}}
    pars = {"a1": {"id": "a1", "text": "父块上下文A"}, "b1": {"id": "b1", "text": "父块上下文B"}}
    reranked = [
        {"chunk_id": "a1c0", "rerank_score": 0.8, "routes": [{"route": "dense"}, {"route": "sparse"}]},
        {"chunk_id": "b1c0", "rerank_score": 0.6, "routes": [{"route": "dense"}]},
    ]
    # 1) 父块回填：a1c0 → content 取父块 a1
    out = assemble_evidence(reranked, graph_paths=[], graph_entities=[], sub_index=subs, parent_index=pars)
    a = next((i for i in out["items"] if i["chunk_id"] == "a1c0"), None)
    if not a or a["content"] != "父块上下文A":
        print(f"[FAIL] 父块回填不正确: {a}")
        fail += 1
    if a.get("channel") != "dense+sparse":
        print(f"[FAIL] channel 拼接不正确: {a.get('channel')}")
        fail += 1
    # 2) 无图谱 → graph_support=0.3
    if out["graph_support"] != 0.3:
        print(f"[FAIL] 无图谱 graph_support 应 0.3: {out['graph_support']}")
        fail += 1
    # 3) 文档与图谱一致 → graph_support=1 且 graph_hint 标注
    out2 = assemble_evidence(reranked, graph_paths=[{"chunk_id": "a1c0"}],
                             graph_entities=["离心泵"], sub_index=subs, parent_index=pars)
    if out2["graph_support"] != 1.0:
        print(f"[FAIL] 一致时应 graph_support=1: {out2['graph_support']}")
        fail += 1
    a2 = next((i for i in out2["items"] if i["chunk_id"] == "a1c0"), None)
    if not a2.get("graph_hint"):
        print("[FAIL] 图谱线索 graph_hint 未标注")
        fail += 1
    if out2["total"] != 2:
        print("[FAIL] 证据条数不正确")
        fail += 1
    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项")
    return fail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W5 证据组装 + 父块回填")
    p.add_argument("--reranked", type=Path, help="rerank.py 输出 json（含 reranked 键或列表）")
    p.add_argument("--graph", type=Path, help="retrieval.py 输出 json（取 graph_paths / graph_entities_hit）")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.reranked:
        rd = json.loads(args.reranked.read_text(encoding="utf-8-sig"))
        reranked = rd if isinstance(rd, list) else rd.get("reranked", [])
        graph_paths: list[dict[str, Any]] = []
        graph_entities: list[str] | None = None
        if args.graph:
            gd = json.loads(args.graph.read_text(encoding="utf-8-sig"))
            graph_paths = gd.get("graph_paths", [])
            graph_entities = gd.get("graph_entities_hit")
        out = assemble_evidence(reranked, graph_paths=graph_paths, graph_entities=graph_entities)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())