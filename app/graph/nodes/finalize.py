"""finalize 节点（D10）

证据校验 + 组装最终状态 + 幂等键。
写操作移出图内（plan §六.2）：本节点不直接写 PG，仅生成 report_id（幂等键），
由 API 层（Phase 4）消费 report_id 做幂等写入。

幂等键: sha256(thread_id:citations:risk_level)[:16]
  - 相同 thread + 相同引用集 + 相同风险等级 → 相同 report_id（幂等）

对应交付物: plan/Phase 3 §三.2 / §五 D10 / §六.2
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..state import DiagnosisState


def _validate_citations(state: DiagnosisState) -> list[dict[str, str]]:
    """证据校验：检查诊断/根因引用是否有效。返回 warnings 列表。"""
    warnings: list[dict[str, str]] = []

    # 诊断结论非空
    if not state.diagnosis:
        warnings.append({"node": "finalize", "code": "W_NO_DIAGNOSIS",
                         "msg": "诊断结论为空"})

    # 根因引用的 chunk_id 应在 evidence 中存在
    valid_ids = {ev.chunk_id for ev in state.evidence if ev.chunk_id}
    for rc in state.root_causes:
        for cite in rc.citations:
            if cite and cite not in valid_ids:
                warnings.append({"node": "finalize", "code": "W_INVALID_CITATION",
                                 "msg": f"根因引用无效 chunk_id: {cite}"})

    # 建议引用的 chunk_id 应在 evidence 中存在
    for s in state.suggestions:
        for cite in s.citations:
            if cite and cite not in valid_ids:
                warnings.append({"node": "finalize", "code": "W_INVALID_CITATION",
                                 "msg": f"建议引用无效 chunk_id: {cite}"})

    return warnings


def _compute_idempotency_key(state: DiagnosisState) -> str:
    """幂等键: sha256(thread_id:sorted_citations:risk_level)[:16]。"""
    citations = sorted(
        c for rc in state.root_causes for c in rc.citations if c
    )
    raw = f"{state.thread_id}:{':'.join(citations)}:{state.risk_level}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def finalize(state: DiagnosisState) -> dict[str, Any]:
    """证据校验 + 组装最终状态 + 幂等键。

    输入: state（全链路执行后的完整状态）
    输出: {"report_id": "RPT-xxxx", "errors": [warnings]}
          warnings 为非阻塞校验提示（W_ 前缀），不阻止输出
    """
    warnings = _validate_citations(state)
    report_id = f"RPT-{_compute_idempotency_key(state)}"

    result: dict[str, Any] = {"report_id": report_id}
    if warnings:
        result["errors"] = warnings
    return result
