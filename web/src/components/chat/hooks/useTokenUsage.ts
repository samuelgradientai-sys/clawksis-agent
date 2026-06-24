/**
 * useTokenUsage — Hook para obtener detalle de tokens de la sesión actual
 * + agregado global por modelo.
 *
 * Combina 2 métodos JSON-RPC del backend:
 *   - session.usage → desglose de la sesión activa (input, output, cache, etc)
 *   - usage.by_model → agregado de todas las sesiones agrupado por modelo
 */

import { useCallback, useState } from "react";

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

export function useTokenUsage(
  sendRpc: RpcSender,
  ready: boolean,
): UseTokenUsageResult {
  const [sessionUsage, setSessionUsage] = useState<SessionUsage | null>(null);
  const [usageByModel, setUsageByModel] = useState<UsageByModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    async (sessionId: string | null) => {
      if (!ready) return;
      setLoading(true);
      setError(null);

      const tasks: Promise<unknown>[] = [];

      tasks.push(
        sendRpc("usage.by_model", {}).then(
          (res) => {
            const r = (res ?? EMPTY_USAGE_BY_MODEL) as UsageByModel;
            setUsageByModel({
              models: Array.isArray(r.models) ? r.models : [],
              total_tokens: Number(r.total_tokens ?? 0),
              total_cost_usd: Number(r.total_cost_usd ?? 0),
            });
          },
          (err) => {
            console.warn("[useTokenUsage] usage.by_model failed", err);
            setUsageByModel(EMPTY_USAGE_BY_MODEL);
          },
        ),
      );

      if (sessionId) {
        tasks.push(
          sendRpc("session.usage", { session_id: sessionId }).then(
            (res) => {
              const r = (res ?? {}) as Record<string, unknown>;
              setSessionUsage({
                model: (r.model as string) ?? null,
                provider: (r.provider as string) ?? null,
                calls: Number(r.calls ?? 0),
                input: Number(r.input ?? 0),
                output: Number(r.output ?? 0),
                cache_read: Number(r.cache_read ?? 0),
                cache_write: Number(r.cache_write ?? 0),
                reasoning: Number(r.reasoning ?? 0),
                total: Number(r.total ?? 0),
                cost_usd: r.cost_usd != null ? Number(r.cost_usd) : null,
                cost_status: (r.cost_status as string) ?? null,
                context_used:
                  r.context_used != null ? Number(r.context_used) : null,
                context_max:
                  r.context_max != null ? Number(r.context_max) : null,
                context_percent:
                  r.context_percent != null
                    ? Number(r.context_percent)
                    : null,
                compressions: Number(r.compressions ?? 0),
              });
            },
            (err) => {
              console.warn("[useTokenUsage] session.usage failed", err);
              setSessionUsage(null);
            },
          ),
        );
      } else {
        setSessionUsage(null);
      }

      try {
        await Promise.all(tasks);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load token usage",
        );
      } finally {
        setLoading(false);
      }
    },
    [sendRpc, ready],
  );

  return {
    sessionUsage,
    usageByModel,
    loading,
    error,
    refresh,
  };
}
