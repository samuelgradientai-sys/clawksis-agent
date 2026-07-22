/**
 * TasksPanel — kanban "lite" integrado al panel lateral del chat.
 *
 * Consume la API del plugin kanban (/api/plugins/kanban/*) pero con una UX
 * mínima pensada para el ancho del panel: nada de drag-drop ni 8 columnas —
 * una lista agrupada en 4 estados simples con acciones de un click:
 *
 *   Por hacer   = triage + todo + scheduled + ready
 *   En curso    = running + review
 *   Bloqueadas  = blocked
 *   Hechas      = done
 *
 * Crear = un input (Enter). Mover = ✓ Hecha / ⏸ Bloquear / ▶ Liberar /
 * archivar. El board completo del plugin sigue en /kanban para lo avanzado.
 * Si el plugin no está instalado, el panel lo dice en vez de romperse.
 */

import { useCallback, useEffect, useState } from "react";
import {
  Archive,
  Check,
  CircleAlert,
  ExternalLink,
  Loader2,
  Pause,
  Play,
  Plus,
  RefreshCw,
} from "lucide-react";
import { Link } from "react-router-dom";

import { fetchJSON } from "@/lib/api";

const BOARD_POLL_MS = 10000;

const DONE_PREVIEW_LIMIT = 8;

interface KanbanTask {
  id: string;
  title: string;
  status: string;
  priority?: number;
  assignee?: string | null;
  age?: string | null;
}

interface BoardColumn {
  name: string;
  tasks: KanbanTask[];
}

interface BoardResponse {
  columns?: BoardColumn[];
}

type GroupId = "pending" | "active" | "blocked" | "done";

const GROUPS: { id: GroupId; label: string; statuses: string[]; dot: string }[] = [
  {
    id: "pending",
    label: "Por hacer",
    statuses: ["triage", "todo", "scheduled", "ready"],
    dot: "bg-sky-400",
  },
  { id: "active", label: "En curso", statuses: ["running", "review"], dot: "bg-amber-400" },
  { id: "blocked", label: "Bloqueadas", statuses: ["blocked"], dot: "bg-rose-400" },
  { id: "done", label: "Hechas", statuses: ["done"], dot: "bg-emerald-400" },
];

/** "409: {"detail":"..."}" → el detail legible; cualquier otra cosa, tal cual. */
function readableError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  const jsonStart = msg.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const body = JSON.parse(msg.slice(jsonStart)) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail) return body.detail;
    } catch {
      /* no era JSON — se muestra crudo */
    }
  }
  return msg;
}

function isPluginMissing(e: unknown): boolean {
  return e instanceof Error && e.message.startsWith("404");
}

export function TasksPanel() {
  const [tasks, setTasks] = useState<KanbanTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [pluginMissing, setPluginMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyTask, setBusyTask] = useState<string | null>(null);
  const [showAllDone, setShowAllDone] = useState(false);

  // Sin guard de unmount: el interval se limpia en el cleanup y un setState
  // tras unmount por un fetch en vuelo es un no-op inofensivo en React 18.
  const refresh = useCallback(async (opts: { silent?: boolean } = {}) => {
    if (!opts.silent) setLoading(true);
    try {
      const res = await fetchJSON<BoardResponse>("/api/plugins/kanban/board");
      const flat = (res.columns ?? []).flatMap((c) =>
        (c.tasks ?? []).map((t) => ({ ...t, status: t.status || c.name })),
      );
      setTasks(flat);
      setPluginMissing(false);
      setError(null);
    } catch (e) {
      if (isPluginMissing(e)) setPluginMissing(true);
      else setError(readableError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Carga inicial + poll suave mientras el panel está visible. El primer
  // setState queda detrás de un await (patrón MediaPanel) para no encadenar
  // renders sincrónicos desde el efecto.
  useEffect(() => {
    void (async () => {
      await Promise.resolve();
      await refresh();
    })();
    const t = setInterval(() => {
      if (!document.hidden) void refresh({ silent: true });
    }, BOARD_POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const createTask = async () => {
    const title = newTitle.trim();
    if (!title || creating) return;
    setCreating(true);
    setError(null);
    try {
      await fetchJSON("/api/plugins/kanban/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });
      setNewTitle("");
      await refresh({ silent: true });
    } catch (e) {
      setError(readableError(e));
    } finally {
      setCreating(false);
    }
  };

  const moveTask = async (id: string, status: string) => {
    setBusyTask(id);
    setError(null);
    try {
      await fetchJSON(`/api/plugins/kanban/tasks/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      await refresh({ silent: true });
    } catch (e) {
      setError(readableError(e));
    } finally {
      setBusyTask(null);
    }
  };

  const iconBtn = (
    label: string,
    onClick: () => void,
    icon: React.ReactNode,
    disabled: boolean,
  ) => (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground disabled:opacity-40"
    >
      {icon}
    </button>
  );

  const taskRow = (t: KanbanTask, group: GroupId) => {
    const busy = busyTask === t.id;
    return (
      <li
        key={t.id}
        className="group flex items-center gap-2 rounded-md border border-border/50 bg-card/30 px-2 py-1.5"
      >
        <span
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${GROUPS.find((g) => g.id === group)?.dot}`}
        />
        <span
          title={t.title}
          className={`min-w-0 flex-1 truncate text-xs ${
            group === "done" ? "text-muted-foreground line-through" : "text-foreground"
          }`}
        >
          {t.title}
        </span>
        {t.assignee ? (
          <span className="hidden max-w-[6rem] truncate rounded bg-muted/40 px-1 text-[10px] text-muted-foreground sm:inline">
            {t.assignee}
          </span>
        ) : null}
        {busy ? (
          <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
        ) : (
          <span className="flex items-center opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100">
            {group === "blocked" &&
              iconBtn("Liberar (lista para correr)", () => void moveTask(t.id, "ready"), <Play className="size-3.5" />, busy)}
            {group !== "done" &&
              group !== "blocked" &&
              iconBtn("Bloquear", () => void moveTask(t.id, "blocked"), <Pause className="size-3.5" />, busy)}
            {group !== "done" &&
              iconBtn("Marcar hecha", () => void moveTask(t.id, "done"), <Check className="size-3.5" />, busy)}
            {group === "done" &&
              iconBtn("Archivar", () => void moveTask(t.id, "archived"), <Archive className="size-3.5" />, busy)}
          </span>
        )}
      </li>
    );
  };

  if (pluginMissing) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-4 text-center text-muted-foreground">
        <CircleAlert className="size-8 opacity-40" />
        <p className="text-xs">
          El plugin Kanban no está disponible en este servidor. Instalalo (viene incluido con
          Clawksis) y recargá.
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 p-2">
      <div className="flex items-center gap-1.5">
        <div className="relative min-w-0 flex-1">
          <Plus className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void createTask();
            }}
            placeholder="Nueva tarea… (Enter)"
            disabled={creating}
            className="w-full rounded-md border border-border/60 bg-card/30 py-1.5 pl-7 pr-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-[#6C4FD6]/60 focus:outline-none disabled:opacity-50"
          />
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="Refrescar tareas"
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground disabled:opacity-40"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
          {error}
        </div>
      )}

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        {loading && tasks.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-1.5 text-muted-foreground">
            <Check className="size-8 opacity-30" />
            <p className="text-xs">Sin tareas — creá la primera arriba</p>
          </div>
        ) : (
          GROUPS.map((g) => {
            const inGroup = tasks.filter((t) => g.statuses.includes(t.status));
            if (inGroup.length === 0) return null;
            const visible =
              g.id === "done" && !showAllDone ? inGroup.slice(0, DONE_PREVIEW_LIMIT) : inGroup;
            return (
              <section key={g.id}>
                <h3 className="mb-1 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                  <span className={`h-1.5 w-1.5 rounded-full ${g.dot}`} />
                  {g.label}
                  <span className="rounded bg-muted/40 px-1 text-[10px]">{inGroup.length}</span>
                </h3>
                <ul className="space-y-1">{visible.map((t) => taskRow(t, g.id))}</ul>
                {g.id === "done" && inGroup.length > DONE_PREVIEW_LIMIT && (
                  <button
                    type="button"
                    onClick={() => setShowAllDone((v) => !v)}
                    className="mt-1 text-[11px] text-muted-foreground hover:text-foreground"
                  >
                    {showAllDone ? "Ver menos" : `Ver las ${inGroup.length} hechas`}
                  </button>
                )}
              </section>
            );
          })
        )}
      </div>

      <Link
        to="/kanban"
        className="inline-flex items-center gap-1.5 self-start rounded-md border border-border/60 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
      >
        <ExternalLink className="size-3" />
        Tablero completo
      </Link>
    </div>
  );
}
