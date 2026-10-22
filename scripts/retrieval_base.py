"""W2 多路召回共享基座（Phase 2 · 混合检索）

提供三路召回（Dense/Sparse/Graph）的统一契约与工具函数，避免脚本间重复实现：
  1. 迷你 YAML 加载（`configs/retrieval.yml`，仅需现有配置文件的无依赖子集）；
  2. 统一改写输入解析：吃 `query_rewrite` 输出 `{semantic, keywords, entities[], numeric}`，
     按 `configs/retrieval.yml::routes` 抽各路所需字段；
  3. 统一候选输出结构：`[_hit]`，每条 `{chunk_id, score, rank, route}`（Graph 为 `source_chunk_ids` 展开）；
  4. Neo4j HTTP 事务 helper（复用 `extract_triples` 的端点/凭证约定）。
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_CONFIG = PROJECT_ROOT / "configs" / "retrieval.yml"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from milvus_endpoint import milvus_uri  # noqa: E402

# 拓扑常量（与 build_milvus_v1.py / extract_triples.py 保持一致，便于复用）
# ISS-042：端点口径收在 `scripts/milvus_endpoint.py`（默认 19531 = deploy 栈宿主映射；
# P5 复现 kee-milvus 口径设 MILVUS_PORT=39530）。
MILVUS_URI = milvus_uri()
MILVUS_COLLECTION = "kb_p1_v1"
NEO4J_URI = "http://127.0.0.1:7474"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "auscult_p0_dev")

# W4 本地重排模型（version-lock §二.2.2.2，已 probe 实测：CPU 加载 4.57s、~54ms/对@batch16）
RERANKER_MODEL_PATH = PROJECT_ROOT / (
    r"D:\modelscope\hub\models\BAAI--bge-reranker-v2-m3\snapshots\master")

# -------------------------------- 迷你 YAML 加载（仅需的扁平子集） --------------------------------

_CONTAINER_KEY_RE = re.compile(r"^([A-Za-z0-9_]+):\s*$")
_SCALAR_RE = re.compile(r"^([A-Za-z0-9_]+):\s*(.+?)\s*$")
_ARRAY_RE = re.compile(r"^([A-Za-z0-9_]+):\s*(\[.*\])\s*$")
_LIST_ITEM_RE = re.compile(r"^-\s*(\S.*)$")
_STR_BARE_RE = re.compile(r"^[A-Za-z0-9_/.]+$")


def _cast_scalar(raw: str) -> Any:
    s = raw.strip()
    # 剥离行尾内联注释（# 之后），含中文注释
    if " #" in s:
        s = s.split(" #", 1)[0].rstrip()
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s.startswith(("\"", "'")) and s.endswith(s[0]):
        return s[1:-1]
    if s.startswith("["):                                        # 内联 JSON 数组（如 ["semantic"]）
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s
    try:                                                         # 先数值后裸串："64"/"1.2" → int/float
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    if _STR_BARE_RE.match(s):
        return s
    return s


def load_yaml(path: Path) -> dict[str, Any]:
    """加载本仓库的 `retrieval.yml`（2~3 层嵌套 + 标量/内联列表，无锚点引用）。"""
    lines: list[tuple[int, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.rstrip()
        if not s.strip() or s.lstrip().startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip()), s.strip()))

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]  # (indent, dict), root 为 -1
    for indent, line in lines:
        # 弹出所有比当前更深的层级
        while stack and len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        m = _SCALAR_RE.match(line)
        if m and m.group(2):                                # key: value
            parent[m.group(1)] = _cast_scalar(m.group(2))
            continue
        m = _CONTAINER_KEY_RE.match(line)                   # key: (空容器，下一行进入)
        if m:
            child: dict[str, Any] = {}
            parent[m.group(1)] = child
            stack.append((indent, child))
            continue
        # 内联数组：key: [a, b]
        m = _ARRAY_RE.match(line)
        if m:
            parent[m.group(1)] = _cast_scalar(m.group(2))
            continue
        # 孤立标量（含嵌套值下的裸项）——本配置文件不产生，忽略即可
    return root


def load_retrieval_config() -> dict[str, Any]:
    return load_yaml(RETRIEVAL_CONFIG)


# -------------------------------- 统一改写输入抽取 --------------------------------

def extract_route_inputs(rewrite: dict[str, Any]) -> dict[str, Any]:
    """从 query_rewrite 输出抽各路输入。

    Returns:
      {"semantic": str, "keywords": str 全文, "entities": [{text,type}], "numeric": [str]}
    """
    cfg = load_retrieval_config()
    semantic_key = (cfg.get("routes", {}).get("semantic_keys") or ["semantic"])[0]
    keyword_key = (cfg.get("routes", {}).get("keyword_keys") or ["keywords"])[0]
    entity_key = (cfg.get("routes", {}).get("entity_keys") or ["entities"])[0]
    semantic = rewrite.get(semantic_key) or ""
    keywords_raw = rewrite.get(keyword_key) or []
    entities = rewrite.get(entity_key) or []
    keywords_text = " ".join(str(k) for k in keywords_raw) if isinstance(keywords_raw, list) else str(keywords_raw)
    return {
        "semantic": str(semantic),
        "keywords": keywords_text,
        "entities": entities,
        "numeric": rewrite.get("numeric") or [],
    }


# -------------------------------- Neo4j HTTP 事务 --------------------------------

def neo4j_run(statements: list[str], uri: str = NEO4J_URI,
              user: str = NEO4J_USER, password: str = NEO4J_PASSWORD) -> Any:
    """POST /db/neo4j/tx/commit 执行一批 Cypher，返回 results 列表。"""
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


# -------------------------------- 统一候选结构 --------------------------------

def make_hit(chunk_id: str, score: float, rank: int, route: str) -> dict[str, Any]:
    return {"chunk_id": chunk_id, "score": score, "rank": rank, "route": route}