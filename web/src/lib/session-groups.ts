/** Date buckets for the Sessions history list: pins first, then by the day of last activity. */
export type SessionGroupKey = "pinned" | "today" | "yesterday" | "week" | "month" | "older";

export interface SessionGroup<T> {
  key: SessionGroupKey;
  sessions: T[];
}

interface GroupableSession {
  pinned?: boolean;
  last_active?: number | null;
  started_at: number;
}

const DAY_MS = 86_400_000;
const ORDER: SessionGroupKey[] = ["pinned", "today", "yesterday", "week", "month", "older"];

/**
 * Bucket *sessions* (epoch-second timestamps) by local calendar day of their last activity:
 * today, yesterday, the 5 days before that ("week"), the rest of the last 30 days ("month") and
 * older. Pinned rows get their own group on top. Input order is kept inside each group (the list
 * arrives sorted by recent activity), and empty groups are dropped.
 */
export function groupSessionsByDate<T extends GroupableSession>(
  sessions: T[],
  now: Date = new Date(),
): SessionGroup<T>[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const bounds: Array<[SessionGroupKey, number]> = [
    ["today", startOfToday],
    ["yesterday", startOfToday - DAY_MS],
    ["week", startOfToday - 6 * DAY_MS],
    ["month", startOfToday - 29 * DAY_MS],
  ];
  const buckets = new Map<SessionGroupKey, T[]>(ORDER.map((key) => [key, []]));
  for (const session of sessions) {
    const ts = (session.last_active || session.started_at) * 1000;
    const key = session.pinned ? "pinned" : (bounds.find(([, start]) => ts >= start)?.[0] ?? "older");
    buckets.get(key)!.push(session);
  }
  return ORDER.filter((key) => buckets.get(key)!.length > 0).map((key) => ({
    key,
    sessions: buckets.get(key)!,
  }));
}
