import { useEffect, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import { usePageHeader } from "@/contexts/usePageHeader";
import { useProfileScope } from "@/contexts/useProfileScope";
import { getManagementProfile } from "@/lib/api";
import type { TodayResponse } from "@/lib/api-today";
import { LoadErrorNotice } from "@/components/LoadErrorNotice";
import { fill, todayCopy, type TodayCopy } from "@/components/today/copy";
import { DashboardCards } from "@/components/today/DashboardCards";
import { DayHeader } from "@/components/today/DayHeader";
import { DevelopedPanel } from "@/components/today/DevelopedPanel";
import { EmptyDay, TodaySkeleton } from "@/components/today/EmptyDay";
import { NightlyDigest } from "@/components/today/NightlyDigest";
import { StatTiles } from "@/components/today/StatTiles";
import { SummaryCard, type SummaryState } from "@/components/today/SummaryCard";
import { TimelinePanel } from "@/components/today/TimelinePanel";
import { browserTimeZone, clock, isoDay, isValidDay, shiftDay } from "@/components/today/today-model";
import { useTodayData } from "@/components/today/useTodayData";

interface DayViewProps {
  copy: TodayCopy;
  data: TodayResponse;
  isToday: boolean;
  locale: string;
  nightly: ReactNode;
  onSummary: (regenerate: boolean) => void;
  summaryState: SummaryState;
}

function DayView({ copy, data, isToday, locale, nightly, onSummary, summaryState }: DayViewProps) {
  const ctx = { copy, locale, tz: data.tz };
  if (!data.has_activity) return <EmptyDay copy={copy} isToday={isToday} footer={nightly} />;
  return (
    <>
      <SummaryCard
        copy={copy}
        footer={nightly}
        locale={locale}
        onGenerate={onSummary}
        state={summaryState}
        summary={data.summary}
        tz={data.tz}
      />
      <StatTiles copy={copy} locale={locale} stats={data.stats} />
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.08fr)] lg:gap-5">
        <div className="flex min-w-0 flex-col gap-4 lg:gap-5">
          <DevelopedPanel {...ctx} data={data} />
          {data.dashboards.length > 0 && <DashboardCards {...ctx} dashboards={data.dashboards} />}
        </div>
        <TimelinePanel {...ctx} data={data} />
      </div>
    </>
  );
}

/** "Hoy": what the agent did and built on one day — summary, numbers, work and timeline. */
export default function TodayPage() {
  const { locale } = useI18n();
  const copy = todayCopy(locale);
  const { setTitle } = usePageHeader();
  const { profile } = useProfileScope();
  const [params, setParams] = useSearchParams();
  const tz = useMemo(() => browserTimeZone(), []);
  const todayIso = isoDay(new Date(), tz);
  const requested = params.get("date");
  const day = isValidDay(requested) && requested <= todayIso ? requested : todayIso;
  const isToday = day === todayIso;
  const { data, previous, fetchedAt, error, loading, reload, summaryState, writeSummary } = useTodayData(
    day,
    tz,
    profile,
    locale,
    isToday,
  );

  useEffect(() => setTitle(copy.pageTitle), [setTitle, copy.pageTitle]);

  const goTo = (next: string) =>
    setParams(next === todayIso ? {} : { date: next }, { replace: false });
  const shown = data ?? previous;
  const nightly = <NightlyDigest copy={copy} profile={getManagementProfile() || "default"} />;
  const updatedAt = data && fetchedAt ? fill(copy.updatedAt, { time: clock(fetchedAt, tz, locale) }) : "";

  return (
    <div className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-4 pb-8 sm:gap-5">
      <DayHeader
        copy={copy}
        day={day}
        locale={locale}
        loading={loading}
        onDay={goTo}
        onRefresh={reload}
        onShift={(delta) => goTo(shiftDay(day, delta))}
        todayIso={todayIso}
        updatedAt={updatedAt}
      />
      {error && !data && <LoadErrorNotice what={copy.loadWhat} detail={error} onRetry={reload} />}
      {!shown && !error && <TodaySkeleton />}
      {shown && (
        <div className={cn("flex min-w-0 flex-col gap-4 transition-opacity sm:gap-5", !data && "pointer-events-none opacity-50")}>
          <DayView
            copy={copy}
            data={shown}
            isToday={isToday}
            locale={locale}
            nightly={nightly}
            onSummary={writeSummary}
            summaryState={summaryState}
          />
        </div>
      )}
    </div>
  );
}
