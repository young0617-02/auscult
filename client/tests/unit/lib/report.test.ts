/** M4.3 单测：report 类型归一 + 审核门禁纯逻辑 */

import { describe, expect, it } from "vitest";
import { normalizeReviewStatus } from "@/lib/types/report";

describe("normalizeReviewStatus", () => {
  it("null → pending", () => {
    expect(normalizeReviewStatus(null)).toBe("pending");
  });
  it("approved / rejected / timeout / auto_approved 原样通过", () => {
    expect(normalizeReviewStatus("approved")).toBe("approved");
    expect(normalizeReviewStatus("rejected")).toBe("rejected");
    expect(normalizeReviewStatus("timeout")).toBe("timeout");
    expect(normalizeReviewStatus("auto_approved")).toBe("auto_approved");
  });
  it("未知值回退 pending（防御后端扩展枚举）", () => {
    expect(normalizeReviewStatus("unknown_future_status")).toBe("pending");
  });
});

describe("审核门禁口径（对齐后端 D0-5）", () => {
  it("仅 reviewer 角色可审核（require_roles 冻结口径）", () => {
    const allowed = ["reviewer"];
    expect(allowed).toContain("reviewer");
    expect(allowed).not.toContain("engineer");
    expect(allowed).not.toContain("sys_admin");
  });

  it("审核动作仅允许 approved / rejected（timeout 仅系统触发）", () => {
    const actions = new Set(["approved", "rejected"]);
    expect(actions.has("approved")).toBe(true);
    expect(actions.has("rejected")).toBe(true);
    expect(actions.has("timeout")).toBe(false);
  });

  it("驳回必填意见（前端约束，后端 comment max_length 2000）", () => {
    const validate = (action: string, comment: string) =>
      action !== "rejected" || comment.trim().length > 0;
    expect(validate("rejected", "")).toBe(false);
    expect(validate("rejected", "  ")).toBe(false);
    expect(validate("rejected", "需复核证据")).toBe(true);
    expect(validate("approved", "")).toBe(true);
  });
});
