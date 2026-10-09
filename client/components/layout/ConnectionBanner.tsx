"use client";

/**
 * ConnectionBanner（P4-D5）：实时连接断开/重连横幅（顶栏下方常驻条）。
 * connected 时不渲染；数据延迟更新、恢复后由 SocketProvider 自动校正。
 */

import { cn } from "cn";
import { useConn } from "@/lib/store/connection";

export function ConnectionBanner() {
  const status = useConn((s) => s.status);
  const attempt = useConn((s) => s.attempt);
  if (status === "connected") return null;

  const down = status === "disconnected";
  return (
    <div
      role="status"
      className={cn(
        "flex h-8 shrink-0 items-center justify-center gap-2 text-xs",
        down
          ? "bg-risk-high-surface text-risk-high-text"
          : "bg-notice-warning-surface text-notice-warning-text",
      )}
    >
      <span aria-hidden>{down ? "●" : "◐"}</span>
      {down ? "实时连接已断开" : "正在重连"}
      {attempt > 0 && `（第 ${attempt} 次）`}
      ，数据可能延迟更新；恢复后自动校正
    </div>
  );
}
