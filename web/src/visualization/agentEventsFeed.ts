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
}

const POLL_MS = 1500;
const MAX_EVENTS = 500;

export function useAgentEventsFeed(): GatewayFeed {
  const [events, setEvents] = useState<GatewayEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const listenersRef = useRef(new Set<(ev: GatewayEvent) => void>());
  const nextIdRef = useRef(1);
  const sinceRef = useRef(0);

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
        const res = await fetchJSON<{ events?: AgentEventRow[] }>(
          `/api/visualization/agent-events?since_id=${String(sinceRef.current)}&limit=300`,
        );
        if (stopped) return;
        setConnected(true);

        const rows = res.events ?? [];
        if (rows.length === 0) return;

        sinceRef.current = rows.reduce((m, r) => Math.max(m, r.id), sinceRef.current);

        const mapped: GatewayEvent[] = rows.map((r) => {
          const isStart = r.kind === "start";
          const toolId = r.tool_call_id ?? `ev-${String(r.id)}`;
          return {
            id: nextIdRef.current++,
            type: isStart ? "tool.start" : "tool.complete",
            sessionId: r.session_id || null,
            payload: isStart
              ? { tool_id: toolId, name: r.tool_name, context: r.summary ?? "" }
              : { tool_id: toolId, name: r.tool_name },
            ts: r.ts ? r.ts * 1000 : Date.now(),
          };
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
