"""B4 三元组抽取（Phase 1 · 知识库 · Neo4j 入库前置）

来源：`plan/p1-plan-detailed.md` §5.7 B4
词表：`configs/triple_schema.json`（实体/关系 enum + OpenAI strict json_schema + Neo4j 关系映射）

流程（抽取 → 校验 → 人工复核门禁 → 全量入库）：
  1. 逐子块拼 prompt（系统提示含受控词表 enum 与抽取/禁止编造规则）→ `LLMAdapter.chat`
     （`structured_output=True` + `grammar=triple_schema.schema` → `response_format: json_schema` 云端约束解码）；
  2. JSON Schema + 语义校验（head/tail 非空、类型/关系属于 enum、confidence∈[0,1]）；
  3. 每子块结果原样落 `experiments/p1/b4/extract_results.jsonl`；
  4. `--sample 100` 从全量三元组抽样 100 条 → `manual_review_100.jsonl` 供人工复核（判据 ≥85%）；
  5. 复核达标后 `--import-neo4j` 全量 MERGE 入库。

纯标准库（与 V1 判分链路一致，不引入第三方包）。

用法：
  python scripts/extract_triples.py --selftest
  python scripts/extract_triples.py --limit 1          # dry-run：验证云端连接 + strict schema 连通
  python scripts/extract_triples.py                    # 全量 36 子块抽取 → extract_results.jsonl
  python scripts/extract_triples.py --sample 100       # 抽样 100 条人工复核
  python scripts/extract_triples.py --import-neo4j     # 从结果文件全量 MERGE 入库
"""

from __future__ import annotations

import argparse
import base64
import json
import random
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_adapter                                                    # noqa: E402
from llm_adapter import LLMAdapter                                     # noqa: E402

DEFAULTS = {
    "config": PROJECT_ROOT / "env" / "cloud.json",
    "schema": PROJECT_ROOT / "configs" / "triple_schema.json",
    "chunks": PROJECT_ROOT / "chunks" / "chunks_v1.jsonl",
    "out_dir": PROJECT_ROOT / "experiments" / "p1" / "b4",
    "neo4j_uri": "http://127.0.0.1:7474",
    "neo4j_user": "neo4j",
    "neo4j_password": "auscult_p0_dev",
}

# B4 抽取用固定参数（从 llm_adapter 的 V1 固定参数继承，仅放宽 max_tokens 以容纳每块多条三元组）
TEMPERATURE = llm_adapter.DEFAULT_TEMPERATURE
SEED = llm_adapter.DEFAULT_SEED
NUM_CTX = llm_adapter.DEFAULT_NUM_CTX
TOP_P = llm_adapter.DEFAULT_TOP_P
MAX_TOKENS = 2048

RESULTS_FILENAME = "extract_results.jsonl"
REVIEW_FILENAME = "manual_review_100.jsonl"
REVIEW_TARGET = 100
REVIEW_PASS_RATE = 0.85


def load_config(path: Path) -> dict[str, Any]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in ("provider", "model", "endpoint", "api_key") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"[b4] {path} 缺必填项：{missing}")
    return cfg


def load_schema(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    need = ("entity_types", "relation_types", "neo4j_relation_map", "schema")
    if any(k not in doc for k in need):
        raise SystemExit(f"[b4] {path} 缺字段：{need}")
    return doc


def load_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---------------------------------------------------------------- 校验


def validate_triple(triple: dict[str, Any], schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """轻量校验单条三元组，返回 (合法?, 问题列表)。纯标准库实现，覆盖 schema items 约束。"""
    errs: list[str] = []
    entity_types = set(schema["entity_types"])
    relation_types = set(schema["relation_types"])
    for key in ("head", "head_type", "relation", "tail", "tail_type", "source_chunk_id"):
        if key not in triple:
            errs.append(f"缺字段 {key}")
    if triple.get("head_type") not in entity_types:
        errs.append(f"head_type 不在词表: {triple.get('head_type')!r}")
    if triple.get("tail_type") not in entity_types:
        errs.append(f"tail_type 不在词表: {triple.get('tail_type')!r}")
    if triple.get("relation") not in relation_types:
        errs.append(f"relation 不在词表: {triple.get('relation')!r}")
    if not isinstance(triple.get("confidence", -1), (int, float)) or not 0 <= triple["confidence"] <= 1:
        errs.append(f"confidence 非法: {triple.get('confidence')!r}")
    head = (triple.get("head") or "").strip()
    tail = (triple.get("tail") or "").strip()
    if not head:
        errs.append("head 为空")
    if not tail:
        errs.append("tail 为空")
    if errs:
        return False, errs
    # 语义对象：头部 span 规范化（写入/入库稳定）
    triple["head"] = head
    triple["tail"] = tail
    return True, []


def parse_content(content: str) -> dict[str, Any] | None:
    """从约束解码正文解析出 `{"triples": [...]}`；失败时回退抽取首个 JSON 顶层对象。"""
    if content and content.strip():
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
    objs = llm_adapter._extract_json_objects(content or "")
    for obj in objs:
        if isinstance(obj, dict) and "triples" in obj:
            return obj
    return None


# ---------------------------------------------------------------- 抽取


def build_system_prompt(schema: dict[str, Any]) -> str:
    entities = "、".join(schema["entity_types"])
    relations = "、".join(schema["relation_types"])
    return (
        "你是工业 IoT 诊断知识图谱的三元组抽取器，输入为设备手册/维修工单/故障案例/判据等文档"
        "子块，输出其中「实体-关系-实体」三元组。\n"
        "抽取规则：\n"
        "  1. 只抽取子块内明确表达的关系，禁止编造/推断原文未提及的内容；\n"
        "  2. head、tail 使用原文中的名称，不得改写缩写或补全型号；\n"
        f"  3. head_type / tail_type 仅可从实体类型 {entities} 中选择；\n"
        f"  4. relation 仅可从关系类型 {relations} 中选择；\n"
        "  5. source_chunk_id 必须等于随语料给出的 chunk_id；\n"
        "  6. confidence 为 0~1 的置信度；\n"
        "  7. 「处置为」仅当原文在**同一句/紧邻**将某故障一与该处置动作直接对应时才抽，"
        "禁止把权属不明的通用处置挂到无关故障；\n"
        "  8. 优先使用具体关系：电机→泵用「驱动」、部件→设备用「构成」、拓扑无驱动而属物理连接的用"
        "「连接」、参数-标准值边界用「阈值/超限」，**禁止使用「关联」这类通用兜底关系**；\n"
        "  9. 每条三元的来源必须 unambiguously 支撑其 head_type/tail_type/relation 选择，否则不抽。\n"
        "输出必须是合法 JSON 对象 `{\"triples\": [...]}`，每项含 "
        "head/head_type/relation/tail/tail_type/confidence/source_chunk_id 七个字段。"
    )


def build_user_message(chunk: dict[str, Any], schema: dict[str, Any]) -> str:
    meta = (
        f"文档 id: {chunk.get('doc_id')}\n文档类型: {chunk.get('doc_type')}\n"
        f"设备型号: {chunk.get('device_model')}\n章节: {chunk.get('section')}\n"
        f"页码: {chunk.get('page')}\nchunk_id: {chunk.get('id')}\n"
    )
    return f"{meta}\n以下为待抽取的文档子块正文：\n---\n{chunk.get('text', '')}\n---\n"


def extract_one(chunk: dict[str, Any], adapter: LLMAdapter, model: str,
                schema: dict[str, Any]) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": build_system_prompt(schema)},
        {"role": "user", "content": build_user_message(chunk, schema)},
    ]
    result = adapter.chat(messages, model=model, use_tools=False)
    valid_triples: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    root = parse_content(result.content_clean)
    if root and isinstance(root.get("triples"), list):
        for triple in root["triples"]:
            triple = dict(triple)
            triple["source_chunk_id"] = chunk["id"]      # 以随语料给定的 chunk id 为准，忽略模型回显
            ok, errs = validate_triple(triple, schema)
            (valid_triples if ok else invalid_rows).append({**triple, "_errors": errs} if not ok else triple)
    return {
        "chunk_id": chunk["id"],
        "doc_id": chunk["doc_id"],
        "doc_type": chunk["doc_type"],
        "n_valid": len(valid_triples),
        "n_invalid": len(invalid_rows),
        "triples": valid_triples,
        "invalid": invalid_rows,
        "latency_ms": round(result.latency_ms, 3),
        "error": result.error,
        "raw_content": result.content_raw,
        "model": model,
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- 落盘


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def flatten_triples(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in results:
        for t in row.get("triples", []):
            t = dict(t)
            t["_doc_id"] = row["doc_id"]
            t["_doc_type"] = row["doc_type"]
            out.append(t)
    return out


# ---------------------------------------------------------------- 人工复核抽样


def make_review_sample(results_path: Path, review_path: Path, target: int = REVIEW_TARGET,
                       seed: int = SEED) -> int:
    results = read_jsonl(results_path)
    triples = flatten_triples(results)
    if len(triples) < target:
        print(f"[b4] 警告：全量三元组仅 {len(triples)} 条，不足抽样目标 {target}，按全量输出。")
        sample = triples
    else:
        sample = random.Random(seed).sample(triples, target)
    rows = [{"pass": "", "note": "", **t} for t in sample]
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                           encoding="utf-8")
    return len(rows)


# ---------------------------------------------------------------- 失败补偿


def retry_failed(results_path: Path, chunks: list[dict[str, Any]], adapter: LLMAdapter,
                 model: str, schema: dict[str, Any]) -> None:
    """增量补偿 error / 缺失子块：重新抽取并重写结果文件（按子块顺序，去重覆盖）。"""
    existing = read_jsonl(results_path)
    have = {r["chunk_id"] for r in existing if not r.get("error")}
    need = [c for c in chunks if c["id"] not in have]
    final = {r["chunk_id"]: r for r in existing if not r.get("error")}
    for c in need:
        row = extract_one(c, adapter, model, schema)
        final[c["id"]] = row
        mark = "OK " if not row["error"] else "ERR"
        print(f"  [{mark}] {row['chunk_id']} 有效={row['n_valid']} 无效={row['n_invalid']} "
              + (f"err={row['error'][:80]}" if row["error"] else ""))
    ordered = [final[c["id"]] for c in chunks if c["id"] in final]
    results_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in ordered) + "\n",
                            encoding="utf-8")
    total = sum(r["n_valid"] for r in ordered)
    errs = sum(1 for r in ordered if r.get("error"))
    print(f"[b4] 重试完成：重试 {len(need)} 块，剩余失败 {errs}，累计有效三元组 {total} → {results_path}")


# ---------------------------------------------------------------- Neo4j 入库


# @- 数组 CQL 事务端（免第三方驱动；Neo4j 5 system/database 默认 neo4j）
def _neo4j_tx(uri: str, user: str, password: str, statements: list[str]) -> list[Any]:
    """POST /db/neo4j/tx/commit 执行一批 Cypher，返回 transactions.commit 结果的 results。"""
    endpoint = uri.rstrip("/") + "/db/neo4j/tx/commit"
    auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {"Content-Type": "application/json", "Authorization": auth}
    body = json.dumps({"statements": [{"statement": s} for s in statements]}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:                                     # noqa: BLE001 - 网络/HTTP 兜底
        raise RuntimeError(f"Neo4j {endpoint} 请求失败：{type(exc).__name__}: {exc}")
    if data.get("errors"):
        raise RuntimeError(f"Neo4j 执行错误：{data['errors']}")
    return data.get("results", [])


def ensure_constraints(uri: str, user: str, password: str) -> None:
    cql = "CREATE CONSTRAINT triple_entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE"
    _neo4j_tx(uri, user, password, [f"SHOW CONSTRAINTS YIELD name RETURN name",
                                    cql,
                                    "SHOW CONSTRAINTS YIELD name RETURN name"])


def entity_id(type_: str, name: str) -> str:
    return f"{type_}:{name}"


def import_neo4j(results_path: Path, uri: str, user: str, password: str,
                 schema: dict[str, Any], exclude: set[str] | None = None) -> tuple[int, int, int]:
    rel_slug = schema["neo4j_relation_map"]
    exclude = exclude or set()
    triples = [t for t in flatten_triples(read_jsonl(results_path)) if t["relation"] not in exclude]
    statements: list[str] = []
    distinct_entities = 0
    rel_count = 0
    seen_nodes: set[str] = set()
    for t in triples:
        hid, tid = entity_id(t["head_type"], t["head"]), entity_id(t["tail_type"], t["tail"])
        cql_rel = rel_slug[t["relation"]]
        cid = t["source_chunk_id"]
        if hid not in seen_nodes:
            statements.append(
                f"MERGE (h:Entity {{id: {hid!r}}}) ON CREATE SET h.name = {t['head']!r}, "
                f"h.type = {t['head_type']!r}")
            seen_nodes.add(hid)
            distinct_entities += 1
        if tid not in seen_nodes:
            statements.append(
                f"MERGE (n:Entity {{id: {tid!r}}}) ON CREATE SET n.name = {t['tail']!r}, "
                f"n.type = {t['tail_type']!r}")
            seen_nodes.add(tid)
            distinct_entities += 1
        # 关系以 rid(=head|关系|tail) MERGE 去重；source 用数组 source_chunk_ids 累加，
        # 支持「同一知识由多个子块表达」的归因（B4 补链：一关系多 source），
        # source_chunk_id 保留为数组首个值，兼容旧查询（reconcile/outbox_worker）。
        statements.append(
            f"MATCH (h:Entity {{id: {hid!r}}}), (n:Entity {{id: {tid!r}}}) "
            f"MERGE (h)-[r:{cql_rel} {{rid: {f'{hid}|{cql_rel}|{tid}'!r}}}]->(n) "
            f"ON CREATE SET r.source_chunk_ids = [{cid!r}], r.source_chunk_id = {cid!r}, "
            f"r.confidence = {float(t['confidence'])}, "
            f"r.source_count = 1 "
            f"ON MATCH SET r.source_chunk_ids = "
            f"CASE WHEN {cid!r} IN coalesce(r.source_chunk_ids, []) "
            f"THEN coalesce(r.source_chunk_ids, []) "
            f"ELSE coalesce(r.source_chunk_ids, []) + [{cid!r}] END, "
            f"r.source_count = size(coalesce(r.source_chunk_ids, []))")
        rel_count += 1
    _neo4j_tx(uri, user, password, statements)
    return distinct_entities, distinct_entities, rel_count


# ---------------------------------------------------------------- 自检


def _selftest(schema_path: Path, chunks_path: Path) -> int:
    failures: list[str] = []
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not schema.get("entity_types") or not schema.get("relation_types"):
        failures.append("entity_types / relation_types 为空")
    if set(schema["neo4j_relation_map"]) != set(schema["relation_types"]):
        failures.append("neo4j_relation_map 与 relation_types 不一致")
    s = schema["schema"]
    if s.get("type") != "object" or "triples" not in s.get("properties", {}):
        failures.append("schema 缺顶层 triples 对象")
    items = s["properties"]["triples"].get("items", {})
    required = items.get("required", [])
    if not set(required) >= {"head", "head_type", "relation", "tail", "tail_type",
                             "confidence", "source_chunk_id"}:
        failures.append(f"triple items required 不完整：{required}")
    if items.get("additionalProperties") is not False:
        failures.append("triple items additionalProperties 须为 false（strict 前提）")
    # 词表 enum 与 schema 内 enum 一致
    item_props = items.get("properties", {})
    for field in ("head_type", "tail_type"):
        if item_props.get(field, {}).get("enum") != schema["entity_types"]:
            failures.append(f"{field} schema enum 与 entity_types 不一致")
    if item_props.get("relation", {}).get("enum") != schema["relation_types"]:
        failures.append("relation schema enum 与 relation_types 不一致")
    chunks = load_chunks(chunks_path)
    if not chunks:
        failures.append("子块为空")
    # 抽样口径保证可采样
    if len(chunks) < 1:
        failures.append("子块数不合预期")
    if failures:
        print("[FAIL] extract_triples 自检未通过：")
        for f in failures:
            print("  -", f)
        return 1
    print(f"[OK] extract_triples 自检通过：实体 {len(schema['entity_types'])} / "
          f"关系 {len(schema['relation_types'])} / 子块 {len(chunks)} 条 / strict schema 完整 / "
          f"Neo4j 映射一致")
    return 0


# ---------------------------------------------------------------- 主流程


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="B4 三元组抽取")
    p.add_argument("--config", type=Path, default=DEFAULTS["config"])
    p.add_argument("--schema", type=Path, default=DEFAULTS["schema"])
    p.add_argument("--chunks", type=Path, default=DEFAULTS["chunks"])
    p.add_argument("--out-dir", type=Path, default=DEFAULTS["out_dir"])
    p.add_argument("--limit", type=int, default=0, help="只处理前 N 个子块（dry-run 验证）")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--results", type=Path, default=None,
                   help="抽取结果文件（--sample / --import-neo4j 的输入，默认 out-dir/extract_results.jsonl）")
    p.add_argument("--sample", type=int, default=0, help="抽样 N 条写入人工复核文件")
    p.add_argument("--retry-failed", action="store_true",
                   help="增量补偿：仅对结果文件中 error/缺失的子块重新抽取并重写结果文件")
    p.add_argument("--import-neo4j", action="store_true", help="从结果文件全量 MERGE 入库")
    p.add_argument("--exclude-relations", default="",
                   help="入库时排除的关系（逗号分隔，如：处置为 表示结构关系优先入库）")
    p.add_argument("--neo4j-uri", default=DEFAULTS["neo4j_uri"])
    p.add_argument("--neo4j-user", default=DEFAULTS["neo4j_user"])
    p.add_argument("--neo4j-password", default=DEFAULTS["neo4j_password"])
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest(args.schema, args.chunks)

    scheme = json.loads(args.schema.read_text(encoding="utf-8"))
    results_path = args.results or (args.out_dir / RESULTS_FILENAME)

    if args.retry_failed:
        cfg = load_config(args.config)
        chunks = load_chunks(args.chunks)
        adapter = LLMAdapter(
            endpoint=cfg["endpoint"], api_key=cfg["api_key"],
            temperature=TEMPERATURE, seed=SEED, num_ctx=NUM_CTX, top_p=TOP_P,
            max_tokens=MAX_TOKENS, grammar=scheme["schema"], structured_output=True,
        )
        retry_failed(results_path, chunks, adapter, cfg["model"], scheme)
        return 0

    if args.import_neo4j:
        exclude = {r.strip() for r in args.exclude_relations.split(",") if r.strip()}
        ensure_constraints(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
        nodes, distinct, rels = import_neo4j(results_path, args.neo4j_uri, args.neo4j_user,
                                             args.neo4j_password, scheme, exclude=exclude or None)
        suffix = f"（排除: {args.exclude_relations}）" if exclude else "（全量）"
        print(f"[b4] Neo4j 入库完成{suffix}：节点 {nodes} / 关系 {rels} 条 → {args.neo4j_uri}")
        print("[b4] 验证示例：MATCH (h:Entity)-[r]->(n) RETURN h.name, type(r), n.name LIMIT 30")
        return 0

    if args.sample:
        n = make_review_sample(results_path, args.out_dir / REVIEW_FILENAME, args.sample)
        print(f"[b4] 人工复核样本 {n} 条 → {args.out_dir / REVIEW_FILENAME}")
        print(f"[b4] 判据：通过率 ≥ {REVIEW_PASS_RATE:.0%} 方可全量入库。"
              f"复核后运行 python scripts/extract_triples.py --import-neo4j")
        return 0

    cfg = load_config(args.config)
    chunks = load_chunks(args.chunks)
    selected = chunks[args.offset:]
    if args.limit:
        selected = selected[: args.limit]
    if not selected:
        print("[b4] 无子块可处理（offset 越界或 limit=0 时正常？limit=0 表示全量；offset 请勿超界）")
        return 1

    adapter = LLMAdapter(
        endpoint=cfg["endpoint"], api_key=cfg["api_key"],
        temperature=TEMPERATURE, seed=SEED, num_ctx=NUM_CTX, top_p=TOP_P,
        max_tokens=MAX_TOKENS, grammar=scheme["schema"], structured_output=True,
    )
    print("[b4] B4 三元组抽取（云端约束解码 response_format=json_schema）")
    print(adapter.describe())
    print(f"[b4] model: {cfg['model']} | 子块: {len(selected)} | 词表: "
          f"实体{len(scheme['entity_types'])} 关系{len(scheme['relation_types'])}")

    total_triples = 0
    total_invalid = 0
    failed = 0
    for i, chunk in enumerate(selected):
        row = extract_one(chunk, adapter, cfg["model"], scheme)
        append_jsonl(results_path, [row])
        total_triples += row["n_valid"]
        total_invalid += row["n_invalid"]
        if row["error"]:
            failed += 1
            mark = "ERR"
        elif row["n_invalid"]:
            mark = "PART"
        else:
            mark = "OK "
        print(f"  [{mark}] {row['chunk_id']} 有效={row['n_valid']} 无效={row['n_invalid']} "
              f"latency={row['latency_ms']:.0f}ms" + (f" err={row['error'][:80]}" if row['error'] else ""))

    print(f"[b4] 完成 {len(selected)} 子块 → {results_path}  累计有效 {total_triples} / "
          f"无效 {total_invalid} / 失败 {failed}")
    print(f"[b4] 下一步：python scripts/extract_triples.py --sample 100 供人工复核")
    return 0


if __name__ == "__main__":
    sys.exit(main())