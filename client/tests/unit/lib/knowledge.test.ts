/** D16 知识库类型归一与 RBAC 口径单测 */

import { describe, expect, it } from "vitest";
import {
  normalizeDocStatus,
  normalizeAdmission,
  DOC_STATUS_LABEL,
  ADMISSION_LABEL,
} from "@/lib/types/knowledge";

describe("normalizeDocStatus", () => {
  it("已知值原样返回", () => {
    expect(normalizeDocStatus("indexed")).toBe("indexed");
    expect(normalizeDocStatus("failed")).toBe("failed");
    expect(normalizeDocStatus("pending")).toBe("pending");
  });

  it("未知值回退 pending（防御）", () => {
    expect(normalizeDocStatus("archived")).toBe("pending");
    expect(normalizeDocStatus("")).toBe("pending");
  });
});

describe("normalizeAdmission", () => {
  it("已知值原样返回", () => {
    expect(normalizeAdmission("approved")).toBe("approved");
    expect(normalizeAdmission("rejected")).toBe("rejected");
  });

  it("未知值回退 pending", () => {
    expect(normalizeAdmission("unknown")).toBe("pending");
  });
});

describe("标签映射完备性", () => {
  it("三种索引状态均有中文标签", () => {
    for (const s of ["pending", "indexed", "failed"] as const) {
      expect(DOC_STATUS_LABEL[s]).toBeTruthy();
    }
  });

  it("三种准入状态均有中文标签", () => {
    for (const s of ["pending", "approved", "rejected"] as const) {
      expect(ADMISSION_LABEL[s]).toBeTruthy();
    }
  });
});
