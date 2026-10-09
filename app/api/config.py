"""P4 API 层配置（环境变量优先，默认值仅限开发环境）。

口径：
- PG 连接串与 app.graph.checkpointer 同源（LANGGRAPH_PG_URL 可覆盖，避免两处口径漂移）
- JWT 密钥生产环境必须通过环境变量注入；默认值仅供本地开发，启动时打警告
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------- 数据库 ----------------
# 与 app.graph.checkpointer.POSTGRES_URL 同源：优先 API_PG_URL，其次 LANGGRAPH_PG_URL
POSTGRES_URL = os.environ.get(
    "API_PG_URL",
    os.environ.get("LANGGRAPH_PG_URL", "postgresql://root:123456@127.0.0.1:5433/auscult_v2"),
)

# ---------------- JWT ----------------
# 开发默认密钥 ≥32 字节（RFC 7518 对 HS256 的建议下限）；生产必须环境变量注入
JWT_SECRET = os.environ.get("JWT_SECRET", "<REDACTED_DEV_SECRET>")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))  # 8h（一个班次）

# ---------------- 数据源（/api/health 探测用） ----------------
HEALTH_TIMEOUT_S = float(os.environ.get("HEALTH_TIMEOUT_S", "1.0"))
MILVUS_HOST = os.environ.get("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = int(os.environ.get("MILVUS_PORT", "19531"))   # v2 栈（基线 19530 被占）
NEO4J_HOST = os.environ.get("NEO4J_HOST", "127.0.0.1")
NEO4J_PORT = int(os.environ.get("NEO4J_PORT", "7687"))
TDENGINE_HOST = os.environ.get("TDENGINE_HOST", "127.0.0.1")
TDENGINE_PORT = int(os.environ.get("TDENGINE_PORT", "6041"))
REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

# ---------------- 云端预算（V5.0 §7.1：340 次/天） ----------------
_CLOUD_JSON = Path(__file__).resolve().parents[2] / "env" / "cloud.json"
CLOUD_BUDGET_LIMIT = int(os.environ.get("CLOUD_BUDGET_LIMIT", "340"))
if _CLOUD_JSON.exists():
    import json

    try:
        _cfg = json.loads(_CLOUD_JSON.read_text(encoding="utf-8"))
        CLOUD_BUDGET_LIMIT = int(_cfg.get("budget_daily_limit", CLOUD_BUDGET_LIMIT))
    except (ValueError, OSError):
        pass  # 配置损坏时回退默认 340，不让 health 挂掉
