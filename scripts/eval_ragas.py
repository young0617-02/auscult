# -*- coding: utf-8 -*-
"""P5-W1/D1 RAGAS 评测接入（评测体系硬化）

针对评测集跑 RAGAS 四指标：

    faithfulness（忠实度）/ answer_relevancy（答案相关性）
    context_precision（上下文精确度）/ context_recall（上下文召回覆盖）

评测集口径（P5-W1 定案）：
  - 默认 `evals/m2_acc_set.jsonl`（12 题配套集，relevant_chunk_ids 与现语料 chunks_v1
    匹配；P5 已补 answer_points 参考答案，来源见各题 answer_points_source 字段）
  - `--eval-set evals/golden_set_v1.jsonl` 可切 golden 50 题，但其 relevant_chunk_ids
    指向未建的扩充语料（0 命中现语料），维持「待扩语料后重评」的 Phase 2 收口约束，
    当前仅作结构验证用

链路口径（plan/Phase 5 §5.1.1 + Q3 定案）：
  - contexts   ：W1→W5 检索管线（RetrievalService，RRF-only，D7 消融结论 rerank 净效果为负）
  - response   ：本地 Ollama `--gen-model`（默认 qwen2.5:7b）基于 contexts 生成
  - reference  ：评测集 answer_points 拼接
  - judge/embeddings：RAGAS LLM judge = 本地 Ollama qwen2.5:7b（Q3=A，零成本离线）；
                      embeddings = 本地 BGE-M3（与检索同源，ModelScope 路径）
  - 兼容性     ：ragas 0.4.3 与 langchain-community 0.4.2 存在 vertexai 导入不兼容，
                以 sys.modules 垫片修复（不动 site-packages）

**局限声明（判据口径）**：所有指标基于模拟数据（模拟语料 + 本地 7B 生成与 judge），
仅作本地验证，不代表生产级评测结论。

用法：
    .venv\\Scripts\\python.exe scripts\\eval_ragas.py             # 全量配套集 12 题
    .venv\\Scripts\\python.exe scripts\\eval_ragas.py --cases 2   # 冒烟
落盘：experiments/p5/w1/RAW-ragas.jsonl + meta-ragas.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import types
import urllib.request
from datetime import datetime, timezone
from importlib.metadata import version as _pkg_version
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

GOLDEN_SET = PROJECT_ROOT / "evals" / "golden_set_v1.jsonl"
EVAL_SET_DEFAULT = PROJECT_ROOT / "evals" / "m2_acc_set.jsonl"
OUT_DIR = PROJECT_ROOT / "experiments" / "p5" / "w1"
RAW = OUT_DIR / "RAW-ragas.jsonl"
META = OUT_DIR / "meta-ragas.json"

OLLAMA_BASE = "http://127.0.0.1:11434"


# ---------------------------------------------------------------- ragas 兼容垫片

def _patch_vertexai() -> None:
    """垫片：langchain-community 0.4.x 移除了 chat_models.vertexai，
    ragas 0.4.3 的 ragas/llms/base.py 仍无条件导入 → 注入占位模块（本评测用不到它）。"""
    try:
        import langchain_community.chat_models.vertexai  # noqa: F401, PLC0415
    except ModuleNotFoundError:
        stub = types.ModuleType("langchain_community.chat_models.vertexai")
        stub.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules["langchain_community.chat_models.vertexai"] = stub


# ---------------------------------------------------------------- Ollama 预检

def _preflight_ollama(model: str) -> None:
    """确认 Ollama 可达且模型已拉取，快速失败。"""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"[预检失败] Ollama 不可达（{OLLAMA_BASE}）: {exc}") from exc
    names = {m.get("name", "") for m in tags.get("models", [])}
    if model not in names and model.split(":")[0] not in {n.split(":")[0] for n in names}:
        raise SystemExit(f"[预检失败] Ollama 无模型 {model}，现有: {sorted(names)}")
    print(f"[预检] Ollama OK，模型 {model} 在位")


# ---------------------------------------------------------------- 生成回答

_GEN_SYSTEM = (
    "你是工业设备故障诊断助手。仅根据给定的知识片段回答问题，"
    "不得编造片段之外的信息；若片段不足以回答，明确说明「依据不足」。"
    "用中文简洁回答（200 字以内）。"
)


def _build_ctx_block(contexts: list[str]) -> str:
    return "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(contexts))


def generate_answer(llm, question: str, contexts: list[str]) -> str:
    """用本地 LLM 基于 contexts 生成回答（response 供 faithfulness/answer_relevancy）。"""
    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415

    user = f"【知识片段】\n{_build_ctx_block(contexts)}\n\n【问题】{question}"
    resp = llm.invoke([SystemMessage(content=_GEN_SYSTEM),
                       HumanMessage(content=user)])
    return resp.content.strip()


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="P5-W1 RAGAS 评测（配套集/golden）")
    ap.add_argument("--eval-set", type=Path, default=EVAL_SET_DEFAULT,
                    help="评测集 jsonl（默认 m2_acc_set 12 题配套集；golden 50 待扩语料）")
    ap.add_argument("--cases", type=int, default=0, help=">0 只评测前 N 条（冒烟）")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--rerank", action="store_true",
                    help="启用重排（默认关：D7 消融 RRF-only 为生产口径）")
    ap.add_argument("--gen-model", default="qwen2.5:7b", help="回答生成模型")
    ap.add_argument("--judge-model", default="qwen2.5:7b", help="RAGAS judge 模型（Q3=A）")
    ap.add_argument("--max-workers", type=int, default=2, help="RAGAS 并发（护本地 7B）")
    args = ap.parse_args()

    _preflight_ollama(args.judge_model)
    if args.gen_model != args.judge_model:
        _preflight_ollama(args.gen_model)

    _patch_vertexai()
    from langchain_huggingface import HuggingFaceEmbeddings      # noqa: PLC0415
    from langchain_ollama import ChatOllama                      # noqa: PLC0415
    from ragas import evaluate                                   # noqa: PLC0415
    from ragas.embeddings import LangchainEmbeddingsWrapper      # noqa: PLC0415
    from ragas.evaluation import EvaluationDataset               # noqa: PLC0415
    from ragas.llms import LangchainLLMWrapper                   # noqa: PLC0415
    from ragas.metrics import (                                  # noqa: PLC0415
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    from ragas.run_config import RunConfig                       # noqa: PLC0415

    from retrieve_knowledge import RetrievalService              # noqa: PLC0415
    from run_v2 import BGE_M3_MODEL_PATH                         # noqa: PLC0415

    eval_set = args.eval_set if args.eval_set.is_absolute() else PROJECT_ROOT / args.eval_set
    cases = [json.loads(l) for l in
             eval_set.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.cases:
        cases = cases[: args.cases]
    print(f"[加载] {eval_set.name} {len(cases)} 题（top_k={args.top_k}，"
          f"rerank={args.rerank}，gen={args.gen_model}，judge={args.judge_model}）")

    # 1) 检索 + 生成（逐题串联，冷启动预热一次）
    svc = RetrievalService(top_k=args.top_k, mode="rules",
                           use_rerank=args.rerank, device=args.device)
    _ = svc.retrieve(cases[0]["question"])          # 预热：模型/索引加载不计延迟
    time.sleep(0.1)

    gen_llm = ChatOllama(model=args.gen_model, base_url=OLLAMA_BASE,
                         temperature=0.0, num_ctx=8192)

    rows: list[dict] = []
    for c in cases:
        t0 = time.perf_counter()
        r = svc.retrieve(c["question"])
        chunk_ids = [it.get("chunk_id", "") for it in r["items"]]
        contexts = [str(it.get("content") or "") for it in r["items"]]
        answer = generate_answer(gen_llm, c["question"], contexts)
        rows.append({
            "qid": c["qid"],
            "category": c.get("category", ""),
            "question": c["question"],
            "reference": "；".join(c.get("answer_points", [])),
            "response": answer,
            "contexts": contexts,
            "retrieved_chunk_ids": chunk_ids,
            "relevant_chunk_ids": c.get("relevant_chunk_ids", []),
            "retrieval_latency_ms": r["latency"].get("total_ms", 0.0),
            "gen_latency_ms": round((time.perf_counter() - t0) * 1000, 1)
                              - r["latency"].get("total_ms", 0.0),
            "degraded": r["degraded"],
        })
        print(f"  [{c['qid']}] ctx={len(contexts)} 生成 {len(answer)} 字")

    # 2) RAGAS evaluate（judge + embeddings 全本地）
    judge = LangchainLLMWrapper(ChatOllama(
        model=args.judge_model, base_url=OLLAMA_BASE,
        temperature=0.0, num_ctx=8192))
    embeddings = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(
        model_name=str(BGE_M3_MODEL_PATH),
        model_kwargs={"device": args.device},
        encode_kwargs={"normalize_embeddings": True}))

    dataset = EvaluationDataset.from_list([
        {"user_input": r["question"],
         "retrieved_contexts": r["contexts"],
         "response": r["response"],
         "reference": r["reference"]}
        for r in rows
    ])
    metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
    print(f"[RAGAS] 评测 {len(rows)} 题 × {len(metrics)} 指标（judge 并发={args.max_workers}）…")
    t0 = time.perf_counter()
    result = evaluate(
        dataset,
        metrics=metrics,
        llm=judge,
        embeddings=embeddings,
        run_config=RunConfig(max_workers=args.max_workers, timeout=300),
        raise_exceptions=False,
        show_progress=True,
    )
    ragas_elapsed = round(time.perf_counter() - t0, 1)

    scores: list[dict] = list(result.scores)      # 与 dataset 行序对齐
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with RAW.open("w", encoding="utf-8") as f:
        for r, sc in zip(rows, scores):
            f.write(json.dumps({**r, "ragas_scores": sc}, ensure_ascii=False) + "\n")

    # 3) 汇总
    avg = {}
    for m in metrics:
        vals = [sc.get(m.name) for sc in scores
                if isinstance(sc, dict) and isinstance(sc.get(m.name), (int, float))]
        avg[m.name] = round(sum(vals) / len(vals), 4) if vals else None

    meta = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "eval_set": eval_set.name,
        "n_cases": len(rows),
        "top_k": args.top_k,
        "use_rerank": args.rerank,
        "gen_model": args.gen_model,
        "judge_model": args.judge_model,
        "embeddings": "BAAI/bge-m3 (local)",
        "versions": {"ragas": _pkg_version("ragas"),
                     "langchain_core": _pkg_version("langchain-core")},
        "ragas_elapsed_sec": ragas_elapsed,
        "avg_scores": avg,
        "degraded_cases": [r["qid"] for r in rows if r["degraded"]],
        "scope_statement": "基于模拟数据（模拟语料 + 本地 7B 生成与 judge）的初步验证，"
                           "不代表生产级评测结论",
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== RAGAS 结果（模拟数据口径）=====")
    for k, v in avg.items():
        print(f"  {k:20s} {v}")
    print(f"  ragas 耗时 {ragas_elapsed}s")
    print(f"落盘 RAW={RAW}")
    print(f"     META={META}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
