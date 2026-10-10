"use client";

/**
 * 全局 Providers（D1）：
 * - QueryClientProvider：服务端状态（D4 告警列表 / D5 实时失效）
 * - TooltipProvider：shadcn Tooltip 必需
 * - Toaster：低打扰 Toast（右上角，UI 方案 §5.1 RealtimeLayer）
 */

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      <Toaster theme="light" position="bottom-right" />
    </QueryClientProvider>
  );
}
