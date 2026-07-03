/**
 * useSessions — Hook para gestionar la lista de sesiones del usuario.
 *
 * Carga sesiones desde REST para recibir metadatos de proyectos/carpetas
 * (project_id/project_name), y conserva RPC para crear/borrar sesiones vivas.
 */

import { useCallback, useEffect, useState } from "react";
import { api, fetchJSON } from "@/lib/api";

export interface ChatProject {
  id: string;
  name: string;
  description: string;
  created_at: number;
  updated_at: number;
  archived: boolean;
  session_count: number;
}

export interface SessionSummary {
  id: string;
  title?: string | null;
  preview?: string | null;
  started_at: number;
  message_count: number;
  source?: string | null;
  /** Modelo de la sesión. Puede faltar en gateways viejos. */
  model?: string | null;
  model_provider?: string | null;
  project_id?: string | null;
  project_name?: string | null;
  project_archived?: boolean;
}

export type RpcSender = (
  method: string,
  params?: Record<string, unknown>,
) => Promise<unknown>;

interface UseSessionsResult {
  sessions: SessionSummary[];
  projects: ChatProject[];
  loading: boolean;
  projectsLoading: boolean;
  error: string | null;
  projectsError: string | null;
  refresh: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  createSession: () => Promise<string | null>;
  deleteSession: (id: string) => Promise<void>;
  renameSession: (id: string, title: string) => Promise<void>;
  createProject: (name: string, description?: string) => Promise<ChatProject | null>;
  moveSessionToProject: (sessionId: string, projectId: string | null) => Promise<void>;
}

const SESSION_LIST_LIMIT = 100;

/**
 * Patrones que indican que el "title" es basura (system prompt o slash command
 * metido en el primer mensaje del usuario). Si matchea, ignorar y usar fallback.
 */
const TOXIC_TITLE_PATTERNS = [
  /^\[IMPORTANT:/i,
  /^\[SYSTEM/i,
  /^\[CRITICAL/i,
  /^You are /,
  /^You're /,
  /^Act as /i,
  /^Pretend /i,
  /^Ignore (previous|prior|above|the)/i,
  /^\//,  // Slash commands tipo /help, /reset
  /^<\|/,  // Tokens especiales tipo <|im_start|>
];

const MAX_TITLE_LENGTH = 50;

function cleanTitle(raw: string): string {
  const cleaned = raw.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= MAX_TITLE_LENGTH) return cleaned;
  return cleaned.slice(0, MAX_TITLE_LENGTH - 1).trimEnd() + "…";
}

function isToxic(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return true;
  return TOXIC_TITLE_PATTERNS.some((p) => p.test(trimmed));
}

export function deriveTitle(session: SessionSummary): string {
  const titleRaw = session.title ?? "";
  if (titleRaw && !isToxic(titleRaw)) {
    const cleaned = cleanTitle(titleRaw);
    if (cleaned) return cleaned;
  }

  const previewRaw = session.preview ?? "";
  if (previewRaw && !isToxic(previewRaw)) {
    const cleaned = cleanTitle(previewRaw);
    if (cleaned) return cleaned;
  }

  const shortId = (session.id ?? "").slice(0, 8) || "?";
  const source = (session.source ?? "").trim().toLowerCase();
  const label = SOURCE_LABELS[source] ?? "Conversación";
  return label + " · " + shortId;
}

const SOURCE_LABELS: Record<string, string> = {
  cron: "Cron job",
  dashboard: "Conversación",
  cli: "Terminal",
  tui: "Terminal",
  webhook: "Webhook",
  api: "API",
  acp: "ACP",
  delegate: "Sub-agente",
};

export function useSessions(
  sendRpc: RpcSender,
  ready: boolean,
): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [projects, setProjects] = useState<ChatProject[]>([]);
  const [loading, setLoading] = useState(false);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!ready) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchJSON<{ sessions?: SessionSummary[] }>(
        `/api/sessions?limit=${SESSION_LIST_LIMIT}&order=recent`,
      );
      const list = res?.sessions ?? [];
      list.sort((a, b) => (b.started_at || 0) - (a.started_at || 0));
      setSessions(list);
    } catch (err) {
      console.error("[useSessions] /api/sessions failed", err);
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, [ready]);

  const refreshProjects = useCallback(async () => {
    if (!ready) return;
    setProjectsLoading(true);
    setProjectsError(null);
    try {
      const res = await fetchJSON<{ projects?: ChatProject[] }>("/api/projects");
      const list = res?.projects ?? [];
      list.sort((a, b) => a.name.localeCompare(b.name));
      setProjects(list);
    } catch (err) {
      console.error("[useSessions] /api/projects failed", err);
      setProjectsError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setProjectsLoading(false);
    }
  }, [ready]);

  useEffect(() => {
    if (!ready) return;
    void refresh();
    void refreshProjects();
  }, [ready, refresh, refreshProjects]);

  const createSession = useCallback(async (): Promise<string | null> => {
    if (!ready) return null;
    try {
      const res = (await sendRpc("session.create", {
        source: "dashboard",
      })) as { session_id?: string };
      const newId = res?.session_id ?? null;
      if (newId) {
        await refresh();
        await refreshProjects();
      }
      return newId;
    } catch (err) {
      console.error("[useSessions] session.create failed", err);
      setError(err instanceof Error ? err.message : "Failed to create session");
      return null;
    }
  }, [sendRpc, ready, refresh, refreshProjects]);

  const deleteSession = useCallback(
    async (id: string): Promise<void> => {
      if (!ready || !id) return;
      try {
        await sendRpc("session.delete", { session_id: id });
      } catch (err) {
        console.error("[useSessions] session.delete failed", err);
        setError(
          err instanceof Error
            ? err.message.replace(/^\d+:\s*/, "")
            : "No se pudo borrar la sesión",
        );
        return;
      }

      setSessions((prev) => prev.filter((s) => s.id !== id));
      void refresh();
      void refreshProjects();
    },
    [sendRpc, ready, refresh, refreshProjects],
  );

  const renameSession = useCallback(
    async (id: string, title: string): Promise<void> => {
      const clean = title.trim();
      if (!id || !clean) return;
      // Optimista: el título nuevo aparece al instante; refresh() reconcilia.
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, title: clean } : s)),
      );
      try {
        await api.renameSession(id, clean);
      } catch (err) {
        console.error("[useSessions] rename failed", err);
        setError(
          err instanceof Error
            ? err.message.replace(/^\d+:\s*/, "")
            : "No se pudo renombrar la conversación",
        );
      }
      void refresh();
    },
    [refresh],
  );

  const createProject = useCallback(
    async (name: string, description = ""): Promise<ChatProject | null> => {
      if (!ready) return null;

      const cleanName = name.trim();
      if (!cleanName) return null;

      try {
        const project = await fetchJSON<ChatProject>("/api/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: cleanName, description }),
        });
        await refreshProjects();
        return project;
      } catch (err) {
        console.error("[useSessions] create project failed", err);
        setProjectsError(err instanceof Error ? err.message : "No se pudo crear el proyecto");
        return null;
      }
    },
    [ready, refreshProjects],
  );

  const moveSessionToProject = useCallback(
    async (sessionId: string, projectId: string | null): Promise<void> => {
      if (!ready || !sessionId) return;

      const cleanProjectId = projectId?.trim() || null;
      const project = cleanProjectId
        ? projects.find((p) => p.id === cleanProjectId) ?? null
        : null;

      try {
        await fetchJSON<{
          ok: boolean;
          session_id: string;
          project_id: string | null;
          project_name: string | null;
        }>(`/api/sessions/${encodeURIComponent(sessionId)}/project`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: cleanProjectId }),
        });

        setSessions((prev) =>
          prev.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  project_id: cleanProjectId,
                  project_name: project?.name ?? null,
                  project_archived: false,
                }
              : s,
          ),
        );

        await refresh();
        await refreshProjects();
      } catch (err) {
        console.error("[useSessions] move session to project failed", err);
        setError(err instanceof Error ? err.message : "No se pudo mover la sesión");
      }
    },
    [ready, projects, refresh, refreshProjects],
  );

  return {
    sessions,
    projects,
    loading,
    projectsLoading,
    error,
    projectsError,
    refresh,
    refreshProjects,
    createSession,
    deleteSession,
    renameSession,
    createProject,
    moveSessionToProject,
  };
}
