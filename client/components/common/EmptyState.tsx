"use client";

/**
 * EmptyState（空态，L2）：每个列表/画布必须有空态，且说明"为什么空"（§6.6）。
 */

import { cn } from "cn";
import type { LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  reason,
  className,
}: {
  icon: LucideIcon;
  title: string;
  reason?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full min-h-48 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-edge-subtle p-8 text-center",
        className,
      )}
    >
      <Icon className="size-8 text-fg-tertiary" aria-hidden />
      <p className="text-sm text-fg-secondary">{title}</p>
      {reason && <p className="max-w-md text-xs text-fg-tertiary">{reason}</p>}
    </div>
  );
}
