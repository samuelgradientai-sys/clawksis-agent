/**
 * Live gateway-event feed for the Visualization section.
 *
 * Subscribes to the dashboard's event mirror (`/api/events?channel=<id>`,
 * see clawk_cli/web_server.py /api/pub + /api/events) and exposes the parsed
 * stream both as React state (ring buffer, for the activity feed / graph)
 * and as an imperative subscription (for the pixel-office bridge, which
 * needs every event in order, not snapshots).
 *
 * The wire format is the TUI gateway's JSON-RPC envelope, the same one
 * ChatSidebar consumes:
 *   { jsonrpc: "2.0", method: "event",
 *     params: { type: "tool.start", session_id?, payload: {...} } }
 *
 * Reconnects with capped backoff while a channel is set. Best-effort by
 * design — the publisher drops frames under pressure, so consumers must
 * tolerate missing tool.complete events (the bridge uses idle timers).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { buildWsAuthParam, CLAWK_BASE_PATH } from "@/lib/api";

export interface GatewayEvent {
  /** Monotonic id, local to this feed instance. */
  id: number;
  /** Event type, e.g. "tool.start", "subagent.complete", "message.start". */
  type: string;
  /** Gateway session id the event belongs to (when the gateway sends one). */
  sessionId: string | null;
  /** Raw event payload — shape varies per type. */
  payload: Record<string, unknown>;
  /** Client receive time (ms epoch). */
  ts: number;
}

interface RpcEnvelope {
  method?: string;
  params?: { type?: string; session_id?: string; payload?: unknown };
}

const MAX_EVENTS = 500;
const RECONNECT_BASE_MS = 1500;
const RECONNECT_MAX_MS = 15000;

export interface GatewayFeed {
  /** Ring buffer of recent events, newest last. */
  events: GatewayEvent[];
  /** True while the events WebSocket is open. */
  connected: boolean;
  /**
   * Register a raw-event listener (fires for every event, in order).
   * Returns an unsubscribe function. Stable across renders.
   */
  subscribe: (cb: (ev: GatewayEvent) => void) => () => void;
}

export function useGatewayFeed(channel: string | null): GatewayFeed {
  const [events, setEvents] = useState<GatewayEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const listenersRef = useRef(new Set<(ev: GatewayEvent) => void>());
  const nextIdRef = useRef(1);

  const subscribe = useCallback((cb: (ev: GatewayEvent) => void) => {
    listenersRef.current.add(cb);
    return () => {
      listenersRef.current.delete(cb);
    };
  }, []);

  useEffect(() => {
    if (!channel) {
      setConnected(false);
      return;
    }

    let disposed = false;
    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const connect = async () => {
      const [authName, authValue] = await buildWsAuthParam();
      if (!authValue || disposed) return;

      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const qs = new URLSearchParams({ [authName]: authValue, channel });
      ws = new WebSocket(
        `${proto}//${window.location.host}${CLAWK_BASE_PATH}/api/events?${qs.toString()}`,
      );

      ws.addEventListener("open", () => {
        if (disposed) return;
        attempt = 0;
        setConnected(true);
      });

      ws.addEventListener("message", (msgEv) => {
        let frame: RpcEnvelope;
        try {
          frame = JSON.parse(msgEv.data as string) as RpcEnvelope;
        } catch {
          return;
        }
        if (frame.method !== "event" || !frame.params?.type) return;

        const ev: GatewayEvent = {
          id: nextIdRef.current++,
          type: frame.params.type,
          sessionId: frame.params.session_id ?? null,
          payload:
            frame.params.payload && typeof frame.params.payload === "object"
              ? (frame.params.payload as Record<string, unknown>)
              : {},
          ts: Date.now(),
        };

        for (const cb of listenersRef.current) {
          try {
            cb(ev);
          } catch {
            // A broken listener must not kill the feed.
          }
        }

        // Skip high-frequency delta noise in the visible ring buffer; the
        // imperative listeners above still see everything.
        if (ev.type.endsWith(".delta")) return;

        setEvents((prev) => {
          const next = prev.length >= MAX_EVENTS ? prev.slice(-MAX_EVENTS + 1) : prev.slice();
          next.push(ev);
          return next;
        });
      });

      const scheduleRetry = () => {
        if (disposed || retryTimer) return;
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
        attempt += 1;
        retryTimer = setTimeout(() => {
          retryTimer = null;
          void connect();
        }, delay);
      };

      ws.addEventListener("close", (closeEv) => {
        setConnected(false);
        // 4401/4403 = auth rejection — retrying with the same credential
        // would loop forever; the page-level 401 reload guard handles it.
        if (!disposed && closeEv.code !== 4401 && closeEv.code !== 4403) {
          scheduleRetry();
        }
      });

      ws.addEventListener("error", () => {
        setConnected(false);
        scheduleRetry();
      });
    };

    void connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      try {
        ws?.close(1000);
      } catch {
        // already closed
      }
      setConnected(false);
    };
  }, [channel]);

  return { events, connected, subscribe };
}
