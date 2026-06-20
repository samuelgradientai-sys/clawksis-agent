/**
 * ModelSelectorMenu — selector de modelo compacto para la barra del composer
 * (estilo Claude: "modelo ⌄"). Cambia el modelo de la sesión sin salir del chat.
 *
 * Carga la lista on-demand (model.options) al abrir y aplica el cambio vía
 * config.set (useModelOptions). El modelo actual del header se actualiza solo
 * por el evento session.info que emite el backend tras el switch.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Search, Check, Loader2, AlertCircle } from "lucide-react";

import { useModelOptions } from "./hooks/useModelOptions";
import type { RpcSender } from "./hooks/useSessions";

const ACCENT = "#6C4FD6";

interface ModelSelectorMenuProps {
  sendRpc: RpcSender;
  ready: boolean;
  sessionId: string | null;
  /** Modelo actual en vivo (de session.info) — se usa para la etiqueta del botón. */
  currentModel: string | null;
  /** Deshabilitado mientras el agente responde (config.set rechaza mid-turn). */
  disabled?: boolean;
}

interface FlatModel {
  provider: string; // slug
  providerName: string;
  model: string;
}

export function ModelSelectorMenu({
  sendRpc,
  ready,
  sessionId,
  currentModel,
  disabled,
}: ModelSelectorMenuProps) {
  const {
    providers,
    currentModel: loadedModel,
    currentProvider,
    loading,
    error,
    refresh,
    switchModel,
  } = useModelOptions(sendRpc, ready, sessionId);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [switching, setSwitching] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const loadedOnceRef = useRef(false);

  const label = currentModel || loadedModel || "Modelo";

  // Cargar la lista la primera vez que se abre.
  useEffect(() => {
    if (open && !loadedOnceRef.current) {
      loadedOnceRef.current = true;
      void refresh();
    }
  }, [open, refresh]);

  // Cerrar al hacer click afuera o con Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const flat = useMemo<FlatModel[]>(() => {
    const out: FlatModel[] = [];
    for (const p of providers) {
      for (const m of p.models ?? []) {
        out.push({ provider: p.slug, providerName: p.name, model: m });
      }
    }
    return out;
  }, [providers]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return flat;
    return flat.filter(
      (f) =>
        f.model.toLowerCase().includes(q) ||
        f.providerName.toLowerCase().includes(q) ||
        f.provider.toLowerCase().includes(q),
    );
  }, [flat, query]);

  // Agrupar por proveedor preservando el orden.
  const grouped = useMemo(() => {
    const map = new Map<string, { name: string; models: string[] }>();
    for (const f of filtered) {
      const g = map.get(f.provider) ?? { name: f.providerName, models: [] };
      g.models.push(f.model);
      map.set(f.provider, g);
    }
    return [...map.entries()].map(([slug, g]) => ({ slug, ...g }));
  }, [filtered]);

  const handlePick = async (model: string, providerSlug: string) => {
    setSwitching(true);
    try {
      let res = await switchModel(model, providerSlug);
      if (res.confirmRequired) {
        const ok = window.confirm(
          (res.confirmMessage ?? "Modelo caro.") + "\n\n¿Cambiar de todas formas?",
        );
        if (!ok) return;
        res = await switchModel(model, providerSlug, true);
      }
      if (res.ok) {
        setOpen(false);
        setQuery("");
      }
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        title={disabled ? "Esperá a que termine la respuesta para cambiar de modelo" : "Cambiar de modelo"}
        className="flex max-w-[180px] items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
      >
        <span className="truncate font-medium">{label}</span>
        <ChevronDown className="size-3 shrink-0 opacity-70" />
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-50 mb-2 flex max-h-80 w-72 flex-col overflow-hidden rounded-lg border border-border bg-popover shadow-xl">
          {/* Buscador */}
          <div className="flex items-center gap-2 border-b border-border px-2.5 py-2">
            <Search className="size-3.5 shrink-0 text-muted-foreground" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar modelo…"
              className="w-full bg-transparent text-xs text-foreground placeholder:text-muted-foreground outline-none"
            />
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto py-1">
            {loading && (
              <div className="flex items-center gap-2 px-3 py-3 text-xs text-muted-foreground">
                <Loader2 className="size-3 animate-spin" /> Cargando modelos…
              </div>
            )}

            {error && !loading && (
              <div className="flex items-start gap-2 px-3 py-3 text-xs text-destructive">
                <AlertCircle className="size-3 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {!loading && !error && grouped.length === 0 && (
              <div className="px-3 py-3 text-xs italic text-muted-foreground">
                {flat.length === 0
                  ? "No hay proveedores autenticados."
                  : "Sin coincidencias."}
              </div>
            )}

            {!loading &&
              grouped.map((g) => (
                <div key={g.slug} className="mb-1">
                  <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                    {g.name}
                  </div>
                  {g.models.map((m) => {
                    const isCurrent =
                      m === (currentModel || loadedModel) &&
                      g.slug === currentProvider;
                    return (
                      <button
                        key={g.slug + "/" + m}
                        type="button"
                        disabled={switching}
                        onClick={() => void handlePick(m, g.slug)}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left font-mono text-xs text-foreground hover:bg-muted/50 disabled:opacity-50 transition-colors"
                      >
                        <Check
                          className="size-3 shrink-0"
                          style={{ color: isCurrent ? ACCENT : "transparent" }}
                        />
                        <span className="flex-1 truncate">{m}</span>
                      </button>
                    );
                  })}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
