/**
 * ChatSidePanel — Visualización + Media integrados al chat moderno.
 *
 * La sección "Visualization" dejó de ser una página aparte del sidebar: ahora
 * vive acá, como panel lateral del chat, junto a una galería de media para
 * mirar todo el contenido generado (imágenes/videos) sin salir de la
 * conversación.
 *
 *   - Visualización: Pixel Office / Actividad / Grafo — mismos componentes de
 *     web/src/visualization, alimentados por el feed cross-process
 *     (/api/events) + el canal PTY si hay uno publicado.
 *   - Media: galería compacta sobre /api/gallery/* (misma data que la página
 *     Media), con lightbox y descarga.
 */

import { useEffect, useState } from "react";
import {
  Download,
  ExternalLink,
  Image as ImageIcon,
  Loader2,
  RefreshCw,
  Video,
  X,
} from "lucide-react";

import { api, fetchJSON } from "@/lib/api";
import type { MediaItem } from "@/lib/api";
import { useActiveEventChannel } from "@/lib/eventChannelStore";

import { ActivityFeedView } from "../../visualization/ActivityFeedView";
import type { AgentMessage } from "../../visualization/CommsGraphView";
import { CommsGraphView } from "../../visualization/CommsGraphView";
import { useAgentEventsFeed } from "../../visualization/agentEventsFeed";
import { useGatewayFeed } from "../../visualization/gatewayFeed";
import { useMergedFeed } from "../../visualization/mergedFeed";
import {
  getOfficeProvider,
  loadOfficeProviderId,
  OFFICE_PROVIDERS,
  saveOfficeProviderId,
} from "../../visualization/officeProviders";
import { PixelOfficeView } from "../../visualization/PixelOfficeView";

export type SidePanelTab = "viz" | "media";

const MSG_POLL_MS = 6000;

type VisualId = "office" | "activity" | "graph";

const VISUALS: { id: VisualId; label: string; hint: string }[] = [
  { id: "office", label: "Oficina", hint: "Agentes como personajes usando sus herramientas" },
  { id: "activity", label: "Actividad", hint: "Stream en vivo de tool calls" },
  { id: "graph", label: "Grafo", hint: "Delegaciones y mensajes entre agentes" },
];

function mediaUrl(item: MediaItem): string {
  return `/media/file/${item.id}`;
}

// ── Visualización ────────────────────────────────────────────────────────────

function VisualizationPanel() {
  const channel = useActiveEventChannel();
  const wsFeed = useGatewayFeed(channel);
  const pollFeed = useAgentEventsFeed();
  const feed = useMergedFeed(wsFeed, pollFeed);
  const [active, setActive] = useState<VisualId>("office");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [officeProviderId, setOfficeProviderId] = useState<string>(loadOfficeProviderId);
  const officeProvider = getOfficeProvider(officeProviderId);

  // P2P persistidos para el grafo, sólo mientras está visible.
  useEffect(() => {
    if (active !== "graph") return;
    let stopped = false;
    const poll = async () => {
      if (document.hidden) return;
      try {
        const res = await fetchJSON<{ messages?: AgentMessage[] }>(
          "/api/visualization/agent-messages?limit=200",
        );
        if (!stopped) setMessages(res.messages ?? []);
      } catch {
        // Endpoint puede no existir en servers viejos.
      }
    };
    void poll();
    const t = setInterval(() => void poll(), MSG_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [active]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      <div className="flex items-center gap-1.5">
        {VISUALS.map((v) => (
          <button
            key={v.id}
            type="button"
            onClick={() => setActive(v.id)}
            title={v.hint}
            className={`rounded-md border px-2 py-1 text-xs transition-colors ${
              active === v.id
                ? "border-[#6C4FD6]/60 bg-[#6C4FD6]/15 text-foreground"
                : "border-border/60 bg-card/30 text-muted-foreground hover:text-foreground"
            }`}
          >
            {v.label}
          </button>
        ))}
        <span
          title={feed.connected ? "En vivo" : "Conectando…"}
          className={`ml-auto inline-block h-2 w-2 rounded-full ${
            feed.connected ? "bg-emerald-500" : "bg-muted-foreground/50"
          }`}
        />
      </div>

      {active === "office" && (
        <div className="flex min-h-0 flex-1 flex-col gap-1.5">
          <select
            value={officeProviderId}
            onChange={(e) => {
              setOfficeProviderId(e.target.value);
              saveOfficeProviderId(e.target.value);
            }}
            aria-label="Visual de la oficina"
            className="self-start rounded-md border border-border/60 bg-card/40 px-1.5 py-0.5 text-[11px] text-muted-foreground"
          >
            {OFFICE_PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
          <div className="min-h-0 flex-1">
            <PixelOfficeView
              key={officeProvider.id}
              provider={officeProvider}
              feed={feed}
            />
          </div>
        </div>
      )}
      {active === "activity" && (
        <div className="min-h-0 flex-1 overflow-hidden">
          <ActivityFeedView feed={feed} />
        </div>
      )}
      {active === "graph" && (
        <div className="min-h-0 flex-1 overflow-hidden">
          <CommsGraphView feed={feed} messages={messages} />
        </div>
      )}
    </div>
  );
}

// ── Media ────────────────────────────────────────────────────────────────────

const MEDIA_PAGE_SIZE = 30;

function MediaPanel() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<"image" | "video" | undefined>();
  const [lightbox, setLightbox] = useState<MediaItem | null>(null);

  const load = async (opts: { append?: boolean } = {}) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getGalleryMedia({
        media_type: typeFilter,
        limit: MEDIA_PAGE_SIZE,
        offset: opts.append ? items.length : 0,
      });
      setItems((prev) => (opts.append ? [...prev, ...res.items] : res.items));
      setTotal(res.total);
      setHasMore(res.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  // Recarga al abrir y al cambiar el filtro de tipo. El primer setState queda
  // detrás de un await para no encadenar renders sincrónicos desde el efecto.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) return;
      setLoading(true);
      setError(null);
      try {
        const res = await api.getGalleryMedia({
          media_type: typeFilter,
          limit: MEDIA_PAGE_SIZE,
          offset: 0,
        });
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
        setHasMore(res.has_more);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [typeFilter]);

  useEffect(() => {
    if (!lightbox) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setLightbox(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [lightbox]);

  const chip = (label: string, value?: "image" | "video") => (
    <button
      type="button"
      onClick={() => setTypeFilter(value)}
      className={`rounded-md border px-2 py-1 text-xs transition-colors ${
        typeFilter === value
          ? "border-[#6C4FD6]/60 bg-[#6C4FD6]/15 text-foreground"
          : "border-border/60 bg-card/30 text-muted-foreground hover:text-foreground"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      <div className="flex items-center gap-1.5">
        {chip("Todo", undefined)}
        {chip("Imágenes", "image")}
        {chip("Videos", "video")}
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          aria-label="Refrescar galería"
          className="ml-auto rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground disabled:opacity-40"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
          {error}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading && items.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1.5 text-muted-foreground">
            <ImageIcon className="size-8 opacity-30" />
            <p className="text-xs">Todavía no hay media generada</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-1.5 xl:grid-cols-3">
            {items.map((item) => {
              const broken = item.status !== "ready";
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setLightbox(item)}
                  title={item.prompt ?? undefined}
                  className="group relative aspect-square overflow-hidden rounded-md border border-border/60 bg-card/30 transition-colors hover:border-[#6C4FD6]/60"
                >
                  {broken ? (
                    <div className="flex h-full w-full items-center justify-center text-muted-foreground">
                      <ImageIcon className="size-6 opacity-40" />
                    </div>
                  ) : item.media_type === "video" ? (
                    <>
                      <video
                        src={mediaUrl(item)}
                        className="h-full w-full object-cover"
                        preload="metadata"
                        muted
                      />
                      <span className="absolute right-1 top-1 rounded bg-black/70 p-0.5">
                        <Video className="size-3 text-white" />
                      </span>
                    </>
                  ) : (
                    <img
                      src={mediaUrl(item)}
                      alt={item.prompt ?? "Media generada"}
                      loading="lazy"
                      className="h-full w-full object-cover"
                    />
                  )}
                </button>
              );
            })}
          </div>
        )}

        {hasMore && (
          <div className="flex justify-center py-2">
            <button
              type="button"
              onClick={() => void load({ append: true })}
              disabled={loading}
              className="rounded-md border border-border/60 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
            >
              Cargar más ({total - items.length})
            </button>
          </div>
        )}
      </div>

      {lightbox && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setLightbox(null)}
        >
          <div
            className="relative flex max-h-[90vh] w-full max-w-3xl flex-col gap-2 overflow-hidden rounded-lg border border-border bg-popover p-3"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setLightbox(null)}
              aria-label="Cerrar"
              className="absolute right-2 top-2 z-10 rounded-full bg-background/70 p-1 hover:bg-background"
            >
              <X className="size-4" />
            </button>
            <div className="flex min-h-0 flex-1 items-center justify-center overflow-hidden rounded bg-background/60">
              {lightbox.media_type === "video" ? (
                <video src={mediaUrl(lightbox)} controls className="max-h-[70vh] max-w-full" />
              ) : (
                <img
                  src={mediaUrl(lightbox)}
                  alt={lightbox.prompt ?? "Media generada"}
                  className="max-h-[70vh] max-w-full object-contain"
                />
              )}
            </div>
            {lightbox.prompt && (
              <p className="line-clamp-2 text-xs text-muted-foreground">{lightbox.prompt}</p>
            )}
            <div className="flex items-center gap-2">
              <a
                href={mediaUrl(lightbox)}
                download
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-muted/40"
              >
                <Download className="size-3.5" />
                Descargar
              </a>
              <a
                href={mediaUrl(lightbox)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-muted/40"
              >
                <ExternalLink className="size-3.5" />
                Abrir
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Panel contenedor ─────────────────────────────────────────────────────────

export function ChatSidePanel({
  tab,
  onSelectTab,
  onClose,
}: {
  tab: SidePanelTab;
  onSelectTab: (tab: SidePanelTab) => void;
  onClose: () => void;
}) {
  return (
    <aside className="absolute inset-y-0 right-0 z-20 flex w-[88vw] max-w-[26rem] flex-col border-l border-border/60 bg-background/80 backdrop-blur-xl lg:static lg:z-auto lg:w-[24rem] lg:bg-background/40 xl:w-[27rem]">
      <div className="flex items-center gap-1 border-b border-border/60 px-2 py-2">
        <button
          type="button"
          onClick={() => onSelectTab("viz")}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            tab === "viz"
              ? "bg-[#6C4FD6]/15 text-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Visualización
        </button>
        <button
          type="button"
          onClick={() => onSelectTab("media")}
          className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
            tab === "media"
              ? "bg-[#6C4FD6]/15 text-foreground"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Media
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar panel"
          className="ml-auto rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>
      {tab === "viz" ? <VisualizationPanel /> : <MediaPanel />}
    </aside>
  );
}
