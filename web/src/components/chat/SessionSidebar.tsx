/**
 * SessionSidebar — Panel izquierdo del modo Moderno con la lista de sesiones.
 *
 * Cada sesión muestra: título + fecha, y abajo-derecha el modelo + un ícono del
 * origen (dashboard / telegram / cron / cli / …). Botón de borrar al pasar el
 * mouse. La sesión que se está viendo queda resaltada (punto + ring violeta).
 */

import {
  Plus,
  Loader2,
  MessageSquare,
  Trash2,
  LayoutDashboard,
  Terminal,
  Send,
  MessageCircle,
  Hash,
  Clock,
  Webhook,
  Globe,
  type LucideIcon,
} from "lucide-react";
import { deriveTitle, type SessionSummary } from "./hooks/useSessions";

interface SessionSidebarProps {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;
  error: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onDeleteSession: (sessionId: string) => void;
}

/** Origen de la sesión → ícono + etiqueta + color (de dónde viene la charla). */
const SOURCE_META: Record<
  string,
  { icon: LucideIcon; label: string; color: string }
> = {
  dashboard: { icon: LayoutDashboard, label: "Dashboard", color: "text-[#6C4FD6]" },
  tui: { icon: Terminal, label: "Terminal", color: "text-primary" },
  cli: { icon: Terminal, label: "CLI", color: "text-primary" },
  telegram: { icon: Send, label: "Telegram", color: "text-[oklch(0.65_0.15_250)]" },
  whatsapp: { icon: MessageCircle, label: "WhatsApp", color: "text-success" },
  discord: { icon: Hash, label: "Discord", color: "text-[oklch(0.65_0.15_280)]" },
  slack: { icon: Hash, label: "Slack", color: "text-[oklch(0.7_0.15_155)]" },
  cron: { icon: Clock, label: "Cron", color: "text-warning" },
  webhook: { icon: Webhook, label: "Webhook", color: "text-muted-foreground" },
};

function sourceMeta(source: string) {
  return (
    SOURCE_META[(source || "").toLowerCase()] ?? {
      icon: Globe,
      label: source || "—",
      color: "text-muted-foreground",
    }
  );
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
  onDelete,
}: {
  session: SessionSummary;
  isActive: boolean;
  onClick: () => void;
  onDelete: () => void;
}) {
  const title = deriveTitle(session);
  const dateLabel = formatRelativeDate(session.started_at);
  const meta = sourceMeta(session.source);
  const SourceIcon = meta.icon;
  const model = session.model?.trim();

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onClick}
        title={title}
        aria-current={isActive ? "true" : undefined}
        className={
          "flex w-full flex-col gap-0.5 rounded px-2 py-1.5 pr-7 text-left transition-colors " +
          (isActive
            ? "bg-[#6C4FD6]/30 text-foreground ring-2 ring-inset ring-[#6C4FD6] shadow-sm"
            : "text-muted-foreground hover:bg-muted/30 hover:text-foreground")
        }
      >
        <span className="flex items-center gap-1.5">
          {isActive && (
            <span className="size-1.5 shrink-0 rounded-full bg-[#6C4FD6]" />
          )}
          <span className="truncate text-xs font-medium">{title}</span>
        </span>
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/80">
          <span className="shrink-0">{dateLabel}</span>
          <span className="ml-auto flex min-w-0 items-center gap-1">
            {model && (
              <span className="max-w-[88px] truncate font-mono" title={model}>
                {model}
              </span>
            )}
            <SourceIcon
              className={"size-3 shrink-0 " + meta.color}
              aria-label={meta.label}
            />
          </span>
        </div>
      </button>

      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        aria-label={"Borrar " + title}
        title="Borrar conversación"
        className="absolute right-1 top-1.5 rounded p-1 text-muted-foreground/60 opacity-0 transition-opacity hover:bg-destructive/20 hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100"
      >
        <Trash2 className="size-3" />
      </button>
    </div>
  );
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  loading,
  error,
  onSelectSession,
  onNewChat,
  onDeleteSession,
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
            onDelete={() => onDeleteSession(session.id)}
          />
        ))}
      </div>
    </aside>
  );
}
