# -*- coding: utf-8 -*-
"""B1 批量解析脚本（P1-D3/D4 · B1）：调用 MinerU 逐份解析语料 PDF。

输入：目录下的全部 `*.pdf`（默认 `experiments/p1/b1-corpus/`）。
输出：对每份 PDF 生成两个文件到 `parsed/`（可用 `--output` 指定）：
  - `<stem>.md`   结构化 Markdown（含标题层级/表格/页边界）
  - `<stem>.json` 版面包装 JSON（含 sha256 / page_range / content_ranges / content 原文）
利用 mineru `parse --json` 的 stdout 一次调用同时产出两者（`content` 字段即 .md）。
失败处理：单文件失败重试 2 次（共 3 次尝试），结束汇总批量失败率，
按 `plan/p1-plan-detailed.md` §7.1 判据判定（≤5% 通过）。

依赖：MinerU 4.0.10 隔离环境（`.venv-mineru`），需已 `server start`；
模型环境变量 `MINERU_MODEL_BASE_DIR=D:\\modelscope\\hub\\models`、
`MINERU_MODEL_SOURCE=local`。见 `docs/prj-ledger-version-lock.md` §二.2.11。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "experiments" / "p1" / "b1-corpus"
DEFAULT_OUTPUT = PROJECT_ROOT / "parsed"
MAX_ATTEMPTS = 3  # 单文件失败重试 2 次 = 共 3 次尝试（§5.4）
FAIL_RATE_LIMIT = 0.05  # §7.1 批量失败率 ≤5%


def _mineru_env() -> dict:
    env = dict(os.environ)
    env.setdefault("MINERU_MODEL_BASE_DIR", r"D:\modelscope\hub\models")
    env.setdefault("MINERU_MODEL_SOURCE", "local")
    env.setdefault("PYTHONUTF8", "1")
    return env


def _extract_payload(stdout: str) -> tuple[dict | None, str | None]:
    """从 mineru stdout 提取 {content:多行JSON, error:末尾摘要}。

    解析时忽略首尾日志噪声，从首个 `{` 取到与 `}` 平衡的最长 JSON。
    """
    start = stdout.find("{")
    if start < 0:
        return None, stdout.strip().splitlines()[-1][:120] if stdout.strip() else "NO_STDOUT"
    # 括号平衡截取
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(stdout)):
        ch = stdout[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = stdout[start:i + 1]
                try:
                    return json.loads(body), None
                except Exception as e:  # noqa: BLE001
                    return None, f"BROKEN_JSON:{e}"
    return None, "NO_BALANCED_JSON"


def run_mineru(executable: Path, pdf: Path, tier: str, wait: int) -> tuple[dict | None, str]:
    """调用 `mineru parse ... --json`，返回 (payload, 错误摘要)。"""
    cmd = [
        str(executable), "parse", str(pdf),
        "--tier", tier, "--pages", "all", "--wait", str(wait), "--json",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, env=_mineru_env(),
                             timeout=wait + 180, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    stdout = (res.stdout or "")
    if res.returncode != 0:
        return None, (res.stderr or stdout).strip().splitlines()[-1][:120]
    payload, err = _extract_payload(stdout)
    if err:
        return None, err
    return payload, ""


def parse_one(executable: Path, pdf: Path, out_dir: Path, tier: str, wait: int) -> dict:
    """解析单份 PDF，产出 md 与 json，返回状态。"""
    stem = pdf.stem
    result = {"file": stem, "pdf_bytes": pdf.stat().st_size,
              "ok": False, "errors": [], "md_bytes": 0, "json_bytes": 0}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"  [parse] {stem} 尝试 {attempt}/{MAX_ATTEMPTS} ...", flush=True)
        payload, reason = run_mineru(executable, pdf, tier, wait)
        if payload is not None:
            break
        result["errors"].append(f"#{attempt}:{reason}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(2)

    if payload is None:
        print(f"  [FAIL] {stem}（重试耗尽 3 次）")
        return result

    md_text = (payload.get("content") or {}).get("content") or ""

    md_out = out_dir / f"{stem}.md"
    json_out = out_dir / f"{stem}.json"
    md_out.write_text(md_text, encoding="utf-8")
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result.update(ok=True, md_bytes=md_out.stat().st_size,
                  json_bytes=json_out.stat().st_size)
    print(f"  [OK] {stem}: md={result['md_bytes']}B json={result['json_bytes']}B", flush=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="B1 批量调用 MinerU 解析语料 PDF")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--mineru", type=Path,
                    default=PROJECT_ROOT / ".venv-mineru" / "Scripts" / "mineru.exe")
    ap.add_argument("--tier", default="basic")
    ap.add_argument("--wait", type=int, default=600)
    ap.add_argument("--pdf", default=None, help="仅解析指定单个 PDF 文件名（调试用）")
    args = ap.parse_args()

    pdfs = sorted(args.input.rglob("*.pdf"))
    if args.pdf:
        pdfs = [args.input / args.pdf] if (args.input / args.pdf).exists() else []
        if not pdfs:
            print(f"[ERROR] 未找到 {args.input / args.pdf}")
            return 2

    if not pdfs:
        print(f"[ERROR] {args.input} 下无 *.pdf")
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    print(f"[run] 待解析 {len(pdfs)} 份 → {args.tier} 档")
    results = []
    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.name}")
        results.append(parse_one(args.mineru, pdf, args.output, args.tier, args.wait))

    total = len(results)
    ok_docs = [r for r in results if r["ok"]]
    fail_docs = [r for r in results if not r["ok"]]
    fail_rate = len(fail_docs) / total if total else 1.0

    print("\n=== 解析汇总 ===")
    print(f"总数={total}  成功={len(ok_docs)}  失败={len(fail_docs)}  失败率={fail_rate:.2%}")
    if fail_docs:
        print("失败清单：")
        for r in fail_docs:
            print(f"  - {r['file']}: {r['errors']}")

    gate = fail_rate <= FAIL_RATE_LIMIT
    print(f"判据（§7.1 失败率 ≤ {FAIL_RATE_LIMIT:.0%}）："
          f"{'✅ 通过' if gate else '❌ 未通过（触发替代解析评估，§7.2）'}")

    summary = {
        "input": str(args.input), "output": str(args.output),
        "tier": args.tier, "total": total,
        "success": len(ok_docs), "fail": len(fail_docs), "fail_rate": fail_rate,
        "gate": gate,
    }
    (args.output / "_parse_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())