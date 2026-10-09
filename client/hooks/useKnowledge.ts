"use client";

/**
 * 知识库 hooks（P4-D16）：
 * - useKnowledgeDocs：GET /api/knowledge/docs 列表（30s 轮询）
 * - useDocCreate：POST /api/knowledge/docs（kb_admin；元数据登记 → pending）
 * - useDocAdmission：POST /api/knowledge/docs/{id}/admission（kb_admin；一次性准入决策）
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { post, request } from "@/lib/api";
import type {
  AdmissionInput,
  DocCreateInput,
  KnowledgeListData,
  KnowledgeQuery,
} from "@/lib/types/knowledge";

export const KNOWLEDGE_KEY = "knowledge-docs";

function buildQueryString(q: KnowledgeQuery): string {
  const sp = new URLSearchParams({ page: String(q.page), size: String(q.size) });
  if (q.status) sp.set("status", q.status);
  if (q.doc_type) sp.set("doc_type", q.doc_type);
  return sp.toString();
}

export function useKnowledgeDocs(query: KnowledgeQuery) {
  return useQuery<KnowledgeListData>({
    queryKey: [KNOWLEDGE_KEY, query],
    queryFn: () => request<KnowledgeListData>(`/api/knowledge/docs?${buildQueryString(query)}`),
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });
}

/** 上传占位（元数据登记；解析/分块/向量化由流水线推进） */
export function useDocCreate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: DocCreateInput) =>
      post<{ doc_id: string; status: string; note: string }>("/api/knowledge/docs", input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [KNOWLEDGE_KEY] });
      toast.success("文档已登记", { description: "状态 pending；准入审核通过后由流水线索引" });
    },
    onError: (e) => toast.error("登记失败", { description: (e as Error).message }),
  });
}

/** 准入审核（一次性决策；重复提交后端返回 E_CONFLICT） */
export function useDocAdmission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ docId, input }: { docId: string; input: AdmissionInput }) =>
      post<{ doc_id: string; admission_status: string }>(
        `/api/knowledge/docs/${docId}/admission`,
        input,
      ),
    onSuccess: (d) => {
      void qc.invalidateQueries({ queryKey: [KNOWLEDGE_KEY] });
      toast.success(d.admission_status === "approved" ? "已准入" : "已驳回", {
        description: "决策已留痕 knowledge_versions",
      });
    },
    onError: (e) => toast.error("准入操作失败", { description: (e as Error).message }),
  });
}
