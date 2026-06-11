/**
 * Merge two GatewayFeeds (the chat WS feed + the cross-process poll feed) into
 * one, de-duplicating tool events that arrive on both.
 *
 * The dashboard chat session publishes tool events via BOTH the WS sidecar
 * (rich: also subagent.* / message.* events) and the shared agent-events log
 * (flat tool.start/complete). Those overlap on `tool.start`/`tool.complete`
 * with the SAME `tool_id` (the model's tool_call_id), so we dedupe by
 * `type:tool_id`. Events without a tool_id (subagent.*, message.*, clarify) are
 * WS-only and pass through untouched.
 *
 * Consumers (PixelBridge via subscribe, ActivityFeed/CommsGraph via events) see
 * a single de-duplicated stream.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { GatewayEvent, GatewayFeed } from "./gatewayFeed";

const MAX_EVENTS = 600;
// Cap the dedup memory so a long-lived view doesn't grow it without bound.
const SEEN_MAX = 4000;

function dedupKey(ev: GatewayEvent): string | null {
  const p = ev.payload as { tool_id?: unknown; subagent_id?: unknown };
  const toolId = p.tool_id;
  if (toolId !== undefined && toolId !== null && toolId !== "") {
    return `${ev.type}:${String(toolId)}`;
  }
  // Sub-agent start/complete arrive on both the WS feed and the poll log for
  // the chat session — dedupe by subagent id. (subagent.tool/thinking have no
  // stable id and the bridge tolerates the occasional repeat.)
  if (
    (ev.type === "subagent.start" || ev.type === "subagent.complete") &&
    p.subagent_id !== undefined &&
    p.subagent_id !== null &&
    p.subagent_id !== ""
  ) {
    return `${ev.type}:${String(p.subagent_id)}`;
  }
  return null;
}

export function useMergedFeed(a: GatewayFeed, b: GatewayFeed): GatewayFeed {
  const [events, setEvents] = useState<GatewayEvent[]>([]);
  const listenersRef = useRef(new Set<(ev: GatewayEvent) => void>());
  const seenRef = useRef<Set<string>>(new Set());
  const nextIdRef = useRef(1);

  const subscribe = useCallback((cb: (ev: GatewayEvent) => void) => {
    listenersRef.current.add(cb);
    return () => {
      listenersRef.current.delete(cb);
    };
  }, []);

  // Re-subscribe only when a child feed's subscribe identity changes (stable
  // useCallback in both feeds → this effect runs once).
  useEffect(() => {
    const onEvent = (ev: GatewayEvent) => {
      const key = dedupKey(ev);
      if (key) {
        if (seenRef.current.has(key)) return;
        seenRef.current.add(key);
        if (seenRef.current.size > SEEN_MAX) {
          // Cheap reset rather than LRU — a duplicate after this is harmless.
          seenRef.current = new Set();
        }
      }
      const merged: GatewayEvent = { ...ev, id: nextIdRef.current++ };
      for (const cb of listenersRef.current) {
        try {
          cb(merged);
        } catch {
          // a broken listener must not kill the feed
        }
      }
      setEvents((prev) => {
        const next = prev.length >= MAX_EVENTS ? prev.slice(-MAX_EVENTS + 1) : prev.slice();
        next.push(merged);
        return next;
      });
    };

    const unsubA = a.subscribe(onEvent);
    const unsubB = b.subscribe(onEvent);
    return () => {
      unsubA();
      unsubB();
    };
  }, [a.subscribe, b.subscribe]);

  return { events, connected: a.connected || b.connected, subscribe };
}
