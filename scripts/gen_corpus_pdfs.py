# -*- coding: utf-8 -*-
"""生成 B1 全量解析用的多文档自编模拟语料 PDF（P1-D3/D4 · B1）。

用途
----
为 `reports/p1-d3-d4-b1-corpus.md` 提供可复现的、字段级等价的多类型模拟语料，
覆盖 `docs/p1-spec-data-sources.md` §3.1 的主要类别（D3–D4 可控版）：
  - 设备手册：文本型 ×2 + 扫描件 ×1 + 含表格 ×1（章节骨架：安全/结构/安装/运行/维护/故障）
  - 维修工单：表格型 ×6（工单字段：编号/日期/现象/处置）
  - 故障案例：文本型 ×6（现象—分析—处置—结论）
  - 标准判据：表格型 ×2（振动/轴温/电流判据，自编要点，不复制标准原文）
  - 拓扑：文本 + 表格 ×1（虚构厂区设备三元组描述）

数据纪律（`docs/p1-spec-data-sources.md` §3.2）
----
- 全部为**自编合成**内容，带 `synthetic: true` 标记（写入 `corpus.meta.json`）；
- 由**固定 seed** 生成，seed 记入实验登记，保证可复现；
- 内容取自公开工业常识骨架，**不复制任何真实手册原文**；
- 模拟数据结构与真实数据结构**字段级等价**（可被真实数据无改代码替换）。

用法
----
    python scripts/gen_corpus_pdfs.py --out-dir experiments/p1/b1-corpus --seed 42
    python scripts/gen_corpus_pdfs.py --selftest

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


def _new_text_doc(title: str, sections: list, fontsize: int = 11) -> "fitz.Document":
    """构造一个多标题段落文档（自动分页）。"""
    doc = fitz.open()
    page = _new_page(doc)
    y = 90.0
    page.insert_text((72, y), title, fontname=CJK_FONT, fontsize=16)
    y += 30
    for heading, paras in sections:
        if y > A4_H - 80:
            page = _new_page(doc)
            y = 90.0
        page.insert_text((72, y), heading, fontname=CJK_FONT, fontsize=13)
        y += 22
        for p in paras:
            if y > A4_H - 60:
                page = _new_page(doc)
                y = 90.0
            y = _insert_wrapped(page, 72, y, p, fontsize=fontsize)
            y += 6
        y += 6
    return doc


def _new_table_doc(title: str, header: list, rows: list, col_w=None,
                   fontsize: int = 10) -> "fitz.Document":
    """构造一个画线表格文档。"""
    if col_w is None:
        n = len(header)
        col_w = [(A4_W - 2 * 72) / n] * n
    doc = fitz.open()
    page = _new_page(doc)
    page.insert_text((72, 90), title, fontname=CJK_FONT, fontsize=16)
    x0, y0 = 72.0, 140.0
    row_h = 34.0
    n_rows = len(rows) + 1  # 含表头
    # 横向分页保护：超出页高则新页重画表头
    if y0 + n_rows * row_h > A4_H - 40:
        out = doc
        # 每页最多装 floor((A4_H-40-y0)/row_h) 行
        per_page = max(1, int((A4_H - 40 - y0) / row_h) - 1)
        doc.close()
        return _new_multi_table_doc(title, header, rows, col_w, per_page, fontsize)
    for r in range(n_rows + 1):
        yy = y0 + r * row_h
        page.draw_line(fitz.Point(x0, yy), fitz.Point(x0 + sum(col_w), yy), width=0.8)
    x = x0
    page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + n_rows * row_h), width=0.8)
    for w in col_w:
        x += w
        page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + n_rows * row_h), width=0.8)
    cell_rows = [header] + rows
    for r, row in enumerate(cell_rows):
        cx = x0
        for c, cell in enumerate(row):
            page.insert_text((cx + 8, y0 + r * row_h + row_h / 2 + 4), str(cell),
                             fontname=CJK_FONT, fontsize=fontsize)
            cx += col_w[c]
    return doc


def _new_multi_table_doc(title: str, header: list, rows: list, col_w: list,
                         per_page: int, fontsize: int) -> "fitz.Document":
    """超长表格分页：每页重画表头。"""
    doc = fitz.open()
    x0, y0 = 72.0, 140.0
    row_h = 34.0
    chunks = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    for ci, chunk in enumerate(chunks):
        page = _new_page(doc)
        page.insert_text((72, 90), title + (f"（第{ci + 1}页）" if len(chunks) > 1 else ""),
                         fontname=CJK_FONT, fontsize=16)
        cell_rows = [header] + chunk
        n_rows = len(cell_rows)
        cur_y = y0
        for r in range(n_rows + 1):
            yy = cur_y + r * row_h
            page.draw_line(fitz.Point(x0, yy), fitz.Point(x0 + sum(col_w), yy), width=0.8)
        x = x0
        page.draw_line(fitz.Point(x, cur_y), fitz.Point(x, cur_y + n_rows * row_h), width=0.8)
        for w in col_w:
            x += w
            page.draw_line(fitz.Point(x, cur_y), fitz.Point(x, cur_y + n_rows * row_h), width=0.8)
        for r, row in enumerate(cell_rows):
            cx = x0
            for c, cell in enumerate(row):
                page.insert_text((cx + 8, cur_y + r * row_h + row_h / 2 + 4), str(cell),
                                 fontname=CJK_FONT, fontsize=fontsize)
                cx += col_w[c]
    return doc


def _save(doc: "fitz.Document", path: Path) -> None:
    doc.save(str(path))
    doc.close()


# ---------------------------------------------------------------------------
# 设备手册语料（章节：安全/结构/安装/运行/维护/故障排查）
# ---------------------------------------------------------------------------

def _manual_sections(model: str, serial: str, variant: int) -> list:
    """按型号/编号自撰手册章节骨架（公开工业常识，非真实手册原文）。"""
    return [
        ("1 安全须知", [
            f"{model}（编号 {serial}）检修前必须切断电源并在配电柜悬挂“禁止合闸”标识。",
            "运行中严禁靠近联轴器防护罩，禁止在带压状态下拆卸法兰螺栓。",
        ]),
        ("2 结构原理", [
            f"{model} 由泵壳、叶轮、轴、机械密封与轴承箱组成，电机经联轴器驱动叶轮旋转。",
            "叶轮旋转使液体获得动能，经蜗壳扩压转化为压力能，实现液体输送。",
        ]),
        ("3 安装要求", [
            "泵组基础应有足够刚度，地脚螺栓对角紧固，联轴器同轴度偏差不超过 0.05 mm。",
            "吸入管路尽量短且避免气囊，进口过滤器通流面积不小于吸入管截面的三倍。",
        ]),
        ("4 运行维护", [
            "轴承温度正常不超过 70 摄氏度，振动烈度控制在 4.5 mm/s 以内。",
            f"运行 {2000 + variant * 500} 小时更换一次润滑油，检查机械密封泄漏量小于 5 滴每分钟。",
        ]),
        ("5 故障排查", [
            "振动超标常见转子不平衡、联轴器不对中或轴承磨损，应结合频谱分析定位。",
            "流量不足多与叶轮磨损、进口堵塞或密封环间隙过大有关，需逐项排查。",
        ]),
    ]


def build_manual_pdf(path: Path, model: str, serial: str, kind: str, dpi: int = 200) -> None:
    """设备手册。kind ∈ {text, scanned, table}。"""
    sections = _manual_sections(model, serial, variant=sum(ord(c) for c in serial) % 4)
    title = f"{model} 离心泵运行与结构手册（合成样本）"
    if kind in ("text", "scanned"):
        doc = _new_text_doc(title, sections)
        if kind == "text":
            _save(doc, path)
        else:
            # 扫描件：渲染为图像后嵌入，去除文本层
            src = doc
            pix = src[0].get_pixmap(dpi=dpi)
            out = fitz.open()
            opage = out.new_page(width=pix.width * 72 / dpi, height=pix.height * 72 / dpi)
            opage.insert_image(opage.rect, pixmap=pix)
            src.close()
            _save(out, path)
    else:  # table：底部附一张振动烈度判据表
        doc = _new_text_doc(title, sections)
        # 追加新页画表格
        page = _new_page(doc)
        page.insert_text((72, 90), "振动烈度判据表（合成样本）", fontname=CJK_FONT, fontsize=14)
        x0, y0 = 72.0, 140.0
        col_w = [180.0, 120.0, 150.0]
        row_h = 34.0
        rows = [
            ["< 1.8", "优", "正常运行"], ["1.8 ~ 4.5", "良", "加强监测"],
            ["4.5 ~ 11.2", "注意", "安排检修"], ["11.2 ~ 28.0", "严重", "尽快停机检查"],
            ["> 28.0", "危险", "立即停机"],
        ]
        n_rows = len(rows) + 1
        for r in range(n_rows + 1):
            yy = y0 + r * row_h
            page.draw_line(fitz.Point(x0, yy), fitz.Point(x0 + sum(col_w), yy), width=0.8)
        x = x0
        page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + n_rows * row_h), width=0.8)
        for w in col_w:
            x += w
            page.draw_line(fitz.Point(x, y0), fitz.Point(x, y0 + n_rows * row_h), width=0.8)
        cell_rows = [["振动烈度 (mm/s)", "设备状态", "建议处置"]] + rows
        for r, row in enumerate(cell_rows):
            cx = x0
            for c, cell in enumerate(row):
                page.insert_text((cx + 8, y0 + r * row_h + row_h / 2 + 4), cell,
                                 fontname=CJK_FONT, fontsize=11)
                cx += col_w[c]
        _save(doc, path)


# ---------------------------------------------------------------------------
# 维修工单（表格型）
# ---------------------------------------------------------------------------

def _workorder_rows(rng: random.Random, n: int, prefix: str) -> list:
    """按真实 CMMS 字段骨架生成伪造工单行（姓名/客户号全部伪造）。"""
    phenomena = ["振动值偏高", "轴承温度异常", "密封渗漏", "噪声增大", "电流超限"]
    dispositions = ["更换轴承", "重新对中", "更换机械密封", "动平衡校正", "清理过滤器"]
    rows = []
    for i in range(n):
        rows.append([
            f"WO-{prefix}-{202401 + i % 2}-{1000 + i}",
            f"客户-{(i * 7) % 1000:03d}",
            f"{rng.choice(['A', 'B', 'C'])}{i}泵",
            rng.choice(phenomena), rng.choice(dispositions),
            f"工作日第{(i % 20) + 1}天",
        ])
    return rows


def build_workorders_pdf(path: Path, rng: random.Random, prefix: str, n: int = 8) -> None:
    """维修工单：表格型，字段结构=编号/客户/设备/现象/处置/日期。"""
    header = ["工单编号", "客户号", "设备", "故障现象", "处置措施", "日期"]
    rows = _workorder_rows(rng, n, prefix)
    col_w = [95.0, 70.0, 70.0, 100.0, 110.0, 90.0]
    doc = _new_table_doc(f"设备维修工单（合成样本 · {prefix}）", header, rows, col_w)
    _save(doc, path)


# ---------------------------------------------------------------------------
# 故障案例（文本型）
# ---------------------------------------------------------------------------

def _fault_case(rng: random.Random, cases: tuple, idx: int) -> tuple:
    """从公开故障机理（不平衡/不对中/轴承磨损/气蚀/松动）自撰案例。"""
    name, cause, symptom, analysis, action = cases[idx % len(cases)]
    return (f"故障案例 {idx + 1}：{name}", [
        f"现象：{symptom}，现场实测振动高于警戒值。",
        f"分析：{analysis}。",
        f"处置：{action}。",
        "结论：经修复并返测，振动恢复至正常区间，建议纳入周期性巡检。",
    ])


_FAULT_CASES = (
    ("转子不平衡", "叶轮结垢或叶片缺损", "径向 1× 工频幅值增大",
     "不平衡谱中一阶转频成分显著，负荷变化幅值波动", "动平衡校正并清理叶轮"),
    ("联轴器不对中", "安装对中偏差过大", "轴向 1×/2× 幅值增大",
     "不对中谱出现 2× 转频成分，轴向与径向幅值比超常", "重新激光对中并复核"),
    ("轴承磨损", "润滑不良或过载", "高频段出现轴承特征频率族",
     "BPFI/BPFO 边带明显，包络谱故障频率随磨损上升", "更换轴承并改善润滑"),
    ("气蚀", "吸入压力不足或进口受阻", "宽频随机噪声伴高频气泡破裂",
     "气蚀产生随机高频冲击，流量与扬程同时下降", "调整吸入压力并清理进口"),
    ("基础松动", "地脚螺栓松脱", "松动侧明显位移且随运行漂移",
     "松动会放大各处振动并随工况漂移，相位不稳定", "紧固并灌浆加固基础"),
    ("过载", "长期超流量运行", "电流与温度同时偏高超限",
     "电机电流持续高于额定，绕组温升按过热模型上升", "降低负荷并核算裕量"),
)


def build_fault_case_pdf(path: Path, rng: random.Random, idx: int) -> None:
    cases = _FAULT_CASES
    case_idx = rng.randrange(len(cases))
    title, paras = _fault_case(rng, cases, case_idx)
    doc = _new_text_doc("设备故障案例分析（合成样本）", [(title, paras)])
    _save(doc, path)


# ---------------------------------------------------------------------------
# 标准判据（表格型，自编要点，不复制标准原文）
# ---------------------------------------------------------------------------

def build_criteria_pdf(path: Path, idx: int) -> None:
    """标准判据：自编判据要点表（振动烈度/轴温/电流），仅引用工程常识，不入标准原文。"""
    if idx == 0:
        title = "振动烈度判据要点表（合成样本）"
        header = ["振动烈度 (mm/s)", "设备状态", "建议处置"]
        rows = [
            ["< 1.8", "优", "正常运行"], ["1.8 ~ 4.5", "良", "加强监测"],
            ["4.5 ~ 11.2", "注意", "安排检修"], ["11.2 ~ 28.0", "严重", "尽快停机检查"],
            ["> 28.0", "危险", "立即停机"],
        ]
        col_w = [180.0, 120.0, 150.0]
    else:
        title = "轴温与电流判据要点表（合成样本）"
        header = ["测点", "正常区间", "警戒值", "建议处置"]
        rows = [
            ["驱动端轴承温度", "≤70 ℃", ">85 ℃", "加强监测"],
            ["非驱动端轴承温度", "≤70 ℃", ">85 ℃", "加强监测"],
            ["电机定子电流", "≤额定", ">额定×1.15", "降低负荷核算裕量"],
        ]
        col_w = [170.0, 130.0, 130.0, 140.0]
    doc = _new_table_doc(title, header, rows, col_w)
    _save(doc, path)


# ---------------------------------------------------------------------------
# 拓扑（文本 + 表格）
# ---------------------------------------------------------------------------

def build_topo_pdf(path: Path) -> None:
    """虚构厂区拓扑：1 份含文字描述 + 设备三元组表。"""
    title = "厂区设备拓扑（合成样本）"
    header = ["来源", "关系", "目标"]
    rows = [
        ["泵组 PUMP-A", "连接", "管线 L-01"],
        ["管线 L-01", "输送", "去流程段 TANK-1"],
        ["泵组 PUMP-A", "安装", "测点 VIB_A"],
        ["测点 VIB_A", "监测", "驱动端轴承"],
        ["电机 M-01", "驱动", "泵组 PUMP-A"],
        ["配电柜 P-01", "供电", "电机 M-01"],
    ]
    col_w = [180.0, 120.0, 240.0]
    doc = _new_table_doc(title, header, rows, col_w)
    _save(doc, path)


# ---------------------------------------------------------------------------
# 顶层组装
# ---------------------------------------------------------------------------

def _collect_pdf(out_dir: Path) -> dict:
    """生成全部语料，返回 {key: Path} 映射。"""
    rng = random.Random(1337)  # 固定派生 seed（与主 seed 独立，仍可复现）
    files: dict[str, Path] = {}

    # 设备手册：4 册（文本×2 / 扫描×1 / 含表格×1）
    manuals = [
        ("manual_impeller_series", "IMP-150", "text"),
        ("manual_centrifugal_hc", "HC-200", "text"),
        ("manual_scanned_dp", "DP-125", "scanned"),
        ("manual_ss_process", "SS-80", "table"),
    ]
    for key, model, kind in manuals:
        p = out_dir / f"{key}.pdf"
        build_manual_pdf(p, model, model, kind)
        files[key] = p

    # 维修工单：表格型 ×6
    prefixes = ["A", "B", "C", "D", "E", "F"]
    for i, pref in enumerate(prefixes):
        p = out_dir / f"workorders_{pref}.pdf"
        build_workorders_pdf(p, rng, pref, n=8)
        files[f"workorders_{pref}"] = p

    # 故障案例：文本型 ×6
    for i in range(6):
        p = out_dir / f"fault_case_{i + 1}.pdf"
        build_fault_case_pdf(p, rng, i)
        files[f"fault_case_{i + 1}"] = p

    # 标准判据：表格型 ×2
    for i in range(2):
        p = out_dir / f"criteria_{i + 1}.pdf"
        build_criteria_pdf(p, i)
        files[f"criteria_{i + 1}"] = p

    # 拓扑：1 份
    p = out_dir / "topo_plant.pdf"
    build_topo_pdf(p)
    files["topo_plant"] = p

    return files


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def generate(out_dir: Path, seed: int) -> dict:
    random.seed(seed)  # 显式固定主 seed（按纪律登记）
    out_dir.mkdir(parents=True, exist_ok=True)
    files = _collect_pdf(out_dir)

    meta = {
        "synthetic": True,
        "seed": seed,
        "generator": "scripts/gen_corpus_pdfs.py",
        "doc_type_counts": {
            "manual_text": 2, "manual_scanned": 1, "manual_table": 1,
            "workorders": 6, "fault_case": 6, "criteria": 2, "topo": 1,
        },
        "note": "自编合成内容，取自公开工业常识骨架，不含任何真实手册原文；"
                "禁止以“现场数据”表述；字段结构与真实数据等价，可被真实数据无改代码替换",
        "samples": {k: {"file": v.name, "bytes": v.stat().st_size,
                        "sha256": sha256_of(v)} for k, v in files.items()},
    }
    (out_dir / "corpus.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def _selftest() -> int:
    with tempfile.TemporaryDirectory() as td:
        meta = generate(Path(td), seed=42)
        ok = all(s["bytes"] > 0 for s in meta["samples"].values())
        if not ok:
            print("[selftest] FAIL: 存在空文件")
            return 1
        # 校验类别与数量
        expect = 4 + 6 + 6 + 2 + 1  # 手册4 + 工单6 + 案例6 + 判据2 + 拓扑1
        if len(meta["samples"]) != expect:
            print(f"[selftest] FAIL: 文件数={len(meta['samples'])} 期望={expect}")
            return 1
        # 校验扫描件无文本层、文本型有文本层
        scan_ok = True
        text_ok = True
        for key in ("manual_scanned_dp", "manual_impeller_series"):
            doc = fitz.open(str(Path(td) / meta["samples"][key]["file"]))
            txt = "".join(pg.get_text() for pg in doc)
            doc.close()
            if key.startswith("manual_scanned"):
                scan_ok = scan_ok and txt.strip() == ""
            else:
                text_ok = text_ok and len(txt.strip()) > 100
        if not (scan_ok and text_ok):
            print(f"[selftest] FAIL: scan_ok={scan_ok} text_ok={text_ok}")
            return 1
    print(f"[selftest] PASS: 生成 {expect} 份语料，文本层/无文本层特征符合预期")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 B1 全量解析用多文档模拟语料 PDF")
    ap.add_argument("--out-dir", type=Path,
                    default=Path("experiments/p1/b1-corpus"))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    meta = generate(args.out_dir, args.seed)
    n = len(meta["samples"])
    print(f"[OK] 已生成 {n} 份语料 → {args.out_dir}")
    for k, v in meta["samples"].items():
        print(f"  - {k:22s} {v['file']:28s} {v['bytes']:>7d} B")
    print(f"[OK] 元数据 → {args.out_dir / 'corpus.meta.json'}（synthetic=true, seed={args.seed}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())