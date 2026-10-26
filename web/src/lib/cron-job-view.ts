// Display helpers for cron job rows, shared by the Cron page and its job card. Moved out of
// CronPage.tsx so the page shrinks (code-health ratchet) and the card can be its own component.
import type { CronJob, CronJobRun } from "./api";
import { describeSchedule, type ScheduleDescribeStrings } from "./schedule";

export function formatTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function truncateText(value: string, maxLength: number): string {
  return value.length > maxLength ? value.slice(0, maxLength) + "..." : value;
}

export function getJobPrompt(job: CronJob): string {
  return asText(job.prompt);
}

export function getJobName(job: CronJob): string {
  return asText(job.name).trim();
}

export function getJobTitle(job: CronJob): string {
  const name = getJobName(job);
  if (name) return name;

  const prompt = getJobPrompt(job);
  if (prompt) return truncateText(prompt, 60);

  const script = asText(job.script);
  if (script) return truncateText(script, 60);

  return job.id || "Cron job";
}

/** Structured render ("Weekly on Mon, Wed, Fri at 14:30") instead of raw five-field cron, falling
 *  back through the backend's ``schedule_display`` and the structured ``display`` field. */
export function getJobScheduleDisplay(
  job: CronJob,
  strings: ScheduleDescribeStrings,
): string {
  return describeSchedule(
    job.schedule,
    asText(job.schedule_display) || asText(job.schedule?.display),
    strings,
  );
}

export function getJobState(job: CronJob): string {
  return asText(job.state) || (job.enabled === false ? "disabled" : "scheduled");
}

export function getRepeatDisplay(job: CronJob): string {
  const repeat = job.repeat;
  if (!repeat || repeat.times == null) return "forever";
  const completed = repeat.completed ?? 0;
  return completed > 0 ? `${completed}/${repeat.times}` : `${repeat.times} times`;
}

export function getJobMode(job: CronJob): string {
  if (job.no_agent) return "no_agent";
  if (job.script) return "script+agent";
  return "agent";
}

export function getModelDisplay(job: CronJob): string {
  const provider = asText(job.provider);
  const model = asText(job.model);
  if (provider && model) return `${provider}/${model}`;
  return model || provider;
}

export function getJobProfile(job: CronJob): string {
  return asText(job.profile) || asText(job.profile_name) || "default";
}

export function getJobKey(job: CronJob): string {
  return `${getJobProfile(job)}:${job.id}`;
}

export function splitJobKey(key: string): { profile: string; id: string } {
  const idx = key.indexOf(":");
  if (idx === -1) return { profile: "default", id: key };
  return { profile: key.slice(0, idx) || "default", id: key.slice(idx + 1) };
}

export const STATUS_TONE: Record<string, "success" | "warning" | "destructive"> = {
  enabled: "success",
  scheduled: "success",
  paused: "warning",
  error: "destructive",
  completed: "destructive",
};

export type CronRunStateKey = "live" | "finished" | "unfinished" | "output";

/** A run-history row's state as the scheduler sees it. A never-closed run session the scheduler
 *  no longer owns is a zombie ("never closed"), not a live run: `is_active` is only a 300 s
 *  activity window, so a live run inside a long tool call reads inactive too (#88443). */
export function cronRunState(run: CronJobRun): {
  key: CronRunStateKey;
  tone: "success" | "warning" | "secondary" | "outline";
} {
  if (run.source === "cron_output") return { key: "output", tone: "outline" };
  if (run.ended_at != null) return { key: "finished", tone: "secondary" };
  const live = typeof run.scheduler_owned === "boolean" ? run.scheduler_owned : !!run.is_active;
  return live ? { key: "live", tone: "success" } : { key: "unfinished", tone: "warning" };
}

/** "42s" / "7m" / "1.5h" for a closed agent run; "" for a live run or a script output doc. */
export function cronRunDuration(run: CronJobRun): string {
  if (run.ended_at == null || run.source === "cron_output") return "";
  const s = Math.max(0, Math.round(run.ended_at - run.started_at));
  if (s < 60) return `${s}s`;
  return s < 3600 ? `${Math.round(s / 60)}m` : `${(s / 3600).toFixed(1)}h`;
}
