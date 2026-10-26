import { Link } from "react-router";
import { ArrowUpRight, Gauge } from "lucide-react";
import { cn } from "@/lib/utils";
import { skillDashboardPath } from "@/lib/api-skill-dashboards";
import type { TodayDashboard } from "@/lib/api-today";
import { formatStat, TONE_TEXT } from "@/components/skill-dashboard/format";
import { fill, type TodayCopy } from "./copy";
import { TodayPanel } from "./Panel";
import { clock } from "./today-model";

interface DashboardCardsProps {
  copy: TodayCopy;
  dashboards: TodayDashboard[];
  locale: string;
  tz: string;
}

/** Skill mini dashboards (e.g. a trading skill) whose snapshot changed that day, with their headline stats. */
export function DashboardCards({ copy, dashboards, locale, tz }: DashboardCardsProps) {
  return (
    <TodayPanel icon={Gauge} title={copy.dashboardsTitle}>
      <div className={cn("grid grid-cols-1 gap-2.5", dashboards.length > 1 && "sm:grid-cols-2")}>
        {[...dashboards].reverse().map((d) => (
          <Link
            key={d.name}
            to={skillDashboardPath(d.name)}
            title={copy.dashboardOpen}
            className="clawk-liquid-stat group flex min-w-0 flex-col gap-2 rounded-2xl px-3.5 py-3"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="text-lg leading-none" aria-hidden>
                {d.emoji || "📊"}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary group-hover:text-midground">{d.title}</span>
              <ArrowUpRight className="h-4 w-4 shrink-0 text-text-tertiary" aria-hidden />
            </span>
            {d.stats.length > 0 && (
              <span className="flex flex-wrap gap-x-4 gap-y-1">
                {d.stats.map((s, i) => (
                  <span key={i} className="flex min-w-0 flex-col">
                    <span className="truncate text-[0.65rem] uppercase tracking-[0.1em] text-text-tertiary">{s.label}</span>
                    <span className={cn("text-base font-semibold tabular-nums", TONE_TEXT[s.tone] ?? "text-text-primary")}>
                      {formatStat(s.value, locale)}
                    </span>
                  </span>
                ))}
              </span>
            )}
            <span className="text-xs text-text-tertiary">{fill(copy.dashboardUpdated, { time: clock(d.at, tz, locale) })}</span>
          </Link>
        ))}
      </div>
    </TodayPanel>
  );
}
