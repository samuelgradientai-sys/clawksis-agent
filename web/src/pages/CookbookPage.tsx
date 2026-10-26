/**
 * Cookbook — local models. The machine's hardware, two local backends behind a common provider
 * architecture (clawk_cli/cookbook_providers): Ollama (pull with real progress + cancel) and
 * llama.cpp (GGUF from Hugging Face: live search, quant picker, resumable downloads, a managed
 * llama-server behind "Use"), a curated catalog with a per-model "does it fit?" verdict, live
 * search, the installed models across backends, and every transfer in flight.
 *
 * Data and actions live in hooks (useCookbookData / useCookbookTransfers / useCookbookSearch),
 * the pieces in components/cookbook/. Backed by /api/cookbook/* (web_routers/cookbook.py).
 */

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Segmented } from "@nous-research/ui/ui/components/segmented";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { usePageHeader } from "@/contexts/usePageHeader";
import { useCookbookData, type CookbookNotice } from "@/hooks/useCookbookData";
import { useCookbookSearch } from "@/hooks/useCookbookSearch";
import { useCookbookTransfers } from "@/hooks/useCookbookTransfers";
import {
  activeTransferCount,
  DEFAULT_FILTERS,
  isActiveDownload,
  type CookbookFilters,
  type DownloadProgress,
} from "@/lib/cookbook";
import { ollamaAvailable } from "@/lib/cookbook-ollama";
import { DownloadBar } from "@/components/cookbook/DownloadBar";
import { DownloadsList } from "@/components/cookbook/DownloadsList";
import { InstalledList } from "@/components/cookbook/InstalledList";
import { ModelsTab } from "@/components/cookbook/ModelsTab";
import { HardwareCard, LlamaCppCard, OllamaCard } from "@/components/cookbook/ProviderCards";
import { Panel } from "@/components/cookbook/CookbookUi";
import { PluginSlot } from "@/plugins";

type Tab = "models" | "installed" | "downloads";

// The backend choice (Ollama vs llama.cpp) is a preference: it survives reloads.
const SOURCE_KEY = "clawksis-cookbook-source";

function initialFilters(): CookbookFilters {
  try {
    const v = window.localStorage.getItem(SOURCE_KEY);
    return { ...DEFAULT_FILTERS, source: v === "ollama" || v === "gguf" ? v : "all" };
  } catch {
    return DEFAULT_FILTERS;
  }
}

function persistSource(source: CookbookFilters["source"]) {
  try {
    if (source === "all") window.localStorage.removeItem(SOURCE_KEY);
    else window.localStorage.setItem(SOURCE_KEY, source);
  } catch {
    /* no persistence available */
  }
}

const NOTICE_TONE: Record<CookbookNotice["tone"], string> = {
  info: "border-sky-500/30 text-foreground",
  success: "border-emerald-500/30 text-foreground",
  warning: "border-amber-500/40 text-amber-200",
  error: "border-rose-500/40 text-rose-200",
};

function NoticeBar({ notice, onClose }: { notice: CookbookNotice; onClose: () => void }) {
  return (
    <div role="status" className={`clawk-liquid-panel flex items-start gap-3 rounded-xl border px-4 py-3 text-sm ${NOTICE_TONE[notice.tone]}`}>
      <p className="min-w-0 flex-1 break-words">{notice.text}</p>
      <button type="button" onClick={onClose} aria-label="Dismiss" className="shrink-0 rounded-md p-0.5 text-muted-foreground hover:text-foreground">
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

function ActiveDownloads({ downloads, onCancel }: { downloads: Array<[string, DownloadProgress]>; onCancel: (id: string) => void }) {
  if (downloads.length === 0) return null;
  return (
    <Panel className="grid gap-3 border border-[rgb(var(--clawk-liquid-violet)/0.35)] p-3">
      {downloads.map(([id, d]) => (
        <DownloadBar
          key={id}
          label={`${d.file ?? "model"} · ${d.status === "downloading" ? "downloading" : `${d.status}…`}`}
          progress={d}
          onCancel={d.status === "downloading" ? () => onCancel(id) : undefined}
        />
      ))}
    </Panel>
  );
}

export default function CookbookPage() {
  const cb = useCookbookData();
  const { load, loadInstalled, setNotice } = cb;
  const [tab, setTab] = useState<Tab>("models");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<CookbookFilters>(initialFilters);
  const search = useCookbookSearch(query);
  const transfers = useCookbookTransfers(
    useCallback(
      (kind: "pull" | "download", p: DownloadProgress) => {
        if (kind === "download") {
          setNotice({ tone: "success", text: `${p.file ?? "Model"} downloaded and registered — use it from Installed.` });
        }
        void load();
        void loadInstalled();
      },
      [load, loadInstalled, setNotice],
    ),
  );
  const { reattach } = transfers;
  const { setEnd } = usePageHeader();

  useEffect(() => {
    const boot = setTimeout(() => {
      void load();
      void reattach();
    }, 0);
    return () => clearTimeout(boot);
  }, [load, reattach]);

  useEffect(() => {
    if (tab !== "installed") return;
    const t = setTimeout(() => void loadInstalled(), 0);
    return () => clearTimeout(t);
  }, [tab, loadInstalled]);

  const refresh = useCallback(() => {
    void load();
    void reattach();
    if (tab === "installed") void loadInstalled();
  }, [load, loadInstalled, reattach, tab]);

  useEffect(() => {
    setEnd(
      <Button ghost size="icon" type="button" onClick={refresh} disabled={cb.loading} aria-label="Refresh cookbook">
        {cb.loading ? <Spinner /> : <RefreshCw />}
      </Button>,
    );
    return () => setEnd(null);
  }, [cb.loading, refresh, setEnd]);

  const startDownload = async (repo: string, file: string) => {
    const err = await transfers.download(repo, file);
    if (err) setNotice({ tone: "error", text: `The download did not start: ${err}` });
  };

  const hw = cb.data?.hardware ?? {};
  const ollama = cb.data?.ollama ?? {};
  const llamaInstall = cb.installing.llamacpp ?? cb.llamacpp.install_status ?? "";
  const active = activeTransferCount(transfers.downloads, transfers.pulls);
  const downloadsList = Object.values(transfers.downloads);

  return (
    <div className="flex min-w-0 max-w-full flex-col gap-4">
      <PluginSlot name="cookbook:top" />
      <p className="max-w-3xl text-xs text-muted-foreground sm:text-sm">
        Open models you can run on this machine — with Ollama or llama.cpp — and use as the agent&apos;s model for the
        selected profile. Each model shows its context window, tool support, size and how it fits your hardware.
      </p>

      <div className="grid gap-2 sm:gap-3 md:grid-cols-3">
        <HardwareCard hw={hw} />
        <OllamaCard ollama={ollama} install={cb.installing.ollama ?? ""} onInstall={() => void cb.installProvider("ollama")} />
        <LlamaCppCard
          llamacpp={cb.llamacpp}
          install={llamaInstall}
          stopping={cb.busyModel === "llamacpp-server"}
          onInstall={() => void cb.installProvider("llamacpp")}
          onStop={() => void cb.stopServer()}
        />
      </div>

      <ActiveDownloads
        downloads={Object.entries(transfers.downloads).filter(([, d]) => isActiveDownload(d.status))}
        onCancel={transfers.cancelDownload}
      />
      {cb.notice && <NoticeBar notice={cb.notice} onClose={() => setNotice(null)} />}
      {cb.loadError && <NoticeBar notice={{ tone: "error", text: `Could not load the cookbook: ${cb.loadError}` }} onClose={refresh} />}

      <Segmented
        className="w-fit max-w-full"
        size="md"
        value={tab}
        onChange={(v) => setTab(v as Tab)}
        options={[
          { value: "models", label: "Models" },
          { value: "installed", label: "Installed" },
          { value: "downloads", label: active > 0 ? `Downloads (${active})` : "Downloads" },
        ]}
      />

      {tab === "models" && (
        <ModelsTab
          query={query}
          onQuery={setQuery}
          filters={filters}
          onFilters={(f) => {
            setFilters(f);
            persistSource(f.source);
          }}
          catalog={cb.data?.models ?? []}
          search={search}
          ollamaReady={ollamaAvailable(ollama)}
          llamaReady={!!cb.llamacpp.installed || llamaInstall === "done"}
          ramGb={hw.ram_gb ?? 0}
          diskFreeGb={hw.disk_free_gb ?? 0}
          pulls={transfers.pulls}
          downloads={downloadsList}
          busyModel={cb.busyModel}
          onPull={(tag) => void transfers.pull(tag)}
          onCancelPull={transfers.cancelPull}
          onUse={(m) => void cb.applyOllamaModel(m)}
          onDownload={(repo, file) => void startDownload(repo, file)}
        />
      )}
      {tab === "installed" && (
        <InstalledList
          models={cb.installed}
          loading={cb.installedLoading}
          actions={{
            busyModel: cb.busyModel,
            onUse: (m) => void cb.applyInstalledModel(m),
            onVerify: (m) => void cb.verifyInstalled(m),
            onRename: (m, name) => void cb.renameInstalled(m, name),
            onDelete: (m) => void cb.deleteInstalled(m),
          }}
        />
      )}
      {tab === "downloads" && (
        <DownloadsList
          downloads={transfers.downloads}
          pulls={transfers.pulls}
          interrupted={transfers.interrupted}
          onCancelDownload={transfers.cancelDownload}
          onCancelPull={transfers.cancelPull}
          onResume={(it) => void startDownload(it.repo, it.file)}
        />
      )}
      <PluginSlot name="cookbook:bottom" />
    </div>
  );
}
