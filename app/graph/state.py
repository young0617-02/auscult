"""DiagnosisState — LangGraph 状态类型（Pydantic）

对应交付物：plan/Phase 3 §三.4 State 定义
设计约束（plan §三.4）：
  - 每步经 Pydantic 校验；校验失败写 errors 并触发重试/降级
  - 节点只返回增量 dict（LangGraph 合并），异常写 errors 而非抛出
  - Annotated[list, add] 字段为追加语义（节点返回增量追加到列表）
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- 子类型

class AlarmEvent(BaseModel):
    """告警事件（对齐 alarm_engine.py 的 AlarmEvent 结构）。"""
    alarm_id: str = ""
    device_id: str = ""
    metric: str = ""
    value: float = 0.0
    baseline: float | None = None
    severity: str = "medium"          # high / medium / low
    ts: int = 0                      # epoch ms
    rule_id: str | None = None
    dedup_count: int = 0


class EvidenceItem(BaseModel):
    """证据条目（对齐 retrieve_knowledge EvidencePackage.items）。"""
    chunk_id: str = ""
    text: str = ""
    score: float = 0.0
    routes: list[str] = Field(default_factory=list)
    source_type: str = "knowledge"  # knowledge / sensor / graph / maintenance


class GraphPath(BaseModel):
    """图谱路径。"""
    nodes: list[str] = Field(default_factory=list)
    edges: list[str] = Field(default_factory=list)
    description: str = ""


class WorkOrder(BaseModel):
    """工单记录（对齐 work_orders 表）。"""
    order_id: str = ""
    device_id: str = ""
    fault: str = ""
    action: str = ""
    result: str | None = None
    created_at: str | None = None


class RootCause(BaseModel):
    """根因（对齐 plan §6.2 诊断输出）。"""
    cause: str = ""
    citations: list[str] = Field(default_factory=list)
    confidence_hint: float = 0.0


class Suggestion(BaseModel):
    """建议（对齐 plan §6.2 诊断输出）。"""
    action: str = ""
    citations: list[str] = Field(default_factory=list)
    risk: str = "low"               # low / medium / high


# ---------------------------------------------------------------- 全局状态

class DiagnosisState(BaseModel):
    """LangGraph 全局状态（plan §3.4）。

    Annotated[list, add] 字段为追加语义：节点返回的增量列表会被追加到现有列表，
    而非覆盖。其余字段为覆盖语义（节点返回的新值替换旧值）。
    """
    model_config = {"arbitrary_types_allowed": True}

    # 输入
    alarm: AlarmEvent | None = None
    thread_id: str = ""

    # 运行态
    sensor_report: dict | None = None
    evidence: Annotated[list[EvidenceItem], add] = Field(default_factory=list)
    graph_paths: Annotated[list[GraphPath], add] = Field(default_factory=list)
    work_orders: Annotated[list[WorkOrder], add] = Field(default_factory=list)
    diagnosis: str | None = None
    root_causes: Annotated[list[RootCause], add] = Field(default_factory=list)
    suggestions: Annotated[list[Suggestion], add] = Field(default_factory=list)
    confidence: float = 0.0
    confidence_breakdown: dict = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"] = "low"

    # 控制
    retry_count: int = 0
    escalate_cloud: bool = False
    degrade_reason: str | None = None
    human_review: dict | None = None

    # 合规拒答/澄清（P7 · 2026-10-21）：Agent 按规则 6a/6b 只回文字时置位。
    # 语义：这是**正确行为**（不是解析失败），路由应直达 finalize，不重试、不降级。
    # 形如 {"kind": "clarification"|"refusal", "reason": "..."}
    refusal: dict | None = None

    # Agent 轨迹（P7 · AUSCULT_DIAGNOSIS_MODE=agent 时逐轮记录工具调用；
    # 追加语义，dict 载荷对 PostgresSaver msgpack 友好，见 p7 设计文档 §五）
    agent_steps: Annotated[list[dict], add] = Field(default_factory=list)

    # 主动求助契约（2026-10-22 · 评审增量 E4）：Agent 收口 JSON 可置 needs_human 并
    # 给出 human_reason（如证据互相矛盾/关键测点缺失/需现场确认）。语义 = 「结论需人定夺」，
    # 一旦置真：risk_level 强制 high → 复用既有 human_review interrupt（不新增中断类型），
    # 路由也在 confidence 判定之前直达 human_review（低置信度另有 degrade/escalate 语义）。
    needs_human: bool = False
    human_reason: str | None = None

    # 未收敛标记（2026-10-22 · 评审增量 E5）：Agent 烧完 max_steps 仍在调工具、被强制收口。
    # 语义 = 模型在本任务上**没有自主收敛**（与低置信度不同：它可能给出了一个看着不错的
    # 结论，但是"拖"出来的）。与 E2 同型思路：把失败信号前移成路由信号，不等 confidence
    # 被磨下去——提前升级云端做二次裁决（云端会拿到完整轨迹，见 E1）。
    not_converged: bool = False

    # 参数/白名单拦截计数（2026-10-22 · 评审增量 E2）：Agent 循环内工具调用被
    # `validate_tool_args` 或白名单拒绝的次数（**不含**写操作护栏——那是安全拒绝，
    # 不是"模型不懂领域语义"）。≥2 说明模型对当前任务域存在系统性理解偏差，
    # 路由据此**提前**升级云端兜底，不必等 confidence 掉到阈值（外部评审建议，
    # 见 Material/05-评审回应.md）。
    tool_arg_rejections: int = 0

    # 产出
    report_id: str | None = None
    errors: Annotated[list[dict], add] = Field(default_factory=list)
