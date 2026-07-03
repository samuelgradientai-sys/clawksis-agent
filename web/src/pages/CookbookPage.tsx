/**
 * Cookbook — local models. Shows the user's hardware, a curated catalog of open
 * LLMs with a per-model "does it fit?" verdict, and TWO fully-supported local
 * backends behind a common provider architecture (clawk_cli/cookbook_providers):
 *
 *   - Ollama    — pull with real progress (streaming /api/pull) + cancel.
 *   - llama.cpp — GGUF models from Hugging Face: live search, quant picker,
 *     download with %/speed/ETA/cancel/resume, instant registration, and a
 *     managed llama-server (OpenAI-compatible) behind "Use".
 *
 * Search is LIVE (like Docker Hub / HF): nothing huge is preloaded — typing
 * queries ollama.com and huggingface.co on the fly, with visible status lines.
 * The "Installed" tab manages models across providers (size, path, verify,
 * rename, delete). Backed by /api/cookbook/* (clawk_cli/web_server.py).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchJSON } from "@/lib/api";

interface Fit {
  mode: "gpu" | "cpu" | "none" | "unknown";
  tier: "perfect" | "good" | "marginal" | "no_fit" | "unknown";
  reason: string;
}

interface CookbookModel {
  id: string;
  name: string;
  family: string;
  params_b: number;
  ollama: string;
  quant: string;
  size_gb: number;
  min_vram_gb: number;
  min_ram_gb: number;
  context: number;
  tool_use: boolean;
  use_case: string;
  fit: Fit;
  installed: boolean;
}

interface Hardware {
  ram_gb?: number;
  cpu_cores?: number;
  gpu_name?: string;
  vram_gb?: number;
  platform?: string;
  arch?: string;
}

interface OllamaStatus {
  installed?: boolean;
  running?: boolean;
  models?: string[];
  base_url?: string;
}

interface LlamaCppStatus {
  installed?: boolean;
  install_status?: string;
  server?: { running?: boolean; model_file?: string; base_url?: string };
  models_dir?: string;
  models?: InstalledModel[];
}

interface CatalogResponse {
  hardware: Hardware;
  ollama: OllamaStatus;
  models: CookbookModel[];
}

interface HFRepo {
  repo: string;
  author: string;
  name: string;
  downloads: number;
  likes: number;
  updated_at: string;
  license: string;
  gated: boolean;
  tags: string[];
}

interface HFFile {
  file: string;
  size_bytes: number;
  quant: string;
  multipart: boolean;
}

interface DownloadProgress {
  status: string;
  repo?: string;
  file?: string;
  downloaded?: number;
  total?: number;
  percent?: number | null;
  speed_bps?: number;
  eta_seconds?: number | null;
  error?: string;
  model_id?: string;
}

interface PullProgress {
  status: string;
  phase?: string;
  downloaded?: number;
  total?: number;
  percent?: number | null;
  speed_bps?: number;
  eta_seconds?: number | null;
}

interface InstalledModel {
  id: string;
  name: string;
  provider: string;
  size_bytes?: number;
  path?: string;
  quant?: string;
  repo?: string;
  file?: string;
}

const TIER_STYLE: Record<Fit["tier"], { label: string; cls: string }> = {
  perfect: { label: "Fits great", cls: "border-emerald-500/60 text-emerald-400" },
  good: { label: "Fits", cls: "border-emerald-500/50 text-emerald-400" },
  marginal: { label: "Tight / slow", cls: "border-amber-500/60 text-amber-400" },
  no_fit: { label: "Too big", cls: "border-rose-500/50 text-rose-400" },
  unknown: { label: "Size unknown", cls: "border-neutral-500/50 text-neutral-400" },
};

function fmtBytes(n?: number | null): string {
  if (!n || n <= 0) return "—";
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`;
  const mb = n / 1024 ** 2;
  return `${mb.toFixed(0)} MB`;
}

function fmtSpeed(bps?: number): string {
  if (!bps || bps <= 0) return "";
  return `${fmtBytes(bps)}/s`;
}

function fmtEta(s?: number | null): string {
  if (s == null || s <= 0) return "";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Barra de progreso de descarga — %, bytes, velocidad, ETA y Cancelar. */
function DownloadBar({
  label,
  progress,
  onCancel,
}: {
  label: string;
  progress: { percent?: number | null; downloaded?: number; total?: number; speed_bps?: number; eta_seconds?: number | null; status?: string; phase?: string };
  onCancel?: () => void;
}) {
  const pct = progress.percent ?? null;
  return (
    <div className="w-full min-w-0">
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="min-w-0 truncate">
          {label}
          {progress.phase ? ` · ${progress.phase}` : ""}
        </span>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="shrink-0 rounded border border-border px-1.5 py-0.5 text-2xs hover:text-rose-400"
          >
            Cancel
          </button>
        )}
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded bg-border/40">
        <div
          className={`h-full rounded bg-[var(--color-primary)] transition-all ${pct == null ? "w-1/3 animate-pulse" : ""}`}
          style={pct != null ? { width: `${Math.max(2, pct)}%` } : undefined}
        />
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 text-2xs text-muted-foreground">
        {pct != null && <span>{pct.toFixed(0)}%</span>}
        {!!progress.total && (
          <span>
            {fmtBytes(progress.downloaded)} / {fmtBytes(progress.total)}
          </span>
        )}
        {!!progress.speed_bps && <span>{fmtSpeed(progress.speed_bps)}</span>}
        {progress.eta_seconds != null && progress.eta_seconds > 0 && (
          <span>ETA: {fmtEta(progress.eta_seconds)}</span>
        )}
      </div>
    </div>
  );
}

export default function CookbookPage() {
  const [data, setData] = useState<CatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // tag -> progreso del pull de Ollama (status + bytes/%, velocidad, ETA).
  const [pulling, setPulling] = useState<Record<string, PullProgress>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  // Live results from the FULL Ollama library (scraped) for the current query.
  const [remoteRows, setRemoteRows] = useState<CookbookModel[]>([]);
  const [remoteLoading, setRemoteLoading] = useState(false);
  // Live results from Hugging Face (GGUF, llama.cpp) for the current query.
  const [hfRows, setHfRows] = useState<HFRepo[]>([]);
  const [hfLoading, setHfLoading] = useState(false);
  // repo -> quant files (expanded picker)
  const [hfFiles, setHfFiles] = useState<Record<string, HFFile[] | "loading">>({});
  // download_id -> progress (GGUF downloads in flight)
  const [downloads, setDownloads] = useState<Record<string, DownloadProgress>>({});
  // "Browse all" loads the entire Ollama library (hundreds of models).
  const [browseAll, setBrowseAll] = useState(false);
  const [libraryRows, setLibraryRows] = useState<CookbookModel[] | null>(null);
  const [libraryLoading, setLibraryLoading] = useState(false);
  // provider -> "" | "installing" | "done" | "error: ..."
  const [installing, setInstalling] = useState<Record<string, string>>({});
  const [llamacpp, setLlamacpp] = useState<LlamaCppStatus>({});
  // Tab: buscar/catálogo vs instalados.
  const [tab, setTab] = useState<"models" | "installed">("models");
  const [installed, setInstalled] = useState<InstalledModel[]>([]);
  const [installedLoading, setInstalledLoading] = useState(false);
  const [busyModel, setBusyModel] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<{ id: string; value: string } | null>(null);
  const pollTimers = useRef<Record<string, ReturnType<typeof setInterval>>>({});

  const load = useCallback(async () => {
    try {
      const res = await fetchJSON<CatalogResponse>("/api/cookbook/catalog");
      setData(res);
      setError(null);
    } catch {
      setError("Could not load the cookbook.");
    } finally {
      setLoading(false);
    }
    try {
      const prov = await fetchJSON<{ llamacpp?: LlamaCppStatus }>(
        "/api/cookbook/providers",
      );
      setLlamacpp(prov.llamacpp ?? {});
    } catch {
      /* provider status es opcional para render */
    }
  }, []);

  const loadInstalled = useCallback(async () => {
    setInstalledLoading(true);
    try {
      const res = await fetchJSON<{ models: InstalledModel[] }>(
        "/api/cookbook/installed",
      );
      setInstalled(res.models ?? []);
    } catch {
      setInstalled([]);
    } finally {
      setInstalledLoading(false);
    }
  }, []);

  useEffect(() => {
    const boot = setTimeout(() => void load(), 0);
    const timers = pollTimers.current;
    return () => {
      clearTimeout(boot);
      for (const t of Object.values(timers)) clearInterval(t);
    };
  }, [load]);

  useEffect(() => {
    if (tab !== "installed") return;
    const t = setTimeout(() => void loadInstalled(), 0);
    return () => clearTimeout(t);
  }, [tab, loadInstalled]);

  // Live search de la librería de Ollama (debounced). Los setState van dentro
  // del timeout — nunca sincrónicos en el cuerpo del efecto (regla compiler).
  useEffect(() => {
    const term = query.trim();
    const handle = setTimeout(
      () => {
        if (!term) {
          setRemoteRows([]);
          setRemoteLoading(false);
          return;
        }
        setRemoteLoading(true);
        void (async () => {
          try {
            const res = await fetchJSON<{ models: CookbookModel[] }>(
              `/api/cookbook/search?q=${encodeURIComponent(term)}`,
            );
            setRemoteRows(res.models ?? []);
          } catch {
            setRemoteRows([]);
          } finally {
            setRemoteLoading(false);
          }
        })();
      },
      term ? 450 : 0,
    );
    return () => clearTimeout(handle);
  }, [query]);

  // Live search de Hugging Face (GGUF para llama.cpp), en paralelo.
  useEffect(() => {
    const term = query.trim();
    const active = term.length >= 2;
    const handle = setTimeout(
      () => {
        if (!active) {
          setHfRows([]);
          setHfLoading(false);
          return;
        }
        setHfLoading(true);
        void (async () => {
          try {
            const res = await fetchJSON<{ models: HFRepo[] }>(
              `/api/cookbook/hf-search?q=${encodeURIComponent(term)}`,
            );
            setHfRows(res.models ?? []);
          } catch {
            setHfRows([]);
          } finally {
            setHfLoading(false);
          }
        })();
      },
      active ? 450 : 0,
    );
    return () => clearTimeout(handle);
  }, [query]);

  const loadLibrary = useCallback(async () => {
    if (libraryRows) {
      setBrowseAll(true);
      return;
    }
    setLibraryLoading(true);
    try {
      const res = await fetchJSON<CatalogResponse>("/api/cookbook/library");
      setLibraryRows(res.models ?? []);
      setBrowseAll(true);
    } catch {
      setNotice("Could not load the Ollama library (no internet?).");
    } finally {
      setLibraryLoading(false);
    }
  }, [libraryRows]);

  // Instalar un backend (ollama / llamacpp) en el host donde corre clawk.
  const onInstallProvider = useCallback(
    async (provider: string) => {
      setNotice(null);
      setInstalling((prev) => ({ ...prev, [provider]: "installing" }));
      try {
        const res = await fetchJSON<{ ok: boolean; status?: string; error?: string }>(
          "/api/cookbook/provider-install",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ provider }),
          },
        );
        if (!res.ok) {
          setInstalling((prev) => ({
            ...prev,
            [provider]: `error: ${res.error ?? "failed"}`,
          }));
          return;
        }
        if (res.status === "done") {
          setInstalling((prev) => ({ ...prev, [provider]: "done" }));
          void load();
          return;
        }
        const timer = setInterval(() => {
          void (async () => {
            try {
              const s = await fetchJSON<{ status: string }>(
                `/api/cookbook/provider-install-status?provider=${provider}`,
              );
              setInstalling((prev) => ({ ...prev, [provider]: s.status }));
              if (s.status === "done" || s.status.startsWith("error")) {
                clearInterval(timer);
                if (s.status === "done") void load();
              }
            } catch {
              // transient — keep polling
            }
          })();
        }, 3000);
      } catch {
        setInstalling((prev) => ({ ...prev, [provider]: "error: request failed" }));
      }
    },
    [load],
  );

  const pollPull = useCallback(
    (tag: string) => {
      if (pollTimers.current[`pull:${tag}`]) return;
      pollTimers.current[`pull:${tag}`] = setInterval(() => {
        void (async () => {
          try {
            const res = await fetchJSON<PullProgress>(
              `/api/cookbook/pull-status?tag=${encodeURIComponent(tag)}`,
            );
            setPulling((prev) => ({ ...prev, [tag]: res }));
            if (
              res.status === "done" ||
              res.status === "cancelled" ||
              res.status.startsWith("error")
            ) {
              clearInterval(pollTimers.current[`pull:${tag}`]);
              delete pollTimers.current[`pull:${tag}`];
              if (res.status === "done") void load(); // refresh installed flags
            }
          } catch {
            // keep polling; transient
          }
        })();
      }, 1500);
    },
    [load],
  );

  const onPull = useCallback(
    async (tag: string) => {
      setNotice(null);
      setPulling((prev) => ({ ...prev, [tag]: { status: "pulling" } }));
      try {
        const res = await fetchJSON<{ ok: boolean; error?: string }>(
          "/api/cookbook/pull",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tag }),
          },
        );
        if (!res.ok) {
          setPulling((prev) => ({
            ...prev,
            [tag]: { status: `error: ${res.error ?? "failed"}` },
          }));
          return;
        }
        pollPull(tag);
      } catch {
        setPulling((prev) => ({ ...prev, [tag]: { status: "error: request failed" } }));
      }
    },
    [pollPull],
  );

  const onCancelPull = useCallback(async (tag: string) => {
    try {
      await fetchJSON("/api/cookbook/pull-cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag }),
      });
    } catch {
      /* el poll refleja el estado final */
    }
  }, []);

  // ── GGUF (llama.cpp): quant picker + descarga con progreso ────────────────

  const onExpandRepo = useCallback(async (repo: string) => {
    setHfFiles((prev) => {
      if (prev[repo]) return prev; // ya cargado o cargando
      return { ...prev, [repo]: "loading" };
    });
    try {
      const res = await fetchJSON<{ files: HFFile[] }>(
        `/api/cookbook/hf-files?repo=${encodeURIComponent(repo)}`,
      );
      setHfFiles((prev) => ({ ...prev, [repo]: res.files ?? [] }));
    } catch {
      setHfFiles((prev) => ({ ...prev, [repo]: [] }));
    }
  }, []);

  const pollDownload = useCallback(
    (id: string) => {
      if (pollTimers.current[`dl:${id}`]) return;
      pollTimers.current[`dl:${id}`] = setInterval(() => {
        void (async () => {
          try {
            const res = await fetchJSON<DownloadProgress>(
              `/api/cookbook/download-status?id=${encodeURIComponent(id)}`,
            );
            setDownloads((prev) => ({ ...prev, [id]: res }));
            if (
              res.status === "done" ||
              res.status === "cancelled" ||
              res.status === "error"
            ) {
              clearInterval(pollTimers.current[`dl:${id}`]);
              delete pollTimers.current[`dl:${id}`];
              if (res.status === "done") {
                setNotice(
                  `Model ready: ${res.file ?? ""} — registered and usable right now (see Installed).`,
                );
                void load();
                void loadInstalled();
              }
            }
          } catch {
            // transient
          }
        })();
      }, 1000);
    },
    [load, loadInstalled],
  );

  const onDownload = useCallback(
    async (repo: string, file: string) => {
      setNotice(null);
      try {
        const res = await fetchJSON<{ ok: boolean; download_id?: string; error?: string }>(
          "/api/cookbook/download",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ repo, file }),
          },
        );
        if (res.ok && res.download_id) {
          setDownloads((prev) => ({
            ...prev,
            [res.download_id!]: { status: "downloading", repo, file },
          }));
          pollDownload(res.download_id);
        }
      } catch (e) {
        setNotice(`Download failed to start: ${e instanceof Error ? e.message : e}`);
      }
    },
    [pollDownload],
  );

  const onCancelDownload = useCallback(async (id: string) => {
    try {
      await fetchJSON("/api/cookbook/download-cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
    } catch {
      /* el poll refleja el estado */
    }
  }, []);

  // ── use / manage ───────────────────────────────────────────────────────────

  const onUseOllama = useCallback(async (model: CookbookModel) => {
    setNotice(null);
    try {
      const res = await fetchJSON<{ ok: boolean; model?: string; error?: string }>(
        "/api/cookbook/use",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tag: model.ollama }),
        },
      );
      if (res.ok) {
        setNotice(
          model.tool_use
            ? `Agent model set to ${model.name} (${model.ollama}) via local Ollama.`
            : `⚠ Set to ${model.name} (${model.ollama}), but this model does NOT support tools — the agent will error the moment it needs one (e.g. delegating a subagent). Pick a model marked "tools ✓".`,
        );
      } else {
        setNotice(`Could not switch model: ${res.error ?? "failed"}`);
      }
    } catch {
      setNotice("Could not switch model.");
    }
  }, []);

  const onUseInstalled = useCallback(
    async (m: InstalledModel) => {
      setNotice(null);
      setBusyModel(m.id);
      if (m.provider === "llamacpp") {
        setNotice("Starting llama-server with this model… (first load can take a bit)");
      }
      try {
        const res = await fetchJSON<{ ok: boolean; model?: string; error?: string }>(
          "/api/cookbook/model-use",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ provider: m.provider, id: m.id }),
          },
        );
        setNotice(
          res.ok
            ? `Agent model set to ${res.model ?? m.name} (${m.provider === "llamacpp" ? "llama.cpp server" : "Ollama"}). Applies everywhere the agent model is used: chat, agents, skills, workflows.`
            : `Could not switch model: ${res.error ?? "failed"}`,
        );
        if (res.ok) void load();
      } catch (e) {
        setNotice(`Could not switch model: ${e instanceof Error ? e.message : e}`);
      } finally {
        setBusyModel(null);
      }
    },
    [load],
  );

  const onDeleteInstalled = useCallback(
    async (m: InstalledModel) => {
      if (!window.confirm(`Delete ${m.name}? The file is removed from disk.`)) return;
      setBusyModel(m.id);
      try {
        await fetchJSON("/api/cookbook/model-delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ provider: m.provider, id: m.id }),
        });
        void loadInstalled();
        void load();
      } catch (e) {
        setNotice(`Delete failed: ${e instanceof Error ? e.message : e}`);
      } finally {
        setBusyModel(null);
      }
    },
    [load, loadInstalled],
  );

  const onVerifyInstalled = useCallback(async (m: InstalledModel) => {
    setBusyModel(m.id);
    try {
      const res = await fetchJSON<{ ok: boolean; error?: string; size_bytes?: number }>(
        "/api/cookbook/model-verify",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: m.id }),
        },
      );
      setNotice(
        res.ok
          ? `✓ ${m.name}: file intact (${fmtBytes(res.size_bytes)}).`
          : `✗ ${m.name}: ${res.error ?? "verification failed"}`,
      );
    } catch (e) {
      setNotice(`Verify failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusyModel(null);
    }
  }, []);

  const onRenameSubmit = useCallback(async () => {
    if (!renaming) return;
    const { id, value } = renaming;
    setRenaming(null);
    if (!value.trim()) return;
    try {
      await fetchJSON("/api/cookbook/model-rename", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, name: value.trim() }),
      });
      void loadInstalled();
    } catch (e) {
      setNotice(`Rename failed: ${e instanceof Error ? e.message : e}`);
    }
  }, [renaming, loadInstalled]);

  const onStopServer = useCallback(async () => {
    try {
      await fetchJSON("/api/cookbook/llamacpp-stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      void load();
    } catch {
      /* refresh igual */
    }
  }, [load]);

  const hw = data?.hardware ?? {};
  const ollama = data?.ollama ?? {};
  const models = data?.models ?? [];

  const q = query.trim().toLowerCase();
  const base = browseAll && libraryRows ? libraryRows : models;
  const localFiltered = q
    ? base.filter((m) =>
        `${m.name} ${m.family} ${m.ollama} ${m.use_case}`.toLowerCase().includes(q),
      )
    : base;
  const localTags = new Set(localFiltered.map((m) => m.ollama));
  const filtered = q
    ? [...localFiltered, ...remoteRows.filter((m) => !localTags.has(m.ollama))]
    : localFiltered;
  const looksLikeTag = /^[a-z0-9][a-z0-9._/-]*(:[a-z0-9._-]+)?$/i.test(query.trim());
  const tagKnown = models.some((m) => m.ollama.toLowerCase() === q);
  const customTag = query.trim();
  const showCustomPull = !!q && looksLikeTag && !tagKnown && !!ollama.installed;
  const customPull = pulling[customTag];

  const llamaInstall = installing["llamacpp"] ?? llamacpp.install_status ?? "";
  const ollamaInstall = installing["ollama"] ?? "";
  const activeDownloads = Object.entries(downloads).filter(
    ([, d]) => d.status === "downloading" || d.status === "verifying" || d.status === "registering",
  );
  const ramGb = hw.ram_gb ?? 0;

  const searchingAny = remoteLoading || hfLoading;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Cookbook — local models</h1>
          <p className="text-sm text-muted-foreground">
            Open LLMs you can run on this machine — via Ollama or llama.cpp — and
            use as the agent&apos;s model.
          </p>
          <p className="mt-0.5 text-xs text-amber-400/90">
            The agent uses tools — pick a model marked “tools ✓”. “no tools”
            models error the moment the agent calls a tool (e.g. delegating).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-border p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setTab("models")}
              className={`rounded px-2.5 py-1 ${tab === "models" ? "bg-[var(--color-primary)]/20 text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >
              Models
            </button>
            <button
              type="button"
              onClick={() => setTab("installed")}
              className={`rounded px-2.5 py-1 ${tab === "installed" ? "bg-[var(--color-primary)]/20 text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >
              Installed
            </button>
          </div>
          <button
            type="button"
            onClick={() => {
              void load();
              if (tab === "installed") void loadInstalled();
            }}
            className="rounded-md border border-border bg-card/40 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            Refresh
          </button>
        </div>
      </header>

      {/* Hardware + backends */}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg border border-border bg-card/40 p-3 text-sm">
          <div className="mb-1 font-medium">Your hardware</div>
          <div className="text-muted-foreground">
            {hw.ram_gb ?? "?"}GB RAM · {hw.cpu_cores ?? "?"} cores ·{" "}
            {hw.gpu_name ? `${hw.gpu_name} (${hw.vram_gb ?? 0}GB VRAM)` : "no discrete GPU"}
            {hw.platform ? ` · ${hw.platform}` : ""}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card/40 p-3 text-sm">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-medium">Ollama</span>
            {!ollama.installed &&
              ollamaInstall !== "done" &&
              (ollamaInstall === "installing" ? (
                <span className="text-xs text-muted-foreground">installing…</span>
              ) : (
                <button
                  type="button"
                  onClick={() => void onInstallProvider("ollama")}
                  className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)]/15 px-2 py-0.5 text-xs"
                >
                  Install
                </button>
              ))}
          </div>
          <div className="text-muted-foreground">
            {ollama.installed
              ? ollama.running
                ? `Running · ${String(ollama.models?.length ?? 0)} model(s) pulled`
                : "Installed — starts automatically when you pull a model."
              : ollamaInstall.startsWith("error")
                ? ollamaInstall
                : ollamaInstall === "installing"
                  ? "Installing on this machine…"
                  : "Not installed."}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card/40 p-3 text-sm">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-medium">llama.cpp</span>
            {!llamacpp.installed &&
              llamaInstall !== "done" &&
              (llamaInstall === "installing" ? (
                <span className="text-xs text-muted-foreground">installing…</span>
              ) : (
                <button
                  type="button"
                  onClick={() => void onInstallProvider("llamacpp")}
                  className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)]/15 px-2 py-0.5 text-xs"
                >
                  Install
                </button>
              ))}
          </div>
          <div className="text-muted-foreground">
            {llamacpp.installed
              ? llamacpp.server?.running
                ? `Serving ${llamacpp.server.model_file || "a model"} · ${String(llamacpp.models?.length ?? 0)} GGUF installed`
                : `Installed · ${String(llamacpp.models?.length ?? 0)} GGUF model(s)`
              : llamaInstall.startsWith("error")
                ? llamaInstall
                : llamaInstall === "installing"
                  ? "Downloading the prebuilt llama.cpp release…"
                  : "Not installed. GGUF models from Hugging Face run here."}
          </div>
          {llamacpp.server?.running && (
            <button
              type="button"
              onClick={() => void onStopServer()}
              className="mt-1 rounded border border-border px-2 py-0.5 text-2xs text-muted-foreground hover:text-rose-400"
            >
              Stop server (free RAM)
            </button>
          )}
        </div>
      </div>

      {/* Descargas GGUF en curso — visibles siempre, nunca parece congelado. */}
      {activeDownloads.length > 0 && (
        <div className="grid gap-2 rounded-lg border border-[var(--color-primary)]/40 bg-[var(--color-primary)]/5 p-3">
          {activeDownloads.map(([id, d]) => (
            <DownloadBar
              key={id}
              label={`${d.file ?? "model"} ${d.status === "verifying" ? "· Verifying…" : d.status === "registering" ? "· Registering…" : "· Downloading…"}`}
              progress={d}
              onCancel={
                d.status === "downloading" ? () => void onCancelDownload(id) : undefined
              }
            />
          ))}
        </div>
      )}

      {notice && (
        <div className="rounded-md border border-[var(--color-primary)]/50 bg-[var(--color-primary)]/10 px-3 py-2 text-sm">
          {notice}
        </div>
      )}

      {tab === "installed" ? (
        /* ── Installed: gestión unificada de modelos de todos los providers ── */
        <div className="grid gap-2">
          {installedLoading ? (
            <div className="text-sm text-muted-foreground">Loading installed models…</div>
          ) : installed.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No local models installed yet. Search and install one from the Models tab.
            </div>
          ) : (
            installed.map((m) => (
              <div
                key={`${m.provider}:${m.id}`}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card/30 px-3 py-2"
              >
                <span
                  className={`shrink-0 rounded border px-2 py-0.5 text-xs ${m.provider === "llamacpp" ? "border-sky-500/50 text-sky-400" : "border-emerald-500/50 text-emerald-400"}`}
                >
                  {m.provider === "llamacpp" ? "llama.cpp" : "Ollama"}
                </span>
                <div className="min-w-0 flex-1">
                  {renaming?.id === m.id ? (
                    <input
                      autoFocus
                      value={renaming.value}
                      onChange={(e) => setRenaming({ id: m.id, value: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") void onRenameSubmit();
                        if (e.key === "Escape") setRenaming(null);
                      }}
                      onBlur={() => void onRenameSubmit()}
                      className="w-64 rounded border border-[var(--color-primary)] bg-card px-2 py-0.5 text-sm outline-none"
                    />
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{m.name}</span>
                      {m.quant && (
                        <span className="rounded bg-border/40 px-1.5 text-2xs">{m.quant}</span>
                      )}
                    </div>
                  )}
                  <div className="truncate text-xs text-muted-foreground">
                    {fmtBytes(m.size_bytes)}
                    {m.repo ? ` · ${m.repo}` : ""}
                    {m.path ? ` · ${m.path}` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="button"
                    disabled={busyModel === m.id}
                    onClick={() => void onUseInstalled(m)}
                    className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)]/15 px-3 py-1 text-xs disabled:opacity-50"
                  >
                    {busyModel === m.id ? "…" : "Use"}
                  </button>
                  {m.provider === "llamacpp" && (
                    <>
                      <button
                        type="button"
                        onClick={() => void onVerifyInstalled(m)}
                        className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                        title="Check file integrity (size + GGUF magic)"
                      >
                        Verify
                      </button>
                      <button
                        type="button"
                        onClick={() => setRenaming({ id: m.id, value: m.name })}
                        className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
                      >
                        Rename
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    disabled={busyModel === m.id}
                    onClick={() => void onDeleteInstalled(m)}
                    className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:text-rose-400 disabled:opacity-50"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      ) : (
        <>
          {/* Search — catálogo curado + Ollama library + Hugging Face GGUF */}
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search models live: Ollama library + Hugging Face GGUF (qwen, llama, gemma…)"
              className="w-full rounded-md border border-border bg-card/40 px-3 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus:border-[var(--color-primary)]"
            />
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="shrink-0 rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                Clear
              </button>
            ) : browseAll ? (
              <button
                type="button"
                onClick={() => setBrowseAll(false)}
                className="shrink-0 rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                Show curated
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void loadLibrary()}
                disabled={libraryLoading}
                className="shrink-0 whitespace-nowrap rounded-md border border-[var(--color-primary)]/60 px-2 py-1.5 text-xs text-[var(--color-primary)] hover:bg-[var(--color-primary)]/10 disabled:opacity-50"
              >
                {libraryLoading ? "Loading…" : "Browse all Ollama"}
              </button>
            )}
          </div>
          {(searchingAny || (browseAll && !!libraryRows)) && (
            <div className="text-xs text-muted-foreground">
              {searchingAny ? (
                <span className="inline-flex items-center gap-2">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-[var(--color-primary)]" />
                  {remoteLoading && hfLoading
                    ? "Searching models… consulting the Ollama library and Hugging Face…"
                    : remoteLoading
                      ? "Searching the Ollama library…"
                      : "Consulting Hugging Face… fetching GGUF repositories…"}
                </span>
              ) : (
                `Showing the full Ollama library (${String(libraryRows?.length ?? 0)} entries). Use search to narrow it down.`
              )}
            </div>
          )}

          {loading ? (
            <div className="text-sm text-muted-foreground">Detecting hardware…</div>
          ) : error ? (
            <div className="text-sm text-rose-400">{error}</div>
          ) : (
            <div className="grid gap-2">
              {/* Pull any tag from the Ollama library, even if not in our catalog. */}
              {showCustomPull && (
                <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-[var(--color-primary)]/50 bg-[var(--color-primary)]/5 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">Run any model</span>
                      <span className="font-mono text-xs text-muted-foreground">{customTag}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Not in the list? Pull it straight from the Ollama library.
                    </div>
                  </div>
                  {customPull &&
                  (customPull.status === "pulling" ||
                    customPull.status === "validating" ||
                    customPull.status === "done") ? (
                    customPull.status === "pulling" ? (
                      <div className="w-64">
                        <DownloadBar
                          label="Downloading…"
                          progress={customPull}
                          onCancel={() => void onCancelPull(customTag)}
                        />
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {customPull.status === "done" ? "ready ✓ — find it below" : "validating…"}
                      </span>
                    )
                  ) : (
                    <button
                      type="button"
                      onClick={() => void onPull(customTag)}
                      className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)]/15 px-3 py-1 text-xs"
                    >
                      Pull “{customTag}”
                    </button>
                  )}
                </div>
              )}

              {filtered.length === 0 &&
                hfRows.length === 0 &&
                !showCustomPull &&
                !searchingAny &&
                !!q && (
                  <div className="text-sm text-muted-foreground">
                    No models match “{query}”.
                  </div>
                )}

              {/* Ollama results (curated + library) */}
              {filtered.map((m) => {
                const tier = TIER_STYLE[m.fit.tier];
                const pull = pulling[m.ollama];
                const status = pull?.status ?? "";
                const pullErr = status.startsWith("error") ? status : null;
                const fits = m.fit.tier !== "no_fit";
                return (
                  <div
                    key={m.id}
                    className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card/30 px-3 py-2"
                  >
                    <span
                      className={`shrink-0 rounded border px-2 py-0.5 text-xs ${tier.cls}`}
                      title={m.fit.reason}
                    >
                      {tier.label}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{m.name}</span>
                        <span className="font-mono text-xs text-muted-foreground">{m.ollama}</span>
                        <span className="rounded border border-emerald-500/40 px-1 text-2xs text-emerald-400/90">
                          Ollama
                        </span>
                        {m.installed && (
                          <span className="rounded bg-emerald-500/15 px-1.5 text-2xs text-emerald-400">
                            installed
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {m.use_case} · ~{m.size_gb}GB · {m.fit.mode.toUpperCase()} ·{" "}
                        {m.tool_use ? (
                          <span className="text-emerald-400">tools ✓</span>
                        ) : (
                          <span className="text-amber-400">no tools ⚠</span>
                        )}
                      </div>
                      {status === "pulling" && (
                        <div className="mt-1 max-w-md">
                          <DownloadBar
                            label="Downloading…"
                            progress={pull}
                            onCancel={() => void onCancelPull(m.ollama)}
                          />
                        </div>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {pullErr && <span className="text-xs text-rose-400">{pullErr}</span>}
                      {m.installed ? (
                        <button
                          type="button"
                          onClick={() => void onUseOllama(m)}
                          className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)]/15 px-3 py-1 text-xs"
                        >
                          Use
                        </button>
                      ) : status === "pulling" || status === "validating" || status === "done" ? (
                        <span className="text-xs text-muted-foreground">
                          {status === "done"
                            ? "ready ✓"
                            : status === "validating"
                              ? "validating…"
                              : ""}
                        </span>
                      ) : (
                        <button
                          type="button"
                          disabled={!fits || !ollama.installed}
                          onClick={() => void onPull(m.ollama)}
                          title={
                            !ollama.installed
                              ? "Install Ollama first"
                              : !fits
                                ? "Too big for this machine"
                                : "Pull with Ollama"
                          }
                          className="rounded-md border border-border px-3 py-1 text-xs hover:text-foreground disabled:opacity-40"
                        >
                          Run
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Hugging Face GGUF results (llama.cpp) */}
              {q && hfRows.length > 0 && (
                <div className="mt-2 text-xs font-medium text-muted-foreground">
                  Hugging Face — GGUF for llama.cpp
                </div>
              )}
              {q &&
                hfRows.map((r) => {
                  const files = hfFiles[r.repo];
                  const expanded = files !== undefined;
                  return (
                    <div
                      key={r.repo}
                      className="rounded-lg border border-border bg-card/30 px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center gap-3">
                        <span className="shrink-0 rounded border border-sky-500/50 px-2 py-0.5 text-xs text-sky-400">
                          GGUF
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{r.name}</span>
                            <span className="text-xs text-muted-foreground">by {r.author}</span>
                            <span className="rounded border border-sky-500/40 px-1 text-2xs text-sky-400/90">
                              llama.cpp
                            </span>
                            {r.gated && (
                              <span className="rounded bg-amber-500/15 px-1.5 text-2xs text-amber-400">
                                gated
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {r.downloads.toLocaleString()} downloads · ♥ {r.likes}
                            {r.license ? ` · ${r.license}` : ""}
                            {r.updated_at ? ` · updated ${r.updated_at.slice(0, 10)}` : ""}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => void onExpandRepo(r.repo)}
                          disabled={!llamacpp.installed && llamaInstall !== "done"}
                          title={
                            !llamacpp.installed && llamaInstall !== "done"
                              ? "Install llama.cpp first"
                              : "Pick a quantization to download"
                          }
                          className="shrink-0 rounded-md border border-border px-3 py-1 text-xs hover:text-foreground disabled:opacity-40"
                        >
                          {expanded ? "Versions ↓" : "Install…"}
                        </button>
                      </div>
                      {expanded && (
                        <div className="mt-2 grid gap-1 border-t border-border/60 pt-2">
                          {files === "loading" ? (
                            <div className="text-xs text-muted-foreground">
                              Fetching GGUF files…
                            </div>
                          ) : files.length === 0 ? (
                            <div className="text-xs text-muted-foreground">
                              No downloadable single-file GGUF found in this repo.
                            </div>
                          ) : (
                            files.map((f) => {
                              const tooBig = ramGb > 0 && f.size_bytes / 1024 ** 3 > ramGb;
                              const dlEntry = Object.entries(downloads).find(
                                ([, d]) => d.repo === r.repo && d.file === f.file,
                              );
                              const dl = dlEntry?.[1];
                              return (
                                <div
                                  key={f.file}
                                  className="flex flex-wrap items-center gap-2 rounded px-1 py-0.5 text-xs hover:bg-border/20"
                                >
                                  <span className="w-20 font-mono">{f.quant || "?"}</span>
                                  <span className="w-20 text-muted-foreground">
                                    {fmtBytes(f.size_bytes)}
                                  </span>
                                  <span className="min-w-0 flex-1 truncate font-mono text-2xs text-muted-foreground">
                                    {f.file}
                                  </span>
                                  {f.multipart ? (
                                    <span className="text-2xs text-muted-foreground">
                                      multi-part (unsupported)
                                    </span>
                                  ) : dl && dl.status === "done" ? (
                                    <span className="text-emerald-400">ready ✓</span>
                                  ) : dl &&
                                    (dl.status === "downloading" ||
                                      dl.status === "verifying" ||
                                      dl.status === "registering") ? (
                                    <span className="text-muted-foreground">
                                      {dl.percent != null ? `${dl.percent.toFixed(0)}%` : "…"}
                                    </span>
                                  ) : (
                                    <button
                                      type="button"
                                      onClick={() => void onDownload(r.repo, f.file)}
                                      title={
                                        tooBig
                                          ? "Bigger than this machine's RAM — will likely not load"
                                          : "Download to the llama.cpp models folder"
                                      }
                                      className={`rounded border px-2 py-0.5 ${tooBig ? "border-amber-500/50 text-amber-400" : "border-[var(--color-primary)] bg-[var(--color-primary)]/15"}`}
                                    >
                                      Install
                                    </button>
                                  )}
                                </div>
                              );
                            })
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
