"""escalate_cloud 节点（D14 · M3.3）

云端升级：本地置信度 ∈ [0.50, 0.75) 时，调用 CloudRouter 将脱敏后的上下文
转发至云端 Qwen/Qwen3.8-27B 做二次诊断，覆盖本地结论。

失败（超时/不可达/JSON 解析失败）→ degrade_reason="cloud_unavailable"，
保留本地诊断结论，由 finalize 输出降级报告。

对应交付物：plan/Phase 3 §三.3 / §五 D14 / §六.4
超时预算：20s（含网络 + 推理）
"""

from __future__ import annotations

from typing import Any

from ...router.cloud import CloudRouter
from ..state import DiagnosisState

_router: CloudRouter | None = None


def _get_router() -> CloudRouter:
    """惰性单例（CloudRouter 无状态，可复用）。"""
    global _router
    if _router is None:
        _router = CloudRouter()
    return _router


def escalate_cloud(state: DiagnosisState) -> dict[str, Any]:
    """云端升级节点。

    输入: state（diagnose 后的完整状态，含本地诊断 + 证据 + 传感器 + 图谱 + 工单）
    输出: 成功 → {diagnosis, root_causes, suggestions, confidence,
                  confidence_breakdown, risk_level, escalate_cloud: True}
          失败 → {degrade_reason, escalate_cloud: True, errors}
    """
    router = _get_router()
    return router.escalate(state)
