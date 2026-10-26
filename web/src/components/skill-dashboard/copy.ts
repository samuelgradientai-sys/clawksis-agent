import { en } from "@/i18n/en";
import type { SkillDashboardsCopy, Translations } from "@/i18n/types";

/** Skill-dashboard strings for the active locale, English where untranslated. */
export function dashboardCopy(t: Translations): SkillDashboardsCopy {
  return { ...(en.skillDashboards as SkillDashboardsCopy), ...t.skillDashboards };
}

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}
