# -*- coding: utf-8 -*-
"""P5-W1/D4 幻觉率实测（3 级评分）

判据（plan/Phase 5 §5.1.3）：
  A 充分依据 —— 每条结论均可溯源到证据          → 非幻觉
  B 部分依据 —— 主结论有依据，细节有外推        → 非幻觉（记警告）
  C 无依据   —— 存在无法溯源的结论（幻觉）      → 判为幻觉

  幻觉率 = C 级数量 / 总数 → 目标 ≤ 10%

评分者口径（Q1=A 精神延伸）：单人项目，3 级评分由本地 LLM（qwen2.5:7b，温度 0）
执行；首判 C 的条目做**独立复核**（逐句核对式二次判定，防 judge 误判）——复核翻案
则保守降为 B 并双判定留痕。**局限声明**：评分者为本地 LLM 非真人，结论基于模拟数据。

输入：experiments/p5/w1/RAW-ragas.jsonl（复用 D1 的 response + contexts，不重跑生成）
输出：RAW-hallucination.jsonl + meta-hallucination.json + reports/p5-hallucination.md 数据源

用法：
    .venv\\Scripts\\python.exe scripts\\eval_hallucination.py             # 全量 12 题
    .venv\\Scripts\\python.exe scripts\\eval_hallucination.py --cases 2   # 冒烟
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

RAW_RAGAS = PROJECT_ROOT / "experiments" / "p5" / "w1" / "RAW-ragas.jsonl"
OUT_DIR = PROJECT_ROOT / "experiments" / "p5" / "w1"
RAW_OUT = OUT_DIR / "RAW-hallucination.jsonl"
META_OUT = OUT_DIR / "meta-hallucination.json"

OLLAMA_BASE = "http://127.0.0.1:11434"
DEFAULT_JUDGE = "qwen2.5:7b"

_JSON_DECODER = json.JSONDecoder()


def _extract_json(text: str) -> dict | None:
    """从文本中提取第一个顶层 JSON 对象（容忍围栏/说明文字）。"""
    idx = 0
    while True:
        start = text.find("{", idx)
        if start < 0:
            break
        try:
            obj, _ = _JSON_DECODER.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = start + 1
    return None


# ---------------------------------------------------------------- judge prompts

_JUDGE_SYSTEM = (
    "你是严格的评测标注员，负责幻觉分级。对照知识片段核查回答中的每一条结论：\n"
    "- A 充分依据：每条结论都能在片段中找到直接依据（允许同义改写，数值必须一致）\n"
    "- B 部分依据：主结论有依据，但个别细节是外推/常识补充，片段中无直接文字\n"
    "- C 无依据：存在片段完全无法支撑的结论（即幻觉）\n"
    "只输出 JSON：{\"grade\":\"A|B|C\",\"unsupported\":[\"无依据的结论原文\"],\"reason\":\"一句话理由\"}"
)

_RECHECK_SYSTEM = (
    "你是独立复核员。请逐句核对回答中的每个结论，判断是否能在知识片段中找到原文依据。"
    "只要存在任何一句无法找到依据的结论，必须判 C；全部能找到但个别细节为合理外推判 B；"
    "每句都有直接依据判 A。\n"
    "只输出 JSON：{\"grade\":\"A|B|C\",\"unsupported\":[\"...\"],\"reason\":\"...\"}"
)


def _build_user_payload(row: dict) -> str:
    ctx = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(row["contexts"]))
    return (f"【问题】{row['question']}\n\n【回答】{row['response']}\n\n"
            f"【知识片段】\n{ctx}")


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="P5-W1 幻觉率 3 级评分（LLM 辅助）")
    ap.add_argument("--cases", type=int, default=0, help=">0 只评前 N 条（冒烟）")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE)
    ap.add_argument("--num-ctx", type=int, default=8192)
    args = ap.parse_args()

    if not RAW_RAGAS.exists():
        raise SystemExit(f"[缺输入] {RAW_RAGAS} 不存在——先跑 eval_ragas.py")
    rows = [json.loads(l) for l in RAW_RAGAS.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    if args.cases:
        rows = rows[: args.cases]
    print(f"[加载] RAW-ragas {len(rows)} 条（judge={args.judge_model}，温度 0）")

    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415
    from langchain_ollama import ChatOllama  # noqa: PLC0415

    judge = ChatOllama(model=args.judge_model, base_url=OLLAMA_BASE,
                       temperature=0.0, num_ctx=args.num_ctx)
    payload = _build_user_payload(rows[0])
    _ = judge.invoke([SystemMessage(content=_JUDGE_SYSTEM), HumanMessage(content=payload)])
    print("[预热] judge 冷启动完成")

    out_rows: list[dict] = []
    for r in rows:
        payload = _build_user_payload(r)
        t0 = datetime.now(timezone.utc)
        resp = judge.invoke([SystemMessage(content=_JUDGE_SYSTEM),
                             HumanMessage(content=payload)])
        first = _extract_json(resp.content) or {}
        grade = str(first.get("grade", "")).upper()
        recheck = None
        if grade == "C":
            # 首判 C → 独立复核（逐句核对口径），翻案保守降为 B 并双判定留痕
            resp2 = judge.invoke([SystemMessage(content=_RECHECK_SYSTEM),
                                  HumanMessage(content=payload)])
            recheck = _extract_json(resp2.content) or {}
            if str(recheck.get("grade", "")).upper() != "C":
                grade = "B"
        final = grade if grade in {"A", "B", "C"} else "C"
        out_rows.append({
            "qid": r["qid"],
            "question": r["question"],
            "grade_first": str(first.get("grade", "")).upper(),
            "recheck": recheck,
            "grade_final": final,
            "unsupported_first": first.get("unsupported", []),
            "reason_first": first.get("reason", ""),
            "response": r["response"],
            "ts": t0.isoformat(),
        })
        print(f"  [{r['qid']}] 首判={out_rows[-1]['grade_first']} "
              f"终判={final}  {out_rows[-1]['reason_first'][:40]}")

    counts = {"A": 0, "B": 0, "C": 0}
    for o in out_rows:
        counts[o["grade_final"]] += 1
    n = len(out_rows)
    halluc_rate = round(counts["C"] / n, 4) if n else None
    gate = "Pass" if halluc_rate is not None and halluc_rate <= 0.10 else "Fail"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with RAW_OUT.open("w", encoding="utf-8") as f:
        for o in out_rows:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    meta = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "experiments/p5/w1/RAW-ragas.jsonl",
        "n_cases": n,
        "judge_model": args.judge_model,
        "judge_temperature": 0.0,
        "recheck_policy": "首判 C → 逐句核对式独立复核；翻案保守降 B，双判定留痕",
        "counts": counts,
        "hallucination_rate": halluc_rate,
        "gate_target": "≤ 0.10",
        "gate": gate,
        "scope_statement": "评分者为本地 LLM（qwen2.5:7b）非真人（Q1=A 精神延伸）；"
                           "基于模拟语料与本地 7B 生成的初步验证，不代表生产级结论",
    }
    META_OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 幻觉率（3 级评分）=====")
    print(f"  A 充分依据 {counts['A']} ｜ B 部分依据 {counts['B']} ｜ C 无依据 {counts['C']}")
    print(f"  幻觉率 = {halluc_rate}（判据 ≤ 0.10 → {gate}）")
    print(f"落盘 RAW={RAW_OUT}\n     META={META_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
