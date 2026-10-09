# -*- coding: utf-8 -*-
"""M2 里程碑汇总评测前的「可评测子集」覆盖度筛查（P2 · 混合检索 M2.3）

背景：`evals/golden_set_v1.jsonl` 的 50 题引用 7 类逻辑文档（doc-pump-manual /
      doc-vibration-std / ...），而真实建库语料 `chunks/chunks_v1.jsonl` 是 19 文档
      36 子块的极小合成样本（3147 token），两者内容覆盖度脱节。直接按 golden
      relevant_chunk_ids 做 Recall 会系统性失真。

本脚本职责：对每条 golden 逐题估算「答案实词在真实语料中的覆盖度」，筛出真实语料
      **可覆盖**的子集，并为这些题给出「最匹配真实子块」映射候选，供人工复核后
      固化为 `evals/m2_rel_map.json`，再交给 `eval_m2.py` 评测。

覆盖度口径（jieba 实词交集）：
      coverage = |answer_tokens ∩ corpus_tokens| / |answer_tokens|
      0.0 边界的题视为「无可覆盖」，排除；coverage>=阈值 的题留下做评测。
      同时输出每题的 top 候选子块（按实词交叠 / token 数加权打分）。

用法：
      .venv\\Scripts\\python.exe scripts\\m2_screen.py            # 全量 50 ← 冒烟/正式
      .venv\\Scripts\\python.exe scripts\\m2_screen.py --cases 5  # 只看前 5 条
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jieba

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN = PROJECT_ROOT / "evals" / "golden_set_v1.jsonl"
CHUNKS = PROJECT_ROOT / "chunks" / "chunks_v1.jsonl"
OUT_JSONL = PROJECT_ROOT / "experiments" / "p2" / "m2" / "screen-subsets.jsonl"
OUT_MAP = PROJECT_ROOT / "experiments" / "p2" / "m2" / "mapping_candidates.jsonl"

_STOP = {
    "我们", "这台", "什么", "多少", "怎么", "为什么", "不要", "分别", "以及", "如何",
    "哪些", "多久", "一次", "之后", "是否", "可以", "应", "要", "会", "是", "的", "了",
    "吗", "呢", "该", "指", "做", "进行", "情况下", "正常", "应设置", "应紧急",
    "这一", "一个", "由", "于", "至", "或", "与", "和", "为", "对", "及", "在", "等",
    "并且", "说明", "采用", "不得", "必须", "编号", "现象", "处置", "analysis",
    "the", "is", "of", "and",
}


def jieba_set(text: str) -> set[str]:
    toks = [w.strip() for w in jieba.lcut(text)]
    out = set()
    for w in toks:
        if not w or w in _STOP:
            continue
        if re.fullmatch(r"[\d.,%℃°±×/·^ \-\u200b\\s]+", w):
            continue
        out.add(w)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=0, help=">0 只看前 N 条")
    args = ap.parse_args()

    goldens = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    chunks = [json.loads(l) for l in CHUNKS.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.cases:
        goldens = goldens[: args.cases]

    # 语料全文本（含 section）拼成一个检索面，用于「领域专有实体命中」判定
    corpus_blob = "\n".join(c["text"] + " " + (c.get("section") or "") for c in chunks)

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    srows = []
    for g in goldens:
        # 1) 提取答案中的领域专有信号：拿每题所有 answer_points 的关键「实体词」
        #    这里不做数值漫浆，只提取与故障诊断/检索强相关的域词与标识符。
        domain = _extract_domain_signals(g)
        # 2) 信号词在真实语料中的命中（子串级，容忍空格/OCR 噪声）
        hits = {}
        for sig in domain["signals"]:
            key = sig["canon"]
            if key in corpus_blob.replace(" ", ""):
                hits[key] = sig["kind"]
        ratio = len(hits) / max(1, len(domain["signals"]))
        # 3) 相关块的「候选命中」= 语料里实际含这些信号的那几个块
        hit_chunks = []
        for c in chunks:
            blob = (c["text"] + " " + (c.get("section") or "")).replace(" ", "")
            got = [k for k in hits if k in blob]
            if got:
                hit_chunks.append({"chunk_id": c["id"], "doc_type": c["doc_type"],
                                   "section": c["section"], "sig_hit": len(got),
                                   "sigs": got})
        hit_chunks.sort(key=lambda x: x["sig_hit"], reverse=True)
        srows.append({
            "qid": g["qid"], "category": g["category"], "difficulty": g["difficulty"],
            "question": g["question"], "relevant_chunk_ids": g["relevant_chunk_ids"],
            "signals": domain["signals"], "hits": sorted(hits.keys()),
            "hit_ratio": round(ratio, 3),
            "hit_chunks": hit_chunks[:5],
        })

    # 排序：命中率降序（可评测优先）
    srows.sort(key=lambda x: x["hit_ratio"], reverse=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in srows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    evalable = [r["qid"] for r in srows if r["hit_ratio"] > 0 and r["hit_chunks"]]
    print(f"cases={len(srows)}")
    print(f"领域信号命中>0 且语料有候选块的题: {evalable}")
    print(f"落盘 screen={OUT_JSONL}")
    return 0


def _extract_domain_signals(g: dict[str, object]) -> dict[str, object]:
    """从题目与答案中提取与故障诊断/检索强相关的领域信号词（子串级匹配用）。

    信号词 = 域实体（ISO 标准、型号、SPB 消息、诊断术语、部件名、作业词）。
    这里返回规范化词及其类别；主函数做大小写/空格归一后做子串命中。
    """
    text = " ".join(g.get("answer_points", [])) + " " + g.get("question", "")
    norm = text.replace(" ", "").upper()
    sig_map: dict[str, dict] = {}  # canon -> {kind, orig}
    def add(canon: str, kind: str) -> None:
        canon = canon.replace(" ", "").upper()
        if canon:
            sig_map.setdefault(canon, {"canon": canon, "kind": kind})
    # —— 规范化标识符 / 协议 / 标准 ——
    for tok in ["BGF-E", "BGEO", "GMF", "NPSH", "PLAN11", "Plan11"]:
        pass
    specs = ["ISO10816", "ISO20816", "ISO2954", "ISO1940", "ISO4406", "SPARKPLUGB"]
    for s in specs:
        if s in norm:
            add(s, "spec")
    msg = ["NBIRTH", "NDEATH", "NDATA", "DBIRTH", "DDEATH", "DDATA", "STATE", "RE-BIRTH", "REBIRTH"]
    for m in msg:
        if m in norm:
            add(m, "spb")
    terms = ["BPFO", "BPFI", "FTF", "BSF", "振动烈度", "轴承温度", "联轴器", "不对中",
             "不平衡", "松动", "气蚀", "汽蚀", "轴承", "电机", "叶轮", "密封", "润滑油",
             "齿轮箱", "点检", "包络", "上锁挂牌", "动火", "动平衡", "测点", "加速度计",
             "油液", "光谱", "铁谱", "颗粒计数", "轴频", "边频", "谐振", "阀门"]
    for t in terms:
        if t.replace(" ", "").upper() in norm:
            add(t, "term")
    # 好消息：term 里含中文，规范化的 `.upper()` 不影响中文子串
    # 但 mid 命中要用原始中文，故 return 时保留 original
    signals = [{"canon": s["canon"], "kind": s["kind"]} for s in sig_map.values()]
    return {"signals": signals}


if __name__ == "__main__":
    sys.exit(main())