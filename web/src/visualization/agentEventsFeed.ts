/**
 * Cross-process agent-activity feed (polls the shared agent-events log).
 *
 * The WS feed (gatewayFeed.ts) only carries the dashboard chat PTY's events.
 * This feed instead polls `/api/visualization/agent-events`, which is backed by
 * the shared `agent_events.db` that EVERY agent writes to — chat, the platform
 * gateway (Telegram/WhatsApp), and cron/batch subprocesses. So this is what
 * makes the Visualization office cover all agents, not just the chat session.
 *
 * It exposes the same `GatewayFeed` interface as the WS feed, mapping each
 * stored row to a `tool.start` / `tool.complete` GatewayEvent, so the bridge,
 * activity feed, and graph consume it unchanged. Near-live (≈1.5s poll), which
 * is plenty for an office visualization.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchJSON } from "@/lib/api";

import type { GatewayEvent, GatewayFeed } from "./gatewayFeed";

interface AgentEventRow {
  id: number;
  ts: number;
  session_id: string;
  task_id?: string | null;
  tool_call_id?: string | null;
  kind: string;
  tool_name: string;
  summary?: string | null;
  ok?: number | null;
  subagent_id?: string | null;
  parent_id?: string | null;
  depth?: number | null;
  goal?: string | null;
}

function rowToEvent(r: AgentEventRow, id: number): GatewayEvent {
  const ts = r.ts ? r.ts * 1000 : Date.now();
  const sessionId = r.session_id || null;

  // Sub-agent lifecycle (delegate_task) — drives the office delegation tree.
  if (r.kind.startsWith("subagent.")) {
    return {
      id,
      type: r.kind,
      sessionId,
      payload: {
        subagent_id: r.subagent_id ?? undefined,
        parent_id: r.parent_id ?? undefined,
        depth: r.depth ?? undefined,
        goal: r.goal ?? undefined,
        tool_name: r.tool_name || undefined,
        text: r.summary ?? undefined,
      },
      ts,
    };
  }

  // Flat tool activity.
  const isStart = r.kind === "start";
  const toolId = r.tool_call_id ?? `ev-${String(r.id)}`;
  return {
    id,
    type: isStart ? "tool.start" : "tool.complete",
    sessionId,
    payload: isStart
      ? { tool_id: toolId, name: r.tool_name, context: r.summary ?? "" }
      : { tool_id: toolId, name: r.tool_name },
    ts,
  };
}

const POLL_MS = 1500;
const MAX_EVENTS = 500;

interface SessionMeta {
  title?: string;
  source?: string;
  model?: string;
}

export function useAgentEventsFeed(): GatewayFeed {
  const [events, setEvents] = useState<GatewayEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const listenersRef = useRef(new Set<(ev: GatewayEvent) => void>());
  const nextIdRef = useRef(1);
  const sinceRef = useRef(0);
  // Accumulated session_id -> {title, source, model} so events keep their meta
  // even when a later poll batch doesn't re-include it.
  const metaRef = useRef<Record<string, SessionMeta>>({});

  const subscribe = useCallback((cb: (ev: GatewayEvent) => void) => {
    listenersRef.current.add(cb);
    return () => {
      listenersRef.current.delete(cb);
    };
  }, []);

  useEffect(() => {
    let stopped = false;

    const poll = async () => {
      try {
        const res = await fetchJSON<{
          events?: AgentEventRow[];
          sessions?: Record<string, SessionMeta>;
        }>(`/api/visualization/agent-events?since_id=${String(sinceRef.current)}&limit=300`);
        if (stopped) return;
        setConnected(true);

        // Merge in session metadata (title/source/model) so we can label desks.
        if (res.sessions) Object.assign(metaRef.current, res.sessions);

        const allRows = res.events ?? [];
        if (allRows.length === 0) return;

        // Advance the cursor over ALL rows (so we don't re-fetch), but skip
        // rows with no session_id — they can't be attributed to a desk and
        // would render as a phantom "empty" agent (already filtered at the
        // writer too; this also covers rows logged before that fix).
        sinceRef.current = allRows.reduce((m, r) => Math.max(m, r.id), sinceRef.current);
        const rows = allRows.filter((r) => r.session_id);
        if (rows.length === 0) return;

        const mapped: GatewayEvent[] = rows.map((r) => {
          const ev = rowToEvent(r, nextIdRef.current++);
          const m = ev.sessionId ? metaRef.current[ev.sessionId] : undefined;
          if (m) {
            ev.payload.session_title = m.title ?? "";
            ev.payload.session_source = m.source ?? "";
            ev.payload.session_model = m.model ?? "";
          }
          return ev;
        });

        for (const ev of mapped) {
          for (const cb of listenersRef.current) {
            try {
              cb(ev);
            } catch {
              // a broken listener must not kill the feed
            }
          }
        }

        setEvents((prev) => {
          const overflow = prev.length + mapped.length - MAX_EVENTS;
          const base = overflow > 0 ? prev.slice(overflow) : prev.slice();
          base.push(...mapped);
          return base;
        });
      } catch {
        if (!stopped) setConnected(false);
      }
    };

    void poll();
    const t = setInterval(() => void poll(), POLL_MS);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, []);

  return { events, connected, subscribe };
}
