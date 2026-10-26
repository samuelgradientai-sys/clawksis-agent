// "Hoy" page API (clawk_cli/web_routers/today.py). It lives under /api/analytics so
// fetchJSON's management-profile scope appends ?profile= like every analytics read.

import { fetchJSON } from "./api";

export interface TodayStats {
  conversations: number;
  messages: number;
  user_messages: number;
  tool_calls: number;
  files_created: number;
  files_edited: number;
  files_deleted: number;
  commands: number;
  errors: number;
  cron_ok: number;
  cron_failed: number;
  cron_other: number;
  skills_created: number;
  skills_updated: number;
  /** Counters of the sessions STARTED that day (same attribution as Analytics). */
  sessions: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  reasoning_tokens: number;
  estimated_cost_usd: number;
  actual_cost_usd: number;
  api_calls: number;
}

export interface TodayConversation {
  id: string;
  /** The lineage's latest session — what "open" resumes. */
  open_id: string;
  title: string;
  source: string;
  model: string;
  started_at: number;
  ended_at: number;
  messages: number;
  tool_calls: number;
  commands: number;
  errors: number;
  files: number;
  /** Up to four basenames of the files it touched. */
  file_names: string[];
  /** First failed tool call ("tool: message"), "" when none failed. */
  error_sample: string;
  children: number;
  top_tools: Array<[string, number]>;
  ask: string;
  outcome: string;
}

export type TodayFileAction = "created" | "edited" | "deleted";

export interface TodayFile {
  path: string;
  action: TodayFileAction;
  count: number;
  first_at: number;
  last_at: number;
  session_id: string;
  /** Git work tree holding the file, else its folder. */
  project: string;
  in_repo: boolean;
}

export interface TodayCommand {
  command: string;
  at: number;
  session_id: string;
  exit_code: number | null;
  /** The tool reported an error (it still ran). */
  failed: boolean;
}

export interface TodaySkill {
  name: string;
  action: "created" | "updated" | "deleted";
  count: number;
  at: number;
  session_id: string;
}

export interface TodayError {
  at: number;
  session_id: string;
  tool: string;
  message: string;
}

export interface TodayCronRun {
  execution_id: string;
  job_id: string;
  job_name: string;
  status: "ok" | "failed" | "unknown" | "running";
  at: number;
  finished_at: number | null;
  error: string | null;
  session_id: string | null;
}

export interface TodayCronJob {
  id: string;
  name: string;
  schedule: string;
  deliver: string;
  at: number;
}

export interface TodayCommit {
  sha: string;
  at: number;
  author: string;
  subject: string;
  repo: string;
  repo_name: string;
}

export interface TodayDashboardStat {
  label: string;
  value: string | number | boolean | null;
  tone: "positive" | "negative" | "warning" | "neutral";
}

export interface TodayDashboard {
  name: string;
  title: string;
  emoji: string;
  subtitle: string;
  at: number;
  stats: TodayDashboardStat[];
}

export interface TodaySummary {
  text: string;
  lang: string;
  model: string;
  generated_at: number;
  fingerprint: string;
  /** The day gained activity after this summary was written. */
  stale: boolean;
}

export interface TodayResponse {
  date: string;
  tz: string;
  start: number;
  end: number;
  stats: TodayStats;
  fingerprint: string;
  has_activity: boolean;
  conversations: TodayConversation[];
  files: TodayFile[];
  commands: TodayCommand[];
  skills: TodaySkill[];
  errors: TodayError[];
  cron_runs: TodayCronRun[];
  cron_jobs_created: TodayCronJob[];
  commits: TodayCommit[];
  dashboards: TodayDashboard[];
  summary: TodaySummary | null;
}

export interface TodaySummaryResponse {
  summary: TodaySummary | null;
  error: string | null;
}

export const todayApi = {
  get: (date: string, tz: string) =>
    fetchJSON<TodayResponse>(
      `/api/analytics/today?date=${encodeURIComponent(date)}&tz=${encodeURIComponent(tz)}`,
    ),
  summary: (body: { date: string; tz: string; lang: string; regenerate?: boolean }) =>
    fetchJSON<TodaySummaryResponse>("/api/analytics/today/summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
