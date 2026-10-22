"""历史报告脱敏代号清理（ISS-062 遗留 · 2026-10-22）。

背景：ISS-062（2026-10-21 已修复）只修了**新报告**的出口——`_finalize_answer._restore_device`
把代号还原为真实设备号，且 `AUSCULT_SANITIZE_OUTBOUND=auto` 让本地后端根本不掩码。
但**修复之前落库**的历史报告（ISS-062 记录：2026-10-21 当天 8 份中 3 份）`payload` 里
仍是 `设备#f6de90` 这类代号，且 payload 无 `device_id` 字段，无法逐份反查。本脚本做补偿清理。

做法（与出口同一算法，不引入第二套口径）：
  1. 从 PG 已知设备编号来源收集候选：`alerts.device_id` ∪ `work_orders.device_id`
     （`--extra PUMP-X-99` 可追加；这两张表覆盖不到的设备不会被错杀，只会进 unmapped）；
     **候选集会补上另一套编号形态**（`app.device_ids` 双向映射）——历史代号是按**当时**的
     设备号取的 hash，迁移前是 `PUMP-A`、迁移后是 `PUMP-A-01`；库里如今只剩规范编号，
     不补变体则旧代号永远不可映射（实测 `设备#f6de90` = `PUMP-A`）；
  2. 用 `app.router.cloud.hash_device_id`（sha256[:6]）建**反查表** `设备#xxxxxx → device_id`
     （还原值是 hash 的原文，不改成当前口径——历史报告是证据，零猜测优先）；
  3. 扫描 `reports.payload`（JSONB）文本里的 `设备#[0-9a-f]{6}` 代号，**能全映射才替换**；
  4. 无法映射的代号**不猜、原样保留**，列入 unmapped 清单交人工——口号：宁可漏还原，
     不可错还原（把代号替换成错误设备号，比留着代号更糟）。

安全口径：
  - **默认 dry-run**（只打印将要改什么），`--apply` 才落 UPDATE；
  - 只改 payload 文本，不动 `report_id` / `idempotency_key` / 其他列（幂等键不变，
    不会与既有报告撞键，报告仍可被 `GET /api/reports/{id}` 原样取到）；
  - 可重复执行（已清理的报告扫不到代号即跳过，第二次跑是 no-op）。

用法：
    python scripts/restore_masked_device_ids.py                  # dry-run（默认）
    python scripts/restore_masked_device_ids.py --apply          # 落库
    python scripts/restore_masked_device_ids.py --apply --json   # 机读输出
    python scripts/restore_masked_device_ids.py --extra PUMP-A-01 --extra MOTOR-1

退出码：0 = 无待清理或全部成功；1 = 存在无法映射的代号（需人工处置）；2 = PG 不可达/依赖缺失。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

#: 脱敏代号形态：设备# + sha256[:6]（与 `cloud.hash_device_id` 逐字同口径）
_TOKEN_RE = re.compile(r"设备#[0-9a-f]{6}")

#: 候选设备编号的 PG 来源（离线环境不可连时由 --extra 兜底）
_CANDIDATE_QUERIES = (
    "SELECT DISTINCT device_id FROM alerts",
    "SELECT DISTINCT device_id FROM work_orders",
)


def build_reverse_map(candidates: set[str]) -> dict[str, str]:
    """候选设备编号 → `设备#<hash>` 反查表（hash 口径 = 出口同算法）。"""
    from app.router.cloud import hash_device_id          # noqa: PLC0415

    return {hash_device_id(dev): dev for dev in candidates if dev}


def _with_scheme_variants(candidates: set[str]) -> set[str]:
    """候选集补上「另一套编号形态」（迁移前短编号 / 迁移后规范编号）。

    历史报告的 `设备#xxxxxx` 是按**当时**的设备号取的 hash：迁移前 `PUMP-A`、迁移后
    `PUMP-A-01`。库内如今只剩规范编号，不补变体则旧代号永远不可映射（实测 `设备#f6de90`
    = `PUMP-A`）。两套形态的 hash 不同，进同一张反查表不会互相覆盖。
    """
    from app.device_ids import CANONICAL_TO_LEGACY, LEGACY_TO_CANONICAL  # noqa: PLC0415

    out: set[str] = set(candidates)
    for dev in candidates:
        out.add(CANONICAL_TO_LEGACY.get(dev, dev))
        out.add(LEGACY_TO_CANONICAL.get(dev, dev))
    return {d for d in out if d}


def collect_candidates(conn: object, extra: list[str] | None = None) -> set[str]:
    """从 alerts / work_orders 收集库里出现过的设备编号（去空、去空白，含双口径变体）。"""
    found: set[str] = set(d.strip() for d in (extra or []) if d and d.strip())
    with conn.cursor() as cur:                            # type: ignore[attr-defined]
        for sql in _CANDIDATE_QUERIES:
            try:
                cur.execute(sql)
                found.update(str(r[0]).strip() for r in cur.fetchall() if r and r[0])
            except Exception as exc:                      # noqa: BLE001 - 单表失败不阻断
                print(f"[warn] 候选查询失败（{sql.split()[-1]}）："
                      f"{type(exc).__name__}: {exc}", file=sys.stderr)
    return _with_scheme_variants({d for d in found if d})


def restore_payload_text(payload_text: str,
                         reverse: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """payload 文本里的代号还原。

    返回 (新文本, 命中的代号, 无法映射的代号)。无法映射的代号原样保留。
    """
    tokens = sorted(set(_TOKEN_RE.findall(payload_text)))
    if not tokens:
        return payload_text, [], []
    unresolved = [t for t in tokens if t not in reverse]
    new_text = payload_text
    for token in tokens:
        if token in reverse:
            new_text = new_text.replace(token, reverse[token])
    return new_text, tokens, unresolved


def scan_reports(conn: object, reverse: dict[str, str]) -> list[dict]:
    """扫描 reports 表，返回每份含代号报告的处理计划（不写库）。"""
    plans: list[dict] = []
    with conn.cursor() as cur:                            # type: ignore[attr-defined]
        cur.execute("SELECT report_id, payload::text FROM reports ORDER BY created_at")
        for report_id, payload_text in cur.fetchall():
            payload_text = payload_text or ""
            new_text, tokens, unresolved = restore_payload_text(payload_text, reverse)
            if not tokens:
                continue
            plans.append({
                "report_id": report_id,
                "tokens": tokens,
                "mapping": {t: reverse[t] for t in tokens if t in reverse},
                "unresolved": unresolved,
                "changed": new_text != payload_text,
                "new_payload": new_text,
            })
    return plans


def apply_plan(conn: object, plan: dict) -> None:
    """落库：仅替换 payload 文本（其余列不动，幂等键不变）。"""
    with conn.cursor() as cur:                            # type: ignore[attr-defined]
        cur.execute("UPDATE reports SET payload = %s::jsonb WHERE report_id = %s",
                    (plan["new_payload"], plan["report_id"]))
    conn.commit()                                         # type: ignore[attr-defined]


def _summary(plans: list[dict], applied: bool) -> dict:
    return {
        "reports_with_tokens": len(plans),
        "reports_changed": sum(1 for p in plans if p["changed"]),
        "reports_fully_mapped": sum(1 for p in plans if p["changed"] and not p["unresolved"]),
        "unresolved_tokens": sorted({t for p in plans for t in p["unresolved"]}),
        "applied": applied,
    }


def _connect() -> object:
    """PG 连接（口径同 `app.report.idempotency`：env 可覆盖，默认交付栈 5433）。"""
    import psycopg                                     # noqa: PLC0415
    from app.report.idempotency import POSTGRES_URL    # noqa: PLC0415
    return psycopg.connect(POSTGRES_URL, connect_timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="历史报告脱敏代号清理（ISS-062 遗留）")
    parser.add_argument("--apply", action="store_true",
                        help="落库（默认 dry-run，只打印计划）")
    parser.add_argument("--extra", action="append", default=[],
                        help="追加候选设备编号（可重复；alerts/work_orders 覆盖不到时用）")
    parser.add_argument("--json", action="store_true", help="机读 JSON 输出")
    args = parser.parse_args(argv)

    try:
        conn = _connect()
    except Exception as exc:                              # noqa: BLE001
        print(f"[error] PG 不可达：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        candidates = collect_candidates(conn, args.extra)
        reverse = build_reverse_map(candidates)
        plans = scan_reports(conn, reverse)

        if args.apply:
            for plan in plans:
                if plan["changed"]:
                    apply_plan(conn, plan)

        summary = _summary(plans, args.apply)
        if args.json:
            print(json.dumps({"summary": summary,
                              "plans": [{k: v for k, v in p.items()
                                         if k != "new_payload"} for p in plans]},
                             ensure_ascii=False, indent=2))
        else:
            print(f"候选设备编号 {len(candidates)} 个，反查表 {len(reverse)} 条")
            for plan in plans:
                tag = "APPLIED" if (args.apply and plan["changed"]) else "DRY-RUN"
                print(f"[{tag}] {plan['report_id']}: "
                      f"{', '.join(plan['mapping'].values()) or '（无可映射代号）'}"
                      + (f"；未映射: {', '.join(plan['unresolved'])}"
                         if plan["unresolved"] else ""))
            print(f"汇总：含代号报告 {summary['reports_with_tokens']} 份，"
                  f"可还原 {summary['reports_fully_mapped']} 份"
                  + ("" if args.apply else "（dry-run，未写库；--apply 生效）"))
            if summary["unresolved_tokens"]:
                print(f"[warn] 无法映射的代号（原样保留，需人工）: "
                      f"{', '.join(summary['unresolved_tokens'])}")
        return 1 if summary["unresolved_tokens"] else 0
    finally:
        conn.close()                                      # type: ignore[attr-defined]


if __name__ == "__main__":
    raise SystemExit(main())
