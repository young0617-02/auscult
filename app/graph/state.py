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

    # 产出
    report_id: str | None = None
    errors: Annotated[list[dict], add] = Field(default_factory=list)
