/**
 * useModelOptions — lista de modelos disponibles + hot-swap en sesión.
 *
 * Reusa la conexión del chat (sendRpc de useChatGateway):
 *   - model.options → proveedores autenticados + modelos curados (precio/caps)
 *   - config.set { key:"model", value:"<model> --provider <slug>" } → hot-swap
 *
 * Tras el switch, el backend emite `session.info`, que useChatGateway ya
 * consume → el modelo del header se actualiza solo. config.set rechaza el
 * cambio mid-turn (code 4009), por eso el menú se deshabilita con `busy`.
 */

import { useCallback, useState } from "react";

import type { RpcSender } from "./useSessions";

export interface ModelOptionProvider {
  name: string;
  slug: string;
  models?: string[];
  total_models?: number;
  /** Backend verdict: this row is the live session's provider (handles a `custom` provider
   *  served by a named endpoint row, whose slug is `custom:<name>`). */
  is_current?: boolean;
  /** Served from a loopback/LAN endpoint (Ollama, LM Studio, llama.cpp, local custom). */
  is_local?: boolean;
  local_url?: string | null;
  warning?: string | null;
}

interface ModelOptionsResponse {
  model?: string;
  provider?: string;
  providers?: ModelOptionProvider[];
}

interface ConfigSetResponse {
  value?: string;
  confirm_required?: boolean;
  confirm_message?: string;
  warning?: string;
}

export interface SwitchModelResult {
  ok: boolean;
  confirmRequired?: boolean;
  confirmMessage?: string;
}

interface UseModelOptionsResult {
  providers: ModelOptionProvider[];
  currentModel: string;
  currentProvider: string;
  loading: boolean;
  error: string | null;
  /** `force` busts the backend's model-id caches and live-probes saved endpoints. */
  refresh: (force?: boolean) => Promise<void>;
  switchModel: (
    model: string,
    providerSlug: string,
    confirmExpensive?: boolean,
  ) => Promise<SwitchModelResult>;
}

export function useModelOptions(
  sendRpc: RpcSender,
  ready: boolean,
  sessionId: string | null,
): UseModelOptionsResult {
  const [providers, setProviders] = useState<ModelOptionProvider[]>([]);
  const [currentModel, setCurrentModel] = useState("");
  const [currentProvider, setCurrentProvider] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (force = false) => {
    if (!ready) return;
    setLoading(true);
    setError(null);
    try {
      const res = (await sendRpc("model.options", {
        ...(sessionId ? { session_id: sessionId } : {}),
        ...(force ? { refresh: true } : {}),
      })) as ModelOptionsResponse;
      setProviders(res?.providers ?? []);
      setCurrentModel(String(res?.model ?? ""));
      setCurrentProvider(String(res?.provider ?? ""));
    } catch (err) {
      console.error("[useModelOptions] model.options failed", err);
      setError(err instanceof Error ? err.message : "Failed to load models");
    } finally {
      setLoading(false);
    }
  }, [sendRpc, ready, sessionId]);

  const switchModel = useCallback(
    async (
      model: string,
      providerSlug: string,
      confirmExpensive = false,
    ): Promise<SwitchModelResult> => {
      if (!sessionId) return { ok: false };
      try {
        const res = (await sendRpc("config.set", {
          key: "model",
          value: `${model} --provider ${providerSlug}`,
          session_id: sessionId,
          confirm_expensive_model: confirmExpensive,
        })) as ConfigSetResponse;
        if (res?.confirm_required) {
          return {
            ok: false,
            confirmRequired: true,
            confirmMessage:
              res.confirm_message ||
              res.warning ||
              "Este modelo tiene un precio inusualmente alto.",
          };
        }
        // Optimista: reflejar el cambio en el indicador "actual" del menú.
        setCurrentModel(model);
        setCurrentProvider(providerSlug);
        return { ok: true };
      } catch (err) {
        console.error("[useModelOptions] config.set model failed", err);
        setError(err instanceof Error ? err.message : "Failed to switch model");
        return { ok: false };
      }
    },
    [sendRpc, sessionId],
  );

  return {
    providers,
    currentModel,
    currentProvider,
    loading,
    error,
    refresh,
    switchModel,
  };
}
