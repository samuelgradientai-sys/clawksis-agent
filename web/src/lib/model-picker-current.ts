/**
 * Resolve what the dashboard model picker should treat as "current".
 *
 * `/api/model/options` always returns the *main* chat model. Auxiliary and
 * MoA pickers reuse that catalog, so they must pass the slot assignment or
 * the header/highlight will show GLM (or whatever the chat model is) while
 * the task list shows the real Vision/MoA pin.
 */

export interface PickerCurrent {
  model: string;
  provider: string;
  /** A slot pinned to a custom/local endpoint: its `base_url` (matches rows by endpoint). */
  baseUrl?: string;
}

export function isAutoPickerCurrent(current: PickerCurrent): boolean {
  const provider = current.provider.trim().toLowerCase();
  return !provider || provider === "auto";
}

/** Map an auxiliary-task row onto picker current. Auto/empty → auto. */
export function assignmentToPickerCurrent(
  assignment: { model?: string; provider?: string; base_url?: string } | null | undefined,
): PickerCurrent {
  const provider = String(assignment?.provider ?? "").trim();
  const model = String(assignment?.model ?? "").trim();
  if (!provider || provider.toLowerCase() === "auto") {
    return { model: "", provider: "auto" };
  }
  const baseUrl = String(assignment?.base_url ?? "").trim();
  return baseUrl ? { model, provider, baseUrl } : { model, provider };
}

/**
 * `override` wins when the picker is for a non-main slot. Missing override
 * keeps the catalog's main model (chat-session / Set Main Model).
 */
export function resolvePickerCurrent(
  options: { model?: string; provider?: string } | null | undefined,
  override?: { model?: string; provider?: string; baseUrl?: string } | null,
): PickerCurrent {
  if (override) {
    return {
      model: String(override.model ?? ""),
      provider: String(override.provider ?? ""),
      ...(override.baseUrl ? { baseUrl: override.baseUrl } : {}),
    };
  }
  return {
    model: String(options?.model ?? ""),
    provider: String(options?.provider ?? ""),
  };
}

export function formatPickerCurrentLabel(current: PickerCurrent): string {
  if (isAutoPickerCurrent(current)) {
    return "auto (use main model)";
  }
  const model = current.model.trim() || "(unknown)";
  const provider = current.provider.trim();
  return provider ? `${model} · ${provider}` : model;
}

export function resolveInitialProviderSlug(
  providers: readonly { slug: string; is_current?: boolean | null }[],
  currentProvider: string,
): string {
  const slug = currentProvider.trim();
  if (slug && slug.toLowerCase() !== "auto") {
    const match = providers.find((p) => p.slug === slug);
    if (match) return match.slug;
  }
  return (providers.find((p) => p.is_current) ?? providers[0])?.slug ?? "";
}

function normUrl(url: unknown): string {
  return String(url ?? "")
    .trim()
    .replace(/\/+$/, "")
    .toLowerCase();
}

/**
 * Whether the picker marks `row` as the slot's current provider. For the main slot the row's
 * `is_current` is the backend's verdict — `provider: custom` + a base_url served by a named
 * endpoint row has slug `custom:<name>`, so a slug comparison alone loses the selection. A slot
 * override (auxiliary task, MoA) is not what `is_current` describes; it matches by slug or by
 * its pinned endpoint instead.
 */
export function isCurrentProviderRow(
  row: {
    slug: string;
    is_current?: boolean | null;
    api_url?: string | null;
    local_url?: string | null;
  },
  current: PickerCurrent,
  hasOverride: boolean,
): boolean {
  if (isAutoPickerCurrent(current)) return false;
  if (row.slug === current.provider) return true;
  if (!hasOverride) return !!row.is_current;
  const pinned = normUrl(current.baseUrl);
  return !!pinned && normUrl(row.local_url ?? row.api_url) === pinned;
}
