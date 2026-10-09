"use client";

/**
 * StatusBar（底部状态条）：存储/推理健康与延迟 + 本地/云端路径指示。
 * 演示时的可信度锚点（§3.2）；D20 接 /api/health 聚合，当前为静态占位灯。
 */

import { useInspector } from "@/lib/store/inspector";

const SOURCES = [
  { name: "PostgreSQL", state: "unknown" },
  { name: "TDengine", state: "unknown" },
  { name: "Milvus", state: "unknown" },
  { name: "Neo4j", state: "unknown" },
  { name: "Ollama", state: "unknown" },
] as const;

const LAMP = {
  ok: "bg-health-ok",
  degraded: "bg-health-degraded",
  down: "bg-health-down",
  unknown: "bg-state-skipped",
} as const;

export function StatusBar() {
  const showInspector = useInspector((s) => s.show);

  return (
    <footer className="flex h-7 shrink-0 items-center gap-4 border-t border-edge-subtle bg-surface-base px-4 text-xs text-fg-tertiary">
      {SOURCES.map(({ name, state }) => (
        <button
          key={name}
          type="button"
          className="flex items-center gap-1.5 hover:text-fg-secondary"
          onClick={() =>
            showInspector({
              tab: "tool",
              title: `${name} 健康详情`,
              payload: { state },
            })
          }
        >
          <span className={`inline-block size-1.5 rounded-full ${LAMP[state]}`} aria-hidden />
          <span>{name}</span>
        </button>
      ))}
      <span className="ml-auto">推理路径：本地</span>
    </footer>
  );
}
