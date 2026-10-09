/** lib/auth.ts 单测（P4-D3）：角色守卫 / 登录默认落地页 */

import { beforeEach, describe, expect, it } from "vitest";
import { useAuth, hasRole, defaultRouteForRole, type AuthUser } from "@/lib/auth";

const userOf = (role: AuthUser["role"]): AuthUser => ({
  user_id: "1",
  username: "u",
  display_name: "用户",
  role,
});

beforeEach(() => {
  useAuth.setState({ token: null, user: null, hydrated: false });
});

describe("hasRole", () => {
  it("未登录一律不放行", () => {
    expect(hasRole(null, ["sys_admin"])).toBe(false);
  });

  it("角色在白名单内放行", () => {
    expect(hasRole(userOf("sys_admin"), ["sys_admin"])).toBe(true);
  });

  it("角色不在白名单内拒绝", () => {
    expect(hasRole(userOf("engineer"), ["sys_admin"])).toBe(false);
  });
});

describe("defaultRouteForRole", () => {
  it("工程师 → 告警看板", () => {
    expect(defaultRouteForRole("engineer")).toBe("/alarms");
  });
  it("审核员 → 报告待办队列", () => {
    expect(defaultRouteForRole("reviewer")).toBe("/reports");
  });
  it("知识库管理员 → 知识库", () => {
    expect(defaultRouteForRole("kb_admin")).toBe("/knowledge");
  });
  it("系统管理员 → 审计日志", () => {
    expect(defaultRouteForRole("sys_admin")).toBe("/audit");
  });
});
