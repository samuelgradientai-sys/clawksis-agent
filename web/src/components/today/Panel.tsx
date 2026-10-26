import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface TodayPanelProps {
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  icon: ComponentType<{ className?: string }>;
  title: string;
}

/** The page's card: liquid panel, icon + title header, optional right-hand aside. */
export function TodayPanel({ aside, children, className, icon: Icon, title }: TodayPanelProps) {
  return (
    <section aria-label={title} className={cn("clawk-liquid-panel flex min-w-0 flex-col gap-4 rounded-3xl p-4 sm:p-5", className)}>
      <header className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-midground" aria-hidden />
        <h2 className="flex-1 text-sm font-semibold uppercase tracking-[0.12em] text-text-secondary">{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}

/** A labelled block inside a panel ("Archivos", "Commits", …). */
export function PanelSection({ children, count, title }: { children: ReactNode; count?: number; title: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <h3 className="flex items-center gap-2 px-1 text-[0.7rem] font-medium uppercase tracking-[0.12em] text-text-tertiary">
        {title}
        {count !== undefined && <span className="rounded-full bg-white/[0.06] px-2 py-0.5 tabular-nums">{count}</span>}
      </h3>
      {children}
    </div>
  );
}
