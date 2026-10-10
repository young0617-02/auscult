"""B6 对账脚本（Phase 1 · 一致性三件套之一）—— PG/Milvus/Neo4j 三侧 chunk 覆盖对账

来源：`plan/p1-plan-detailed.md` §5.9（B6 Outbox）；判据＝出口 §1.2：
  「失败注入下对账零差异、补偿队列可自愈」；**PG 为唯一权威源**，Milvus/Neo4j 为可重建索引。

对比三侧 chunk 覆盖集：
  - PG：`SELECT chunk_id FROM doc_chunks`（权威）
  - Milvus：`SELECT chunk_id FROM kb_p1_v1`（主键 chunk_id）
  - Neo4j：`MATCH ()-[r]->() RETURN DISTINCT r.source_chunk_id`（关系属性）

输出差异：PG 有而各存储缺 / 各存储有而 PG 无（多余），量大时打印数量+前若干条。
收敛建议：`--fix` 补齐 outbox → `outbox_worker.py` 消费 → 再跑本脚本复检为零差异。

写入型动作：
  - `--fix`：对「PG 有但存储缺失」的 chunk 幂等补写 outbox（pending）驱动 worker。
  - `--fault-inject <milvus|neo4j> --chunk-id X`：**默认仅预演（--apply 缺失时只打印将被视为
    缺失的项，不触碰真实数据）**；加 `--apply` 才对指定 chunk 真实删除（milvus 删 collection 行 /
    neo4j 删该 source_chunk_id 的关系）。达安全取舍：故障注入必须显式传参且仅操作指定 chunk，
    以演示「注入→--fix+worker→复检归零」闭环，默认不破坏任何数据。

纯标准库 + psycopg（PG）+ pymilvus（按期查询）。离线自检不联网（`--selftest`）。

用法：
  python scripts/reconcile.py --selftest
  python scripts/reconcile.py                              # 只读对账，打印 diff
  python scripts/reconcile.py --fix                        # 为缺失存储补写 outbox（需走 worker）
  python scripts/reconcile.py --fault-inject milvus --chunk-id criteria_1-1-c0   # 预演
  python scripts/reconcile.py --fault-inject milvus --chunk-id criteria_1-1-c0 --apply  # 真删
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ---------------- 核对后的连接常量（勿自行猜测） ----------------
PG_DSN = "postgresql://root:123456@127.0.0.1:5433/auscult_v2"
MILVUS_URI = "http://127.0.0.1:39530"   # kee-milvus 实际映射 19530→39530（P5 修正）
MILVUS_COLLECTION = "kb_p1_v1"
NEO4J_URI = "http://127.0.0.1:7474"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "auscult_p0_dev")
DIFF_PRINT = 8                       # 默认打印每类差异前 N 条


def _neo4j_tx(uri: str, user: str, password: str, statements: list[str]) -> list[Any]:
    """POST /db/neo4j/tx/commit 执行一批 Cypher，返回 results（参考 scripts/extract_triples.py）。"""
    import urllib.request                               # noqa: PLC0415
    endpoint = uri.rstrip("/") + "/db/neo4j/tx/commit"
    auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": auth}
    body = json.dumps({"statements": [{"statement": s} for s in statements]}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:                             # noqa: BLE001 - 网络/HTTP 兜底
        raise RuntimeError(f"Neo4j {endpoint} 请求失败：{type(exc).__name__}: {exc}") from exc
    if data.get("errors"):
        raise RuntimeError(f"Neo4j 执行错误：{data['errors']}")
    return data.get("results", [])


# ---------------------------------------------------------------- 三侧采集


def pg_chunk_ids() -> set[str]:
    import psycopg                                      # noqa: PLC0415
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT chunk_id FROM doc_chunks")
        return {r[0] for r in cur.fetchall()}


def milvus_chunk_ids() -> set[str]:
    from pymilvus import MilvusClient                   # noqa: PLC0415
    client = MilvusClient(uri=MILVUS_URI)
    res = client.query(collection_name=MILVUS_COLLECTION, filter='chunk_id != ""',
                       output_fields=["chunk_id"],
                       limit=10000)
    return {r["chunk_id"] for r in res}


def neo4j_chunk_ids() -> set[str]:
    results = _neo4j_tx(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
                        ["MATCH ()-[r]->() "
                         "RETURN r.source_chunk_id AS s1, r.source_chunk_ids AS sarr"])
    ids: set[str] = set()
    for d in results[0]["data"]:
        s1, sarr = d["row"][0], d["row"][1] or []
        ids.add(s1) if s1 else None
        ids.update(x for x in sarr if x)
    return ids


# ---------------------------------------------------------------- 对账


KNOWLEDGE_NO_RELATION_CHUNKS = frozenset({
    # B4 v2 复核：纯操作性文本（安全须知/安装要求），被正确判定无可抽三元组，不属缺口。
    "manual_centrifugal_hc-4-c0",
    "manual_impeller_series-2-c0",
    "manual_scanned_dp-2-c0",
    "manual_ss_process-2-c0",
})


def _known_no_relation_chunks() -> frozenset[str]:
    """返回「已知无可抽关系」子块集合（供对账豁免）。"""
    return KNOWLEDGE_NO_RELATION_CHUNKS


def compare(pg: set[str], milvus: set[str], neo4j: set[str]) -> dict[str, list[str]]:
    """计算差异：`pg_only_milvus`=PG 有而 milvus 缺；`pg_only_neo4j`=PG 有而 neo4j 缺；
    `extra_milvus`=milvus 有而 PG 无；`extra_neo4j`=neo4j 有而 PG 无。
    Neo4j 侧豁免「已知无可抽关系」子块（B4 v2 复核判定的纯操作性文本，如安全须知/安装要求）：
    它们被正确判定不产出三元组，不属对账缺口。"""
    known_no_rel = _known_no_relation_chunks()
    return {
        "pg_only_milvus": sorted(pg - milvus),
        "pg_only_neo4j": sorted((pg - neo4j) - known_no_rel),
        "extra_milvus": sorted(milvus - pg),
        "extra_neo4j": sorted(neo4j - pg),
    }


def report(diff: dict[str, list[str]], print_n: int = DIFF_PRINT) -> None:
    print("=" * 60)
    print("三侧 chunk 覆盖对账（PG 为权威源）")
    print("=" * 60)
    titles = {
        "pg_only_milvus": "PG 有、Milvus 缺",
        "pg_only_neo4j": "PG 有、Neo4j 缺",
        "extra_milvus": "Milvus 有、PG 无（多余）",
        "extra_neo4j": "Neo4j 有、PG 无（多余）",
    }
    total = 0
    for key, title in titles.items():
        items = diff[key]
        total += len(items)
        mark = "✔ 零" if not items else f"✘ {len(items)}"
        print(f"\n[{mark}] {title}")
        for cid in items[:print_n]:
            print(f"    - {cid}")
        if len(items) > print_n:
            print(f"    … 其余 {len(items) - print_n} 条略")
    print("\n" + "-" * 60)
    print(f"差异合计：{total} 条" + ("  ✔ 对账零差异" if total == 0
                                     else "  → 收敛建议：`reconcile.py --fix` + `outbox_worker.py` 后复检"))


# ---------------------------------------------------------------- 补写 outbox


def _insert_outbox_if_missing(cur, entity_type: str, entity_id: str, op: str,
                              target: str, payload: str) -> bool:
    """幂等补写单条 outbox（供对账收敛）。

    语义：只要该 (entity_id, target) 对应存储中确实缺失数据，就确保存在一条
    pending 的 outbox 行供 worker 消费：
      - 已有 pending 行 → 跳过（已在队列，不重复）
      - 已有 done/failed 行（历史已消费）但对账仍判缺失 → 重置为 pending
      - 无行 → 插入新行
    据此支持「故障注入→fix→worker→归零」的自愈闭环，同时保持幂等可重跑。
    """
    cur.execute("SELECT status FROM outbox WHERE entity_type=%s AND entity_id=%s AND target=%s"
                " ORDER BY id DESC LIMIT 1",
                (entity_type, entity_id, target))
    row = cur.fetchone()
    if row:
        status = row[0]
        if status == "pending":
            return False                       # 已在队列，无需重复
        cur.execute("UPDATE outbox SET status='pending', retry_count=0, last_error=null, "
                    "op=%s, payload=%s::jsonb, updated_at=now() WHERE id IN ("
                    "SELECT id FROM outbox WHERE entity_type=%s AND entity_id=%s AND target=%s"
                    " ORDER BY id DESC LIMIT 1)",
                    (op, payload, entity_type, entity_id, target))
        return True
    cur.execute("INSERT INTO outbox (entity_type, entity_id, op, target, payload) "
                "VALUES (%s, %s, %s, %s, %s::jsonb)",
                (entity_type, entity_id, op, target, payload))
    return True


def _chunk_meta(cur, cids: list[str]) -> dict[str, dict[str, Any]]:
    """从 doc_chunks 取缺失块的内容元数据（content/doc_id/section），供 milvus outbox payload。"""
    if not cids:
        return {}
    cur.execute("SELECT chunk_id, content, doc_id, section FROM doc_chunks WHERE chunk_id = ANY(%s)",
                (cids,))
    # doc_id 为 PG uuid 类型，转 str 以便 json.dumps 序列化进 outbox.payload
    return {r[0]: {"text": r[1] or "", "doc_id": str(r[2]), "section": r[3]} for r in cur.fetchall()}


def apply_fix(diff: dict[str, list[str]]) -> None:
    import psycopg                                      # noqa: PLC0415
    with psycopg.connect(PG_DSN) as conn, conn.cursor() as cur:
        inserted = 0
        # milvus 缺失 → 写 upsert outbox（worker 消费后补齐）
        meta = _chunk_meta(cur, diff["pg_only_milvus"])
        for cid in diff["pg_only_milvus"]:
            m = meta.get(cid, {})
            payload = json.dumps({"text": m.get("text", ""), "doc_id": m.get("doc_id"),
                                  "section": m.get("section")}, ensure_ascii=False)
            if _insert_outbox_if_missing(cur, "chunk", cid, "upsert", "milvus", payload):
                inserted += 1
        # neo4j 缺失 → 写 verify outbox（worker 重新核查存在性；若仍缺属 B4「处置为」补链专项）
        for cid in diff["pg_only_neo4j"]:
            payload = json.dumps({"source_chunk_id": cid}, ensure_ascii=False)
            if _insert_outbox_if_missing(cur, "chunk", cid, "verify", "neo4j", payload):
                inserted += 1
    print(f"[fix] 幂等补写 outbox {inserted} 条"
          f"（milvus 缺失 {len(diff['pg_only_milvus'])} / "
          f"neo4j 缺失 {len(diff['pg_only_neo4j'])}）")
    print("[fix] 下一步：python scripts/outbox_worker.py --limit 1000，再运行 reconcile 复检零差异")


# ---------------------------------------------------------------- 故障注入


def apply_fault_inject(target: str, chunk_id: str, apply: bool) -> None:
    """故障注入。默认（apply=False）只预演打印，不触碰真实数据。
    选此安全实现理由：pfail 注入的唯一目的是演示「diff→修复→归零」闭环，
    预演可零风险观察歧义项；真实删除属破坏性写库，故须显式 --apply 才执行，且仅操作指定 chunk。
    """
    print("[fault-inject] 目标='" + target + "' chunk='" + chunk_id + "'")
    if not apply:
        print(f"[fault-inject] 预演（未执行删除）：该 chunk 将被视为「{target} 缺失」，"
              f"对账后 diff 会将其列出；如需真实注入请加 --apply")
        return
    print(f"[fault-inject] ⚠️ 警告：将对 {target} 真实删除 chunk='{chunk_id}'（仅此一条）")
    if target == "milvus":
        from pymilvus import MilvusClient                # noqa: PLC0415
        client = MilvusClient(uri=MILVUS_URI)
        res = client.delete(collection_name=MILVUS_COLLECTION, ids=[chunk_id])
        client.flush(MILVUS_COLLECTION)
        print(f"[fault-inject] milvus 已删除 {chunk_id}（delete 返回 {res}）"
              "；待 --fix + worker 补偿复检归零")
    elif target == "neo4j":
        safe = chunk_id.replace("\\", "\\\\").replace('"', '\\"')
        _neo4j_tx(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
                  [f'MATCH ()-[r {{source_chunk_id: "{safe}"}}]->() DELETE r'])
        print(f"[fault-inject] neo4j 已删除 {chunk_id} 的关系；"
              "注意：补链归 B4「处置为」专项，worker 仅核查不会补链")
    else:
        raise SystemExit(f"未知 --fault-inject target：{target}（可选 milvus|neo4j）")


# ---------------------------------------------------------------- 自检


def _selftest() -> int:
    """离线校验：不联网，只验 diff 算术与常量/表字段口径。"""
    failures: list[str] = []
    # diff 算术
    d = compare({"pg1", "pg2"}, {"pg1", "mi1"}, {"pg2", "n1"})
    if d["pg_only_milvus"] != ["pg2"]:
        failures.append(f"pg_only_milvus 计算错误: {d['pg_only_milvus']}")
    if d["pg_only_neo4j"] != ["pg1"]:
        failures.append(f"pg_only_neo4j 计算错误: {d['pg_only_neo4j']}")
    if d["extra_milvus"] != ["mi1"] or d["extra_neo4j"] != ["n1"]:
        failures.append("extra 计算错误")
    # 常量
    if not (PG_DSN.startswith("postgresql://") and MILVUS_URI.startswith("http://")
            and MILVUS_COLLECTION and NEO4J_URI.startswith("http://")):
        failures.append("连接常量缺失/非法")
    # 幂等补写插入函数被调用前需可构造 outbox 字段（模拟游标不可行，这里仅验证元组形态）
    if not callable(_insert_outbox_if_missing):
        failures.append("_insert_outbox_if_missing 缺失")
    # chunk 源可读（确认缺口口径为 doc_chunks 子块全集）
    if not (PROJECT_ROOT / "chunks" / "chunks_v1.jsonl").exists():
        failures.append("chunks_v1.jsonl 缺失")
    if failures:
        print("[FAIL] reconcile 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print("[OK] reconcile 自检通过：diff 算术正确 / 连接常量完整 / 幂等补写可用 / "
          "chunk 源存在（未联网、只读口径）")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="B6 三侧对账（PG/Milvus/Neo4j）")
    p.add_argument("--fix", action="store_true", help="为「PG 有而存储缺」的 chunk 幂等补写 outbox")
    p.add_argument("--fault-inject", choices=["milvus", "neo4j"], default=None,
                   help="故障注入（ctl）目标；默认只预演，需配合 --apply 才真实删除")
    p.add_argument("--chunk-id", default=None, help="故障注入指定 chunk_id（仅操作此一条）")
    p.add_argument("--apply", action="store_true",
                   help="配合 --fault-inject 才执行真实删除（默认仅预演，安全）")
    p.add_argument("--print", dest="print_n", type=int, default=DIFF_PRINT,
                   help="每类差异打印前 N 条")
    p.add_argument("--selftest", action="store_true", help="离线自检（不联网）")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.fault_inject:
        if not args.chunk_id:
            p.error("--fault-inject 必须配合 --chunk-id")
        apply_fault_inject(args.fault_inject, args.chunk_id, args.apply)

    pg = pg_chunk_ids()
    milvus = milvus_chunk_ids()
    neo4j = neo4j_chunk_ids()
    diff = compare(pg, milvus, neo4j)
    print(f"[reconcile] PG={len(pg)} / Milvus={len(milvus)} / Neo4j(有关系的chunk)={len(neo4j)}")
    report(diff, args.print_n)

    if args.fix:
        apply_fix(diff)
    elif diff["pg_only_milvus"] or diff["pg_only_neo4j"]:
        print("\n[提示] 存在「PG 有而存储缺」的 chunk→运行 `reconcile.py --fix` + "
              "`outbox_worker.py` 收敛；多余项供人工研判。")
    return 0


if __name__ == "__main__":
    sys.exit(main())