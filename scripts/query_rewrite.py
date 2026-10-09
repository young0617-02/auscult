"""W1 查询改写器（Phase 2 · 混合检索入口）

对应交付物：`plan/Phase 2 详细开发计划（混合检索）.md` §W1（P2-D1）
职责：把自然语言问题改写为 **三路检索输入**（semantic / keywords / entities），
      供 Dense / BM25 / 图谱 三路召回使用。

两档策略：
  - **规则快路径（默认）**：数字+单位、设备词/部件/参数正则 + jieba 分词取候选，
    零模型调用，满足 P95<800ms 与可解释性（`mode="rules"`）。
  - **LLM 增强（可选，`--llm`）**：复用 `scripts/llm_adapter.py` LLMAdapter，走云端
    约束解码（response_format json_schema），输出
    `{semantic, cause, keywords[], entities[]}`；结果按 (model, question) 落盘缓存
    `experiments/p2/w1/cache/*.jsonl`，二次同样输入**不重复调用**。

设计约束：
  - 仅依赖标准库 + jieba（requirements.txt 已锁 0.42.1）；LLM 路径复用 llm_adapter（urllib 实现）。
  - 工具边界：改写器自身**不访问任何检索库**（PG/Milvus/Neo4j），只产出改写结果；检索编排在调用方。
  - 实体词表优先复用 `run_v2.py::INDUSTRIAL_TERMS` 同源工业词（设备/部件/参数），避免词表漂移。

自检：`python scripts/query_rewrite.py --selftest`
用法：
  python scripts/query_rewrite.py --query "离心泵轴承箱振动烈度超标的故障原因" --mode rules
  python scripts/query_rewrite.py --query "..." --llm --endpoint <...> --model <...>
  python scripts/query_rewrite.py --file evals/golden_set_v1.jsonl --mode rules
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "experiments" / "p2" / "w1" / "cache"

# ★ 复用 run_v2.py 同源工业术语词表（设备/部件/参数），保证与检索侧词表对齐
INDUSTRIAL_TERMS: tuple[str, ...] = (
    "离心泵", "轴承箱", "机械密封", "联轴器", "叶轮", "泵轴", "驱动端", "非驱动端",
    "深沟球轴承", "圆柱滚子轴承", "汽轮机油", "振动烈度", "振动速度有效值", "位移峰峰值",
    "加速度包络", "特征频率", "转频", "倍频", "边带", "包络谱", "轴心轨迹",
    "内圈故障", "外圈故障", "滚动体", "保持架", "点蚀", "剥落", "磨损",
    "动平衡", "对中偏差", "软脚", "气蚀", "汽蚀余量", "喘振", "松动", "碰摩",
    "润滑油", "油品乳化", "铁谱分析", "红外测温", "状态监测", "故障诊断",
)

# 参数/监测量类（entities 分类为 parameter）
PARAM_TERMS: tuple[str, ...] = (
    "振动烈度", "振动速度有效值", "位移峰峰值", "加速度包络", "特征频率",
    "转频", "倍频", "边带", "包络谱", "轴心轨迹", "径向", "轴向", "转速", "电流", "温度",
    "振动", "压力", "流量", "电压", "功率", "效率", "温升", "油压", "油温",
)

# 设备/部件类（entities 分类为 equipment）
EQUIP_TERMS: tuple[str, ...] = (
    "离心泵", "轴承箱", "机械密封", "联轴器", "叶轮", "泵轴", "驱动端", "非驱动端",
    "深沟球轴承", "圆柱滚子轴承", "滚动体", "保持架", "电机", "冷却塔", "汽轮机",
)

# 故障/诊断类（entities 分类为 fault）
FAULT_TERMS: tuple[str, ...] = (
    "点蚀", "剥落", "磨损", "动平衡", "对中偏差", "软脚", "气蚀", "汽蚀余量", "喘振",
    "松动", "碰摩", "油品乳化", "内圈故障", "外圈故障", "故障", "异常", "超标", "失效", "烧毁",
)

# 数字+单位（用于 keywords 精化，如 "1.8 mm/s"）
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")

# LLM 增强输出的 JSON Schema（供 llm_adapter 约束解码；与 tools_v1.json 无重叠，独立 schema）
QUERY_REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "semantic": {"type": "string", "description": "保持业务语义的规整后查询"},
        "keywords": {"type": "array", "items": {"type": "string"},
                     "description": "面向 BM25 的中文检索关键词（设备/部件/参数/故障）"},
        "entities": {"type": "array",
                     "items": {"type": "object", "properties": {
                         "text": {"type": "string"},
                         "type": {"type": "string", "enum": ["equipment", "parameter", "fault"]}},
                         "required": ["text", "type"], "additionalProperties": False},
                     "description": "面向图谱的实体标记"},
    },
    "required": ["semantic", "keywords", "entities"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- 规则快路径


def _tokenize(text: str) -> list[str]:
    """分词：优先 jieba；不可用时按中文 n-gram + 词表匹配退回（保证无环境也能跑）。"""
    try:
        import jieba                                             # noqa: PLC0415
        return [t for t in jieba.lcut(text) if t.strip()]
    except ImportError:
        return _NUM_RE_and_unicode(text)


def _NUM_RE_and_unicode(text: str) -> list[str]:
    out: list[str] = []
    for frag in re.split(r"[，。、？\s]+", text):
        frag = frag.strip()
        if not frag:
            continue
        nums = _NUM_RE.findall(frag)
        core = _NUM_RE.sub("", frag)
        if core:
            out.append(core)
        out.extend(nums)
    return out


def rewrite_rules(question: str) -> dict[str, Any]:
    """规则快路径：不调用任何模型。

    返回 {semantic, keywords, entities, mode, cache_key, ts}
    """
    q = question.strip()
    tokens = _tokenize(q)

    # entities：扫描全部三类词表命中的实体（去重、保序）。词表之间可能有包含关系
    # （如「振动烈度」含「振动」），长词优先：先排序再按「已命中则不重复取子串」。
    _vocab: dict[str, str] = {}
    for t in PARAM_TERMS:
        _vocab[t] = "parameter"
    for t in EQUIP_TERMS:
        _vocab.setdefault(t, "equipment")
    for t in FAULT_TERMS:
        _vocab.setdefault(t, "fault")
    for t in INDUSTRIAL_TERMS:
        _vocab.setdefault(t, "equipment")

    entities: list[dict[str, str]] = []
    for term in sorted(_vocab, key=len, reverse=True):
        if term not in q:
            continue
        # 已被更长词覆盖则跳过（如「振动烈度」覆盖「振动」）
        if any(term in e["text"] for e in entities):
            continue
        entities.append({"text": term, "type": _vocab[term]})
    # 恢复语序：按原问出现顺序排序，避免词表顺序导致输出乱序
    entities.sort(key=lambda e: q.index(e["text"]))

    # 关键词 = 实体词表命中的文本 + 数值 token（面向 BM25；词表精确匹配，避免 jieba 切字丢失）
    numeric_tokens = [t for t in tokens if _NUM_RE.fullmatch(t)]
    keywords: list[str] = [e["text"] for e in entities]
    keywords.extend(numeric_tokens)
    # 去重保序
    seen_kw: set[str] = set()
    keywords = [k for k in keywords if not (k in seen_kw or seen_kw.add(k))]

    return {
        "semantic": q,
        "keywords": keywords,
        "entities": entities,
        "numeric": numeric_tokens,
        "mode": "rules",
        "ts": datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- 缓存


def cache_key(question: str, model: str | None) -> str:
    raw = f"{model or 'rules'}|{question}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def load_cache(question: str, model: str | None) -> dict[str, Any] | None:
    key = cache_key(question, model)
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(question: str, model: str | None, result: dict[str, Any]) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = cache_key(question, model)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------- LLM 增强


def rewrite_llm(question: str, endpoint: str, model: str,
                api_key: str, seed: int = 42) -> tuple[dict[str, Any], bool]:
    """走 llm_adapter 云端约束解码；命中缓存则直接返回 (result, from_cache=True)。

    返回 (改写结果 dict, 是否来自缓存)。失败时回退规则路径并置 flag。
    """
    cached = load_cache(question, model)
    if cached is not None:
        return cached, True

    from scripts.llm_adapter import LLMAdapter                     # noqa: PLC0415

    adapter = LLMAdapter(
        endpoint=endpoint, api_key=api_key, seed=seed,
        max_tokens=512, timeout_s=60.0,
        grammar=QUERY_REWRITE_SCHEMA, structured_output=True,
    )
    system = (
        "你是工业设备故障诊断检索的查询改写器。把用户的自然语言问题改写为三路检索输入："
        "semantic（保持业务语义的规整查询）、keywords（面向BM25的中文关键词，含设备/部件/参数/故障/数值），"
        "entities（面向知识图谱的实体，type∈equipment|parameter|fault）。不要编造原问题不存在的实体。"
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    res = adapter.chat(messages, model, use_tools=False)
    if res.error:
        return rewrite_rules(question), False
    try:
        data = json.loads(res.content_clean)
    except json.JSONDecodeError:
        return rewrite_rules(question), False
    result = {
        "semantic": data.get("semantic", question),
        "keywords": data.get("keywords", []),
        "entities": data.get("entities", []),
        "mode": "llm",
        "model": model,
        "cache_key": cache_key(question, model),
        "latency_ms": round(res.latency_ms, 1),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    save_cache(question, model, result)
    return result, False


# ---------------------------------------------------------------- 门面


def rewrite(question: str, mode: str = "rules",
            endpoint: str | None = None, model: str | None = None,
            api_key: str = "") -> dict[str, Any]:
    """统一入口。mode="rules" 走规则快路径；mode="llm" 走 LLM（含缓存）。"""
    if mode == "llm":
        if not endpoint or not model:
            raise ValueError("mode=llm 需提供 --endpoint 与 --model")
        result, _ = rewrite_llm(question, endpoint, model, api_key)
        return result
    return rewrite_rules(question)


# ---------------------------------------------------------------- 自检


_E2E_EXAMPLES = (
    ("离心泵驱动端振动烈度超标，轴承箱温度偏高，可能的原因有哪些？",
     [("离心泵", "equipment"), ("驱动端", "equipment"), ("振动烈度", "parameter"),
      ("轴承箱", "equipment"), ("温度", "parameter")]),
    ("机械密封渗漏与联轴器对中偏差是否存在关联？",
     [("机械密封", "equipment"), ("联轴器", "equipment"), ("对中偏差", "fault")]),
)


def _selftest() -> int:
    fail = 0

    # 1) 规则路径：实体抽取、semantic 保真
    for q, expected in _E2E_EXAMPLES:
        r = rewrite_rules(q)
        got = {(e["text"], e["type"]) for e in r["entities"]}
        exp = set(expected)
        missing = exp - got
        if missing:
            print(f"[FAIL] 实体抽取缺漏 q={q} missing={missing} got={r['entities']}")
            fail += 1
        if r["semantic"] != q.strip():
            print("[FAIL] semantic 应保持原问")
            fail += 1
        if not r["keywords"]:
            print(f"[FAIL] keywords 不应为空 q={q}")
            fail += 1

    # 2) 数值关键词
    r = rewrite_rules("振动烈度达到 11.2 mm/s 是否超标的判定阈值是多少？")
    if "11.2" not in r["keywords"] and "11.2" not in "".join(r["keywords"]):
        print(f"[FAIL] 数值关键词未抽取 q=...11.2... got_keywords={r['keywords']}")
        fail += 1

    # 3) 缓存：写入再读，命中
    probe = "缓存自检探针问题-查询改写"
    save_cache(probe, "selftest", {"mode": "rules", "semantic": probe})
    cached = load_cache(probe, "selftest")
    if cached is None or cached.get("semantic") != probe:
        print("[FAIL] 缓存写入/读取不一致")
        fail += 1
    else:
        print("[PASS] 缓存命中 100%")

    # 4) LLM 路径：约束解码 schema 字段齐全（离线不连接后端时仅验证结构；后端未就绪会回退）
    #    —— 自检不做真实网络请求，只验证脚本根目录可导入 llm_adapter（复用其 strip_think）。
    sys.path.insert(0, str(PROJECT_ROOT))
    from llm_adapter import strip_think                            # noqa: PLC0415
    _ = strip_think  # 保证导入路径可用（selftest 与本脚本同目录约定）

    print(f"[{'OK' if fail == 0 else 'FAIL'}] selftest 结束：失败 {fail} 项")
    return fail


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="W1 查询改写器")
    p.add_argument("--query", help="单条问题")
    p.add_argument("--file", help="jsonl 文件（每行含 question / chunk_id）")
    p.add_argument("--mode", choices=["rules", "llm"], default="rules")
    p.add_argument("--endpoint", help="LLM OpenAI 兼容端点")
    p.add_argument("--model", help="LLM 模型名")
    p.add_argument("--api-key", default="")
    p.add_argument("--selftest", action="store_true", help="运行自检")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.query:
        out = rewrite(args.query, args.mode, args.endpoint, args.model, args.api_key)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.file:
        path = PROJECT_ROOT / args.file
        results = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            q = row.get("question") or row.get("query") or ""
            if not q:
                continue
            r = rewrite(q, args.mode, args.endpoint, args.model, args.api_key)
            r["qid"] = row.get("qid", row.get("item_id", ""))
            results.append(r)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        print(f"\n共改写 {len(results)} 条 → 模式 {args.mode}")
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())