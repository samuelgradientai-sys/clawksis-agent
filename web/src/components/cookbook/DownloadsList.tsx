import {
  fmtBytes,
  type DownloadProgress,
  type InterruptedDownload,
  type TransferProgress,
} from "@/lib/cookbook";
import { CbButton, Pill, Row } from "./CookbookUi";
import { DownloadBar } from "./DownloadBar";

function stateLabel(status: string, error?: string): { text: string; tone: "violet" | "error" | "done" } {
  if (status === "done") return { text: "ready ✓", tone: "done" };
  if (status === "cancelled") return { text: "cancelled — resumable", tone: "error" };
  if (status === "error" || status.startsWith("error")) {
    return { text: error || status.replace(/^error:\s*/, "") || "failed", tone: "error" };
  }
  if (status === "verifying") return { text: "verifying…", tone: "violet" };
  if (status === "registering") return { text: "registering…", tone: "violet" };
  if (status === "validating") return { text: "checking it runs…", tone: "violet" };
  return { text: "downloading", tone: "violet" };
}

/** Everything being (or recently) downloaded. Transfers run on the server and keep going when
 *  this page is closed; a server restart mid-download leaves a resumable partial file. */
export function DownloadsList({
  downloads,
  pulls,
  interrupted,
  onCancelDownload,
  onCancelPull,
  onResume,
}: {
  downloads: Record<string, DownloadProgress>;
  pulls: Record<string, TransferProgress>;
  interrupted: InterruptedDownload[];
  onCancelDownload: (id: string) => void;
  onCancelPull: (tag: string) => void;
  onResume: (it: InterruptedDownload) => void;
}) {
  const dl = Object.entries(downloads);
  const pl = Object.entries(pulls);
  const orphans = interrupted.filter((it) => !dl.some(([, d]) => d.file === it.file));
  if (dl.length === 0 && pl.length === 0 && orphans.length === 0) {
    return (
      <Row className="border-dashed text-sm text-muted-foreground">
        Nothing downloading. Start one from the Models tab — downloads run on the server and keep going even if you
        close this page.
      </Row>
    );
  }
  return (
    <div className="grid gap-2">
      {orphans.map((it) => (
        <Row key={`int-${it.file}`} className="flex flex-col gap-2 border-amber-500/30 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <p className="break-all text-sm">{it.file}</p>
            <p className="text-xs text-muted-foreground">
              Interrupted by a server restart · {fmtBytes(it.downloaded)} kept{it.repo ? ` · ${it.repo}` : ""}
            </p>
          </div>
          {it.resumable ? (
            <CbButton tone="primary" onClick={() => onResume(it)}>
              Resume
            </CbButton>
          ) : (
            <Pill kind="warn">download it again from Models — it picks up the partial file</Pill>
          )}
        </Row>
      ))}
      {dl.map(([id, d]) => {
        const label = stateLabel(d.status, d.error);
        return (
          <Row key={id}>
            <DownloadBar
              label={`${d.file ?? "model"} · llama.cpp · ${label.text}`}
              progress={d}
              tone={label.tone}
              onCancel={d.status === "downloading" ? () => onCancelDownload(id) : undefined}
            />
          </Row>
        );
      })}
      {pl.map(([tag, p]) => {
        const label = stateLabel(p.status);
        return (
          <Row key={tag}>
            <DownloadBar
              label={`${tag} · Ollama · ${label.text}`}
              progress={p}
              tone={label.tone}
              onCancel={p.status === "pulling" ? () => onCancelPull(tag) : undefined}
            />
          </Row>
        );
      })}
    </div>
  );
}
