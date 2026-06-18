/**
 * SessionSidebar — Panel izquierdo del modo Moderno con la lista de sesiones.
 *
 * Diseño Linear/Vercel:
 * - Ancho fijo 240px (siempre visible — opción A elegida en Fase 2.7)
 * - Header: botón "+ New chat" estilo violet (action principal)
 * - Lista: cada sesión con título + fecha relativa
 * - Sesión activa destacada con background violeta sutil
 */

import { Plus, Loader2, MessageSquare } from "lucide-react";
import type { SessionSummary } from "./hooks/useSessions";

interface SessionSidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;
  error: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
}

function formatRelativeDate(unixSeconds: number): string {
  if (!unixSeconds) return "";
  const ms = unixSeconds * 1000;
  const now = Date.now();
  const diffSec = Math.floor((now - ms) / 1000);

  if (diffSec < 60) return "ahora";
  if (diffSec < 3600) return "hace " + Math.floor(diffSec / 60) + " min";

  const today = new Date();
  const dt = new Date(ms);
  const isSameDay =
    dt.getFullYear() === today.getFullYear() &&
    dt.getMonth() === today.getMonth() &&
    dt.getDate() === today.getDate();
  if (isSameDay) {
    const hh = String(dt.getHours()).padStart(2, "0");
    const mm = String(dt.getMinutes()).padStart(2, "0");
    return "hoy " + hh + ":" + mm;
  }

  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  const isYesterday =
    dt.getFullYear() === yesterday.getFullYear() &&
    dt.getMonth() === yesterday.getMonth() &&
    dt.getDate() === yesterday.getDate();
  if (isYesterday) return "ayer";

  const diffDays = Math.floor(diffSec / 86400);
  if (diffDays < 7) return "hace " + diffDays + " días";

  const months = [
    "ene", "feb", "mar", "abr", "may", "jun",
    "jul", "ago", "sep", "oct", "nov", "dic",
  ];
  return dt.getDate() + " " + months[dt.getMonth()];
}

function SessionItem({
  session,
  isActive,
  onClick,
}: {
  session: SessionSummary;
  isActive: boolean;
  onClick: () => void;
}) {
  const title = session.title?.trim() || session.preview?.trim() || "Sin título";
  const dateLabel = formatRelativeDate(session.started_at);

  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={
        "group flex w-full flex-col gap-0.5 rounded px-2 py-1.5 text-left transition-colors " +
        (isActive
          ? "bg-[#6C4FD6]/15 text-foreground"
          : "text-muted-foreground hover:bg-muted/30 hover:text-foreground")
      }
    >
      <span className="truncate text-xs font-medium">{title}</span>
      <span className="text-[10px] text-muted-foreground/80">{dateLabel}</span>
    </button>
  );
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  loading,
  error,
  onSelectSession,
  onNewChat,
}: SessionSidebarProps) {
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col gap-2 border-r border-border bg-muted/10 p-2">
      <button
        type="button"
        onClick={onNewChat}
        className="flex items-center justify-center gap-1.5 rounded-md bg-[#6C4FD6] px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-[#5a40c2]"
      >
        <Plus className="size-3.5" />
        Nueva conversación
      </button>

      <div className="mt-1 px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        Sesiones
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto">
        {loading && sessions.length === 0 && (
          <div className="flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            Cargando...
          </div>
        )}

        {!loading && error && (
          <div className="px-2 py-2 text-xs text-destructive">{error}</div>
        )}

        {!loading && !error && sessions.length === 0 && (
          <div className="flex flex-col items-center gap-1 px-2 py-6 text-center">
            <MessageSquare className="size-5 text-muted-foreground/50" />
            <span className="text-xs text-muted-foreground">
              Sin sesiones todavía
            </span>
          </div>
        )}

        {sessions.map((session) => (
          <SessionItem
            key={session.id}
            session={session}
            isActive={session.id === activeSessionId}
            onClick={() => onSelectSession(session.id)}
          />
        ))}
      </div>
    </aside>
  );
}
