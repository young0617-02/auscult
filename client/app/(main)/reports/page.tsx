import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { ReportsList } from "@/components/features/ReportsList";

/** ③ 报告工作台 /reports：useSearchParams 需 Suspense 边界（cacheComponents） */
export default function ReportsPage() {
  return (
    <Suspense fallback={<div className="p-6"><Skeleton className="h-64 w-full" /></div>}>
      <ReportsList />
    </Suspense>
  );
}
