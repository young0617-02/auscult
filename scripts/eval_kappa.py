# -*- coding: utf-8 -*-
"""P5-W1/D2 双人标注一致性（Cohen's Kappa）

口径（plan/Phase 5 §5.1.2 + Q1=A 定案）：
  - 标注任务：对 golden 50 题的 top-5 检索候选逐条判定「与问题是否相关」（二值）
  - 标注者 A：golden 集 `relevant_chunk_ids`（Phase 0/2 人工主标注）
  - 标注者 B：本地 Ollama qwen2.5:7b（第二标注，零成本离线）
              —— 报告须显式声明局限：B 为本地 LLM，非真人
  - 一致性：Cohen's κ = (Po - Pe) / (1 - Pe)
      κ ≥ 0.7 可接受；0.4–0.7 复核争议项；< 0.4 标注规范需重订

用法：
    .venv\\Scripts\\python.exe scripts\\eval_kappa.py             # 全量 50 题
    .venv\\Scripts\\python.exe scripts\\eval_kappa.py --cases 2   # 冒烟
落盘：experiments/p5/w1/RAW-kappa.jsonl + meta-kappa.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

GOLDEN_SET = PROJECT_ROOT / "evals" / "golden_set_v1.jsonl"
EVAL_SET_DEFAULT = PROJECT_ROOT / "evals" / "m2_acc_set.jsonl"
OUT_DIR = PROJECT_ROOT / "experiments" / "p5" / "w1"
RAW = OUT_DIR / "RAW-kappa.jsonl"
META = OUT_DIR / "meta-kappa.json"

OLLAMA_BASE = "http://127.0.0.1:11434"
MODEL = "qwen2.5:7b"


# ---------------------------------------------------------------- 标注 B（LLM）

_JUDGE_SYSTEM = (
    "你是工业设备知识标注员。给定一个问题与若干候选知识片段（带编号），"
    "逐条判断该片段是否与问题相关。判定标准（从严）："
    "仅当片段包含回答该问题所需的**具体信息**（数值、限值、步骤、原因、"
    "处置方法、部件构成、关系等）时判 relevant=true；"
    "若片段仅是同主题的背景/邻近内容而不含具体答案要素，判 relevant=false。"
    "只输出严格 JSON，格式："
    '{"judgements": [{"idx": 1, "relevant": true}, ...]}，不要输出其他内容。'
)


def _judge_relevance(llm_url: str, question: str, chunks: list[str],
                     timeout: float = 120.0) -> list[bool]:
    """一次调用判定该题全部候选（省调用数）；解析失败按全 False 记并留痕。"""
    block = "\n".join(f"[{i + 1}] {c[:400]}" for i, c in enumerate(chunks))
    user = f"【问题】{question}\n\n【候选片段】\n{block}\n\n请逐条判定并输出 JSON。"
    payload = json.dumps({
        "model": MODEL, "stream": False, "temperature": 0.0,
        "options": {"num_ctx": 8192},
        "messages": [{"role": "system", "content": _JUDGE_SYSTEM},
                     {"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(llm_url, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = json.loads(resp.read().decode("utf-8"))["choices"][0]["message"]["content"]
        obj = json.loads(content[content.find("{"): content.rfind("}") + 1])
        by_idx = {int(j["idx"]): bool(j.get("relevant", False))
                  for j in obj.get("judgements", []) if str(j.get("idx", "")).lstrip("-").isdigit()}
        return [by_idx.get(i + 1, False) for i in range(len(chunks))]
    except Exception as exc:  # noqa: BLE001
        print(f"    [WARN] judge 解析失败按全不相关记: {exc}")
        return [False] * len(chunks)


# ---------------------------------------------------------------- Cohen's Kappa

def cohens_kappa(a: list[int], b: list[int]) -> tuple[float, float, float]:
    """二值标注 Cohen's κ。返回 (kappa, po, pe)。"""
    n = len(a)
    if n == 0:
        return 0.0, 0.0, 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = 0.0
    for cat in (0, 1):
        pa = a.count(cat) / n
        pb = b.count(cat) / n
        pe += pa * pb
    kappa = (po - pe) / (1 - pe) if pe < 1 else 0.0
    return round(kappa, 4), round(po, 4), round(pe, 4)


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="P5-W1 双人标注 κ（A=人工，B=本地 LLM）")
    ap.add_argument("--eval-set", type=Path, default=EVAL_SET_DEFAULT,
                    help="评测集 jsonl（默认 m2_acc_set 12 题配套集；golden 50 待扩语料）")
    ap.add_argument("--cases", type=int, default=0, help=">0 只标注前 N 条（冒烟）")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    eval_set = args.eval_set if args.eval_set.is_absolute() else PROJECT_ROOT / args.eval_set
    cases = [json.loads(l) for l in
             eval_set.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.cases:
        cases = cases[: args.cases]
    # 标注 A 口径：优先完备相关集（L3+L2，P5-κ 规范修订后补标），回退原最小锚点
    label_field = ("relevant_chunk_ids_full"
                   if all("relevant_chunk_ids_full" in c for c in cases)
                   else "relevant_chunk_ids")
    print(f"[加载] {eval_set.name} {len(cases)} 题（top_k={args.top_k}，B={MODEL}，"
          f"A 字段={label_field}）")

    from retrieve_knowledge import RetrievalService  # noqa: PLC0415
    svc = RetrievalService(top_k=args.top_k, mode="rules", use_rerank=False,
                           device=args.device)
    _ = svc.retrieve(cases[0]["question"])           # 预热
    time.sleep(0.1)

    llm_url = f"{OLLAMA_BASE}/v1/chat/completions"
    rows: list[dict] = []
    label_a: list[int] = []
    label_b: list[int] = []
    for c in cases:
        rel = set(c.get(label_field, c.get("relevant_chunk_ids", [])))
        r = svc.retrieve(c["question"])
        items = r["items"][: args.top_k]
        chunk_ids = [it.get("chunk_id", "") for it in items]
        chunks = [str(it.get("content") or "") for it in items]
        a = [1 if cid in rel else 0 for cid in chunk_ids]
        b = _judge_relevance(llm_url, c["question"], chunks)
        label_a.extend(a)
        label_b.extend(b)
        rows.append({
            "qid": c["qid"], "question": c["question"],
            "relevant_chunk_ids": sorted(rel),
            "candidates": [{"chunk_id": cid, "label_a": x, "label_b": y}
                           for cid, x, y in zip(chunk_ids, a, b)],
        })
        print(f"  [{c['qid']}] A={sum(a)}/{len(a)} 命中  B={sum(b)}/{len(b)} 相关")

    kappa, po, pe = cohens_kappa(label_a, label_b)

    # 争议项（A≠B）逐条留痕
    disputes = []
    for row in rows:
        for cand in row["candidates"]:
            if cand["label_a"] != cand["label_b"]:
                disputes.append({"qid": row["qid"], **cand})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with RAW.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    band = ("可接受" if kappa >= 0.7 else
            "需复核争议项" if kappa >= 0.4 else "标注规范需重订")
    meta = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "eval_set": eval_set.name,
        "n_questions": len(rows),
        "n_pairs": len(label_a),
        "annotator_a": f"{eval_set.name}.{label_field}"
                       f"（人工主标注·{'完备相关集 L3+L2（P5-κ 规范修订后补标）' if label_field == 'relevant_chunk_ids_full' else '最小锚点'}）",
        "annotator_b": f"Ollama {MODEL}（本地 LLM 第二标注，非真人——局限声明）",
        "top_k": args.top_k,
        "use_rerank": False,
        "po": po, "pe": pe, "kappa": kappa,
        "band": band,
        "confusion": {
            "a1_b1": sum(1 for x, y in zip(label_a, label_b) if x == 1 and y == 1),
            "a1_b0": sum(1 for x, y in zip(label_a, label_b) if x == 1 and y == 0),
            "a0_b1": sum(1 for x, y in zip(label_a, label_b) if x == 0 and y == 1),
            "a0_b0": sum(1 for x, y in zip(label_a, label_b) if x == 0 and y == 0),
        },
        "n_disputes": len(disputes),
        "disputes": disputes,
        "scope_statement": "B 标注者为本地 LLM（qwen2.5:7b）非真人，κ 结论仅表征人工标注与"
                           "本地 LLM 判定的一致性，基于模拟数据，不代表双人真⼈标注一致性",
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== Cohen's Kappa（A=人工，B=本地 LLM）=====")
    print(f"  标注对数 {len(label_a)}  Po={po}  Pe={pe}")
    print(f"  κ = {kappa}  （判据：{band}）")
    print(f"  混淆矩阵: a1b1={meta['confusion']['a1_b1']} a1b0={meta['confusion']['a1_b0']} "
          f"a0b1={meta['confusion']['a0_b1']} a0b0={meta['confusion']['a0_b0']}")
    print(f"  争议项 {len(disputes)} 条")
    print(f"落盘 RAW={RAW}")
    print(f"     META={META}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
