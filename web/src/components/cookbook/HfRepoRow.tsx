import { ChevronDown, ChevronRight } from "lucide-react";
import {
  fmtBytes,
  fmtCtx,
  hfRepoFits,
  isActiveDownload,
  TIER_STYLE,
  type DownloadProgress,
  type HFFile,
  type HFRepo,
} from "@/lib/cookbook";
import { CbButton, Pill, Row } from "./CookbookUi";
import { ToolsPill } from "./ModelRow";

/** The quant files of an expanded repo: a loading line, an error, or the file list. */
export type RepoFiles = HFFile[] | "loading" | { error: string };

interface FileLineProps {
  file: HFFile;
  download?: DownloadProgress;
  ramGb: number;
  diskFreeGb: number;
  onDownload: () => void;
}

function FileAction({ file, download, ramGb, diskFreeGb, onDownload }: FileLineProps) {
  if (file.multipart) return <span className="text-[11px] text-muted-foreground">multi-part (unsupported)</span>;
  if (download?.status === "done") return <Pill kind="ok">ready ✓</Pill>;
  if (isActiveDownload(download?.status)) {
    return <Pill kind="info">{download?.percent != null ? `${download.percent.toFixed(0)}%` : "…"}</Pill>;
  }
  const sizeGb = file.size_bytes / 1024 ** 3;
  const noDisk = diskFreeGb > 0 && sizeGb > diskFreeGb;
  const tooBig = (ramGb > 0 && sizeGb > ramGb) || noDisk;
  const title = noDisk
    ? "Not enough free disk space for this file"
    : tooBig
      ? "Bigger than this machine's RAM — will likely not load"
      : "Download to the llama.cpp models folder";
  return (
    <CbButton tone={tooBig ? "danger" : "primary"} className="px-2.5 py-1" onClick={onDownload} title={title}>
      {download?.status === "cancelled" || download?.status === "error" ? "Retry" : "Download"}
    </CbButton>
  );
}

function FileLine(props: FileLineProps) {
  const { file, download } = props;
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 rounded-lg px-2 py-1.5 text-xs hover:bg-white/[0.04] sm:grid-cols-[6rem_5rem_1fr_auto]">
      <span className="font-mono font-medium">{file.quant || "?"}</span>
      <span className="text-right text-muted-foreground tabular-nums sm:text-left">{fmtBytes(file.size_bytes)}</span>
      <span className="col-span-2 min-w-0 truncate font-mono text-[11px] text-muted-foreground sm:col-span-1" title={file.file}>
        {file.file}
      </span>
      <span className="col-span-2 flex justify-end sm:col-span-1">
        <FileAction {...props} />
      </span>
      {download?.status === "error" && (
        <span className="col-span-2 text-[11px] text-rose-300 sm:col-span-4">{download.error || "download failed"}</span>
      )}
    </div>
  );
}

function RepoMeta({ repo }: { repo: HFRepo }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <Pill kind="llamacpp">llama.cpp</Pill>
      <ToolsPill toolUse={repo.tool_use} />
      {repo.context > 0 && (
        <Pill kind="info" title={`Context window: ${repo.context.toLocaleString()} tokens`}>
          ctx {fmtCtx(repo.context)}
        </Pill>
      )}
      {repo.gated && <Pill kind="warn">gated</Pill>}
      {repo.params_b > 0 && (
        <span>
          {repo.params_b}B · ~{repo.size_q4_gb} GB Q4
        </span>
      )}
      {repo.architecture && <span>{repo.architecture}</span>}
      <span>
        {repo.downloads.toLocaleString()} downloads · ♥ {repo.likes}
      </span>
      {repo.license && <span>{repo.license}</span>}
    </div>
  );
}

/** One Hugging Face GGUF repo (llama.cpp): what it brings, and its quant picker when expanded. */
export function HfRepoRow({
  repo,
  files,
  downloads,
  llamaReady,
  ramGb,
  diskFreeGb,
  onToggle,
  onDownload,
}: {
  repo: HFRepo;
  files?: RepoFiles;
  downloads: DownloadProgress[];
  llamaReady: boolean;
  ramGb: number;
  diskFreeGb: number;
  onToggle: () => void;
  onDownload: (file: string) => void;
}) {
  const expanded = files !== undefined;
  const fits = hfRepoFits(repo, ramGb);
  const tier = TIER_STYLE[repo.size_q4_gb > 0 ? (fits ? "good" : "no_fit") : "unknown"];
  return (
    <Row>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="min-w-0 break-all font-medium">{repo.name}</span>
            <span className="text-xs text-muted-foreground">by {repo.author}</span>
            <Pill className={tier.cls} title={repo.size_q4_gb > 0 ? `~${repo.size_q4_gb} GB in Q4 vs ${ramGb} GB RAM` : "Size unknown until you pick a version"}>
              {tier.label}
            </Pill>
          </div>
          <RepoMeta repo={repo} />
        </div>
        <div className="flex shrink-0 justify-end">
          <CbButton onClick={onToggle} disabled={!llamaReady} title={llamaReady ? "Pick a quantization" : "Install llama.cpp first"}>
            {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            Versions
          </CbButton>
        </div>
      </div>
      {expanded && (
        <div className="mt-3 grid gap-0.5 border-t border-white/[0.06] pt-2">
          {files === "loading" ? (
            <p className="px-2 py-1 text-xs text-muted-foreground">Fetching GGUF files…</p>
          ) : !Array.isArray(files) ? (
            <p className="px-2 py-1 text-xs text-rose-300">Could not list the files: {files.error}</p>
          ) : files.length === 0 ? (
            <p className="px-2 py-1 text-xs text-muted-foreground">No single-file GGUF in this repo.</p>
          ) : (
            files.map((f) => (
              <FileLine
                key={f.file}
                file={f}
                download={downloads.find((d) => d.repo === repo.repo && d.file === f.file)}
                ramGb={ramGb}
                diskFreeGb={diskFreeGb}
                onDownload={() => onDownload(f.file)}
              />
            ))
          )}
        </div>
      )}
    </Row>
  );
}
