/**
 * useSessions — Hook para gestionar la lista de sesiones del usuario.
 *
 * Consume los métodos JSON-RPC:
 *   - session.list — trae lista paginada (top N por started_at desc)
 *   - session.create — crea sesión nueva (devuelve session_id)
 *
 * Fase 2.9 — exporta deriveTitle(): heurística para mostrar mejor el título
 * de la sesión cuando el backend no tiene uno bueno (ej: system prompts
 * metidos como primer mensaje del usuario).
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

/**
 * Limpia y trunca un texto candidato a título.
 *  - Colapsa whitespace múltiple
 *  - Trunca a MAX_TITLE_LENGTH con "..."
 *  - Devuelve "" si quedaría vacío después de limpiar
 */
function cleanTitle(raw: string): string {
  const cleaned = raw.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= MAX_TITLE_LENGTH) return cleaned;
  return cleaned.slice(0, MAX_TITLE_LENGTH - 1).trimEnd() + "…";
}

/**
 * Verifica si un texto candidato a título es "tóxico" (system prompt, slash
 * command, etc) y por lo tanto NO debería usarse como título.
 */
function isToxic(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return true;
  return TOXIC_TITLE_PATTERNS.some((p) => p.test(trimmed));
}

/**
 * Deriva el título a mostrar en el sidebar usando heurística:
 *  1. Si session.title NO es tóxico → usarlo
 *  2. Sino, intentar session.preview (último mensaje) si NO es tóxico
 *  3. Sino, fallback a "Conversación {short-id}"
 *
 * Función pura — fácil de testear y razonar.
 */
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

  // Fallback final: usar source + primeros 8 chars del ID
  const shortId = (session.id ?? "").slice(0, 8) || "?";
  const source = (session.source ?? "").trim().toLowerCase();
  const label = SOURCE_LABELS[source] ?? "Conversación";
  return label + " · " + shortId;
}

/**
 * Mapeo de source del backend → etiqueta amigable en el sidebar.
 * Solo se usa cuando no hay title ni preview útil (fallback).
 */
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
