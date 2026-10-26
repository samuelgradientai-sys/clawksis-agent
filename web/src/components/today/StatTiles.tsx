import type { ComponentType } from "react";
import {
  Clock,
  Coins,
  FileCode2,
  MessageSquare,
  MessagesSquare,
  Package,
  SquareTerminal,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodayStats } from "@/lib/api-today";
import { fill, type TodayCopy } from "./copy";
import { compactNumber, usd } from "./today-model";

interface Tile {
  key: string;
  icon: ComponentType<{ className?: string }>;
  tint: string;
  label: string;
  value: string;
  hint: string;
  title?: string;
  alert?: boolean;
}

function tiles(s: TodayStats, copy: TodayCopy, locale: string): Tile[] {
  const n = (v: number) => compactNumber(v, locale);
  // A breakdown under a zero says nothing ("0 nuevos · 0 editados"): only non-zero tiles get one.
  const hint = (total: number, template: string, values: Record<string, string | number>) =>
    total ? fill(template, values) : "";
  const tokens = s.input_tokens + s.output_tokens;
  const files = s.files_created + s.files_edited + s.files_deleted;
  const cron = s.cron_ok + s.cron_failed + s.cron_other;
  const skills = s.skills_created + s.skills_updated;
  return [
    { key: "conversations", icon: MessageSquare, tint: "text-violet-300", label: copy.statConversations, value: n(s.conversations), hint: "" },
    { key: "messages", icon: MessagesSquare, tint: "text-sky-300", label: copy.statMessages, value: n(s.messages), hint: hint(s.messages, copy.statMessagesHint, { count: n(s.user_messages) }) },
    { key: "tools", icon: Wrench, tint: "text-amber-300", label: copy.statTools, value: n(s.tool_calls), hint: hint(s.errors, copy.statToolsHint, { count: n(s.errors) }), alert: s.errors > 0 },
    { key: "files", icon: FileCode2, tint: "text-emerald-300", label: copy.statFiles, value: n(files), hint: hint(files, copy.statFilesHint, { created: n(s.files_created), edited: n(s.files_edited) }) },
    { key: "commands", icon: SquareTerminal, tint: "text-fuchsia-300", label: copy.statCommands, value: n(s.commands), hint: "" },
    { key: "cron", icon: Clock, tint: "text-orange-300", label: copy.statCron, value: n(cron), hint: hint(cron, copy.statCronHint, { ok: n(s.cron_ok), failed: n(s.cron_failed) }), alert: s.cron_failed > 0 },
    { key: "skills", icon: Package, tint: "text-pink-300", label: copy.statSkills, value: n(skills), hint: hint(skills, copy.statSkillsHint, { created: n(s.skills_created), updated: n(s.skills_updated) }) },
    { key: "tokens", icon: Coins, tint: "text-yellow-200", label: copy.statTokens, value: tokens ? n(tokens) : "—", hint: hint(tokens, copy.statTokensHint, { cost: usd(s.actual_cost_usd || s.estimated_cost_usd, locale), calls: n(s.api_calls) }), title: copy.statTokensNote },
  ];
}

/** The day in eight numbers: two rows of four on desktop, four rows of two on a phone. */
export function StatTiles({ copy, locale, stats }: { copy: TodayCopy; locale: string; stats: TodayStats }) {
  return (
    <section aria-label={copy.statsTitle} className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 sm:gap-3">
      {tiles(stats, copy, locale).map((tile) => (
        <div
          key={tile.key}
          title={tile.title}
          className="clawk-liquid-stat flex min-w-0 flex-col gap-1 rounded-2xl bg-[color-mix(in_srgb,var(--background-base)_60%,transparent)] px-3.5 py-3"
        >
          <span className="flex items-center gap-1.5 text-[0.7rem] uppercase tracking-[0.1em] text-text-tertiary">
            <tile.icon className={cn("h-3.5 w-3.5 shrink-0", tile.tint)} aria-hidden />
            <span className="truncate">{tile.label}</span>
          </span>
          <span className="text-2xl font-semibold tabular-nums text-text-primary">{tile.value}</span>
          <span className={cn("min-h-[1rem] truncate text-xs", tile.alert ? "text-rose-300" : "text-text-tertiary")}>{tile.hint}</span>
        </div>
      ))}
    </section>
  );
}
