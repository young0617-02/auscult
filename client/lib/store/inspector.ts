"use client";

/**
 * Inspector（全局上下文检查器）状态（D1 壳，后续天接入真实内容）。
 * 四类内容页签（UI 方案 §8.4）：引用原文 / 图谱实体 / 文档分块 / 工具出入参。
 * 支持栈式浏览：open 压栈、back 出栈（面包屑导航）。
 */

import { create } from "zustand";

export type InspectorTab = "citation" | "entity" | "chunk" | "tool";

export interface InspectorEntry {
  tab: InspectorTab;
  title: string;
  payload?: unknown;
}

interface InspectorState {
  open: boolean;
  stack: InspectorEntry[];
  show: (entry: InspectorEntry) => void;
  back: () => void;
  close: () => void;
}

export const useInspector = create<InspectorState>((set) => ({
  open: false,
  stack: [],
  show: (entry) => set((s) => ({ open: true, stack: [...s.stack, entry] })),
  back: () =>
    set((s) => ({
      stack: s.stack.slice(0, -1),
      open: s.stack.length > 1,
    })),
  close: () => set({ open: false, stack: [] }),
}));
