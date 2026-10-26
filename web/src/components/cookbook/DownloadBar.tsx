import { X } from "lucide-react";
import { fmtBytes, fmtEta, fmtSpeed, type TransferProgress } from "@/lib/cookbook";

/** Transfer progress: label + phase, a bar (indeterminate until the size is known), %, bytes,
 *  speed and ETA, with Cancel while it can still be cancelled. */
export function DownloadBar({
  label,
  progress,
  onCancel,
  tone = "violet",
}: {
  label: string;
  progress: TransferProgress;
  onCancel?: () => void;
  tone?: "violet" | "error" | "done";
}) {
  const pct = progress.percent ?? null;
  const bar =
    tone === "error" ? "bg-rose-400/80" : tone === "done" ? "bg-emerald-400/80" : "bg-[rgb(var(--clawk-liquid-violet))]";
  return (
    <div className="w-full min-w-0">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="min-w-0 truncate text-foreground/90">
          {label}
          {progress.phase ? <span className="text-muted-foreground"> · {progress.phase}</span> : null}
        </span>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            aria-label={`Cancel ${label}`}
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-rose-500/10 hover:text-rose-300"
          >
            <X className="h-3 w-3" /> Cancel
          </button>
        )}
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]">
        <div
          className={`h-full rounded-full ${bar} transition-all ${pct == null && tone === "violet" ? "w-1/3 animate-pulse" : ""}`}
          style={pct != null ? { width: `${Math.max(2, pct)}%` } : tone !== "violet" ? { width: "100%" } : undefined}
        />
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 text-[11px] text-muted-foreground tabular-nums">
        {pct != null && <span>{pct.toFixed(0)}%</span>}
        {!!progress.total && (
          <span>
            {fmtBytes(progress.downloaded)} / {fmtBytes(progress.total)}
          </span>
        )}
        {!!progress.speed_bps && <span>{fmtSpeed(progress.speed_bps)}</span>}
        {!!progress.eta_seconds && progress.eta_seconds > 0 && <span>ETA {fmtEta(progress.eta_seconds)}</span>}
      </div>
    </div>
  );
}
