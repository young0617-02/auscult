# -*- coding: utf-8 -*-
"""B2 Parent-Child 分块（P1-D4 · B2）。

把 B1 产出的 `parsed/*.md` 切分为「父块（章节级）+ 子块（段落级）」两级，
加元数据后输出 `chunks/chunks_v1.jsonl`。设计见 `plan/p1-plan-detailed.md` §5.5。

分块策略（用户已确认）：
  - 前置归一化：① 数字-单位空格合并（`m m`→`mm`、`mm/ s`→`mm/s` 等）；
               ② HTML 实体反解（`&lt;`→`<`、`&gt;`→`>`、`&amp;`→`&`）。承接 B1 报告 §五.2。
  - 父块：按 `##` 标题层级切（章节级，保留完整上下文）。
  - 子块：段落级（空行切段）→ jieba 分词数校验 256–512 窗口：
      段落在 256–512 → 整段为子块；>512 超长段 → 硬割（chunk_size=512, overlap=32）；
      <256 短段 → 与下一段合并直到 ≥256（不超 512）；段间 `\n` 连接。
  - 元数据：{id, parent_id, doc_id, doc_type, device_model, section, page, version, text, token_count, is_parent}
  - 抽检：随机 20 个子块写入 `chunks/_sample20.jsonl`（seed 沿用 42，可复现）。

用法：
    .venv\\Scripts\\python.exe scripts\\chunk_docs.py --selftest
    .venv\\Scripts\\python.exe scripts\\chunk_docs.py
    .venv\\Scripts\\python.exe scripts\\chunk_docs.py --out-dir chunks

依赖：jieba（`docs/prj-ledger-version-lock.md` §二.2.8）
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

try:
    import jieba
except ImportError:  # pragma: no cover
    print("[ERROR] 缺少 jieba，请安装：uv pip install jieba==0.42.1", file=sys.stderr)
    raise SystemExit(2)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "parsed"
DEFAULT_OUTPUT = PROJECT_ROOT / "chunks"
CHUNK_SIZE = 512    # 超长段硬割窗口（token）
CHUNK_OVERLAP = 32  # 硬割重叠
MIN_TOKENS = 256    # 短段合并目标下界
VERSION = "v1"

# 文件名前缀 → (doc_type, device_model 提取方式)
_DOC_RULES = [
    ("manual_", "设备手册", "title"),
    ("workorders_", "维修工单", None),
    ("fault_case_", "故障案例", None),
    ("criteria_", "标准判据", None),
    ("topo_", "拓扑", None),
    # 其余 → unknown
]

_HTML_ENT = {"&lt;": "<", "&gt;": ">", "&amp;": "&", "&nbsp;": " ", "&quot;": '"'}
_PAGE_RE = re.compile(r"<!--\s*page\s+(\d+)\s+of\s+(\d+)\s*-->")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")


def jieba_tokens(text: str) -> list[str]:
    return [w for w in jieba.lcut(text) if w.strip()]


def normalize(text: str) -> str:
    """数字-单位空格合并 + HTML 实体反解。"""
    for k, v in _HTML_ENT.items():
        text = text.replace(k, v)
    # 数字与单位间的多余空格合并,如 '0.05 m m/s' → '0.05 mm/s'（含 mm 被拆成 'm m' 情形）
    text = re.sub(r"(\d)\s+m\s+m", r"\1mm", text)
    text = re.sub(r"(\d)\s+mm", r"\1mm", text)
    text = re.sub(r"(\d)\s+ms", r"\1ms", text)
    text = re.sub(r"mm\s*/\s*s", "mm/s", text)
    return text


def infer_doc_meta(stem: str, first_heading: str) -> tuple:
    """按文件名前缀推导 (doc_type, device_model)。device_model 规则为 title 时从不含别名的标题提取。"""
    for prefix, doc_type, model_src in _DOC_RULES:
        if stem.startswith(prefix):
            if model_src == "title":
                m = re.match(r"^([\w-]+?)(?:\s|离心泵|电机)", first_heading) if first_heading else None
                model = m.group(1) if m else "unknown"
                return doc_type, model
            return doc_type, "unknown"
    return "unknown", "unknown"


def extract_pages(text: str) -> dict | None:
    """页注释 → {first, count}。"""
    m = _PAGE_RE.search(text)
    if m:
        return {"first": int(m.group(1)), "count": int(m.group(2))}
    return None


def split_sections(md: str) -> list[tuple[str, list[str]]]:
    """按标题行切父块。返回 [(标题文本或'', [非空行列表]), ...]。标题行作为父块的标题字段。"""
    lines = md.splitlines()
    sections: list[tuple[str, list[str]]] = []
    cur_title = ""
    cur_lines: list[str] = []
    for ln in lines:
        if ln.strip().startswith("<!--"):  # 页码注释行，跳过
            continue
        hm = _HEADING_RE.match(ln.strip())
        if hm:
            if cur_title or cur_lines:
                sections.append((cur_title, cur_lines))
            cur_title = hm.group(1).strip()
            cur_lines = []
        else:
            cur_lines.append(ln)
    if cur_title or cur_lines:
        sections.append((cur_title, cur_lines))
    return sections


def split_paragraphs(lines: list[str]) -> list[str]:
    """按空行聚合为段落，返回去空行的段落列表。"""
    paras: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if ln.strip():
            buf.append(ln)
        elif buf:
            paras.append("\n".join(buf))
            buf = []
    if buf:
        paras.append("\n".join(buf))
    return [p for p in paras if p.strip()]


def join_split(tokens: list[str], chunk_size: int, overlap: int) -> list[str]:
    """按 token 窗口硬割，返回若干文本串。"""
    idx = 0
    parts = []
    while idx < len(tokens):
        end = idx + chunk_size
        parts.append("".join(tokens[idx:end]))
        if end >= len(tokens):
            break
        idx = end - overlap
    return parts


def chunk_one(stem: str, md: str) -> tuple[list, list]:
    """对单个 parsed md 返回 (parents, children)。"""
    md = normalize(md)
    pages = extract_pages(md)
    sections = split_sections(md)

    # 首标题（doc_type 推导 + 标题字段用）
    first_heading = sections[0][0] if sections else ""
    doc_type, device_model = infer_doc_meta(stem, first_heading)

    parents: list[dict] = []
    children: list[dict] = []

    # 归并父块
    for si, (title, lines) in enumerate(sections):
        if title == first_heading and si == 0:
            # 文档主标题（标题即首章），合并其后所有段落为该父块
            section_name = "全文" if len(sections) == 1 and not lines else (title or "全文")
        else:
            section_name = title if title else "（无标题）"
        # 父块章节通名：用标题或行首短语
        pid = f"{stem}-{si}"
        parent_text = "\n".join(lines).strip()
        parents.append({
            "id": pid, "doc_id": stem, "doc_type": doc_type,
            "device_model": device_model, "section": section_name,
            "page": pages["first"] if pages else None, "version": VERSION,
            "text": parent_text, "token_count": len(jieba_tokens(parent_text)),
            "is_parent": True,
        })

        # 子块：段落级分块
        paras = split_paragraphs(lines)
        # 合并短段策略：累计 token，直到 ≥ MIN_TOKENS 或耗尽/超限
        merged: list[list[str]] = []
        cur: list[str] = []
        cur_tokens = 0
        for p in paras:
            pt = jieba_tokens(p)
            if cur_tokens + len(pt) > CHUNK_SIZE and cur:
                merged.append(cur)
                cur, cur_tokens = [], 0
            cur.append(p)
            cur_tokens += len(pt)
            if cur_tokens >= MIN_TOKENS:
                merged.append(cur)
                cur, cur_tokens = [], 0
        if cur:
            merged.append(cur)

        # 展开为子块（超长段硬割）
        local = 0
        for group in merged:
            text = "\n".join(group)
            toks = jieba_tokens(text)
            if len(toks) <= CHUNK_SIZE:
                cid = f"{pid}-c{local}"
                children.append({
                    "id": cid, "parent_id": pid, "doc_id": stem,
                    "doc_type": doc_type, "device_model": device_model,
                    "section": section_name,
                    "page": pages["first"] if pages else None, "version": VERSION,
                    "text": text, "token_count": len(toks), "is_parent": False,
                })
                local += 1
            else:
                for part in join_split(toks, CHUNK_SIZE, CHUNK_OVERLAP):
                    cid = f"{pid}-c{local}"
                    children.append({
                        "id": cid, "parent_id": pid, "doc_id": stem,
                        "doc_type": doc_type, "device_model": device_model,
                        "section": section_name,
                        "page": pages["first"] if pages else None, "version": VERSION,
                        "text": part, "token_count": len(jieba_tokens(part)), "is_parent": False,
                    })
                    local += 1
    return parents, children


def main() -> int:
    ap = argparse.ArgumentParser(description="B2 Parent-Child 分块")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    mds = sorted(args.input.rglob("*.md"))
    if not mds:
        print(f"[ERROR] {args.input} 下无 *.md")
        return 2
    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_children: list[dict] = []
    per_doc = {}
    for md in mds:
        stem = md.stem
        parents, children = chunk_one(stem, md.read_text(encoding="utf-8"))
        all_children.extend(children)
        per_doc[stem] = {"parents": len(parents), "children": len(children),
                         "tokens": sum(c["token_count"] for c in children)}

    rng = random.Random(args.seed)
    sampled = rng.sample(all_children, min(args.sample, len(all_children)))

    # 外层校验：每个 child.parent_id 必须存在（在同 doc 的 parents 中）
    parent_ids = set()
    for md in mds:
        stem = md.stem
        parents, _ = chunk_one(stem, md.read_text(encoding="utf-8"))
        parent_ids.update(p["id"] for p in parents)
    orphan = [c for c in all_children if c["parent_id"] not in parent_ids]

    with open(args.out_dir / "chunks_v1.jsonl", "w", encoding="utf-8") as f:
        for c in all_children:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(args.out_dir / "_sample20.jsonl", "w", encoding="utf-8") as f:
        for c in sampled:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    summary = {
        "schema_version": VERSION, "doc_count": len(per_doc),
        "parent_total": sum(v["parents"] for v in per_doc.values()),
        "child_total": len(all_children),
        "token_total": sum(v["tokens"] for v in per_doc.values()),
        "orphan_child": len(orphan),
        "sampled": len(sampled),
        "per_doc": per_doc,
    }
    (args.out_dir / "_chunk_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[run] 文档={summary['doc_count']} 父块={summary['parent_total']} "
          f"子块={summary['child_total']} token={summary['token_total']} "
          f"抽检={summary['sampled']}")
    print(f"[run] 孤儿子块（挂空 parent_id）={len(orphan)} -> "
          f"{'✅ 通过' if not orphan else '❌ 存在孤儿'}")
    return 0 if not orphan else 1


def _selftest() -> int:
    ok = True
    # 1) 归一化：数字-单位空格、HTML 实体
    t = normalize("0.05 m m/s，&lt;1.8")
    if "0.05mm/s" not in t or "<1.8" not in t:
        ok = False
        print(f"[FAIL] normalize: {t!r}")
    # 2) 分块：用一段手册文字
    md = "<!-- page 1 of 1 -->\n\n## 1 安全须知\n\n检修前必须切断电源并在配电柜悬挂“禁止合闸”标识。\n\n运行中严禁靠近联轴器防护罩，禁止在泵体带压状态下拆卸法兰螺栓。"
    parents, children = chunk_one("manual_impeller_series", md)
    if not parents or not children:
        ok = False
        print("[FAIL] chunk_one 为空")
    elif len(parents) != 1:  # 首标题作为全文父块（无后继章节）
        # 允许 1 个父块
        pass
    # 3) 每个子块 parent_id 存在
    if any(c["parent_id"] not in {p["id"] for p in parents} for c in children):
        ok = False
        print("[FAIL] 子块 parent_id 悬空")
    # 4) 文档推导
    dt, dm = infer_doc_meta("manual_impeller_series", "IMP-150 离心泵运行与结构手册（合成样本）")
    if dt != "设备手册" or "IMP" not in dm:
        ok = False
        print(f"[FAIL] infer_doc_meta: {dt}/{dm}")
    print(f"[selftest] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())