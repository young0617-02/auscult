"use client";

/**
 * 实时连接状态（P4-D5）：SocketProvider 维护；TopStatusBar 指示灯与
 * ConnectionBanner 消费；断线期间审核提交禁用（D14 读此状态）。
 */

import { create } from "zustand";

export type ConnStatus = "connecting" | "connected" | "disconnected";

interface ConnectionState {
  status: ConnStatus;
  /** 第几次重连尝试（1 起，0=未在重连） */
  attempt: number;
  /** 未读新告警数（alarm:new 累计，点击铃铛清零） */
  unreadAlarms: number;
  setStatus: (status: ConnStatus) => void;
  setAttempt: (n: number) => void;
  bumpUnread: () => void;
  clearUnread: () => void;
}

export const useConn = create<ConnectionState>((set) => ({
  status: "connecting",
  attempt: 0,
  unreadAlarms: 0,
  setStatus: (status) => set({ status }),
  setAttempt: (attempt) => set({ attempt }),
  bumpUnread: () => set((s) => ({ unreadAlarms: s.unreadAlarms + 1 })),
  clearUnread: () => set({ unreadAlarms: 0 }),
}));
