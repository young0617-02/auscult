"""生成 MinerU Spike 用的 3 类样本 PDF（自编合成数据，P1-D1）。

用途
----
为 `reports/p1-mineru-spike.md` 提供可复现的三类样本：
  ① `sample_text.pdf`    文本型 PDF（有文本层，可直接抽取）
  ② `sample_scanned.pdf` 扫描件 PDF（**无文本层**，仅图像，模拟扫描件）
  ③ `sample_table.pdf`   含表格 PDF（用于检验表格还原）

数据纪律（`docs/p1-spec-data-sources.md` §3.2）
----
- 全部为**自编合成**内容，带 `synthetic: true` 标记（写入 `samples.meta.json`）；
- 由**固定 seed** 生成，seed 记入实验登记，保证可复现；
- 内容取自公开工业常识（离心泵手册骨架），**不复制任何真实手册原文**。

用法
----
    python scripts/gen_sample_pdfs.py --out-dir experiments/p1/mineru-spike/samples --seed 42
    python scripts/gen_sample_pdfs.py --selftest

依赖：pymupdf（见 `docs/prj-ledger-version-lock.md` §二.2.11）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF（1.28 起 `fitz` 别名为弃用写法）
except ImportError:  # pragma: no cover - 环境缺失时给出明确指引
    print("[ERROR] 缺少 pymupdf，请先安装：uv pip install pymupdf", file=sys.stderr)
    raise SystemExit(2)

# 内置简体中文字体（PyMuPDF 自带 CJK 字体，无需外部字体文件）
CJK_FONT = "china-s"

A4_W, A4_H = 595, 842

# ---------------------------------------------------------------------------
# 样本正文（自编，离心泵手册骨架；作为「文本完整率」评测的 ground truth）
# ---------------------------------------------------------------------------

TEXT_TITLE = "离心泵运行与结构手册（合成样本）"

TEXT_PARAGRAPHS = [
    ("1 安全须知", [
        "检修前必须切断电源并在配电柜悬挂“禁止合闸”标识，确认泵体完全停转、机封冷却后方可拆卸。",
        "运行中严禁靠近联轴器防护罩，禁止在泵体带压状态下拆卸法兰螺栓。",
    ]),
    ("2 结构原理", [
        "离心泵由泵壳、叶轮、轴、机械密封与轴承箱等部件组成，电机通过联轴器驱动叶轮高速旋转。",
        "叶轮旋转使液体获得动能，经蜗壳扩压后转化为压力能，从而实现液体输送。",
    ]),
    ("3 安装要求", [
        "泵组基础应具有足够刚度，地脚螺栓逐个对角紧固，联轴器同轴度偏差不超过 0.05 mm。",
        "吸入管路应尽量短且避免气囊，进口过滤器通流面积不小于吸入管截面的三倍。",
    ]),
    ("4 运行维护", [
        "轴承温度正常不超过 70 摄氏度，振动烈度应控制在 4.5 mm/s 以内。",
        "每运行 2000 小时更换一次润滑油，并检查机械密封泄漏量是否小于 5 滴每分钟。",
    ]),
    ("5 故障排查", [
        "振动超标常见原因为转子不平衡、联轴器不对中或轴承磨损，应结合频谱分析定位。",
        "流量不足多与叶轮磨损、进口堵塞或密封环间隙过大有关，需逐项排查。",
    ]),
]

# 表格样本：振动烈度判据表（自编判据，形似标准区间表但不复制标准原文）
TABLE_TITLE = "振动烈度判据表（合成样本）"
TABLE_HEADER = ["振动烈度 (mm/s)", "设备状态", "建议处置"]
TABLE_ROWS = [
    ["< 1.8", "优", "正常运行"],
    ["1.8 ~ 4.5", "良", "加强监测"],
    ["4.5 ~ 11.2", "注意", "安排检修"],
    ["11.2 ~ 28.0", "严重", "尽快停机检查"],
    ["> 28.0", "危险", "立即停机"],
]


def _new_page(doc: "fitz.Document") -> "fitz.Page":
    return doc.new_page(width=A4_W, height=A4_H)


def _insert_wrapped(page: "fitz.Page", x: float, y: float, text: str,
                    fontsize: int = 11, max_width: float = A4_W - 2 * 72,
                    line_gap: float = 8) -> float:
    """按像素宽度手工折行写入中文文本，返回下一行 y。"""
    line = ""
    for ch in text:
        trial = line + ch
        if fitz.get_text_length(trial, fontname=CJK_FONT, fontsize=fontsize) > max_width:
            page.insert_text((x, y), line, fontname=CJK_FONT, fontsize=fontsize)
            y += fontsize + line_gap
            line = ch
        else:
            line = trial
    if line:
        page.insert_text((x, y), line, fontname=CJK_FONT, fontsize=fontsize)
        y += fontsize + line_gap
    return y


def build_text_pdf(path: Path) -> None:
    """① 文本型 PDF：有文本层，可直接抽取。"""
    doc = fitz.open()
    page = _new_page(doc)
    y = 90.0
    page.insert_text((72, y), TEXT_TITLE, fontname=CJK_FONT, fontsize=16)
    y += 30
    for heading, paras in TEXT_PARAGRAPHS:
        page.insert_text((72, y), heading, fontname=CJK_FONT, fontsize=13)
        y += 22
        for p in paras:
            y = _insert_wrapped(page, 72, y, p, fontsize=11)
            y += 6
        y += 6
    doc.save(str(path))
    doc.close()


def build_table_pdf(path: Path) -> None:
    """③ 含表格 PDF：画线 + 单元格文本，用于检验表格还原。"""
    doc = fitz.open()
    page = _new_page(doc)
    page.insert_text((72, 90), TABLE_TITLE, fontname=CJK_FONT, fontsize=16)

    x0, y0 = 72.0, 140.0
    col_w = [180.0, 120.0, 150.0]
    row_h = 34.0
    n_rows = len(TABLE_ROWS) + 1  # 含表头

    # 横线
    for r in range(n_rows + 1):
        yy = y0 + r * row_h
        page.draw_line(fitz.Point(x0, yy), fitz.Point(x0 + sum(col_w), yy), width=0.8)
    # 竖线
    x = x0
    page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + n_rows * row_h), width=0.8)
    for w in col_w:
        x += w
        page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + n_rows * row_h), width=0.8)

    # 单元格文本
    cell_rows = [TABLE_HEADER] + TABLE_ROWS
    for r, row in enumerate(cell_rows):
        cx = x0
        for c, cell in enumerate(row):
            page.insert_text((cx + 8, y0 + r * row_h + row_h / 2 + 4),
                             cell, fontname=CJK_FONT, fontsize=11)
            cx += col_w[c]
    doc.save(str(path))
    doc.close()


def build_scanned_pdf(path: Path, dpi: int = 200) -> None:
    """② 扫描件 PDF：把文本页渲染为图像后嵌入，**去除文本层**，模拟扫描件。"""
    src = fitz.open()
    page = _new_page(src)
    y = 90.0
    page.insert_text((72, y), TEXT_TITLE, fontname=CJK_FONT, fontsize=16)
    y += 30
    for heading, paras in TEXT_PARAGRAPHS:
        page.insert_text((72, y), heading, fontname=CJK_FONT, fontsize=13)
        y += 22
        for p in paras:
            y = _insert_wrapped(page, 72, y, p, fontsize=11)
            y += 6
        y += 6
    pix = page.get_pixmap(dpi=dpi)

    out = fitz.open()
    opage = out.new_page(width=pix.width * 72 / dpi, height=pix.height * 72 / dpi)
    opage.insert_image(opage.rect, pixmap=pix)
    out.save(str(path))
    out.close()
    src.close()


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def generate(out_dir: Path, seed: int) -> dict:
    random.seed(seed)  # 显式固定 seed（本脚本内容确定，仍按纪律登记）
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "text": out_dir / "sample_text.pdf",
        "scanned": out_dir / "sample_scanned.pdf",
        "table": out_dir / "sample_table.pdf",
    }
    build_text_pdf(files["text"])
    build_scanned_pdf(files["scanned"])
    build_table_pdf(files["table"])

    meta = {
        "synthetic": True,
        "seed": seed,
        "generator": "scripts/gen_sample_pdfs.py",
        "note": "自编合成内容，取自公开工业常识骨架，不含任何真实手册原文；禁止以“现场数据”表述",
        "samples": {
            k: {"file": v.name, "bytes": v.stat().st_size, "sha256": sha256_of(v)}
            for k, v in files.items()
        },
    }
    (out_dir / "samples.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        meta = generate(Path(td), seed=42)
        ok = all(s["bytes"] > 0 for s in meta["samples"].values())
        if not ok:
            print("[selftest] FAIL: 生成文件为空")
            return 1
        # 校验文本型 PDF 确有文本层、扫描件 PDF 无文本层
        text_doc = fitz.open(str(Path(td) / "sample_text.pdf"))
        scan_doc = fitz.open(str(Path(td) / "sample_scanned.pdf"))
        has_text = len(text_doc[0].get_text().strip()) > 100
        no_text = len(scan_doc[0].get_text().strip()) == 0
        text_doc.close()
        scan_doc.close()
        if not (has_text and no_text):
            print(f"[selftest] FAIL: has_text={has_text} no_text={no_text}")
            return 1
    print("[selftest] PASS: 3 类样本可生成，文本层/无文本层特征符合预期")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 MinerU Spike 用的 3 类样本 PDF")
    ap.add_argument("--out-dir", type=Path,
                    default=Path("experiments/p1/mineru-spike/samples"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    meta = generate(args.out_dir, args.seed)
    print(f"[OK] 已生成 3 类样本 → {args.out_dir}")
    for k, v in meta["samples"].items():
        print(f"  - {k:8s} {v['file']:20s} {v['bytes']:>7d} B  sha256={v['sha256'][:16]}…")
    print(f"[OK] 元数据 → {args.out_dir / 'samples.meta.json'}（synthetic=true, seed={args.seed}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())