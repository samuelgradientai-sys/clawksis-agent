/**
 * Grouping for the composer's model menu: the model in use pinned on top, then local providers
 * (Ollama, LM Studio, llama.cpp, local endpoints), then cloud providers — each in the backend's
 * order. "In use" is the row's `is_current` (the backend's verdict for the live session) or a
 * slug match, plus the model id: a `provider: custom` session served by a named endpoint row has
 * slug `custom:<name>`, so the slug alone never found it.
 */
import type { ModelOptionProvider } from "./hooks/useModelOptions";

export interface MenuModel {
  provider: string;
  providerName: string;
  model: string;
  isLocal: boolean;
}

export interface MenuGroup {
  slug: string;
  name: string;
  isLocal: boolean;
  models: string[];
}

export interface MenuGroups {
  inUse: MenuModel | null;
  local: MenuGroup[];
  cloud: MenuGroup[];
}

export function isRowInUse(
  row: ModelOptionProvider,
  model: string,
  currentModel: string,
  currentProvider: string,
): boolean {
  if (!currentModel || model !== currentModel) return false;
  return !!row.is_current || (!!currentProvider && row.slug === currentProvider);
}

function matchesQuery(text: string, query: string): boolean {
  return text.toLowerCase().includes(query);
}

export function groupMenuModels(
  providers: ModelOptionProvider[],
  currentModel: string,
  currentProvider: string,
  query: string,
): MenuGroups {
  const q = query.trim().toLowerCase();
  let inUse: MenuModel | null = null;
  const local: MenuGroup[] = [];
  const cloud: MenuGroup[] = [];
  for (const row of providers) {
    const all = row.models ?? [];
    const providerHit = !!q && (matchesQuery(row.name, q) || matchesQuery(row.slug, q));
    const models = !q || providerHit ? all : all.filter((m) => matchesQuery(m, q));
    for (const model of all) {
      if (!inUse && isRowInUse(row, model, currentModel, currentProvider)) {
        inUse = { provider: row.slug, providerName: row.name, model, isLocal: !!row.is_local };
      }
    }
    if (!models.length) continue;
    (row.is_local ? local : cloud).push({
      slug: row.slug,
      name: row.name,
      isLocal: !!row.is_local,
      models,
    });
  }
  const inUseVisible =
    inUse &&
    (!q ||
      matchesQuery(inUse.model, q) ||
      matchesQuery(inUse.providerName, q) ||
      matchesQuery(inUse.provider, q));
  return { inUse: inUseVisible ? inUse : null, local, cloud };
}
