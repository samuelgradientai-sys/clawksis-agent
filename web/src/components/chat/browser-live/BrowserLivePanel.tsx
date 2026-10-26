/** "Navegador" side panel: the agent's browser, live, with the page it is on and what it just did.
 *  "Tomar control" forwards clicks, scroll and typing to that same browser (pair browsing). */

import { useState } from "react";
import { Globe, Hand, MousePointerClick } from "lucide-react";
import { useBrowserActions, usePreferredBrowserKey } from "./browserLiveStore";
import { actionLabel, keyboardEvent, mouseEvent, toViewport, wheelEvent } from "./liveInput";
import { useLiveBrowser, type LiveBrowser, type LiveState } from "./useLiveBrowser";

const STATE_COPY: Record<LiveState, { label: string; dot: string }> = {
  live: { label: "En vivo", dot: "bg-emerald-400 animate-pulse" },
  connecting: { label: "Conectando…", dot: "bg-amber-400" },
  searching: { label: "Sin navegador abierto", dot: "bg-muted-foreground/50" },
  ended: { label: "Terminado", dot: "bg-muted-foreground/50" },
};

function StatusBar({ live, control, onToggle }: { live: LiveBrowser; control: boolean; onToggle: () => void }) {
  const copy = STATE_COPY[live.state];
  return (
    <div className="flex items-center gap-2 px-3 pt-3">
      <span className="flex items-center gap-1.5 rounded-full border border-border/60 px-2 py-0.5 text-[11px] text-muted-foreground">
        <span className={`size-1.5 rounded-full ${copy.dot}`} />
        {copy.label}
      </span>
      {live.state === "live" && (
        <button
          type="button"
          onClick={onToggle}
          aria-pressed={control}
          className={`ml-auto flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors ${
            control
              ? "border-[#6C4FD6] bg-[#6C4FD6]/20 text-foreground"
              : "border-border/60 text-muted-foreground hover:text-foreground"
          }`}
        >
          <Hand className="size-3.5" />
          {control ? "Devolver control" : "Tomar control"}
        </button>
      )}
    </div>
  );
}

function AddressBar({ live }: { live: LiveBrowser }) {
  if (!live.tab) return null;
  return (
    <div className="mx-3 mt-2 flex min-w-0 items-center gap-2 rounded-lg border border-border/60 bg-muted/20 px-2.5 py-1.5">
      <Globe className="size-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        {live.tab.title && <p className="truncate text-xs font-medium">{live.tab.title}</p>}
        <p className="truncate font-mono text-[11px] text-muted-foreground">{live.tab.url}</p>
      </div>
    </div>
  );
}

function Viewport({ live, control }: { live: LiveBrowser; control: boolean }) {
  const frame = live.frame;
  if (!frame) return null;
  const point = (e: React.MouseEvent<HTMLImageElement>) =>
    toViewport(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect(), frame.meta);
  const onPointer = (eventType: "mousePressed" | "mouseReleased") => (e: React.PointerEvent<HTMLImageElement>) => {
    const p = control ? point(e) : null;
    if (p) live.send(mouseEvent(eventType, p, e));
  };
  const onWheel = (e: React.WheelEvent<HTMLImageElement>) => {
    const p = control ? point(e) : null;
    if (p) live.send(wheelEvent(p, e.deltaX, e.deltaY));
  };
  const onKey = (eventType: "keyDown" | "keyUp") => (e: React.KeyboardEvent) => {
    if (!control) return;
    e.preventDefault();
    live.send(keyboardEvent(eventType, e));
  };
  return (
    <div
      tabIndex={control ? 0 : -1}
      onKeyDown={onKey("keyDown")}
      onKeyUp={onKey("keyUp")}
      className={`relative mx-3 mt-2 overflow-hidden rounded-xl border bg-black/40 outline-none ${
        control ? "border-[#6C4FD6] ring-2 ring-[#6C4FD6]/40" : "border-border/60"
      } ${live.state === "ended" ? "opacity-60 grayscale-[40%]" : ""}`}
      style={{ aspectRatio: `${frame.meta.deviceWidth} / ${frame.meta.deviceHeight}` }}
    >
      <img
        src={frame.src}
        alt={live.tab?.title || "Navegador del agente"}
        draggable={false}
        onPointerDown={onPointer("mousePressed")}
        onPointerUp={onPointer("mouseReleased")}
        onWheel={onWheel}
        onContextMenu={(e) => control && e.preventDefault()}
        className={`size-full select-none object-contain ${control ? "cursor-pointer" : "cursor-default"}`}
      />
    </div>
  );
}

function ActionFeed() {
  const actions = useBrowserActions();
  if (!actions.length) return null;
  return (
    <ol className="mx-3 mt-3 space-y-1" aria-label="Acciones recientes del agente">
      {[...actions].reverse().map((action, i) => (
        <li
          key={`${i}-${action}`}
          className={`flex items-center gap-2 text-xs ${i === 0 ? "text-foreground" : "text-muted-foreground"}`}
        >
          <MousePointerClick className="size-3.5 shrink-0" />
          {actionLabel(action)}
        </li>
      ))}
    </ol>
  );
}

function EmptyState() {
  return (
    <div className="mx-3 mt-6 rounded-xl border border-dashed border-border/60 p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">El agente no tiene un navegador abierto.</p>
      <p className="mt-1">
        Pedile algo como «abrí google.com y buscá el precio de NVDA» y lo vas a ver acá en vivo, mientras
        navega, hace clic y escribe.
      </p>
    </div>
  );
}

export function BrowserLivePanel() {
  const live = useLiveBrowser(usePreferredBrowserKey());
  const [control, setControl] = useState(false);
  const liveControl = control && live.state === "live";
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pb-4">
      <StatusBar live={live} control={liveControl} onToggle={() => setControl((c) => !c)} />
      {live.state === "searching" ? (
        <EmptyState />
      ) : (
        <>
          <AddressBar live={live} />
          <Viewport live={live} control={liveControl} />
          {live.state === "ended" && (
            <p className="mx-3 mt-2 text-[11px] text-muted-foreground">
              El agente cerró el navegador al terminar la tarea. Esta es la última imagen; cuando vuelva a
              navegar, la vas a ver acá en vivo.
            </p>
          )}
          {liveControl && (
            <p className="mx-3 mt-2 text-[11px] text-muted-foreground">
              Tenés el control: tus clics, scroll y teclas van al navegador del agente.
            </p>
          )}
          <ActionFeed />
        </>
      )}
    </div>
  );
}
