"""Prometheus 指标暴露（P5-W2/D6 · M5.2）

职责：进程内 Prometheus 指标注册与打点，供 `/metrics` 端点抓取。

指标清单（plan/Phase 5 §5.2.1，在线部分；资源类由监控栈抓取）：
  推理   auscult_node_duration_ms{node}          LangGraph 节点耗时直方图
         auscult_http_requests_total{method,path,status}
         auscult_http_request_duration_ms{path}
  路由   auscult_routes_total{route}             finalize/degrade/escalate_cloud/human_review
         auscult_diagnosis_confidence            置信度分布直方图
  审核   auscult_review_duration_ms{status}
         auscult_review_timeout_total{kind}      notify_4h / degrade_24h
  检索   auscult_retrieval_duration_ms{channel}  dense/sparse/graph/total
  工具   auscult_tool_calls_total{tool,status}   ok/error/empty
  预算   auscult_cloud_budget_used_ratio         云端日预算消耗比（0-1，渲染时刷新）

与 MetricsCollector（JSONL 快照）并行：MetricsCollector.record_* 同步调用本模块
镜像打点，两路输出不互斥。历史 JSONL 仪表盘不受影响。

对应交付物：plan/Phase 5 §5.2 / D6
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# ---------------------------------------------------------------- 指标定义

NODE_DURATION = Histogram(
    "auscult_node_duration_ms", "LangGraph 节点耗时（毫秒）",
    ["node"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000),
)
HTTP_REQUESTS = Counter(
    "auscult_http_requests_total", "HTTP 请求总数",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "auscult_http_request_duration_ms", "HTTP 请求耗时（毫秒）",
    ["path"],
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)
ROUTES = Counter(
    "auscult_routes_total", "诊断条件路由结果计数",
    ["route"],
)
CONFIDENCE = Histogram(
    "auscult_diagnosis_confidence", "诊断置信度分布",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0),
)
REVIEW_DURATION = Histogram(
    "auscult_review_duration_ms", "人工审核时长（毫秒）",
    ["status"],
    buckets=(1000, 10000, 60000, 300000, 3600000, 7200000, 14400000),
)
REVIEW_TIMEOUT = Counter(
    "auscult_review_timeout_total", "审核超时事件计数",
    ["kind"],   # notify_4h / degrade_24h
)
RETRIEVAL_DURATION = Histogram(
    "auscult_retrieval_duration_ms", "检索通道耗时（毫秒）",
    ["channel"],   # dense / sparse / graph / total
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500),
)
TOOL_CALLS = Counter(
    "auscult_tool_calls_total", "工具调用计数",
    ["tool", "status"],   # status: ok / error / empty
)
CLOUD_BUDGET_RATIO = Gauge(
    "auscult_cloud_budget_used_ratio", "云端日预算消耗比（0-1）",
)
RECONCILE_DIFF = Gauge(
    "auscult_reconcile_diff", "存储对账差异数（reconcile.py 推送，>0 触发 Critical 告警）",
)
CHECKPOINT_KEYS = Gauge(
    "auscult_checkpoint_keys", "LangGraph checkpoint key 数（checkpointer 清理策略观测）",
)
CACHE_OPS = Counter(
    "auscult_cache_ops_total", "Redis 缓存层操作计数（P7）",
    ["op", "result"],   # op: get/set/del/set_nx；result: hit/miss/ok/error/skip/blocked
)
AUTO_TRIGGER = Counter(
    "auscult_auto_trigger_total", "告警自动触发计数（P7）",
    ["result"],   # started / skipped / error / disabled
)
NEEDS_HUMAN = Counter(
    "auscult_needs_human_total", "转人工审核的原因计数（E4/E5 可观测）",
    ["reason"],   # needs_human（模型主动求助）/ risk_high（风险等级高）
)
DEVICE_ID_SCHEME_MISMATCH = Counter(
    "auscult_device_id_scheme_mismatch_total",
    "工具层入参编号与库内口径不一致的调用计数（ISS-056 映射退场判据）",
    ["direction"],   # short_input：canonical 模式收到短编号 / canonical_input：legacy 模式收到规范编号
)

# ---------------------------------------------------------------- 打点辅助

def observe_node(node: str, duration_ms: float) -> None:
    NODE_DURATION.labels(node=node).observe(max(duration_ms, 0.0))


def observe_http(method: str, path: str, status: int, duration_ms: float) -> None:
    HTTP_REQUESTS.labels(method=method, path=path, status=str(status)).inc()
    HTTP_DURATION.labels(path=path).observe(max(duration_ms, 0.0))


def inc_route(route: str) -> None:
    ROUTES.labels(route=route).inc()


def observe_confidence(confidence: float) -> None:
    CONFIDENCE.observe(min(max(confidence, 0.0), 1.0))


def observe_review(status: str, duration_ms: float) -> None:
    REVIEW_DURATION.labels(status=status).observe(max(duration_ms, 0.0))


def inc_review_timeout(kind: str) -> None:
    REVIEW_TIMEOUT.labels(kind=kind).inc()


def observe_retrieval(channel: str, duration_ms: float) -> None:
    RETRIEVAL_DURATION.labels(channel=channel).observe(max(duration_ms, 0.0))


def inc_tool_call(tool: str, status: str = "ok") -> None:
    TOOL_CALLS.labels(tool=tool, status=status).inc()


def inc_cache(op: str, result: str) -> None:
    CACHE_OPS.labels(op=op, result=result).inc()


def inc_auto_trigger(result: str) -> None:
    AUTO_TRIGGER.labels(result=result).inc()


def inc_needs_human(reason: str) -> None:
    """转人工审核原因打点：区分「模型主动求助」与「风险等级高」。

    动机（E4 运维缺口）：若模型学会"拿不准就求助"（尤其 7B），人工审核量会静默
    上涨——只有把两者分开计数，才能从 `auscult_needs_human_total{reason=...}`
    的占比变化里提前发现，而不是等审核工单积压。
    """
    NEEDS_HUMAN.labels(reason=reason).inc()


def inc_device_id_mismatch(direction: str) -> None:
    """设备编号口径漂移打点（ISS-056 映射退场判据）。

    动机：`storage_id()` 兼容层什么时候能删，不能靠"感觉该删了"。两类方向都为 0
    （连续一周）才说明所有调用方都已跟上迁移；否则删掉就是让历史调用方静默查空。
    """
    DEVICE_ID_SCHEME_MISMATCH.labels(direction=direction).inc()


def refresh_budget_ratio() -> None:
    """渲染 /metrics 前刷新预算 Gauge（Redis 不可达时保持上次值，不抛错）。"""
    try:
        from ..router.budget import budget_status   # noqa: PLC0415
        st = budget_status()
        count, limit = st.get("count", -1), st.get("limit", 0)
        CLOUD_BUDGET_RATIO.set(count / limit if count >= 0 and limit > 0 else 0.0)
    except Exception:   # noqa: BLE001 — 指标刷新失败不影响业务
        pass


def render() -> tuple[bytes, str]:
    """生成 /metrics 响应体（含预算刷新）。"""
    refresh_budget_ratio()
    return generate_latest(), CONTENT_TYPE_LATEST
