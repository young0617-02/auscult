"""设备编号数据层统一迁移（ISS-056 候选① · 2026-10-22）。

## 这是什么

候选②（工具层 `DEVICE_ALIAS_MAP` 垫片）让"查得到"，但数据层仍是两套口径。本脚本是候选①的
执行器：**把存量数据原地改写成规范编号**（`PUMP-A` → `PUMP-A-01`），不重灌、不丢时序数据。

覆盖三侧（`--target` 可只跑其一）：
  - `pg`：`alerts.device_id`（`work_orders.device_id` 一并尝试——源数据是图纸/台账口径，
    预期 0 行命中，脚本会如实报告"无迁移对象"而不是假装成功）；
  - `td`：TDengine 子表 **TAG**（子表名保留，见下）；
  - `neo4j`：`Entity.name`（图谱实体若以设备编号命名）。

为什么不是"清库重灌"：重灌会丢历史时序、破坏已锁定实验的可复现性，也没必要——TAG/实体名
都可原地改写。需要重灌的只有 Redis 去重键，其 TTL=5min，迁移窗口后自然过期。

## 2026-10-22 真机验证结论（TDengine 3.3.8.0 / PG / Neo4j 实跑）

  - `SET TAG device_id='PUMP-A-01'` ✅：`d_plant1_PUMP-A` 的 12919 点改后按新编号全量可查，零丢失；
  - `ALTER TABLE ... RENAME` ❌：该版本报 syntax error（新表名加反引号不被接受，子表名含连字符
    又必须加引号）→ **不做**，改为"子表名保留历史形态"；
  - 不做 RENAME 无功能影响（实测）：新写入自动建 `d_plant1_PUMP-A-01`，`WHERE device_id=...`
    按 TAG 跨两代子表合并（12919 → 12920 点、新点可见、删除后回 12919）；
  - ★ 子表名必须用 `tbname` 伪列取**实际名**：RENAME 失败后名与 TAG 不一致，若按
    `d_{group}_{device}` 模板推导，回滚会改到另一张空表，历史数据永远改不回来。
  - Neo4j `planned=0`：图谱实体是部件/现象名，不含设备编号（与语料体检结论一致）。

## 用法

    python scripts/migrate_device_ids.py                    # dry-run（默认，全部目标）
    python scripts/migrate_device_ids.py --apply            # 执行迁移
    python scripts/migrate_device_ids.py --target pg --apply
    python scripts/migrate_device_ids.py --verify           # 三侧编号分布 vs 目标口径核对
    python scripts/migrate_device_ids.py --revert --apply   # 反向回滚（canonical → legacy）

**执行顺序（runbook）**：
  1. 停机或静默写入（避免迁移中新数据落旧子表）；
  2. `--apply` 迁移三侧 → 看每目标 applied 数与 errors；
  3. 设 `AUSCULT_DEVICE_ID_SCHEME=canonical` 并重启 API（查询端切到规范编号）；
  4. `--verify` 应全绿；回归 `pytest tests -q`；
  5. 灌数脚本默认值已是规范编号，后续新数据天然同口径。

## 风险与护栏

- **默认 dry-run**，`--apply` 才写；`--revert` 反向可回滚。
- 每条语句独立 try/except，**单个子表/实体失败不阻断其余**，最后汇总（避免"改一半就断"）。
- 所有编号只允许来自 `app.device_ids` 的受控集合 + 库内实际分布（不做自由字符串拼接）。

退出码：0 = 全部目标可达且无错误；1 = 有错误/部分失败；2 = 全部目标不可达（离线环境即此态）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.device_ids import (                            # noqa: E402
    CANONICAL_TO_LEGACY, canonical_ids, device_id_scheme, legacy_ids,
)

#: 允许迁移的编号集合（受控，防注入）
_ALLOWED = set(canonical_ids()) | set(legacy_ids())

#: 允许改写的 PG 表（白名单，表名拼接用）
_PG_TABLES = ("alerts", "work_orders")

#: TDengine 子表名/标识符白名单（同 self_decoder 口径）
_SAFE_IDENT_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

TARGETS = ("pg", "td", "neo4j")


def _pairs(revert: bool = False) -> list[tuple[str, str]]:
    """(源编号, 目标编号) 列表；`revert` 时反向。"""
    base = [(legacy, canon) for canon, legacy in CANONICAL_TO_LEGACY.items()]
    return [(b, a) for a, b in base] if revert else base


def _check_ids(*ids: str) -> None:
    for value in ids:
        if value not in _ALLOWED:
            raise ValueError(f"拒绝迁移非受控编号：{value!r}")


# ---------------------------------------------------------------- PG

def migrate_pg(conn: object, pairs: list[tuple[str, str]], apply: bool) -> dict:
    """改写 `alerts` / `work_orders` 的 device_id（原地 UPDATE，不删行）。"""
    out: dict[str, Any] = {"target": "pg", "reachable": True, "planned": 0,
                           "applied": 0, "errors": [], "detail": []}
    for table in _PG_TABLES:
        for old, new in pairs:
            _check_ids(old, new)
            try:
                with conn.cursor() as cur:                 # type: ignore[attr-defined]
                    cur.execute(f"SELECT count(*) FROM {table} WHERE device_id = %s", (old,))
                    n = int(cur.fetchone()[0])
                    out["planned"] += n
                    out["detail"].append(f"{table}: {old} → {new} ({n} 行)")
                    if apply and n:
                        cur.execute(f"UPDATE {table} SET device_id = %s WHERE device_id = %s",
                                    (new, old))
                        out["applied"] += n
            except Exception as exc:                       # noqa: BLE001 - 单表失败不阻断
                out["errors"].append(f"{table} {old}: {type(exc).__name__}: {exc}")
    if apply and out["applied"]:
        conn.commit()                                      # type: ignore[attr-defined]
    return out


# ---------------------------------------------------------------- TDengine

def _td_connect(host: str, port: int, user: str, password: str):
    import taosrest                                      # noqa: PLC0415
    return taosrest.connect(url=f"http://{host}:{port}", user=user,
                            password=password, timeout=8)


def migrate_td(conn: object, pairs: list[tuple[str, str]], apply: bool) -> dict:
    """只改子表 TAG（以 `tbname` 为准，**不做 RENAME**）。

    真机结论见模块头注：`SET TAG` 有效且数据零丢失；`RENAME` 在 3.3.8.0 语法不通，且
    不做也完全可接受（新写入自动建规范名子表，查询按 TAG 跨代合并）。子表名必须用
    `tbname` 伪列取实际名，不能按模板推导——否则回滚会改到另一张空表。
    """
    out: dict[str, Any] = {"target": "td", "reachable": True, "planned": 0,
                           "applied": 0, "errors": [], "warnings": [], "detail": []}
    mapping = dict(pairs)
    try:
        rows = conn.query("SELECT DISTINCT tbname, device_id "      # type: ignore[attr-defined]
                          "FROM iot.st_pump_metrics").data
    except Exception as exc:                               # noqa: BLE001
        out["reachable"] = False
        out["errors"].append(f"查询子表分布失败：{type(exc).__name__}: {exc}")
        return out

    for tbname, dev in rows:
        old = str(dev)
        if old not in mapping:
            continue
        new = mapping[old]
        _check_ids(old, new)
        if not _SAFE_IDENT_RE.match(str(tbname)):
            out["errors"].append(f"非法子表名，跳过：{tbname!r}")
            continue
        sql = f"ALTER TABLE `iot`.`{tbname}` SET TAG device_id='{new}'"
        out["planned"] += 1
        out["detail"].append(sql)
        if not apply:
            continue
        try:
            conn.execute(sql)                              # type: ignore[attr-defined]
            out["applied"] += 1
        except Exception as exc:                           # noqa: BLE001 - 逐表容错
            out["errors"].append(f"{sql} → {type(exc).__name__}: {exc}")
    return out


# ---------------------------------------------------------------- Neo4j

def migrate_neo4j(pairs: list[tuple[str, str]], apply: bool) -> dict:
    """改图谱实体名（`Entity.name`）；无该编号实体则 0 行（如实报告）。"""
    out: dict[str, Any] = {"target": "neo4j", "reachable": True, "planned": 0,
                           "applied": 0, "errors": [], "detail": []}
    from scripts.retrieval_base import neo4j_run     # noqa: PLC0415
    for old, new in pairs:
        _check_ids(old, new)
        try:
            res = neo4j_run([f"MATCH (e {{name:'{old}'}}) RETURN count(e) AS c"])
            n = int((res[0]["data"][0]["row"][0]) if res and res[0].get("data") else 0)
            out["planned"] += n
            out["detail"].append(f"Entity.name: {old} → {new} ({n} 个)")
            if apply and n:
                neo4j_run([f"MATCH (e {{name:'{old}'}}) "
                           f"SET e.name='{new}' RETURN count(e) AS c"])
                out["applied"] += n
        except Exception as exc:                           # noqa: BLE001 - 单实体失败不阻断
            out["reachable"] = False
            out["errors"].append(f"{old}: {type(exc).__name__}: {exc}")
    return out


# ---------------------------------------------------------------- 校验

def verify() -> dict:
    """三侧编号分布 vs 目标口径（迁移完成后应全部 ∈ canonical）。"""
    scheme = device_id_scheme()
    expected = set(canonical_ids()) if scheme == "canonical" else set(legacy_ids())
    result: dict[str, Any] = {"scheme": scheme, "sides": {}, "off_scheme": {}}

    try:
        import psycopg                                     # noqa: PLC0415
        from app.report.idempotency import POSTGRES_URL     # noqa: PLC0415
        with psycopg.connect(POSTGRES_URL, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT device_id, count(*) FROM alerts GROUP BY 1")
                dist = {str(d): int(n) for d, n in cur.fetchall()}
        result["sides"]["pg"] = dist
        result["off_scheme"]["pg"] = sorted(set(dist) - expected)
    except Exception as exc:                               # noqa: BLE001
        result["sides"]["pg"] = f"unreachable: {type(exc).__name__}"

    try:
        conn = _td_connect("127.0.0.1", 6041, "root", "taosdata")
        rows = conn.query("SELECT device_id, count(*) FROM iot.st_pump_metrics "
                          "GROUP BY device_id").data
        dist = {str(d): int(n) for d, n in rows}
        result["sides"]["td"] = dist
        result["off_scheme"]["td"] = sorted(set(dist) - expected)
    except Exception as exc:                               # noqa: BLE001
        result["sides"]["td"] = f"unreachable: {type(exc).__name__}"

    try:
        from scripts.retrieval_base import neo4j_run       # noqa: PLC0415
        names = ", ".join(f"'{n}'" for n in sorted(_ALLOWED))
        res = neo4j_run([f"MATCH (e) WHERE e.name IN [{names}] "
                         f"RETURN e.name AS n, count(e) AS c"])
        rows = res[0]["data"] if res and res[0].get("data") else []
        dist = {str(r["row"][0]): int(r["row"][1]) for r in rows}
        result["sides"]["neo4j"] = dist
        result["off_scheme"]["neo4j"] = []                 # 查询本身已按受控集合过滤
    except Exception as exc:                               # noqa: BLE001
        result["sides"]["neo4j"] = f"unreachable: {type(exc).__name__}"

    # 三侧必须都可达：不可达不等于"没有偏离"，不能给绿灯
    sides_reached = sum(1 for v in result["sides"].values()
                        if not str(v).startswith("unreachable"))
    result["sides_reached"] = sides_reached
    result["ok"] = (sides_reached == 3
                    and not any(result["off_scheme"].values()))
    return result


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="设备编号数据层统一迁移（ISS-056 候选①）")
    parser.add_argument("--apply", action="store_true", help="执行（默认 dry-run）")
    parser.add_argument("--target", action="append", choices=TARGETS, default=[],
                        help="只跑指定目标（可重复；默认全部）")
    parser.add_argument("--revert", action="store_true", help="反向迁移（canonical → legacy）")
    parser.add_argument("--verify", action="store_true", help="只做三侧口径核对")
    parser.add_argument("--json", action="store_true", help="机读输出")
    args = parser.parse_args(argv)

    if args.verify:
        result = verify()
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json
              else f"口径={result['scheme']} ok={result['ok']}\n"
                   + "\n".join(f"  {k}: {v}" for k, v in result["sides"].items())
                   + (f"\n  偏离目标口径：{result['off_scheme']}"
                      if any(result["off_scheme"].values()) else ""))
        return 0 if result["ok"] else 1

    pairs = _pairs(revert=args.revert)
    targets = args.target or list(TARGETS)
    reports: list[dict] = []
    reachable_any = False

    if "pg" in targets:
        try:
            import psycopg                                 # noqa: PLC0415
            from app.report.idempotency import POSTGRES_URL  # noqa: PLC0415
            conn = psycopg.connect(POSTGRES_URL, connect_timeout=5)
            try:
                reports.append(migrate_pg(conn, pairs, args.apply))
                reachable_any = True
            finally:
                conn.close()
        except Exception as exc:                           # noqa: BLE001
            reports.append({"target": "pg", "reachable": False, "planned": 0,
                            "applied": 0, "errors": [f"{type(exc).__name__}: {exc}"],
                            "detail": []})

    if "td" in targets:
        try:
            conn = _td_connect("127.0.0.1", 6041, "root", "taosdata")
            reports.append(migrate_td(conn, pairs, args.apply))
            reachable_any = reachable_any or reports[-1]["reachable"]
        except Exception as exc:                           # noqa: BLE001
            reports.append({"target": "td", "reachable": False, "planned": 0,
                            "applied": 0, "errors": [f"{type(exc).__name__}: {exc}"],
                            "detail": []})

    if "neo4j" in targets:
        reports.append(migrate_neo4j(pairs, args.apply))
        reachable_any = reachable_any or reports[-1]["reachable"]

    if args.json:
        print(json.dumps({"apply": args.apply, "revert": args.revert,
                          "reports": reports}, ensure_ascii=False, indent=2))
    else:
        for rep in reports:
            state = "APPLY" if args.apply else "DRY-RUN"
            print(f"[{state}] {rep['target']}: planned={rep['planned']} "
                  f"applied={rep['applied']} reachable={rep['reachable']}")
            for line in rep["detail"][:20]:
                print(f"    {line}")
            if len(rep["detail"]) > 20:
                print(f"    … 另有 {len(rep['detail']) - 20} 条")
            for err in rep["errors"]:
                print(f"    [error] {err}")
            for warn in rep.get("warnings") or []:
                print(f"    [warn] {warn}")
        print("提示：迁移完成后设 AUSCULT_DEVICE_ID_SCHEME=canonical 并重启 API，"
              "再跑 --verify 与全量回归。")

    has_error = any(rep["errors"] for rep in reports)
    if not reachable_any:
        return 2
    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
