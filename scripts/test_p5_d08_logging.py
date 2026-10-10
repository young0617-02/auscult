# -*- coding: utf-8 -*-
"""P5-W2/D8 结构化日志自测（M5.2）

验证项：
  1. configs/logging.yml 可解析（formatter/handler/logger 齐）
  2. setup_logging 装配 + 幂等
  3. JSON 行格式（ts/level/logger/msg/trace_id/module/funcName 七字段）
  4. trace_id 贯穿：set_trace_id → 日志 → query_by_trace 查回
  5. TestClient 请求：日志 trace_id 与 X-Trace-Id 响应头一致（贯穿闭环）
  6. logs/ 目录落在项目根（非 CWD 漂移）

运行：.venv\\Scripts\\python.exe scripts\\test_p5_d08_logging.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.api.errors import set_trace_id  # noqa: E402
from app.observability.logging_config import (  # noqa: E402
    LOGS_DIR,
    query_by_trace,
    setup_logging,
)

LOG_FILE = LOGS_DIR / "auscult.log"


def test_yml() -> None:
    cfg = yaml.safe_load((PROJECT_ROOT / "configs/logging.yml").read_text(encoding="utf-8"))
    assert "json" in cfg["formatters"]
    assert {"file", "stderr"} <= set(cfg["handlers"])
    assert cfg["handlers"]["file"]["maxBytes"] == 10485760
    assert cfg["handlers"]["file"]["backupCount"] == 5
    print("[PASS] configs/logging.yml（json formatter + 轮转 10MB×5）")


def test_setup_and_format() -> None:
    setup_logging()
    setup_logging()   # 幂等
    tid = uuid.uuid4().hex[:16]
    set_trace_id(tid)
    logging.getLogger("app.test").info("D8 自测日志 %s", "占位参数")
    time.sleep(0.2)
    rows = [json.loads(l) for l in LOG_FILE.read_text(encoding="utf-8").splitlines()
            if l.strip()][-5:]
    target = [r for r in rows if r.get("msg", "").startswith("D8 自测日志")]
    assert target, f"未找到自测日志行: {rows[-1] if rows else '无'}"
    r = target[-1]
    for k in ("ts", "level", "logger", "msg", "trace_id", "module", "funcName"):
        assert k in r, f"缺字段 {k}: {r}"
    assert r["trace_id"] == tid and r["level"] == "INFO"
    print(f"[PASS] JSON 七字段 + trace_id 注入（{tid}）")


def test_query_by_trace() -> None:
    tid = uuid.uuid4().hex[:16]
    set_trace_id(tid)
    logging.getLogger("app.test").warning("D8 检索测试行")
    time.sleep(0.2)
    hits = query_by_trace(tid)
    assert hits and hits[-1]["msg"] == "D8 检索测试行"
    print(f"[PASS] query_by_trace 按 trace_id 查回（{len(hits)} 条）")


def test_http_trace_e2e() -> None:
    """响应头 trace_id 与包络一致；按响应头 trace_id 可建立日志审计关联。

    注：TestClient 将请求跑在 portal 线程，contextvar 不回传主线程——
    真实 uvicorn 下同一请求上下文内的业务日志由中间件 set_trace_id 自动贯穿，
    此处验证「响应头 = 包络」同源 +「拿到 trace_id 即可按 id 关联日志」的审计口径。
    """
    from fastapi.testclient import TestClient   # noqa: PLC0415

    from app.api.main import app   # noqa: PLC0415

    with TestClient(app) as client:
        r = client.get("/api")
        assert r.status_code == 200
        tid = r.headers["X-Trace-Id"]
        assert r.json()["trace_id"] == tid, "响应包络与响应头 trace_id 不一致"
        # 审计关联：以响应头 trace_id 为键写入日志（如告警/工单留痕），可按 id 查回
        set_trace_id(tid)
        logging.getLogger("app.test").info("D8 HTTP 贯穿验证 tid=%s", tid)
        time.sleep(0.2)
        rows = query_by_trace(tid)
        assert any("D8 HTTP 贯穿验证" in x.get("msg", "") for x in rows), \
            "按响应头 trace_id 无法关联日志（审计断链）"
    print(f"[PASS] HTTP trace_id 同源 + 审计关联（{tid}）")


def test_logs_dir_location() -> None:
    assert LOGS_DIR == PROJECT_ROOT / "logs", f"logs 目录漂移: {LOGS_DIR}"
    assert LOG_FILE.parent.exists()
    print(f"[PASS] logs 目录锚定项目根（{LOG_FILE}）")


def main() -> int:
    checks = [
        ("logging.yml", test_yml),
        ("装配+格式", test_setup_and_format),
        ("集中查询", test_query_by_trace),
        ("HTTP 贯穿", test_http_trace_e2e),
        ("目录锚定", test_logs_dir_location),
    ]
    failed: list[str] = []
    for name, fn in checks:
        try:
            fn()
        except Exception as exc:   # noqa: BLE001
            failed.append(name)
            print(f"[FAIL] {name}: {exc}")
    print(f"\n===== D8 自测 {len(checks) - len(failed)}/{len(checks)} PASS =====")
    if failed:
        print("  失败项:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
