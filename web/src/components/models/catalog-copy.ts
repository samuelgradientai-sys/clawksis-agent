import { en } from "@/i18n/en";
import { useI18n } from "@/i18n";
import type { ModelCatalogStrings } from "@/i18n/types";

/** Models page catalog copy, English until the active locale translates it. */
export function useCatalogCopy(): ModelCatalogStrings {
  const { t } = useI18n();
  return t.models.catalog ?? en.models.catalog!;
}

/** Replace `{name}` placeholders; unknown placeholders stay visible. */
export function fillCopy(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}
