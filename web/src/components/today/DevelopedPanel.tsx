import { useState } from "react";
import { Link } from "react-router";
import { Clock, Folder, FolderGit2, GitCommitHorizontal, Hammer, Package, SquareTerminal } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodayCommand, TodayCommit, TodayCronJob, TodayFileAction, TodayResponse, TodaySkill } from "@/lib/api-today";
import { fill, type TodayCopy } from "./copy";
import { PanelSection, TodayPanel } from "./Panel";
import { budgetGroups, clock, filesPageLink, groupFilesByProject, type FileGroup } from "./today-model";

interface Ctx {
  copy: TodayCopy;
  locale: string;
  tz: string;
}

const FILES_COLLAPSED = 8;

const ACTION_STYLE: Record<TodayFileAction, { dot: string; text: string }> = {
  created: { dot: "bg-emerald-400", text: "text-emerald-300" },
  edited: { dot: "bg-sky-400", text: "text-sky-300" },
  deleted: { dot: "bg-rose-400", text: "text-rose-300" },
};

function actionLabel(copy: TodayCopy, action: TodayFileAction): string {
  return { created: copy.fileCreated, edited: copy.fileEdited, deleted: copy.fileDeleted }[action];
}

function FileGroupBlock({ ctx, group, limit }: { ctx: Ctx; group: FileGroup; limit: number }) {
  const Icon = group.inRepo ? FolderGit2 : Folder;
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex min-w-0 items-center gap-2 px-1 py-1">
        <Icon className="h-4 w-4 shrink-0 text-amber-200/80" aria-hidden />
        <span className="shrink-0 text-sm font-medium text-text-primary">{group.name}</span>
        <span className="min-w-0 flex-1 truncate font-mono-ui text-xs text-text-tertiary" title={group.project}>
          {group.project}
        </span>
        <span className="shrink-0 rounded-full bg-white/[0.06] px-2 py-0.5 text-xs tabular-nums text-text-tertiary">{group.files.length}</span>
      </div>
      <ul className="flex flex-col gap-1">
        {group.files.slice(0, limit).map((file) => (
          <li key={file.path}>
            <Link
              to={filesPageLink(file.path)}
              title={`${file.path} — ${ctx.copy.openFolder}`}
              className="clawk-liquid-row flex min-h-[44px] min-w-0 items-center gap-3 rounded-xl px-3 py-2"
            >
              <span className={cn("inline-flex w-[4.5rem] shrink-0 items-center gap-1.5 text-xs", ACTION_STYLE[file.action].text)}>
                <span className={cn("h-1.5 w-1.5 rounded-full", ACTION_STYLE[file.action].dot)} aria-hidden />
                {actionLabel(ctx.copy, file.action)}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono-ui text-[0.8rem] text-text-primary">{file.rel}</span>
              <span className="shrink-0 text-xs tabular-nums text-text-tertiary">
                {file.count > 1 && <span className="mr-2">×{file.count}</span>}
                {clock(file.last_at, ctx.tz, ctx.locale)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FilesSection({ ctx, data }: { ctx: Ctx; data: TodayResponse }) {
  const [expanded, setExpanded] = useState(false);
  const shown = budgetGroups(groupFilesByProject(data.files), expanded ? Infinity : FILES_COLLAPSED);
  const hidden = data.files.length - shown.reduce((n, g) => n + g.limit, 0);
  return (
    <PanelSection title={ctx.copy.filesTitle} count={data.files.length}>
      <div className="flex flex-col gap-3">
        {shown.map(({ group, limit }) => (
          <FileGroupBlock key={group.project} ctx={ctx} group={group} limit={limit} />
        ))}
      </div>
      {(hidden > 0 || expanded) && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="min-h-[44px] self-start rounded-full px-3 text-sm text-midground hover:underline"
        >
          {expanded ? ctx.copy.showFewerFiles : fill(ctx.copy.showMoreFiles, { count: hidden })}
        </button>
      )}
    </PanelSection>
  );
}

function SkillsSection({ ctx, skills }: { ctx: Ctx; skills: TodaySkill[] }) {
  const label = { created: ctx.copy.skillCreated, updated: ctx.copy.skillUpdated, deleted: ctx.copy.skillDeleted };
  return (
    <PanelSection title={ctx.copy.skillsTitle} count={skills.length}>
      <div className="flex flex-wrap gap-2">
        {skills.map((s) => (
          <Link
            key={s.name}
            to="/skills"
            className="clawk-liquid-chip inline-flex min-h-[44px] items-center gap-2 rounded-full px-3.5 text-sm text-text-primary"
          >
            <Package className="h-3.5 w-3.5 text-pink-300" aria-hidden />
            <span className="font-medium">{s.name}</span>
            <span className={cn("text-xs", s.action === "created" ? "text-emerald-300" : "text-text-tertiary")}>{label[s.action]}</span>
          </Link>
        ))}
      </div>
    </PanelSection>
  );
}

function CommitsSection({ commits, ctx }: { commits: TodayCommit[]; ctx: Ctx }) {
  return (
    <PanelSection title={ctx.copy.commitsTitle} count={commits.length}>
      <ul className="flex flex-col gap-1">
        {[...commits].reverse().map((c) => (
          <li key={`${c.repo}:${c.sha}`} className="clawk-liquid-row flex min-h-[44px] min-w-0 items-center gap-3 rounded-xl px-3 py-2">
            <GitCommitHorizontal className="h-4 w-4 shrink-0 text-orange-300" aria-hidden />
            <span className="shrink-0 font-mono-ui text-xs text-text-tertiary">{c.sha.slice(0, 7)}</span>
            <span className="min-w-0 flex-1 truncate text-sm text-text-primary" title={c.subject}>{c.subject}</span>
            <span className="hidden shrink-0 rounded-full bg-white/[0.06] px-2 py-0.5 text-xs text-text-tertiary sm:inline">{c.repo_name}</span>
            <span className="shrink-0 text-xs tabular-nums text-text-tertiary">{clock(c.at, ctx.tz, ctx.locale)}</span>
          </li>
        ))}
      </ul>
    </PanelSection>
  );
}

function CronJobsSection({ ctx, jobs }: { ctx: Ctx; jobs: TodayCronJob[] }) {
  return (
    <PanelSection title={ctx.copy.cronJobsTitle} count={jobs.length}>
      <ul className="flex flex-col gap-1">
        {jobs.map((j) => (
          <li key={j.id}>
            <Link to="/cron" className="clawk-liquid-row flex min-h-[44px] min-w-0 items-center gap-3 rounded-xl px-3 py-2">
              <Clock className="h-4 w-4 shrink-0 text-orange-300" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-sm text-text-primary">{j.name}</span>
              <span className="shrink-0 font-mono-ui text-xs text-text-tertiary">{j.schedule}</span>
            </Link>
          </li>
        ))}
      </ul>
    </PanelSection>
  );
}

function CommandsSection({ commands, ctx, total }: { commands: TodayCommand[]; ctx: Ctx; total: number }) {
  const shown = commands.slice(-10).reverse();
  return (
    <details className="group min-w-0">
      <summary className="flex min-h-[44px] cursor-pointer list-none items-center gap-2 rounded-xl px-1 text-[0.7rem] font-medium uppercase tracking-[0.12em] text-text-tertiary hover:text-text-secondary">
        <SquareTerminal className="h-3.5 w-3.5" aria-hidden />
        {ctx.copy.commandsTitle}
        <span className="rounded-full bg-white/[0.06] px-2 py-0.5 tabular-nums">{total}</span>
        <span className="ml-auto text-base transition-transform group-open:rotate-90" aria-hidden>›</span>
      </summary>
      <ul className="mt-1 flex flex-col gap-1">
        {shown.map((c, i) => (
          <li key={`${c.at}:${i}`} className="flex min-w-0 items-baseline gap-3 rounded-xl bg-black/20 px-3 py-2">
            <span className="shrink-0 text-xs tabular-nums text-text-tertiary">{clock(c.at, ctx.tz, ctx.locale)}</span>
            <code className="min-w-0 flex-1 break-all font-mono-ui text-[0.78rem] text-text-secondary">{c.command}</code>
            {(c.failed || (c.exit_code !== null && c.exit_code !== 0)) && (
              <span className="shrink-0 rounded-full bg-rose-400/15 px-2 text-xs text-rose-300">exit {c.exit_code ?? "!"}</span>
            )}
          </li>
        ))}
      </ul>
      {total > shown.length && (
        <p className="mt-1 px-1 text-xs text-text-tertiary">{fill(ctx.copy.commandsMore, { shown: shown.length, total })}</p>
      )}
    </details>
  );
}

/** "Lo que desarrolló": files by project, skills, commits, new cron jobs and the commands it ran. */
export function DevelopedPanel({ data, ...ctx }: Ctx & { data: TodayResponse }) {
  const empty = !data.files.length && !data.skills.length && !data.commits.length && !data.cron_jobs_created.length;
  return (
    <TodayPanel icon={Hammer} title={ctx.copy.developedTitle}>
      {empty && <p className="text-sm text-text-tertiary">{ctx.copy.developedEmpty}</p>}
      {data.files.length > 0 && <FilesSection ctx={ctx} data={data} />}
      {data.skills.length > 0 && <SkillsSection ctx={ctx} skills={data.skills} />}
      {data.commits.length > 0 && <CommitsSection ctx={ctx} commits={data.commits} />}
      {data.cron_jobs_created.length > 0 && <CronJobsSection ctx={ctx} jobs={data.cron_jobs_created} />}
      {data.commands.length > 0 && <CommandsSection ctx={ctx} commands={data.commands} total={data.stats.commands} />}
    </TodayPanel>
  );
}
