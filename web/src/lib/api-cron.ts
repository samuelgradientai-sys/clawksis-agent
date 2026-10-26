// Cron API shapes (clawk_cli/web_routers/cron.py). Split out of api.ts so that facade
// stays under its code-health line cap.

export interface CronOccurrenceJob {
  id: string;
  name: string;
  profile?: string | null;
  schedule_display?: string | null;
  /** Map of "YYYY-MM-DD" → number of firings that day (in server timezone). */
  days: Record<string, number>;
}

export interface CronJobRepeat {
  times: number | null;
  completed?: number;
}

export interface CronJobMutation {
  name?: string;
  prompt?: string;
  schedule?: string;
  deliver?: string;
  skills?: string[];
  provider?: string | null;
  model?: string | null;
  base_url?: string | null;
  script?: string | null;
  no_agent?: boolean;
  context_from?: string[] | null;
  enabled_toolsets?: string[] | null;
  workdir?: string | null;
  // Clawksis cron extensions (repeat count, SOUL/USER/MEMORY toggles,
  // "no news" notice, per-job model fallback chain as "provider:model").
  repeat?: number | null;
  silent_notice?: boolean;
  use_soul?: boolean;
  use_user_md?: boolean;
  use_memory?: boolean;
  fallback_models?: string[];
}

export interface CronJob {
  id: string;
  profile?: string | null;
  profile_name?: string | null;
  clawk_home?: string | null;
  is_default_profile?: boolean;
  name?: string | null;
  prompt?: string | null;
  script?: string | null;
  skills?: string[] | null;
  schedule?: { kind?: string; expr?: string; run_at?: string; display?: string };
  schedule_display?: string | null;
  repeat?: CronJobRepeat | null;
  enabled: boolean;
  state?: string | null;
  deliver?: string | null;
  model?: string | null;
  provider?: string | null;
  base_url?: string | null;
  no_agent?: boolean | null;
  context_from?: string[] | string | null;
  enabled_toolsets?: string[] | null;
  workdir?: string | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  /** Seconds since the job's profile ticker last iterated; null when it cannot be dated. */
  scheduler_heartbeat_age_s?: number | null;
  last_status?: string | null;
  last_error?: string | null;
  last_delivery_error?: string | null;
  last_fire_error?: { at?: string | null; detail?: string | null } | null;
  silent_notice?: boolean;
  use_soul?: boolean;
  use_user_md?: boolean;
  use_memory?: boolean;
  fallback_models?: { provider: string; model: string }[] | null;
}

export interface CronDeliveryTarget {
  id: string;
  name: string;
  home_target_set: boolean;
  home_env_var: string | null;
}

/** One run-history row (GET /api/cron/jobs/{id}/runs): an agent run is a ``source="cron"``
 * session; a script-only fire is its output doc (``source="cron_output"``, no transcript). */
export interface CronJobRun {
  id: string;
  source: string | null;
  title: string | null;
  preview: string | null;
  started_at: number;
  ended_at: number | null;
  last_active: number;
  message_count: number;
  is_active?: boolean;
  /** The scheduler still owns this never-closed run (a live run, not a zombie). */
  scheduler_owned?: boolean;
  profile?: string;
  model?: string | null;
}

export interface CronJobRunsResponse {
  runs: CronJobRun[];
  limit: number;
}
