"use client";

/**
 * 会话与 RBAC（D1 建库，D3 接登录页与路由守卫）。
 * - JWT + 用户信息持久化 localStorage（zustand persist）
 * - 角色与后端 users.role 一致：engineer / reviewer / kb_admin / sys_admin
 * - SSR 安全：persist 在客户端水合，组件侧用 hasHydrated 判断再渲染角色相关 UI
 */

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type Role = "engineer" | "reviewer" | "kb_admin" | "sys_admin";

export interface AuthUser {
  user_id: string;
  username: string;
  display_name: string;
  role: Role;
}

export const ROLE_LABEL: Record<Role, string> = {
  engineer: "工程师",
  reviewer: "审核员",
  kb_admin: "知识库管理员",
  sys_admin: "系统管理员",
};

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  hydrated: boolean;
  setAuth: (token: string, user: AuthUser) => void;
  clear: () => void;
  setHydrated: () => void;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      hydrated: false,
      setAuth: (token, user) => set({ token, user }),
      clear: () => set({ token: null, user: null }),
      setHydrated: () => set({ hydrated: true }),
    }),
    {
      name: "auscult-auth",
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ token: s.token, user: s.user }),
      onRehydrateStorage: () => (state) => state?.setHydrated(),
    },
  ),
);

/** 角色守卫：user 角色在 roles 内视为放行（D3 路由守卫使用） */
export function hasRole(user: AuthUser | null, roles: readonly Role[]): boolean {
  return !!user && roles.includes(user.role);
}

/** 登录后默认落地页（UI 方案 §1.2：审核员→待办队列，知识库管理员→知识库） */
export function defaultRouteForRole(role: Role): string {
  switch (role) {
    case "reviewer":
      return "/reports";
    case "kb_admin":
      return "/knowledge";
    case "sys_admin":
      return "/audit";
    default:
      return "/alarms";
  }
}
