"""V2 压力档压测脚本（只测延迟与内存，不做质量，纪律见 p0-report-v2-hybrid-retrieval §六）。

对给定规模 × 两 BM25 实现（Milvus 服务端 BM25 / ParadeDB 真 BM25）依次：
  1. **建库**：ParadeDB 侧子进程调 `v2_pg_build.py`（sparse，embedding=NULL）；Milvus 侧
     sparse-only 建库（不建 dense 字段、不调 bge-m3，隔离 embedding）。记录建库 wall time。
  2. **延迟**：固定 query 集（`--golden` 前 `--query-limit` 条）重复 `--repeat` 次检索，
     复用 run_v2 计时口径，统计 `P95 latency_ms`/mean。
  3. **内存峰值**：压测期间多次采样 `docker stats` 对应容器（milvus / auscult-v2-milvus、
     pg / auscult-v2-pg），取常驻内存峰值。
  4. 结果落盘 `experiments/v2/raw/EXP-V2-LOAD/`（CSV + JSONL）。

用法（在本仓库 `.venv` 下，三档各跑一次）：
  python scripts/v2_load_test.py --scale 10000
  python scripts/v2_load_test.py --scale 30000
  python scripts/v2_load_test.py --scale 100000
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from run_v2 import GOLDEN_PATH, load_corpus, load_golden  # noqa: E402
from milvus_endpoint import milvus_uri  # noqa: E402

DEFAULT_PG_DSN = "postgresql://root:123456@127.0.0.1:5433/auscult_v2"
DEFAULT_MILVUS_URI = milvus_uri()   # ISS-042：端点单一事实源（默认 19531 = deploy 栈）
TOP_K = 5
PG_CONTAINER = "auscult-v2-pg"
MILVUS_CONTAINER = "auscult-v2-milvus"


# ---------------------------------------------------------------- Milvus sparse-only 建库


class MilvusSparse:
    """压力档 Milvus 稀疏集合（服务端 BM25，无 dense 字段，不调 embedding）。"""

    def __init__(self, uri: str, scale: int, analyzer: str = "jieba") -> None:
        from pymilvus import DataType, Function, FunctionType, MilvusClient  # noqa: PLC0415
        self._api = {"DataType": DataType, "Function": Function,
                     "FunctionType": FunctionType}
        self.uri = uri
        self.analyzer = analyzer
        self.collection = f"kb_v1_load_{scale}"
        self.client = MilvusClient(uri=uri)

    def build(self, docs) -> None:
        DataType = self._api["DataType"]
        Function = self._api["Function"]
        FunctionType = self._api["FunctionType"]
        client = self.client
        if client.has_collection(self.collection):
            client.drop_collection(self.collection)
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, max_length=128, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=65535,
                         enable_analyzer=True,
                         analyzer_params={"tokenizer": self.analyzer})
        schema.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
        schema.add_function(Function(name="bm25", function_type=FunctionType.BM25,
                                     input_field_names=["text"],
                                     output_field_names=["sparse"]))
        idx = client.prepare_index_params()
        idx.add_index(field_name="sparse", index_type="SPARSE_INVERTED_INDEX",
                      metric_type="BM25")
        client.create_collection(self.collection, schema=schema, index_params=idx)
        client.insert(self.collection, [
            {"chunk_id": d.chunk_id, "text": d.text} for d in docs
        ])
        client.flush(self.collection)
        print(f"[milvus] sparse-only 建库完成：{len(docs)} 块 -> {self.collection}")

    def search_sparse(self, question: str, top_k: int) -> list[str]:
        res = self.client.search(collection_name=self.collection, data=[question],
                                 anns_field="sparse", limit=top_k,
                                 output_fields=["chunk_id"])
        return [hit["entity"]["chunk_id"] for hit in (res[0] if res else [])]


# ---------------------------------------------------------------- 工具


def sample_container_mem_gb(container: str) -> float | None:
    """返回容器 CPU 常驻内存使用 GB（峰值采样），失败返回 None。"""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--no-trunc",
             "--format", "{{.Name}}\t{{.MemUsage}}", container],
            capture_output=True, text=True, timeout=30, check=True)
    except Exception:                                   # noqa: BLE001 - 采样容错
        return None
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] == container:
            use = parts[1].split(" / ")[0]             # 例如 "1.870GiB" / "512.3MiB"
            if use.lower().endswith("gib"):
                return float(use[:-3])
            if use.lower().endswith("mib"):
                return float(use[:-3]) / 1024.0
    return None


def _p95(samples: list[float]) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def measure_latency(retriever, queries, repeat: int, top_k: int) -> tuple[list[float], int]:
    """对 query 集重复检索，返回 (samples_ms, total_calls)。复用 run_v2 计时口径。"""
    samples: list[float] = []
    total = 0
    for _ in range(repeat):
        for q in queries:
            started = time.perf_counter()
            retriever(q.question, top_k)
            samples.append((time.perf_counter() - started) * 1000)
            total += 1
    return samples, total


def _run_latency_and_peak(retriever, container: str, queries, repeat: int,
                          top_k: int) -> tuple[float, float, int, float]:
    """返回 (p95_ms, mean_ms, total_calls, peak_gb)，压测期间穿插 docker 内存采样。"""
    all_samples: list[float] = []
    total = 0
    peak = 0.0
    for i in range(repeat):
        samples, calls = measure_latency(retriever, queries, 1, top_k)
        all_samples.extend(samples)
        total += calls
        mem = sample_container_mem_gb(container)
        if mem is not None and mem > peak:
            peak = mem
    return _p95(all_samples), sum(all_samples) / len(all_samples), total, peak


# ---------------------------------------------------------------- 主流程


def run_scale(scale: int, args) -> dict:
    corpus = PROJECT_ROOT / "experiments" / "v2" / "raw" / "corpora_v2" / f"corpus_{scale}.jsonl"
    queries = load_golden(args.golden)[: args.query_limit]
    print(f"\n==== 规模 {scale}｜query={len(queries)}，repeat={args.repeat} ====")

    out_sub = args.out_dir
    out_sub.mkdir(parents=True, exist_ok=True)
    prefix = f"EXP-V2-LOAD-{scale}"
    rows: list[dict] = []

    # ---- ParadeDB side ----
    pg_build_start = time.perf_counter()
    subprocess.run([
        sys.executable, str(PROJECT_ROOT / "scripts" / "v2_pg_build.py"),
        "--dsn", args.pg_dsn, "--corpus", str(corpus), "--ingest-mode", "sparse",
    ], check=True, cwd=str(PROJECT_ROOT))
    pg_build_s = time.perf_counter() - pg_build_start

    pg_ret = _mk_pg_retriever(args.pg_dsn)
    pg_p95, pg_mean, pg_calls, pg_peak = _run_latency_and_peak(
        pg_ret, PG_CONTAINER, queries, args.repeat, TOP_K)
    rows.append(_row(prefix, "pgvector-paradedb", scale, pg_build_s, pg_p95, pg_mean,
                     pg_calls, pg_peak, queries))
    print(f"pgvector-paradedb｜建库 {pg_build_s:.1f}s｜P95 {pg_p95:.1f}ms｜峰值 {pg_peak:.2f}GB")

    # ---- Milvus side ----
    mv = MilvusSparse(args.milvus_uri, scale, analyzer=args.analyzer)
    mv_build_start = time.perf_counter()
    mv.build(load_corpus(corpus))
    mv_build_s = time.perf_counter() - mv_build_start

    mv_p95, mv_mean, mv_calls, mv_peak = _run_latency_and_peak(
        mv.search_sparse, MILVUS_CONTAINER, queries, args.repeat, TOP_K)
    rows.append(_row(prefix, "milvus-bm25", scale, mv_build_s, mv_p95, mv_mean,
                     mv_calls, mv_peak, queries))
    print(f"milvus-bm25｜建库 {mv_build_s:.1f}s｜P95 {mv_p95:.1f}ms｜峰值 {mv_peak:.2f}GB")

    # ---- 落盘 ----
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    csv_path = out_sub / f"{prefix}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        import csv
        writer = csv.DictWriter(fh, fieldnames=[
            "experiment_id", "scale", "route", "build_s", "p95_ms", "mean_ms",
            "calls", "peak_gb", "query_count", "ts",
        ])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    (out_sub / f"{prefix}.json").write_text(
        json.dumps({"ts": ts, "scale": scale, "rows": rows,
                    "query_sample": [q.question for q in queries]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已落盘：{csv_path}")
    return {"scale": scale, "rows": rows}


def _row(prefix, route, scale, build_s, p95, mean, calls, peak, queries) -> dict:
    return {
        "experiment_id": prefix,
        "route": route, "scale": scale, "build_s": round(build_s, 1),
        "p95_ms": round(p95, 1), "mean_ms": round(mean, 1),
        "calls": calls, "peak_gb": round(peak, 2),
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "query_count": len(queries),
    }


def _mk_pg_retriever(dsn):
    from run_v2 import PgvectorRetriever  # noqa: PLC0415
    return PgvectorRetriever(dsn=dsn, embedder=None,  # type: ignore[arg-type]
                             mode="sparse", pg_sparse="paradedb")


def main() -> int:
    parser = argparse.ArgumentParser(description="V2 压力档：BM25 两实现的延迟/内存/建库耗时")
    parser.add_argument("--scale", type=int, choices=(10000, 30000, 100000), required=True)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    parser.add_argument("--milvus-uri", default=DEFAULT_MILVUS_URI)
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--query-limit", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=5,
                        help="对 query 集的重复压测轮数（每轮内逐条 query 检索）")
    parser.add_argument("--analyzer", default="jieba")
    parser.add_argument("--out-dir", type=Path,
                        default=PROJECT_ROOT / "experiments" / "v2" / "raw" / "EXP-V2-LOAD")
    args = parser.parse_args()

    result = run_scale(args.scale, args)
    print(f"\n[汇总] scale={result['scale']}")
    for r in result["rows"]:
        print(f"  {r['route']}: 建库 {r['build_s']}s ｜ P95 {r['p95_ms']}ms "
              f"｜ mean {r['mean_ms']}ms ｜ peak {r['peak_gb']}GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())