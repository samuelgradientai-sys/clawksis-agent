import { useState } from "react";
import { Button } from "@nous-research/ui/ui/components/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@nous-research/ui/ui/components/dialog";
import { Input } from "@nous-research/ui/ui/components/input";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/api-error";
import { formatSessionPruneResult } from "@/lib/session-prune";
import { buildCleanupRequest, parsePruneDays, type CleanupFilterText } from "@/lib/session-cleanup";
import { useI18n } from "@/i18n";
import { sessionsLabels } from "./SessionsPage_labels";
import { sourceLabel } from "./SessionsPage_sources";

type Notify = (message: string, type: "success" | "error") => void;

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Reload the list/stats after the store changed. */
  onChanged: () => void;
  notify: Notify;
}

export function PruneDialog({ open, onOpenChange, onChanged, notify }: DialogProps) {
  const { t } = useI18n();
  const L = sessionsLabels(t);
  const [days, setDays] = useState("90");
  const [pruning, setPruning] = useState(false);

  const prune = async () => {
    const value = parsePruneDays(days);
    if (value === null) {
      notify(L.pruneInvalidDays, "error");
      return;
    }
    setPruning(true);
    try {
      notify(formatSessionPruneResult(await api.pruneSessions(value)), "success");
      onOpenChange(false);
      onChanged();
    } catch (e) {
      notify(`${L.pruneFailed}: ${errorMessage(e)}`, "error");
    } finally {
      setPruning(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !pruning && onOpenChange(next)}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{L.pruneTitle}</DialogTitle>
          <DialogDescription>{L.pruneDescription}</DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-1.5 px-4 pt-3">
          <label htmlFor="prune-days" className="text-xs font-medium text-muted-foreground">
            {L.pruneDays}
          </label>
          <Input
            id="prune-days"
            type="number"
            min={1}
            value={days}
            onChange={(e) => setDays(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void prune();
            }}
            disabled={pruning}
          />
        </div>
        <DialogFooter>
          <Button outlined onClick={() => onOpenChange(false)} disabled={pruning}>
            {t.common.cancel}
          </Button>
          <Button destructive onClick={() => void prune()} disabled={pruning} className="gap-1.5">
            {pruning && <Spinner className="text-sm" />}
            {L.pruneAction}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const EMPTY_FILTER: CleanupFilterText = { source: "", model: "", days: "", maxMessages: "" };

const PRESETS: Array<{ label: string; filter: CleanupFilterText }> = [
  { label: "Vacías / cortas", filter: { ...EMPTY_FILTER, maxMessages: "1" } },
  { label: "+ de 30 días", filter: { ...EMPTY_FILTER, days: "30" } },
  { label: "Cron viejas", filter: { ...EMPTY_FILTER, source: "cron", days: "7" } },
  { label: "Limpiar filtros", filter: EMPTY_FILTER },
];

function CleanupFields({
  filter,
  sources,
  busy,
  onChange,
}: {
  filter: CleanupFilterText;
  sources: string[];
  busy: boolean;
  onChange: (next: CleanupFilterText) => void;
}) {
  const field = (key: keyof CleanupFilterText, value: string) => onChange({ ...filter, [key]: value });
  // The store's own sources (stats.by_source), plus a preset's source the store does not hold.
  const options = filter.source && !sources.includes(filter.source) ? [...sources, filter.source] : sources;
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">Atajos</span>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              disabled={busy}
              onClick={() => onChange(preset.filter)}
              className="rounded-md border border-border bg-card/60 px-2 py-1 text-xs text-foreground transition-colors hover:bg-muted/40 disabled:opacity-50"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="cleanup-source" className="text-xs font-medium text-muted-foreground">
          Canal
        </label>
        <select
          id="cleanup-source"
          value={filter.source}
          onChange={(e) => field("source", e.target.value)}
          disabled={busy}
          className="rounded-md border border-border bg-card/60 px-2 py-1.5 text-sm text-foreground"
        >
          <option value="">Cualquiera</option>
          {options.map((source) => (
            <option key={source} value={source}>
              Solo {sourceLabel(source)}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="cleanup-model" className="text-xs font-medium text-muted-foreground">
          Modelo contiene (ej: un modelo que no funciona)
        </label>
        <Input
          id="cleanup-model"
          value={filter.model}
          onChange={(e) => field("model", e.target.value)}
          placeholder="(cualquiera)"
          disabled={busy}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cleanup-days" className="text-xs font-medium text-muted-foreground">
            Más viejas que (días)
          </label>
          <Input id="cleanup-days" type="number" min={0} value={filter.days} onChange={(e) => field("days", e.target.value)} placeholder="—" disabled={busy} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cleanup-max" className="text-xs font-medium text-muted-foreground">
            Máx. mensajes (vacías/cortas)
          </label>
          <Input
            id="cleanup-max"
            type="number"
            min={0}
            value={filter.maxMessages}
            onChange={(e) => field("maxMessages", e.target.value)}
            placeholder="—"
            disabled={busy}
          />
        </div>
      </div>
    </>
  );
}

interface CleanupPreview {
  matched: number;
  messages: number;
  skippedActive: number;
}

function previewText(preview: CleanupPreview): string {
  const live = preview.skippedActive
    ? ` ${preview.skippedActive} con actividad en curso no se tocan.`
    : "";
  return preview.matched === 0
    ? `Ninguna sesión coincide con esos filtros.${live}`
    : `Coinciden ${preview.matched} sesiones (${preview.messages} mensajes). Se eliminarán permanentemente.${live}`;
}

/** Filtered free-space cleanup ("Limpiar"): channel / model / age / size, dry-run preview first.
 *  Acts on the profile the dashboard switcher selected. */
export function CleanupDialog({
  open,
  onOpenChange,
  onChanged,
  notify,
  sources,
}: DialogProps & { sources: string[] }) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<CleanupFilterText>(EMPTY_FILTER);
  const [preview, setPreview] = useState<CleanupPreview | null>(null);
  const [busy, setBusy] = useState(false);

  const close = (next: boolean) => {
    if (busy) return;
    onOpenChange(next);
    if (!next) setPreview(null);
  };

  const runPreview = async () => {
    const body = buildCleanupRequest(filter, true);
    if (!body) {
      notify("Elegí al menos un filtro", "error");
      return;
    }
    setBusy(true);
    try {
      const r = await api.cleanupSessions(body);
      setPreview({ matched: r.matched ?? 0, messages: r.messages ?? 0, skippedActive: r.skipped_active ?? 0 });
    } catch (e) {
      notify(`No se pudo previsualizar la limpieza: ${errorMessage(e)}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const runDelete = async () => {
    const body = buildCleanupRequest(filter, false);
    if (!body) return;
    setBusy(true);
    try {
      const r = await api.cleanupSessions(body);
      notify(`Se eliminaron ${r.deleted ?? 0} sesiones`, "success");
      onOpenChange(false);
      setPreview(null);
      onChanged();
    } catch (e) {
      notify(`No se pudo limpiar las sesiones: ${errorMessage(e)}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const canDelete = !busy && !!preview && preview.matched > 0;
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Limpiar sesiones · liberar espacio</DialogTitle>
          <DialogDescription>
            Elegí uno o más filtros (se combinan), previsualizá cuántas se borrarían y confirmá. El borrado es
            permanente.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3 px-4 pt-3">
          <CleanupFields
            filter={filter}
            sources={sources}
            busy={busy}
            onChange={(next) => {
              setFilter(next);
              setPreview(null);
            }}
          />
          {preview && (
            <div className="rounded-md border border-border bg-background-base/40 px-3 py-2 text-xs">
              {previewText(preview)}
            </div>
          )}
        </div>
        <DialogFooter className="flex-wrap gap-2">
          <Button outlined onClick={() => close(false)} disabled={busy}>
            {t.common.cancel}
          </Button>
          <Button outlined onClick={() => void runPreview()} disabled={busy} className="gap-1.5">
            {busy && !preview && <Spinner className="text-sm" />}
            Previsualizar
          </Button>
          <Button destructive onClick={() => void runDelete()} disabled={!canDelete} className="gap-1.5">
            {busy && !!preview && <Spinner className="text-sm" />}
            {preview && preview.matched > 0 ? `Eliminar (${preview.matched})` : "Eliminar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
