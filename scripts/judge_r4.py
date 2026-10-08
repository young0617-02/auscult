"""R-4 本地证据归纳/诊断 判分器（ISS-014 专项）

对应验证项：R-4（读证据 → 写根因/结论 → 带 evidence_refs 引用）
判据依据：`docs/p0-spec-gate-criteria.md` §3.7（R4）｜ 专项登记：`docs/prj-ledger-known-issues.md` ISS-014
合规锁死：R-4 本地执行，本判分器不落库、不转云。

职责（与 `scripts/judge_tools.py` 架构对齐，但独立实现，本文件与 R-4 纯生成型归纳耦合）：
  1. 从 `evals/r4_cases.jsonl` 加载 20 条证据归纳用例，并校验用例自检不变量；
  2. 从 `prompts/r4_prompt_v1.md` 装配 System Prompt（注入 `generate_report.parameters`，
     经 `schemas/tools_v1.json` 单一来源）与 R-4 专用 few-shot，并构造消息；
  3. 从模型输出（`content_clean`）解析 generate_report 参数 JSON；
  4. 按维度判分（结构 / 引用忠实零幻觉 / 证据覆盖 / 根因正确 / severity / 建议动作）；
  5. 汇总各维度率（分子/分母分行）并 `verdict()` 分档判决（Pass/中间/No-Go）；
  6. 输出汇总表 CSV。

自检：`python scripts/judge_r4.py --selftest`
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = PROJECT_ROOT / "evals" / "r4_cases.jsonl"
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "tools_v1.json"
PROMPT_PATH = PROJECT_ROOT / "prompts" / "r4_prompt_v1.md"

# ---- 判据档位（§3.7 待定稿初值；整体 = 有数据维度的最差档位）----
# 每个维度: (pass_line, mid_lower, no_go_flag)。rate>=pass → pass；mid_lower<=rate<pass → 中间；rate<mid_lower → No-Go
DIM_STRUCT = ("structure_parseable", 0.90, 0.70)
DIM_HALLUC = ("hallucination_rate", 0.00, 0.00)   # 红线：=0 才 Pass；0<、<=0.15 中间；>0.15 No-Go
DIM_HALLUC_NOGO = 0.15
DIM_COVER = ("coverage_rate", 0.70, 0.50)
DIM_ROOT = ("root_cause_rate", 0.70, 0.50)
DIM_SEVERITY = ("severity_rate", 0.70, 0.50)
DIM_ACTIONS = ("actions_rate", 0.90, 0.70)

SEVERITIES = {"info", "warning", "critical"}
REAL_KINDS = ("real", "distractor")
FABRICATED_KIND = "fabricated"

# ---- 失败归类（互斥，按优先级）----
FAIL_STRUCT = "结构退化"
FAIL_HALLUC = "引用幻觉"
FAIL_MISS = "证据漏引"
FAIL_ROOT = "根因错"
FAIL_SEVERITY = "severity错"
FAIL_ACTIONS = "建议动作空"

_JSON_DECODER = json.JSONDecoder()
_FENCE_RE = re.compile(r"```(?:text|json)?\n(.*?)```", re.S)


# ---------------------------------------------------------------- 用例加载


def load_r4_cases(path: Path = CASES_PATH) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cases.append(json.loads(line))
    return cases


def validate_case_invariants(case: dict[str, Any]) -> list[str]:
    """返回用例自检违规列表（空 = 通过）。"""
    errors: list[str] = []
    cid = case.get("case_id", "?")
    refs: list[str] = []

    kinds = [e.get("kind") for e in case.get("evidence", []) if isinstance(e, dict)]
    if "real" not in kinds:
        errors.append(f"{cid}: evidence 缺 real 条目")
    if FABRICATED_KIND not in kinds:
        errors.append(f"{cid}: evidence 缺 fabricated 条目")
    # distractor 为可选（fabrication-trap 纯陷阱用例可不含，见 r4-016 计划示例）

    ev_by_kind: dict[str, set[str]] = {k: set() for k in ("real", "distractor", FABRICATED_KIND)}
    for e in case.get("evidence", []) or []:
        ref = e.get("ref")
        if not ref:
            errors.append(f"{cid}: evidence 条目缺 ref")
            continue
        if ref in refs:
            errors.append(f"{cid}: ref 重复 {ref}")
        refs.append(ref)
        ev_by_kind.setdefault(e.get("kind"), set()).add(ref)

    g = case.get("golden", {})
    for r in g.get("expected_refs", []):
        if r not in ev_by_kind["real"]:
            errors.append(f"{cid}: expected_refs {r} 不在 real 证据内")
    for r in g.get("distractor_refs", []):
        if r not in ev_by_kind["distractor"]:
            errors.append(f"{cid}: distractor_refs {r} 不在 distractor 证据内")
    for r in g.get("fabricated_must_not_refs", []):
        if r not in ev_by_kind[FABRICATED_KIND]:
            errors.append(f"{cid}: fabricated_must_not_refs {r} 不在 fabricated 证据内")

    if not g.get("root_cause_keywords"):
        errors.append(f"{cid}: golden.root_cause_keywords 为空")
    if g.get("severity") not in SEVERITIES:
        errors.append(f"{cid}: golden.severity 非法 {g.get('severity')}")
    schema_max_words = 2000
    for k in g.get("root_cause_keywords", []):
        if not isinstance(k, str) or not k:
            errors.append(f"{cid}: root_cause_keyword 非法 {k!r}")
    _ = schema_max_words
    pt = case.get("type")
    if pt not in ("sensor-only", "knowledge-only", "graph+maintenance",
                  "multi-source", "distractor-trap", "fabrication-trap"):
        errors.append(f"{cid}: type 非法 {pt!r}")
    return errors


# ---------------------------------------------------------------- 提示词装配


def inject_report_schema(schema_path: Path = SCHEMA_PATH) -> str:
    """从 tools_v1.json 单一来源抽取 generate_report.parameters 并序列化。"""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for tool in schema["tools"]:
        if tool.get("name") == "generate_report":
            return json.dumps(tool["parameters"], ensure_ascii=False, indent=2)
    raise ValueError(f"在 {schema_path} 中未找到 generate_report 工具")


def load_r4_system_prompt(prompt_path: Path = PROMPT_PATH,
                          schema_path: Path = SCHEMA_PATH) -> str:
    text = prompt_path.read_text(encoding="utf-8")
    m = re.search(r"##\s*一、System Prompt.*?```text\n(.*?)```", text, re.S)
    if not m:
        raise ValueError(f"未能在 {prompt_path} 中定位 System Prompt 代码块")
    system = m.group(1).strip()
    if "{{REPORT_JSON_SCHEMA}}" not in system:
        raise ValueError("System Prompt 缺少 {{REPORT_JSON_SCHEMA}} 占位符")
    return system.replace("{{REPORT_JSON_SCHEMA}}", inject_report_schema(schema_path))


def load_r4_fewshot(prompt_path: Path = PROMPT_PATH) -> list[dict[str, str]]:
    """抽取 prompt §二 的 few-shot 示例，转为 user/assistant 消息对。"""
    text = prompt_path.read_text(encoding="utf-8")
    section = re.search(r"##\s*二、Few-shot.*?(?=\n##\s*三、)", text, re.S)
    if not section:
        raise ValueError(f"未能在 {prompt_path} 中定位 Few-shot 章节")
    messages: list[dict[str, str]] = []
    for block in re.findall(r"###\s*示例.*?```(?:text|json)?\n(.*?)```", section.group(0), re.S):
        user_part = re.search(r"user:\s*(.*?)(?=\n\s*assistant:)", block, re.S)
        asst_part = re.search(r"assistant:\s*(.*)", block, re.S)
        if not user_part or not asst_part:
            continue
        messages.append({"role": "user", "content": user_part.group(1).strip()})
        messages.append({"role": "assistant", "content": asst_part.group(1).strip()})
    return messages


def _serialize_evidence_for_user(case: dict[str, Any]) -> str:
    lines = [f"设备：{case.get('device_id')}", f"场景：{case.get('scenario')}", "证据条目："]
    for e in case.get("evidence", []) or []:
        lines.append(
            f"- [{e.get('id')}] ({e.get('type')}) ref={e.get('ref')}：{e.get('content')}"
        )
    lines.append(
        "请输出 generate_report 参数 JSON（diagnosis_summary / evidence_refs / "
        "severity / recommended_actions / idempotency_key / device_id）。"
    )
    return "\n".join(lines)


def build_r4_messages(case: dict[str, Any], system_prompt: str,
                      fewshot: bool = True,
                      prompt_path: Path = PROMPT_PATH) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]
    if fewshot:
        messages.extend(load_r4_fewshot(prompt_path))
    messages.append({"role": "user", "content": _serialize_evidence_for_user(case)})
    return messages


# ---------------------------------------------------------------- JSON 解析


def parse_report_args(text: str) -> tuple[dict[str, Any] | None, str]:
    """从内容中抽取第一个含 diagnosis_summary 的 JSON 对象。

    容错三种形态：① 直接 JSON 对象；② Markdown 围栏包裹的 JSON；③ 前后夹带说明文字。
    返回 (解析后的 dict, 错误信息)。错误时 dict 为 None。
    """
    if not text or not text.strip():
        return None, "输出为空"

    candidates: list[str] = []
    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1))
    candidates.append(text)

    for blob in candidates:
        idx = 0
        while idx < len(blob):
            start = blob.find("{", idx)
            if start < 0:
                break
            try:
                obj, end = _JSON_DECODER.raw_decode(blob[start:])
            except json.JSONDecodeError:
                idx = start + 1
                continue
            if isinstance(obj, dict) and "diagnosis_summary" in obj:
                return obj, ""
            # 兼容 `{"report": {...}}` / `{"arguments": {...}}` / `{"tool_calls":[...]}` 包装
            if isinstance(obj, dict):
                for container in (obj.get("report"), obj.get("arguments")):
                    if isinstance(container, dict) and "diagnosis_summary" in container:
                        return container, ""
                for tc in (obj.get("tool_calls") or []):
                    if not isinstance(tc, dict):
                        continue
                    inner = tc.get("arguments")
                    if isinstance(inner, dict) and "diagnosis_summary" in inner:
                        return inner, ""
                    if "diagnosis_summary" in tc:
                        return tc, ""
            idx = start + end
    return None, "未找到含 diagnosis_summary 的合法 JSON 对象"


# ---------------------------------------------------------------- 单条判分


def judge_case(case: dict[str, Any], output: dict[str, Any] | None,
               result: dict[str, Any]) -> dict[str, Any]:
    """对模型输出的 generate_report 参数做维度判分。"""
    golden = case.get("golden", {})
    evidence = case.get("evidence", []) or []
    real_refs = {e["ref"] for e in evidence if e.get("kind") in REAL_KINDS}
    distractor_refs = {e["ref"] for e in evidence if e.get("kind") == "distractor"}
    fabricated_refs = {e["ref"] for e in evidence if e.get("kind") == FABRICATED_KIND}
    expected_refs = set(golden.get("expected_refs", []))
    root_keywords = golden.get("root_cause_keywords", [])
    golden_severity = golden.get("severity")

    # ---- 结构 ----
    if output is None:
        reason = result.get("error") or "无法解析 generate_report 参数"
        cited: set[str] = set()
        summary = ""
        severity = None
        actions = []
        structure_ok = False
    else:
        summary = str(output.get("diagnosis_summary") or "")
        refs_raw = output.get("evidence_refs")
        cited = {r.get("ref") for r in refs_raw
                 if isinstance(refs_raw, list) and isinstance(r, dict) and r.get("ref")}
        severity = output.get("severity")
        actions = output.get("recommended_actions")
        has_idem = isinstance(output.get("idempotency_key"), str) and bool(
            re.fullmatch(r"[A-Za-z0-9_-]{8,64}", output.get("idempotency_key") or ""))
        structure_ok = (
            isinstance(output.get("diagnosis_summary"), str)
            and len(summary) >= 10 and len(summary) <= 2000
            and len(cited) >= 1
            and severity in SEVERITIES
            and isinstance(actions, list) and len(actions) >= 1
            and has_idem
        )

    # ---- 根因（must_have 关键词全含）----
    root_cause_ok = bool(summary) and all(k and k in summary for k in root_keywords)

    # ---- 引用忠实（红线：零幻觉 / 零包外）----
    hallucinated = cited - real_refs
    over_cited = cited & distractor_refs
    citation_honest = len(hallucinated) == 0
    missed = expected_refs - cited
    coverage_ok = len(missed) == 0

    severity_ok = severity == golden_severity
    actions_ok = isinstance(actions, list) and len(actions) > 0

    success = (structure_ok and root_cause_ok and citation_honest
               and coverage_ok and severity_ok and actions_ok)

    # ---- 失败归类（互斥，按优先级）----
    if not structure_ok:
        failure = FAIL_STRUCT
    elif not citation_honest:
        failure = FAIL_HALLUC
    elif not coverage_ok:
        failure = FAIL_MISS
    elif not root_cause_ok:
        failure = FAIL_ROOT
    elif not severity_ok:
        failure = FAIL_SEVERITY
    elif not actions_ok:
        failure = FAIL_ACTIONS
    else:
        failure = None

    return {
        "case_id": case.get("case_id"),
        "structure_ok": structure_ok,
        "root_cause_ok": root_cause_ok,
        "citation_honest": citation_honest,
        "hallucinated_refs": sorted(hallucinated),
        "over_cited": sorted(over_cited),
        "missed": sorted(missed),
        "coverage_ok": coverage_ok,
        "severity_ok": severity_ok,
        "actions_ok": actions_ok,
        "hallucinated": bool(hallucinated),
        "success": success,
        "failure": failure,
        "_reason": result.get("error") or "",
    }


# ---------------------------------------------------------------- 汇总与分档


def _rate(ok: list[bool]) -> float | None:
    if not ok:
        return None
    return sum(bool(x) for x in ok) / len(ok)


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    return xs[int(len(xs) * 0.95) - 1]


def aggregate(judged: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(judged)
    dims = {
        "structure_parseable": _rate([j["structure_ok"] for j in judged]),
        "root_cause_rate": _rate([j["root_cause_ok"] for j in judged]),
        "citation_faithful_rate": _rate([j["citation_honest"] for j in judged]),
        "hallucination_rate": _rate([j["hallucinated"] for j in judged]),
        "coverage_rate": _rate([j["coverage_ok"] for j in judged]),
        "severity_rate": _rate([j["severity_ok"] for j in judged]),
        "actions_rate": _rate([j["actions_ok"] for j in judged]),
        "success_rate_first": _rate([j["success"] for j in judged]),
    }
    # 重试后成功率（同一 (case,model) 最后一次 attempt 判成功）
    by_case: dict[str, dict[str, Any]] = {}
    for j in judged:
        by_case[j["case_id"]] = j          # 记录按 attempt 顺序写入，末次覆盖
    dims["success_rate_retry"] = _rate([j["success"] for j in by_case.values()])

    lat = [j.get("_latency_ms") for j in judged if j.get("_latency_ms") is not None]
    dims["mean_latency_ms"] = _mean(lat)
    dims["p95_latency_ms"] = _p95(lat)
    dims["total_cases"] = n
    dims["n_by_failure"] = {}
    for j in judged:
        dims["n_by_failure"][j.get("failure") or "success"] = \
            dims["n_by_failure"].get(j.get("failure") or "success", 0) + 1
    return dims


def _tier_rate(rate: float | None, pass_line: float, mid_lower: float) -> str:
    if rate is None:
        return "无数据"
    if rate >= pass_line:
        return "Pass"
    if rate < mid_lower:
        return "No-Go"
    return "中间区间"


def _tier_halluc(rate: float | None) -> str:
    """红线维度：引用幻觉率。仅 ==0 判 Pass；0<rate<=0.15 中间；>0.15 No-Go。"""
    if rate is None:
        return "无数据"
    if rate == 0.0:
        return "Pass"
    if rate <= DIM_HALLUC_NOGO:
        return "中间区间"
    return "No-Go"


def verdict(metrics: dict[str, Any]) -> dict[str, str]:
    """按维度分档并合成整体（整体 = 有数据维度的最差档位）。"""
    tiers: dict[str, str] = {}
    for dim, pass_line, mid_lower in (DIM_STRUCT, DIM_COVER, DIM_ROOT,
                                      DIM_SEVERITY, DIM_ACTIONS):
        tiers[dim] = _tier_rate(metrics.get(dim), pass_line, mid_lower)
    tiers[DIM_HALLUC[0]] = _tier_halluc(metrics.get(DIM_HALLUC[0]))
    rank = {"Pass": 0, "中间区间": 1, "No-Go": 2, "无数据": -1}
    present = [v for v in tiers.values() if v != "无数据"]
    if not present:
        tiers["overall"] = "无数据"
    else:
        tiers["overall"] = max(present, key=lambda v: rank[v])
    return tiers


# ---------------------------------------------------------------- CSV


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def write_summary_csv(summary: dict[str, Any], tiers: dict[str, str],
                      out_path: Path) -> None:
    rows: list[tuple[str, str]] = []
    metric_order = [
        ("total_cases", "用例总数"), ("structure_parseable", "结构可解析率"),
        ("root_cause_rate", "根因正确率"), ("citation_faithful_rate", "引用忠实率"),
        ("hallucination_rate", "幻觉率[红线]"), ("coverage_rate", "证据覆盖率"),
        ("severity_rate", "severity匹配率"), ("actions_rate", "建议动作非空率"),
        ("success_rate_first", "首次成功率"), ("success_rate_retry", "重试后成功率"),
        ("mean_latency_ms", "平均延迟_ms"), ("p95_latency_ms", "P95延迟_ms"),
        ("n_by_failure", "失败分布"),
    ]
    for key, label in metric_order:
        rows.append((label, _csv_cell(summary.get(key))))
    for dim in (DIM_STRUCT[0], DIM_HALLUC[0], DIM_COVER[0], DIM_ROOT[0],
                DIM_SEVERITY[0], DIM_ACTIONS[0]):
        rows.append((f"{dim}_档位", tiers.get(dim, "")))
    rows.append(("overall_档位", tiers.get("overall", "")))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "\n".join(f"{label},{value}" for label, value in rows) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------- 主流程


def load_records(raw_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R-4 本地证据归纳/诊断 判分器")
    parser.add_argument("--raw", type=Path, default=None, help="原始结果 JSONL")
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="R-4 用例 JSONL")
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH, help="tools schema")
    parser.add_argument("--prompt", type=Path, default=PROMPT_PATH, help="R-4 提示词")
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "experiments" / "r4" / "summary.csv",
                        help="汇总 CSV 输出")
    parser.add_argument("--detail-out", type=Path, default=None, help="逐条明细 CSV")
    parser.add_argument("--selftest", action="store_true", help="运行判分器自检（不联网）")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.raw is None:
        parser.error("--raw 必填（原始 JSONL）")
    records = load_records(args.raw)
    if not records:
        parser.error(f"--raw 为空或不存在：{args.raw}")

    judgments = []
    for rec in records:
        case = rec.get("expected", {})
        result = rec.get("result", {})
        output_txt = result.get("content_clean") or result.get("content_raw") or ""
        output, _ = parse_report_args(output_txt)
        j = judge_case(case, output, result)
        j["_latency_ms"] = result.get("latency_ms")
        j["_attempt"] = rec.get("attempt")
        judgments.append(j)
        if args.detail_out:
            # 明细行
            pass

    summary = aggregate(judgments)
    tiers = verdict(summary)
    write_summary_csv(summary, tiers, args.out)
    if args.detail_out:
        write_detail_csv(judgments, args.detail_out)

    print("\n== R-4 判分汇总 ==")
    for label, key in [("用例总数", "total_cases"), ("结构可解析率", "structure_parseable"),
                       ("根因正确率", "root_cause_rate"), ("引用忠实率", "citation_faithful_rate"),
                       ("幻觉率[红线]", "hallucination_rate"), ("证据覆盖率", "coverage_rate"),
                       ("severity匹配率", "severity_rate"), ("首次成功率", "success_rate_first")]:
        val = summary.get(key)
        print(f"  {label}: {val if val is None else round(val, 4)}")
    for k, v in tiers.items():
        print(f"  {k}_档位: {v}")
    print(f"写入 → {args.out}")
    return 0


def write_detail_csv(judgments: list[dict[str, Any]], out_path: Path) -> None:
    headers = ["case_id", "structure_ok", "root_cause_ok", "citation_honest",
               "hallucinated_refs", "over_cited", "missed", "coverage_ok",
               "severity_ok", "actions_ok", "hallucinated", "success", "failure"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(",".join(headers) + "\n")
        for j in judgments:
            fh.write(",".join(_csv_cell(j.get(h)) for h in headers) + "\n")


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    failures: list[str] = []

    cases = load_r4_cases()
    if len(cases) != 20:
        failures.append(f"R-4 用例数应为 20，实际 {len(cases)}")
    for c in cases:
        errs = validate_case_invariants(c)
        if errs:
            failures.append(f"{c['case_id']}: " + "; ".join(errs))
    type_check = {c["type"] for c in cases}
    if any(t not in type_check for t in
           ("sensor-only", "knowledge-only", "graph+maintenance",
            "multi-source", "distractor-trap", "fabrication-trap")):
        failures.append("用例类型覆盖不全")

    # schema 注入
    schema_json = inject_report_schema()
    if "evidence_refs" not in schema_json or "diagnosis_summary" not in schema_json:
        failures.append("inject_report_schema 未含 generate_report 必填字段")
    system = load_r4_system_prompt()
    if "{{REPORT_JSON_SCHEMA}}" in system or '"evidence_refs"' not in system:
        failures.append("R-4 System Prompt 注入失败")
    few = load_r4_fewshot()
    if len(few) != 4:
        failures.append(f"R-4 few-shot 应为 2 组共 4 条消息，实际 {len(few)}")
    elif few[1]["role"] != "assistant":
        failures.append("R-4 few-shot 角色顺序错误")

    # 消息构造
    msgs = build_r4_messages(cases[0], system, fewshot=True)
    if msgs[0]["role"] != "system" or msgs[-1]["role"] != "user":
        failures.append("R-4 消息构造角色顺序错误")
    if "PUMP-A-01.vib_x" not in msgs[-1]["content"]:
        failures.append("R-4 user 消息未正确序列化证据包")

    # parse_report_args 三形态
    good = ('{"device_id":"PUMP-A-01","diagnosis_summary":"驱动端轴承磨损",'
            '"evidence_refs":[{"type":"sensor","ref":"PUMP-A-01.vib_x"}],'
            '"severity":"warning","recommended_actions":["x"],"idempotency_key":"abcDEF12345"}')
    obj, err = parse_report_args(good)
    if err or obj.get("diagnosis_summary") != "驱动端轴承磨损":
        failures.append("直接 JSON 形态解析失败")
    fenced = f"```json\n{good}\n```"
    obj2, _ = parse_report_args(fenced)
    if not obj2:
        failures.append("Markdown 围栏形态解析失败")
    wrapped = '{"tool_calls": [' + good + "]}"
    obj3, _ = parse_report_args("以下是参数：" + wrapped)
    if not obj3:
        failures.append("对象包装/夹带文字形态解析失败")
    bad, _ = parse_report_args("抱歉，我无法诊断，也不输出 JSON。")
    if bad is not None:
        failures.append("非 JSON 输出不应解析出参数")

    # judge_case：伪造命中应判幻觉
    tr = {"content_clean": json.dumps(
        {"diagnosis_summary": "驱动端轴承磨损，依据振动证据。",
         "evidence_refs": [{"type": "sensor", "ref": "PUMP-A-01.vib_x"},
                           {"type": "knowledge", "ref": "doc-fake-nu210"}],
         "severity": "warning", "recommended_actions": ["x"],
         "idempotency_key": "abcDEF12345"})}
    empty = {"content_clean": ""}
    j_halluc = judge_case(cases[0], parse_report_args(tr["content_clean"])[0], tr)
    if not j_halluc["hallucinated"] or "doc-fake-nu210" not in j_halluc["hallucinated_refs"]:
        failures.append("伪造 ref 未判幻觉")
    if j_halluc["success"]:
        failures.append("含伪造引用的用例不应 success")
    j_empty = judge_case(cases[0], None, empty)
    if j_empty["structure_ok"] or j_empty["failure"] != FAIL_STRUCT:
        failures.append("空输出未判结构退化")

    # 分档合成
    fake = {"structure_parseable": 0.95, "hallucination_rate": 0.0, "coverage_rate": 0.80,
            "root_cause_rate": 0.75, "severity_rate": 0.80, "actions_rate": 0.95}
    if verdict(fake)["overall"] != "Pass":
        failures.append("全 Pass 样本未合成 Pass")
    fake2 = dict(fake, hallucination_rate=0.3)
    if verdict(fake2)["overall"] != "No-Go":
        failures.append("幻觉超红线未合成 No-Go")

    if failures:
        print("[FAIL] judge_r4 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] judge_r4 自检通过：用例不变量 / schema 注入 / few-shot / 消息构造 / "
          "parse 三形态 / 幻觉红线 / 失败归类 / 分档合成")
    return 0


if __name__ == "__main__":
    sys.exit(main())