// Pure helpers for the "Hoy" page: calendar days in the viewer's zone, file grouping,
// the merged timeline and the summary's shape. No React, no fetch — vitest covers them.

import type {
  TodayCommit,
  TodayConversation,
  TodayCronJob,
  TodayCronRun,
  TodayDashboard,
  TodayFile,
  TodayResponse,
  TodaySkill,
} from "@/lib/api-today";

// ── calendar days ────────────────────────────────────────────────────────────

/** The viewer's IANA zone ("" when the runtime cannot name one). */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch {
    return "";
  }
}

/** YYYY-MM-DD of `when` in zone `tz` ("" = the runtime's zone). */
export function isoDay(when: Date, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz || undefined,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(when);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function dayToUtcNoon(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 12));
}

/** `iso` moved by `delta` calendar days (DST-proof: plain date arithmetic). */
export function shiftDay(iso: string, delta: number): string {
  const date = dayToUtcNoon(iso);
  date.setUTCDate(date.getUTCDate() + delta);
  return date.toISOString().slice(0, 10);
}

export function isValidDay(value: string | null | undefined): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  return shiftDay(value, 0) === value;
}

export type DayRelation = "today" | "yesterday" | "past" | "future";

export function dayRelation(iso: string, todayIso: string): DayRelation {
  if (iso === todayIso) return "today";
  if (iso === shiftDay(todayIso, -1)) return "yesterday";
  return iso < todayIso ? "past" : "future";
}

/** "lunes, 26 de octubre" — the calendar day itself, never shifted by a zone. */
export function longDay(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    timeZone: "UTC",
    weekday: "long",
    day: "numeric",
    month: "long",
    year: iso.slice(0, 4) === String(new Date().getFullYear()) ? undefined : "numeric",
  }).format(dayToUtcNoon(iso));
}

/** "09:12" of an epoch-seconds instant in zone `tz`. */
export function clock(ts: number, tz: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    timeZone: tz || undefined,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(ts * 1000));
}

/** "09:12–09:40", or one time when both ends fall in the same minute. */
export function timeSpan(start: number, end: number, tz: string, locale: string): string {
  const a = clock(start, tz, locale);
  const b = clock(end, tz, locale);
  return a === b ? a : `${a}–${b}`;
}

// ── numbers ──────────────────────────────────────────────────────────────────

export function compactNumber(n: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export function usd(n: number, locale: string): string {
  const format = (value: number) =>
    new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: value >= 100 ? 0 : 2,
    }).format(value);
  return n > 0 && n < 0.01 ? `< ${format(0.01)}` : format(n);
}

// ── files ────────────────────────────────────────────────────────────────────

export function basename(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

export function dirname(path: string): string {
  const cut = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return cut > 0 ? path.slice(0, cut) : path;
}

export interface FileRow extends TodayFile {
  /** Path inside its project folder. */
  rel: string;
}

export interface FileGroup {
  project: string;
  name: string;
  inRepo: boolean;
  lastAt: number;
  files: FileRow[];
}

function relativeTo(path: string, root: string): string {
  const prefix = root.endsWith("/") ? root : `${root}/`;
  return path.startsWith(prefix) ? path.slice(prefix.length) : basename(path);
}

/** Files bucketed by project (git work tree, else folder); busiest-recent project first. */
export function groupFilesByProject(files: readonly TodayFile[]): FileGroup[] {
  const groups = new Map<string, FileGroup>();
  for (const file of files) {
    const project = file.project || dirname(file.path);
    let group = groups.get(project);
    if (!group) {
      group = { project, name: basename(project), inRepo: file.in_repo, lastAt: 0, files: [] };
      groups.set(project, group);
    }
    group.files.push({ ...file, rel: relativeTo(file.path, project) });
    group.lastAt = Math.max(group.lastAt, file.last_at);
  }
  const sorted = [...groups.values()].sort((a, b) => b.lastAt - a.lastAt);
  for (const group of sorted) group.files.sort((a, b) => b.last_at - a.last_at);
  return sorted;
}

/** How many rows of each group fit in `budget` rows overall, in group order (groups left at 0 drop). */
export function budgetGroups(groups: readonly FileGroup[], budget: number): Array<{ group: FileGroup; limit: number }> {
  const shown: Array<{ group: FileGroup; limit: number }> = [];
  let left = budget;
  for (const group of groups) {
    const limit = Math.min(group.files.length, left);
    if (limit <= 0) break;
    shown.push({ group, limit });
    left -= limit;
  }
  return shown;
}

export function filesPageLink(path: string): string {
  return `/files?path=${encodeURIComponent(dirname(path))}`;
}

export function chatLink(sessionId: string): string {
  return `/chat?resume=${encodeURIComponent(sessionId)}`;
}

// ── timeline ─────────────────────────────────────────────────────────────────

export type TimelineItem =
  | { kind: "conversation"; at: number; key: string; conversation: TodayConversation }
  | { kind: "cron"; at: number; key: string; run: TodayCronRun }
  | { kind: "commit"; at: number; key: string; commit: TodayCommit }
  | { kind: "skill"; at: number; key: string; skill: TodaySkill }
  | { kind: "cronJob"; at: number; key: string; job: TodayCronJob }
  | { kind: "dashboard"; at: number; key: string; dashboard: TodayDashboard };

type TimelineSource = Pick<
  TodayResponse,
  "conversations" | "cron_runs" | "commits" | "skills" | "cron_jobs_created" | "dashboards"
>;

/** Everything that happened, oldest first (ties keep conversations ahead of what they caused). */
export function buildTimeline(data: TimelineSource): TimelineItem[] {
  const items: TimelineItem[] = [
    ...data.conversations.map((c) => ({ kind: "conversation" as const, at: c.started_at, key: `c:${c.id}`, conversation: c })),
    ...data.cron_runs.map((r, i) => ({ kind: "cron" as const, at: r.at, key: `r:${r.execution_id || i}`, run: r })),
    ...data.commits.map((c) => ({ kind: "commit" as const, at: c.at, key: `g:${c.repo}:${c.sha}`, commit: c })),
    ...data.skills.map((s) => ({ kind: "skill" as const, at: s.at, key: `s:${s.name}`, skill: s })),
    ...data.cron_jobs_created.map((j) => ({ kind: "cronJob" as const, at: j.at, key: `j:${j.id}`, job: j })),
    ...data.dashboards.map((d) => ({ kind: "dashboard" as const, at: d.at, key: `d:${d.name}`, dashboard: d })),
  ];
  const rank: Record<TimelineItem["kind"], number> = {
    conversation: 0,
    cron: 1,
    cronJob: 2,
    skill: 3,
    commit: 4,
    dashboard: 5,
  };
  return items.sort((a, b) => a.at - b.at || rank[a.kind] - rank[b.kind]);
}

// ── summary ──────────────────────────────────────────────────────────────────

export interface SummaryShape {
  headline: string;
  bullets: string[];
}

const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+/;

function plain(line: string): string {
  return line.replace(/^#+\s*/, "").replace(/^\*\*(.*)\*\*$/, "$1").trim();
}

/** The model's reply as a headline plus bullets; loose prose lines become bullets too. */
export function parseSummary(text: string): SummaryShape {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return { headline: "", bullets: [] };
  const [first, ...rest] = lines;
  const headline = BULLET.test(first) ? "" : plain(first);
  const body = BULLET.test(first) ? lines : rest;
  return { headline, bullets: body.map((l) => plain(l.replace(BULLET, ""))).filter(Boolean) };
}

/** `**bold**` runs of a summary line as alternating plain/bold segments. */
export function boldSegments(line: string): Array<{ text: string; bold: boolean }> {
  return line
    .split(/(\*\*[^*]+\*\*)/)
    .filter(Boolean)
    .map((part) =>
      part.startsWith("**") && part.endsWith("**")
        ? { text: part.slice(2, -2), bold: true }
        : { text: part, bold: false },
    );
}

// ── nightly digest ───────────────────────────────────────────────────────────

/** "0 22 * * *" → "22:00"; null for anything but a plain once-a-day expression. */
export function dailyTime(expr: string | null | undefined): string | null {
  const match = /^(\d{1,2}) (\d{1,2}) \* \* \*$/.exec((expr ?? "").trim());
  if (!match || Number(match[1]) > 59 || Number(match[2]) > 23) return null;
  return `${match[2].padStart(2, "0")}:${match[1].padStart(2, "0")}`;
}

/** "22:00" → "0 22 * * *"; null for anything that is not HH:MM. */
export function dailyCron(time: string): string | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(time.trim());
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return null;
  return `${minute} ${hour} * * *`;
}
