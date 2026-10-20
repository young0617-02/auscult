"use client";

/**
 * InspectorDrawer（全局上下文检查器，跨页复用的右侧抽屉，§8.4 亮点 4）。
 * 四类页签：引用原文 / 图谱实体 / 文档分块 / 工具出入参；
 * D1 交付壳 + 栈式导航；真实内容由 D8 证据卡片 / D17 图谱 / D18 联动接入。
 * P7：工具出入参页签接入 Agent 循环轨迹（thread_status.agent_steps，
 *     见 docs/p7-design-agent-diagnosis-2026-10-19.md §3.2）。
 */

import { useInspector, type InspectorTab } from "@/lib/store/inspector";
import type { AgentStep } from "@/lib/types/thread";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

const TAB_LABEL: Record<InspectorTab, string> = {
  citation: "引用原文",
  entity: "图谱实体",
  chunk: "文档分块",
  tool: "工具出入参",
};

function ToolDetail({ step }: { step: AgentStep }) {
  const forced = step.forced_final === true;
  return (
    <div className="flex flex-col gap-3 p-6 text-left">
      <div className="flex items-center gap-2">
        <span className="text-sm text-fg-primary">
          第 {step.step} 轮 · {step.tool ?? "无工具强制收口"}
        </span>
        <span
          className={
            step.ok
              ? "rounded bg-risk-low-surface px-1.5 py-0.5 text-xs text-risk-low-text"
              : "rounded bg-risk-high-surface px-1.5 py-0.5 text-xs text-risk-high-text"
          }
        >
          {step.ok ? "成功" : "失败/拒绝"}
        </span>
      </div>
      {forced && (
        <p className="text-xs text-fg-tertiary">
          已达工具调用步数上限，模型被要求基于已获证据直接输出诊断结论。
        </p>
      )}
      <div>
        <p className="pb-1 text-xs text-fg-tertiary">参数键名（值不回传前端）</p>
        <div className="flex flex-wrap gap-1">
          {step.args_keys.length > 0 ? (
            step.args_keys.map((k) => (
              <code
                key={k}
                className="rounded bg-surface-raised px-1.5 py-0.5 text-xs text-fg-secondary"
              >
                {k}
              </code>
            ))
          ) : (
            <span className="text-xs text-fg-tertiary">—</span>
          )}
        </div>
      </div>
      {step.latency_ms != null && (
        <p className="text-xs text-fg-tertiary">LLM 调用耗时：{step.latency_ms} ms</p>
      )}
    </div>
  );
}

export function InspectorDrawer() {
  const { open, stack, back, close } = useInspector();
  const current = stack[stack.length - 1];
  const toolStep =
    current?.tab === "tool" && current.payload && typeof current.payload === "object"
      ? (current.payload as AgentStep)
      : null;

  return (
    <Sheet open={open} onOpenChange={(o) => !o && close()}>
      <SheetContent
        side="right"
        className="w-[420px] gap-0 sm:max-w-[420px]"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <SheetHeader className="border-b border-edge-subtle pb-3">
          <div className="flex items-center gap-2">
            {stack.length > 1 && (
              <Button variant="ghost" size="icon-sm" aria-label="返回上一层" onClick={back}>
                <ArrowLeft className="size-4" aria-hidden />
              </Button>
            )}
            <SheetTitle className="truncate">
              {current ? TAB_LABEL[current.tab] : "检查器"}
            </SheetTitle>
          </div>
          <SheetDescription className="truncate">
            {current?.title ?? "未选择内容"}
          </SheetDescription>
        </SheetHeader>

        {toolStep ? (
          <ToolDetail step={toolStep} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
            {current ? (
              <>
                <p className="text-sm text-fg-secondary">
                  页签「{TAB_LABEL[current.tab]}」内容待接入
                </p>
                <p className="text-xs text-fg-tertiary">
                  引用原文（D8）/ 图谱实体（D17）/ 工具出入参（Agent 轨迹，P7）逐步接入
                </p>
              </>
            ) : (
              <p className="text-sm text-fg-tertiary">点击页面中的引用、实体或工具调用在此查看详情</p>
            )}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
