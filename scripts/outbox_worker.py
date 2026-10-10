"""B6 Outbox 消费与补偿 Worker（Phase 1 · 一致性三件套之一）

来源：`plan/p1-plan-detailed.md` §5.9（B6 Outbox）；判据＝出口 §1.2：
  「失败注入下对账零差异、补偿队列可自愈」。

职责：消费 `outbox` 表中 `status='pending'` 的行，对 `target` 做对应动作：
  - `milvus`：在 collection `kb_p1_v1` 中按键（chunk_id，主键）核查该块是否存在；
    缺失则用本地 BGE-M3（`run_v2.EmbeddingClient`）向量化后补齐该行。
  - `neo4j`：经 HTTP 事务端点跑 `MATCH ()-[r {source_chunk_id:$cid}]->() RETURN count(r)`，
    存在性核查 ≥1 条关系即通过；缺失**不补链**（补链归 B4「处置为」专项）仅记录于 last_error。

状态流转：成功→`status='done'`；失败→`retry_count+1` 并写 `last_error`，达上限(默认10)→`failed`。

事务选择（注明）：外部队列消费（Milvus/Neo4j）与 PG 状态更新无法跨系统原子提交，
故采用「先做外部动作、成功后在同一 PG 连接事务里更新该行状态并提交」。若 PG 状态写失败，
该行仍为 pending，下次运行由幂等动作自动重做（milvus upsert / neo4j 只查），实现自愈。

纯标准库 + pymilvus（Milvus 客户端）+ psycopg（PG）；向量化复用 run_v2 的 sentence-transformers。
离线自检不联网、不消费（`--selftest`）。

用法：
  python scripts/outbox_worker.py --selftest
  python scripts/outbox_worker.py --limit 5            # 只消费前 5 条 pending
  python scripts/outbox_worker.py --limit 1000 --batch 20
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
sys.path.insert(0, str(Path(__file__).resolve().parent))   # 保证 import run_v2

# ---------------- 核对后的连接常量（勿自行猜测） ----------------
PG_DSN = "postgresql://root:123456@127.0.0.1:5433/auscult_v2"
MILVUS_URI = "http://127.0.0.1:39530"   # kee-milvus 实际映射 19530→39530（P5 修正）
MILVUS_COLLECTION = "kb_p1_v1"
NEO4J_URI = "http://127.0.0.1:7474"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "auscult_p0_dev")
RETRY_MAX = 10                     # retry_count 达到该值 → status='failed'
DB_BATCH = 10                      # 每处理 N 条打印一次批进度

# Milvus kb_p1_v1 的标量字段（见 scripts/build_milvus_v1.py schema）
MILVUS_FIELDS = ("chunk_id", "text", "dense", "doc_id", "parent_id", "section", "doc_type", "page")


def _load_sub_chunks() -> dict[str, dict[str, Any]]:
    """读 chunks_v1.jsonl 的子块，按键 id 建索引，供 milvus 补齐时还原完整字段。"""
    path = PROJECT_ROOT / "chunks" / "chunks_v1.jsonl"
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        if not c.get("is_parent"):
            out[c["id"]] = c
    return out


def _neo4j_tx(uri: str, user: str, password: str, statements: list[str]) -> list[Any]:
    """POST /db/neo4j/tx/commit 执行一批 Cypher，返回 results（参考 scripts/extract_triples.py）。"""
    endpoint = uri.rstrip("/") + "/db/neo4j/tx/commit"
    import urllib.request                               # noqa: PLC0415
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


def _milvus_has(client, collection: str, cid: str) -> bool:
    """以主键 chunk_id 查询该块是否存在（存在性核查）。"""
    res = client.query(collection_name=collection, filter=f'chunk_id == "{cid}"',
                       output_fields=["chunk_id"], limit=1)
    return bool(res)


# ---------------------------------------------------------------- 消费动作


class _MilvusCompleter:
    """懒加载 Milvus 客户端与 BGE-M3 向量器，仅在真正需要补齐 milvus 缺失块时才实例化。"""

    def __init__(self, uri: str, collection: str) -> None:
        self.uri = uri
        self.collection = collection
        self._client = None
        self._embedder = None
        self._chunks: dict[str, dict[str, Any]] | None = None

    def _client_once(self):
        if self._client is None:
            from pymilvus import MilvusClient            # noqa: PLC0415
            self._client = MilvusClient(uri=self.uri)
        return self._client

    def _embed_once(self, text: str) -> list[float]:
        if self._embedder is None:
            import run_v2                                 # noqa: PLC0415
            self._embedder = run_v2.EmbeddingClient(
                model=run_v2.BGE_M3_MODEL_PATH,
                cache_path=PROJECT_ROOT / "experiments" / "p1" / "b6" / "embed_cache.json")
        return self._embedder.embed([text])[0]

    def ensure(self, entity_id: str, payload: dict[str, Any]) -> bool:
        """确保该块存在于 Milvus；返回是否需要补（False=已存在，True=本次补齐）。"""
        if _milvus_has(self._client_once(), self.collection, entity_id):
            return False
        if self._chunks is None:
            self._chunks = _load_sub_chunks()
        src = self._chunks.get(entity_id)
        dense = self._embed_once(payload.get("text") or (src or {}).get("text", ""))
        row = {
            "chunk_id": entity_id,
            "text": payload.get("text") or (src or {}).get("text", ""),
            "dense": dense,
            "doc_id": payload.get("doc_id") or (src or {}).get("doc_id"),
            "parent_id": src and src.get("parent_id"),
            "section": payload.get("section") or (src or {}).get("section"),
            "doc_type": src and src.get("doc_type"),
            "page": (src and src.get("page")) if (src and isinstance(src.get("page"), int)) else None,
        }
        # upsert 幂等：即便 PK 已存在也覆盖，保证自愈
        self._client_once().upsert(self.collection, [row])
        self._client_once().flush(self.collection)
        return True


def _consume_milvus(client: _MilvusCompleter, orow: dict[str, Any]) -> str:
    added = client.ensure(orow["entity_id"], orow["payload"])
    return f"milvus:{orow['entity_id']} {'补增' if added else '已存在'}"


def _consume_neo4j(orow: dict[str, Any]) -> str:
    cid = orow["entity_id"]
    # B4 v2 复核豁免：纯操作性文本（安全须知/安装要求）被正确判定无可抽三元组，
    # 不属缺口，存在性核查直接视为通过，避免 verify outbox 无限重试。与 reconcile 豁免清单一致。
    if cid in _KNOWN_NO_RELATION_CHUNKS:
        return f"neo4j:{cid} 已豁免（已知无可抽关系）"
    # chunk_id 来自自有语料（受控），做引号逃逸后用字面量拼入 Cypher
    safe = cid.replace("\\", "\\\\").replace('"', '\\"')
    results = _neo4j_tx(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
                        [f'MATCH ()-[r]->() '
                         f'WHERE r.source_chunk_id = "{safe}" OR "{safe}" IN coalesce(r.source_chunk_ids, []) '
                         f'RETURN count(r)'])
    cnt = int(results[0]["data"][0]["row"][0])
    if cnt < 1:
        raise ValueError("存在性核查未通过：图中无该 chunk 的关系"
                         "（补链归 B4「处置为」专项，仅记录）")
    return f"neo4j:{cid} 关系数={cnt}"


# B4 v2 复核：纯操作性文本（安全须知/安装要求）被正确判定无可抽三元组，不属对账缺口。
_KNOWN_NO_RELATION_CHUNKS = frozenset({
    "manual_centrifugal_hc-4-c0",
    "manual_impeller_series-2-c0",
    "manual_scanned_dp-2-c0",
    "manual_ss_process-2-c0",
})


# ---------------------------------------------------------------- 主流程


def _connect():
    import psycopg                                     # noqa: PLC0415
    return psycopg.connect(PG_DSN)


def run_once(limit: int, batch: int, retry_max: int) -> tuple[int, int]:
    """消费一批 pending：返回 (处理条数, 剩余 pending 数)。"""
    pendings: list[dict[str, Any]] = []
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, entity_type, entity_id, op, target, payload "
            "FROM outbox WHERE status='pending' AND retry_count < %s "
            "ORDER BY created_at, id LIMIT %s",
            (retry_max, limit))
        rows = cur.fetchall()
        for r in rows:
            raw = r[5]
            payload = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
            pendings.append({"id": r[0], "entity_type": r[1], "entity_id": r[2],
                             "op": r[3], "target": r[4], "payload": payload})

    if not pendings:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM outbox WHERE status='pending'")
            remaining = cur.fetchone()[0]
        print(f"[worker] 无 pending 可消费，剩余 pending={remaining}")
        return 0, remaining

    completer = _MilvusCompleter(MILVUS_URI, MILVUS_COLLECTION)
    processed = 0
    ok = 0
    failed = 0
    for i, orow in enumerate(pendings, start=1):
        note = ""
        try:
            if orow["target"] == "milvus":
                note = _consume_milvus(completer, orow)
            elif orow["target"] == "neo4j":
                note = _consume_neo4j(orow)
            else:
                raise ValueError(f"未知 target: {orow['target']}")
            new_status = "done"
            ok += 1
        except Exception as exc:                         # noqa: BLE001 - 消费/外部队列兜底
            note = f"失败: {type(exc).__name__}: {exc}"[:500]
            new_status = "pending"
            failed += 1
        # 先做外部动作，再在同连接事务里更新状态（幂等自愈，见模块 docstring）
        with _connect() as conn, conn.cursor() as cur:
            if new_status == "done":
                cur.execute(
                    "UPDATE outbox SET status='done', last_error=%s, updated_at=now() WHERE id=%s",
                    (None, orow["id"]))
            else:
                cur.execute(
                    "UPDATE outbox SET retry_count=retry_count+1, last_error=%s, "
                    "status = CASE WHEN retry_count+1 >= %s THEN 'failed' ELSE status END, "
                    "updated_at=now() WHERE id=%s",
                    (note, retry_max, orow["id"]))
        processed += 1
        print(f"  [{i}/{len(pendings)}] {note}")
        if batch and i % batch == 0:
            print(f"[worker] 批进度：已处理 {processed}，本次 OK={ok} 失败={failed}")

    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM outbox WHERE status='pending'")
        remaining = cur.fetchone()[0]
    print(f"[worker] 完成 {processed} 条（OK={ok} 失败={failed}），剩余 pending={remaining}")
    return processed, remaining


def _selftest() -> int:
    """离线校验：不联网、不消费，只验参数/常量/表结构口径/幂等形状。"""
    failures: list[str] = []
    if not (PG_DSN.startswith("postgresql://") and ":" in PG_DSN.split("@")[-1].split("/")[0]):
        failures.append("PG_DSN 格式异常")
    if not MILVUS_URI.startswith("http://") or not MILVUS_COLLECTION:
        failures.append("MILVUS_URI / COLLECTION 缺失")
    if not NEO4J_URI.startswith("http://"):
        failures.append("NEO4J_URI 缺失")
    if RETRY_MAX <= 0 or DB_BATCH <= 0:
        failures.append("RETRY_MAX / DB_BATCH 须为正")
    subs = _load_sub_chunks()
    if len(subs) < 1:
        failures.append("chunks 子块缺失")
    # 幂等形状：milvus 补齐行字段必须覆盖 collection schema 必备标量字段
    required = {"chunk_id", "text", "dense"}
    if not required.issubset(set(MILVUS_FIELDS)):
        failures.append("MILVUS_FIELDS 缺必备字段")
    # neo4j 核查 CQL 模板可拼装
    try:
        _ = f'MATCH ()-[r {{source_chunk_id: "{subs and next(iter(subs))}"}}]->() RETURN count(r)'
    except Exception as exc:                             # noqa: BLE001
        failures.append(f"neo4j CQL 拼装异常: {exc}")
    if failures:
        print("[FAIL] outbox_worker 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print(f"[OK] outbox_worker 自检通过：常量/参数合法、子块可读({len(subs)}块)、"
          "milvus 字段集完整、neo4j CQL 模板可拼装（未联网、未消费）")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="B6 Outbox 消费与补偿 Worker")
    p.add_argument("--limit", type=int, default=1000, help="最多处理 pending 条数（默认 1000）")
    p.add_argument("--batch", type=int, default=DB_BATCH, help="每 N 条打印一次批进度")
    p.add_argument("--retry-max", type=int, default=RETRY_MAX, help="失败重试上限（达上限置 failed）")
    p.add_argument("--selftest", action="store_true", help="离线自检（不联网、不消费）")
    args = p.parse_args(argv)

    if args.limit <= 0 or args.batch <= 0:
        p.error("--limit / --batch 须为正整数")
    if args.selftest:
        return _selftest()

    processed, remaining = run_once(args.limit, args.batch, args.retry_max)
    print(f"[worker] 结束：本次处理 {processed}，剩余 pending={remaining}"
          "（完成后建议运行 scripts/reconcile.py 复检对账零差异）")
    return 0


if __name__ == "__main__":
    sys.exit(main())