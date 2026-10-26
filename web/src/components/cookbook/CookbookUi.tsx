import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

type Tone = "primary" | "default" | "danger" | "ghost";

const TONE: Record<Tone, string> = {
  primary:
    "border-[rgb(var(--clawk-liquid-violet)/0.55)] bg-[rgb(var(--clawk-liquid-violet)/0.18)] text-foreground hover:bg-[rgb(var(--clawk-liquid-violet)/0.28)]",
  default: "border-white/10 bg-white/[0.04] text-foreground/90 hover:bg-white/[0.08]",
  danger: "border-rose-500/30 bg-rose-500/[0.06] text-rose-300 hover:bg-rose-500/[0.14]",
  ghost: "border-transparent text-muted-foreground hover:bg-white/[0.06] hover:text-foreground",
};

/** The Cookbook's action button: rounded, compact, one of four tones. */
export function CbButton({
  tone = "default",
  className,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        TONE[tone],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

const PILL: Record<string, string> = {
  ollama: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  llamacpp: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  ok: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  warn: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  info: "border-sky-500/30 bg-sky-500/10 text-sky-300",
  muted: "border-white/10 bg-white/[0.04] text-muted-foreground",
};

/** A small rounded label (backend, "installed", "tools", context…). */
export function Pill({
  kind = "muted",
  className,
  title,
  children,
}: {
  kind?: keyof typeof PILL | string;
  className?: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] leading-4",
        PILL[kind] ?? kind,
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A liquid-glass panel (cards, list rows). */
export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("clawk-liquid-panel min-w-0 rounded-2xl p-3 sm:p-4", className)}>{children}</div>;
}

export function Row({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("clawk-liquid-row min-w-0 rounded-xl border border-white/[0.06] p-3", className)}>{children}</div>
  );
}
