"""语料规模体检（`Material/02` §15 遗留"知识库语料为演示级" · 2026-10-22）。

**本脚本不灌数据**——`chunks/chunks_v1.jsonl` 是全部已锁定实验（EXP-P7-GATE*/V1 判据）
的语料基准，扩语料会平移基线、使历史数字不可比（"原始实验数据只增不改"纪律）。
它只回答三个问题，把"要不要扩、扩什么"的决策材料备齐：

  ① 现在有多少：chunks / parents / blobs / parsed 源文件 / token 总量；
  ② 覆盖了什么：设备型号分布 + 故障关键词命中（对照 `schemas/tools_v4.json`
     的 `fault_keywords` 语义域：轴承/齿轮/密封/叶轮/振动/温度/泄漏/噪声…）；
  ③ 盲区在哪：**零命中的关键词 = 检索必挂的问句**（模型按提示词列全部件词/现象词
     去检索，语料里没有对应文本 → 只能空结果或低分噪声）。

在线项（Milvus / Neo4j / PG 计数）在栈不可达时标记 `skipped`，不影响离线结论
（离线只统计仓库内语料文件，是"入库源"口径）。

用法：
    python scripts/corpus_stats.py                    #  stdout 表 + 写 reports/ 报告
    python scripts/corpus_stats.py --no-write         #  只打印不落文件
    python scripts/corpus_stats.py --out <path.md>    #  自定义输出路径
    python scripts/corpus_stats.py --strict           # 存在零命中关键词时退出码 1

退出码：0 = 正常（默认）；1 = `--strict` 且存在零命中关键词；2 = 依赖缺失。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CHUNKS_PATH = PROJECT_ROOT / "chunks" / "chunks_v1.jsonl"
PARENTS_PATH = PROJECT_ROOT / "chunks" / "parents_v1.jsonl"
BLOBS_DIR = PROJECT_ROOT / "blobs"
PARSED_DIR = PROJECT_ROOT / "parsed"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "tools_v4.json"
REPORT_DIR = PROJECT_ROOT / "reports"

#: 故障语义域词表（与提示词 `fault_keywords` 指引"列全部件词与现象词"同口径：
#: 部件 = 轴承/齿轮/密封/叶轮…，现象 = 振动/温度/泄漏/噪声…）
_DOMAIN_WORDS = (
    "轴承", "齿轮", "密封", "叶轮", "电机", "转子", "联轴器", "过滤器", "阀门",
    "振动", "温度", "泄漏", "噪声", "异响", "电流", "对中", "动平衡", "磨损",
    "剥落", "点蚀", "润滑", "油液", "喘振", "汽蚀", "松动", "裂纹", "疲劳",
    "频谱", "波形", "趋势", "阈值", "限值", "标准",
)

#: 设备型号族（语料覆盖度按族统计）
_MODEL_FAMILIES = ("PUMP", "MOTOR", "GEAR", "FAN")


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _load_chunks(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def corpus_stats() -> dict:
    """离线统计：语料文件规模 / 型号分布 / 关键词覆盖 / 盲区。"""
    chunks = _load_chunks(CHUNKS_PATH)
    texts = [str(c.get("text") or "") for c in chunks]
    joined = "\n".join(texts)

    docs = Counter(str(c.get("doc_id") or "") for c in chunks)
    doc_types = Counter(str(c.get("doc_type") or "") for c in chunks)
    tokens = sum(int(c.get("token_count") or 0) for c in chunks)

    families = Counter()
    for fam in _MODEL_FAMILIES:
        families[fam] = len(re.findall(rf"\b{fam}-", joined))
    models = Counter(re.findall(r"\b(?:PUMP|MOTOR|GEAR|FAN)-[A-Z0-9-]+", joined))

    hits = {w: joined.count(w) for w in _DOMAIN_WORDS}
    blind = sorted(w for w, n in hits.items() if n == 0)

    # 工具 schema 的故障语义域（description 里的中文词，与内置表取并集）。
    # 只收 2–3 字词：域词（轴承/振动/异响/联轴器/动平衡…）都是这个长度，
    # "故障关键词过滤"这类说明性词组会被自然排除（不维护停用词表）。
    schema_words: set[str] = set()
    if SCHEMA_PATH.exists():
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        for tool in schema.get("tools", []):
            props = (tool.get("parameters") or {}).get("properties") or {}
            desc = str(props.get("fault_keywords", {}).get("description") or "")
            schema_words.update(w for w in re.findall(r"[\u4e00-\u9fa5]{2,}", desc)
                                if 2 <= len(w) <= 3)
    for w in schema_words:
        if w not in hits:
            hits[w] = joined.count(w)
            if hits[w] == 0:
                blind.append(w)
    blind = sorted(set(blind))

    online = _online_counts()
    return {
        "chunks": len(chunks),
        "parents": _count_jsonl(PARENTS_PATH),
        "docs": len(docs),
        "doc_types": dict(doc_types),
        "tokens": tokens,
        "avg_chunk_chars": round(sum(len(t) for t in texts) / max(len(texts), 1), 1),
        "blob_files": len(list(BLOBS_DIR.rglob("*"))) if BLOBS_DIR.exists() else 0,
        "parsed_files": len(list(PARSED_DIR.glob("*.md"))) if PARSED_DIR.exists() else 0,
        "model_families": dict(families),
        "models": dict(models.most_common()),
        "keyword_hits": hits,
        "blind_keywords": blind,
        "online": online,
    }


def _online_counts() -> dict:
    """Milvus / Neo4j / PG 计数（离线环境标记 skipped，不阻断体检）。"""
    out: dict[str, object] = {"milvus": "skipped", "neo4j": "skipped", "pg_doc_chunks": "skipped"}
    try:
        import psycopg                                     # noqa: PLC0415
        from app.report.idempotency import POSTGRES_URL     # noqa: PLC0415
        with psycopg.connect(POSTGRES_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM doc_chunks")
                out["pg_doc_chunks"] = cur.fetchone()[0]
    except Exception:                                      # noqa: BLE001 - 离线跳过
        pass
    return out


def _render_markdown(st: dict) -> str:
    lines = [
        f"# 语料规模体检（{date.today().isoformat()}）",
        "",
        "> 由 `scripts/corpus_stats.py` 生成。口径：仓库内语料文件（入库源）为权威；",
        "> Milvus/Neo4j/PG 在线计数栈不可达时记 `skipped`。**本报告不改变任何已锁定实验基线**",
        "> （扩语料 = 平移基线，需所有者单独判决，见 `Material/02` §15 遗留 4）。",
        "",
        "## 规模",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| chunks（子块） | {st['chunks']} |",
        f"| parents（父块） | {st['parents']} |",
        f"| documents（去重 doc_id） | {st['docs']} |",
        f"| token 总量 | {st['tokens']} |",
        f"| 平均块字符数 | {st['avg_chunk_chars']} |",
        f"| blob 源文件 | {st['blob_files']} |",
        f"| parsed 源文件 | {st['parsed_files']} |",
        "",
        "## 设备型号覆盖",
        "",
        f"- 型号族命中次数：{st['model_families']}",
        f"- 具体型号：{st['models']}",
        "",
        "## 故障关键词覆盖（对照 tools_v4 fault_keywords 语义域）",
        "",
        "| 关键词 | 语料命中次数 |",
        "|---|---|",
    ]
    lines += [f"| {w} | {n} |" for w, n in sorted(st["keyword_hits"].items())]
    lines += ["", "## 盲区（零命中 = 检索必挂的问句）", ""]
    if st["blind_keywords"]:
        lines += [f"- {w}" for w in st["blind_keywords"]]
        lines += ["",
                  "处置建议：这些词对应的问句（如按提示词列全部件词/现象词检索）在当前语料下",
                  "只能拿到空结果或低分噪声。扩语料时按本清单优先补齐；扩前须评估对已锁定",
                  "实验基线的影响（EXP-P7-GATE*/V1 判据均以当前语料为基准）。"]
    else:
        lines.append("无 —— 语义域词表在当前语料中全部有命中。")
    lines += ["", f"在线计数：{st['online']}", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="语料规模体检（不灌数据）")
    parser.add_argument("--no-write", action="store_true", help="只打印，不写报告文件")
    parser.add_argument("--out", default="", help="自定义报告输出路径（.md）")
    parser.add_argument("--strict", action="store_true",
                        help="存在零命中关键词时退出码 1（供 CI 守门）")
    args = parser.parse_args(argv)

    st = corpus_stats()
    md = _render_markdown(st)
    print(md)

    if not args.no_write:
        out = Path(args.out) if args.out else REPORT_DIR / f"p1-corpus-stats-{date.today().isoformat()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"[written] {out}")

    if st["blind_keywords"]:
        print(f"[warn] 零命中关键词 {len(st['blind_keywords'])} 个："
              f"{', '.join(st['blind_keywords'])}")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
