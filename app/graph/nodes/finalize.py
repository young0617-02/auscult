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


def _normalize_cite(cite: str) -> str:
    """规范化证据引用：兼容 `chunk_id=<id>` 与纯 `<id>` 两种形态。

    与 `nodes/diagnose.py::_normalize_cite` 同口径（ diagnose 侧已先规范化一遍，
    此处兜底，防御其它来源的未规范化引用）。
    """
    c = (cite or "").strip()
    return c[len("chunk_id="):].strip() if c.startswith("chunk_id=") else c


def _validate_citations(state: DiagnosisState) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """证据校验。返回 (warnings, errors)。

    - `warnings`（W_ 前缀）：非阻塞提示；
    - `errors`（E_ 前缀）：**阻塞级** —— 引用无效时 `finalize` 不产出 `report_id`，
      而 `app/api/runner.py` 仅在 `report_id` 存在时才调 `generate_report` 落库，
      故报告不会落库 → 落实「无来源不出结论」。

    2026-10-14 修复：原实现把无效引用仅记为 `W_INVALID_CITATION`（非阻塞），
    实测导致报告带着 3 条无效引用照常定稿；同时引用格式 `chunk_id=<id>` 与
    evidence 的纯 id 不匹配，使校验恒判无效（误报）。
    """
    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    # 诊断结论非空
    if not state.diagnosis:
        warnings.append({"node": "finalize", "code": "W_NO_DIAGNOSIS",
                         "msg": "诊断结论为空"})

    # 根因/建议引用的 chunk_id 应在 evidence 中存在（规范化后比对）
    valid_ids = {ev.chunk_id for ev in state.evidence if ev.chunk_id}
    for rc in state.root_causes:
        for cite in rc.citations:
            c = _normalize_cite(cite)
            if c and c not in valid_ids:
                errors.append({"node": "finalize", "code": "E_INVALID_CITATION",
                               "msg": f"根因引用无效 chunk_id: {c}"})

    for s in state.suggestions:
        for cite in s.citations:
            c = _normalize_cite(cite)
            if c and c not in valid_ids:
                errors.append({"node": "finalize", "code": "E_INVALID_CITATION",
                               "msg": f"建议引用无效 chunk_id: {c}"})

    return warnings, errors


def _compute_idempotency_key(state: DiagnosisState) -> str:
    """幂等键: sha256(thread_id:sorted_citations:risk_level)[:16]。

    citations 取**规范化**后的值，避免 `chunk_id=` 前缀差异导致同内容不同键。
    """
    citations = sorted(
        _normalize_cite(c) for rc in state.root_causes for c in rc.citations if c
    )
    raw = f"{state.thread_id}:{':'.join(citations)}:{state.risk_level}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def finalize(state: DiagnosisState) -> dict[str, Any]:
    """证据校验 + 组装最终状态 + 幂等键。

    输入: state（全链路执行后的完整状态）
    输出（通过）: {"report_id": "RPT-xxxx", "errors": [warnings?]}
          warnings 为非阻塞校验提示（W_ 前缀）
    输出（硬校验失败）: {"report_id": None, "blocked": True,
                        "degrade_reason": "invalid_citation_blocked",
                        "errors": [E_INVALID_CITATION..., warnings...]}
          —— 不产出 report_id ⇒ runner 不会调 generate_report ⇒ **报告不落库**
    """
    warnings, errors = _validate_citations(state)

    if errors:
        # 硬校验失败：不放行定稿（"无来源不出结论"）
        return {"report_id": None, "blocked": True,
                "degrade_reason": "invalid_citation_blocked",
                "errors": errors + warnings}

    report_id = f"RPT-{_compute_idempotency_key(state)}"
    result: dict[str, Any] = {"report_id": report_id}
    if warnings:
        result["errors"] = warnings
    return result
