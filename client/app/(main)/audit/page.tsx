"use client";

/**
 * ⑥ 审计日志 /audit（仅系统管理员；P4-D16+ 随角色守卫生效，数据接入 D20）。
 * 追加型只读：无编辑、无删除入口（§11 禁忌 10）。
 */

import { ShieldCheck } from "lucide-react";
import { PageScaffold } from "@/components/layout/PageScaffold";
import { EmptyState } from "@/components/common/EmptyState";
import { AuthGate } from "@/components/auth/AuthGate";

export default function AuditPage() {
  return (
    <AuthGate roles={["sys_admin"]}>
      <PageScaffold
        title="审计日志"
        description="追加型只读 · 无编辑/删除入口 · 时间/操作人/角色/动作/对象/trace_id"
      >
        <EmptyState
          icon={ShieldCheck}
          title="暂无审计记录"
          reason="为什么空：系统操作将按时间追加写入；本页仅系统管理员可见。"
        />
      </PageScaffold>
    </AuthGate>
  );
}
