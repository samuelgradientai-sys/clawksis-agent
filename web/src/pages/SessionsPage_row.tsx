import { useEffect, useState, type MouseEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import {
  Archive,
  ArchiveRestore,
  Check,
  Download,
  Globe,
  Pencil,
  Pin,
  PinOff,
  Play,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { Checkbox } from "@nous-research/ui/ui/components/checkbox";
import { Input } from "@nous-research/ui/ui/components/input";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api } from "@/lib/api";
import type { SessionInfo, SessionMessagesResponse } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { timeAgo } from "@/lib/utils";
import { useI18n } from "@/i18n";
import { SOURCE_CONFIG, sourceLabel } from "./SessionsPage_sources";
import { MessageList, SnippetHighlight } from "./SessionsPage_messages";
import { sessionsLabels } from "./SessionsPage_labels";

export interface SessionFlags {
  archived?: boolean;
  pinned?: boolean;
}

export interface SessionRowProps {
  isExpanded: boolean;
  isSelected: boolean;
  onDelete: () => void;
  onExport: (id: string) => void;
  onRename: (id: string, title: string, profile?: string) => Promise<void>;
  onSetFlags: (session: SessionInfo, flags: SessionFlags) => Promise<void>;
  onSelectClick: (event: MouseEvent) => void;
  onToggle: () => void;
  resumeInChatEnabled: boolean;
  searchQuery?: string;
  session: SessionInfo;
  snippet?: string;
}

const DATE_TIME = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function sourceVisual(source: string | null) {
  const key = source?.split(":")[0];
  return (source ? (SOURCE_CONFIG[source] ?? (key ? SOURCE_CONFIG[key] : null)) : null) ?? {
    icon: Globe,
    color: "text-muted-foreground",
  };
}

function hasRealTitle(session: SessionInfo): boolean {
  return Boolean(session.title && session.title !== "Untitled");
}

function IconAction({
  label,
  onClick,
  children,
  className = "text-muted-foreground hover:text-foreground",
  destructive,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
  className?: string;
  destructive?: boolean;
}) {
  return (
    <Button
      ghost
      destructive={destructive}
      size="icon"
      className={destructive ? undefined : className}
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      {children}
    </Button>
  );
}

function RowActions({
  session,
  resumeInChatEnabled,
  onStartRename,
  onExport,
  onDelete,
  onSetFlags,
}: Pick<SessionRowProps, "session" | "resumeInChatEnabled" | "onExport" | "onDelete" | "onSetFlags"> & {
  onStartRename: () => void;
}) {
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const navigate = useNavigate();
  const visual = sourceVisual(session.source);
  const SourceIcon = visual.icon;
  return (
    <>
      <Badge tone="outline" className="text-xs">
        <SourceIcon className={`mr-1 h-3 w-3 ${visual.color}`} />
        {session.source ? sourceLabel(session.source) : "local"}
      </Badge>
      {resumeInChatEnabled && (
        <IconAction
          label={t.sessions.resumeInChat}
          className="text-muted-foreground hover:text-success"
          onClick={() => navigate(`/chat?resume=${encodeURIComponent(session.id)}`)}
        >
          <Play />
        </IconAction>
      )}
      <IconAction label={L.rename} onClick={onStartRename}>
        <Pencil />
      </IconAction>
      <IconAction label={session.pinned ? L.unpin : L.pin} onClick={() => void onSetFlags(session, { pinned: !session.pinned })}>
        {session.pinned ? <PinOff /> : <Pin />}
      </IconAction>
      <IconAction
        label={session.archived ? L.unarchive : L.archive}
        onClick={() => void onSetFlags(session, { archived: !session.archived })}
      >
        {session.archived ? <ArchiveRestore /> : <Archive />}
      </IconAction>
      <IconAction label={L.exportJson} onClick={() => onExport(session.id)}>
        <Download />
      </IconAction>
      <IconAction label={t.sessions.deleteSession} onClick={onDelete} destructive>
        <Trash2 />
      </IconAction>
    </>
  );
}

function TitleEditor({
  session,
  onRename,
  onDone,
}: {
  session: SessionInfo;
  onRename: SessionRowProps["onRename"];
  onDone: () => void;
}) {
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const [value, setValue] = useState(hasRealTitle(session) ? (session.title ?? "") : "");
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    const next = value.trim();
    if (!next || next === session.title) {
      onDone();
      return;
    }
    setSaving(true);
    try {
      await onRename(session.id, next, session.profile);
      onDone();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex min-w-0 flex-1 items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
      <Input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") void submit();
          else if (e.key === "Escape") onDone();
        }}
        placeholder="Session title"
        className="h-7 min-w-0 flex-1 py-0 text-sm"
        disabled={saving}
        aria-label={L.rename}
      />
      <IconAction label="Save title" className="text-muted-foreground hover:text-success" onClick={() => void submit()}>
        {saving ? <Spinner className="text-sm" /> : <Check />}
      </IconAction>
      <IconAction label="Cancel rename" onClick={onDone}>
        <X />
      </IconAction>
    </div>
  );
}

function RowMeta({ session }: { session: SessionInfo }) {
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const sep = <span className="text-border">&#183;</span>;
  const lastActive = session.last_active || session.started_at;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-xs text-muted-foreground">
      {session.model && (
        <>
          <span className="max-w-[min(100%,12rem)] truncate sm:max-w-[180px]">{session.model.split("/").pop()}</span>
          {sep}
        </>
      )}
      <span className="shrink-0">
        {session.message_count} {t.common.msgs}
      </span>
      {session.tool_call_count > 0 && (
        <>
          {sep}
          <span className="shrink-0">
            {session.tool_call_count} {t.common.tools}
          </span>
        </>
      )}
      {sep}
      <span
        className="shrink-0"
        title={`${L.lastActiveAt}: ${DATE_TIME.format(lastActive * 1000)} · ${L.startedAt}: ${DATE_TIME.format(session.started_at * 1000)}`}
      >
        {timeAgo(lastActive)}
      </span>
    </div>
  );
}

function RowTitle({ session }: { session: SessionInfo }) {
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const titled = hasRealTitle(session);
  return (
    <>
      <span
        className={`font-mondwest normal-case min-w-0 flex-1 truncate text-sm ${titled ? "font-medium" : "text-muted-foreground italic"}`}
      >
        {titled ? session.title : session.preview ? session.preview.slice(0, 60) : t.sessions.untitledSession}
      </span>
      {session.pinned && (
        <Badge tone="outline" className="shrink-0 text-xs">
          <Pin className="mr-1 h-3 w-3" />
          {L.pinnedBadge}
        </Badge>
      )}
      {session.archived && (
        <Badge tone="secondary" className="shrink-0 text-xs">
          {L.archivedBadge}
        </Badge>
      )}
      {session.is_active && (
        <Badge tone="success" className="shrink-0 text-xs">
          <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
          {t.common.live}
        </Badge>
      )}
    </>
  );
}

/** The expanded transcript: latest 500 messages, with a note when older ones are cut off. */
function RowTranscript({ session, searchQuery }: { session: SessionInfo; searchQuery?: string }) {
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const [resp, setResp] = useState<SessionMessagesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getSessionMessages(session.id, session.profile)
      .then((r) => !cancelled && setResp(r))
      .catch((err) => !cancelled && setError(errorMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [session.id, session.profile]);

  const page = resp?.pagination;
  const truncated = page ? page.returned >= page.limit : false;
  return (
    <div className="min-w-0 border-t border-border bg-background/50 p-4">
      {!resp && !error && (
        <div className="flex items-center justify-center py-8">
          <Spinner className="text-xl text-primary" />
        </div>
      )}
      {error && <p className="text-sm text-destructive py-4 text-center">{error}</p>}
      {resp && resp.messages.length === 0 && (
        <p className="text-sm text-muted-foreground py-4 text-center">{t.sessions.noMessages}</p>
      )}
      {truncated && page && (
        <p className="mb-2 text-xs text-muted-foreground">{L.historyTruncated.replace("{count}", String(page.limit))}</p>
      )}
      {resp && resp.messages.length > 0 && <MessageList messages={resp.messages} highlight={searchQuery} />}
    </div>
  );
}

export function SessionRow(props: SessionRowProps) {
  const { session, snippet, searchQuery, isExpanded, isSelected, onToggle, onSelectClick } = props;
  const { t } = useI18n();
  const [renaming, setRenaming] = useState(false);
  const visual = sourceVisual(session.source);
  const SourceIcon = visual.icon;

  // Selected beats live: an explicit selection must stay unambiguous while scrolling.
  const containerClasses = isSelected
    ? "border-primary/40 bg-primary/[0.06]"
    : session.is_active
      ? "border-success/30 bg-success/[0.03]"
      : "border-border";

  const actions = (
    <RowActions
      session={session}
      resumeInChatEnabled={props.resumeInChatEnabled}
      onStartRename={() => setRenaming(true)}
      onExport={props.onExport}
      onDelete={props.onDelete}
      onSetFlags={props.onSetFlags}
    />
  );

  return (
    <div className={`max-w-full min-w-0 overflow-hidden border transition-colors ${containerClasses}`}>
      <div className="flex cursor-pointer items-start gap-3 p-3 transition-colors hover:bg-secondary/30" onClick={onToggle}>
        <span className="flex shrink-0 items-center pt-0.5">
          {/* onClick on the Checkbox itself: carries shiftKey for range select, and Space
              on the focused checkbox synthesizes the same click — one path for both. */}
          <Checkbox
            checked={isSelected}
            onClick={(e) => {
              e.stopPropagation();
              onSelectClick(e);
            }}
            aria-label={t.sessions.selectSession}
          />
        </span>
        <div className={`shrink-0 pt-0.5 ${visual.color}`}>
          <SourceIcon className="h-4 w-4" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <div className="flex min-w-0 items-center gap-2">
                {renaming ? (
                  <TitleEditor session={session} onRename={props.onRename} onDone={() => setRenaming(false)} />
                ) : (
                  <RowTitle session={session} />
                )}
              </div>
              <RowMeta session={session} />
              {snippet && <SnippetHighlight snippet={snippet} />}
            </div>
            <div className="hidden shrink-0 items-center gap-2 sm:flex">{actions}</div>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:hidden">{actions}</div>
        </div>
      </div>
      {isExpanded && <RowTranscript session={session} searchQuery={searchQuery} />}
    </div>
  );
}
