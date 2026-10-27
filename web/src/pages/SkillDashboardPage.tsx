import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, Gauge, RefreshCw, Settings2 } from "lucide-react";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import { usePageHeader } from "@/contexts/usePageHeader";
import { skillDashboardsApi, type SkillDashboardDetail } from "@/lib/api-skill-dashboards";
import { dashboardCopy, fill } from "@/components/skill-dashboard/copy";
import { relativeTime } from "@/components/skill-dashboard/format";
import { DashboardPanelView } from "@/components/skill-dashboard/panels";
import { SkillSettingsCard } from "@/components/skill-dashboard/SkillSettingsCard";
import { LoadErrorNotice } from "@/components/LoadErrorNotice";
import { errorMessage } from "@/lib/api-error";

const REFRESH_MS = 30_000;

/** One skill's mini dashboard: the snapshot the skill wrote, refreshed every
 *  30 s while the tab is visible. */
export default function SkillDashboardPage() {
  const { name = "" } = useParams();
  const { t, locale } = useI18n();
  const copy = dashboardCopy(t);
  const { setTitle } = usePageHeader();
  const [loaded, setDetail] = useState<SkillDashboardDetail | null>(null);
  // Switching dashboards keeps the old data until the new one arrives; never show it.
  const detail = loaded?.name === name ? loaded : null;
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (document.hidden) return;
    try {
      setDetail(await skillDashboardsApi.get(name));
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [name]);
  const refresh = () => {
    setLoading(true);
    void load().finally(() => setLoading(false));
  };

  useEffect(() => {
    const tick = () => void load();
    tick();
    const id = window.setInterval(tick, REFRESH_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [load]);

  const title = detail?.snapshot?.title || detail?.title || name;
  useEffect(() => setTitle(title), [setTitle, title]);

  if (error && !detail) return <LoadErrorNotice detail={errorMessage(error)} onRetry={refresh} what={title} />;

  const snapshot = detail?.snapshot ?? null;
  const updated = relativeTime(snapshot?.updated_at || detail?.modified_at || "", locale);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-1 sm:px-0">
      <div className="clawk-liquid-glass flex flex-wrap items-center gap-4 rounded-3xl border border-white/10 px-5 py-4">
        <div className="clawk-liquid-chip flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-xl">
          {detail?.emoji || <Gauge className="h-5 w-5 text-midground" />}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-semibold text-text-primary">{title}</h1>
          <p className="text-sm text-text-tertiary sm:truncate">
            {snapshot?.subtitle || detail?.description}
            {updated && <span className="ml-2 opacity-80">· {fill(copy.updated, { when: updated })}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-text-tertiary sm:inline">{copy.autoRefresh}</span>
          <button
            type="button"
            onClick={() => document.getElementById("skill-settings")?.scrollIntoView({ behavior: "smooth" })}
            aria-label={copy.settingsTitle}
            title={copy.settingsTitle}
            className="clawk-liquid-chip rounded-full p-2 text-text-secondary transition-colors hover:text-midground"
          >
            <Settings2 className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={refresh}
            aria-label={t.common.refresh}
            className="clawk-liquid-chip rounded-full p-2 text-text-secondary transition-colors hover:text-midground"
          >
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
          </button>
        </div>
      </div>

      {detail && !detail.enabled && (
        <p className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-2 text-sm text-amber-200">{copy.disabled}</p>
      )}
      {detail?.error && (
        <p className="rounded-2xl border border-rose-400/30 bg-rose-400/10 px-4 py-2 text-sm text-rose-200">
          {fill(copy.error, { error: detail.error })}
        </p>
      )}
      {detail && !snapshot && !detail.error && (
        <div className="clawk-liquid-panel rounded-3xl px-6 py-10 text-center">
          <p className="text-base text-text-primary">{copy.noSnapshot}</p>
          <p className="mt-2 text-sm text-text-tertiary">{fill(copy.noSnapshotHint, { file: detail.snapshot_file })}</p>
        </div>
      )}
      {snapshot && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {snapshot.panels.map((panel) => (
            <DashboardPanelView key={panel.id} copy={copy} locale={locale} panel={panel} />
          ))}
        </div>
      )}

      <div id="skill-settings" className="scroll-mt-4">
        <SkillSettingsCard key={name} copy={copy} locale={locale} name={name} onSaved={refresh} />
      </div>

      <Link to="/skills/dashboards" className="inline-flex items-center gap-1.5 self-start text-sm text-text-tertiary hover:text-midground">
        <ArrowLeft className="h-4 w-4" /> {copy.back}
      </Link>
    </div>
  );
}
