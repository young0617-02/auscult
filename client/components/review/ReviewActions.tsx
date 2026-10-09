"use client";

/**
 * ReviewActions（P4-D13）：审核操作区（通过/驳回 + 意见必填）。
 * 安全约束（D14-D15）：
 * - RBAC：仅 reviewer 可见审核操作（按钮级角色门控）
 * - 禁止自审：诊断发起人=当前用户时禁用 + 原因文案
 * - 断线禁用：Socket 断开时禁止提交（防状态漂移）
 * - 驳回必填意见（≥1 字符）
 * 审核提交后 → toast + 列表/详情/线程查询失效（useReviewSubmit 已处理）。
 */

import { useState } from "react";
import { ShieldCheck, ShieldX, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuth, hasRole } from "@/lib/auth";
import { useConn } from "@/lib/store/connection";
import { useReviewSubmit } from "@/hooks/useReports";
import { useThread } from "@/hooks/useThread";
import {
  normalizeReviewStatus,
  REVIEW_STATUS_LABEL,
  REVIEW_STATUS_TONE,
  type ReportDetailData,
} from "@/lib/types/report";
import { cn } from "cn";

export function ReviewActions({ report }: { report: ReportDetailData }) {
  const user = useAuth((s) => s.user);
  const conn = useConn((s) => s.status);
  const isReviewer = hasRole(user, ["reviewer"]);
  const isConnected = conn === "connected";

  // 线程数据取 submitter（自审判定用）
  const { data: thread } = useThread(report.thread_id);
  const submitter = thread?.submitter ?? "";
  const isSelfReview = !!(submitter && user && submitter === user.username);

  const status = normalizeReviewStatus(report.review_status);
  // 仅 pending 态可审核；其他态展示结果
  const canReview = status === "pending";

  return (
    <section className="rounded-lg border border-edge-subtle bg-surface-raised p-4" data-testid="review-actions">
      <h3 className="flex items-center gap-1.5 text-xs text-fg-tertiary">
        <ShieldCheck className="size-3.5" />
        审核操作
      </h3>

      {!isReviewer && (
        <p className="mt-2 text-xs text-fg-tertiary">
          你的角色无审核权限（需审核员或系统管理员）。
        </p>
      )}

      {isReviewer && !canReview && (
        <div className="mt-2 flex items-center gap-2 text-xs">
          <span className={cn("rounded-full border px-2 py-0.5", REVIEW_STATUS_TONE[status])}>
            {REVIEW_STATUS_LABEL[status]}
          </span>
          <span className="text-fg-secondary">{submitter ? `发起人 ${submitter}` : ""}</span>
        </div>
      )}

      {isReviewer && canReview && (
        <ReviewForm
          reportId={report.report_id}
          threadId={report.thread_id}
          disabled={!isConnected || isSelfReview}
          disabledReason={
            !isConnected
              ? "连接断开，请等待重连后再提交审核"
              : isSelfReview
                ? `你是该诊断的发起人（${submitter}），不可自审，请更换审核员`
                : undefined
          }
        />
      )}
    </section>
  );
}

function ReviewForm({
  reportId,
  threadId,
  disabled,
  disabledReason,
}: {
  reportId: string;
  threadId: string;
  disabled?: boolean;
  disabledReason?: string;
}) {
  const [action, setAction] = useState<"approved" | "rejected">("approved");
  const [comment, setComment] = useState("");
  const submit = useReviewSubmit(reportId, threadId);

  const onSubmit = () => {
    if (disabled || submit.isPending) return;
    if (action === "rejected" && comment.trim().length === 0) return;
    submit.mutate({ action, comment: comment.trim() });
  };

  return (
    <div className="mt-3 flex flex-col gap-3">
      {disabled && disabledReason && (
        <p className="rounded-md border border-dashed border-risk-medium-edge bg-risk-medium-surface px-2.5 py-2 text-xs text-risk-medium-text">
          {disabledReason}
        </p>
      )}

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1.5 text-xs">
          <input
            type="radio"
            name="review-action"
            value="approved"
            checked={action === "approved"}
            onChange={() => setAction("approved")}
            disabled={disabled || submit.isPending}
            className="accent-risk-low"
          />
          通过
        </label>
        <label className="flex items-center gap-1.5 text-xs">
          <input
            type="radio"
            name="review-action"
            value="rejected"
            checked={action === "rejected"}
            onChange={() => setAction("rejected")}
            disabled={disabled || submit.isPending}
            className="accent-risk-high"
          />
          驳回
        </label>
      </div>

      <Textarea
        placeholder={action === "rejected" ? "驳回意见（必填）" : "审核意见（建议留痕）"}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        className="min-h-16 max-h-32 resize-none text-xs"
        maxLength={2000}
        disabled={disabled || submit.isPending}
        aria-label="审核意见"
      />
      {action === "rejected" && comment.trim().length === 0 && (
        <p className="text-xs text-risk-high-text">驳回时必填意见</p>
      )}

      <Button
        size="sm"
        disabled={disabled || submit.isPending || (action === "rejected" && comment.trim().length === 0)}
        onClick={onSubmit}
        data-testid="review-submit"
        className={cn(
          action === "approved" ? "bg-risk-low hover:bg-risk-low/80" : "bg-risk-high hover:bg-risk-high/80",
          "text-white",
        )}
      >
        {submit.isPending ? (
          <span className="animate-pulse">提交中…</span>
        ) : (
          <>
            <Send className="size-3.5" />
            {action === "approved" ? "通过" : "驳回"}
          </>
        )}
      </Button>
    </div>
  );
}
