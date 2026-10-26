import { CalendarDays, ChevronLeft, ChevronRight, RefreshCw, Sun } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodayCopy } from "./copy";
import { dayRelation, longDay } from "./today-model";

interface DayHeaderProps {
  copy: TodayCopy;
  day: string;
  locale: string;
  loading: boolean;
  onDay: (day: string) => void;
  onRefresh: () => void;
  onShift: (delta: number) => void;
  todayIso: string;
  updatedAt: string;
}

const ROUND_BUTTON =
  "clawk-liquid-chip inline-flex h-[44px] min-w-[44px] items-center justify-center rounded-full text-text-secondary transition-colors hover:text-midground disabled:pointer-events-none disabled:opacity-35";

function capitalize(text: string): string {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/** Title bar: which day is shown, ← → to browse, a jump back to today and a refresh. */
export function DayHeader(props: DayHeaderProps) {
  const { copy, day, locale, loading, onDay, onRefresh, onShift, todayIso, updatedAt } = props;
  const relation = dayRelation(day, todayIso);
  const dateLabel = capitalize(longDay(day, locale));
  const title =
    relation === "today" ? copy.today : relation === "yesterday" ? copy.yesterday : dateLabel;
  const Icon = relation === "today" ? Sun : CalendarDays;

  return (
    <header className="clawk-liquid-glass flex flex-wrap items-center gap-3 rounded-3xl border border-white/10 px-4 py-3 sm:gap-4 sm:px-5 sm:py-4">
      <div className="clawk-liquid-chip flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded-2xl">
        <Icon className="h-5 w-5 text-midground" aria-hidden />
      </div>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-xl font-semibold tracking-tight text-text-primary sm:text-2xl">{title}</h1>
        <p className="truncate text-sm text-text-tertiary">
          {relation === "today" || relation === "yesterday" ? dateLabel : copy.pageTitle}
          {updatedAt && <span className="opacity-80"> · {updatedAt}</span>}
        </p>
      </div>
      <nav className="flex w-full items-center justify-between gap-2 sm:w-auto sm:justify-end" aria-label={copy.pageTitle}>
        <button type="button" className={ROUND_BUTTON} onClick={() => onShift(-1)} aria-label={copy.previousDay} title={copy.previousDay}>
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button
          type="button"
          className={cn(ROUND_BUTTON, "px-4 text-sm font-medium", relation === "today" && "text-midground")}
          onClick={() => onDay(todayIso)}
          disabled={relation === "today"}
          title={copy.backToToday}
        >
          {copy.today}
        </button>
        <button
          type="button"
          className={ROUND_BUTTON}
          onClick={() => onShift(1)}
          disabled={relation === "today" || relation === "future"}
          aria-label={copy.nextDay}
          title={copy.nextDay}
        >
          <ChevronRight className="h-5 w-5" />
        </button>
        <button type="button" className={cn(ROUND_BUTTON, "ml-auto sm:ml-1")} onClick={onRefresh} aria-label={copy.refresh} title={copy.refresh}>
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </button>
      </nav>
    </header>
  );
}
