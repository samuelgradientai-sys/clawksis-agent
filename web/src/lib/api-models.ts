/** Wire types + calls for the Models page: usage analytics, hidden usage cards and the
 *  local model server probe (`GET /api/model/local-status`). */
import { fetchJSON, getManagementProfile } from "./api";

export interface ModelsAnalyticsModelEntry {
  model: string;
  provider: string;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  reasoning_tokens: number;
  estimated_cost: number;
  actual_cost: number;
  sessions: number;
  api_calls: number;
  tool_calls: number;
  last_used_at: number;
  avg_tokens_per_session: number;
  capabilities: {
    supports_tools?: boolean;
    supports_vision?: boolean;
    supports_reasoning?: boolean;
    context_window?: number;
    max_output_tokens?: number;
    model_family?: string;
  };
}

export interface ModelsAnalyticsResponse {
  models: ModelsAnalyticsModelEntry[];
  totals: {
    distinct_models: number;
    total_input: number;
    total_output: number;
    total_cache_read: number;
    total_reasoning: number;
    total_estimated_cost: number;
    total_actual_cost: number;
    total_sessions: number;
    total_api_calls: number;
  };
  period_days: number;
  /** `dashboard.hidden_models` of the same profile ("provider|model" or a bare model). */
  hidden_models?: string[];
}

/** One probed local endpoint (`clawk_cli/model_locality.py::_probe_one`). Any HTTP answer is
 *  `reachable` (a 401 server is up but wants a key); `models` is null when the list could not be
 *  read. Joins `/api/model/options` rows on their `local_url`. */
export interface LocalEndpointStatus {
  url: string;
  reachable: boolean;
  status?: number | null;
  models?: string[] | null;
  error?: string | null;
  latency_ms?: number;
}

export interface LocalModelStatusResponse {
  endpoints: LocalEndpointStatus[];
}

export interface HiddenModelsResponse {
  ok: boolean;
  hidden_models: string[];
}

function withProfile(path: string, profile: string): string {
  if (!profile) return path;
  return `${path}${path.includes("?") ? "&" : "?"}profile=${encodeURIComponent(profile)}`;
}

function hiddenCardRequest(
  method: "POST" | "DELETE",
  entry: { model: string; provider?: string },
  profile: string,
) {
  return fetchJSON<HiddenModelsResponse>(
    withProfile("/api/analytics/models/hide", profile),
    {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: entry.model, provider: entry.provider ?? "" }),
    },
  );
}

export const modelsApi = {
  getLocalStatus: (profile = getManagementProfile()) =>
    fetchJSON<LocalModelStatusResponse>(
      withProfile("/api/model/local-status", profile),
    ),
  hideUsageCard: (
    entry: { model: string; provider?: string },
    profile = getManagementProfile(),
  ) => hiddenCardRequest("POST", entry, profile),
  unhideUsageCard: (
    entry: { model: string; provider?: string },
    profile = getManagementProfile(),
  ) => hiddenCardRequest("DELETE", entry, profile),
};
