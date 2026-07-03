/**
 * SessionSidebar — Panel izquierdo del modo Moderno con apartado de proyectos.
 *
 * UX:
 * - Conversaciones generales y Proyectos son apartados separados.
 * - La vista "Proyectos" muestra carpetas, no todos los chats mezclados.
 * - Al abrir un proyecto, se muestran solo sus conversaciones.
 * - Los chats existentes se pueden mover desde un menú discreto de tres puntos.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import {
  Plus,
  Loader2,
  MessageSquare,
  LayoutDashboard,
  Terminal,
  Send,
  MessageCircle,
  Hash,
  Clock,
  Webhook,
  Globe,
  Folder,
  FolderOpen,
  FolderPlus,
  Inbox,
  MoreHorizontal,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Pin,
  PinOff,
  Copy,
  Download,
  Pencil,
  ListTree,
  type LucideIcon,
} from "lucide-react";
import {
  deriveTitle,
  type ChatProject,
  type SessionSummary,
} from "./hooks/useSessions";

interface SessionSidebarProps {
  sessions: SessionSummary[];
  projects: ChatProject[];
  activeSessionId: string | null;
  /** Running state of the *open* conversation, for instant spinner feedback. */
  activeBusy?: boolean;
  loading: boolean;
  error: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewChat: () => void;
  onNewChatInProject: (projectId: string) => void;
  onCreateProject: () => void;
  onDeleteSession: (sessionId: string) => void;
  onMoveSessionToProject: (sessionId: string, projectId: string | null) => void;
  /** Renombrar conversación (persiste vía PATCH + refresca la lista). */
  onRenameSession: (sessionId: string, title: string) => void | Promise<void>;
}

type SidebarMode = "chats" | "projects";

// ── Fijados + agrupación (persistidos en localStorage, solo-cliente) ────────
const PINNED_STORAGE_KEY = "clawksis-pinned-chats";
const GROUPED_STORAGE_KEY = "clawksis-chats-grouped";

function readPinnedIds(): string[] {
  try {
    const raw = window.localStorage.getItem(PINNED_STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

/** Etiqueta corta de modelo para agrupar ("deepseek/deepseek-v4-flash" → "deepseek-v4-flash"). */
function modelGroupLabel(model?: string | null): string {
  const m = (model || "").trim();
  if (!m) return "otros";
  return m.split("/").pop() || m;
}

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

function sourceMeta(source: string | null | undefined) {
  const normalized = (source || "").toLowerCase();
  return (
    SOURCE_META[normalized] ?? {
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

function SidebarTab({
  active,
  icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  icon: "chats" | "projects";
  label: string;
  count: number;
  onClick: () => void;
}) {
  const Icon = icon === "projects" ? Folder : Inbox;

  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs transition-colors " +
        (active
          ? "bg-[#6C4FD6]/20 text-foreground ring-1 ring-inset ring-[#6C4FD6]/40"
          : "text-muted-foreground hover:bg-muted/30 hover:text-foreground")
      }
    >
      <Icon className="size-3.5 shrink-0" />
      <span className="min-w-0 flex-1 truncate font-medium">{label}</span>
      <span className="rounded bg-background/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
        {count}
      </span>
    </button>
  );
}

function SectionTitle({
  icon,
  title,
  count,
}: {
  icon: "chats" | "project";
  title: string;
  count: number;
}) {
  const Icon = icon === "project" ? FolderOpen : Inbox;

  return (
    <div className="mt-2 flex items-center gap-1.5 px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
      <Icon className="size-3 shrink-0" />
      <span className="min-w-0 flex-1 truncate" title={title}>
        {title}
      </span>
      <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px]">
        {count}
      </span>
    </div>
  );
}

function ProjectCard({
  project,
  count,
  onOpen,
  onNewChat,
}: {
  project: ChatProject;
  count: number;
  onOpen: () => void;
  onNewChat: () => void;
}) {
  return (
    <div className="rounded-md border border-border bg-background/40 p-2 transition-colors hover:bg-muted/20">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-2 text-left"
      >
        <Folder className="size-4 shrink-0 text-[#6C4FD6]" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs font-semibold text-foreground">
            {project.name}
          </div>
          <div className="text-[10px] text-muted-foreground">
            {count === 1 ? "1 conversación" : count + " conversaciones"}
          </div>
        </div>
        <ChevronRight className="size-3.5 text-muted-foreground" />
      </button>

      <button
        type="button"
        onClick={onNewChat}
        className="mt-2 flex w-full items-center justify-center gap-1.5 rounded border border-border bg-muted/10 px-2 py-1.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground"
      >
        <Plus className="size-3" />
        Chat en este proyecto
      </button>
    </div>
  );
}

function SessionItem({
  session,
  projects,
  isActive,
  isRunning,
  isPinned,
  menuOpen,
  onClick,
  onToggleMenu,
  onCloseMenu,
  onDelete,
  onMoveToProject,
  onTogglePin,
  onRename,
  onExport,
  onCopyId,
}: {
  session: SessionSummary;
  projects: ChatProject[];
  isActive: boolean;
  isRunning: boolean;
  isPinned: boolean;
  menuOpen: boolean;
  onClick: () => void;
  onToggleMenu: () => void;
  onCloseMenu: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string | null) => void;
  onTogglePin: () => void;
  onRename: (title: string) => void | Promise<void>;
  onExport: () => void;
  onCopyId: () => void;
}) {
  const title = deriveTitle(session);
  const dateLabel = formatRelativeDate(session.started_at);
  const meta = sourceMeta(session.source);
  const SourceIcon = meta.icon;
  const model = session.model?.trim();

  // Renombrado inline: reemplaza el título por un input (Enter guarda, Esc cancela).
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");

  const move = (projectId: string | null) => {
    onMoveToProject(projectId);
    onCloseMenu();
  };

  const saveRename = () => {
    const next = draft.trim();
    setRenaming(false);
    if (next && next !== title) void onRename(next);
  };

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={(e) => {
          // Shift+click fija/desfija (patrón Hermes) sin abrir la conversación.
          if (e.shiftKey) {
            e.preventDefault();
            onTogglePin();
            return;
          }
          if (renaming) return;
          onCloseMenu();
          onClick();
        }}
        title={title + " (Shift+click para fijar)"}
        aria-current={isActive ? "true" : undefined}
        className={
          "flex w-full flex-col gap-0.5 rounded px-2 py-1.5 pr-8 text-left transition-colors " +
          (isActive
            ? "bg-[#6C4FD6]/30 text-foreground ring-2 ring-inset ring-[#6C4FD6] shadow-sm"
            : "text-muted-foreground hover:bg-muted/30 hover:text-foreground")
        }
      >
        <span className="flex items-center gap-1.5">
          {isRunning ? (
            <Loader2
              className="size-3 shrink-0 animate-spin text-[#6C4FD6]"
              aria-label="corriendo"
            />
          ) : isActive ? (
            <span className="size-1.5 shrink-0 rounded-full bg-[#6C4FD6]" />
          ) : null}
          {isPinned && (
            <Pin className="size-3 shrink-0 text-[#6C4FD6]/80" aria-label="fijado" />
          )}
          {renaming ? (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  saveRename();
                } else if (e.key === "Escape") {
                  e.preventDefault();
                  setRenaming(false);
                }
              }}
              onBlur={saveRename}
              className="w-full min-w-0 rounded border border-[#6C4FD6]/50 bg-background px-1 py-0.5 text-xs text-foreground focus:outline-none"
            />
          ) : (
            <span className="truncate text-xs font-medium">{title}</span>
          )}
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
          onToggleMenu();
        }}
        aria-label={"Opciones de " + title}
        title="Opciones"
        className={
          "absolute right-1 top-1.5 rounded p-1 text-muted-foreground/60 transition-opacity hover:bg-muted hover:text-foreground focus-visible:opacity-100 " +
          (menuOpen ? "opacity-100" : "opacity-0 group-hover:opacity-100")
        }
      >
        <MoreHorizontal className="size-3.5" />
      </button>

      {menuOpen && (
        <div className="absolute right-1 top-7 z-30 w-52 overflow-hidden rounded-md border border-border bg-popover p-1 text-xs text-popover-foreground shadow-lg">
          <button
            type="button"
            onClick={() => {
              onCloseMenu();
              onTogglePin();
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
          >
            {isPinned ? (
              <PinOff className="size-3.5 text-muted-foreground" />
            ) : (
              <Pin className="size-3.5 text-muted-foreground" />
            )}
            {isPinned ? "Desfijar" : "Fijar"}
          </button>

          <button
            type="button"
            onClick={() => {
              onCloseMenu();
              setDraft(title);
              setRenaming(true);
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
          >
            <Pencil className="size-3.5 text-muted-foreground" />
            Renombrar
          </button>

          <button
            type="button"
            onClick={() => {
              onCloseMenu();
              onCopyId();
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
          >
            <Copy className="size-3.5 text-muted-foreground" />
            Copiar ID
          </button>

          <button
            type="button"
            onClick={() => {
              onCloseMenu();
              onExport();
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
          >
            <Download className="size-3.5 text-muted-foreground" />
            Exportar
          </button>

          <div className="my-1 border-t border-border" />

          <div className="px-2 py-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Mover a
          </div>

          <button
            type="button"
            onClick={() => move(null)}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
          >
            <Inbox className="size-3.5 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate">Conversaciones</span>
            {!session.project_id && <span className="text-[10px]">✓</span>}
          </button>

          {projects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => move(project.id)}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
            >
              <Folder className="size-3.5 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate">{project.name}</span>
              {session.project_id === project.id && (
                <span className="text-[10px]">✓</span>
              )}
            </button>
          ))}

          <div className="my-1 border-t border-border" />

          <button
            type="button"
            onClick={() => {
              onCloseMenu();
              onDelete();
            }}
            className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-destructive hover:bg-destructive/10"
          >
            <Trash2 className="size-3.5" />
            Borrar conversación
          </button>
        </div>
      )}
    </div>
  );
}

export function SessionSidebar({
  sessions,
  projects,
  activeSessionId,
  activeBusy,
  loading,
  error,
  onSelectSession,
  onNewChat,
  onNewChatInProject,
  onCreateProject,
  onDeleteSession,
  onMoveSessionToProject,
  onRenameSession,
}: SessionSidebarProps) {
  const [mode, setMode] = useState<SidebarMode>("chats");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [openMenuSessionId, setOpenMenuSessionId] = useState<string | null>(null);
  const lastAutoOpenedSessionId = useRef<string | null>(null);

  // Fijados (Shift+click o menú) + agrupación por modelo — persistidos local.
  const [pinnedIds, setPinnedIds] = useState<string[]>(readPinnedIds);
  const [grouped, setGrouped] = useState<boolean>(
    () => window.localStorage.getItem(GROUPED_STORAGE_KEY) === "1",
  );
  const togglePin = (id: string) => {
    setPinnedIds((prev) => {
      const next = prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id];
      try {
        window.localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* localStorage lleno/bloqueado: el pin queda solo en memoria */
      }
      return next;
    });
  };
  const toggleGrouped = () => {
    setGrouped((prev) => {
      try {
        window.localStorage.setItem(GROUPED_STORAGE_KEY, prev ? "0" : "1");
      } catch {
        /* ídem */
      }
      return !prev;
    });
  };
  const exportSession = (id: string) => {
    const a = document.createElement("a");
    a.href = api.exportSessionUrl(id);
    a.download = "clawksis-chat-" + id.slice(0, 8) + ".json";
    document.body.appendChild(a);
    a.click();
    a.remove();
  };
  const copySessionId = (id: string) => {
    void navigator.clipboard?.writeText(id).catch(() => {});
  };

  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  // Poll which conversations have an in-flight turn so each row shows a spinner
  // while it runs — even ones the user isn't viewing (turns run server-side in a
  // worker thread, independent of the open WebSocket).
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await api.getRunningSessions();
        if (alive) setRunningIds(new Set(res.running ?? []));
      } catch {
        /* best-effort: a failed poll leaves the last known state */
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 2500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  // Overlay the open conversation's busy state for instant feedback (the poll is
  // every 2.5s, but the open chat should flip to a spinner the moment you send).
  const effectiveRunning = useMemo(() => {
    const set = new Set(runningIds);
    if (activeBusy && activeSessionId) set.add(activeSessionId);
    return set;
  }, [runningIds, activeBusy, activeSessionId]);

  const activeProjects = projects.filter((project) => !project.archived);
  const projectIds = new Set(activeProjects.map((project) => project.id));

  const sessionsByProject = new Map<string, SessionSummary[]>();
  for (const project of activeProjects) {
    sessionsByProject.set(project.id, []);
  }

  const pinnedSet = new Set(pinnedIds);
  // Fijados: cualquier conversación (general o de proyecto), en su propia sección.
  const pinnedSessions = sessions.filter((s) => pinnedSet.has(s.id));

  const generalSessions: SessionSummary[] = [];

  for (const session of sessions) {
    if (pinnedSet.has(session.id)) continue; // ya listado en Fijados
    const projectId = session.project_id ?? "";
    if (projectId && projectIds.has(projectId)) {
      sessionsByProject.get(projectId)?.push(session);
    } else {
      generalSessions.push(session);
    }
  }

  // Agrupación por modelo (toggle): [etiqueta, sesiones] ordenado por recencia.
  const groupedGeneral = useMemo(() => {
    if (!grouped) return null;
    const groups = new Map<string, SessionSummary[]>();
    for (const s of generalSessions) {
      const label = modelGroupLabel(s.model);
      const arr = groups.get(label);
      if (arr) arr.push(s);
      else groups.set(label, [s]);
    }
    return Array.from(groups.entries()).sort(
      (a, b) => (b[1][0]?.started_at ?? 0) - (a[1][0]?.started_at ?? 0),
    );
    // generalSessions se deriva de props en cada render; agrupar es barato.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grouped, sessions, pinnedIds, projects]);

  const selectedProject =
    activeProjects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedProjectSessions = selectedProject
    ? sessionsByProject.get(selectedProject.id) ?? []
    : [];

  useEffect(() => {
    if (!activeSessionId) return;
    if (lastAutoOpenedSessionId.current === activeSessionId) return;

    lastAutoOpenedSessionId.current = activeSessionId;

    const activeSession = sessions.find((session) => session.id === activeSessionId);
    if (activeSession?.project_id && projectIds.has(activeSession.project_id)) {
      setMode("projects");
      setSelectedProjectId(activeSession.project_id);
    }
  }, [activeSessionId, sessions, projectIds]);

  const renderSession = (session: SessionSummary) => (
    <SessionItem
      key={session.id}
      session={session}
      projects={activeProjects}
      isActive={session.id === activeSessionId}
      isRunning={effectiveRunning.has(session.id)}
      isPinned={pinnedSet.has(session.id)}
      menuOpen={openMenuSessionId === session.id}
      onClick={() => onSelectSession(session.id)}
      onToggleMenu={() =>
        setOpenMenuSessionId((current) =>
          current === session.id ? null : session.id,
        )
      }
      onCloseMenu={() => setOpenMenuSessionId(null)}
      onDelete={() => onDeleteSession(session.id)}
      onMoveToProject={(projectId) => onMoveSessionToProject(session.id, projectId)}
      onTogglePin={() => togglePin(session.id)}
      onRename={(title) => onRenameSession(session.id, title)}
      onExport={() => exportSession(session.id)}
      onCopyId={() => copySessionId(session.id)}
    />
  );

  const openChats = () => {
    setOpenMenuSessionId(null);
    setSelectedProjectId(null);
    setMode("chats");
  };

  const openProjects = () => {
    setOpenMenuSessionId(null);
    setSelectedProjectId(null);
    setMode("projects");
  };

  return (
    <aside className="flex h-full w-64 shrink-0 flex-col gap-2 border-r border-border bg-muted/10 p-2">
      <button
        type="button"
        onClick={() => {
          setOpenMenuSessionId(null);
          onNewChat();
          setMode("chats");
          setSelectedProjectId(null);
        }}
        className="flex items-center justify-center gap-1.5 rounded-md bg-[#6C4FD6] px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-[#5a40c2]"
      >
        <Plus className="size-3.5" />
        Nueva conversación
      </button>

      <button
        type="button"
        onClick={() => {
          setOpenMenuSessionId(null);
          setMode("projects");
          setSelectedProjectId(null);
          onCreateProject();
        }}
        className="flex items-center justify-center gap-1.5 rounded-md border border-border bg-background px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground"
      >
        <FolderPlus className="size-3.5" />
        Nuevo proyecto
      </button>

      <div className="grid grid-cols-2 gap-1">
        <SidebarTab
          active={mode === "chats"}
          icon="chats"
          label="Chats"
          count={generalSessions.length}
          onClick={openChats}
        />
        <SidebarTab
          active={mode === "projects"}
          icon="projects"
          label="Proyectos"
          count={activeProjects.length}
          onClick={openProjects}
        />
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

        {!loading && !error && sessions.length === 0 && activeProjects.length === 0 && (
          <div className="flex flex-col items-center gap-1 px-2 py-6 text-center">
            <MessageSquare className="size-5 text-muted-foreground/50" />
            <span className="text-xs text-muted-foreground">
              Sin conversaciones todavía
            </span>
          </div>
        )}

        {!error && mode === "chats" && (
          <div>
            {/* FIJADOS — estilo Hermes: shift+click o el menú ⋯ fija un chat. */}
            <div className="mt-2 flex items-center gap-1.5 px-2 text-[10px] font-medium uppercase tracking-wide text-[#6C4FD6]">
              <Pin className="size-3 shrink-0" />
              <span className="min-w-0 flex-1 truncate">Fijados</span>
              {pinnedSessions.length > 0 && (
                <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                  {pinnedSessions.length}
                </span>
              )}
            </div>
            {pinnedSessions.length === 0 ? (
              <div className="flex items-center gap-1.5 px-2 py-2 text-[11px] text-muted-foreground/70">
                <Pin className="size-3 shrink-0 opacity-50" />
                Shift+click para fijar un chat
              </div>
            ) : (
              <div className="mb-1 flex flex-col gap-0.5">
                {pinnedSessions.map(renderSession)}
              </div>
            )}

            <div className="mt-2 flex items-center gap-1.5 px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              <Inbox className="size-3 shrink-0" />
              <span className="min-w-0 flex-1 truncate">Conversaciones</span>
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px]">
                {generalSessions.length}
              </span>
              <button
                type="button"
                onClick={toggleGrouped}
                title={grouped ? "Lista plana" : "Agrupar por modelo"}
                aria-pressed={grouped}
                className={
                  "rounded p-0.5 transition-colors hover:bg-muted hover:text-foreground " +
                  (grouped ? "bg-[#6C4FD6]/20 text-[#6C4FD6]" : "")
                }
              >
                <ListTree className="size-3.5" />
              </button>
            </div>

            {generalSessions.length === 0 ? (
              <div className="px-2 py-4 text-xs text-muted-foreground">
                No hay chats generales. Puedes crear una conversación nueva o abrir un proyecto.
              </div>
            ) : groupedGeneral ? (
              <div className="flex flex-col gap-0.5">
                {groupedGeneral.map(([label, groupSessions]) => (
                  <div key={label}>
                    <div className="mt-1.5 flex items-center gap-1.5 px-2 text-[10px] text-muted-foreground/80">
                      <span className="min-w-0 truncate font-mono">{label}</span>
                      <span className="font-mono text-[9px]">{groupSessions.length}</span>
                    </div>
                    <div className="flex flex-col gap-0.5">
                      {groupSessions.map(renderSession)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex flex-col gap-0.5">
                {generalSessions.map(renderSession)}
              </div>
            )}
          </div>
        )}

        {!error && mode === "projects" && !selectedProject && (
          <div>
            <div className="mt-2 flex items-center gap-1.5 px-2 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              <Folder className="size-3 shrink-0" />
              <span className="min-w-0 flex-1 truncate">Proyectos</span>
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[9px]">
                {activeProjects.length}
              </span>
            </div>

            {activeProjects.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-2 py-6 text-center">
                <Folder className="size-5 text-muted-foreground/50" />
                <span className="text-xs text-muted-foreground">
                  Sin proyectos todavía
                </span>
                <button
                  type="button"
                  onClick={onCreateProject}
                  className="rounded border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted/30 hover:text-foreground"
                >
                  Crear proyecto
                </button>
              </div>
            ) : (
              <div className="mt-1 flex flex-col gap-2">
                {activeProjects.map((project) => {
                  const projectSessions = sessionsByProject.get(project.id) ?? [];
                  const count = project.session_count ?? projectSessions.length;

                  return (
                    <ProjectCard
                      key={project.id}
                      project={project}
                      count={count}
                      onOpen={() => {
                        setOpenMenuSessionId(null);
                        setSelectedProjectId(project.id);
                      }}
                      onNewChat={() => {
                        setOpenMenuSessionId(null);
                        setSelectedProjectId(project.id);
                        onNewChatInProject(project.id);
                      }}
                    />
                  );
                })}
              </div>
            )}
          </div>
        )}

        {!error && mode === "projects" && selectedProject && (
          <div>
            <button
              type="button"
              onClick={() => {
                setOpenMenuSessionId(null);
                setSelectedProjectId(null);
              }}
              className="mt-1 flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted/30 hover:text-foreground"
            >
              <ChevronLeft className="size-3.5" />
              Proyectos
            </button>

            <SectionTitle
              icon="project"
              title={selectedProject.name}
              count={selectedProjectSessions.length}
            />

            <button
              type="button"
              onClick={() => {
                setOpenMenuSessionId(null);
                onNewChatInProject(selectedProject.id);
              }}
              className="mb-2 mt-1 flex w-full items-center justify-center gap-1.5 rounded-md border border-[#6C4FD6]/40 bg-[#6C4FD6]/10 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-[#6C4FD6]/20"
            >
              <Plus className="size-3.5 text-[#6C4FD6]" />
              Chat en este proyecto
            </button>

            {selectedProjectSessions.length === 0 ? (
              <div className="px-2 py-4 text-xs text-muted-foreground">
                Este proyecto todavía no tiene conversaciones.
              </div>
            ) : (
              <div className="flex flex-col gap-0.5">
                {selectedProjectSessions.map(renderSession)}
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
