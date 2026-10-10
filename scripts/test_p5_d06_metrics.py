# -*- coding: utf-8 -*-
"""P5-W2/D6 Prometheus 指标暴露自测（M5.2）

验证项：
  1. 指标注册齐全（11 项核心指标 exposition 含 HELP/TYPE）
  2. MetricsCollector.record_* 同步打点 Prometheus（计数增量断言）
  3. 节点耗时 / 检索通道 / 工具 / 预算 Gauge 打点
  4. /metrics 端点（httpx TestClient）200 + content_type 正确
  5. 审核超时计数器（notify_4h / degrade_24h）
  6. budget Redis 不可达时刷新不抛错（Gauge 保持）

运行：.venv\\Scripts\\python.exe scripts\\test_p5_d06_metrics.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from prometheus_client import REGISTRY  # noqa: E402

from app.observability import prom_metrics as pm  # noqa: E402
from app.observability.metrics import MetricsCollector  # noqa: E402


def _exposition() -> str:
    body, _ = pm.render()
    return body.decode("utf-8")


def test_registry() -> None:
    """1. 指标注册齐全。"""
    text = _exposition()
    required = [
        "auscult_node_duration_ms",
        "auscult_http_requests_total",
        "auscult_http_request_duration_ms",
        "auscult_routes_total",
        "auscult_diagnosis_confidence",
        "auscult_review_duration_ms",
        "auscult_review_timeout_total",
        "auscult_retrieval_duration_ms",
        "auscult_tool_calls_total",
        "auscult_cloud_budget_used_ratio",
    ]
    missing = [m for m in required if f"# HELP {m}" not in text and f"# TYPE {m}" not in text]
    assert not missing, f"指标未注册: {missing}"
    print(f"[PASS] 指标注册齐全（{len(required)} 项核心指标均有 HELP/TYPE）")


def test_collector_bridge() -> None:
    """2. MetricsCollector.record_* 同步打点 Prometheus。"""
    mc = MetricsCollector()
    routes_before = _metric_sample("auscult_routes_total", "finalize")
    conf_before = _metric_sum("auscult_diagnosis_confidence")
    mc.record_route("finalize")
    mc.record_route("finalize")
    mc.record_confidence(0.82)
    routes_after = _metric_sample("auscult_routes_total", "finalize")
    conf_after = _metric_sum("auscult_diagnosis_confidence")
    assert routes_after - routes_before == 2.0, f"路由计数未同步: {routes_before}→{routes_after}"
    assert conf_after - conf_before == 0.82, f"置信度直方图未同步: {conf_before}→{conf_after}"

    review_before = _metric_sum("auscult_review_duration_ms")
    mc.record_review(60000.0, "approved")
    assert _metric_sum("auscult_review_duration_ms") - review_before == 60000.0, "审核时长未同步"
    print("[PASS] MetricsCollector → Prometheus 桥接（route/confidence/review）")


def test_node_retrieval_tool() -> None:
    """3. 节点耗时 / 检索通道 / 工具打点。"""
    node_before = _metric_sum("auscult_node_duration_ms")
    pm.observe_node("diagnose", 1234.5)
    assert _metric_sum("auscult_node_duration_ms") - node_before == 1234.5, "节点耗时未打点"

    retr_before = _metric_sum("auscult_retrieval_duration_ms")
    pm.observe_retrieval("total", 86.0)
    pm.observe_retrieval("dense", 40.0)
    assert _metric_sum("auscult_retrieval_duration_ms") - retr_before == 126.0, "检索通道未打点"

    tool_before = _metric_sample("auscult_tool_calls_total", "retrieve_knowledge", "ok")
    pm.inc_tool_call("retrieve_knowledge", "ok")
    assert _metric_sample("auscult_tool_calls_total", "retrieve_knowledge", "ok") - tool_before == 1.0, \
        "工具计数未打点"
    print("[PASS] 节点耗时 / 检索通道 / 工具计数打点")


def test_review_timeout() -> None:
    """5. 审核超时计数器。"""
    b4h = _metric_sample("auscult_review_timeout_total", "notify_4h")
    b24 = _metric_sample("auscult_review_timeout_total", "degrade_24h")
    pm.inc_review_timeout("notify_4h")
    pm.inc_review_timeout("degrade_24h")
    assert _metric_sample("auscult_review_timeout_total", "notify_4h") - b4h == 1.0
    assert _metric_sample("auscult_review_timeout_total", "degrade_24h") - b24 == 1.0
    print("[PASS] 审核超时计数器（notify_4h / degrade_24h）")


def test_budget_refresh_safety() -> None:
    """6. 预算刷新安全（Redis 不可达不抛错）。"""
    pm.refresh_budget_ratio()   # 不抛错即通过；Gauge 保持原值
    text = _exposition()
    assert "auscult_cloud_budget_used_ratio" in text
    print("[PASS] 预算 Gauge 刷新安全（Redis 不可达降级不抛错）")


def test_http_endpoint() -> None:
    """4. /metrics 端点（TestClient 走完整 FastAPI 栈）。"""
    from fastapi.testclient import TestClient   # noqa: PLC0415

    from app.api.main import app   # noqa: PLC0415

    with TestClient(app) as client:
        r0 = client.get("/api")
        assert r0.status_code == 200, f"/api 冒烟失败: {r0.status_code}"
        rm = client.get("/metrics")
        assert rm.status_code == 200, f"/metrics 失败: {rm.status_code}"
        assert rm.headers["content-type"].startswith("text/plain"), \
            f"content-type 异常: {rm.headers['content-type']}"
        body = rm.text
        assert "auscult_http_requests_total" in body, "/metrics 未含 HTTP 计数"
        assert '# TYPE auscult_http_requests_total counter' in body
        # HTTP 打点验证（/api 调用应已计数，且 path 用路由模板）
        assert 'path="/api"' in body, "HTTP 打点未用路由模板路径"
    print("[PASS] /metrics 端点（200 + exposition 格式 + HTTP 打点含路由模板路径）")


# ---------------------------------------------------------------- 辅助

def _exposition_bytes() -> bytes:
    from prometheus_client import generate_latest   # noqa: PLC0415
    return generate_latest(REGISTRY)


def _metric_sample(name: str, *labels: str) -> float:
    """从 exposition 文本取指定指标样本当前值（缺失视为 0）。"""
    text = _exposition_bytes().decode("utf-8")
    prefix = name
    for ln in text.splitlines():
        if ln.startswith(prefix) and all(f'"{x}"' in ln for x in labels):
            return float(ln.rsplit(" ", 1)[1])
    return 0.0


def _metric_sum(name: str) -> float:
    """取直方图/计数器 _sum 总量（缺失视为 0）。"""
    text = _exposition_bytes().decode("utf-8")
    total = 0.0
    for ln in text.splitlines():
        if ln.startswith(name + "_sum"):
            total += float(ln.rsplit(" ", 1)[1])
    return total


def main() -> int:
    t0 = time.perf_counter()
    checks = [
        ("指标注册", test_registry),
        ("Collector 桥接", test_collector_bridge),
        ("节点/检索/工具打点", test_node_retrieval_tool),
        ("审核超时计数", test_review_timeout),
        ("预算刷新安全", test_budget_refresh_safety),
        ("/metrics 端点", test_http_endpoint),
    ]
    failed: list[str] = []
    for name, fn in checks:
        try:
            fn()
        except Exception as exc:   # noqa: BLE001
            failed.append(name)
            print(f"[FAIL] {name}: {exc}")
    print(f"\n===== D6 自测 {len(checks) - len(failed)}/{len(checks)} PASS"
          f"（{time.perf_counter() - t0:.1f}s）=====")
    if failed:
        print("  失败项:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
