/**
 * useTokenUsage — Hook para obtener detalle de tokens de la sesión actual
 * + agregado global por modelo.
 *
 * Combina 2 métodos JSON-RPC del backend:
 *   - session.usage → desglose de la sesión activa (input, output, cache, etc)
 *   - usage.by_model → agregado de todas las sesiones agrupado por modelo
 *
 * Guardrail:
 *   Si el backend devuelve 0/vacío de forma transitoria, no borramos el último
 *   dato válido conocido. Esto evita que el header/popover vuelva a 0 después
 *   de recargas, cambios de sesión o reinicios del dashboard.
 */

import { useCallback, useRef, useState } from "react";

import type { RpcSender } from "./useSessions";

export interface SessionUsage {
  model: string | null;
  provider: string | null;
  calls: number;
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  reasoning: number;
  total: number;
  cost_usd: number | null;
  cost_status: string | null;
  context_used: number | null;
  context_max: number | null;
  context_percent: number | null;
  compressions: number;
}

export interface ModelUsageRow {
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  cost_usd: number;
  sessions_count: number;
}

export interface UsageByModel {
  models: ModelUsageRow[];
  total_tokens: number;
  total_cost_usd: number;
}

interface UseTokenUsageResult {
  sessionUsage: SessionUsage | null;
  usageByModel: UsageByModel | null;
  loading: boolean;
  error: string | null;
  refresh: (sessionId: string | null) => Promise<void>;
}

const EMPTY_USAGE_BY_MODEL: UsageByModel = {
  models: [],
  total_tokens: 0,
  total_cost_usd: 0,
};

const SESSION_USAGE_CACHE_PREFIX = "clawksis.chat.sessionUsage.v2:";
const USAGE_BY_MODEL_CACHE_KEY = "clawksis.chat.usageByModel.v2";

function toNumber(value: unknown): number {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

function canUseLocalStorage(): boolean {
  try {
    return typeof window !== "undefined" && !!window.localStorage;
  } catch {
    return false;
  }
}

function readJson<T>(key: string): T | null {
  if (!canUseLocalStorage()) return null;

  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  if (!canUseLocalStorage()) return;

  try {
    window.localStorage.setItem(
      key,
      JSON.stringify({
        ...((value ?? {}) as Record<string, unknown>),
        cached_at: Date.now(),
      }),
    );
  } catch {
    // No bloquear la UI por cuota/localStorage deshabilitado.
  }
}

function sessionUsageCacheKey(sessionId: string): string {
  return SESSION_USAGE_CACHE_PREFIX + sessionId;
}

function normalizeSessionUsage(res: unknown): SessionUsage {
  const r = (res ?? {}) as Record<string, unknown>;

  return {
    model: (r.model as string) ?? null,
    provider: (r.provider as string) ?? null,
    calls: toNumber(r.calls),
    input: toNumber(r.input),
    output: toNumber(r.output),
    cache_read: toNumber(r.cache_read),
    cache_write: toNumber(r.cache_write),
    reasoning: toNumber(r.reasoning),
    total: toNumber(r.total ?? r.total_tokens ?? r.tokens_used),
    cost_usd: r.cost_usd != null ? Number(r.cost_usd) : null,
    cost_status: (r.cost_status as string) ?? null,
    context_used:
      r.context_used != null
        ? Number(r.context_used)
        : r.total != null
          ? Number(r.total)
          : null,
    context_max:
      r.context_max != null
        ? Number(r.context_max)
        : r.tokens_max != null
          ? Number(r.tokens_max)
          : null,
    context_percent:
      r.context_percent != null ? Number(r.context_percent) : null,
    compressions: toNumber(r.compressions),
  };
}

function normalizeUsageByModel(res: unknown): UsageByModel {
  const r = (res ?? EMPTY_USAGE_BY_MODEL) as Record<string, unknown>;
  const rawModels = Array.isArray(r.models) ? r.models : [];

  return {
    models: rawModels.map((row) => {
      const m = (row ?? {}) as Record<string, unknown>;
      return {
        model: String(m.model ?? "unknown"),
        input_tokens: toNumber(m.input_tokens),
        output_tokens: toNumber(m.output_tokens),
        cache_read_tokens: toNumber(m.cache_read_tokens),
        cache_write_tokens: toNumber(m.cache_write_tokens),
        reasoning_tokens: toNumber(m.reasoning_tokens),
        total_tokens: toNumber(m.total_tokens),
        cost_usd: toNumber(m.cost_usd),
        sessions_count: toNumber(m.sessions_count),
      };
    }),
    total_tokens: toNumber(r.total_tokens),
    total_cost_usd: toNumber(r.total_cost_usd),
  };
}

function hasRealSessionUsage(usage: SessionUsage | null): boolean {
  if (!usage) return false;

  return (
    usage.total > 0 ||
    usage.input > 0 ||
    usage.output > 0 ||
    usage.cache_read > 0 ||
    usage.cache_write > 0 ||
    usage.reasoning > 0
  );
}

function hasRealModelUsage(usage: UsageByModel | null): boolean {
  if (!usage) return false;

  return (
    usage.total_tokens > 0 ||
    usage.models.some((m) => m.total_tokens > 0 || m.sessions_count > 0)
  );
}

export function useTokenUsage(
  sendRpc: RpcSender,
  ready: boolean,
): UseTokenUsageResult {
  const [sessionUsage, setSessionUsage] = useState<SessionUsage | null>(null);
  const [usageByModel, setUsageByModel] = useState<UsageByModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeSessionIdRef = useRef<string | null>(null);

  const refresh = useCallback(
    async (sessionId: string | null) => {
      if (!ready) return;

      activeSessionIdRef.current = sessionId;
      setLoading(true);
      setError(null);

      const cachedModelUsage = readJson<UsageByModel>(USAGE_BY_MODEL_CACHE_KEY);
      if (hasRealModelUsage(cachedModelUsage)) {
        setUsageByModel(cachedModelUsage);
      }

      if (sessionId) {
        const cachedSessionUsage = readJson<SessionUsage>(
          sessionUsageCacheKey(sessionId),
        );
        setSessionUsage(hasRealSessionUsage(cachedSessionUsage) ? cachedSessionUsage : null);
      } else {
        setSessionUsage(null);
      }

      const tasks: Promise<unknown>[] = [];

      tasks.push(
        sendRpc("usage.by_model", {}).then(
          (res) => {
            const next = normalizeUsageByModel(res);

            if (hasRealModelUsage(next)) {
              writeJson(USAGE_BY_MODEL_CACHE_KEY, next);
              setUsageByModel(next);
              return;
            }

            const cached = readJson<UsageByModel>(USAGE_BY_MODEL_CACHE_KEY);
            setUsageByModel(
              hasRealModelUsage(cached)
                ? cached
                : usageByModel && hasRealModelUsage(usageByModel)
                  ? usageByModel
                  : EMPTY_USAGE_BY_MODEL,
            );
          },
          (err) => {
            console.warn("[useTokenUsage] usage.by_model failed", err);
            const cached = readJson<UsageByModel>(USAGE_BY_MODEL_CACHE_KEY);
            setUsageByModel(
              hasRealModelUsage(cached)
                ? cached
                : usageByModel && hasRealModelUsage(usageByModel)
                  ? usageByModel
                  : EMPTY_USAGE_BY_MODEL,
            );
          },
        ),
      );

      if (sessionId) {
        tasks.push(
          sendRpc("session.usage", { session_id: sessionId }).then(
            (res) => {
              if (activeSessionIdRef.current !== sessionId) return;

              const next = normalizeSessionUsage(res);

              if (hasRealSessionUsage(next)) {
                writeJson(sessionUsageCacheKey(sessionId), next);
                setSessionUsage(next);
                return;
              }

              const cached = readJson<SessionUsage>(
                sessionUsageCacheKey(sessionId),
              );
              setSessionUsage(hasRealSessionUsage(cached) ? cached : null);
            },
            (err) => {
              console.warn("[useTokenUsage] session.usage failed", err);
              if (activeSessionIdRef.current !== sessionId) return;

              const cached = readJson<SessionUsage>(
                sessionUsageCacheKey(sessionId),
              );
              setSessionUsage(hasRealSessionUsage(cached) ? cached : null);
            },
          ),
        );
      }

      try {
        // Un RPC puede quedar huérfano (WS reconectando, sesión no viva) y no
        // resolver NUNCA — sin este techo, el popover quedaba en "Cargando
        // datos…" para siempre. A los 10s soltamos con lo cacheado.
        await Promise.race([
          Promise.all(tasks),
          new Promise((_, reject) =>
            window.setTimeout(
              () => reject(new Error("timeout cargando uso de tokens")),
              10_000,
            ),
          ),
        ]);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load token usage",
        );
      } finally {
        setLoading(false);
      }
    },
    [sendRpc, ready, usageByModel],
  );

  return {
    sessionUsage,
    usageByModel,
    loading,
    error,
    refresh,
  };
}
