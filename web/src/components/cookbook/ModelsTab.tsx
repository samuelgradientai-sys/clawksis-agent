import { useCallback, useState } from "react";
import { cookbookApi } from "@/lib/api-cookbook";
import { errorMessage } from "@/lib/api-error";
import {
  customPullTag,
  filtersActive,
  hfRepoVisible,
  isActivePull,
  mergeOllamaRows,
  ollamaModelVisible,
  type CookbookFilters,
  type CookbookModel,
  type DownloadProgress,
  type HFRepo,
  type TransferProgress,
} from "@/lib/cookbook";
import type { useCookbookSearch } from "@/hooks/useCookbookSearch";
import { CbButton, Row } from "./CookbookUi";
import { CookbookFilterChips, CookbookSearchBar } from "./CookbookFilters";
import { DownloadBar } from "./DownloadBar";
import { HfRepoRow, type RepoFiles } from "./HfRepoRow";
import { ModelRow } from "./ModelRow";

type Search = ReturnType<typeof useCookbookSearch>;

export interface ModelsTabProps {
  query: string;
  onQuery: (q: string) => void;
  filters: CookbookFilters;
  onFilters: (f: CookbookFilters) => void;
  catalog: CookbookModel[];
  search: Search;
  ollamaReady: boolean;
  llamaReady: boolean;
  ramGb: number;
  diskFreeGb: number;
  pulls: Record<string, TransferProgress>;
  downloads: DownloadProgress[];
  busyModel: string | null;
  onPull: (tag: string) => void;
  onCancelPull: (tag: string) => void;
  onUse: (m: CookbookModel) => void;
  onDownload: (repo: string, file: string) => void;
}

function SearchStatus({ search, query }: { search: Search; query: string }) {
  const lines: Array<{ text: string; error?: boolean }> = [];
  if (search.ollama.loading || search.hf.loading) lines.push({ text: "Searching the Ollama library and Hugging Face…" });
  if (search.ollama.error) lines.push({ text: `Ollama library unreachable — ${search.ollama.error}`, error: true });
  if (search.hf.error) lines.push({ text: `Hugging Face unreachable — ${search.hf.error}`, error: true });
  if (search.libraryError) lines.push({ text: `Could not load the full Ollama library — ${search.libraryError}`, error: true });
  if (!query && search.browseAll && search.library) {
    lines.push({ text: `Full Ollama library: ${search.library.length} entries. Search to narrow it down.` });
  }
  if (lines.length === 0) return null;
  return (
    <div className="grid gap-1 text-xs" role="status">
      {lines.map((l) => (
        <p key={l.text} className={l.error ? "text-amber-300" : "text-muted-foreground"}>
          {l.text}
        </p>
      ))}
    </div>
  );
}

function CustomPull({ tag, pull, onPull, onCancel }: { tag: string; pull?: TransferProgress; onPull: () => void; onCancel: () => void }) {
  return (
    <Row className="flex flex-col gap-2 border-dashed border-[rgb(var(--clawk-liquid-violet)/0.4)] sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          Download any model: <span className="break-all font-mono text-xs text-muted-foreground">{tag}</span>
        </p>
        <p className="text-xs text-muted-foreground">Not listed? Pull this exact tag from the Ollama library.</p>
        {pull?.status === "pulling" && (
          <div className="mt-2 max-w-md">
            <DownloadBar label="Downloading" progress={pull} onCancel={onCancel} />
          </div>
        )}
        {pull?.status.startsWith("error") && <p className="mt-1 text-xs text-rose-300">{pull.status.replace(/^error:\s*/, "")}</p>}
      </div>
      {!isActivePull(pull?.status) && (
        <CbButton tone="primary" onClick={onPull}>
          {pull?.status === "done" ? "Downloaded ✓" : `Pull “${tag}”`}
        </CbButton>
      )}
    </Row>
  );
}

/** The Models tab: live search, filters, Ollama models, Hugging Face GGUF repos. */
export function ModelsTab(props: ModelsTabProps) {
  const { query, filters, search, ramGb } = props;
  const [repoFiles, setRepoFiles] = useState<Record<string, RepoFiles>>({});

  const toggleRepo = useCallback(
    (repo: string, open: boolean) => {
      if (open) {
        setRepoFiles((prev) => {
          const next = { ...prev };
          delete next[repo];
          return next;
        });
        return;
      }
      setRepoFiles((prev) => ({ ...prev, [repo]: "loading" }));
      cookbookApi
      .hfFiles(repo)
      .then((res) => setRepoFiles((prev) => ({ ...prev, [repo]: res.error ? { error: res.error } : (res.files ?? []) })))
        .catch((e) => setRepoFiles((prev) => ({ ...prev, [repo]: { error: errorMessage(e) } })));
    },
    [],
  );

  const base = search.browseAll && search.library ? search.library : props.catalog;
  const ollamaRows = mergeOllamaRows(base, search.ollama.rows, query);
  const visibleModels = ollamaRows.filter((m) => ollamaModelVisible(m, filters));
  const hfRows: HFRepo[] = query.trim() ? search.hf.rows : [];
  const visibleHf = hfRows.filter((r) => hfRepoVisible(r, filters, ramGb));
  const hidden = filtersActive(filters) ? ollamaRows.length - visibleModels.length + hfRows.length - visibleHf.length : 0;
  const custom = props.ollamaReady ? customPullTag(query, props.catalog) : null;
  const searching = search.ollama.loading || search.hf.loading;

  return (
    <div className="grid gap-3">
      <CookbookSearchBar
        query={query}
        onQuery={props.onQuery}
        aside={
          search.browseAll ? (
            <CbButton onClick={() => search.setBrowseAll(false)}>Show curated</CbButton>
          ) : (
            <CbButton tone="primary" onClick={() => void search.loadLibrary()} disabled={search.libraryLoading}>
              {search.libraryLoading ? "Loading…" : "Browse all Ollama"}
            </CbButton>
          )
        }
      />
      <CookbookFilterChips filters={filters} onChange={props.onFilters} hiddenCount={hidden} />
      <SearchStatus search={search} query={query} />

      {custom && (
        <CustomPull tag={custom} pull={props.pulls[custom]} onPull={() => props.onPull(custom)} onCancel={() => props.onCancelPull(custom)} />
      )}
      {filters.source === "gguf" && !query.trim() && (
        <Row className="border-dashed text-sm text-muted-foreground">
          llama.cpp models come from a live Hugging Face search — type a name above (e.g. <span className="font-mono">qwen</span>,{" "}
          <span className="font-mono">gemma</span>). Installed ones are in the Installed tab.
        </Row>
      )}
      {query.trim() && !searching && !custom && visibleModels.length === 0 && visibleHf.length === 0 && !search.ollama.error && !search.hf.error && (
        <p className="text-sm text-muted-foreground">No models match “{query}”.</p>
      )}

      <div className="grid gap-2">
        {visibleModels.map((m) => (
          <ModelRow
            key={m.id}
            model={m}
            pull={props.pulls[m.ollama]}
            ollamaReady={props.ollamaReady}
            busy={props.busyModel === m.id}
            onPull={() => props.onPull(m.ollama)}
            onCancel={() => props.onCancelPull(m.ollama)}
            onUse={() => props.onUse(m)}
          />
        ))}
      </div>

      {visibleHf.length > 0 && (
        <div className="grid gap-2">
          <h3 className="mt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Hugging Face — GGUF for llama.cpp</h3>
          {visibleHf.map((r) => (
            <HfRepoRow
              key={r.repo}
              repo={r}
              files={repoFiles[r.repo]}
              downloads={props.downloads}
              llamaReady={props.llamaReady}
              ramGb={ramGb}
              diskFreeGb={props.diskFreeGb}
              onToggle={() => toggleRepo(r.repo, repoFiles[r.repo] !== undefined)}
              onDownload={(file) => props.onDownload(r.repo, file)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
