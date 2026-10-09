"use client";

/**
 * Socket.IO 客户端单例（P4-D5）。
 * - connect 鉴权：auth={"token": <JWT>}（对齐 app/api/socket.py）
 * - 重连：指数退避上限 5s；重连成功后由 SocketProvider invalidateQueries 全量校正
 * - 事件消费集中在 SocketProvider（UI 方案 §10.2：实时状态不进全局 store，
 *   走 react-query 定向更新）
 */

import { io, type Socket } from "socket.io-client";

let socket: Socket | null = null;

export function getSocket(token: string): Socket {
  if (socket) return socket;
  // dev 经 Next rewrite 的 /socket.io/ 会 308 重定向（websocket 无法跟随），
  // 故 dev 直连 NEXT_PUBLIC_API_ORIGIN（默认 http://127.0.0.1:8000）；生产留空走同源（Nginx 9763）
  const origin = process.env.NEXT_PUBLIC_API_ORIGIN || window.location.origin;
  socket = io(origin, {
    path: "/socket.io",
    transports: ["websocket", "polling"],
    auth: { token },
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
    timeout: 10_000,
  });
  return socket;
}

export function closeSocket(): void {
  socket?.removeAllListeners();
  socket?.disconnect();
  socket = null;
}

/** alarm:new / REST 双形态时间戳由 components/domain/AlarmCard.alarmTime 归一 */
export type AlarmNewPayload = {
  alarm_id: string;
  device_id: string;
  metric: string;
  value: number | null;
  severity: "info" | "warning" | "critical";
  status: "open" | "acked" | "closed";
  ts: number | null;
};
