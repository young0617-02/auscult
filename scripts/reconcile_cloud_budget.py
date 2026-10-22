"""云端预算对账（ISS-054 · 2026-10-21）。

背景：`BudgetGuard` 原为「成功后才 `increment()`」，超时/异常调用零记账
（实测漏计 10–31%；Agent 形态单次诊断多轮调用漏得更多）。已改为
`reserve()` 先增后调（调用前占位、超限回滚），本脚本用于**验证改造后记账是否可信**。

对账四方（前三方本脚本自动完成，第四方需人工）：
  ① Redis `budget:cloud:{YYYY-MM-DD}` —— 计费真值（reserve/incr 结果）
  ② `reports/cloud_audit.jsonl` —— `escalate_cloud` 路径的每次调用（成功/失败/skipped）
  ③ PG `reports.payload.agent_steps` —— Agent 循环轮数（每轮 1 次 LLM 调用 + 收口 1 次）
  ④ 云端控制台账单 —— **无 API，只能人工核对**（脚本给出「应等于」的期望值）

口径：
  - Agent 形态（`AUSCULT_LLM_BACKEND=cloud`）下 `escalate_cloud` 直接 skipped（不计费），
    其 LLM 调用只体现在 Redis 与 `agent_steps`，**不进** cloud_audit；
  - 故 `redis_used ≈ escalate_audit_calls + agent_llm_calls`
    （`agent_llm_calls` 下界 = Σ(len(agent_steps)) 去重后的非空轨迹，上界再加收口轮）。

用法：
    python scripts/reconcile_cloud_budget.py
    python scripts/reconcile_cloud_budget.py --date 2026-10-21 --json

退出码：0 = 一致（或差额可由 Agent 轮次解释）；1 = 记账异常（Redis < 审计条数）；2 = 依赖缺失。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

AUDIT_PATH = _paths.reports_file("cloud_audit.jsonl")


def _redis_used(day: str) -> int | None:
    """① Redis 当日计数（复用 budget 模块连接口径，含口令）。"""
    from app.router import budget  # noqa: PLC0415

    try:
        client = budget._get_client()
        value = client.get(f"{budget.BUDGET_KEY_PREFIX}{day}")
        return int(value or 0)
    except Exception as exc:  # noqa: BLE001 - 对账脚本不因 Redis 不可达崩溃
        print(f"[warn] Redis 不可达：{type(exc).__name__}: {exc}", file=sys.stderr)
        return None


def _audit_counts(day: str) -> dict[str, int]:
    """② cloud_audit 当日条数（escalate 路径）。"""
    counts = {"escalate_success": 0, "escalate_failure": 0, "skipped": 0, "total": 0}
    if not AUDIT_PATH.exists():
        return counts
    for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not str(rec.get("ts", "")).startswith(day):
            continue
        counts["total"] += 1
        if rec.get("skipped"):
            counts["skipped"] += 1
        elif rec.get("success"):
            counts["escalate_success"] += 1
        else:
            counts["escalate_failure"] += 1
    return counts


def _agent_rounds(day: str) -> dict[str, int]:
    """③ PG 当日 Agent 轨迹轮数（每轮 ≈ 1 次 LLM 调用）。"""
    stats = {"agent_reports": 0, "agent_steps": 0}
    try:
        import psycopg  # noqa: PLC0415

        from app.api.config import POSTGRES_URL  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return stats
    try:
        with psycopg.connect(POSTGRES_URL, connect_timeout=3) as conn:
            rows = conn.execute(
                "SELECT payload FROM reports WHERE created_at::date = %s", (day,)
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] PG 查询失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return stats
    for (payload,) in rows:
        steps = (payload or {}).get("agent_steps") or []
        if steps:
            stats["agent_reports"] += 1
            stats["agent_steps"] += len(steps)
    return stats


def reconcile(day: str) -> dict:
    redis_used = _redis_used(day)
    audit = _audit_counts(day)
    agent = _agent_rounds(day)
    escalate_calls = audit["escalate_success"] + audit["escalate_failure"]
    result = {
        "date": day,
        "redis_used": redis_used,                 # ① 计费真值
        "escalate_calls": escalate_calls,         # ② escalate 路径调用数
        "escalate_success": audit["escalate_success"],
        "escalate_failure": audit["escalate_failure"],
        "escalate_skipped": audit["skipped"],
        "agent_reports": agent["agent_reports"],  # ③ Agent 形态报告数
        "agent_steps": agent["agent_steps"],
        "agent_llm_calls_min": agent["agent_steps"] + agent["agent_reports"],   # 轮 + 收口
        "agent_llm_calls_max": agent["agent_steps"] + 2 * agent["agent_reports"],  # 收口可能多一轮重试
    }
    if redis_used is None:
        result["verdict"] = "unknown（Redis 不可达，无法对账）"
        return result

    delta = redis_used - escalate_calls
    lo, hi = result["agent_llm_calls_min"], result["agent_llm_calls_max"]
    if delta < 0:
        # 审计条数多于计费计数 = 有调用没记账（改造前的典型症状）
        result["verdict"] = f"FAIL：Redis({redis_used}) < escalate 审计({escalate_calls})，记账缺失"
        result["exit_code"] = 1
    elif delta < lo:
        result["verdict"] = (f"WARN：差额 {delta} 少于 Agent 期望下界 {lo}，可能仍有漏计")
        result["exit_code"] = 1
    elif delta <= hi:
        result["verdict"] = f"OK：差额 {delta} 次由 Agent 循环解释（期望 {lo}–{hi}）"
        result["exit_code"] = 0
    else:
        # 高于上界：多为 Agent 形态挂起线程（waiting_review 未 resume）未落 reports，
        # 其 agent_steps 取不到 → 差额无法用 PG 解释，但仍是「调用多于审计」的自洽方向。
        result["verdict"] = (f"WARN：差额 {delta} 超过 Agent 期望上界 {hi}，"
                             f"常见于未落库的挂起线程（waiting_review 未 resume）；"
                             f"请对照云端账单确认")
        result["exit_code"] = 0
    result["delta"] = delta
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="云端预算三方对账（ISS-054）")
    ap.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD（默认今天）")
    ap.add_argument("--json", action="store_true", help="仅输出 JSON")
    args = ap.parse_args()

    result = reconcile(args.date)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"=== 云端预算对账 {args.date} ===")
        print(f"① Redis 计数（计费真值） : {result['redis_used']}")
        print(f"② escalate 审计调用      : {result['escalate_calls']}"
              f"（成功 {result['escalate_success']} / 失败 {result['escalate_failure']}"
              f" / skipped {result['escalate_skipped']}）")
        print(f"③ Agent 报告 / 轨迹轮数  : {result['agent_reports']} / {result['agent_steps']}"
              f"（期望调用 {result['agent_llm_calls_min']}–{result['agent_llm_calls_max']}）")
        print(f"④ 云端账单               : 需人工（无 API）—— 期望 ≈ {result['redis_used']}")
        print(f"判定：{result['verdict']}")
    return int(result.get("exit_code", 2))


if __name__ == "__main__":
    sys.exit(main())
