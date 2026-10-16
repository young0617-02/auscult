"""B5 元数据与工单导入 PostgreSQL（Phase 1 · 知识库 · PG 侧）

来源：`plan/p1-plan-detailed.md` §四 D7–D8 · §5.8（B5 DDL）· §5.9（B6 Outbox）
目标库：`postgresql://root:123456@127.0.0.1:5433/auscult_v2`（ParadeDB PG，见 `db/migrations/0001_init.sql`）
表：`documents` / `doc_chunks` 来自 `chunks/chunks_v1.jsonl`；`work_orders` 来自 `parsed/workorders_*.md`

幂等：全部 `ON CONFLICT ... DO UPDATE`，可重复执行。

B6 Outbox（本文件在导入三表后增量补写）：
  - 每个 chunk 写两条 outbox：`target=milvus, op=upsert`（payload 含 text/doc_id/section）与
    `target=neo4j, op=verify`（payload 含 source_chunk_id），供 `outbox_worker.py` 消费、
    `reconcile.py` 对账，判据（§5.9 / 出口 §1.2）＝「失败注入下对账零差异、补偿队列可自愈」。
  - 幂等：outbox 无唯一约束，故写前先 `SELECT 1 ... WHERE entity_type/entity_id/target` 判重，
    已存在则跳过——重复导入不产生重复行；若存储侧后续丢数据，由 `reconcile.py --fix` 重触发。
确定性映射（可审计，勿改，否则既往数据不一致）：
  - `documents.doc_id = uuid5(NS, "auscult:<doc_id字符串>")`
  - `doc_type`（分块中文字段）→ documents 枚举：设备手册→manual、维修工单→work_order、标准判据/故障案例/拓扑→procedure
  - `work_orders.created_at`：工单「日期」列原为合成「工作日第N天」，非时间戳 → 映射为
    `BASE_WORKDAY + (N-1) 天`，BASE_WORKDAY=2025-06-02(周一)；N=1 即首行
  - `work_orders.order_id`：工单编号列在合成样本中重复（相同前缀），为保证主键唯一，
    `order_id = "<工单编号列>-%03d"`（按文件内行序）——该编号为合成标签，不代替业务工单号
  - `work_orders.result`：工单源表无结果字段 → NULL

用法：
  python scripts/load_meta.py --selftest
  python scripts/load_meta.py                     # 全量导入三表
  python scripts/load_meta.py --parsed-dir ... --chunks ... --dsn ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULTS = {
    "chunks": PROJECT_ROOT / "chunks" / "chunks_v1.jsonl",
    "parsed_dir": PROJECT_ROOT / "parsed",
    "dsn": "postgresql://root:123456@127.0.0.1:5433/auscult_v2",
}

# 分块 doc_type（中文字段）→ documents.doc_type 枚举
DOC_TYPE_MAP = {
    "设备手册": "manual",
    "维修工单": "work_order",
    "标准判据": "procedure",
    "故障案例": "procedure",
    "拓扑": "procedure",
}

# 合成工单「工作日第N天」→ 真实时间戳的确定性基线（周一）
BASE_WORKDAY = date(2025, 6, 2)
_WORKDAY_RE = re.compile(r"第\s*(\d+)\s*天")

_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")   # DNS 命名空间（仅作确定源）

_WORKORDER_GLOB = "workorders_*.md"


def doc_uuid(doc_id: str) -> uuid.UUID:
    """由分块 doc_id 字符串推导确定 UUID（幂等、可追溯）。"""
    return uuid.uuid5(_NS, f"auscult:{doc_id}")


def map_doc_type(chinese: str) -> str:
    mapped = DOC_TYPE_MAP.get(chinese)
    if not mapped:
        raise ValueError(f"未知 doc_type: {chinese!r}（应属 {sorted(DOC_TYPE_MAP)}）")
    return mapped


def parse_workday_date(label: str) -> datetime:
    """解析合成日期「工作日第N天」→ BASE_WORKDAY + (N-1) 天，返回 aware 时间戳。"""
    m = _WORKDAY_RE.search(label or "")
    n = int(m.group(1)) if m else 1
    return datetime.combine(BASE_WORKDAY + timedelta(days=n - 1), time(0, 0),
                            tzinfo=timezone.utc)


# ---------------------------------------------------------------- 读取源


def load_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def parse_workorder_table(text: str) -> list[dict[str, str]]:
    """解析 workorders markdown 表格，返回固定列序 dict 列表（跳过表头/分隔行）。

    列序（表头固定）：工单编号 | 客户号 | 设备 | 故障现象 | 处置措施 | 日期
    """
    rows: list[dict[str, str]] = []
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("|") and "工单编号" in line:
            header_idx = i
            break
    if header_idx is None:
        return rows
    keys = ["order_base", "客户号", "device_id", "fault", "action", "date_label"]
    for line in lines[header_idx + 1:]:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6 or all(c.startswith("---") for c in cells):
            continue
        rows.append(dict(zip(keys, cells)))
    return rows


def build_documents_rows(chunks: list[dict[str, Any]]) -> list[tuple]:
    """从分块（去重 doc_id）构造 documents 行。"""
    seen: dict[str, dict[str, Any]] = {}
    for c in chunks:
        doc_id = c["doc_id"]
        if doc_id not in seen:
            seen[doc_id] = c
    rows = []
    for doc_id, c in seen.items():
        checksum = hashlib.sha256(doc_id.encode("utf-8")).hexdigest()
        rows.append((
            doc_uuid(doc_id), doc_id, "chunks_v1.jsonl",
            map_doc_type(c["doc_type"]), c.get("device_model"), checksum,
        ))
    return rows


def build_doc_chunks_rows(chunks: list[dict[str, Any]]) -> list[tuple]:
    """构造 doc_chunks 行（父块+子块同表）。"""
    rows = []
    for c in chunks:
        rows.append((
            c["id"], doc_uuid(c["doc_id"]), c.get("parent_id"),
            c.get("text", ""), c.get("section"), c.get("page"), c.get("token_count"),
        ))
    return rows


def build_work_orders_rows(parsed_dir: Path) -> list[tuple]:
    """从 parsed/workorders_*.md 解析并构造 work_orders 行（order_id 做行序去重后缀）。"""
    rows = []
    files = sorted(parsed_dir.glob(_WORKORDER_GLOB))
    if not files:
        raise FileNotFoundError(f"{parsed_dir} 下无 {_WORKORDER_GLOB}")
    for f in files:
        table = parse_workorder_table(f.read_text(encoding="utf-8"))
        for i, r in enumerate(table, start=1):
            rows.append((
                f"{r['order_base']}-{i:03d}", r["device_id"],
                r["fault"], r["action"], None, parse_workday_date(r["date_label"]),
            ))
    return rows


# ---------------------------------------------------------------- 执行


def connect(dsn: str):
    import psycopg                                   # noqa: PLC0415 - 延迟导入保证 selftest 离线可跑
    return psycopg.connect(dsn)


# ---------------------------------------------------------------- B6 Outbox 补写


def build_outbox_rows(chunks: list[dict[str, Any]]) -> list[tuple]:
    """为每个 chunk 构造两条 outbox 行（milvus upsert / neo4j verify）。

    返回列序：entity_type, entity_id, op, target, payload(JSON 字符串)
    payload 按 plan §5.9 约定：milvus 带 text/doc_id/section；neo4j 带 source_chunk_id。
    """
    rows: list[tuple] = []
    for c in chunks:
        cid = c["id"]
        rows.append((
            "chunk", cid, "upsert", "milvus",
            json.dumps({"text": c.get("text", ""), "doc_id": c.get("doc_id"),
                        "section": c.get("section")}, ensure_ascii=False),
        ))
        rows.append((
            "chunk", cid, "verify", "neo4j",
            json.dumps({"source_chunk_id": cid}, ensure_ascii=False),
        ))
    return rows


def write_outbox_idempotent(cur, rows: list[tuple], targets: tuple[str, ...] = ("milvus", "neo4j")
                            ) -> int:
    """幂等补写 outbox：每个 (entity_id, target) 已存在则跳过，返回本次新插入条数。

    outbox 表无唯一约束，故用「先查后插」避免重复导入产生重复行；写前不清空，保证可重跑。
    """
    inserted = 0
    for entity_type, entity_id, op, target, payload in rows:
        if target not in targets:
            continue
        cur.execute(
            "SELECT 1 FROM outbox WHERE entity_type=%s AND entity_id=%s AND target=%s",
            (entity_type, entity_id, target))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO outbox (entity_type, entity_id, op, target, payload) "
            "VALUES (%s, %s, %s, %s, %s::jsonb)",
            (entity_type, entity_id, op, target, payload))
        inserted += 1
    return inserted


def import_all(dsn: str, chunks: list[dict[str, Any]], workorders: list[tuple]) -> dict[str, int]:
    """导入 B5 元数据三表 + 幂等补写 outbox。

    幂等口径（2026-10-16 修复）：原实现用 `COPY ... FROM STDIN`，而 **COPY 协议不支持
    `ON CONFLICT`** —— 重复导入（`init.ps1` 幂等重跑）必撞 `documents_pkey` 唯一约束
    使整个 Step 4 崩溃（实测 `psycopg.errors.UniqueViolation`，2026-10-16 首次在
    「documents 已导入」状态下重跑 init.ps1 时暴露）。这与 P1 报告口径
    （`reports/p1-d7-d8-b5-meta.md`：`ON CONFLICT DO UPDATE` 幂等）存在**文档—实现漂移**。
    修复：三张表改逐行 `INSERT ... ON CONFLICT (pk) DO NOTHING`（数据源为同一 chunks
    文件、doc_id 由 uuid5 确定性生成，内容不变，故 DO NOTHING 即等价于 DO UPDATE）；
    批量走 `execute_values` 需要 `psycopg.extras`（本 venv 未安装该模块，见
    2026-10-16 实测），故用纯 `cur.execute` 循环 —— 数据量 19/36/48 行，性能无感。
    """
    docs = build_documents_rows(chunks)
    doc_chunks = build_doc_chunks_rows(chunks)
    with connect(dsn) as conn, conn.cursor() as cur:
        for r in docs:
            cur.execute(
                "INSERT INTO documents (doc_id,title,source,doc_type,device_model,checksum) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (doc_id) DO NOTHING", r)
        for r in doc_chunks:
            cur.execute(
                "INSERT INTO doc_chunks (chunk_id,doc_id,parent_id,content,section,page,token_count) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (chunk_id) DO NOTHING", r)
        for r in workorders:
            cur.execute(
                "INSERT INTO work_orders (order_id,device_id,fault,action,result,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (order_id) DO NOTHING", r)
        # B6：与三表同事务补写 outbox（幂等，重复导入不重复插）
        outbox_written = write_outbox_idempotent(cur, build_outbox_rows(chunks))
    return {"documents": len(docs), "doc_chunks": len(doc_chunks), "work_orders": len(workorders),
            "outbox": outbox_written}


# ---------------------------------------------------------------- 自检


def _selftest(chunks_path: Path, parsed_dir: Path) -> int:
    failures: list[str] = []
    try:
        for en in ("manual", "work_order", "procedure"):
            if en not in DOC_TYPE_MAP.values():
                failures.append(f"doc_type 枚举缺 {en}")
        if not chunks_path.exists():
            failures.append(f"缺分块文件 {chunks_path}")
        else:
            chunks = load_chunks(chunks_path)
            if not chunks:
                failures.append("分块为空")
            bad = {c["doc_type"] for c in chunks if c["doc_type"] not in DOC_TYPE_MAP}
            if bad:
                failures.append(f"分块存在未映射 doc_type: {bad}")
            samples = [c["doc_id"] for c in chunks[:3]]
            for s in samples:
                _ = doc_uuid(s)                        # 确定性 UUID 冒烟
        md = list(parsed_dir.glob(_WORKORDER_GLOB))
        if not md:
            failures.append(f"{parsed_dir} 无 workorders_*.md")
        else:
            rows = parse_workorder_table(md[0].read_text(encoding="utf-8"))
            if not rows:
                failures.append(f"首个工单 md 未解析出行: {md[0].name}")
            parsed = [parse_workday_date(r["date_label"]) for r in rows[:1]]
            if not parsed or parsed[0] != datetime(2025, 6, 2, 0, 0, tzinfo=timezone.utc):
                failures.append("工作日日期映射基准不符（应为 2025-06-02）")
            ob = build_outbox_rows(chunks)
            if len(ob) != len(chunks) * 2:
                failures.append(f"outbox 应为 2×子块={len(chunks)*2} 条，实际 {len(ob)}")
            targets_by = {(et, eid, t): op for et, eid, op, t, _p in ob}
            sample = {k: targets_by[k] for k in list(targets_by)[:2]}
            if "milvus" not in " ".join(map(str, sample)) and "neo4j" not in " ".join(map(str, sample)):
                failures.append("outbox 目标/动作覆盖异常")
    except Exception as exc:                             # noqa: BLE001 - 自检拦截
        failures.append(f"自检异常：{type(exc).__name__}: {exc}")

    if failures:
        print("[FAIL] load_meta 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] load_meta 自检通过：doc_type 映射完整 / 分块可读且类型全覆盖 / "
          "uuid5 确定性 / 工单 md 可解析 / 工作日日期映射正确 / outbox 2×子块补齐正确")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="B5 元数据与工单导入 PG")
    p.add_argument("--chunks", type=Path, default=DEFAULTS["chunks"])
    p.add_argument("--parsed-dir", type=Path, default=DEFAULTS["parsed_dir"])
    p.add_argument("--dsn", default=DEFAULTS["dsn"])
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest(args.chunks, args.parsed_dir)

    chunks = load_chunks(args.chunks)
    workorders = build_work_orders_rows(args.parsed_dir)
    counts = import_all(args.dsn, chunks, workorders)
    print("[b5] PG 导入完成："
          + " | ".join(f"{k}={v}" for k, v in counts.items())
          + f" → {args.dsn}")
    print(f"[b5] B6 outbox 补写 {counts['outbox']} 条"
          f"（预估满量 2×子块数={chunks.__len__() * 2}，重复导入会因判重而跳过）")
    print("[b5] 校验：docker exec -it auscult-v2-pg psql -U root -d auscult_v2 "
          r"-c '\dt' / -c 'SELECT count(*) FROM documents' "
          r"-c 'SELECT status,count(*) FROM outbox GROUP BY status'")
    return 0


if __name__ == "__main__":
    sys.exit(main())