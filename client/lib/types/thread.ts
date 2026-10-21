/** 诊断线程相关 TS 类型（对齐 app/api/runner.py thread_status / diagnose.py 契约） */

export type ThreadStatus = "running" | "waiting_review" | "done" | "error";

export const THREAD_STATUS_LABEL: Record<ThreadStatus, string> = {
  running: "分析中",
  waiting_review: "待审核",
  done: "已完成",
  error: "失败",
};

/** 线程内告警上下文（severity 兼容 PG 口径 info/warning/critical 与 AlarmEvent 口径 high/medium/low） */
export interface ThreadAlarm {
  alarm_id: string;
  device_id: string;
  metric: string;
  value: number | null;
  severity: string;
  /** epoch ms */
  ts: number;
}

/** 线程元数据（客户端注册表条目；实时态由 socket 事件驱动更新） */
export interface ThreadMeta {
  thread_id: string;
  alarm: ThreadAlarm;
  status: ThreadStatus;
  nodes_done: string[];
  /** 节点完成时刻（epoch ms，由 diagnosis:progress ts×1000），推每步耗时 */
  node_ts: Record<string, number>;
  report_id: string | null;
  degrade_reason: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
}

/** chat:ask 追问条目（runner.ask_question 返回 + qa_log 留痕同形） */
export interface QaEntry {
  question: string;
  answer: string;
  citations: string[];
  user?: string;
  model?: string;
  /** epoch 秒（服务端 time.time()） */
  ts?: number;
}

/** 高风险审核 payload（nodes/review.py _build_review_payload） */
export interface ReviewPayload {
  thread_id?: string;
  review_status?: string;
  risk_level?: string;
  diagnosis?: string;
  root_causes?: { cause: string; citations: string[] }[];
  suggestions?: { action: string; risk: string; citations: string[] }[];
  evidence_count?: number;
  confidence?: number;
  question?: string;
  risk_eval?: {
    needs_review?: boolean;
    keywords_hit?: string[];
    operations_hit?: string[];
    reasons?: string[];
  };
}

/** GET /api/threads/{id} 返回（runner.thread_status） */
export interface ThreadStatusData {
  thread_id: string;
  status: ThreadStatus;
  submitter: string | null;
  alarm: ThreadAlarm | null;
  nodes_done: string[];
  report_id: string | null;
  review_payload: ReviewPayload | null;
  degrade_reason: string | null;
  qa_log: QaEntry[];
  error: string | null;
  /** epoch 秒 */
  started_at: number | null;
  finished_at: number | null;
  /** P7 Agent 循环工具调用轨迹（可选：旧缓存 payload 无此字段） */
  agent_steps?: AgentSteps;
  /** P7 合规拒答/澄清（可选：旧缓存 payload 无此字段；null = 正常诊断） */
  refusal?: RefusalInfo | null;
}

/** 合规拒答/澄清（app/graph/state.py::refusal，规则 6a/6b）。
 *  - clarification：告警缺具体设备编号，需补充信息后重发；
 *  - refusal：请求超出系统职责（改数据/现场操作/寿命预测）。
 *  两者都是**正确行为**（不重试、不降级），故不按"失败"展示。 */
export interface RefusalInfo {
  kind: "clarification" | "refusal";
  reason: string;
}

/** P7 Agent 循环单步轨迹（state.agent_steps 元素；app/graph/nodes/agent_diagnose.py）。
 *  可选：Redis 只读缓存可能留存本字段上线前的旧 payload（缺省视为无轨迹）。 */
export interface AgentStep {
  /** 第几轮工具调用（1 起） */
  step: number;
  /** 工具名；null = 步数上限后的无工具强制收口轮 */
  tool: string | null;
  ok: boolean;
  /** 模型所给参数键名（不含值，避免敏感数据入前端） */
  args_keys: string[];
  /** 该轮 LLM 调用耗时 ms */
  latency_ms: number | null;
  /** 强制收口轮标记 */
  forced_final?: boolean;
}

/** thread_status 上的 Agent 轨迹字段（registry/回退双路径均返回；旧缓存缺省 []） */
export type AgentSteps = AgentStep[];

/** GET /api/reports/{id} 返回（报告详情：M4.2 仅取 confidence/risk_level 做徽章） */
export interface ReportDetail {
  report_id: string;
  thread_id: string;
  risk_level: string;
  confidence: number;
  review_status: string | null;
  degrade_reason: string | null;
  payload: Record<string, unknown>;
}

// ---------------------------------------------------------------- 节点管线（D7）

/** 六节点主管线（build.py：START → parse_alarm → … → diagnose → 条件路由） */
export const PIPELINE_NODES = [
  { key: "parse_alarm", label: "告警解析" },
  { key: "analyze_sensor", label: "传感器分析" },
  { key: "retrieve_evidence", label: "知识检索" },
  { key: "get_history", label: "历史工单" },
  { key: "diagnose", label: "诊断推理" },
] as const;

/** 路由节点（条件路由四去向；human_review 通过后接 finalize） */
export const ROUTE_NODES: Record<string, { label: string }> = {
  escalate_cloud: { label: "云端复核" },
  degrade: { label: "降级输出" },
  human_review: { label: "人工审核" },
  finalize: { label: "报告生成" },
};
