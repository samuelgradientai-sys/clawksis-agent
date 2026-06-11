import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

/**
 * Dependency-free month-grid calendar for picking a single day.
 *
 * Used by the cron ScheduleBuilder's "Once" mode so users can click a
 * day instead of typing a date into the native datetime-local field.
 * Emits/accepts dates as ``YYYY-MM-DD`` strings (local time, no TZ
 * math) so the value concatenates directly into the ISO timestamp the
 * backend's ``parse_schedule`` expects.
 *
 * Month/year labels come from ``Intl.DateTimeFormat`` with the active
 * i18n locale; weekday headers reuse the existing
 * ``cron.scheduleModes.weekdaysShort`` strings (Sunday-first, matching
 * the cron weekday convention used across the schedule builder).
 *
 * Days before today are disabled — a one-shot job in the past would
 * never run, so offering those cells only invites a confusing 400.
 */
export function CalendarDayPicker({ onChange, value }: CalendarDayPickerProps) {
  const { t, locale } = useI18n();
  const weekdayLabels = t.cron.scheduleModes.weekdaysShort;

  const today = new Date();
  const todayIso = toIsoDate(
    today.getFullYear(),
    today.getMonth() + 1,
    today.getDate(),
  );

  const selected = parseIsoDate(value);
  const [view, setView] = useState<{ month: number; year: number }>(() =>
    selected
      ? { year: selected.year, month: selected.month }
      : { year: today.getFullYear(), month: today.getMonth() + 1 },
  );

  const monthLabel = new Intl.DateTimeFormat(locale, {
    month: "long",
    year: "numeric",
  }).format(new Date(view.year, view.month - 1, 1));

  const atCurrentMonth =
    view.year === today.getFullYear() && view.month === today.getMonth() + 1;

  const shiftMonth = (delta: number) => {
    setView((v) => {
      const d = new Date(v.year, v.month - 1 + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() + 1 };
    });
  };

  // Sunday-first grid: leading blanks for the offset of day 1, then one
  // cell per day of the viewed month.
  const firstWeekday = new Date(view.year, view.month - 1, 1).getDay();
  const daysInMonth = new Date(view.year, view.month, 0).getDate();
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
          disabled={atCurrentMonth}
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
          const isSelected = iso === value;
          const isToday = iso === todayIso;
          const isPast = iso < todayIso;
          return (
            <button
              key={iso}
              type="button"
              disabled={isPast}
              aria-pressed={isSelected}
              onClick={() => onChange(iso)}
              className={cn(
                "h-8 w-full text-xs font-mono-ui transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/30",
                isSelected
                  ? "bg-primary text-primary-foreground"
                  : isPast
                    ? "cursor-not-allowed text-muted-foreground/40"
                    : "text-foreground hover:bg-primary/15",
                isToday && !isSelected && "border border-primary/60",
              )}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Build a ``YYYY-MM-DD`` string from local calendar parts. String
 * comparison on this shape is chronological, which is what the
 * past-day checks above rely on. */
function toIsoDate(year: number, month: number, day: number): string {
  return `${year}-${pad2(month)}-${pad2(day)}`;
}

function parseIsoDate(
  value: string,
): { day: number; month: number; year: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return null;
  return {
    year: parseInt(m[1], 10),
    month: parseInt(m[2], 10),
    day: parseInt(m[3], 10),
  };
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

interface CalendarDayPickerProps {
  onChange: (value: string) => void;
  /** Selected day as ``YYYY-MM-DD``, or ``""`` when nothing is picked. */
  value: string;
}
