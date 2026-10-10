/** 报告相关 TS 类型（对齐 app/report/idempotency.py state_to_payload + routes/reports.py 契约） */

/** 审核状态（review_status 列） */
export type ReviewStatus =
  | "pending"        // 前端语义占位（后端 NULL），详情/列表统一归一
  | "approved"
  | "rejected"
  | "timeout"
  | "auto_approved";

export const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: "待审核",
  approved: "已通过",
  rejected: "已驳回",
  timeout: "已超时",
  auto_approved: "自动通过",
};

export const REVIEW_STATUS_TONE: Record<ReviewStatus, string> = {
  pending: "border-risk-medium-edge bg-risk-medium-surface text-risk-medium-text",
  approved: "border-risk-low-edge bg-risk-low-surface text-risk-low-text",
  rejected: "border-risk-high-edge bg-risk-high-surface text-risk-high-text",
  timeout: "border-risk-high-edge bg-risk-high-surface text-risk-high-text",
  auto_approved: "border-edge-subtle bg-surface-raised text-fg-secondary",
};

/** 根因条目（payload.root_causes） */
export interface RootCause {
  cause: string;
  citations: string[];
  confidence_hint?: number;
}

/** 建议条目（payload.suggestions） */
export interface Suggestion {
  action: string;
  citations: string[];
  risk: string;   // low / medium / high
}

/** 审核留痕（payload.human_review） */
export interface HumanReviewRecord {
  status?: string;
  decision?: string;
  reviewer_id?: string;
  comment?: string;
  reason?: string;           // auto_approved 场景
  risk_eval?: {
    keywords_hit?: string[];
    operations_hit?: string[];
    reasons?: string[];
  };
}

/** 证据原文条目（payload.evidence，P5-Q8 补持久化；历史报告无此字段） */
export interface EvidenceRecord {
  chunk_id: string;
  text: string;
  score: number;
  source_type: string;   // knowledge / sensor / graph / maintenance
  routes?: string[];
}

/** 置信度四分量（payload.confidence_breakdown，P5-Q8 补持久化） */
export interface ConfidenceBreakdownData {
  retrieval: number;     // 检索覆盖 ×0.35
  sensor: number;        // 传感器一致性 ×0.20
  graph: number;         // 图谱支撑 ×0.15
  self: number;          // 模型自评 ×0.30
}

/** 报告 payload 主体（reports.payload JSONB） */
export interface ReportPayload {
  diagnosis: string | null;
  root_causes: RootCause[];
  suggestions: Suggestion[];
  confidence: number;
  confidence_breakdown?: ConfidenceBreakdownData;  // P5-Q8
  evidence?: EvidenceRecord[];                     // P5-Q8
  risk_level: string;
  escalate_cloud: boolean;
  human_review: HumanReviewRecord | null;
  degrade_reason: string | null;
  errors: { node?: string; code?: string; msg?: string }[];
}

/** GET /api/reports/{id} 返回 */
export interface ReportDetailData {
  report_id: string;
  idempotency_key: string;
  thread_id: string;
  payload: ReportPayload;
  risk_level: string;
  confidence: number | string;   // psycopg Decimal 序列化为字符串，前端 Number() 归一
  review_status: string | null;  // null = pending
  degrade_reason: string | null;
  created_at: string | null;
}

/** GET /api/reports 列表条目 */
export interface ReportListItem {
  report_id: string;
  thread_id: string;
  risk_level: string;
  confidence: number | string;
  review_status: string | null;
  degrade_reason: string | null;
  created_at: string;
  diagnosis: string | null;      // payload->>'diagnosis'
}

export interface ReportListData {
  items: ReportListItem[];
  total: number;
  page: number;
  size: number;
}

export interface ReportQuery {
  page: number;
  size: number;
  status?: string;   // pending/approved/rejected/timeout/auto_approved
  risk?: string;     // low/medium/high
}

/** 归一：review_status null → "pending"（前端语义占位） */
export function normalizeReviewStatus(s: string | null): ReviewStatus {
  if (s === null) return "pending";
  return (["approved", "rejected", "timeout", "auto_approved"].includes(s) ? s : "pending") as ReviewStatus;
}

export const RISK_LABEL: Record<string, string> = { low: "低", medium: "中", high: "高" };
