/** 知识库相关 TS 类型（对齐 app/api/routes/knowledge.py 契约，D0-2 契约5 + D0-6 契约补丁） */

/** 文档类型（后端 _DOC_TYPES） */
export type DocType = "manual" | "work_order" | "procedure";

/** 索引状态（documents.status） */
export type DocStatus = "pending" | "indexed" | "failed";

/** 准入状态（documents.admission_status；一次性决策 pending → approved/rejected） */
export type AdmissionStatus = "pending" | "approved" | "rejected";

export const DOC_TYPE_LABEL: Record<DocType, string> = {
  manual: "手册",
  work_order: "工单",
  procedure: "规程",
};

export const DOC_STATUS_LABEL: Record<DocStatus, string> = {
  pending: "待索引",
  indexed: "已索引",
  failed: "索引失败",
};

export const DOC_STATUS_TONE: Record<DocStatus, string> = {
  pending: "border-risk-medium-edge bg-risk-medium-surface text-risk-medium-text",
  indexed: "border-risk-low-edge bg-risk-low-surface text-risk-low-text",
  failed: "border-risk-high-edge bg-risk-high-surface text-risk-high-text",
};

export const ADMISSION_LABEL: Record<AdmissionStatus, string> = {
  pending: "待准入",
  approved: "已准入",
  rejected: "已驳回",
};

export const ADMISSION_TONE: Record<AdmissionStatus, string> = {
  pending: "border-risk-medium-edge bg-risk-medium-surface text-risk-medium-text",
  approved: "border-risk-low-edge bg-risk-low-surface text-risk-low-text",
  rejected: "border-risk-high-edge bg-risk-high-surface text-risk-high-text",
};

/** GET /api/knowledge/docs 列表条目 */
export interface KnowledgeDocItem {
  doc_id: string;
  title: string;
  source: string;
  doc_type: DocType;
  device_model: string | null;
  status: DocStatus;
  admission_status: AdmissionStatus;
  created_at: string;
}

export interface KnowledgeListData {
  items: KnowledgeDocItem[];
  total: number;
  page: number;
  size: number;
}

export interface KnowledgeQuery {
  page: number;
  size: number;
  status?: DocStatus;
  doc_type?: DocType;
}

/** POST /api/knowledge/docs 上传占位请求体（仅元数据登记） */
export interface DocCreateInput {
  title: string;
  doc_type: DocType;
  source: string;
  device_model?: string | null;
  content?: string | null;
}

/** POST /api/knowledge/docs/{id}/admission 请求体 */
export interface AdmissionInput {
  action: "approve" | "reject";
  comment: string;
}

/** 未知值防御归一 */
export function normalizeDocStatus(s: string): DocStatus {
  return (["pending", "indexed", "failed"].includes(s) ? s : "pending") as DocStatus;
}

export function normalizeAdmission(s: string): AdmissionStatus {
  return (["pending", "approved", "rejected"].includes(s) ? s : "pending") as AdmissionStatus;
}
