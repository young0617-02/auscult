import { Suspense } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { DiagnosisConsole } from "@/components/features/DiagnosisConsole";

/** ② 诊断控制台 /diagnosis：useSearchParams 需 Suspense 边界（cacheComponents） */
export default function DiagnosisPage() {
  return (
    <Suspense fallback={<div className="p-6"><Skeleton className="h-64 w-full" /></div>}>
      <DiagnosisConsole />
    </Suspense>
  );
}
