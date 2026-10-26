import type { RefObject, UIEventHandler } from "react";
import { Download, FileText } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@nous-research/ui/ui/components/card";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import type { LogFileInfo } from "@/lib/api";
import { classifyLine } from "@/lib/log-classify";
import { formatBytes } from "@/lib/save-blob";

const LINE_COLORS: Record<string, string> = {
  error: "text-destructive",
  warning: "text-warning",
  info: "text-foreground",
  debug: "text-text-tertiary",
};

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

interface LogViewerProps {
  file: string;
  info?: LogFileInfo;
  lines: string[];
  loading: boolean;
  error: string | null;
  downloading: boolean;
  onDownload: () => void;
  scrollRef: RefObject<HTMLDivElement | null>;
  onScroll: UIEventHandler<HTMLDivElement>;
  labels: { noLogLines: string; noFileYet: string; download: string };
}

function fileMeta(info?: LogFileInfo): string {
  if (!info?.exists) return "";
  const when = info.mtime ? ` · ${DATE_FORMAT.format(info.mtime * 1000)}` : "";
  return `${formatBytes(info.size)}${when}${info.root_home ? " · root home" : ""}`;
}

/** The log card: filename + size/mtime header with a full-file download, and the tail itself. */
export function LogViewer({
  file,
  info,
  lines,
  loading,
  error,
  downloading,
  onDownload,
  scrollRef,
  onScroll,
  labels,
}: LogViewerProps) {
  const missing = info !== undefined && !info.exists;
  return (
    <Card className="min-w-0 max-w-full overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between gap-2 py-3 px-4">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm">
          <FileText className="h-4 w-4 shrink-0" />
          <span className="truncate">{info?.filename ?? `${file}.log`}</span>
          <span className="truncate text-xs font-normal normal-case text-muted-foreground">
            {fileMeta(info)}
          </span>
        </CardTitle>
        <Button
          type="button"
          ghost
          size="sm"
          onClick={onDownload}
          disabled={downloading || missing}
          prefix={downloading ? <Spinner /> : <Download />}
          title={labels.download}
          aria-label={labels.download}
        >
          <span className="hidden sm:inline">{labels.download}</span>
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        {error && (
          <div className="bg-destructive/10 border-b border-destructive/20 p-3">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="max-w-full min-h-[400px] max-h-[calc(100vh-220px)] overflow-auto p-4 font-mono-ui text-xs leading-5 break-words"
        >
          {lines.length === 0 && !loading && (
            <p className="text-muted-foreground text-center py-8">
              {missing ? labels.noFileYet : labels.noLogLines}
            </p>
          )}
          {lines.map((line, i) => (
            <div key={i} className={`${LINE_COLORS[classifyLine(line)]} hover:bg-secondary/20 px-1 -mx-1`}>
              {line}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
