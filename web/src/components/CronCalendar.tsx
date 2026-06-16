import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import { api, type CronOccurrenceJob } from "@/lib/api";

/**
 * Month-grid visual of when the active cron jobs fire. For each day in the
 * viewed month it renders a small chip per job that fires that day (with a
 * ``×N`` suffix when it fires multiple times, e.g. a 30-minute interval).
 *
 * Firing days come from the backend ``/api/cron/occurrences`` endpoint, which
 * projects each job's schedule with the canonical scheduler logic (croniter /
 * interval phase / one-shot) — so "every day" lands on every day and
 * "every 3 days" lands on the right days, matching what will actually run.
 *
 * Grid math mirrors CalendarDayPicker (Sunday-first, leading blanks); unlike
 * that picker we allow navigating into past months so the pattern is visible.
 */
export function CronCalendar({ profile }: { profile: string }) {
  const { t, locale } = useI18n();
  const weekdayLabels = t.cron.scheduleModes.weekdaysShort;

  const today = new Date();
  const todayIso = toIsoDate(
    today.getFullYear(),
    today.getMonth() + 1,
    today.getDate(),
  );

  const [view, setView] = useState({
    year: today.getFullYear(),
    month: today.getMonth() + 1,
  });
  const [jobs, setJobs] = useState<CronOccurrenceJob[]>([]);
  const [loading, setLoading] = useState(false);

  const daysInMonth = new Date(view.year, view.month, 0).getDate();
  const firstWeekday = new Date(view.year, view.month - 1, 1).getDay();
  const monthLabel = new Intl.DateTimeFormat(locale, {
    month: "long",
    year: "numeric",
  }).format(new Date(view.year, view.month - 1, 1));

  useEffect(() => {
    const from = toIsoDate(view.year, view.month, 1);
    const to = toIsoDate(view.year, view.month, daysInMonth);
    let alive = true;
    setLoading(true);
    api
      .getCronOccurrences(from, to, profile)
      .then((r) => {
        if (alive) setJobs(r.jobs || []);
      })
      .catch(() => {
        if (alive) setJobs([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [view.year, view.month, daysInMonth, profile]);

  const shiftMonth = (delta: number) => {
    setView((v) => {
      const d = new Date(v.year, v.month - 1 + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1 };
    });
  };

  const cells: (number | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <div className="border border-border bg-background/40 p-3">
      <div className="mb-2 flex items-center justify-between">
        <Button
          ghost
          type="button"
          size="icon"
          onClick={() => shiftMonth(-1)}
          aria-label="Previous month"
        >
          <ChevronLeft />
        </Button>
        <span className="text-sm font-mono-ui capitalize">{monthLabel}</span>
        <Button
          ghost
          type="button"
          size="icon"
          onClick={() => shiftMonth(1)}
          aria-label="Next month"
        >
          <ChevronRight />
        </Button>
      </div>

      <div className="grid grid-cols-7 gap-1">
        {weekdayLabels.map((label, i) => (
          <span
            key={`${i}-${label}`}
            className="py-1 text-center text-[10px] uppercase tracking-wide text-muted-foreground"
          >
            {label}
          </span>
        ))}

        {cells.map((day, i) => {
          if (day === null) {
            return <span key={`blank-${i}`} />;
          }
          const iso = toIsoDate(view.year, view.month, day);
          const isToday = iso === todayIso;
          const fires = jobs
            .map((job, idx) => ({ job, idx, count: job.days[iso] || 0 }))
            .filter((f) => f.count > 0);
          return (
            <div
              key={iso}
              className={cn(
                "min-h-[68px] border border-border/40 p-1 align-top",
                isToday && "ring-1 ring-primary/60",
              )}
            >
              <div
                className={cn(
                  "text-[10px] leading-none text-muted-foreground",
                  isToday && "font-semibold text-foreground",
                )}
              >
                {day}
              </div>
              <div className="mt-1 flex flex-col gap-0.5">
                {fires.slice(0, 3).map(({ job, idx, count }) => (
                  <span
                    key={job.id}
                    title={`${job.name}${count > 1 ? ` ×${count}` : ""}${
                      job.schedule_display ? ` — ${job.schedule_display}` : ""
                    }`}
                    className={cn(
                      "truncate rounded-sm px-1 text-[9px] leading-tight",
                      CHIP_STYLES[idx % CHIP_STYLES.length],
                    )}
                  >
                    {job.name}
                    {count > 1 ? ` ×${count}` : ""}
                  </span>
                ))}
                {fires.length > 3 && (
                  <span className="px-1 text-[9px] text-muted-foreground">
                    +{fires.length - 3}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {loading && (
        <div className="mt-2 text-center text-xs text-muted-foreground">
          {t.common.loading}
        </div>
      )}
      {!loading && jobs.length === 0 && (
        <div className="mt-2 text-center text-xs text-muted-foreground">
          {t.cron.noJobs}
        </div>
      )}
    </div>
  );
}

/** Tailwind chip styles cycled per job so adjacent crons are distinguishable. */
const CHIP_STYLES = [
  "bg-primary/20 text-foreground",
  "bg-emerald-500/20 text-emerald-200",
  "bg-amber-500/20 text-amber-200",
  "bg-sky-500/20 text-sky-200",
  "bg-fuchsia-500/20 text-fuchsia-200",
  "bg-rose-500/20 text-rose-200",
];

function toIsoDate(year: number, month: number, day: number): string {
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}
