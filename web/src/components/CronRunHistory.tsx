import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api, type CronJobRun, type SessionMessage } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { LoadErrorNotice } from "@/components/LoadErrorNotice";
import { cronRunDuration, cronRunState } from "@/lib/cron-job-view";
import { useI18n } from "@/i18n";
import { en } from "@/i18n/en";


function RunTranscript({ run }: { run: CronJobRun }) {
  const [messages, setMessages] = useState<SessionMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getSessionMessages(run.id, run.profile)
      .then((r) => alive && setMessages(r.messages))
      .catch((e) => alive && setError(errorMessage(e)));
    return () => {
      alive = false;
    };
  }, [run.id, run.profile]);

  if (error) return <p className="px-3 py-2 text-xs text-destructive">{error}</p>;
  if (!messages) return <Spinner className="m-3 text-sm" />;
  return (
    <div className="max-h-72 overflow-y-auto border-t border-border bg-background/40 px-3 py-2">
      {messages
        .filter((m) => m.content)
        .map((m, i) => (
          <div key={i} className="mb-2 text-xs">
            <span className="mr-2 font-mono-ui uppercase text-muted-foreground">{m.tool_name ?? m.role}</span>
            <span className="whitespace-pre-wrap break-words">{(m.content ?? "").slice(0, 2000)}</span>
          </div>
        ))}
    </div>
  );
}

function RunRow({ run }: { run: CronJobRun }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const state = cronRunState(run);
  const labels = {
    live: t.cron.runLive ?? en.cron.runLive!,
    finished: t.cron.runFinished ?? en.cron.runFinished!,
    unfinished: t.cron.runUnfinished ?? en.cron.runUnfinished!,
    output: t.cron.runScriptOutput ?? en.cron.runScriptOutput!,
  };
  const hasTranscript = run.source === "cron";
  return (
    <div className="border-b border-border/60 last:border-b-0">
      <button
        type="button"
        disabled={!hasTranscript}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={hasTranscript ? open : undefined}
        title={hasTranscript ? (t.cron.showTranscript ?? en.cron.showTranscript) : undefined}
        className="flex w-full min-w-0 items-center gap-2 px-3 py-2 text-left text-xs hover:bg-secondary/30 disabled:cursor-default disabled:hover:bg-transparent"
      >
        {hasTranscript ? (
          open ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <span className="shrink-0 tabular-nums text-muted-foreground">
          {new Date(run.started_at * 1000).toLocaleString()}
        </span>
        <Badge tone={state.tone} className="shrink-0 text-xs">
          {labels[state.key]}
        </Badge>
        {cronRunDuration(run) && <span className="shrink-0 text-muted-foreground">{cronRunDuration(run)}</span>}
        {hasTranscript && (
          <span className="shrink-0 text-muted-foreground">
            {run.message_count} {t.common.msgs}
          </span>
        )}
        <span className="min-w-0 flex-1 truncate">{run.preview || run.title || ""}</span>
      </button>
      {open && hasTranscript && <RunTranscript run={run} />}
    </div>
  );
}

/** A job's recent runs (agent sessions + script-only output docs, newest first), each agent run
 *  expandable to its transcript. Backed by GET /api/cron/jobs/{id}/runs. */
export function CronRunHistory({ jobId, profile }: { jobId: string; profile: string }) {
  const { t } = useI18n();
  const [runs, setRuns] = useState<CronJobRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .getCronJobRuns(jobId, profile)
      .then((r) => setRuns(r.runs))
      .catch((e) => setError(errorMessage(e)));
  }, [jobId, profile]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mt-3 border border-border bg-background/30">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t.cron.runHistory ?? en.cron.runHistory}
        </span>
        <Button ghost size="icon" onClick={load} aria-label={t.common.refresh} title={t.common.refresh}>
          <RefreshCw />
        </Button>
      </div>
      {error && (
        <LoadErrorNotice
          className="m-2"
          what={t.cron.runsWhat ?? en.cron.runsWhat!}
          detail={error}
          onRetry={load}
        />
      )}
      {!error && runs === null && <Spinner className="m-3 text-sm" />}
      {runs && runs.length === 0 && (
        <p className="px-3 py-3 text-xs text-muted-foreground">{t.cron.noRuns ?? en.cron.noRuns}</p>
      )}
      {runs?.map((run) => <RunRow key={run.id} run={run} />)}
    </div>
  );
}
