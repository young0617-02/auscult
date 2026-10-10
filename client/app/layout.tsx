import type { Metadata } from "next";
import { AppProviders } from "@/components/providers/AppProviders";
import "./globals.css";

export const metadata: Metadata = {
  title: "工业设备诊断 Agent",
  description: "云侧工业 IoT 诊断 Agent 系统 · 告警监盘 / 诊断 / 审核工作台",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // 明色为当前默认（tokens.css 提供 [data-theme="light"] 全套语义槽位）；
    // 暗色为工业中控原默认（UI 方案 §9.1），换肤仍只切 data-theme 属性
    <html lang="zh-CN" data-theme="light" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full flex flex-col">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
