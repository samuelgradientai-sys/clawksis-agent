/**
 * The Models page catalog: `/api/model/options` rows joined with the profile's slot assignments
 * (`/api/model/auxiliary`) and the local server probe (`/api/model/local-status`).
 *
 * Everything here is a backend verdict re-shaped for display — locality is the row's `is_local`,
 * "current main provider" is the row's `is_current`, reachability is the probe's answer — so the
 * page never guesses from slugs (a `provider: custom` main served by a named `custom_providers`
 * row has slug `custom:<name>`; only the backend knows they are the same endpoint).
 */
import { fuzzyScoreMulti, modelSearchText } from "@clawk/shared";
import type { ModelOptionProvider, ModelOptionsResult } from "@clawk/shared";

import type { AuxiliaryModelsResponse } from "./api-aux";
import type { LocalEndpointStatus } from "./api-models";

/** Role key of the main chat model; auxiliary roles use their task key. */
export const MAIN_ROLE = "main";

export type Reachability =
  | "running" // the endpoint answered
  | "unreachable" // transport failure / timeout
  | "checking" // probe not answered yet
  | "on_demand" // managed llama.cpp: not running, starts when a model is selected
  | "unknown"; // not a local row, or the probe did not cover it

export interface CatalogModel {
  id: string;
  /** Slots this model fills right now: `main` and/or auxiliary task keys. */
  roles: string[];
  /** Local rows with a live model list: false = the server answered without this model. */
  served: boolean | null;
  /** Listed by the live probe but missing from the provider's saved list. */
  detected: boolean;
}

export interface CatalogProvider {
  slug: string;
  name: string;
  isLocal: boolean;
  isCurrent: boolean;
  localUrl: string;
  /** `base_url` an assignment from this row carries (see `assignmentBaseUrl`). */
  assignBaseUrl: string;
  reachability: Reachability;
  probeError: string;
  warning: string;
  models: CatalogModel[];
  inUse: boolean;
}

export interface InUseEntry {
  key: string;
  provider: string;
  providerName: string;
  model: string;
  roles: string[];
  isLocal: boolean;
  reachability: Reachability;
}

export interface ModelCatalog {
  inUse: InUseEntry[];
  local: CatalogProvider[];
  cloud: CatalogProvider[];
  /** Cloud providers with no models (no key / not signed in). */
  unconfigured: CatalogProvider[];
}

export interface CatalogInputs {
  options: ModelOptionsResult | null;
  aux: AuxiliaryModelsResponse | null;
  /** `null` while the probe has not answered. */
  localStatus: LocalEndpointStatus[] | null;
}

interface Assignment {
  role: string;
  provider: string;
  model: string;
  baseUrl: string;
  local: boolean;
}

/**
 * The `base_url` a slot assignment from this row must carry: user-defined endpoints by their
 * `api_url`, the Ollama row by its local endpoint. An auxiliary lane on a custom/local provider
 * routes only through an explicit base_url (`agent/auxiliary_client.py::_resolve_custom_branch`);
 * without one it falls back to the MAIN model's endpoint. Built-ins resolve their own URL, and the
 * managed llama.cpp row must not pin its server's current port.
 */
export function assignmentBaseUrl(
  row: Pick<ModelOptionProvider, "api_url" | "local_url" | "source">,
): string {
  if (row.api_url) return row.api_url;
  return row.source === "local" ? (row.local_url ?? "") : "";
}

export function normUrl(url: unknown): string {
  return String(url ?? "")
    .trim()
    .replace(/\/+$/, "")
    .toLowerCase();
}

function isAutoProvider(provider: string): boolean {
  const p = provider.trim().toLowerCase();
  return !p || p === "auto";
}

/** Main + every pinned auxiliary slot that names a concrete model. */
export function catalogAssignments(
  aux: AuxiliaryModelsResponse | null,
  options: ModelOptionsResult | null,
): Assignment[] {
  const out: Assignment[] = [];
  const mainModel = (aux?.main.model ?? options?.model ?? "").trim();
  if (mainModel) {
    out.push({
      role: MAIN_ROLE,
      provider: (aux?.main.provider ?? options?.provider ?? "").trim(),
      model: mainModel,
      baseUrl: aux?.main.base_url ?? "",
      local: !!aux?.main.local_endpoint,
    });
  }
  for (const task of aux?.tasks ?? []) {
    const model = (task.model ?? "").trim();
    if (isAutoProvider(task.provider ?? "") || !model) continue;
    out.push({
      role: task.task,
      provider: task.provider.trim(),
      model,
      baseUrl: task.base_url ?? "",
      local: !!task.local_endpoint,
    });
  }
  return out;
}

/** How strongly `row` is the provider an assignment routes to (0 = not at all). The slug wins,
 *  then an alias, then the endpoint URL; the main slot finally falls back to the backend's
 *  `is_current` (a bare `custom` provider whose URL a named endpoint row serves). */
function rowAffinity(row: ModelOptionProvider, a: Assignment): number {
  const provider = a.provider.toLowerCase();
  if (row.slug.toLowerCase() === provider) return 4;
  if ((row.aliases ?? []).some((alias) => alias.toLowerCase() === provider)) return 3;
  const rowUrl = normUrl(row.local_url ?? row.api_url);
  if (a.baseUrl && rowUrl && rowUrl === normUrl(a.baseUrl)) return 2;
  return a.role === MAIN_ROLE && row.is_current ? 1 : 0;
}

function rowFor(rows: ModelOptionProvider[], a: Assignment): ModelOptionProvider | null {
  let best: ModelOptionProvider | null = null;
  let bestScore = 0;
  for (const row of rows) {
    const score = rowAffinity(row, a);
    if (score > bestScore) {
      best = row;
      bestScore = score;
    }
  }
  return best;
}

function statusIndex(status: LocalEndpointStatus[] | null) {
  const byUrl = new Map<string, LocalEndpointStatus>();
  for (const entry of status ?? []) byUrl.set(normUrl(entry.url), entry);
  return byUrl;
}

function reachabilityOf(
  url: string,
  byUrl: Map<string, LocalEndpointStatus>,
  probed: boolean,
): Reachability {
  if (!url) return "on_demand";
  const hit = byUrl.get(normUrl(url));
  if (!hit) return probed ? "unknown" : "checking";
  return hit.reachable ? "running" : "unreachable";
}

function catalogModels(
  row: ModelOptionProvider,
  roles: Map<string, string[]>,
  live: LocalEndpointStatus | undefined,
): CatalogModel[] {
  const listed = [...(row.models ?? [])];
  for (const id of roles.keys()) if (!listed.includes(id)) listed.unshift(id);
  const liveIds = live?.reachable && Array.isArray(live.models) ? live.models : null;
  const models: CatalogModel[] = listed.map((id) => ({
    id,
    roles: roles.get(id) ?? [],
    served: liveIds ? liveIds.includes(id) : null,
    detected: false,
  }));
  for (const id of liveIds ?? []) {
    if (!listed.includes(id)) models.push({ id, roles: [], served: true, detected: true });
  }
  // In-use models first, the rest in the provider's own order.
  return models
    .map((model, index) => ({ model, index }))
    .sort((a, b) => Number(!a.model.roles.length) - Number(!b.model.roles.length) || a.index - b.index)
    .map(({ model }) => model);
}

function byUsage(list: CatalogProvider[]): CatalogProvider[] {
  return list
    .map((provider, index) => ({ provider, index }))
    .sort(
      (a, b) =>
        Number(b.provider.inUse) - Number(a.provider.inUse) ||
        Number(b.provider.isCurrent) - Number(a.provider.isCurrent) ||
        a.index - b.index,
    )
    .map(({ provider }) => provider);
}

export function buildModelCatalog({ options, aux, localStatus }: CatalogInputs): ModelCatalog {
  const rows = options?.providers ?? [];
  const byUrl = statusIndex(localStatus);
  const probed = localStatus !== null;
  const assignments = catalogAssignments(aux, options);

  // provider slug -> model id -> roles
  const rolesByRow = new Map<string, Map<string, string[]>>();
  const inUse = new Map<string, InUseEntry>();
  for (const a of assignments) {
    const row = rowFor(rows, a);
    if (row) {
      const models = rolesByRow.get(row.slug) ?? new Map<string, string[]>();
      models.set(a.model, [...(models.get(a.model) ?? []), a.role]);
      rolesByRow.set(row.slug, models);
    }
    const isLocal = row ? !!row.is_local : a.local;
    const url = row ? (row.local_url ?? "") : a.baseUrl;
    const key = `${row?.slug ?? a.provider}|${a.model}`;
    const entry = inUse.get(key) ?? {
      key,
      provider: row?.slug ?? a.provider,
      providerName: row?.name ?? a.provider,
      model: a.model,
      roles: [],
      isLocal,
      reachability: isLocal ? reachabilityOf(url, byUrl, probed) : "unknown",
    };
    entry.roles.push(a.role);
    inUse.set(key, entry);
  }

  // Empty setup skeletons (`source: canonical`, no models — e.g. LM Studio's registry row while
  // nothing is configured) are "could be set up", not "available", even with a local default URL.
  const skeleton = new Set(
    rows
      .filter((r) => r.source === "canonical" && !(r.models ?? []).length && !r.is_current)
      .map((r) => r.slug),
  );
  const providers = rows.map((row): CatalogProvider => {
    const isLocal = !!row.is_local;
    const localUrl = row.local_url ?? "";
    const roles = rolesByRow.get(row.slug) ?? new Map<string, string[]>();
    const live = isLocal && localUrl ? byUrl.get(normUrl(localUrl)) : undefined;
    return {
      slug: row.slug,
      name: row.name,
      isLocal,
      isCurrent: !!row.is_current,
      localUrl,
      assignBaseUrl: assignmentBaseUrl(row),
      reachability: isLocal ? reachabilityOf(localUrl, byUrl, probed) : "unknown",
      probeError: live && !live.reachable ? (live.error ?? "") : "",
      warning: row.warning ?? "",
      models: catalogModels(row, roles, live),
      inUse: roles.size > 0,
    };
  });
  const unconfigured = (p: CatalogProvider) =>
    skeleton.has(p.slug) || (!p.isLocal && p.models.length === 0 && !p.isCurrent);

  return {
    inUse: [...inUse.values()],
    local: byUsage(providers.filter((p) => p.isLocal && !unconfigured(p))),
    cloud: byUsage(providers.filter((p) => !p.isLocal && !unconfigured(p))),
    unconfigured: providers.filter(unconfigured),
  };
}

function matches(text: string, query: string): boolean {
  return fuzzyScoreMulti(text, query) != null;
}

function filterProviders(list: CatalogProvider[], query: string): CatalogProvider[] {
  return list.flatMap((provider) => {
    // Finding the provider by name keeps all of its models (same rule as the picker dialog).
    if (matches(`${provider.name} ${provider.slug}`, query)) return [provider];
    const models = provider.models.filter((m) => matches(modelSearchText(m.id), query));
    return models.length ? [{ ...provider, models }] : [];
  });
}

export function filterModelCatalog(catalog: ModelCatalog, query: string): ModelCatalog {
  const q = query.trim();
  if (!q) return catalog;
  return {
    inUse: catalog.inUse.filter(
      (e) => matches(modelSearchText(e.model), q) || matches(`${e.providerName} ${e.provider}`, q),
    ),
    local: filterProviders(catalog.local, q),
    cloud: filterProviders(catalog.cloud, q),
    unconfigured: filterProviders(catalog.unconfigured, q),
  };
}

export function catalogModelCount(catalog: ModelCatalog): number {
  return [...catalog.local, ...catalog.cloud].reduce((n, p) => n + p.models.length, 0);
}
