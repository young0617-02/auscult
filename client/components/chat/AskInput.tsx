"use client";

/**
 * AskInput（P4-D10）：对话式追问输入框（chat:ask，复用 thread 上下文）。
 * 仅 done / waiting_review 态可追问（后端 ask_question 同口径，E_CONFLICT 前置拦截）；
 * kb_admin 无发起/追问权限 → 显示原因文案而非隐藏（UI 方案 §1.2）。
 */

import { useState } from "react";
import { SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function AskInput({
  disabled,
  disabledReason,
  pending,
  onSubmit,
}: {
  disabled?: boolean;
  disabledReason?: string;
  pending?: boolean;
  onSubmit: (question: string) => void;
}) {
  const [value, setValue] = useState("");

  const submit = () => {
    const q = value.trim();
    if (!q || disabled || pending) return;
    onSubmit(q);
    setValue("");
  };

  return (
    <div className="border-t border-edge-subtle bg-surface-base p-3">
      {disabled ? (
        <p className="rounded-md border border-dashed border-edge-subtle px-3 py-2.5 text-xs text-fg-tertiary">
          {disabledReason ?? "当前状态不可追问"}
        </p>
      ) : (
        <div className="flex items-end gap-2">
          <Textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="追问细节，如「润滑不足的依据是哪条证据？」（Enter 发送，Shift+Enter 换行）"
            className="min-h-16 max-h-40 resize-none text-xs"
            maxLength={2000}
            aria-label="追问输入框"
          />
          <Button size="sm" disabled={pending || !value.trim()} onClick={submit} aria-label="发送追问">
            {pending ? <span className="animate-pulse">…</span> : <SendHorizonal className="size-3.5" />}
            发送
          </Button>
        </div>
      )}
    </div>
  );
}
