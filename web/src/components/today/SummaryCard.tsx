import type { ReactNode } from "react";
import { AlertTriangle, RefreshCw, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodaySummary } from "@/lib/api-today";
import { fill, type TodayCopy } from "./copy";
import { boldSegments, clock, parseSummary } from "./today-model";

export interface SummaryState {
  writing: boolean;
  error: string | null;
}

interface SummaryCardProps {
  copy: TodayCopy;
  footer?: ReactNode;
  locale: string;
  onGenerate: (regenerate: boolean) => void;
  state: SummaryState;
  summary: TodaySummary | null;
  tz: string;
}

function Rich({ text }: { text: string }) {
  return (
    <>
      {boldSegments(text).map((seg, i) =>
        seg.bold ? <strong key={i} className="font-semibold text-text-primary">{seg.text}</strong> : <span key={i}>{seg.text}</span>,
      )}
    </>
  );
}

function SummaryBody({ summary }: { summary: TodaySummary }) {
  const { headline, bullets } = parseSummary(summary.text);
  return (
    <div className="flex flex-col gap-3">
      {headline && (
        <p className="text-lg font-semibold leading-snug text-text-primary sm:text-xl">
          <Rich text={headline} />
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {bullets.map((line, i) => (
          <li key={i} className="flex gap-2.5 text-[0.95rem] leading-relaxed text-text-secondary">
            <span className="mt-[0.6rem] h-1.5 w-1.5 shrink-0 rounded-full bg-[rgb(var(--clawk-liquid-violet))]" aria-hidden />
            <span className="min-w-0">
              <Rich text={line} />
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Writing({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-live="polite">
      <div className="h-5 w-2/3 animate-pulse rounded-full bg-white/10" />
      {[0.92, 0.8, 0.86].map((w, i) => (
        <div key={i} className="h-3.5 animate-pulse rounded-full bg-white/[0.07]" style={{ width: `${w * 100}%` }} />
      ))}
      <p className="text-sm text-text-tertiary">{label}</p>
    </div>
  );
}

function Failure({ copy, error }: { copy: TodayCopy; error: string }) {
  return (
    <div className="flex gap-2.5 rounded-2xl border border-amber-400/25 bg-amber-400/[0.07] px-3.5 py-3 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" aria-hidden />
      <div className="min-w-0">
        <p className="break-words text-amber-100">{fill(copy.summaryFailed, { error })}</p>
        <p className="mt-1 text-text-tertiary">{copy.summaryNoModel}</p>
      </div>
    </div>
  );
}

function meta(copy: TodayCopy, summary: TodaySummary, tz: string, locale: string): string {
  const written = fill(copy.summaryMeta, { time: clock(summary.generated_at, tz, locale) });
  return summary.model ? `${written} ${fill(copy.summaryModel, { model: summary.model })}` : written;
}

/** The AI-written recap of the day: written on demand, cached per day, regenerable. */
export function SummaryCard({ copy, footer, locale, onGenerate, state, summary, tz }: SummaryCardProps) {
  const shown = state.writing ? null : summary;
  return (
    <section
      aria-label={copy.summaryTitle}
      className="clawk-liquid-panel relative overflow-hidden rounded-3xl p-4 sm:p-6"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-[radial-gradient(circle,rgb(var(--clawk-liquid-violet)/0.28),transparent_65%)] blur-2xl"
      />
      <header className="relative mb-4 flex items-center gap-2">
        <span className="clawk-liquid-chip flex h-8 w-8 items-center justify-center rounded-xl">
          <Sparkles className="h-4 w-4 text-[rgb(var(--clawk-liquid-violet))]" aria-hidden />
        </span>
        <h2 className="flex-1 text-sm font-semibold uppercase tracking-[0.12em] text-text-secondary">{copy.summaryTitle}</h2>
        <button
          type="button"
          onClick={() => onGenerate(Boolean(summary))}
          disabled={state.writing}
          className="clawk-liquid-chip inline-flex h-[44px] items-center gap-2 rounded-full px-4 text-sm text-text-secondary transition-colors hover:text-midground disabled:opacity-50"
        >
          <RefreshCw className={cn("h-4 w-4", state.writing && "animate-spin")} aria-hidden />
          {summary ? copy.summaryRegenerate : copy.summaryGenerate}
        </button>
      </header>
      <div className="relative flex flex-col gap-4">
        {state.writing && <Writing label={copy.summaryWriting} />}
        {shown && <SummaryBody summary={shown} />}
        {state.error && !state.writing && <Failure copy={copy} error={state.error} />}
        {!summary && !state.writing && !state.error && <p className="text-sm text-text-tertiary">{copy.summaryEmpty}</p>}
        {(shown || footer) && (
          <div className="flex flex-col gap-3 border-t border-white/[0.07] pt-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-text-tertiary">
              {shown && meta(copy, shown, tz, locale)}
              {shown?.stale && <span className="ml-1 text-amber-200/90">· {copy.summaryStale}</span>}
            </p>
            {footer}
          </div>
        )}
      </div>
    </section>
  );
}
