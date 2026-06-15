/**
 * Cookbook — local models. Shows the user's hardware, a curated catalog of open
 * LLMs with a per-model "does it fit?" verdict, and (via Ollama) one-click pull
 * + set-as-agent-model. Backed by /api/cookbook/* (see clawk_cli/cookbook.py).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchJSON } from "@/lib/api";

interface Fit {
  mode: "gpu" | "cpu" | "none";
  tier: "perfect" | "good" | "marginal" | "no_fit";
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

interface CatalogResponse {
  hardware: Hardware;
  ollama: OllamaStatus;
  models: CookbookModel[];
}

const TIER_STYLE: Record<Fit["tier"], { label: string; cls: string }> = {
  perfect: { label: "Fits great", cls: "border-emerald-500/60 text-emerald-400" },
  good: { label: "Fits", cls: "border-emerald-500/50 text-emerald-400" },
  marginal: { label: "Tight / slow", cls: "border-amber-500/60 text-amber-400" },
  no_fit: { label: "Too big", cls: "border-rose-500/50 text-rose-400" },
};

export default function CookbookPage() {
  const [data, setData] = useState<CatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // tag -> "pulling" | "done" | "error: ..."
  const [pulling, setPulling] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
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
  }, []);

  useEffect(() => {
    void load();
    const timers = pollTimers.current;
    return () => {
      for (const t of Object.values(timers)) clearInterval(t);
    };
  }, [load]);

  const pollPull = useCallback(
    (tag: string) => {
      if (pollTimers.current[tag]) return;
      pollTimers.current[tag] = setInterval(() => {
        void (async () => {
          try {
            const res = await fetchJSON<{ status: string }>(
              `/api/cookbook/pull-status?tag=${encodeURIComponent(tag)}`,
            );
            setPulling((prev) => ({ ...prev, [tag]: res.status }));
            if (res.status === "done" || res.status.startsWith("error")) {
              clearInterval(pollTimers.current[tag]);
              delete pollTimers.current[tag];
              if (res.status === "done") void load(); // refresh installed flags
            }
          } catch {
            // keep polling; transient
          }
        })();
      }, 2500);
    },
    [load],
  );

  const onPull = useCallback(
    async (tag: string) => {
      setNotice(null);
      setPulling((prev) => ({ ...prev, [tag]: "pulling" }));
      try {
        const res = await fetchJSON<{ ok: boolean; error?: string }>("/api/cookbook/pull", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tag }),
        });
        if (!res.ok) {
          setPulling((prev) => ({ ...prev, [tag]: `error: ${res.error ?? "failed"}` }));
          return;
        }
        pollPull(tag);
      } catch {
        setPulling((prev) => ({ ...prev, [tag]: "error: request failed" }));
      }
    },
    [pollPull],
  );

  const onUse = useCallback(async (model: CookbookModel) => {
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
        setNotice(`Agent model set to ${model.name} (${model.ollama}) via local Ollama.`);
      } else {
        setNotice(`Could not switch model: ${res.error ?? "failed"}`);
      }
    } catch {
      setNotice("Could not switch model.");
    }
  }, []);

  const hw = data?.hardware ?? {};
  const ollama = data?.ollama ?? {};
  const models = data?.models ?? [];

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Cookbook — local models</h1>
          <p className="text-sm text-muted-foreground">
            Open LLMs you can run on this machine, and use as the agent&apos;s model.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-md border border-border bg-card/40 px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          Refresh
        </button>
      </header>

      {/* Hardware + Ollama status */}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-border bg-card/40 p-3 text-sm">
          <div className="mb-1 font-medium">Your hardware</div>
          <div className="text-muted-foreground">
            {hw.ram_gb ?? "?"}GB RAM · {hw.cpu_cores ?? "?"} cores ·{" "}
            {hw.gpu_name ? `${hw.gpu_name} (${hw.vram_gb ?? 0}GB VRAM)` : "no discrete GPU"}
            {hw.platform ? ` · ${hw.platform}` : ""}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-card/40 p-3 text-sm">
          <div className="mb-1 font-medium">Ollama</div>
          <div className="text-muted-foreground">
            {ollama.installed
              ? ollama.running
                ? `Running · ${String(ollama.models?.length ?? 0)} model(s) pulled`
                : "Installed but not running — start it with `ollama serve`."
              : "Not installed — get it at ollama.com to run models locally."}
          </div>
        </div>
      </div>

      {notice && (
        <div className="rounded-md border border-[var(--color-primary)]/50 bg-[var(--color-primary)]/10 px-3 py-2 text-sm">
          {notice}
        </div>
      )}

      {loading ? (
        <div className="text-sm text-muted-foreground">Detecting hardware…</div>
      ) : error ? (
        <div className="text-sm text-rose-400">{error}</div>
      ) : (
        <div className="grid gap-2">
          {models.map((m) => {
            const tier = TIER_STYLE[m.fit.tier];
            const pull = pulling[m.ollama];
            const isPulling = pull === "pulling";
            const pullErr = pull?.startsWith("error") ? pull : null;
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
                    {m.installed && (
                      <span className="rounded bg-emerald-500/15 px-1.5 text-2xs text-emerald-400">
                        installed
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {m.use_case} · ~{m.size_gb}GB · {m.fit.mode.toUpperCase()} ·{" "}
                    {m.tool_use ? "tools ✓" : "no tools"}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {pullErr && <span className="text-xs text-rose-400">{pullErr}</span>}
                  {m.installed ? (
                    <button
                      type="button"
                      onClick={() => void onUse(m)}
                      className="rounded-md border border-[var(--color-primary)] bg-[var(--color-primary)]/15 px-3 py-1 text-xs"
                    >
                      Use
                    </button>
                  ) : isPulling || pull === "done" ? (
                    <span className="text-xs text-muted-foreground">
                      {pull === "done" ? "pulled ✓" : "pulling…"}
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
        </div>
      )}
    </div>
  );
}
