/**
 * 拒答/澄清的展示口径（P7 · 2026-10-21）。
 *
 * 来源：`app/graph/state.py::refusal`（规则 6a 缺设备号 / 6b 越界请求）。
 * 两者都是**正确行为**（路由直达 finalize、不重试、不降级），
 * 故前端不得按"诊断失败"呈现 —— 抽成纯函数以便单测锁住文案口径。
 */

import type { RefusalInfo } from "./types/thread";

/** 各类型的标题文案 */
const REFUSAL_TITLE: Record<RefusalInfo["kind"], string> = {
  clarification: "需要补充信息",
  refusal: "超出诊断职责范围",
};

/** 兜底文案（kind 非法/缺失时的安全值，避免空标题） */
export const REFUSAL_FALLBACK_TITLE = "未生成诊断结论";

export function refusalTitle(kind?: string | null): string {
  if (!kind) return REFUSAL_FALLBACK_TITLE;
  return REFUSAL_TITLE[kind as RefusalInfo["kind"]] ?? REFUSAL_FALLBACK_TITLE;
}

/** 是否属于拒答/澄清（无结论、无置信度语义） */
export function isRefusal(info?: RefusalInfo | null): boolean {
  return !!info && (info.kind === "clarification" || info.kind === "refusal");
}
