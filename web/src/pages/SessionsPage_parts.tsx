import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  ListFilter,
  Terminal,
  X,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Checkbox } from "@nous-research/ui/ui/components/checkbox";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import type { SessionInfo, SessionStoreStats } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { useSystemActions } from "@/contexts/useSystemActions";
import { useI18n } from "@/i18n";
import { SOURCE_CONFIG, sourceLabel } from "./SessionsPage_sources";
import { sessionsLabels } from "./SessionsPage_labels";

export const PAGE_SIZE = 20;

export function SessionsPagination({
  className,
  compact = false,
  onPageChange,
  page,
  total,
}: {
  className?: string;
  compact?: boolean;
  onPageChange: (page: number) => void;
  page: number;
  total: number;
}) {
  const { t } = useI18n();
  const pageCount = Math.ceil(total / PAGE_SIZE);
  return (
    <div className={`flex items-center ${compact ? "gap-1" : "justify-between pt-2"}${className ? ` ${className}` : ""}`}>
      {!compact && (
        <span className="text-xs text-muted-foreground">
          {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} {t.common.of} {total}
        </span>
      )}
      <div className="flex items-center gap-1">
        <Button outlined size="icon" disabled={page === 0} onClick={() => onPageChange(page - 1)} aria-label={t.sessions.previousPage}>
          <ChevronLeft />
        </Button>
        <span className="px-2 text-xs text-muted-foreground">
          {t.common.page} {page + 1} {t.common.of} {pageCount}
        </span>
        <Button
          outlined
          size="icon"
          disabled={(page + 1) * PAGE_SIZE >= total}
          onClick={() => onPageChange(page + 1)}
          aria-label={t.sessions.nextPage}
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

function Stat({ value, label, tone }: { value: number; label: string; tone?: string }) {
  return (
    <div className="flex flex-col">
      <span className={`text-lg font-semibold tabular-nums leading-none ${tone ?? ""}`}>{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

/** Store totals. "Not archived" is what the default list shows; the archived count opens the
 *  archived view (archived rows are otherwise unreachable from this page). */
export function SessionStatsStrip({
  stats,
  archivedView,
  onToggleArchived,
}: {
  stats: SessionStoreStats;
  archivedView: boolean;
  onToggleArchived: () => void;
}) {
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const sourceCount = Object.keys(stats.by_source).length;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 border border-border bg-background-base/40 px-4 py-3">
      <Stat value={stats.total} label="Total" />
      <Stat value={stats.active_store} label={L.notArchived} tone="text-success" />
      <button
        type="button"
        onClick={onToggleArchived}
        aria-pressed={archivedView}
        className={`text-left transition-colors hover:text-foreground ${archivedView ? "underline underline-offset-4" : ""}`}
        title={L.showArchived}
      >
        <Stat value={stats.archived} label={L.showArchived} />
      </button>
      <Stat value={stats.messages} label="Messages" />
      {sourceCount > 0 && <Stat value={sourceCount} label="Sources" />}
    </div>
  );
}

/** Overview card: the newest sessions INCLUDING live ones; clicking one opens it in the history. */
export function RecentSessionsCard({
  sessions,
  onOpen,
}: {
  sessions: SessionInfo[];
  onOpen: (session: SessionInfo) => void;
}) {
  const { t } = useI18n();
  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="min-w-0">
        <div className="flex min-w-0 items-center gap-2">
          <Clock className="h-5 w-5 shrink-0 text-muted-foreground" />
          <CardTitle className="min-w-0 truncate text-base">{t.status.recentSessions}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="grid min-w-0 gap-3">
        {sessions.map((s) => (
          <button
            type="button"
            key={s.id}
            onClick={() => onOpen(s)}
            className="flex min-w-0 max-w-full flex-col gap-2 border border-border p-3 text-left transition-colors hover:bg-secondary/30 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <span className={`font-mondwest normal-case min-w-0 truncate text-sm ${s.title ? "font-medium" : "text-muted-foreground italic"}`}>
                {s.title ?? (s.preview ? s.preview.slice(0, 60) : t.common.untitled)}
              </span>
              <span className="min-w-0 break-words text-xs text-muted-foreground">
                {s.model && <span className="font-mono-ui">{s.model.split("/").pop()} · </span>}
                {s.message_count} {t.common.msgs} · {timeAgo(s.last_active)}
              </span>
              {s.preview && s.title && (
                <p className="font-mondwest normal-case min-w-0 max-w-full text-xs leading-snug text-text-tertiary [overflow-wrap:anywhere]">
                  {s.preview}
                </p>
              )}
            </div>
            <span className="flex shrink-0 items-center gap-2 self-start sm:self-center">
              {s.is_active && (
                <Badge tone="success" className="text-xs">
                  <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                  {t.common.live}
                </Badge>
              )}
              <Badge tone="outline" className="text-xs">
                <Database className="mr-1 h-3 w-3" />
                {s.source ? sourceLabel(s.source) : "local"}
              </Badge>
            </span>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

/** The per-source checkbox dropdown (sources come from the store's stats). */
export function SourceFilterMenu({
  label,
  title,
  options,
  selected,
  canClear,
  onToggle,
  onClear,
}: {
  label: string;
  title: string;
  options: Array<[string, number]>;
  selected: Set<string>;
  canClear: boolean;
  onToggle: (source: string) => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <Button
        outlined
        size="sm"
        prefix={<ListFilter />}
        suffix={<ChevronDown className={`transition-transform ${open ? "rotate-180" : ""}`} />}
        className="h-8 min-w-[10rem] max-w-[14rem] justify-between text-xs"
        aria-label={t.sessions.sourceFilter}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="min-w-0 truncate">{label}</span>
      </Button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-[18rem] max-w-[calc(100vw-2rem)] border border-border bg-background-base shadow-lg">
          <div className="flex items-center justify-between gap-2 border-b border-border px-2 py-1.5">
            <span className="min-w-0 truncate text-xs text-muted-foreground">{title}</span>
            {canClear && (
              <Button ghost size="xs" onClick={onClear} className="shrink-0">
                {t.common.clear}
              </Button>
            )}
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {options.length === 0 && <div className="px-2 py-2 text-xs text-muted-foreground">{title}</div>}
            {options.map(([source, count]) => {
              const Icon = SOURCE_CONFIG[source]?.icon ?? Terminal;
              const color = SOURCE_CONFIG[source]?.color ?? "text-muted-foreground";
              return (
                <div key={source} className="flex min-w-0 items-center gap-2 px-2 py-1.5 hover:bg-secondary/40">
                  <Checkbox
                    checked={selected.has(source)}
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggle(source);
                    }}
                    aria-label={`${t.sessions.sourceFilter}: ${sourceLabel(source)}`}
                  />
                  <button type="button" className="flex min-w-0 flex-1 items-center gap-2 text-left text-xs" onClick={() => onToggle(source)}>
                    <Icon className={`h-3.5 w-3.5 shrink-0 ${color}`} />
                    <span className="min-w-0 flex-1 truncate">{sourceLabel(source)}</span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">{count}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

/** Output of a running restart/update action (System actions), shown above the list. */
export function SystemActionLog() {
  const { t } = useI18n();
  const { activeAction, actionStatus, dismissLog } = useSystemActions();
  const logRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [actionStatus?.lines]);

  if (!activeAction) return null;
  const failed = actionStatus !== null && actionStatus?.exit_code !== 0 && !actionStatus?.running;
  const tone = actionStatus?.running ? "warning" : actionStatus?.exit_code === 0 ? "success" : actionStatus ? "destructive" : "outline";
  const statusText = actionStatus?.running
    ? t.status.running
    : actionStatus?.exit_code === 0
      ? t.status.actionFinished
      : actionStatus
        ? `${t.status.actionFailed} (${actionStatus.exit_code ?? "?"})`
        : t.common.loading;
  return (
    <div className="border border-border bg-background-base/50">
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 min-w-0">
          {actionStatus?.running || actionStatus === null ? (
            <Spinner className={`shrink-0 text-[0.875rem] ${actionStatus ? "text-warning" : "text-muted-foreground"}`} />
          ) : failed ? (
            <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-success" />
          )}
          <span className="text-xs font-mondwest tracking-[0.12em] truncate">
            {activeAction === "restart" ? t.status.restartGateway : t.status.updateClawksis}
          </span>
          <Badge tone={tone} className="text-xs shrink-0">
            {statusText}
          </Badge>
        </div>
        <Button ghost size="icon" onClick={dismissLog} className="shrink-0 text-text-secondary hover:text-foreground" aria-label={t.common.close}>
          <X />
        </Button>
      </div>
      <pre ref={logRef} className="max-h-72 overflow-auto px-3 py-2 font-mono-ui text-xs leading-relaxed whitespace-pre-wrap break-all">
        {actionStatus?.lines && actionStatus.lines.length > 0 ? actionStatus.lines.join("\n") : t.status.waitingForOutput}
      </pre>
    </div>
  );
}
