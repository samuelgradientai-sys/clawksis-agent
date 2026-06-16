/**
 * Office visual — a swappable iframe office visualizer (default: the vendored
 * pixel-agents webview), fed with REAL Clawksis gateway events via PixelBridge.
 *
 * The provider is selectable (see officeProviders.ts). Only providers that
 * speak the pixel-agents postMessage protocol get the live event bridge +
 * layout persistence; other providers render as a plain iframe.
 *
 * Pixel-agents lifecycle:
 *  1. iframe loads the provider index.html (browser runtime → browserMock loads
 *     sprites + default layout, then posts {__pixelAgentsReady} up to us).
 *  2. We fetch the saved office layout (GET /api/visualization/layout) and post
 *     a layoutLoaded override into the iframe.
 *  3. PixelBridge translates the live event feed into pixel-agents messages
 *     (queued until ready, then flushed in order).
 *  4. Outbound webview messages arrive as {__pixelAgentsOut}; saveLayout is
 *     persisted via PUT /api/visualization/layout so the office editor works.
 *
 * The parent re-mounts this component on provider change (via `key`), so refs
 * and the bridge always start fresh for a new provider.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { CLAWK_BASE_PATH, fetchJSON } from "@/lib/api";

import type { GatewayFeed } from "./gatewayFeed";
import type { OfficeProvider } from "./officeProviders";
import { PixelBridge } from "./pixelBridge";

const ROSTER_POLL_MS = 7000;
const ROSTER_LIMIT = 10;

// Roster = show *other* active sessions (Telegram/WhatsApp/cron) as idle desks.
// Disabled for now: today only the dashboard-chat PTY publishes events, and that
// same session ALSO appears in /api/sessions — but the event stream's session_id
// can't be reliably correlated to the /api/sessions id, so enabling the roster
// risks a duplicate desk for the live chat. Re-enable once the backend exposes a
// session id shared between the event feed and the roster.
const ENABLE_ROSTER = false;

interface SessionRow {
  id?: string;
  session_id?: string;
  title?: string;
  preview?: string;
  source?: string;
  is_active?: boolean;
}

interface PixelOfficeViewProps {
  feed: GatewayFeed;
  provider: OfficeProvider;
}

export function PixelOfficeView({ feed, provider }: PixelOfficeViewProps) {
  const isPixelAgents = provider.protocol === "pixel-agents";
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [ready, setReady] = useState(false);

  // Post-or-queue transport: pixel messages sent before the iframe finishes its
  // asset/layout boot are buffered and flushed on the ready signal.
  const queueRef = useRef<Array<Record<string, unknown>>>([]);
  const readyRef = useRef(false);

  const bridge = useMemo(
    () =>
      new PixelBridge((msg) => {
        if (readyRef.current) {
          iframeRef.current?.contentWindow?.postMessage(msg, "*");
        } else {
          queueRef.current.push(msg);
        }
      }),
    [],
  );

  // Window message handler: iframe → host (ready signal + outbound shim).
  useEffect(() => {
    if (!isPixelAgents) return;
    const onMessage = (ev: MessageEvent) => {
      const data = ev.data as Record<string, unknown> | null;
      if (!data || typeof data !== "object") return;
      if (ev.source !== iframeRef.current?.contentWindow) return;

      if (data.__pixelAgentsReady) {
        void (async () => {
          // Layout override BEFORE live agents so seats land correctly.
          try {
            const saved = await fetchJSON<{ layout: unknown }>("/api/visualization/layout");
            if (saved?.layout) {
              iframeRef.current?.contentWindow?.postMessage(
                { type: "layoutLoaded", layout: saved.layout },
                "*",
              );
            }
          } catch {
            // No saved layout (404) or transient error — default stays.
          }
          readyRef.current = true;
          setReady(true);
          for (const queued of queueRef.current) {
            iframeRef.current?.contentWindow?.postMessage(queued, "*");
          }
          queueRef.current = [];
        })();
        return;
      }

      const out = data.__pixelAgentsOut as Record<string, unknown> | undefined;
      if (out && typeof out === "object") {
        if (out.type === "saveLayout" && out.layout) {
          void fetchJSON("/api/visualization/layout", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ layout: out.layout }),
          }).catch(() => {
            // Best-effort persistence; the in-iframe layout still applies.
          });
        }
        // Other outbound types (saveAgentSeats, settings) are session-local.
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [isPixelAgents]);

  // Live events → bridge.
  useEffect(() => {
    if (!isPixelAgents) return;
    return feed.subscribe((ev) => bridge.handleEvent(ev));
  }, [isPixelAgents, feed, bridge]);

  // Roster poll: show active sessions as present characters.
  useEffect(() => {
    if (!isPixelAgents || !ENABLE_ROSTER) return;
    let stopped = false;

    const poll = async () => {
      try {
        const res = await fetchJSON<{ sessions?: SessionRow[] } | SessionRow[]>(
          `/api/sessions?limit=${ROSTER_LIMIT}&order=recent`,
        );
        if (stopped) return;
        const rows = Array.isArray(res) ? res : (res.sessions ?? []);
        const roster = rows
          .filter((s) => s.is_active)
          .map((s) => {
            const key = s.id ?? s.session_id ?? "";
            const label =
              (s.title || s.preview || "").trim().slice(0, 24) ||
              (s.source ? `${s.source}` : `Session ${key.slice(0, 6)}`);
            return { key, label };
          })
          .filter((s) => s.key);
        bridge.syncRoster(roster);
      } catch {
        // Roster is cosmetic; ignore transient failures.
      }
    };

    void poll();
    const t = setInterval(() => void poll(), ROSTER_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [isPixelAgents, bridge]);

  useEffect(() => () => bridge.dispose(), [bridge]);

  const showLoading = isPixelAgents && !ready;

  return (
    <div className="relative h-full min-h-[70vh] w-full overflow-hidden rounded-lg border border-border bg-black/40">
      {showLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center text-sm text-muted-foreground">
          Loading office…
        </div>
      )}
      <iframe
        ref={iframeRef}
        title={`${provider.label} office`}
        src={`${CLAWK_BASE_PATH}${provider.src}`}
        className="h-full w-full border-0"
        sandbox="allow-scripts allow-same-origin"
      />
    </div>
  );
}
