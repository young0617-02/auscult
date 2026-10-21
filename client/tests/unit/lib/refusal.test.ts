/**
 * 拒答/澄清展示口径回归锁（P7 · 2026-10-21）。
 *
 * 背景：规则 6a/6b 的"只回文字"是**正确行为**，后端已不再按 `E_JSON_PARSE`
 * 处理（`state.refusal` + 路由直达 finalize）。前端必须能把它与"诊断失败"区分开，
 * 否则用户看到的就是一个没有报告、没有解释的死胡同。
 */

import { describe, expect, it } from "vitest";

import { isRefusal, refusalTitle, REFUSAL_FALLBACK_TITLE } from "@/lib/refusal";

describe("refusalTitle", () => {
  it("澄清 → 提示补充信息", () => {
    expect(refusalTitle("clarification")).toBe("需要补充信息");
  });

  it("拒止 → 提示超出职责范围", () => {
    expect(refusalTitle("refusal")).toBe("超出诊断职责范围");
  });

  it("未知/缺失 kind → 兜底文案（不渲染空标题）", () => {
    expect(refusalTitle("weird")).toBe(REFUSAL_FALLBACK_TITLE);
    expect(refusalTitle(null)).toBe(REFUSAL_FALLBACK_TITLE);
    expect(refusalTitle(undefined)).toBe(REFUSAL_FALLBACK_TITLE);
  });
});

describe("isRefusal", () => {
  it("仅 clarification / refusal 为真", () => {
    expect(isRefusal({ kind: "clarification", reason: "x" })).toBe(true);
    expect(isRefusal({ kind: "refusal", reason: "x" })).toBe(true);
    expect(isRefusal(null)).toBe(false);
    expect(isRefusal(undefined)).toBe(false);
  });
});
