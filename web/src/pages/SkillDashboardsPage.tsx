import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ArrowRight, Gauge, Package } from "lucide-react";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { cn } from "@/lib/utils";
import { api, type SkillInfo } from "@/lib/api";
import { useSkillDashboards } from "@/hooks/useSkillDashboards";
import { skillDashboardPath } from "@/lib/api-skill-dashboards";
import { dashboardCopy, fill } from "@/components/skill-dashboard/copy";
import { relativeTime } from "@/components/skill-dashboard/format";

/** Every skill dashboard of the managed profile, next to a summary of the
 *  installed skills — the one place where skills and their data meet. */
export default function SkillDashboardsPage() {
  const { t, locale } = useI18n();
  const copy = dashboardCopy(t);
  const dashboards = useSkillDashboards();
  const [skills, setSkills] = useState<SkillInfo[] | null>(null);
  const { setTitle } = usePageHeader();
  useEffect(() => setTitle(copy.title), [setTitle, copy.title]);

  useEffect(() => {
    api.getSkills().then(setSkills).catch(() => setSkills(null));
  }, []);

  const enabled = skills?.filter((s) => s.enabled).length ?? 0;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-1 sm:px-0">
      <header className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold text-text-primary">{copy.title}</h1>
        <p className="text-sm text-text-tertiary">{copy.subtitle}</p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          to="/skills"
          className="clawk-liquid-glass group flex flex-col gap-3 rounded-3xl border border-white/10 p-5 transition-colors hover:border-[#8B6DFF]/40"
        >
          <div className="flex items-center gap-3">
            <span className="clawk-liquid-chip flex h-10 w-10 items-center justify-center rounded-2xl">
              <Package className="h-5 w-5 text-midground" />
            </span>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-text-primary">{copy.installedSkills}</div>
              {skills && (
                <div className="text-xs text-text-tertiary">
                  {fill(copy.installedSkillsHint, { enabled, total: skills.length })}
                </div>
              )}
            </div>
          </div>
          <span className="mt-auto inline-flex items-center gap-1 text-sm text-text-secondary group-hover:text-midground">
            {copy.manageSkills} <ArrowRight className="h-4 w-4" />
          </span>
        </Link>

        {dashboards.map((d) => {
          const updated = relativeTime(d.modified_at, locale);
          return (
            <Link
              key={d.name}
              to={skillDashboardPath(d.name)}
              className={cn(
                "clawk-liquid-glass group flex flex-col gap-3 rounded-3xl border border-white/10 p-5 transition-colors hover:border-[#8B6DFF]/40",
                !d.enabled && "opacity-60",
              )}
            >
              <div className="flex items-center gap-3">
                <span className="clawk-liquid-chip flex h-10 w-10 items-center justify-center rounded-2xl text-lg">
                  {d.emoji || <Gauge className="h-5 w-5 text-midground" />}
                </span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-text-primary">{d.title}</div>
                  <div className="truncate text-xs text-text-tertiary">
                    {d.enabled ? (updated ? fill(copy.updated, { when: updated }) : copy.noData) : copy.disabled}
                  </div>
                </div>
              </div>
              {d.description && <p className="line-clamp-2 text-sm text-text-secondary">{d.description}</p>}
              <span className="mt-auto inline-flex items-center gap-1 text-sm text-text-secondary group-hover:text-midground">
                {copy.open} <ArrowRight className="h-4 w-4" />
              </span>
            </Link>
          );
        })}
      </div>

      {dashboards.length === 0 && (
        <div className="clawk-liquid-panel rounded-3xl px-6 py-8 text-center">
          <p className="text-base text-text-primary">{copy.empty}</p>
          <p className="mt-2 text-sm text-text-tertiary">{copy.emptyHint}</p>
        </div>
      )}
    </div>
  );
}
