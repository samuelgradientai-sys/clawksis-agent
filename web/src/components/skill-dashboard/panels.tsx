import type { ReactNode } from "react";
import { AlertTriangle, Minus, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  DashboardPanel,
  DashboardTone,
  ListPanel as ListPanelData,
  StatsPanel as StatsPanelData,
  TablePanel as TablePanelData,
} from "@/lib/api-skill-dashboards";
import type { SkillDashboardsCopy } from "@/i18n/types";
import { ChartPanel } from "./ChartPanel";
import { fill } from "./copy";
import { formatCell, formatStat, TONE_DOT, TONE_TEXT } from "./format";

// Tone is never carried by color alone: an icon rides along.
const TONE_ICON: Record<DashboardTone, typeof TrendingUp> = {
  positive: TrendingUp,
  negative: TrendingDown,
  warning: AlertTriangle,
  neutral: Minus,
};

function PanelShell({ children, panel }: { children: ReactNode; panel: DashboardPanel }) {
  return (
    <section
      className={cn(
        "clawk-liquid-panel flex min-w-0 flex-col gap-3 rounded-3xl p-4 sm:p-5",
        panel.width === "half" ? "lg:col-span-1" : "lg:col-span-2",
      )}
      aria-label={panel.title || undefined}
    >
      {(panel.title || panel.description) && (
        <header className="flex flex-col gap-0.5">
          {panel.title && <h2 className="text-sm font-semibold tracking-wide text-text-primary">{panel.title}</h2>}
          {panel.description && <p className="text-xs text-text-tertiary">{panel.description}</p>}
        </header>
      )}
      {children}
    </section>
  );
}

function StatsPanel({ locale, panel }: { locale: string; panel: StatsPanelData }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
      {panel.items.map((item, i) => {
        const Icon = TONE_ICON[item.tone];
        return (
          <div key={i} className="clawk-liquid-stat flex min-w-0 flex-col gap-1 rounded-2xl px-3.5 py-3">
            <span className="line-clamp-2 text-[0.7rem] uppercase tracking-[0.1em] text-text-tertiary">{item.label}</span>
            <span className="flex items-center gap-1.5 text-xl font-semibold text-text-primary">
              {item.tone !== "neutral" && <Icon className={cn("h-4 w-4 shrink-0", TONE_TEXT[item.tone])} aria-hidden />}
              <span className="truncate">{formatStat(item.value, locale)}</span>
            </span>
            {item.hint && <span className="line-clamp-2 text-xs text-text-tertiary" title={item.hint}>{item.hint}</span>}
          </div>
        );
      })}
    </div>
  );
}

function TablePanel({ copy, locale, panel }: { copy: SkillDashboardsCopy; locale: string; panel: TablePanelData }) {
  if (!panel.rows.length) return <p className="text-sm text-text-tertiary">{panel.empty || copy.emptyPanel}</p>;
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[22rem] border-separate border-spacing-y-1 text-sm">
        <thead>
          <tr className="text-[0.7rem] uppercase tracking-[0.08em] text-text-tertiary">
            {panel.columns.map((c) => (
              <th key={c.key} className={cn("px-3 pb-1 font-medium", c.align === "right" ? "text-right" : "text-left")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {panel.rows.map((row, ri) => (
            <tr key={ri} className="clawk-liquid-row">
              {panel.columns.map((c, ci) => (
                <td
                  key={c.key}
                  className={cn(
                    "px-3 py-2 first:rounded-l-xl last:rounded-r-xl",
                    c.align === "right" ? "text-right font-mono-ui" : "text-left",
                    c.format === "money" || c.format === "number" || c.format === "percent" ? "tabular-nums" : "",
                  )}
                >
                  {ci === 0 && row._tone !== "neutral" ? (
                    <span className="inline-flex items-center gap-2">
                      <span className={cn("h-2 w-2 shrink-0 rounded-full", TONE_DOT[row._tone])} aria-hidden />
                      {formatCell(row[c.key] ?? null, c.format, locale)}
                    </span>
                  ) : (
                    formatCell(row[c.key] ?? null, c.format, locale)
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ListPanel({ copy, panel }: { copy: SkillDashboardsCopy; panel: ListPanelData }) {
  if (!panel.items.length) return <p className="text-sm text-text-tertiary">{panel.empty || copy.emptyPanel}</p>;
  return (
    <ul className="flex flex-col gap-2">
      {panel.items.map((item, i) => {
        const Icon = TONE_ICON[item.tone];
        return (
          <li key={i} className="clawk-liquid-row flex gap-3 rounded-2xl px-3.5 py-3">
            <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", TONE_TEXT[item.tone])} aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <span className="text-sm font-medium text-text-primary">{item.title}</span>
                {item.meta && <span className="text-xs text-text-tertiary">{item.meta}</span>}
              </div>
              {item.body && <p className="mt-0.5 whitespace-pre-line text-sm text-text-secondary">{item.body}</p>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

type PanelBody<K extends DashboardPanel["type"]> = (props: {
  copy: SkillDashboardsCopy;
  locale: string;
  panel: Extract<DashboardPanel, { type: K }>;
}) => ReactNode;

const PANEL_BODIES: { [K in DashboardPanel["type"]]: PanelBody<K> } = {
  stats: ({ locale, panel }) => <StatsPanel locale={locale} panel={panel} />,
  table: ({ copy, locale, panel }) => <TablePanel copy={copy} locale={locale} panel={panel} />,
  list: ({ copy, panel }) => <ListPanel copy={copy} panel={panel} />,
  chart: ({ copy, locale, panel }) => <ChartPanel copy={copy} locale={locale} panel={panel} />,
  text: ({ panel }) => <p className="whitespace-pre-line text-sm text-text-secondary">{panel.body}</p>,
  unsupported: ({ copy, panel }) => (
    <p className="text-sm text-text-tertiary">{fill(copy.unsupported, { type: panel.original_type })}</p>
  ),
};

export function DashboardPanelView({ copy, locale, panel }: { copy: SkillDashboardsCopy; locale: string; panel: DashboardPanel }) {
  const render = PANEL_BODIES[panel.type] as PanelBody<DashboardPanel["type"]>;
  return <PanelShell panel={panel}>{render({ copy, locale, panel: panel as never })}</PanelShell>;
}
