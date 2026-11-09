"""P4 API 层配置（环境变量优先，默认值仅限开发环境）。

口径：
- PG 连接串与 app.graph.checkpointer 同源（LANGGRAPH_PG_URL 可覆盖，避免两处口径漂移）
- JWT 密钥生产环境必须通过环境变量注入；默认值仅供本地开发，启动时打警告
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

# ---------------- 数据库 ----------------
# 与 app.graph.checkpointer.POSTGRES_URL 同源：优先 API_PG_URL，其次 LANGGRAPH_PG_URL
POSTGRES_URL = os.environ.get(
    "API_PG_URL",
    os.environ.get("LANGGRAPH_PG_URL", "postgresql://root:123456@127.0.0.1:5433/auscult_v2"),
)

# ---------------- JWT ----------------
# 2026-11-09 脱敏：**不再内置固定密钥**。未注入 JWT_SECRET 时每次启动随机生成
# （长度 ≥32 字节，满足 RFC 7518 对 HS256 的下限）——本地开发可直接跑，重启后旧
# token 失效；生产/云端必须由环境变量注入稳定密钥。
JWT_SECRET = os.environ.get("JWT_SECRET") or secrets.token_urlsafe(32)
IS_DEV_SECRET = not os.environ.get("JWT_SECRET")
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

# ---------------- Redis 缓存层（P7；db 1 与协调原语 db 0 隔离） ----------------
# 定位：非权威、可重建、fail-open（docs/p7-design-redis-cache-layer-2026-10-16.md）。
# 独立环境变量（不复用 AUSCULT_REDIS_URL）——后者面向 db 0 协调原语，
# 缓存换 DB 号/地址时不得影响限流/预算/锁/去重。
CACHE_REDIS_URL = os.environ.get(
    "AUSCULT_CACHE_REDIS_URL", "redis://:auscult-dev-redis@127.0.0.1:6379/1")
CACHE_ENABLED = os.environ.get("AUSCULT_CACHE_ENABLED", "1") not in ("0", "false", "False")
# noeviction + maxmemory 1gb 下，超体积 payload 会牵连 db 0 协调原语 → 主动闸门
CACHE_MAX_VALUE_BYTES = int(os.environ.get("AUSCULT_CACHE_MAX_VALUE_BYTES", str(256 * 1024)))
CACHE_TTL_STATE = int(os.environ.get("AUSCULT_CACHE_TTL_STATE", "86400"))      # 24h（会话口径）
CACHE_TTL_VALUES = int(os.environ.get("AUSCULT_CACHE_TTL_VALUES", "86400"))    # 24h
CACHE_TTL_RETRIEVAL = int(os.environ.get("AUSCULT_CACHE_TTL_RETRIEVAL", "21600"))   # 6h
CACHE_TTL_EMBEDDING = int(os.environ.get("AUSCULT_CACHE_TTL_EMBEDDING", str(30 * 86400)))  # 30d
CACHE_TTL_LLM = int(os.environ.get("AUSCULT_CACHE_TTL_LLM", "86400"))          # 24h
# db 0 协调原语鉴权（ISS-051：health 预算探针原缺失 → used 恒 null）。开发默认与
# CACHE_REDIS_URL 内嵌口令同源（compose 交付栈口径），生产必须 env 注入。
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "auscult-dev-redis")

# ---------------- 告警自动触发（P7；默认关闭，启用须过判据前置） ----------------
# 开启后：alerts 表 status='open' 且 diagnosed_thread_id IS NULL 的新告警
# 自动发起诊断（submitter=system:auto-trigger），幂等标记见 migration 0007。
AUTO_TRIGGER_ENABLED = os.environ.get("AUSCULT_AUTO_TRIGGER", "0") in ("1", "true", "True")
# 空 = 不按严重度过滤；否则逗号分隔子集，如 "high,critical"
AUTO_TRIGGER_SEVERITY = tuple(
    s.strip() for s in os.environ.get("AUSCULT_AUTO_TRIGGER_SEVERITY", "").split(",") if s.strip())
AUTO_TRIGGER_INTERVAL_SEC = float(os.environ.get("AUSCULT_AUTO_TRIGGER_INTERVAL_SEC", "5"))
AUTO_TRIGGER_LIMIT = int(os.environ.get("AUSCULT_AUTO_TRIGGER_LIMIT", "50"))

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
