"use client";

/**
 * 图谱探索（P4-D17）：react-force-graph-2d 懒加载 + 实体精确查询 + 跳数/关系过滤 + 节点检查器。
 * 后端契约 GET /api/graph/neighbors（D0-2 契约4）：degraded=true 时展示降级横幅不打断监盘。
 * 渲染保护：默认 hops≤2；关系过滤为客户端过滤（受控关系白名单由后端约束）。
 */

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Share2, Search } from "lucide-react";
import { PageScaffold, KpiCard } from "@/components/layout/PageScaffold";
import { EmptyState } from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useGraphNeighbors, type GraphEdge, type GraphNode } from "@/hooks/useGraph";
import { ApiError } from "@/lib/api";

// force-graph 依赖 window/canvas → 关 SSR 懒加载
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const NODE_COLORS: Record<string, string> = {
  device: "#60a5fa",
  component: "#34d399",
  failure_mode: "#f87171",
  symptom: "#fbbf24",
  metric: "#a78bfa",
};
const DEFAULT_COLOR = "#94a3b8";

// 节点标签色随主题：canvas 不支持 var()，故解析语义槽位 --text-primary 的实际值（暗/明主题均满足对比度）
let cachedLabelColor: string | null = null;
function labelColor() {
  if (cachedLabelColor === null) {
    cachedLabelColor =
      getComputedStyle(document.documentElement).getPropertyValue("--text-primary").trim() || "#182029";
  }
  return cachedLabelColor;
}

export function GraphExplorer({ initialEntity }: { initialEntity?: string | null }) {
  const [input, setInput] = useState(initialEntity ?? "");
  const [entity, setEntity] = useState<string | null>(initialEntity ?? null);
  const [hops, setHops] = useState(2);
  const [relFilter, setRelFilter] = useState<string>("all");
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const { data, isPending, isError, error } = useGraphNeighbors(entity, hops);

  const relations = useMemo(
    () => Array.from(new Set((data?.edges ?? []).map((e) => e.relation))).sort(),
    [data],
  );

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const edges = relFilter === "all" ? data.edges : data.edges.filter((e) => e.relation === relFilter);
    const used = new Set<string>();
    for (const e of edges) { used.add(e.source); used.add(e.target); }
    // 保留起始节点 + 过滤后涉及的节点
    const nodes = data.nodes.filter((n) => used.has(n.id) || n.name === data.entity);
    return { nodes, links: edges };
  }, [data, relFilter]);

  const notFound = isError && error instanceof ApiError && error.code === "E_NOT_FOUND";

  const search = () => {
    const v = input.trim();
    if (v) { setEntity(v); setSelected(null); }
  };

  return (
    <PageScaffold
      title="图谱探索"
      description="关系证据可探索；实体精确匹配，跳数 ≤2，单次边数上限 400（渲染保护）"
      toolbar={
        <div className="flex items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="graph-entity" className="text-xs">起始实体（精确名称）</Label>
            <Input
              id="graph-entity"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
              placeholder="如：给水泵A"
              className="w-48"
              maxLength={64}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">跳数</Label>
            <Select value={String(hops)} onValueChange={(v) => setHops(Number(v))}>
              <SelectTrigger size="sm" className="w-20" aria-label="跳数">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">1 跳</SelectItem>
                <SelectItem value="2">2 跳</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">关系过滤</Label>
            <Select value={relFilter} onValueChange={setRelFilter}>
              <SelectTrigger size="sm" className="w-36" aria-label="关系过滤">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部关系</SelectItem>
                {relations.map((r) => (
                  <SelectItem key={r} value={r}>{r}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button size="sm" onClick={search} disabled={!input.trim()} data-testid="graph-search-btn">
            <Search className="mr-1 size-4" />
            查询
          </Button>
        </div>
      }
      kpis={
        <div className="grid grid-cols-4 gap-3">
          <KpiCard label="节点" value={graphData.nodes.length} />
          <KpiCard label="关系边" value={graphData.links.length} />
          <KpiCard label="关系类型" value={relations.length} />
          <KpiCard label="查询耗时" value={data ? `${data.latency_ms}ms` : "—"} />
        </div>
      }
    >
      {!entity && (
        <EmptyState
          icon={Share2}
          title="输入起始实体开始探索"
          reason="为什么空：在上方输入实体精确名称（如设备/部件/故障模式），或从报告页「从当前报告载入」。"
        />
      )}

      {entity && isPending && <Skeleton className="h-96 w-full" />}

      {entity && notFound && (
        <EmptyState
          icon={Share2}
          title={`图谱中未找到实体「${entity}」`}
          reason="实体名需与图谱精确一致；可检查大小写或从报告证据卡片跳转。"
        />
      )}

      {entity && isError && !notFound && (
        <EmptyState
          icon={Share2}
          title="图谱查询失败"
          reason={`${(error as Error).message}（请重试）`}
        />
      )}

      {data?.degraded && (
        <div
          className="mb-3 rounded-lg border border-risk-medium-edge bg-risk-medium-surface px-4 py-2 text-sm text-risk-medium-text"
          data-testid="graph-degraded-banner"
        >
          图谱暂不可用（已降级）：{data.reason}。实体/关系数据来自 Neo4j，当前不可达不影响其他功能。
        </div>
      )}

      {data && !data.degraded && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
          <div
            className="overflow-hidden rounded-lg border border-edge-subtle bg-surface-raised"
            data-testid="graph-canvas"
          >
            {graphData.nodes.length === 0 ? (
              <EmptyState
                icon={Share2}
                title="该实体在当前过滤下无关联关系"
                reason="可切换关系过滤为「全部关系」或增加跳数。"
              />
            ) : (
              <ForceGraph2D
                graphData={graphData as { nodes: object[]; links: object[] }}
                nodeId="id"
                nodeLabel={(n) => `${(n as GraphNode).name}（${(n as GraphNode).type}）`}
                nodeCanvasObject={(n, ctx, scale) => {
                  const node = n as GraphNode & { x?: number; y?: number };
                  const label = node.name;
                  const fontSize = Math.max(10 / scale, 2.5);
                  const r = 5;
                  ctx.beginPath();
                  ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
                  ctx.fillStyle = NODE_COLORS[node.type] ?? DEFAULT_COLOR;
                  ctx.fill();
                  ctx.font = `${fontSize}px sans-serif`;
                  ctx.textAlign = "center";
                  ctx.fillStyle = labelColor();
                  ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + r + fontSize);
                }}
                linkLabel={(l) => {
                  const e = l as unknown as GraphEdge;
                  return `${e.relation}${e.confidence != null ? ` · 置信度 ${Number(e.confidence).toFixed(2)}` : ""}`;
                }}
                linkColor={() => "#475569"}
                linkDirectionalArrowLength={4}
                onNodeClick={(n) => setSelected(n as GraphNode)}
                width={undefined}
                height={480}
              />
            )}
          </div>

          <aside className="rounded-lg border border-edge-subtle bg-surface-raised p-3" data-testid="graph-inspector">
            <h3 className="mb-2 text-sm font-medium text-fg-primary">节点检查器</h3>
            {selected ? (
              <dl className="flex flex-col gap-1.5 text-xs">
                <div><dt className="text-fg-tertiary">名称</dt><dd className="text-fg-primary">{selected.name}</dd></div>
                <div><dt className="text-fg-tertiary">类型</dt><dd className="text-fg-primary">{selected.type || "—"}</dd></div>
                <div><dt className="text-fg-tertiary">实体 ID</dt><dd className="font-mono text-fg-primary">{selected.entity_id || "—"}</dd></div>
                <div>
                  <dt className="text-fg-tertiary">关联关系</dt>
                  <dd className="text-fg-primary">
                    {data.edges.filter((e) => e.source === selected.id || e.target === selected.id).length} 条
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="text-xs text-fg-tertiary">点击图中节点查看详情。</p>
            )}
          </aside>
        </div>
      )}
    </PageScaffold>
  );
}
