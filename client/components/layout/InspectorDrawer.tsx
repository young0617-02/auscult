"use client";

/**
 * InspectorDrawer（全局上下文检查器，跨页复用的右侧抽屉，§8.4 亮点 4）。
 * 四类页签：引用原文 / 图谱实体 / 文档分块 / 工具出入参；
 * D1 交付壳 + 栈式导航；真实内容由 D8 证据卡片 / D17 图谱 / D18 联动接入。
 */

import { useInspector, type InspectorTab } from "@/lib/store/inspector";
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

export function InspectorDrawer() {
  const { open, stack, back, close } = useInspector();
  const current = stack[stack.length - 1];

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

        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          {current ? (
            <>
              <p className="text-sm text-fg-secondary">
                页签「{TAB_LABEL[current.tab]}」内容待接入
              </p>
              <p className="text-xs text-fg-tertiary">
                引用原文（D8）/ 图谱实体（D17）/ 工具出入参（D10）逐步接入
              </p>
            </>
          ) : (
            <p className="text-sm text-fg-tertiary">点击页面中的引用、实体或工具调用在此查看详情</p>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
