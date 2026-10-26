import {
  useEffect,
  useLayoutEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import { RefreshCw, Search } from "lucide-react";
import { useSearchParams } from "react-router";
import { api } from "@/lib/api";
import type { LogFilesResponse } from "@/lib/api";
import { Badge } from "@nous-research/ui/ui/components/badge";
import { Button } from "@nous-research/ui/ui/components/button";
import { FilterGroup, Segmented } from "@nous-research/ui/ui/components/segmented";
import { Input } from "@nous-research/ui/ui/components/input";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { Switch } from "@nous-research/ui/ui/components/switch";
import { Label } from "@nous-research/ui/ui/components/label";
import { useToast } from "@nous-research/ui/hooks/use-toast";
import { Toast } from "@nous-research/ui/ui/components/toast";
import { useI18n } from "@/i18n";
import { en } from "@/i18n/en";
import { usePageHeader } from "@/contexts/usePageHeader";
import { PluginSlot } from "@/plugins";
import { errorMessage } from "@/lib/api-error";
import { isNearBottom, logFileOptions } from "@/lib/log-files";
import { saveBlob } from "@/lib/save-blob";
import { LogViewer } from "./LogsPage_viewer";

const LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR"] as const;
// Fallback until /api/logs/files answers (older backend: this was the whole set).
const DEFAULT_COMPONENTS = ["gateway", "agent", "tools", "cli", "cron"];
const LINE_COUNTS = [50, 100, 200, 500] as const;

const formatFilterLabel = (value: string) => value.toUpperCase();

const toSegmentOptions = <T extends string>(values: readonly T[]) =>
  values.map((v) => ({ value: v, label: formatFilterLabel(v) }));

const filterGroupClass =
  "flex min-w-0 w-full flex-col items-start gap-1.5 sm:w-auto sm:max-w-full sm:flex-row sm:items-center";

const segmentedClass =
  "w-fit max-w-full flex-wrap justify-start self-start";

/** Debounced copy of *value* so typing a filter does not refetch per keystroke. */
function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

export default function LogsPage() {
  // `?file=gateway` deep link (System page "Open logs" next to a failed gateway).
  const [searchParams] = useSearchParams();
  const [file, setFile] = useState(() => searchParams.get("file") || "agent");
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("ALL");
  const [component, setComponent] = useState("all");
  const [lineCount, setLineCount] = useState<(typeof LINE_COUNTS)[number]>(100);
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search, 300);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inventory, setInventory] = useState<LogFilesResponse | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Follow the tail only while the reader sits at the bottom (true until they scroll up).
  const followRef = useRef(true);
  const { t } = useI18n();
  const { toast, showToast } = useToast();
  const { setAfterTitle, setEnd } = usePageHeader();
  const logsT = { ...en.logs, ...t.logs } as Required<typeof en.logs>;

  useEffect(() => {
    api.getLogFiles().then(setInventory).catch(() => setInventory(null));
  }, []);

  const fetchLogs = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getLogs({ file, lines: lineCount, level, component, search: debouncedSearch })
      .then((resp) => {
        setLines(resp.lines);
        setTimeout(() => {
          const el = scrollRef.current;
          if (el && followRef.current) el.scrollTop = el.scrollHeight;
        }, 50);
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }, [file, lineCount, level, component, debouncedSearch]);

  const downloadFile = useCallback(async () => {
    setDownloading(true);
    try {
      const info = inventory?.files.find((f) => f.name === file);
      saveBlob(await api.downloadLog(file), info?.filename ?? `${file}.log`);
    } catch (err) {
      showToast(`${logsT.downloadFailed}: ${errorMessage(err)}`, "error");
    } finally {
      setDownloading(false);
    }
  }, [file, inventory, logsT.downloadFailed, showToast]);

  useLayoutEffect(() => {
    setAfterTitle(
      <span className="flex items-center gap-1.5">
        <Badge tone="secondary" className="text-xs">
          {formatFilterLabel(file)} · {formatFilterLabel(level)} ·{" "}
          {formatFilterLabel(component)}
        </Badge>
        <Button
          type="button"
          ghost
          size="icon"
          className="text-muted-foreground hover:text-foreground"
          onClick={fetchLogs}
          disabled={loading}
          aria-label={t.common.refresh}
        >
          {loading ? <Spinner /> : <RefreshCw />}
        </Button>
      </span>,
    );
    setEnd(
      <div className="flex w-full min-w-0 flex-wrap items-center justify-start gap-2 sm:justify-end sm:gap-3">
        <div className="flex items-center gap-2">
          <Label htmlFor="logs-auto-refresh" className="text-xs cursor-pointer">
            {t.logs.autoRefresh}
          </Label>
          <Switch
            checked={autoRefresh}
            onCheckedChange={setAutoRefresh}
            id="logs-auto-refresh"
          />
          {autoRefresh && (
            <Badge tone="success" className="text-xs">
              <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              {t.common.live}
            </Badge>
          )}
        </div>
      </div>,
    );
    return () => {
      setAfterTitle(null);
      setEnd(null);
    };
  }, [
    autoRefresh,
    component,
    file,
    level,
    loading,
    setAfterTitle,
    setEnd,
    t.common.live,
    t.common.refresh,
    t.logs.autoRefresh,
    fetchLogs,
  ]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (!autoRefresh) return;
    const tick = () => {
      if (!document.hidden) fetchLogs();
    };
    const interval = setInterval(tick, 5000);
    const onVisible = () => {
      if (!document.hidden) fetchLogs();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [autoRefresh, fetchLogs]);

  const selectFile = (next: string) => {
    followRef.current = true;
    setFile(next);
  };

  return (
    <div className="flex min-w-0 max-w-full flex-col gap-4">
      <Toast toast={toast} />
      <PluginSlot name="logs:top" />
      <div
        role="toolbar"
        aria-label={t.logs.title}
        className="flex min-w-0 max-w-full flex-col items-start gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:gap-x-6 sm:gap-y-3"
      >
        <FilterGroup label={t.logs.file} className={filterGroupClass}>
          <Segmented
            className={segmentedClass}
            value={file}
            onChange={selectFile}
            options={toSegmentOptions(logFileOptions(inventory?.files ?? null, file))}
          />
        </FilterGroup>

        <FilterGroup label={t.logs.level} className={filterGroupClass}>
          <Segmented
            className={segmentedClass}
            value={level}
            onChange={setLevel}
            options={toSegmentOptions(LEVELS)}
          />
        </FilterGroup>

        <FilterGroup label={t.logs.component} className={filterGroupClass}>
          <Segmented
            className={segmentedClass}
            value={component}
            onChange={setComponent}
            options={toSegmentOptions(["all", ...(inventory?.components ?? DEFAULT_COMPONENTS)])}
          />
        </FilterGroup>

        <FilterGroup label={t.logs.lines} className={filterGroupClass}>
          <Segmented
            className={segmentedClass}
            value={String(lineCount)}
            onChange={(v) =>
              setLineCount(Number(v) as (typeof LINE_COUNTS)[number])
            }
            options={LINE_COUNTS.map((n) => ({
              value: String(n),
              label: String(n),
            }))}
          />
        </FilterGroup>

        <div className="relative w-full sm:w-64">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={logsT.search}
            aria-label={logsT.search}
            className="h-8 py-0 pl-8 text-xs"
          />
        </div>
      </div>

      <LogViewer
        file={file}
        info={inventory?.files.find((f) => f.name === file)}
        lines={lines}
        loading={loading}
        error={error}
        downloading={downloading}
        onDownload={() => void downloadFile()}
        scrollRef={scrollRef}
        onScroll={(e) => {
          followRef.current = isNearBottom(e.currentTarget);
        }}
        labels={{
          noLogLines: t.logs.noLogLines,
          noFileYet: logsT.noFileYet,
          download: logsT.download,
        }}
      />
      <PluginSlot name="logs:bottom" />
    </div>
  );
}
