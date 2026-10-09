import { Suspense } from "react";
import { AlarmsBoard } from "@/components/features/AlarmsBoard";
import { Skeleton } from "@/components/ui/skeleton";

/** ① 告警看板 /alarms：useSearchParams 需 Suspense 边界（cacheComponents） */
export default function AlarmsPage() {
  return (
    <Suspense fallback={<div className="p-6"><Skeleton className="h-64 w-full" /></div>}>
      <AlarmsBoard />
    </Suspense>
  );
}
