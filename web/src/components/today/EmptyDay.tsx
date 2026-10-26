import type { ReactNode } from "react";
import { Link } from "react-router";
import { Coffee, MessageSquarePlus, Moon } from "lucide-react";
import type { TodayCopy } from "./copy";

interface EmptyDayProps {
  copy: TodayCopy;
  footer?: ReactNode;
  isToday: boolean;
}

/** "Hoy todavía no hizo nada" — or, for a past day, that nothing happened then. */
export function EmptyDay({ copy, footer, isToday }: EmptyDayProps) {
  const Icon = isToday ? Coffee : Moon;
  return (
    <section className="clawk-liquid-panel relative flex flex-col items-center gap-3 overflow-hidden rounded-3xl px-6 py-12 text-center sm:py-16">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-0 h-56 w-56 -translate-x-1/2 -translate-y-1/3 rounded-full bg-[radial-gradient(circle,rgb(var(--clawk-liquid-violet)/0.22),transparent_65%)] blur-2xl"
      />
      <span className="clawk-liquid-chip relative flex h-14 w-14 items-center justify-center rounded-2xl">
        <Icon className="h-6 w-6 text-midground" aria-hidden />
      </span>
      <h2 className="relative text-lg font-semibold text-text-primary sm:text-xl">
        {isToday ? copy.emptyTodayTitle : copy.emptyPastTitle}
      </h2>
      <p className="relative max-w-md text-sm text-text-tertiary">{isToday ? copy.emptyTodayBody : copy.emptyPastBody}</p>
      {isToday && (
        <Link
          to="/chat"
          className="clawk-liquid-chip relative mt-2 inline-flex min-h-[44px] items-center gap-2 rounded-full px-5 text-sm font-medium text-text-primary transition-colors hover:text-midground"
        >
          <MessageSquarePlus className="h-4 w-4" aria-hidden />
          {copy.openChat}
        </Link>
      )}
      {footer && <div className="relative mt-2">{footer}</div>}
    </section>
  );
}

/** Placeholder blocks shaped like the page while the first load runs. */
export function TodaySkeleton() {
  const block = "animate-pulse rounded-3xl bg-white/[0.04] border border-white/[0.06]";
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <div className={`${block} h-44`} />
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 sm:gap-3">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="h-[5.5rem] animate-pulse rounded-2xl bg-white/[0.04]" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className={`${block} h-72`} />
        <div className={`${block} h-72`} />
      </div>
    </div>
  );
}
