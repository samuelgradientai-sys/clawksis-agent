import { useCallback, useMemo, useState } from "react";
import type { SessionQueryOptions, SessionStoreStats } from "@/lib/api";
import type { Translations } from "@/i18n/types";
import {
  AUTOMATION_SESSION_SOURCES,
  NO_MATCHING_SESSION_SOURCE,
  type SessionFilterCategory,
  type SourceSelectionsByCategory,
  isAutomationSource,
  sourceBelongsToCategory,
  sourceLabel,
} from "./SessionsPage_sources";

/** Source scoping of the session list as backend query options. ``null`` selection = the
 *  category's default (chats exclude automation sources; automation keeps only them). */
function sourceQuery(
  selectedSources: string[] | null,
  category: SessionFilterCategory,
  allSourceNames: string[],
): SessionQueryOptions {
  if (selectedSources !== null) {
    if (selectedSources.length === 0) {
      return allSourceNames.length > 0 ? { excludeSources: allSourceNames } : { source: NO_MATCHING_SESSION_SOURCE };
    }
    if (selectedSources.length === 1) return { source: selectedSources[0] };
    const selected = new Set(selectedSources);
    const excluded = allSourceNames.filter((source) => !selected.has(source));
    return excluded.length > 0 ? { excludeSources: excluded } : {};
  }
  if (category === "chats") return { excludeSources: AUTOMATION_SESSION_SOURCES };
  if (category === "automation") {
    const excluded = allSourceNames.filter((source) => !isAutomationSource(source));
    return excluded.length > 0 ? { excludeSources: excluded } : { sources: AUTOMATION_SESSION_SOURCES };
  }
  return {};
}

function categoryLabels(category: SessionFilterCategory, t: Translations) {
  if (category === "chats") return { any: "Any chat source", title: "Chat sources" };
  if (category === "automation") return { any: "Any automation source", title: "Automation sources" };
  return { any: t.sessions.anySource, title: t.sessions.sourceFilter };
}

/**
 * Category (chats / automation / all) + per-source selection for the Sessions list, remembered
 * per category. ``onChange`` runs after every user change (reset page, expansion, selection).
 */
export function useSessionSourceFilter(stats: SessionStoreStats | null, t: Translations, onChange: () => void) {
  const [category, setCategory] = useState<SessionFilterCategory>("chats");
  const [selections, setSelections] = useState<SourceSelectionsByCategory>({ chats: null, automation: null, all: null });
  const selectedSources = selections[category];

  const allSourceOptions = useMemo(() => {
    const entries = Object.entries(stats?.by_source ?? {}).sort(
      ([aSource, aCount], [bSource, bCount]) => bCount - aCount || sourceLabel(aSource).localeCompare(sourceLabel(bSource)),
    );
    const seen = new Set(entries.map(([source]) => source));
    // A selected source the store no longer reports stays visible (count 0) so it can be unticked.
    for (const source of Object.values(selections).flatMap((selection) => selection ?? [])) {
      if (!seen.has(source)) {
        entries.unshift([source, 0]);
        seen.add(source);
      }
    }
    return entries;
  }, [selections, stats]);

  const allSourceNames = useMemo(() => allSourceOptions.map(([source]) => source), [allSourceOptions]);
  const queryOptions = useMemo(
    () => sourceQuery(selectedSources, category, allSourceNames),
    [selectedSources, category, allSourceNames],
  );
  const categoryDefaults = useMemo(
    () => allSourceNames.filter((source) => sourceBelongsToCategory(source, category)),
    [category, allSourceNames],
  );
  const options = useMemo(() => {
    const selected = new Set(selectedSources ?? []);
    return allSourceOptions.filter(([source]) => sourceBelongsToCategory(source, category) || selected.has(source));
  }, [allSourceOptions, selectedSources, category]);
  const selectedSet = useMemo(() => new Set(selectedSources ?? categoryDefaults), [selectedSources, categoryDefaults]);

  const labels = categoryLabels(category, t);
  let label = labels.any;
  if (selectedSources !== null) {
    label =
      selectedSources.length === 0
        ? "No sources"
        : selectedSources.length === 1
          ? sourceLabel(selectedSources[0])
          : `${selectedSources.length} sources`;
  }

  const changeCategory = useCallback(
    (value: string) => {
      setCategory(value as SessionFilterCategory);
      onChange();
    },
    [onChange],
  );

  const toggle = useCallback(
    (source: string) => {
      setSelections((current) => {
        const next = new Set(current[category] ?? categoryDefaults);
        if (next.has(source)) next.delete(source);
        else next.add(source);
        return {
          ...current,
          [category]: options.map(([optionSource]) => optionSource).filter((optionSource) => next.has(optionSource)),
        };
      });
      onChange();
    },
    [category, categoryDefaults, onChange, options],
  );

  const clear = useCallback(() => {
    setSelections((current) => ({ ...current, [category]: null }));
    onChange();
  }, [category, onChange]);

  return {
    category,
    changeCategory,
    queryOptions,
    options,
    selectedSet,
    hasSelection: selectedSources !== null,
    label,
    title: labels.title,
    allSourceNames,
    toggle,
    clear,
  };
}
