"use client";

/**
 * 图谱 hooks（P4-D17）：GET /api/graph/neighbors?entity=&hops=
 * 降级口径：Neo4j 不可达 → degraded=true（展示「图谱暂不可用」，不打断监盘）。
 */

import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";

export interface GraphNode {
  id: string;         // Neo4j elementId
  entity_id: string;
  name: string;
  type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  chunk_ids: string[];
  confidence: number | null;
  source_count: number | null;
}

export interface GraphNeighborsData {
  entity: string;
  hops: number;
  degraded: boolean;
  reason: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  latency_ms: number;
}

export function useGraphNeighbors(entity: string | null, hops: number) {
  return useQuery<GraphNeighborsData>({
    queryKey: ["graph-neighbors", entity, hops],
    queryFn: () =>
      request<GraphNeighborsData>(
        `/api/graph/neighbors?entity=${encodeURIComponent(entity!)}&hops=${hops}`,
      ),
    enabled: !!entity,
    staleTime: 30_000,
    retry: 1,
  });
}
