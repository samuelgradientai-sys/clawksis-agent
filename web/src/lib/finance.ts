// Finanzas: the dashboard section that gathers every finance skill (category
// "finance"): their mini dashboards as tabs, their settings, and the rest of
// the finance skills. Finance dashboards leave the Plugins group for it.

import type { FinanceCopy, Translations } from "@/i18n/types";

export type { FinanceCopy };

export const FINANCE_CATEGORY = "finance";
export const FINANCE_PATH = "/finanzas";

export function financePath(name?: string): string {
  return name ? `${FINANCE_PATH}/${encodeURIComponent(name)}` : FINANCE_PATH;
}

const EN: FinanceCopy = {
  title: "Finance",
  empty: "No finance skill with a dashboard is installed yet.",
  emptyHint: "Install a finance skill (for example Kronos) to see its panels and settings here.",
  otherSkills: "Other finance skills",
  disabled: "disabled",
  manageSkills: "Manage skills",
};

/** Finance strings for the active locale, English where untranslated. */
export function financeCopy(t: Translations): FinanceCopy {
  return { ...EN, ...(t.finance ?? {}) };
}
