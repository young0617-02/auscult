"use client";

/**
 * 诊断控制台装配层（P4-D6~D10）：三栏 = 会话列表 / 对话流 / 推理轨迹。
 * 数据双源合并：
 * - 实时态：socket 事件 → threads store（节点进度/终态，诊断页订阅）
 * - 富数据：GET /api/threads/{id}（qa_log / review_payload / submitter），socket 终态后失效刷新
 * 深链 /diagnosis?thread=xxx 打开注册表未见的线程时由 REST 水合（服务重启/换浏览器场景）。
 */

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Loader2, Stethoscope } from "lucide-react";
import { toast } from "sonner";
import { PageScaffold } from "@/components/layout/PageScaffold";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { ThreadList } from "@/components/domain/ThreadList";
import { ProgressSteps } from "@/components/chat/ProgressSteps";
import { DoneMessage, ErrorMessage, WaitingReviewMessage } from "@/components/chat/DiagnosisResult";
import { AskInput } from "@/components/chat/AskInput";
import { EvidenceChip } from "@/components/common/EvidenceCard";
import { useThread } from "@/hooks/useThread";
import { getSocket } from "@/lib/socket";
import { useAuth } from "@/lib/auth";
import { useThreads } from "@/lib/store/threads";
import { THREAD_STATUS_LABEL, type QaEntry, type ThreadStatus } from "@/lib/types/thread";
import { cn } from "cn";

const STATUS_PILL: Record<ThreadStatus, string> = {
  running: "border-state-running/40 bg-state-running/10 text-state-running",
  waiting_review: "border-risk-medium-edge bg-risk-medium-surface text-risk-medium-text",
  done: "border-risk-low-edge bg-risk-low-surface text-risk-low-text",
  error: "border-risk-high-edge bg-risk-high-surface text-risk-high-text",
};

/** 终态优先级：socket 与 REST 冲突时取更「终」者（简历后 REST done 兜底陈旧 running） */
const STATUS_PRIORITY: Record<ThreadStatus, number> = {
  running: 0,
  waiting_review: 1,
  done: 2,
  error: 3,
};

function formatTs(sec: number | null | undefined): string {
  if (!sec) return "—";
  return new Date(sec * 1000).toLocaleTimeString("zh-CN", { hour12: false });
}

export function DiagnosisConsole() {
  const sp = useSearchParams();
  const threadId = sp.get("thread");

  const { data, isPending, isError, error } = useThread(threadId);
  const storeThread = useThreads((s) => (threadId ? s.threads[threadId] : undefined));

  // REST 水合：注册表未见过的线程（深链/换浏览器）入册
  useEffect(() => {
    if (data) useThreads.getState().hydrateFromStatus(data);
  }, [data]);

  // 追问本地态：首次提问后本地为真相源（避免 refetch 闪烁）；切线程重置
  const [localQa, setLocalQa] = useState<QaEntry[] | null>(null);
  const [pendingAsk, setPendingAsk] = useState<string | null>(null);
  useEffect(() => {
    setLocalQa(null);
    setPendingAsk(null);
  }, [threadId]);

  const status: ThreadStatus = useMemo(() => {
    const a = storeThread?.status;
    const b = data?.status;
    if (!a && !b) return "running";
    if (!a) return b!;
    if (!b) return a;
    return STATUS_PRIORITY[a] >= STATUS_PRIORITY[b] ? a : b;
  }, [storeThread, data]);

  const nodesDone = useMemo(() => {
    const set = new Set<string>([...(storeThread?.nodes_done ?? []), ...(data?.nodes_done ?? [])]);
    return [...set];
  }, [storeThread, data]);

  const role = useAuth((s) => s.user?.role);
  const canAsk = role === "engineer" || role === "reviewer" || role === "sys_admin";
  const askable = status === "done" || status === "waiting_review";

  const ask = (question: string) => {
    const token = useAuth.getState().token;
    if (!token || !threadId) return;
    setPendingAsk(question);
    // chat:ask ack 回调（socket.py）：{code: 0, data: {answer, citations}} 或 {code: E_*}
    socketAsk(token, threadId, question)
      .then((resp) => {
        setPendingAsk(null);
        if (!resp || resp.code !== 0) {
          toast.error("追问失败", {
            description: resp?.message ?? "服务无响应，请稍后重试",
          });
          return;
        }
        const d = resp.data;
        if (!d) {
          toast.error("追问失败", { description: "服务返回数据为空" });
          return;
        }
        setLocalQa((prev) => [
          ...(prev ?? data?.qa_log ?? []),
          { question, answer: d.answer, citations: d.citations ?? [], ts: Date.now() / 1000 },
        ]);
      })
      .catch(() => {
        setPendingAsk(null);
        toast.error("追问失败", { description: "网络异常，请稍后重试" });
      });
  };

  const qaList = localQa ?? data?.qa_log ?? [];

  return (
    <PageScaffold
      title="诊断控制台"
      description="会话 = 一次诊断线程；节点进度由 diagnosis:progress 实时驱动"
      contentClassName="min-h-0 flex-1 overflow-hidden"
    >
      <div className="flex h-full min-h-0">
        {/* 左：会话列表 */}
        <aside className="hidden w-60 shrink-0 overflow-y-auto border-r border-edge-subtle md:block">
          <ThreadList activeId={threadId} />
        </aside>

        {/* 中：对话流 */}
        <section className="flex min-w-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {!threadId && (
              <EmptyState
                icon={Stethoscope}
                title="未选择诊断会话"
                reason="从左侧列表选择会话，或在告警看板点击「发起诊断」创建新线程。"
              />
            )}

            {threadId && isPending && (
              <div className="flex flex-col gap-3">
                <Skeleton className="h-20 w-full" />
                <Skeleton className="h-32 w-full" />
              </div>
            )}

            {threadId && isError && (
              <EmptyState
                icon={Stethoscope}
                title="线程加载失败"
                reason={`${(error as Error).message}（线程可能不存在，或服务重启后状态已回收）`}
              />
            )}

            {threadId && data && (
              <div className="flex flex-col gap-4">
                {/* 会话头 */}
                <div className="flex flex-wrap items-center gap-2 text-xs text-fg-tertiary">
                  <span className={cn("rounded-full border px-2 py-0.5", STATUS_PILL[status])} data-testid="thread-status">
                    {THREAD_STATUS_LABEL[status]}
                  </span>
                  <span className="font-mono">{threadId}</span>
                  {data.submitter && <span>发起人 {data.submitter}</span>}
                  <span className="ml-auto font-mono">开始 {formatTs(data.started_at)}</span>
                </div>

                {/* 告警上下文卡 */}
                <div className="rounded-lg border border-edge-subtle bg-surface-raised px-3 py-2.5 text-xs">
                  <div className="text-fg-tertiary">触发告警</div>
                  <div className="mt-1 font-mono text-sm text-fg-primary">
                    {data.alarm?.device_id ?? "未知设备"} · {data.alarm?.metric ?? "未知测点"}
                    <span className="ml-2">{data.alarm?.value ?? "—"}</span>
                  </div>
                  <div className="mt-0.5 text-fg-tertiary">
                    严重度 {data.alarm?.severity || "—"}
                    {data.alarm?.alarm_id && <span className="ml-2 font-mono">{data.alarm.alarm_id}</span>}
                  </div>
                </div>

                {/* 内联进度（窄屏时替代右栏） */}
                <div className="rounded-lg border border-edge-subtle bg-surface-base p-2 lg:hidden">
                  <ProgressSteps nodesDone={nodesDone} nodeTs={storeThread?.node_ts} status={status} />
                </div>

                {/* 终态消息 */}
                {status === "done" && (
                  <DoneMessage reportId={data.report_id} degradeReason={data.degrade_reason} />
                )}
                {status === "error" && <ErrorMessage error={data.error ?? storeThread?.error ?? null} />}
                {status === "waiting_review" && <WaitingReviewMessage payload={data.review_payload} />}

                {/* 追问记录 */}
                {qaList.length > 0 && (
                  <div className="flex flex-col gap-3">
                    {qaList.map((e, i) => (
                      <QaBlock key={`${e.ts ?? "x"}-${i}`} entry={e} />
                    ))}
                  </div>
                )}

                {/* 追问进行中（乐观消息） */}
                {pendingAsk && (
                  <div className="flex flex-col gap-2">
                    <div className="self-end rounded-lg bg-surface-raised px-3 py-2 text-xs text-fg-primary">
                      {pendingAsk}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-fg-tertiary">
                      <Loader2 className="size-3.5 animate-spin" />
                      助手思考中…
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* 追问输入（D10） */}
          {threadId && data && (
            <AskInput
              disabled={!canAsk || !askable}
              disabledReason={
                !canAsk
                  ? "你的角色无追问权限（需工程师及以上）"
                  : status === "running"
                    ? "诊断完成后可追问"
                    : "当前状态不可追问"
              }
              pending={!!pendingAsk}
              onSubmit={ask}
            />
          )}
        </section>

        {/* 右：推理轨迹 */}
        <aside className="hidden w-72 shrink-0 overflow-y-auto border-l border-edge-subtle p-3 lg:block">
          <h2 className="px-2 pb-2 text-xs text-fg-tertiary">推理轨迹</h2>
          {threadId ? (
            <ProgressSteps nodesDone={nodesDone} nodeTs={storeThread?.node_ts} status={status} />
          ) : (
            <p className="px-2 text-xs text-fg-tertiary">选择会话后展示节点流。</p>
          )}
        </aside>
      </div>
    </PageScaffold>
  );
}

function QaBlock({ entry }: { entry: QaEntry }) {
  return (
    <div className="flex flex-col gap-1.5" data-testid="qa-block">
      <div className="self-end rounded-lg bg-surface-raised px-3 py-2 text-xs text-fg-primary">{entry.question}</div>
      <div className="rounded-lg border border-edge-subtle bg-surface-base px-3 py-2">
        <div className="text-[10px] text-fg-tertiary">助手{entry.model ? ` · ${entry.model}` : ""}</div>
        <p className="mt-1 whitespace-pre-wrap text-xs leading-5 text-fg-primary">{entry.answer}</p>
        {entry.citations.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {entry.citations.map((c) => (
              <EvidenceChip key={c} chunkId={c} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** chat:ask socket 调用（45s > 服务端 30s 推理超时 + 余量） */
function socketAsk(
  token: string,
  threadId: string,
  question: string,
): Promise<{ code: number | string; message?: string; data?: { answer: string; citations: string[] } } | null> {
  return new Promise((resolve) => {
    const socket = getSocket(token);
    socket
      .timeout(45_000)
      .emit(
        "chat:ask",
        { thread_id: threadId, question },
        (
          err: Error | null,
          resp?: { code: number | string; message?: string; data?: { answer: string; citations: string[] } },
        ) => {
          if (err) resolve(null);
          else resolve(resp ?? null);
        },
      );
  });
}
