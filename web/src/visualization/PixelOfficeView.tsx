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
import { Maximize2, Minimize2 } from "lucide-react";
import { useNavigate } from "react-router-dom";

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
  /** Called with the session key when an agent is clicked inside the office,
   *  so the host can select it in the Agent Inspector dock. */
  onSelectAgent?: (sessionKey: string) => void;
}

export function PixelOfficeView({ feed, provider, onSelectAgent }: PixelOfficeViewProps) {
  const isPixelAgents = provider.protocol === "pixel-agents";
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [ready, setReady] = useState(false);
  // Modo teatro: la oficina ocupa toda la ventana (overlay fixed). El iframe
  // sigue montado en el mismo nodo — el canvas se re-mide solo (ResizeObserver
  // interno de pixel-agents), sin perder el estado del bridge.
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

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
        } else if (out.type === "openClaude") {
          // pixel-agents' "+ Agent" button posts {type:'openClaude'} to spawn a
          // VS Code Claude session — meaningless here. Repurpose it to jump to
          // the Chat section so the user can talk with an agent.
          navigate("/chat");
        } else if (out.type === "focusAgent" && typeof out.id === "number") {
          // Clicking an agent (sprite or overlay) posts focusAgent — translate
          // the office character id back to a session and select it in the dock.
          const key = bridge.sessionKeyForId(out.id);
          if (key) onSelectAgent?.(key);
        }
        // Other outbound types (saveAgentSeats, settings) are session-local.
      }
    };

    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [isPixelAgents, navigate, bridge, onSelectAgent]);

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
    // h-full (sin min-h de viewport): el host decide la altura — página
    // Visualization a pantalla completa o el panel lateral del chat. El
    // min-h chico evita colapsos mientras el flex del host se asienta.
    // En modo teatro pasa a overlay fixed a pantalla completa.
    <div
      className={
        expanded
          ? "fixed inset-0 z-50 overflow-hidden bg-background/95 p-2 backdrop-blur-sm"
          : "relative h-full min-h-[280px] w-full overflow-hidden rounded-xl border border-foreground/10 bg-black/30"
      }
    >
      {showLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-[#6C4FD6]" />
          Cargando oficina…
        </div>
      )}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        title={expanded ? "Salir de pantalla completa (Esc)" : "Expandir la oficina"}
        aria-label={expanded ? "Salir de pantalla completa" : "Expandir la oficina"}
        className="absolute right-2 top-2 z-20 rounded-md border border-border/60 bg-background/70 p-1.5 text-muted-foreground backdrop-blur transition-colors hover:text-foreground"
      >
        {expanded ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
      </button>
      <iframe
        ref={iframeRef}
        title={`${provider.label} office`}
        src={`${CLAWK_BASE_PATH}${provider.src}`}
        className={`h-full w-full border-0 ${expanded ? "rounded-lg" : ""}`}
        sandbox="allow-scripts allow-same-origin"
      />
    </div>
  );
}
