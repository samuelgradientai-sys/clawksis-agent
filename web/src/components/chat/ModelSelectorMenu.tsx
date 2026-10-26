/**
 * ModelSelectorMenu — selector de modelo compacto para la barra del composer
 * (estilo Claude: "modelo ⌄"). Cambia el modelo de la sesión sin salir del chat.
 *
 * Recarga la lista (model.options) cada vez que se abre — es la lectura barata
 * del backend (caché de disco), así un switch hecho en otra superficie o un
 * modelo recién bajado a Ollama aparecen sin recargar la página — y el botón ⟳
 * fuerza la re-detección (refresh: invalida cachés y sondea endpoints guardados).
 * Aplica el cambio vía config.set (useModelOptions); el modelo del header se
 * actualiza solo por el evento session.info que emite el backend tras el switch.
 *
 * Orden: el modelo en uso arriba, después los proveedores locales (Ollama,
 * LM Studio, llama.cpp, endpoints locales) y luego los de la nube.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Cloud,
  HardDrive,
  Loader2,
  RefreshCw,
  Search,
} from "lucide-react";

import { useModelOptions } from "./hooks/useModelOptions";
import type { RpcSender } from "./hooks/useSessions";
import { groupMenuModels, type MenuGroup, type MenuGroups } from "./model-menu-groups";

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

  const label = currentModel || loadedModel || "Modelo";
  // model.options trae el modelo del agente vivo; session.info cubre el hueco antes de cargar.
  const liveModel = loadedModel || currentModel || "";

  // Recargar al abrir: barato (caché del backend) y evita una lista vieja.
  useEffect(() => {
    if (open) void refresh();
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

  const groups = useMemo(
    () => groupMenuModels(providers, liveModel, currentProvider, query),
    [providers, liveModel, currentProvider, query],
  );
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
        <div className="absolute bottom-full left-0 z-50 mb-2 flex max-h-96 w-80 flex-col overflow-hidden rounded-lg border border-border bg-popover shadow-xl">
          {/* Buscador + re-detectar */}
          <div className="flex items-center gap-2 border-b border-border px-2.5 py-2">
            <Search className="size-3.5 shrink-0 text-muted-foreground" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar modelo…"
              className="w-full bg-transparent text-xs text-foreground placeholder:text-muted-foreground outline-none"
            />
            <button
              type="button"
              onClick={() => void refresh(true)}
              disabled={loading}
              title="Volver a detectar modelos (servidores locales y proveedores)"
              aria-label="Volver a detectar modelos"
              className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted/50 hover:text-foreground disabled:opacity-50"
            >
              {loading ? (
                <Loader2 className="size-3 animate-spin" />
              ) : (
                <RefreshCw className="size-3" />
              )}
            </button>
          </div>

          <ModelMenuList
            groups={groups}
            firstLoad={loading && providers.length === 0}
            hasModels={providers.some((p) => (p.models ?? []).length > 0)}
            error={loading ? null : error}
            switching={switching}
            onPick={(model, slug) => void handlePick(model, slug)}
          />
        </div>
      )}
    </div>
  );
}

function SectionTitle({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 border-t border-border/60 px-3 pb-0.5 pt-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground first:border-t-0">
      {icon}
      {text}
    </div>
  );
}

function ProviderGroup({
  group,
  inUse,
  switching,
  onPick,
}: {
  group: MenuGroup;
  inUse: MenuGroups["inUse"];
  switching: boolean;
  onPick(model: string, slug: string): void;
}) {
  return (
    <div className="mb-1">
      <div className="flex items-center gap-1.5 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/70">
        <span className="truncate">{group.name}</span>
      </div>
      {group.models.map((m) => {
        const isCurrent = inUse?.provider === group.slug && inUse.model === m;
        return (
          <button
            key={group.slug + "/" + m}
            type="button"
            disabled={switching}
            onClick={() => onPick(m, group.slug)}
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
  );
}

function ModelMenuList({
  groups,
  firstLoad,
  hasModels,
  error,
  switching,
  onPick,
}: {
  groups: MenuGroups;
  firstLoad: boolean;
  hasModels: boolean;
  error: string | null;
  switching: boolean;
  onPick(model: string, slug: string): void;
}) {
  const empty = !groups.inUse && !groups.local.length && !groups.cloud.length;
  const sections = [
    { key: "local", icon: <HardDrive className="size-3" />, text: "Locales", list: groups.local },
    { key: "cloud", icon: <Cloud className="size-3" />, text: "Nube", list: groups.cloud },
  ];
  return (
    <div className="min-h-0 flex-1 overflow-y-auto py-1">
      {firstLoad && (
        <div className="flex items-center gap-2 px-3 py-3 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" /> Cargando modelos…
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 px-3 py-3 text-xs text-destructive">
          <AlertCircle className="size-3 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!firstLoad && !error && empty && (
        <div className="px-3 py-3 text-xs italic text-muted-foreground">
          {hasModels ? "Sin coincidencias." : "No hay proveedores autenticados."}
        </div>
      )}

      {!firstLoad && groups.inUse && (
        <>
          <SectionTitle icon={<Check className="size-3" style={{ color: ACCENT }} />} text="En uso" />
          <div className="flex items-center gap-2 px-3 py-1.5 text-xs">
            <span className="flex-1 truncate font-mono text-foreground">{groups.inUse.model}</span>
            <span className="shrink-0 truncate text-[10px] text-muted-foreground">
              {groups.inUse.providerName}
              {groups.inUse.isLocal ? " · local" : ""}
            </span>
          </div>
        </>
      )}

      {!firstLoad &&
        sections.map(
          (section) =>
            section.list.length > 0 && (
              <div key={section.key}>
                <SectionTitle icon={section.icon} text={section.text} />
                {section.list.map((g) => (
                  <ProviderGroup
                    key={g.slug}
                    group={g}
                    inUse={groups.inUse}
                    switching={switching}
                    onPick={onPick}
                  />
                ))}
              </div>
            ),
        )}
    </div>
  );
}
