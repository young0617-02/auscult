"""指标打点（D22 · M3.5）

职责（plan/Phase 3 §6.7 可观测性 · 指标维度）：
  1. 节点耗时：每节点 duration_ms 列表 → P50 / P95 / P99；
  2. 置信度分布：<0.50 / 0.50–0.75 / ≥0.75 三档直方图；
  3. 云端升级率：escalate_cloud 触发 / 总路由；
  4. 降级率：degrade 触发 / 总路由；
  5. 审核覆盖率：human_review 触发 / 总路由；
  6. 审核平均时长：review duration 列表 → avg。

采集方式：
  - 手动调用 record_* 方法（节点/路由/审核）；
  - 或从 Tracer.spans 自动聚合（aggregate_from_tracer）。

输出：reports/metrics/{date}.jsonl（每次 snapshot 写一行，供仪表盘消费）。

对应交付物：plan/Phase 3 §五 D22 / §六.7
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import paths as _paths

# ---------------------------------------------------------------- 常量

METRICS_DIR = _paths.METRICS_DIR      # AUSCULT_REPORTS_DIR 可覆盖（默认 <repo>/reports/metrics）

CONFIDENCE_BINS = ("low", "medium", "high")   # <0.50, 0.50–0.75, ≥0.75
ROUTE_TARGETS = ("finalize", "degrade", "escalate_cloud", "human_review")


# ---------------------------------------------------------------- 工具函数

def _percentile(values: list[float], p: float) -> float:
    """计算百分位数（线性插值，数据量小时仍可用）。"""
    if not values:
        return 0.0
    s = sorted(values)
    idx = (len(s) - 1) * (p / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------- MetricsCollector

class MetricsCollector:
    """指标采集 + 聚合器。

    用法：
        mc = MetricsCollector()
        mc.record_node_duration("parse_alarm", 5.2)
        mc.record_confidence(0.82)
        mc.record_route("finalize")
        mc.record_review(3600.0, "approved")
        snapshot = mc.snapshot()
        mc.flush()  # 写入 JSONL
    """

    def __init__(self) -> None:
        self._node_durations: dict[str, list[float]] = {}
        self._confidences: list[float] = []
        self._routes: dict[str, int] = {t: 0 for t in ROUTE_TARGETS}
        self._review_durations: list[float] = []
        self._review_statuses: dict[str, int] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- 采集

    def record_node_duration(self, node: str, duration_ms: float) -> None:
        """记录节点执行耗时（同步 Prometheus，D6）。"""
        from . import prom_metrics   # noqa: PLC0415
        prom_metrics.observe_node(node, duration_ms)
        with self._lock:
            self._node_durations.setdefault(node, []).append(duration_ms)

    def record_confidence(self, confidence: float) -> None:
        """记录诊断置信度（同步 Prometheus，D6）。"""
        from . import prom_metrics   # noqa: PLC0415
        prom_metrics.observe_confidence(confidence)
        with self._lock:
            self._confidences.append(confidence)

    def record_route(self, target: str) -> None:
        """记录条件路由结果（finalize/degrade/escalate_cloud/human_review；同步 Prometheus，D6）。"""
        from . import prom_metrics   # noqa: PLC0415
        prom_metrics.inc_route(target)
        with self._lock:
            if target not in self._routes:
                self._routes[target] = 0
            self._routes[target] += 1

    def record_review(self, duration_ms: float, status: str) -> None:
        """记录审核完成（耗时 + 状态；同步 Prometheus，D6）。"""
        from . import prom_metrics   # noqa: PLC0415
        prom_metrics.observe_review(status, duration_ms)
        with self._lock:
            self._review_durations.append(duration_ms)
            self._review_statuses[status] = \
                self._review_statuses.get(status, 0) + 1

    # ---------------------------------------------------------------- 聚合

    def node_p50(self, node: str) -> float:
        return _percentile(self._node_durations.get(node, []), 50)

    def node_p95(self, node: str) -> float:
        """节点 P95 耗时（毫秒）。"""
        return _percentile(self._node_durations.get(node, []), 95)

    def node_p99(self, node: str) -> float:
        return _percentile(self._node_durations.get(node, []), 99)

    def node_count(self, node: str) -> int:
        return len(self._node_durations.get(node, []))

    def confidence_distribution(self) -> dict[str, int]:
        """置信度三档直方图。"""
        bins = {b: 0 for b in CONFIDENCE_BINS}
        for c in self._confidences:
            if c < 0.50:
                bins["low"] += 1
            elif c < 0.75:
                bins["medium"] += 1
            else:
                bins["high"] += 1
        return bins

    def total_routes(self) -> int:
        return sum(self._routes.values())

    def escalation_rate(self) -> float:
        """云端升级率：escalate_cloud / 总路由。"""
        total = self.total_routes()
        if total == 0:
            return 0.0
        return round(self._routes.get("escalate_cloud", 0) / total, 4)

    def degradation_rate(self) -> float:
        """降级率：degrade / 总路由。"""
        total = self.total_routes()
        if total == 0:
            return 0.0
        return round(self._routes.get("degrade", 0) / total, 4)

    def review_coverage(self) -> float:
        """审核覆盖率：human_review / 总路由。"""
        total = self.total_routes()
        if total == 0:
            return 0.0
        return round(self._routes.get("human_review", 0) / total, 4)

    def review_avg_duration(self) -> float:
        """审核平均时长（毫秒）。"""
        if not self._review_durations:
            return 0.0
        return round(sum(self._review_durations) / len(self._review_durations), 2)

    def review_status_counts(self) -> dict[str, int]:
        return dict(self._review_statuses)

    # ---------------------------------------------------------------- 快照

    def snapshot(self) -> dict[str, Any]:
        """全量指标快照（供仪表盘 / JSONL 输出）。"""
        with self._lock:
            return {
                "ts": _now_iso(),
                "nodes": {
                    node: {
                        "count": len(durs),
                        "p50_ms": _percentile(durs, 50),
                        "p95_ms": _percentile(durs, 95),
                        "p99_ms": _percentile(durs, 99),
                    }
                    for node, durs in self._node_durations.items()
                },
                "confidence_distribution": self.confidence_distribution(),
                "routes": dict(self._routes),
                "total_routes": self.total_routes(),
                "escalation_rate": self.escalation_rate(),
                "degradation_rate": self.degradation_rate(),
                "review_coverage": self.review_coverage(),
                "review_avg_duration_ms": self.review_avg_duration(),
                "review_statuses": dict(self._review_statuses),
            }

    # ---------------------------------------------------------------- 持久化

    def flush(self, path: Path | None = None) -> Path:
        """将 snapshot 追加写入 JSONL 文件。返回文件路径。"""
        snap = self.snapshot()
        target = path or METRICS_DIR / f"{date.today().isoformat()}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap, ensure_ascii=False) + "\n")
        return target

    # ---------------------------------------------------------------- Tracer 聚合

    def aggregate_from_tracer(self, tracer: Any) -> None:
        """从 D21 Tracer 的 spans 中自动聚合指标。

        - type=="span" → node_duration
        - type=="event" name=="route" → route
        - type=="event" name=="confidence" → confidence
        - type=="event" name=="review_done" → review
        """
        for record in tracer.spans:
            rtype = record.get("type")
            if rtype == "span":
                name = record.get("name", "")
                dur = record.get("duration_ms", 0.0)
                if name and dur is not None:
                    self.record_node_duration(name, dur)
            elif rtype == "event":
                name = record.get("name", "")
                if name == "route":
                    target = record.get("target", "")
                    if target:
                        self.record_route(target)
                elif name == "confidence":
                    conf = record.get("value", 0.0)
                    if conf:
                        self.record_confidence(float(conf))
                elif name == "review_done":
                    dur = record.get("duration_ms", 0.0)
                    status = record.get("status", "")
                    if dur and status:
                        self.record_review(float(dur), status)
