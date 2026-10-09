"use client";

/**
 * ④ 知识库 /knowledge（P4-D16 实装）。
 * 文档列表/状态/上传准入/准入留痕展示（版本历史降级，M4.4 Q1=B）。
 */

import { Suspense } from "react";
import { KnowledgeBoard } from "@/components/features/KnowledgeBoard";
import { Skeleton } from "@/components/ui/skeleton";

export default function KnowledgePage() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-2 p-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      }
    >
      <KnowledgeBoard />
    </Suspense>
  );
}
