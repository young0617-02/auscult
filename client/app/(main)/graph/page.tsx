"use client";

/**
 * ⑤ 图谱探索 /graph（P4-D17 实装）。
 * react-force-graph-2d 懒加载 + 邻居查询 + 关系过滤 + 节点检查器。
 * 支持 ?entity=<名称> 预载（报告页「从当前报告载入」跳转，D18）。
 */

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { GraphExplorer } from "@/components/features/GraphExplorer";
import { Skeleton } from "@/components/ui/skeleton";

function GraphInner() {
  const sp = useSearchParams();
  return <GraphExplorer initialEntity={sp.get("entity")} />;
}

export default function GraphPage() {
  return (
    <Suspense fallback={<Skeleton className="m-6 h-96 w-[calc(100%-3rem)]" />}>
      <GraphInner />
    </Suspense>
  );
}
