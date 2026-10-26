import { useState } from "react";
import { History, Pause, Pencil, Play, Trash2, Zap } from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import type { CronJob } from "@/lib/api";
import { cronLastResult, cronNextRunOverdueMs } from "@/lib/cron-job";
import {
  asText,
  formatTime,
  getJobMode,
  getJobName,
  getJobProfile,
  getJobPrompt,
  getJobScheduleDisplay,
  getJobState,
  getJobTitle,
  getModelDisplay,
  getRepeatDisplay,
  STATUS_TONE,
  truncateText,
} from "@/lib/cron-job-view";
import type { ScheduleDescribeStrings } from "@/lib/schedule";
import { CronRunHistory } from "@/components/CronRunHistory";
import { useI18n } from "@/i18n";
import { en } from "@/i18n/en";

interface CronJobCardProps {
  job: CronJob;
  scheduleStrings: ScheduleDescribeStrings;
  triggering: boolean;
  onPauseResume: (job: CronJob) => void;
  onTrigger: (job: CronJob) => void;
  onEdit: (job: CronJob) => void;
  onDelete: (job: CronJob) => void;
}

function JobBadges({ job }: { job: CronJob }) {
  const state = getJobState(job);
  const deliver = asText(job.deliver);
  const mode = getJobMode(job);
  const modelDisplay = getModelDisplay(job);
  const toolsets = Array.isArray(job.enabled_toolsets) ? job.enabled_toolsets.filter(Boolean) : [];
  const lastResult = cronLastResult(job);
  return (
    <>
      <Badge tone={STATUS_TONE[state] ?? "secondary"}>{state}</Badge>
      {lastResult && lastResult.status !== "ok" && (
        <Badge tone={lastResult.tone} title={lastResult.detail ?? undefined} data-testid="cron-last-result">
          {lastResult.status}
        </Badge>
      )}
      <Badge tone="outline">{getJobProfile(job)}</Badge>
      {deliver && deliver !== "local" && <Badge tone="outline">{deliver}</Badge>}
      {Array.isArray(job.skills) && job.skills.length > 0 && (
        <Badge tone="outline" title={job.skills.join(", ")}>
          {job.skills.length === 1 ? job.skills[0] : `${job.skills.length} skills`}
        </Badge>
      )}
      {mode !== "agent" && <Badge tone="outline">{mode}</Badge>}
      {modelDisplay && (
        <Badge tone="outline" title={modelDisplay}>
          model
        </Badge>
      )}
      {toolsets.length > 0 && (
        <Badge tone="outline" title={toolsets.join(", ")}>
          {toolsets.length} toolsets
        </Badge>
      )}
    </>
  );
}

function JobTimes({ job, scheduleStrings }: { job: CronJob; scheduleStrings: ScheduleDescribeStrings }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      <span className="font-mono-ui">{getJobScheduleDisplay(job, scheduleStrings)}</span>
      <span>repeat: {getRepeatDisplay(job)}</span>
      <span className="flex items-center gap-1">
        {job.last_run_at && job.last_status === "ok" && (
          <span className="inline-block text-success" title="Última ejecución exitosa" aria-label="ok">
            ✓
          </span>
        )}
        {job.last_run_at && job.last_status === "error" && (
          <span className="inline-block text-destructive" title="Última ejecución falló" aria-label="error">
            ✗
          </span>
        )}
        {t.cron.last}: {formatTime(job.last_run_at)}
      </span>
      {cronNextRunOverdueMs(job) === null ? (
        <span>
          {t.cron.next}: {formatTime(job.next_run_at)}
        </span>
      ) : (
        <span className="text-warning font-medium" data-testid="cron-next-run-overdue">
          {t.cron.overdueSince ?? en.cron.overdueSince!}: {formatTime(job.next_run_at)}
        </span>
      )}
    </div>
  );
}

/** One scheduled job: identity + badges, schedule/last/next, its errors, the actions, and an
 *  expandable run history. */
export function CronJobCard({
  job,
  scheduleStrings,
  triggering,
  onPauseResume,
  onTrigger,
  onEdit,
  onDelete,
}: CronJobCardProps) {
  const { t } = useI18n();
  const [historyOpen, setHistoryOpen] = useState(false);
  const paused = getJobState(job) === "paused";
  const promptText = getJobPrompt(job);
  const historyLabel = t.cron.runHistory ?? en.cron.runHistory!;

  return (
    <Card>
      <CardContent className="py-4">
        <div className="flex items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className="font-medium text-sm truncate min-w-0">{getJobTitle(job)}</span>
              <JobBadges job={job} />
            </div>
            {getJobName(job) && promptText && (
              <p className="text-xs text-muted-foreground truncate mb-1">{truncateText(promptText, 100)}</p>
            )}
            <JobTimes job={job} scheduleStrings={scheduleStrings} />
            {job.last_delivery_error && (
              <p className="text-xs text-destructive mt-1">delivery: {job.last_delivery_error}</p>
            )}
            {job.last_fire_error?.detail && (
              <p className="text-xs text-destructive mt-1">
                missed scheduled fire ({formatTime(job.last_fire_error.at ?? null)}): {job.last_fire_error.detail}
              </p>
            )}
            {job.last_error && <p className="text-xs text-destructive mt-1">{job.last_error}</p>}
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <Button
              ghost
              size="icon"
              title={historyLabel}
              aria-label={historyLabel}
              aria-expanded={historyOpen}
              onClick={() => setHistoryOpen((v) => !v)}
              className={historyOpen ? "text-foreground" : undefined}
            >
              <History />
            </Button>
            <Button
              ghost
              size="icon"
              title={paused ? t.cron.resume : t.cron.pause}
              aria-label={paused ? t.cron.resume : t.cron.pause}
              onClick={() => onPauseResume(job)}
              className={paused ? "text-success" : "text-warning"}
            >
              {paused ? <Play /> : <Pause />}
            </Button>
            <Button
              ghost
              size="icon"
              disabled={triggering}
              title={t.cron.triggerNow}
              aria-label={t.cron.triggerNow}
              onClick={() => onTrigger(job)}
            >
              {triggering ? <Spinner /> : <Zap />}
            </Button>
            <Button ghost size="icon" title="Edit job" aria-label="Edit job" onClick={() => onEdit(job)}>
              <Pencil />
            </Button>
            <Button
              ghost
              destructive
              size="icon"
              title={t.common.delete}
              aria-label={t.common.delete}
              onClick={() => onDelete(job)}
            >
              <Trash2 />
            </Button>
          </div>
        </div>
        {historyOpen && <CronRunHistory jobId={job.id} profile={getJobProfile(job)} />}
      </CardContent>
    </Card>
  );
}
