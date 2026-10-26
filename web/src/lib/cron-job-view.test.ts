import { describe, expect, it } from "vitest";

import type { CronJobRun } from "./api";
import { cronRunDuration, cronRunState } from "./cron-job-view";

const run = (over: Partial<CronJobRun>): CronJobRun => ({
  id: "cron_job_20261026_090000",
  source: "cron",
  title: null,
  preview: null,
  started_at: 1_000,
  ended_at: null,
  last_active: 1_000,
  message_count: 2,
  ...over,
});

describe("cronRunState", () => {
  it("trusts scheduler ownership over the activity window for a never-closed run", () => {
    // Inside a long tool call: no recent activity, but the scheduler still owns it.
    expect(cronRunState(run({ is_active: false, scheduler_owned: true })).key).toBe("live");
    // Recently active but its process died: a zombie, not a live run.
    expect(cronRunState(run({ is_active: true, scheduler_owned: false })).key).toBe("unfinished");
  });

  it("falls back to the activity window on a backend without scheduler_owned", () => {
    expect(cronRunState(run({ is_active: true })).key).toBe("live");
    expect(cronRunState(run({})).key).toBe("unfinished");
  });

  it("labels closed runs and script-only output docs", () => {
    expect(cronRunState(run({ ended_at: 1_050 })).key).toBe("finished");
    expect(cronRunState(run({ source: "cron_output", ended_at: 1_000 })).key).toBe("output");
  });
});

describe("cronRunDuration", () => {
  it("formats closed agent runs and leaves live runs and output docs blank", () => {
    expect(cronRunDuration(run({ ended_at: 1_042 }))).toBe("42s");
    expect(cronRunDuration(run({ ended_at: 1_000 + 7 * 60 }))).toBe("7m");
    expect(cronRunDuration(run({ ended_at: 1_000 + 5400 }))).toBe("1.5h");
    expect(cronRunDuration(run({}))).toBe("");
    expect(cronRunDuration(run({ source: "cron_output", ended_at: 2_000 }))).toBe("");
  });
});
