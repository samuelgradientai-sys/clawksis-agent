/** Every open agent browser at once (the agent and its subagents during a mass search), as small
 *  live previews; tap one to watch it full size. */

import type { LiveBrowserSession } from "@/lib/api-browser-live";
import { useLiveBrowser } from "./useLiveBrowser";

interface TileProps {
  taskId: string;
  label: string;
  onOpen: (taskId: string) => void;
}

function MosaicTile({ taskId, label, onOpen }: TileProps) {
  const live = useLiveBrowser(taskId, true);
  return (
    <button
      type="button"
      onClick={() => onOpen(taskId)}
      className="group flex min-w-0 flex-col overflow-hidden rounded-xl border border-border/60 bg-black/30 text-left transition-colors hover:border-[#6C4FD6]/70"
    >
      <div className="relative aspect-[16/10] w-full bg-black/40">
        {live.frame ? (
          <img
            src={live.frame.src}
            alt={live.tab?.title || label}
            className="size-full object-contain"
            draggable={false}
          />
        ) : (
          <span className="absolute inset-0 grid place-items-center text-[11px] text-muted-foreground">
            Conectando…
          </span>
        )}
        <span
          className={`absolute left-1.5 top-1.5 size-2 rounded-full ${
            live.state === "live" ? "bg-emerald-400 motion-safe:animate-pulse" : "bg-muted-foreground/50"
          }`}
        />
      </div>
      <div className="min-w-0 px-2 py-1.5">
        <p className="truncate text-[11px] font-medium">{label}</p>
        <p className="truncate text-[10px] text-muted-foreground">
          {live.tab?.title || live.tab?.url || " "}
        </p>
      </div>
    </button>
  );
}

interface LiveMosaicProps {
  sessions: LiveBrowserSession[];
  labels: Map<string, string>;
  onOpen: (taskId: string) => void;
}

export function LiveMosaic({ sessions, labels, onOpen }: LiveMosaicProps) {
  return (
    <div className="mx-3 mt-3 grid grid-cols-2 gap-2" aria-label="Todos los navegadores del agente">
      {sessions.map((s) => (
        <MosaicTile
          key={s.task_id}
          taskId={s.task_id}
          label={labels.get(s.task_id) ?? s.task_id}
          onOpen={onOpen}
        />
      ))}
    </div>
  );
}
