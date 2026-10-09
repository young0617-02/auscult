import { ReportDetail } from "@/components/features/ReportDetail";

/** cacheComponents 要求 generateStaticParams 至少返回一项（占位，运行时由真实路由参数驱动） */
export function generateStaticParams() {
  return [{ id: "placeholder" }];
}

/** 报告详情 + 审核（/reports/[id]，P4-D11~D15） */
export default async function ReportDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ReportDetail reportId={id} />;
}
