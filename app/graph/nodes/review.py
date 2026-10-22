"""human_review 审核节点（D16-D17 · M3.4）

高风险确定性规则判定 + interrupt() 审核节点 + 审核状态机。

职责：
  1. 用 `configs/risk_rules.yml` 的关键词/操作类型**确定性规则**检查诊断结论
     和建议（**不依赖 LLM**）；
  2. 构造审核 payload（报告预览 + 风险等级 + 证据 + 规则命中详情）；
  3. 调用 `interrupt()` 挂起流程，等待人工 `resume({action, comment, reviewer_id})`；
  4. **审核状态机**（D17）：pending → approved / rejected / timeout
     - approved → 正常通过到 finalize
     - rejected → degrade_reason="review_rejected"，仍输出报告（带降级标记）
     - timeout → degrade_reason="review_timeout"，流程不挂起（D18 触发）

对应交付物：plan/Phase 3 §三.4 / §五 D16-D17 / §六.5
D18 待接入：4h 通知 / 24h 超时触发 / 并发锁 / 职责分离
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from langgraph.types import interrupt

from ...observability import prom_metrics as pm
from ..state import DiagnosisState

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RISK_RULES_PATH = PROJECT_ROOT / "configs" / "risk_rules.yml"

# ---------------------------------------------------------------- 审核状态机（D17）

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
TIMEOUT = "timeout"

_VALID_ACTIONS = {APPROVED, REJECTED, TIMEOUT}


_rules_cache: dict | None = None


def _load_rules() -> dict:
    """惰性加载 risk_rules.yml（进程内缓存）。"""
    global _rules_cache
    if _rules_cache is None:
        with open(RISK_RULES_PATH, "r", encoding="utf-8") as f:
            _rules_cache = yaml.safe_load(f)
    return _rules_cache


# ---------------------------------------------------------------- 确定性规则判定

def evaluate_high_risk(state: DiagnosisState) -> dict[str, Any]:
    """确定性规则判定：检查诊断/建议中是否含高风险关键词或操作类型。

    不依赖 LLM。返回 {needs_review, keywords_hit, operations_hit, reasons}
    """
    rules = _load_rules()
    keywords = rules.get("high_risk_keywords", [])
    operations = rules.get("high_risk_operations", [])

    # 汇总所有待检查文本（诊断结论 + 根因 + 建议）
    texts: list[str] = []
    if state.diagnosis:
        texts.append(state.diagnosis)
    for rc in state.root_causes:
        if rc.cause:
            texts.append(rc.cause)
    for s in state.suggestions:
        if s.action:
            texts.append(s.action)
    combined = " ".join(texts)

    keywords_hit = [kw for kw in keywords if kw in combined]
    operations_hit = [op for op in operations if op in combined]

    policy = rules.get("review_policy", {})
    always_high = policy.get("always_interrupt_when_high", True)
    needs_review = bool(keywords_hit or operations_hit)
    # E4（2026-10-22）：模型主动求助（needs_human）→ 必须进人工审核，不受关键词表限制
    if state.needs_human:
        needs_review = True
    if always_high and state.risk_level == "high":
        needs_review = True

    reasons: list[str] = []
    if state.needs_human:
        reasons.append(f"模型主动求助: {state.human_reason or '未说明原因'}")
    if keywords_hit:
        reasons.append(f"关键词命中: {', '.join(keywords_hit)}")
    if operations_hit:
        reasons.append(f"高风险操作: {', '.join(operations_hit)}")
    if not reasons and needs_review:
        reasons.append("risk_level=high（LLM 判定，保守审核）")

    return {
        "needs_review": needs_review,
        "keywords_hit": keywords_hit,
        "operations_hit": operations_hit,
        "reasons": reasons,
    }


# ---------------------------------------------------------------- payload 构造

def _build_review_payload(state: DiagnosisState, risk_eval: dict) -> dict[str, Any]:
    """构造审核 payload（供 interrupt 展示给审核人）。"""
    return {
        "thread_id": state.thread_id,
        "review_status": PENDING,
        "risk_level": state.risk_level,
        "diagnosis": state.diagnosis or "(无诊断结论)",
        "root_causes": [
            {"cause": rc.cause, "citations": rc.citations}
            for rc in state.root_causes
        ],
        "suggestions": [
            {"action": s.action, "risk": s.risk, "citations": s.citations}
            for s in state.suggestions
        ],
        "evidence_count": len(state.evidence),
        "confidence": state.confidence,
        # E4：模型主动求助时把「需要人做什么」原样带给审核人
        "needs_human": state.needs_human,
        "human_reason": state.human_reason,
        "risk_eval": risk_eval,
        "question": ("模型主动请求人工介入" if state.needs_human
                     else "高风险诊断，需人工审核"),
        "resume_hint": 'resume({action: "approved"|"rejected", comment, reviewer_id})',
    }


# ---------------------------------------------------------------- resume 校验（D17）

def _validate_resume(decision: Any) -> dict[str, Any]:
    """校验 resume 值，返回规范化的决策 dict + errors。

    合法格式: {action: "approved"|"rejected"|"timeout", comment?: str, reviewer_id?: str}
    timeout 可无 reviewer_id（系统触发）。
    """
    errors: list[dict[str, str]] = []
    if not isinstance(decision, dict):
        return {"action": REJECTED,
                "errors": [{"node": "human_review", "code": "E_BAD_RESUME",
                             "msg": f"resume 值非 dict: {type(decision).__name__}"}]}

    action = decision.get("action", "")
    if action not in _VALID_ACTIONS:
        errors.append({"node": "human_review", "code": "E_INVALID_ACTION",
                       "msg": f"action 非法: {action}，应为 {sorted(_VALID_ACTIONS)}"})
        action = REJECTED

    reviewer_id = decision.get("reviewer_id", "")
    if action in (APPROVED, REJECTED) and not reviewer_id:
        errors.append({"node": "human_review", "code": "E_NO_REVIEWER",
                       "msg": f"{action} 需提供 reviewer_id"})

    return {"action": action,
            "comment": decision.get("comment", ""),
            "reviewer_id": reviewer_id,
            "errors": errors}


def should_auto_approve(state: DiagnosisState, risk_eval: dict[str, Any]) -> bool:
    """是否可跳过 `interrupt`（仅当确定性规则判定"确无高风险"时）。

    2026-10-22（Must#9 绕过路径③）：原判据只看 `risk_eval["needs_review"]`，而它受
    `configs/risk_rules.yml` 的 `always_interrupt_when_high` 开关影响 —— 该开关一旦被改成
    false（配置漂移/误改），`risk_level=high` 就会落到这里**自动通过**，等于"改一行 YAML
    就能绕过强制审核"。此处把 `risk_level=high` 与 `needs_human` 作为**代码级硬约束**叠加，
    使该行为无法由配置关闭（配置只能让审核更严，不能更松）。
    """
    return (
        not risk_eval["needs_review"]
        and state.risk_level != "high"
        and not state.needs_human
    )


# ---------------------------------------------------------------- human_review 节点

def human_review(state: DiagnosisState) -> dict[str, Any]:
    """高风险审核节点（D16-D17）。

    流程：
      1. 确定性规则判定（evaluate_high_risk）
      2. 如果 needs_review → interrupt() 挂起，等待 resume
      3. resume 后按状态机处理：
         - approved → 正常通过
         - rejected → degrade_reason="review_rejected" + errors
         - timeout → degrade_reason="review_timeout" + errors

    resume 格式: {action: "approved"|"rejected"|"timeout", comment: str, reviewer_id: str}
    """
    risk_eval = evaluate_high_risk(state)

    if should_auto_approve(state, risk_eval):
        # 确定性规则判定无需审核（安全阀：LLM 误标 high 但无实际高风险操作）。
        # 注意：`risk_level=high` / `needs_human` 永不走这里（见 should_auto_approve 注释）。
        return {"human_review": {"decision": "auto_approved",
                                  "status": "auto_approved",
                                  "reason": "无高风险关键词/操作命中"}}

    # E4/E5 可观测（2026-10-22）：转人工的原因分开计数——若"模型主动求助"占比
    # 异常上升，说明模型在该域退化成"拿不准就上交"，审核量会静默积压。
    pm.inc_needs_human("needs_human" if state.needs_human else "risk_high")

    # 构造 payload 并挂起
    payload = _build_review_payload(state, risk_eval)
    decision = interrupt(payload)

    # D17: 校验 resume 值
    validated = _validate_resume(decision)
    action = validated["action"]
    errors = validated.get("errors", [])

    # 状态机转换
    if action == APPROVED:
        review_result = {
            "status": APPROVED,
            "reviewer_id": validated["reviewer_id"],
            "comment": validated["comment"],
            "decision": decision,
            "risk_eval": risk_eval,
        }
    elif action == REJECTED:
        review_result = {
            "status": REJECTED,
            "reviewer_id": validated["reviewer_id"],
            "comment": validated["comment"],
            "decision": decision,
            "risk_eval": risk_eval,
        }
        result: dict[str, Any] = {
            "human_review": review_result,
            "degrade_reason": "review_rejected",
        }
        if errors:
            result["errors"] = errors
        return result
    else:  # TIMEOUT
        review_result = {
            "status": TIMEOUT,
            "comment": validated["comment"] or "审核超时（24h），自动降级",
            "decision": decision,
            "risk_eval": risk_eval,
        }
        result = {
            "human_review": review_result,
            "degrade_reason": "review_timeout",
        }
        if errors:
            result["errors"] = errors
        return result

    result = {"human_review": review_result}
    if errors:
        result["errors"] = errors
    return result
