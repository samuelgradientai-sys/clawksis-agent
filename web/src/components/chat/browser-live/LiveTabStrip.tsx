/** The agent browser's open tabs: tap one to watch it; "Seguir al agente" goes back to following
 *  whichever tab the agent works in. */

import { Crosshair } from "lucide-react";
import type { LiveBrowser } from "./useLiveBrowser";

function hostOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

export function LiveTabStrip({ live }: { live: LiveBrowser }) {
  if (live.tabs.length < 2 && !live.pinned) return null;
  return (
    <div
      className="mx-3 mt-2 flex gap-1.5 overflow-x-auto pb-1"
      role="tablist"
      aria-label="Pestañas del navegador del agente"
    >
      {live.pinned && (
        <button
          type="button"
          onClick={live.followAgent}
          className="flex shrink-0 items-center gap-1 rounded-full border border-[#6C4FD6]/60 bg-[#6C4FD6]/15 px-2.5 py-1 text-[11px] text-foreground"
        >
          <Crosshair className="size-3" />
          Seguir al agente
        </button>
      )}
      {live.tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={tab.active}
          title={tab.url}
          onClick={() => live.focusTab(tab.id)}
          className={`max-w-[11rem] shrink-0 truncate rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
            tab.active
              ? "border-foreground/30 bg-muted/40 text-foreground"
              : "border-border/60 text-muted-foreground hover:text-foreground"
          }`}
        >
          {tab.title || hostOf(tab.url)}
        </button>
      ))}
    </div>
  );
}
