import { useEffect, useLayoutEffect, useMemo, useState, useCallback, useRef } from "react";
import { AlertTriangle, Archive, Clock, Eraser, Search, Trash2, Upload, X } from "lucide-react";
import { api } from "@/lib/api";
import { shouldRefreshSessions } from "@/lib/session-refresh";
import { importSummary, parseImportSessions } from "@/lib/session-import";
import { groupSessionsByDate, type SessionGroupKey } from "@/lib/session-groups";
import type { SessionInfo, SessionSearchResult, SessionStoreStats, StatusResponse } from "@/lib/api";
import { PlatformsCard } from "@/components/PlatformsCard";
import { LoadErrorNotice } from "@/components/LoadErrorNotice";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { Button } from "@nous-research/ui/ui/components/button";
import { Segmented } from "@nous-research/ui/ui/components/segmented";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { useConfirmDelete } from "@nous-research/ui/hooks/use-confirm-delete";
import { Input } from "@nous-research/ui/ui/components/input";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { useI18n } from "@/i18n";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";
import { isDashboardEmbeddedChatEnabled } from "@/lib/dashboard-flags";
import { apiErrorFromResponse, errorMessage } from "@/lib/api-error";
import { saveBlob } from "@/lib/save-blob";
import { SessionRow, type SessionFlags } from "./SessionsPage_row";
import { CleanupDialog, PruneDialog } from "./SessionsPage_dialogs";
import {
  PAGE_SIZE,
  RecentSessionsCard,
  SessionStatsStrip,
  SessionsPagination,
  SourceFilterMenu,
  SystemActionLog,
} from "./SessionsPage_parts";
import { useSessionSourceFilter } from "./SessionsPage_filters";
import { sessionsLabels, type SessionsLabels } from "./SessionsPage_labels";

type SessionsView = "list" | "overview";

const GROUP_LABEL: Record<SessionGroupKey, keyof SessionsLabels> = {
  pinned: "groupPinned",
  today: "groupToday",
  yesterday: "groupYesterday",
  week: "groupWeek",
  month: "groupMonth",
  older: "groupOlder",
};

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadedOnce, setLoadedOnce] = useState(false);
  // A failed list load is NOT "no sessions": keep the error visible with a retry.
  const [listError, setListError] = useState<string | null>(null);
  const [storageCorrupt, setStorageCorrupt] = useState(false);
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<SessionSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [overviewSessions, setOverviewSessions] = useState<SessionInfo[]>([]);
  // History (grouped, searchable, actionable) is the default; Overview is the glance view.
  const [view, setView] = useState<SessionsView>("list");
  const [archivedView, setArchivedView] = useState(false);
  const sessionsRequestRef = useRef(0);
  // Global count of empty (no-message, ended, non-archived) sessions — a page can't know it.
  const [emptyCount, setEmptyCount] = useState(0);
  const [deleteEmptyOpen, setDeleteEmptyOpen] = useState(false);
  const [deletingEmpty, setDeletingEmpty] = useState(false);
  // Bulk selection; ``lastClickedIndexRef`` anchors shift-click ranges in the visible list.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const lastClickedIndexRef = useRef<number | null>(null);
  const [deleteSelectedOpen, setDeleteSelectedOpen] = useState(false);
  const [deletingSelected, setDeletingSelected] = useState(false);
  const [stats, setStats] = useState<SessionStoreStats | null>(null);
  const [pruneOpen, setPruneOpen] = useState(false);
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [importingSessions, setImportingSessions] = useState(false);
  const { toast, showToast } = useToast();
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const { setAfterTitle, setEnd } = usePageHeader();
  const resumeInChatEnabled = isDashboardEmbeddedChatEnabled();

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
    lastClickedIndexRef.current = null;
  }, []);

  const resetForFilterChange = useCallback(() => {
    setPage(0);
    setExpandedId(null);
    clearSelection();
  }, [clearSelection]);

  const sourceFilter = useSessionSourceFilter(stats, t, resetForFilterChange);

  // Sorted by latest activity across the compression chain, so the date groups are coherent
  // and a chat continued today sits on top whenever it was created.
  const sessionQueryOptions = useMemo(
    () => ({
      ...sourceFilter.queryOptions,
      order: "recent" as const,
      ...(archivedView ? { archived: "only" as const } : {}),
    }),
    [sourceFilter.queryOptions, archivedView],
  );

  const refreshEmptyCount = useCallback(() => {
    api
      .getEmptySessionsCount()
      .then((r) => setEmptyCount(r.count))
      .catch(() => {});
  }, []);

  useLayoutEffect(() => {
    if (loading && !loadedOnce) {
      setAfterTitle(null);
      return;
    }
    setAfterTitle(
      <Badge tone="secondary" className="text-xs tabular-nums">
        {total}
      </Badge>,
    );
    return () => {
      setAfterTitle(null);
    };
  }, [loading, loadedOnce, setAfterTitle, total]);

  useEffect(() => {
    setEnd(
      <div className="flex items-center gap-2">
        <Button outlined size="sm" onClick={() => setCleanupOpen(true)} prefix={<Trash2 />}>
          Limpiar
        </Button>
        <Button outlined size="sm" onClick={() => setPruneOpen(true)} prefix={<Archive />}>
          {L.pruneButton}
        </Button>
      </div>,
    );
    return () => {
      setEnd(null);
    };
  }, [setEnd, L.pruneButton]);

  const loadSessions = useCallback(
    (p: number, silent = false) => {
      // ``silent``: background refresh (overview poll saw a new session) without the spinner.
      const requestId = silent ? sessionsRequestRef.current : sessionsRequestRef.current + 1;
      if (!silent) {
        sessionsRequestRef.current = requestId;
        setLoading(true);
      }
      api
        .getSessions(PAGE_SIZE, p * PAGE_SIZE, sessionQueryOptions)
        .then((resp) => {
          if (requestId !== sessionsRequestRef.current) return;
          setSessions(resp.sessions);
          setTotal(resp.total);
          setListError(null);
          setStorageCorrupt(Object.values(resp.storage ?? {}).includes("corrupt"));
        })
        .catch((e) => {
          if (requestId === sessionsRequestRef.current && !silent) setListError(errorMessage(e));
        })
        .finally(() => {
          if (requestId !== sessionsRequestRef.current || silent) return;
          setLoading(false);
          setLoadedOnce(true);
        });
    },
    [sessionQueryOptions],
  );

  const loadStats = useCallback(() => {
    api
      .getSessionStats()
      .then(setStats)
      .catch(() => {});
  }, []);

  const reloadAll = useCallback(() => {
    clearSelection();
    setPage(0);
    loadSessions(0);
    loadStats();
    refreshEmptyCount();
  }, [clearSelection, loadSessions, loadStats, refreshEmptyCount]);

  const handleImportSessions = useCallback(
    async (files: FileList | null) => {
      const file = files?.[0];
      if (!file) return;
      setImportingSessions(true);
      try {
        const result = await api.importSessions(parseImportSessions(await file.text()));
        showToast(`Import complete: ${importSummary(result)}`, "success");
        clearSelection();
        loadSessions(page, true);
        loadStats();
        refreshEmptyCount();
      } catch (error) {
        showToast(`Import failed: ${errorMessage(error)}`, "error");
      } finally {
        setImportingSessions(false);
        if (importInputRef.current) importInputRef.current.value = "";
      }
    },
    [clearSelection, loadSessions, loadStats, page, refreshEmptyCount, showToast],
  );

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  // The overview poll reads page / newest-seen id through refs (it mounts once per filter).
  const newestSeenRef = useRef<string | null>(null);
  const pageRef = useRef(page);

  useEffect(() => {
    pageRef.current = page;
  }, [page]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      loadSessions(page);
      refreshEmptyCount();
    });
    return () => {
      cancelled = true;
    };
  }, [loadSessions, page, refreshEmptyCount]);

  useEffect(() => {
    let cancelled = false;
    const loadOverview = () => {
      if (document.hidden) return; // a hidden tab does not need to refresh
      api
        .getStatus()
        .then((nextStatus) => !cancelled && setStatus(nextStatus))
        .catch(() => {});
      api
        .getSessions(50, 0, sessionQueryOptions)
        .then((r) => {
          if (cancelled) return;
          setOverviewSessions(r.sessions);
          // No push channel between the dashboard and a terminal CLI sharing the DB: a new
          // head id means another process created (or, sorted by activity, continued) a
          // session — refresh the page silently.
          const newest = r.sessions[0]?.id ?? null;
          if (shouldRefreshSessions(newestSeenRef.current, newest)) {
            loadSessions(pageRef.current, true);
          }
          newestSeenRef.current = newest;
        })
        .catch(() => {});
    };
    loadOverview();
    const id = setInterval(loadOverview, 5000);
    const onVisible = () => {
      if (!document.hidden) loadOverview();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [loadSessions, sessionQueryOptions]);

  // These setters also clear the bulk selection: a selection carried across a page change,
  // search or view switch would arm rows the user can no longer see.
  const goToPage = useCallback(
    (p: number) => {
      setPage(p);
      clearSelection();
    },
    [clearSelection],
  );
  const updateSearch = useCallback(
    (value: string) => {
      setSearch(value);
      if (value.trim()) setView("list");
      clearSelection();
    },
    [clearSelection],
  );
  const switchView = useCallback(
    (next: string) => {
      setView(next as SessionsView);
      clearSelection();
    },
    [clearSelection],
  );
  const toggleArchivedView = useCallback(() => {
    setArchivedView((v) => !v);
    setView("list");
    resetForFilterChange();
  }, [resetForFilterChange]);

  // Debounced FTS search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!search.trim()) {
      debounceRef.current = setTimeout(() => {
        setSearchResults(null);
        setSearching(false);
      }, 0);
      return;
    }
    debounceRef.current = setTimeout(() => {
      setSearching(true);
      setSearchResults(null);
      api
        .searchSessions(search.trim(), sessionQueryOptions)
        .then((resp) => setSearchResults(resp.results))
        .catch((e) => {
          setSearchResults(null);
          showToast(`Search failed: ${errorMessage(e)}`, "error");
        })
        .finally(() => setSearching(false));
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [search, sessionQueryOptions, showToast]);

  // The profile a listed row was read from — every per-row request (delete, rename, export,
  // messages) must go to that store, not the global management profile, which can lag the
  // row. An unstamped row from an older backend falls back to the management profile.
  const rowProfile = useCallback(
    (id: string) => (searchResults ?? sessions).find((s) => s.id === id)?.profile,
    [searchResults, sessions],
  );

  const sessionDelete = useConfirmDelete({
    onDelete: useCallback(
      async (id: string) => {
        try {
          await api.deleteSession(id, rowProfile(id));
          setSessions((prev) => prev.filter((s) => s.id !== id));
          setSearchResults((prev) => prev?.filter((s) => s.id !== id) ?? null);
          setTotal((prev) => prev - 1);
          if (expandedId === id) setExpandedId(null);
          setSelectedIds((prev) => {
            if (!prev.has(id)) return prev;
            const next = new Set(prev);
            next.delete(id);
            return next;
          });
          refreshEmptyCount();
          showToast(t.sessions.sessionDeleted, "success");
          loadStats();
        } catch (e) {
          showToast(`${t.sessions.failedToDelete}: ${errorMessage(e)}`, "error");
          throw new Error("delete failed");
        }
      },
      [expandedId, refreshEmptyCount, rowProfile, showToast, loadStats, t.sessions.sessionDeleted, t.sessions.failedToDelete],
    ),
  });

  /** Toggle one row; shift-click extends from the last anchor to here (Gmail/Notion style).
   *  ``visibleList`` is what is rendered (post-search), since indices resolve against it. */
  const handleSelectClick = useCallback((event: React.MouseEvent, index: number, visibleList: SessionInfo[]) => {
    const id = visibleList[index]?.id;
    if (!id) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const willSelect = !next.has(id);
      const anchor = lastClickedIndexRef.current;
      if (event.shiftKey && anchor !== null && anchor < visibleList.length) {
        const [lo, hi] = anchor <= index ? [anchor, index] : [index, anchor];
        for (let i = lo; i <= hi; i++) {
          const rowId = visibleList[i]?.id;
          if (!rowId) continue;
          if (willSelect) next.add(rowId);
          else next.delete(rowId);
        }
      } else if (willSelect) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
    lastClickedIndexRef.current = index;
  }, []);

  const selectAllOnPage = useCallback((visibleList: SessionInfo[]) => {
    setSelectedIds((prev) => new Set([...prev, ...visibleList.map((s) => s.id)]));
  }, []);

  const handleDeleteSelected = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) {
      setDeleteSelectedOpen(false);
      return;
    }
    setDeletingSelected(true);
    try {
      // One listed page shares one owning profile; a mixed selection uses the management one.
      const owners = new Set(ids.map(rowProfile));
      const resp = await api.bulkDeleteSessions(ids, owners.size === 1 ? [...owners][0] : undefined);
      const skippedCount = resp.skipped_active?.length ?? 0;
      showToast(
        skippedCount
          ? t.sessions.selectedSessionsSkippedActive
              .replace("{deleted}", String(resp.deleted))
              .replace("{count}", String(skippedCount))
          : t.sessions.selectedSessionsDeleted.replace("{count}", String(resp.deleted)),
        skippedCount ? "error" : "success",
      );
      setDeleteSelectedOpen(false);
      // Rows a live turn still owns were refused server-side; keep them listed.
      const skipped = new Set(resp.skipped_active ?? []);
      const deletedSet = new Set(ids.filter((id) => !skipped.has(id)));
      setSessions((prev) => prev.filter((s) => !deletedSet.has(s.id)));
      setTotal((prev) => Math.max(0, prev - resp.deleted));
      if (expandedId && deletedSet.has(expandedId)) setExpandedId(null);
      clearSelection();
      loadSessions(page);
      refreshEmptyCount();
    } catch (e) {
      showToast(`${t.sessions.failedToDeleteSelected}: ${errorMessage(e)}`, "error");
    } finally {
      setDeletingSelected(false);
    }
  }, [clearSelection, expandedId, loadSessions, page, refreshEmptyCount, rowProfile, selectedIds, showToast, t.sessions]);

  const handleDeleteEmpty = useCallback(async () => {
    setDeletingEmpty(true);
    try {
      const resp = await api.deleteEmptySessions();
      showToast(t.sessions.emptySessionsDeleted.replace("{count}", String(resp.deleted)), "success");
      setDeleteEmptyOpen(false);
      loadSessions(page);
      refreshEmptyCount();
    } catch (e) {
      showToast(`${t.sessions.failedToDeleteEmpty}: ${errorMessage(e)}`, "error");
    } finally {
      setDeletingEmpty(false);
    }
  }, [loadSessions, page, refreshEmptyCount, showToast, t.sessions]);

  const handleRename = useCallback(
    async (id: string, title: string, profile?: string) => {
      try {
        await api.renameSession(id, title, profile ?? rowProfile(id));
        const retitle = (rows: SessionInfo[]) => rows.map((s) => (s.id === id ? { ...s, title } : s));
        setSessions(retitle);
        setOverviewSessions(retitle);
        showToast(L.renamed, "success");
        loadStats();
      } catch (e) {
        showToast(`${L.renameFailed}: ${errorMessage(e)}`, "error");
      }
    },
    [rowProfile, showToast, loadStats, L.renamed, L.renameFailed],
  );

  /** Archive / pin. An archived row leaves the default list (and an unarchived one leaves the
   *  archived view), so the page reloads; a pin re-groups in place. */
  const handleSetFlags = useCallback(
    async (session: SessionInfo, flags: SessionFlags) => {
      try {
        await api.setSessionFlags(session.id, flags, session.profile ?? rowProfile(session.id));
        if (flags.archived !== undefined) {
          showToast(flags.archived ? L.sessionArchived : L.sessionUnarchived, "success");
          loadSessions(page);
          loadStats();
          refreshEmptyCount();
        } else {
          setSessions((rows) => rows.map((s) => (s.id === session.id ? { ...s, ...flags } : s)));
        }
      } catch (e) {
        showToast(`${L.updateFailed}: ${errorMessage(e)}`, "error");
      }
    },
    [rowProfile, showToast, loadSessions, loadStats, page, refreshEmptyCount, L.sessionArchived, L.sessionUnarchived, L.updateFailed],
  );

  const handleExport = useCallback(
    async (id: string) => {
      try {
        const res = await fetch(api.exportSessionUrl(id, rowProfile(id)), {
          credentials: "include",
          headers: { "X-Clawksis-Session-Token": window.__CLAWK_SESSION_TOKEN__ ?? "" },
        });
        if (!res.ok) throw apiErrorFromResponse(res.status, await res.text().catch(() => ""), res.url);
        saveBlob(await res.blob(), `session-${id}.json`);
      } catch (e) {
        showToast(`${L.exportFailed}: ${errorMessage(e)}`, "error");
      }
    },
    [rowProfile, showToast, L.exportFailed],
  );

  const openFromOverview = useCallback(
    (session: SessionInfo) => {
      setView("list");
      setExpandedId(session.id);
      goToPage(0);
    },
    [goToPage],
  );

  const pendingSession = sessionDelete.pendingId ? sessions.find((s) => s.id === sessionDelete.pendingId) : null;

  // session_id → FTS snippet for the matched rows.
  const snippetMap = new Map<string, string>();
  for (const r of searchResults ?? []) {
    snippetMap.set(r.session_id, r.snippet);
    snippetMap.set(r.id, r.snippet);
  }

  const filtered = searchResults ?? sessions;
  const isSearching = Boolean(search.trim());
  // Relevance order for search hits; date groups for the history.
  const groups = isSearching ? [{ key: null, sessions: filtered }] : groupSessionsByDate(filtered);
  const indexById = new Map(filtered.map((s, i) => [s.id, i]));

  const platformEntries = status ? Object.entries(status.gateway_platforms ?? {}) : [];
  const recentSessions = overviewSessions.slice(0, 5);
  const showOverviewTab = !archivedView && (platformEntries.length > 0 || recentSessions.length > 0);
  const showList = view === "list" || isSearching || !showOverviewTab;
  const showPagination = showList && !isSearching && total > PAGE_SIZE;

  const alerts: { message: string; detail?: string }[] = [];
  if (status?.gateway_state === "startup_failed") {
    alerts.push({ message: t.status.gatewayFailedToStart, detail: status.gateway_exit_reason ?? undefined });
  }
  for (const [name, info] of platformEntries) {
    if (info.state !== "fatal" && info.state !== "disconnected") continue;
    alerts.push({
      message: `${name.charAt(0).toUpperCase() + name.slice(1)} ${info.state === "fatal" ? t.status.platformError : t.status.platformDisconnected}`,
      detail: info.error_message ?? undefined,
    });
  }

  if (loading && !loadedOnce) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner className="text-2xl text-primary" />
      </div>
    );
  }

  const emptyMessage = search
    ? t.sessions.noMatch
    : archivedView || sourceFilter.hasSelection || sourceFilter.category !== "chats"
      ? t.sessions.noSessionsInFilter
      : t.sessions.noSessions;

  return (
    <div className="flex min-w-0 w-full max-w-full flex-col gap-4">
      <PluginSlot name="sessions:top" />
      <Toast toast={toast} />
      <input
        ref={importInputRef}
        type="file"
        accept=".json,.jsonl,application/json,application/x-ndjson"
        className="hidden"
        onChange={(event) => void handleImportSessions(event.currentTarget.files)}
      />

      <DeleteConfirmDialog
        open={sessionDelete.isOpen}
        onCancel={sessionDelete.cancel}
        onConfirm={sessionDelete.confirm}
        title={t.sessions.confirmDeleteTitle}
        description={
          pendingSession?.title && pendingSession.title !== "Untitled"
            ? `"${pendingSession.title}" — ${t.sessions.confirmDeleteMessage}`
            : t.sessions.confirmDeleteMessage
        }
        loading={sessionDelete.isDeleting}
      />
      <DeleteConfirmDialog
        open={deleteEmptyOpen}
        onCancel={() => setDeleteEmptyOpen(false)}
        onConfirm={handleDeleteEmpty}
        title={t.sessions.deleteEmptyConfirmTitle}
        description={t.sessions.deleteEmptyConfirmMessage.replace("{count}", String(emptyCount))}
        loading={deletingEmpty}
      />
      <DeleteConfirmDialog
        open={deleteSelectedOpen}
        onCancel={() => setDeleteSelectedOpen(false)}
        onConfirm={handleDeleteSelected}
        title={t.sessions.deleteSelectedConfirmTitle.replace("{count}", String(selectedIds.size))}
        description={t.sessions.deleteSelectedConfirmMessage.replace("{count}", String(selectedIds.size))}
        loading={deletingSelected}
      />
      <PruneDialog open={pruneOpen} onOpenChange={setPruneOpen} onChanged={reloadAll} notify={showToast} />
      <CleanupDialog
        open={cleanupOpen}
        onOpenChange={setCleanupOpen}
        onChanged={reloadAll}
        notify={showToast}
        sources={sourceFilter.allSourceNames}
      />

      {stats && <SessionStatsStrip stats={stats} archivedView={archivedView} onToggleArchived={toggleArchivedView} />}

      {alerts.length > 0 && (
        <div className="border border-destructive/30 bg-destructive/[0.06] p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
            <div className="flex flex-col gap-2 min-w-0">
              {alerts.map((alert, i) => (
                <div key={i}>
                  <p className="text-sm font-medium text-destructive">{alert.message}</p>
                  {alert.detail && <p className="text-xs text-destructive/70 mt-0.5">{alert.detail}</p>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <SystemActionLog />

      <div className="flex w-full min-w-0 flex-wrap items-center gap-2 sm:gap-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 sm:gap-3">
          <Segmented
            className="w-fit shrink-0"
            size="md"
            value={sourceFilter.category}
            onChange={sourceFilter.changeCategory}
            options={[
              { value: "chats", label: t.sessions.filterChats },
              { value: "automation", label: t.sessions.filterAutomation },
              { value: "all", label: t.sessions.filterAll },
            ]}
          />
          <SourceFilterMenu
            label={sourceFilter.label}
            title={sourceFilter.title}
            options={sourceFilter.options}
            selected={sourceFilter.selectedSet}
            canClear={sourceFilter.hasSelection}
            onToggle={sourceFilter.toggle}
            onClear={sourceFilter.clear}
          />
          <Button
            outlined={!archivedView}
            size="sm"
            className="shrink-0"
            onClick={toggleArchivedView}
            aria-pressed={archivedView}
            prefix={<Archive />}
          >
            <span className="font-mondwest normal-case text-xs">{L.showArchived}</span>
          </Button>
          {showOverviewTab && !isSearching && (
            <Segmented
              className="w-fit shrink-0"
              size="md"
              value={view}
              onChange={switchView}
              options={[
                { value: "list", label: t.sessions.history },
                { value: "overview", label: t.sessions.overview },
              ]}
            />
          )}
          <div className="relative min-w-0 w-full sm:w-auto sm:min-w-[12rem] sm:max-w-md sm:flex-1">
            {searching ? (
              <Spinner className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[0.875rem] text-primary" />
            ) : (
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            )}
            <Input
              placeholder={t.sessions.searchPlaceholder}
              value={search}
              onChange={(e) => updateSearch(e.target.value)}
              className="h-8 py-0 pr-7 pl-8 text-xs leading-none"
            />
            {search && (
              <Button
                ghost
                size="xs"
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => updateSearch("")}
                aria-label={t.common.clear}
              >
                <X />
              </Button>
            )}
          </div>
          {showList && emptyCount > 0 && !isSearching && !archivedView && (
            <Button
              outlined
              destructive
              size="sm"
              className="shrink-0"
              onClick={() => setDeleteEmptyOpen(true)}
              aria-label={t.sessions.deleteEmpty}
              title={t.sessions.deleteEmpty}
              prefix={<Eraser />}
            >
              <span className="font-mondwest normal-case text-xs">
                {t.sessions.deleteEmpty} ({emptyCount})
              </span>
            </Button>
          )}
          {!isSearching && (
            <Button
              outlined
              size="sm"
              className="shrink-0"
              disabled={importingSessions}
              onClick={() => importInputRef.current?.click()}
              aria-label="Import exported sessions"
              title="Import exported session JSON or JSONL"
              prefix={importingSessions ? <Spinner /> : <Upload />}
            >
              <span className="font-mondwest normal-case text-xs">Import sessions</span>
            </Button>
          )}
          {loading && <Spinner className="text-sm text-muted-foreground" />}
        </div>
        {showPagination && (
          <SessionsPagination compact className="shrink-0 sm:ml-auto" page={page} total={total} onPageChange={goToPage} />
        )}
      </div>

      {listError && <LoadErrorNotice what={L.loadWhat} detail={listError} onRetry={() => loadSessions(page)} />}
      {storageCorrupt && (
        <div role="alert" className="border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {L.storeCorrupt}
        </div>
      )}

      {showList && selectedIds.size > 0 && (
        <div
          className="flex flex-wrap items-center gap-2 border border-primary/30 bg-primary/[0.06] px-3 py-2"
          role="region"
          aria-label={t.sessions.selectedCount.replace("{count}", String(selectedIds.size))}
        >
          <span className="font-mondwest normal-case text-xs text-primary tabular-nums">
            {t.sessions.selectedCount.replace("{count}", String(selectedIds.size))}
          </span>
          {filtered.some((s) => !selectedIds.has(s.id)) && (
            <Button ghost size="sm" onClick={() => selectAllOnPage(filtered)} aria-label={t.sessions.selectAllOnPage} title={t.sessions.selectAllOnPage}>
              <span className="font-mondwest normal-case text-xs">{t.sessions.selectAllOnPage}</span>
            </Button>
          )}
          <Button ghost size="sm" onClick={clearSelection} aria-label={t.sessions.clearSelection} title={t.sessions.clearSelection}>
            <span className="font-mondwest normal-case text-xs">{t.sessions.clearSelection}</span>
          </Button>
          <Button
            outlined
            destructive
            size="sm"
            className="ml-auto"
            onClick={() => setDeleteSelectedOpen(true)}
            aria-label={t.sessions.deleteSelected.replace("{count}", String(selectedIds.size))}
            title={t.sessions.deleteSelected.replace("{count}", String(selectedIds.size))}
            prefix={<Trash2 />}
          >
            <span className="font-mondwest normal-case text-xs">
              {t.sessions.deleteSelected.replace("{count}", String(selectedIds.size))}
            </span>
          </Button>
        </div>
      )}

      {showList ? (
        filtered.length === 0 && !listError ? (
          <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
            <Clock className="h-8 w-8 mb-3 opacity-40" />
            <p className="text-sm font-medium">{emptyMessage}</p>
            {emptyMessage === t.sessions.noSessions && <p className="text-xs mt-1 text-text-tertiary">{t.sessions.startConversation}</p>}
          </div>
        ) : (
          <>
            {groups.map((group) => (
              <section key={group.key ?? "results"} className="flex min-w-0 flex-col gap-1.5">
                {group.key && (
                  <h3 className="mt-1 text-xs font-medium uppercase tracking-[0.08em] text-muted-foreground">
                    {L[GROUP_LABEL[group.key]] as string}{" "}
                    <span className="tabular-nums text-text-tertiary">({group.sessions.length})</span>
                  </h3>
                )}
                {group.sessions.map((s) => (
                  <SessionRow
                    key={s.id}
                    session={s}
                    snippet={snippetMap.get(s.id)}
                    searchQuery={search || undefined}
                    isExpanded={expandedId === s.id}
                    isSelected={selectedIds.has(s.id)}
                    onToggle={() => setExpandedId((prev) => (prev === s.id ? null : s.id))}
                    onSelectClick={(event) => handleSelectClick(event, indexById.get(s.id) ?? 0, filtered)}
                    onDelete={() => sessionDelete.requestDelete(s.id)}
                    onRename={handleRename}
                    onSetFlags={handleSetFlags}
                    onExport={handleExport}
                    resumeInChatEnabled={resumeInChatEnabled}
                  />
                ))}
              </section>
            ))}
            {showPagination && <SessionsPagination page={page} total={total} onPageChange={goToPage} />}
          </>
        )
      ) : (
        <div className="flex min-w-0 flex-col gap-4">
          {platformEntries.length > 0 && status && <PlatformsCard platforms={platformEntries} />}
          {recentSessions.length > 0 && <RecentSessionsCard sessions={recentSessions} onOpen={openFromOverview} />}
        </div>
      )}

      <PluginSlot name="sessions:bottom" />
    </div>
  );
}
