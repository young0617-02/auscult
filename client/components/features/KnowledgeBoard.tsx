"use client";

/**
 * 知识库看板（P4-D16）：文档列表 + 状态/类型筛选 + 上传登记 + 准入审核。
 * RBAC：GET 任意已登录；上传/准入仅 kb_admin（后端 require_roles 二次校验）。
 * 版本历史：Q1=B 降级——展示 admission_status/admitted_by 三列，不新增 GET versions 契约。
 */

import { useCallback, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BookOpen, Upload } from "lucide-react";
import { PageScaffold, KpiCard } from "@/components/layout/PageScaffold";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth, hasRole } from "@/lib/auth";
import {
  useKnowledgeDocs,
  useDocCreate,
  useDocAdmission,
} from "@/hooks/useKnowledge";
import {
  DOC_TYPE_LABEL,
  DOC_STATUS_LABEL,
  DOC_STATUS_TONE,
  ADMISSION_LABEL,
  ADMISSION_TONE,
  normalizeDocStatus,
  normalizeAdmission,
  type DocType,
  type KnowledgeDocItem,
  type KnowledgeQuery,
} from "@/lib/types/knowledge";
import { cn } from "cn";

const PAGE_SIZE = 20;

export function KnowledgeBoard() {
  const router = useRouter();
  const sp = useSearchParams();
  const user = useAuth((s) => s.user);
  const canManage = hasRole(user, ["kb_admin"]);

  const query: KnowledgeQuery = {
    page: Number(sp.get("page") ?? 1) || 1,
    size: PAGE_SIZE,
    status: (sp.get("status") || undefined) as KnowledgeQuery["status"],
    doc_type: (sp.get("doc_type") || undefined) as KnowledgeQuery["doc_type"],
  };
  const { data, isPending, isError, error } = useKnowledgeDocs(query);

  const setParam = useCallback(
    (patch: Record<string, string | undefined>) => {
      const next = new URLSearchParams(sp.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === "") next.delete(k);
        else next.set(k, v);
      }
      if (!("page" in patch)) next.set("page", "1");
      router.replace(`/knowledge?${next.toString()}`, { scroll: false });
    },
    [router, sp],
  );

  const [uploadOpen, setUploadOpen] = useState(false);
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const pendingAdmission = data?.items.filter((d) => d.admission_status === "pending").length ?? 0;

  return (
    <PageScaffold
      title="知识库"
      description="文档准入 → 三存储索引 → 每日对账；版本历史降级为准入留痕展示（M4.4 Q1=B）"
      toolbar={
        <div className="flex items-center gap-2">
          <Select
            value={sp.get("doc_type") ?? "all"}
            onValueChange={(v) => setParam({ doc_type: v === "all" ? undefined : v })}
          >
            <SelectTrigger size="sm" className="w-28" aria-label="类型筛选">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部类型</SelectItem>
              <SelectItem value="manual">手册</SelectItem>
              <SelectItem value="work_order">工单</SelectItem>
              <SelectItem value="procedure">规程</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={sp.get("status") ?? "all"}
            onValueChange={(v) => setParam({ status: v === "all" ? undefined : v })}
          >
            <SelectTrigger size="sm" className="w-28" aria-label="状态筛选">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部状态</SelectItem>
              <SelectItem value="pending">待索引</SelectItem>
              <SelectItem value="indexed">已索引</SelectItem>
              <SelectItem value="failed">索引失败</SelectItem>
            </SelectContent>
          </Select>
          {canManage && (
            <Button size="sm" onClick={() => setUploadOpen(true)} data-testid="kb-upload-btn">
              <Upload className="mr-1 size-4" />
              上传文档
            </Button>
          )}
        </div>
      }
      kpis={
        <div className="grid grid-cols-4 gap-3">
          <KpiCard label="当前筛选文档" value={data?.total ?? 0} />
          <KpiCard label="本页待准入" value={pendingAdmission} tone={pendingAdmission > 0 ? "medium" : "default"} />
          <KpiCard label="已索引（本页）" value={data?.items.filter((d) => d.status === "indexed").length ?? 0} tone="low" />
          <KpiCard label="失败（本页）" value={data?.items.filter((d) => d.status === "failed").length ?? 0} tone="high" />
        </div>
      }
    >
      {isPending && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <EmptyState
          icon={BookOpen}
          title="知识库加载失败"
          reason={`${(error as Error).message}（请刷新重试）`}
        />
      )}

      {data && data.items.length === 0 && (
        <EmptyState
          icon={BookOpen}
          title="暂无文档"
          reason="为什么空：知识库管理员上传文档并完成准入后，文档进入索引与版本管理。"
        />
      )}

      {data && data.items.length > 0 && (
        <>
          <ul className="flex flex-col gap-2" data-testid="kb-list">
            {data.items.map((d) => (
              <DocRow key={d.doc_id} doc={d} canManage={canManage} />
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-end gap-2 text-xs text-fg-secondary">
            <span className="font-mono">
              第 {data.page} / {totalPages} 页 · 共 {data.total} 条
            </span>
            <Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => setParam({ page: String(data.page - 1) })}>
              上一页
            </Button>
            <Button variant="outline" size="sm" disabled={data.page >= totalPages} onClick={() => setParam({ page: String(data.page + 1) })}>
              下一页
            </Button>
          </div>
        </>
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </PageScaffold>
  );
}

// ---------------------------------------------------------------- 行

function DocRow({ doc, canManage }: { doc: KnowledgeDocItem; canManage: boolean }) {
  const status = normalizeDocStatus(doc.status);
  const admission = normalizeAdmission(doc.admission_status);
  const [admitOpen, setAdmitOpen] = useState(false);
  return (
    <li
      className="flex items-center gap-3 rounded-lg border border-edge-subtle bg-surface-raised px-4 py-2.5"
      data-testid={`kb-row-${doc.doc_id}`}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-fg-primary">{doc.title}</div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-fg-tertiary">
          <span>{DOC_TYPE_LABEL[doc.doc_type] ?? doc.doc_type}</span>
          <span>·</span>
          <span>{doc.source}</span>
          {doc.device_model && (
            <>
              <span>·</span>
              <span className="font-mono">{doc.device_model}</span>
            </>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <span className={cn("rounded-full border px-2 py-0.5 text-xs", DOC_STATUS_TONE[status])} data-testid={`kb-status-${doc.doc_id}`}>
          {DOC_STATUS_LABEL[status]}
        </span>
        <span className={cn("rounded-full border px-2 py-0.5 text-xs", ADMISSION_TONE[admission])} data-testid={`kb-admission-${doc.doc_id}`}>
          {ADMISSION_LABEL[admission]}
        </span>
        <time className="font-mono text-xs text-fg-tertiary" dateTime={doc.created_at}>
          {new Date(doc.created_at).toLocaleString("zh-CN", { hour12: false })}
        </time>
        {canManage && admission === "pending" && (
          <Button size="sm" variant="outline" onClick={() => setAdmitOpen(true)} data-testid={`kb-admit-btn-${doc.doc_id}`}>
            准入审核
          </Button>
        )}
      </div>
      <AdmissionDialog doc={doc} open={admitOpen} onOpenChange={setAdmitOpen} />
    </li>
  );
}

// ---------------------------------------------------------------- 上传对话框

function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const create = useDocCreate();
  const [title, setTitle] = useState("");
  const [docType, setDocType] = useState<DocType>("manual");
  const [source, setSource] = useState("");
  const [deviceModel, setDeviceModel] = useState("");
  const [content, setContent] = useState("");

  const canSubmit = title.trim().length > 0 && source.trim().length > 0 && !create.isPending;

  const submit = () => {
    create.mutate(
      {
        title: title.trim(),
        doc_type: docType,
        source: source.trim(),
        device_model: deviceModel.trim() || null,
        content: content.trim() || null,
      },
      {
        onSuccess: () => {
          onOpenChange(false);
          setTitle(""); setSource(""); setDeviceModel(""); setContent("");
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="kb-upload-dialog">
        <DialogHeader>
          <DialogTitle>上传文档（元数据登记）</DialogTitle>
          <DialogDescription>
            仅登记元数据，状态置 pending；解析/分块/向量化由索引流水线推进，准入审核通过后方可索引。
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="kb-title">标题 *</Label>
            <Input id="kb-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label>类型 *</Label>
              <Select value={docType} onValueChange={(v) => setDocType(v as DocType)}>
                <SelectTrigger aria-label="文档类型">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">手册</SelectItem>
                  <SelectItem value="work_order">工单</SelectItem>
                  <SelectItem value="procedure">规程</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="kb-source">来源 *</Label>
              <Input id="kb-source" value={source} onChange={(e) => setSource(e.target.value)} placeholder="供应商手册 / 工单系统" maxLength={100} />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="kb-model">设备型号（可选）</Label>
            <Input id="kb-model" value={deviceModel} onChange={(e) => setDeviceModel(e.target.value)} maxLength={100} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="kb-content">正文（可选，仅用于 checksum）</Label>
            <Textarea id="kb-content" value={content} onChange={(e) => setContent(e.target.value)} rows={3} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="kb-upload-submit">
            {create.isPending ? "提交中…" : "登记"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------- 准入审核对话框

function AdmissionDialog({
  doc,
  open,
  onOpenChange,
}: {
  doc: KnowledgeDocItem;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const admit = useDocAdmission();
  const [action, setAction] = useState<"approve" | "reject">("approve");
  const [comment, setComment] = useState("");

  const canSubmit = !admit.isPending;

  const submit = () => {
    admit.mutate(
      { docId: doc.doc_id, input: { action, comment: comment.trim() } },
      {
        onSuccess: () => {
          onOpenChange(false);
          setComment(""); setAction("approve");
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="kb-admission-dialog">
        <DialogHeader>
          <DialogTitle>准入审核：{doc.title}</DialogTitle>
          <DialogDescription>
            一次性决策：pending → approved / rejected；决策写入 knowledge_versions 留痕，不可重复审核。
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-4">
            <Label className="flex items-center gap-1.5">
              <input
                type="radio"
                name="admission-action"
                checked={action === "approve"}
                onChange={() => setAction("approve")}
                aria-label="准予入库"
              />
              准予入库
            </Label>
            <Label className="flex items-center gap-1.5">
              <input
                type="radio"
                name="admission-action"
                checked={action === "reject"}
                onChange={() => setAction("reject")}
                aria-label="驳回"
              />
              驳回
            </Label>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="kb-admit-comment">审核意见（可选）</Label>
            <Textarea
              id="kb-admit-comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              maxLength={2000}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={submit} disabled={!canSubmit} data-testid="kb-admission-submit">
            {admit.isPending ? "提交中…" : "提交决策"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
