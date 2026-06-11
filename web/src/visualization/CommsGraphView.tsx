/**
 * Communication & delegation graph.
 *
 * Builds a live node/edge graph from the gateway event feed:
 *   - one node per session/agent and per delegated subagent
 *   - delegation edges (parent agent → subagent) from subagent.* events
 *   - message edges (agent → agent) from inter-agent utterance events, when
 *     the inter-agent backend is emitting them
 *
 * Rendered as plain SVG (no graph lib) in a depth-layered layout: roots on
 * the left, each delegation level a column to the right. Active nodes pulse.
 */

import { useMemo } from "react";

import type { GatewayEvent, GatewayFeed } from "./gatewayFeed";

interface GNode {
  id: string;
  label: string;
  kind: "agent" | "subagent";
  depth: number;
  active: boolean;
}

interface GEdge {
  from: string;
  to: string;
  kind: "delegate" | "message";
  label?: string;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

export interface AgentMessage {
  id: number;
  from: string;
  to: string;
  text: string;
}

function buildGraph(
  events: GatewayEvent[],
  messages: AgentMessage[],
): { nodes: GNode[]; edges: GEdge[] } {
  const nodes = new Map<string, GNode>();
  const edges: GEdge[] = [];
  const edgeSeen = new Set<string>();

  const ensure = (id: string, label: string, kind: GNode["kind"], depth: number) => {
    const existing = nodes.get(id);
    if (existing) {
      if (label && existing.label.startsWith("Session")) existing.label = label;
      existing.depth = Math.min(existing.depth, depth);
      return existing;
    }
    const n: GNode = { id, label: label || id.slice(0, 8), kind, depth, active: false };
    nodes.set(id, n);
    return n;
  };

  const addEdge = (from: string, to: string, kind: GEdge["kind"], label?: string) => {
    const key = `${kind}:${from}->${to}`;
    if (edgeSeen.has(key)) return;
    edgeSeen.add(key);
    edges.push({ from, to, kind, label });
  };

  for (const ev of events) {
    const p = ev.payload;
    const sid = ev.sessionId ?? "main";

    if (ev.type === "subagent.spawn_requested" || ev.type === "subagent.start") {
      const subId = str(p.subagent_id) || `sub-${ev.id}`;
      const parentId = str(p.parent_id) || sid;
      const depth = typeof p.depth === "number" ? (p.depth as number) : 1;
      ensure(sid, "Chat", "agent", 0);
      if (parentId !== sid) ensure(parentId, "Subagent", "subagent", Math.max(0, depth - 1));
      ensure(subId, str(p.goal).slice(0, 20) || "Subagent", "subagent", depth).active = true;
      addEdge(parentId, subId, "delegate", str(p.goal).slice(0, 30));
    } else if (ev.type === "subagent.complete") {
      const subId = str(p.subagent_id);
      const n = subId ? nodes.get(subId) : undefined;
      if (n) n.active = false;
    } else if (ev.type === "subagent.tool" || ev.type === "subagent.thinking") {
      const subId = str(p.subagent_id);
      const n = subId ? nodes.get(subId) : undefined;
      if (n) n.active = true;
    } else if (ev.type === "agent.message" || ev.type === "inter_agent.utterance") {
      const from = str(p.from) || sid;
      const to = str(p.to);
      ensure(from, str(p.from_name) || "Agent", "agent", 0);
      if (to) {
        ensure(to, str(p.to_name) || "Agent", "agent", 0);
        addEdge(from, to, "message", str(p.text).slice(0, 30));
      }
    }
  }

  // Persisted peer-to-peer messages (agent_message tool → agent_comms.db).
  for (const m of messages) {
    if (!m.to) continue;
    ensure(m.from, m.from, "agent", 0);
    ensure(m.to, m.to, "agent", 0);
    addEdge(m.from, m.to, "message", m.text.slice(0, 30));
  }

  return { nodes: [...nodes.values()], edges };
}

interface CommsGraphViewProps {
  feed: GatewayFeed;
  messages?: AgentMessage[];
}

export function CommsGraphView({ feed, messages = [] }: CommsGraphViewProps) {
  const { nodes, edges } = useMemo(
    () => buildGraph(feed.events, messages),
    [feed.events, messages],
  );

  const layout = useMemo(() => {
    const byDepth = new Map<number, GNode[]>();
    for (const n of nodes) {
      const arr = byDepth.get(n.depth) ?? [];
      arr.push(n);
      byDepth.set(n.depth, arr);
    }
    const COL_W = 220;
    const ROW_H = 90;
    const pos = new Map<string, { x: number; y: number }>();
    const maxDepth = Math.max(0, ...nodes.map((n) => n.depth));
    for (let d = 0; d <= maxDepth; d++) {
      const col = byDepth.get(d) ?? [];
      col.forEach((n, i) => {
        pos.set(n.id, { x: 120 + d * COL_W, y: 70 + i * ROW_H });
      });
    }
    const width = 240 + maxDepth * COL_W;
    const height =
      70 + Math.max(1, ...[...byDepth.values()].map((c) => c.length)) * ROW_H + 30;
    return { pos, width, height };
  }, [nodes]);

  if (nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center rounded-lg border border-border bg-card/40 text-sm text-muted-foreground">
        No delegations or inter-agent messages yet. When an agent spawns a
        subagent or messages another agent, the graph appears here.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto rounded-lg border border-border bg-card/40 p-2">
      <svg
        width={layout.width}
        height={layout.height}
        className="min-h-full"
        role="img"
        aria-label="Agent communication graph"
      >
        <defs>
          <marker
            id="viz-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
          </marker>
        </defs>

        {edges.map((e, i) => {
          const a = layout.pos.get(e.from);
          const b = layout.pos.get(e.to);
          if (!a || !b) return null;
          const color = e.kind === "message" ? "rgb(251 191 36)" : "var(--color-primary)";
          return (
            <g key={`e-${i}`} style={{ color }}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="currentColor"
                strokeWidth={1.5}
                strokeDasharray={e.kind === "message" ? "4 3" : undefined}
                markerEnd="url(#viz-arrow)"
                opacity={0.7}
              />
            </g>
          );
        })}

        {nodes.map((n) => {
          const pt = layout.pos.get(n.id);
          if (!pt) return null;
          const fill =
            n.kind === "agent" ? "var(--color-primary)" : "rgb(245 158 11)";
          return (
            <g key={n.id} transform={`translate(${pt.x}, ${pt.y})`}>
              {n.active && (
                <circle r={18} fill={fill} opacity={0.25}>
                  <animate
                    attributeName="r"
                    values="14;22;14"
                    dur="1.4s"
                    repeatCount="indefinite"
                  />
                </circle>
              )}
              <circle r={12} fill={fill} stroke="rgba(0,0,0,0.4)" strokeWidth={1.5} />
              <text
                x={18}
                y={4}
                fill="var(--color-foreground)"
                fontSize={12}
                className="select-none"
              >
                {n.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
