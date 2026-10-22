"""pytest 根配置：**集成测试隔离**（2026-10-22 单独一轮）。

## 为什么要这一层

`scripts/test_*.py` 是打真栈的集成脚本：会跑图、写报告、打审计/轨迹/指标点。
在改造前它们直接写**生产库** `auscult_v2` 和**仓库内已跟踪**的产物文件，于是每跑一次
回归就脏一片（实测：`reports` 表 +8 份测试报告，`reports/*.jsonl`、
`experiments/v1/raw/*.jsonl` 各追加若干行），diff 无法评审、也无法判断"这个改动到底
动了什么"。详见 `reports/cloud-model-switch-verification-2026-10-22.md` §四.2。

## 做了什么（三段，全部在 import app 之前生效）

1. **产物目录**：`AUSCULT_REPORTS_DIR` 指向临时目录 —— 审计（security/cloud/review）、
   轨迹、指标全部落在 `%TEMP%/auscult-it-reports-*`，仓库文件零写入；
2. **数据库**：建一次性临时库 `auscult_it_<uuid>`（跑 db/migrations + 种子 4 角色），
   通过 `API_PG_URL` / `LANGGRAPH_PG_URL`（app 内两处同源）切过去；会话结束 `DROP`；
3. **兜底**：临时库建不起来（无 CREATEDB 权限 / 实例不可达 / 已有同名连接）→
   回退生产库并**大声告警**，绝不静默降级。

为什么必须在 **模块级** 做而不是 fixture 里做：`app/observability/paths.py`、
`app/api/config.py`、`app/graph/checkpointer.py` 的路径/DSN 都是 **import 时求值**的常量，
fixture 执行时 app 模块早被测试模块 import 完了（改不动）。

## 开关

- `AUSCULT_IT_DB=off`：只隔离产物目录，不建临时库（排查"是不是隔离导致"时用）；
- `AUSCULT_IT_REPORTS_DIR=/some/path`：产物目录换到指定位置（默认临时目录）。
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _p in (ROOT, ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_PROD_DSN_DEFAULT = "postgresql://root:123456@127.0.0.1:5433/auscult_v2"

# ---------------------------------------------------------------- 1) 产物目录
_REPORTS_DIR = Path(
    os.environ.get("AUSCULT_IT_REPORTS_DIR")
    or tempfile.mkdtemp(prefix="auscult-it-reports-")
)
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
os.environ["AUSCULT_REPORTS_DIR"] = str(_REPORTS_DIR)
# 路径 D gate（scripts/run_agent_gate.py）的实验审计默认落在**已跟踪**的
# experiments/v1/raw/EXP-P7-GATE-D.security_audit.jsonl；回归也会跑到它，同样重定向到临时目录。
os.environ.setdefault("AUSCULT_AGENT_GATE_AUDIT_PATH",
                      str(_REPORTS_DIR / "agent_gate_audit.jsonl"))

# ---------------------------------------------------------------- 2) 数据库
_ENV_KEYS = ("API_PG_URL", "LANGGRAPH_PG_URL")
_DSN_BEFORE = {k: os.environ.get(k) for k in _ENV_KEYS}
_IT_DB = ""
_IT_NOTE = "未启用"


def _swap_dbname(dsn: str, dbname: str) -> str:
    """把 DSN 的库名换掉（保留 host/port/user/password/options）。"""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo  # noqa: PLC0415

    params = conninfo_to_dict(dsn)
    params["dbname"] = dbname
    return make_conninfo(**params)


def _restore_env() -> None:
    for key, val in _DSN_BEFORE.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def _bootstrap_db() -> None:
    """建临时库 + 迁移 + 种子用户；失败则回退生产库（大声告警）。"""
    global _IT_DB, _IT_NOTE

    if os.environ.get("AUSCULT_IT_DB", "on").strip().lower() in {"off", "0", "false", "no"}:
        _IT_NOTE = "已关闭（AUSCULT_IT_DB=off），使用生产库"
        print(f"[it-isolation] {_IT_NOTE}", file=sys.stderr)
        return

    base = (os.environ.get("API_PG_URL") or os.environ.get("LANGGRAPH_PG_URL")
            or _PROD_DSN_DEFAULT)
    db_name = f"auscult_it_{uuid.uuid4().hex[:8]}"

    try:
        import psycopg  # noqa: PLC0415

        with psycopg.connect(_swap_dbname(base, "postgres"),
                             autocommit=True, connect_timeout=5) as conn:
            conn.execute(f'CREATE DATABASE "{db_name}"')

        it_dsn = _swap_dbname(base, db_name)

        # 迁移（幂等脚本，按序执行；文件内含 BEGIN/COMMIT，需 autocommit）
        with psycopg.connect(it_dsn, autocommit=True, connect_timeout=5) as conn:
            for sql_file in sorted((ROOT / "db" / "migrations").glob("*.sql")):
                conn.execute(sql_file.read_text(encoding="utf-8"))

        # 先切 env，再 import app（config/checkpointer 都是 import 时读 env）
        os.environ["API_PG_URL"] = it_dsn
        os.environ["LANGGRAPH_PG_URL"] = it_dsn

        from app.api.security import hash_password  # noqa: PLC0415

        password = os.environ.get("AUSCULT_SEED_PASSWORD", "Auscult#Dev2026")
        users = [
            ("eng_dev", "张工（工程）", "engineer"),
            ("rev_dev", "李工（审核）", "reviewer"),
            ("kb_dev", "王工（知识库）", "kb_admin"),
            ("sys_dev", "系统管理员", "sys_admin"),
        ]
        with psycopg.connect(it_dsn, connect_timeout=5) as conn:
            for username, display, role in users:
                conn.execute(
                    "INSERT INTO users (username, password_hash, display_name, role) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING",
                    (username, hash_password(password), display, role))

            # 最小工单台账样本：`scripts/test_d5_get_history.py::test_query_real`
            # 断言"已知设备能查到工单"，空库下会 0 行。这里只放 2 条最小样本，
            # 不复制生产数据（生产台账设备名与规范设备号不同源，属 ISS-056 遗留口径）。
            for order_id, fault, action, result in (
                ("WO-IT-0001", "轴承磨损", "更换驱动端轴承", "已恢复"),
                ("WO-IT-0002", "润滑不足", "补充润滑脂", "已恢复"),
            ):
                conn.execute(
                    "INSERT INTO work_orders (order_id, device_id, fault, action, result, "
                    "created_at) VALUES (%s, %s, %s, %s, %s, now()) ON CONFLICT DO NOTHING",
                    (order_id, "C 0泵", fault, action, result))
            conn.commit()

        _IT_DB = db_name
        _IT_NOTE = f"临时库 {db_name}（迁移 {len(list((ROOT / 'db' / 'migrations').glob('*.sql')))} 个 + 种子 4 角色）"
    except Exception as exc:            # noqa: BLE001 —— 隔离失败不能拖垮整轮回归
        _restore_env()
        _IT_DB = ""
        _IT_NOTE = (f"**回退生产库**：临时库创建失败（{type(exc).__name__}: {exc}）"
                    "—— 本轮会写生产库，请检查 CREATEDB 权限/实例状态")
        print(f"[it-isolation][WARN] {_IT_NOTE}", file=sys.stderr)


def _drop_db() -> None:
    if not _IT_DB:
        return
    try:
        import psycopg  # noqa: PLC0415

        base = (_DSN_BEFORE["API_PG_URL"] or _DSN_BEFORE["LANGGRAPH_PG_URL"]
                or _PROD_DSN_DEFAULT)
        with psycopg.connect(_swap_dbname(base, "postgres"),
                             autocommit=True, connect_timeout=5) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{_IT_DB}" WITH (FORCE)')
    except Exception as exc:            # noqa: BLE001
        print(f"[it-isolation][WARN] 临时库 {_IT_DB} 清理失败：{exc}", file=sys.stderr)


_bootstrap_db()


# ---------------------------------------------------------------- pytest hooks
def pytest_report_header(config):            # noqa: ANN001, ARG001
    """把隔离状态打在测试头，跑起来就知道有没有生效。"""
    return [
        f"it-isolation: 产物目录 = {_REPORTS_DIR}",
        f"it-isolation: 数据库   = {_IT_NOTE}",
    ]


def pytest_sessionfinish(session, exitstatus):   # noqa: ANN001, ARG001
    _drop_db()
    print(f"\n[it-isolation] 会话结束：产物留在 {_REPORTS_DIR}"
          f"；数据库={'临时库已 DROP' if _IT_DB else '生产库（未动）'}",
          file=sys.stderr)
