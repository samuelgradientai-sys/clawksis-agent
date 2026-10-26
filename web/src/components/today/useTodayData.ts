import { useCallback, useEffect, useRef, useState } from "react";
import { todayApi, type TodayResponse } from "@/lib/api-today";
import { errorMessage } from "@/lib/api-error";
import type { SummaryState } from "./SummaryCard";

const TODAY_REFRESH_MS = 60_000;

interface Loaded {
  scope: string;
  data: TodayResponse;
  fetchedAt: number;
}

interface TodayData {
  /** The requested day/profile, once loaded. */
  data: TodayResponse | null;
  /** Whatever was last on screen (another day or profile) while the new one loads. */
  previous: TodayResponse | null;
  /** When the shown data was fetched (epoch seconds), 0 before the first load. */
  fetchedAt: number;
  error: string | null;
  loading: boolean;
  reload: () => void;
  summaryState: SummaryState;
  writeSummary: (regenerate: boolean) => void;
}

/** One day's activity for the managed profile: refetched on day/profile change and every minute
 *  while today is on screen; the summary is written the first time a day with activity is opened
 *  (the backend caches it, so later visits just read it). */
export function useTodayData(day: string, tz: string, profile: string, lang: string, live: boolean): TodayData {
  const scope = `${profile}|${day}|${tz}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<{ scope: string; state: SummaryState } | null>(null);
  const request = useRef(0);
  const attempted = useRef(new Set<string>());

  const load = useCallback(async () => {
    const mine = ++request.current;
    setLoading(true);
    try {
      const next = await todayApi.get(day, tz);
      if (request.current !== mine) return;
      setLoaded({ scope, data: next, fetchedAt: Date.now() / 1000 });
      setError(null);
    } catch (err) {
      if (request.current === mine) setError(errorMessage(err));
    } finally {
      if (request.current === mine) setLoading(false);
    }
  }, [day, scope, tz]);

  const writeSummary = useCallback(
    async (regenerate: boolean) => {
      attempted.current.add(scope);
      setSummary({ scope, state: { writing: true, error: null } });
      try {
        const res = await todayApi.summary({ date: day, tz, lang, regenerate });
        setLoaded((prev) => (prev?.scope === scope ? { ...prev, data: { ...prev.data, summary: res.summary } } : prev));
        setSummary({ scope, state: { writing: false, error: res.error } });
      } catch (err) {
        setSummary({ scope, state: { writing: false, error: errorMessage(err) } });
      }
    },
    [day, lang, scope, tz],
  );

  useEffect(() => {
    // Dashboard data surfaces fetch from an effect on mount + scope change (same as FilesPage).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  useEffect(() => {
    if (!live) return;
    const tick = () => {
      if (!document.hidden) void load();
    };
    const id = window.setInterval(tick, TODAY_REFRESH_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [live, load]);

  const current = loaded?.scope === scope ? loaded.data : null;
  useEffect(() => {
    if (!current || current.summary || !current.has_activity || attempted.current.has(scope)) return;
    void writeSummary(false);
  }, [current, scope, writeSummary]);

  return {
    data: current,
    previous: loaded?.data ?? null,
    fetchedAt: loaded?.fetchedAt ?? 0,
    error,
    loading,
    reload: () => void load(),
    summaryState: summary?.scope === scope ? summary.state : { writing: false, error: null },
    writeSummary: (regenerate) => void writeSummary(regenerate),
  };
}
