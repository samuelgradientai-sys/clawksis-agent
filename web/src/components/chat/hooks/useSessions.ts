/**
 * useSessions — Hook para gestionar la lista de sesiones del usuario.
 *
 * Consume los métodos JSON-RPC:
 *   - session.list — trae lista paginada (top N por started_at desc)
 *   - session.create — crea sesión nueva (devuelve session_id)
 *
 * Diseñado para vivir AL LADO de useChatGateway, NO dentro.
 */

import { useCallback, useEffect, useState } from "react";

export interface SessionSummary {
  id: string;
  title: string;
  preview: string;
  started_at: number;
  message_count: number;
  source: string;
}

export type RpcSender = (
  method: string,
  params?: Record<string, unknown>,
) => Promise<unknown>;

interface UseSessionsResult {
  sessions: SessionSummary[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  createSession: () => Promise<string | null>;
}

const SESSION_LIST_LIMIT = 50;

export function useSessions(
  sendRpc: RpcSender,
  ready: boolean,
): UseSessionsResult {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!ready) return;
    setLoading(true);
    setError(null);
    try {
      const res = (await sendRpc("session.list", {
        limit: SESSION_LIST_LIMIT,
      })) as { sessions?: SessionSummary[] };
      const list = res?.sessions ?? [];
      list.sort((a, b) => (b.started_at || 0) - (a.started_at || 0));
      setSessions(list);
    } catch (err) {
      console.error("[useSessions] session.list failed", err);
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  }, [sendRpc, ready]);

  useEffect(() => {
    if (!ready) return;
    void refresh();
  }, [ready, refresh]);

  const createSession = useCallback(async (): Promise<string | null> => {
    if (!ready) return null;
    try {
      const res = (await sendRpc("session.create", {
        source: "dashboard",
      })) as { session_id?: string };
      const newId = res?.session_id ?? null;
      if (newId) {
        await refresh();
      }
      return newId;
    } catch (err) {
      console.error("[useSessions] session.create failed", err);
      setError(err instanceof Error ? err.message : "Failed to create session");
      return null;
    }
  }, [sendRpc, ready, refresh]);

  return {
    sessions,
    loading,
    error,
    refresh,
    createSession,
  };
}
