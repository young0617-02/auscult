# -*- coding: utf-8 -*-
"""P5-W1/D5 端到端指标 + 置信度 ECE

三块指标（plan/Phase 5 §7.1）：
  1. P95 检索 / P95 端到端（本地路径）——汇总 D1 RAGAS RAW 的逐题延迟
     （retrieval_latency_ms / gen_latency_ms；端到端 = 检索 + 生成，全本地路径）
  2. 工具首次成功率 —— 检索工具（retrieve_knowledge）执行口径：
     首次调用即「非降级且返回 ≥1 命中」视为成功；成功率 ≥ 90% 判据
  3. 置信度 ECE ≤ 0.10 —— 12 题重跑生成（要求模型输出 answer + self_confidence），
     judge 按 answer_points 严格判定正确性（覆盖全部要点且数值精确 → correct），
     ECE 用 5 桶分桶（样本量 12，10 桶过稀）；复用 diagnose.compute_ece 同款算法

**局限声明**：ECE 基于 12 题模拟数据 + 本地 7B 自评置信度（非校准后概率），
仅作初步验证；P95 端到端口径为「检索 + 本地 7B 生成」知识问答全链路，
诊断编排链路（LangGraph）口径不同，另行统计。

用法：
    .venv\\Scripts\\python.exe scripts\\eval_e2e.py             # 全量 12 题
    .venv\\Scripts\\python.exe scripts\\eval_e2e.py --cases 2   # 冒烟
    .venv\\Scripts\\python.exe scripts\\eval_e2e.py --skip-ece  # 只汇总延迟/成功率
落盘：experiments/p5/w1/RAW-e2e.jsonl + meta-e2e.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

RAW_RAGAS = PROJECT_ROOT / "experiments" / "p5" / "w1" / "RAW-ragas.jsonl"
EVAL_SET_DEFAULT = PROJECT_ROOT / "evals" / "m2_acc_set.jsonl"
OUT_DIR = PROJECT_ROOT / "experiments" / "p5" / "w1"
RAW_OUT = OUT_DIR / "RAW-e2e.jsonl"
META_OUT = OUT_DIR / "meta-e2e.json"

OLLAMA_BASE = "http://127.0.0.1:11434"
JSON_DECODER = json.JSONDecoder()


def extract_json(text: str) -> dict | None:
    idx = 0
    while True:
        start = text.find("{", idx)
        if start < 0:
            break
        try:
            obj, _ = JSON_DECODER.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = start + 1
    return None


def percentile(values: list[float], p: float) -> float:
    """线性插值分位（与 eval_m2 同款口径）。"""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return round(s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f), 1)


def preflight_ollama(model: str) -> None:
    with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5) as resp:
        tags = json.loads(resp.read().decode("utf-8"))
    names = {m.get("name", "") for m in tags.get("models", [])}
    if model not in names and model.split(":")[0] not in {n.split(":")[0] for n in names}:
        raise SystemExit(f"[预检失败] Ollama 无模型 {model}，现有: {sorted(names)}")


# ---------------------------------------------------------------- ECE（与 diagnose.compute_ece 同款）

def compute_ece(predictions: list[tuple[float, bool]], n_bins: int = 5) -> float:
    if not predictions:
        return 1.0
    bin_size = 1.0 / n_bins
    ece = 0.0
    for i in range(n_bins):
        lo, hi = i * bin_size, (i + 1) * bin_size
        bin_items = [(c, r) for c, r in predictions
                     if lo <= c < hi or (i == n_bins - 1 and c == 1.0)]
        if not bin_items:
            continue
        avg_conf = sum(c for c, _ in bin_items) / len(bin_items)
        avg_acc = sum(1 for _, r in bin_items if r) / len(bin_items)
        ece += abs(avg_conf - avg_acc) * len(bin_items) / len(predictions)
    return round(ece, 4)


# ---------------------------------------------------------------- 生成（带自评置信度）

_GEN_SYSTEM = (
    "你是工业设备故障诊断助手。仅根据给定的知识片段回答问题，不得编造片段之外的信息；"
    "若片段不足以回答，在 answer 中明确说明「依据不足」。"
    "回答用中文简洁（200 字以内）。同时给出 self_confidence ∈ [0,1]，"
    "表示你确信本回答完整且正确的程度（0=完全不确定，1=完全确信）。\n"
    "只输出 JSON：{\"answer\":\"...\",\"self_confidence\":0.75}"
)


def gen_with_confidence(llm, question: str, contexts: list[str]) -> tuple[str, float]:
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    ctx = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))
    user = f"【知识片段】\n{ctx}\n\n【问题】{question}"
    resp = llm.invoke([SystemMessage(content=_GEN_SYSTEM), HumanMessage(content=user)])
    obj = extract_json(resp.content) or {}
    ans = str(obj.get("answer", "")).strip() or resp.content.strip()[:300]
    try:
        conf = max(0.0, min(1.0, float(obj.get("self_confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return ans, conf


# ---------------------------------------------------------------- 正确性 judge

_JUDGE_SYSTEM = (
    "你是评测判定员。判断回答是否覆盖了全部期望要点：语义覆盖允许同义改写，"
    "但数值（阈值/周期/频率/范围）必须精确一致；多要点需全部覆盖。"
    "任一要点缺失、语义不符或数值错误 → correct=false。\n"
    "只输出 JSON：{\"correct\":true|false,\"missing\":[\"未覆盖要点\"],\"reason\":\"一句话\"}"
)


def judge_correctness(llm, question: str, answer_points: list[str], answer: str) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    pts = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(answer_points))
    user = f"【问题】{question}\n\n【期望要点】\n{pts}\n\n【回答】{answer}"
    resp = llm.invoke([SystemMessage(content=_JUDGE_SYSTEM), HumanMessage(content=user)])
    obj = extract_json(resp.content) or {}
    return {"correct": bool(obj.get("correct", False)),
            "missing": obj.get("missing", []),
            "reason": str(obj.get("reason", ""))[:80]}


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="P5-W1 端到端指标 + ECE")
    ap.add_argument("--cases", type=int, default=0, help=">0 只跑前 N 条（冒烟）")
    ap.add_argument("--skip-ece", action="store_true", help="只汇总延迟/成功率（不重跑生成）")
    ap.add_argument("--gen-model", default="qwen2.5:7b")
    ap.add_argument("--judge-model", default="qwen2.5:7b")
    ap.add_argument("--num-ctx", type=int, default=8192)
    args = ap.parse_args()

    if not RAW_RAGAS.exists():
        raise SystemExit(f"[缺输入] {RAW_RAGAS} 不存在——先跑 eval_ragas.py")
    ragas_rows = [json.loads(l) for l in RAW_RAGAS.read_text(encoding="utf-8").splitlines()
                  if l.strip()]
    if args.cases:
        ragas_rows = ragas_rows[: args.cases]

    # ---- ① 延迟汇总（检索 / 端到端 = 检索+生成，全本地路径）
    retr_ms = [r["retrieval_latency_ms"] for r in ragas_rows]
    e2e_ms = [r["retrieval_latency_ms"] + r["gen_latency_ms"] for r in ragas_rows]
    latency = {
        "n": len(ragas_rows),
        "retrieval": {"p50": percentile(retr_ms, 0.50), "p95": percentile(retr_ms, 0.95)},
        "e2e_local": {"p50": percentile(e2e_ms, 0.50), "p95": percentile(e2e_ms, 0.95),
                      "mean": round(sum(e2e_ms) / len(e2e_ms), 1)},
    }

    # ---- ② 工具首次成功率（retrieve_knowledge 执行口径：非降级且 ≥1 命中）
    n_ok = sum(1 for r in ragas_rows
               if not r["degraded"] and len(r.get("retrieved_chunk_ids", [])) > 0)
    tool_first_rate = round(n_ok / len(ragas_rows), 4) if ragas_rows else None

    print(f"[延迟汇总] 检索 P50={latency['retrieval']['p50']}ms "
          f"P95={latency['retrieval']['p95']}ms ｜ 端到端 P50={latency['e2e_local']['p50']}ms "
          f"P95={latency['e2e_local']['p95']}ms")
    print(f"[工具首次成功率] {tool_first_rate}（{n_ok}/{len(ragas_rows)}）")

    meta: dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "experiments/p5/w1/RAW-ragas.jsonl",
        "n_cases": len(ragas_rows),
        "latency_local": latency,
        "tool_first_success_rate": tool_first_rate,
        "tool_first_success_rule": "retrieve_knowledge 首次调用即非降级且返回≥1命中",
        "gate_targets": {"p95_retrieval_ms": 800, "p95_e2e_local_ms": 3000,
                         "tool_first_success_rate": 0.90},
        "gate": {
            "p95_retrieval": "Pass" if latency["retrieval"]["p95"] < 800 else "Fail",
            "p95_e2e_local": "Pass" if latency["e2e_local"]["p95"] < 3000 else "Fail",
            "tool_first_success": "Pass" if tool_first_rate is not None
                                  and tool_first_rate >= 0.90 else "Fail",
        },
        "scope_statement": "基于模拟数据（模拟语料 + 本地 7B）的初步验证；"
                           "P95 端到端口径=检索+本地7B生成知识问答全链路，"
                           "诊断编排链路（LangGraph）口径不同另行统计",
    }

    # ---- ③ ECE（重跑生成带 self_confidence + judge 正确性）
    if not args.skip_ece:
        preflight_ollama(args.gen_model)
        preflight_ollama(args.judge_model)
        from langchain_ollama import ChatOllama  # noqa: PLC0415

        eval_set = EVAL_SET_DEFAULT
        cases = {c["qid"]: c for c in
                 (json.loads(l) for l in eval_set.read_text(encoding="utf-8").splitlines()
                  if l.strip())}
        gen_llm = ChatOllama(model=args.gen_model, base_url=OLLAMA_BASE,
                             temperature=0.0, num_ctx=args.num_ctx)
        judge_llm = ChatOllama(model=args.judge_model, base_url=OLLAMA_BASE,
                               temperature=0.0, num_ctx=args.num_ctx)
        _ = gen_with_confidence(gen_llm, ragas_rows[0]["question"],
                                ragas_rows[0]["contexts"])   # 预热
        print("[预热] 生成/judge 冷启动完成")

        ece_rows: list[dict] = []
        for r in ragas_rows:
            c = cases.get(r["qid"], {})
            points = c.get("answer_points", [])
            t0 = time.perf_counter()
            ans, conf = gen_with_confidence(gen_llm, r["question"], r["contexts"])
            gen_ms = round((time.perf_counter() - t0) * 1000, 1)
            verdict = judge_correctness(judge_llm, r["question"], points, ans)
            ece_rows.append({
                "qid": r["qid"], "answer": ans, "self_confidence": conf,
                "correct": verdict["correct"], "missing": verdict["missing"],
                "reason": verdict["reason"], "gen_latency_ms": gen_ms,
                "n_answer_points": len(points),
            })
            print(f"  [{r['qid']}] conf={conf:.2f} correct={verdict['correct']} "
                  f"gen={gen_ms}ms  {verdict['reason'][:36]}")

        preds = [(row["self_confidence"], row["correct"]) for row in ece_rows]
        ece = compute_ece(preds, n_bins=5)
        acc = round(sum(1 for _, ok in preds if ok) / len(preds), 4) if preds else None
        meta["ece"] = {"ece": ece, "n_bins": 5, "accuracy": acc,
                       "gate": "Pass" if ece <= 0.10 else "Fail",
                       "note": "样本量 12，5 桶；自评置信度未做温度校准"}
        RAW_OUT.write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in ece_rows) + "\n",
            encoding="utf-8")
        print(f"\n[ECE] ece={ece}  acc={acc}  判据 ≤0.10 → {meta['ece']['gate']}")

    META_OUT.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"落盘 META={META_OUT}" + ("" if args.skip_ece else f"  RAW={RAW_OUT}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
