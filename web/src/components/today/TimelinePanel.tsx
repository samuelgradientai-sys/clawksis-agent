import type { ComponentType, ReactNode } from "react";
import { Link } from "react-router";
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Gauge,
  GitCommitHorizontal,
  History,
  MessageSquare,
  Package,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { SOURCE_CONFIG, sourceLabel } from "@/pages/SessionsPage_sources";
import { skillDashboardPath } from "@/lib/api-skill-dashboards";
import type { TodayConversation, TodayCronRun, TodayResponse, TodaySkill } from "@/lib/api-today";
import { fill, type TodayCopy } from "./copy";
import { TodayPanel } from "./Panel";
import { buildTimeline, chatLink, clock, timeSpan, type TimelineItem } from "./today-model";

interface Ctx {
  copy: TodayCopy;
  locale: string;
  tz: string;
}

type Icon = ComponentType<{ className?: string }>;

function Row({ children, icon: RowIcon, tint, time }: { children: ReactNode; icon: Icon; tint: string; time: string }) {
  return (
    <li className="relative grid grid-cols-[2.75rem_1.75rem_minmax(0,1fr)] items-start gap-x-2 sm:grid-cols-[3.25rem_2rem_minmax(0,1fr)]">
      <span className="pt-1.5 text-right text-xs tabular-nums text-text-tertiary">{time}</span>
      <span className="relative z-[1] mt-0.5 flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-[color-mix(in_srgb,var(--background-base)_85%,transparent)] sm:h-8 sm:w-8">
        <RowIcon className={cn("h-3.5 w-3.5", tint)} aria-hidden />
      </span>
      <div className="min-w-0 pb-4">{children}</div>
    </li>
  );
}

function Chip({ children, tone }: { children: ReactNode; tone?: "bad" }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs tabular-nums",
        tone === "bad" ? "bg-rose-400/15 text-rose-300" : "bg-white/[0.06] text-text-tertiary",
      )}
    >
      {children}
    </span>
  );
}

function sourceMeta(source: string): { icon: Icon; color: string; label: string } {
  const config = SOURCE_CONFIG[source];
  return { icon: config?.icon ?? MessageSquare, color: config?.color ?? "text-midground", label: sourceLabel(source || "chat") };
}

function ConversationChips({ c, copy }: { c: TodayConversation; copy: TodayCopy }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      <Chip>{fill(copy.messagesCount, { count: c.messages })}</Chip>
      {c.tool_calls > 0 && <Chip>{fill(copy.toolsCount, { count: c.tool_calls })}</Chip>}
      {c.files > 0 && (
        <span className="inline-flex" title={c.file_names.join(", ")}>
          <Chip>{fill(copy.filesCount, { count: c.files })}</Chip>
        </span>
      )}
      {c.children > 0 && <Chip>{fill(copy.childrenCount, { count: c.children })}</Chip>}
      {c.errors > 0 && <Chip tone="bad">{fill(copy.errorsCount, { count: c.errors })}</Chip>}
    </div>
  );
}

function ConversationItem({ c, ctx }: { c: TodayConversation; ctx: Ctx }) {
  const meta = sourceMeta(c.source);
  return (
    <Row icon={meta.icon} tint={meta.color} time={clock(c.started_at, ctx.tz, ctx.locale)}>
      <Link
        to={chatLink(c.open_id)}
        className="clawk-liquid-row group block rounded-2xl px-3.5 py-3"
        title={ctx.copy.openConversation}
      >
        <div className="flex min-w-0 items-start gap-2">
          <span className="min-w-0 flex-1 text-[0.95rem] font-medium leading-snug text-text-primary group-hover:text-midground">
            {c.title || c.ask || ctx.copy.untitled}
          </span>
          <ArrowUpRight className="mt-0.5 h-4 w-4 shrink-0 text-text-tertiary opacity-60 group-hover:opacity-100" aria-hidden />
        </div>
        <p className="mt-0.5 text-xs text-text-tertiary">
          {meta.label} · {timeSpan(c.started_at, c.ended_at, ctx.tz, ctx.locale)}
        </p>
        {c.ask && c.ask !== c.title && (
          <p className="mt-1.5 line-clamp-2 text-sm text-text-secondary">
            <span className="text-text-tertiary">{ctx.copy.askLabel}: </span>
            {c.ask}
          </p>
        )}
        {c.outcome && <p className="mt-1 line-clamp-2 text-sm text-text-tertiary">↳ {c.outcome}</p>}
        {c.error_sample && <p className="mt-1 line-clamp-1 text-xs text-rose-300/90">⚠ {c.error_sample}</p>}
        <ConversationChips c={c} copy={ctx.copy} />
      </Link>
    </Row>
  );
}

const CRON_STATUS: Record<TodayCronRun["status"], { icon: Icon; tint: string; key: keyof TodayCopy }> = {
  ok: { icon: CheckCircle2, tint: "text-emerald-300", key: "cronOk" },
  failed: { icon: XCircle, tint: "text-rose-300", key: "cronFailed" },
  unknown: { icon: Clock, tint: "text-text-tertiary", key: "cronUnknown" },
  running: { icon: Clock, tint: "text-sky-300", key: "cronRunning" },
};

function CronItem({ ctx, run }: { ctx: Ctx; run: TodayCronRun }) {
  const status = CRON_STATUS[run.status];
  const body = (
    <>
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="min-w-0 truncate text-sm font-medium text-text-primary">{fill(ctx.copy.cronRun, { name: run.job_name })}</span>
        <span className={cn("inline-flex items-center gap-1 text-xs", status.tint)}>
          <status.icon className="h-3.5 w-3.5" aria-hidden />
          {ctx.copy[status.key]}
        </span>
      </div>
      {run.error && <p className="mt-1 line-clamp-2 break-words text-xs text-rose-300/90">{run.error}</p>}
    </>
  );
  return (
    <Row icon={Clock} tint="text-orange-300" time={clock(run.at, ctx.tz, ctx.locale)}>
      {run.session_id ? (
        <Link to={chatLink(run.session_id)} className="clawk-liquid-row block rounded-2xl px-3.5 py-2.5">
          {body}
        </Link>
      ) : (
        <div className="rounded-2xl px-3.5 py-2.5">{body}</div>
      )}
    </Row>
  );
}

const SKILL_ACTION_KEY: Record<TodaySkill["action"], keyof TodayCopy> = {
  created: "skillCreated",
  updated: "skillUpdated",
  deleted: "skillDeleted",
};

function Note({ children }: { children: ReactNode }) {
  return <p className="min-w-0 break-words px-3.5 pt-1.5 text-sm text-text-secondary">{children}</p>;
}

function NotableItem({ ctx, item }: { ctx: Ctx; item: Exclude<TimelineItem, { kind: "conversation" | "cron" }> }) {
  const time = clock(item.at, ctx.tz, ctx.locale);
  const { copy } = ctx;
  switch (item.kind) {
    case "commit":
      return (
        <Row icon={GitCommitHorizontal} tint="text-orange-300" time={time}>
          <Note>
            <span className="text-text-tertiary">{fill(copy.commitIn, { repo: item.commit.repo_name })}: </span>
            {item.commit.subject}
          </Note>
        </Row>
      );
    case "skill":
      return (
        <Row icon={Package} tint="text-pink-300" time={time}>
          <Note>
            {fill(copy.skillEvent, { name: item.skill.name })} · {copy[SKILL_ACTION_KEY[item.skill.action]]}
          </Note>
        </Row>
      );
    case "cronJob":
      return (
        <Row icon={Clock} tint="text-orange-300" time={time}>
          <Note>{fill(copy.cronJobEvent, { name: item.job.name })}</Note>
        </Row>
      );
    case "dashboard":
      return (
        <Row icon={Gauge} tint="text-violet-300" time={time}>
          <Link
            to={skillDashboardPath(item.dashboard.name)}
            className="clawk-liquid-row -mt-1.5 flex min-h-[44px] items-center gap-2 rounded-2xl px-3.5 text-sm text-text-secondary hover:text-midground"
          >
            <span className="min-w-0 flex-1 truncate">{fill(copy.dashboardEvent, { name: item.dashboard.title })}</span>
            <ArrowUpRight className="h-4 w-4 shrink-0 text-text-tertiary" aria-hidden />
          </Link>
        </Row>
      );
  }
}

function TimelineEntry({ ctx, item }: { ctx: Ctx; item: TimelineItem }) {
  if (item.kind === "conversation") return <ConversationItem c={item.conversation} ctx={ctx} />;
  if (item.kind === "cron") return <CronItem ctx={ctx} run={item.run} />;
  return <NotableItem ctx={ctx} item={item} />;
}

/** "Línea de tiempo": every conversation, cron run and notable action of the day, oldest first. */
export function TimelinePanel({ data, ...ctx }: Ctx & { data: TodayResponse }) {
  const items = buildTimeline(data);
  const errors = data.stats.errors;
  return (
    <TodayPanel
      icon={History}
      title={ctx.copy.timelineTitle}
      aside={
        errors > 0 ? (
          <span className="inline-flex items-center gap-1 text-xs text-rose-300">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
            {fill(ctx.copy.errorsCount, { count: errors })}
          </span>
        ) : null
      }
    >
      {items.length === 0 ? (
        <p className="text-sm text-text-tertiary">{ctx.copy.timelineEmpty}</p>
      ) : (
        <ol className="relative before:absolute before:bottom-4 before:left-[4.125rem] before:top-3 before:w-px before:bg-white/10 sm:before:left-[4.75rem]">
          {items.map((item) => (
            <TimelineEntry key={item.key} ctx={ctx} item={item} />
          ))}
        </ol>
      )}
    </TodayPanel>
  );
}
