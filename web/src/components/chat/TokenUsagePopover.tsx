/**
 * TokenUsagePopover — Desplegable que muestra detalle de tokens.
 *
 * Anclado al botón "Session X · Y tokens" del header del chat moderno.
 * Muestra:
 *   1) Sesión actual: input/output/cache/reasoning + costo estimado
 *   2) Acumulado por modelo: lista ordenada por uso
 *
 * Cierre: click fuera, ESC, o botón X.
 */

import { useEffect, useRef } from "react";
import { X, Loader2, Coins, Database } from "lucide-react";

import type {
  SessionUsage,
  UsageByModel,
} from "./hooks/useTokenUsage";

interface TokenUsagePopoverProps {
  open: boolean;
  onClose: () => void;
  loading: boolean;
  error: string | null;
  sessionUsage: SessionUsage | null;
  usageByModel: UsageByModel | null;
  anchorRef: React.RefObject<HTMLElement | null>;
}

function formatTokens(n: number): string {
  if (n === 0) return "0";
  if (n < 1000) return n.toLocaleString();
  if (n < 1_000_000) return (n / 1000).toFixed(n < 10_000 ? 2 : 1) + "k";
  return (n / 1_000_000).toFixed(2) + "M";
}

function formatCost(cost: number | null | undefined): string {
  if (cost == null || cost === 0) return "—";
  if (cost < 0.01) return "<$0.01";
  if (cost < 1) return "$" + cost.toFixed(3);
  return "$" + cost.toFixed(2);
}

function ModelRow({
  model,
  tokens,
  cost,
  sessions,
}: {
  model: string;
  tokens: number;
  cost: number;
  sessions?: number;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5 text-xs">
      <div className="flex min-w-0 items-center gap-2">
        <span className="size-1.5 shrink-0 rounded-full bg-[#6C4FD6]" />
        <span className="truncate font-mono text-foreground" title={model}>
          {model}
        </span>
        {sessions != null && (
          <span className="shrink-0 text-muted-foreground">
            · {sessions} {sessions === 1 ? "sesión" : "sesiones"}
          </span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3 text-muted-foreground">
        <span className="font-mono">{formatTokens(tokens)}</span>
        <span className="font-mono">{formatCost(cost)}</span>
      </div>
    </div>
  );
}

export function TokenUsagePopover({
  open,
  onClose,
  loading,
  error,
  sessionUsage,
  usageByModel,
  anchorRef,
}: TokenUsagePopoverProps) {
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      const pop = popoverRef.current;
      const anchor = anchorRef.current;
      if (!pop) return;
      if (pop.contains(target)) return;
      if (anchor && anchor.contains(target)) return;
      onClose();
    };
    const tid = window.setTimeout(() => {
      window.addEventListener("mousedown", handler);
    }, 0);
    return () => {
      window.clearTimeout(tid);
      window.removeEventListener("mousedown", handler);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;

  const sessionTotal = sessionUsage?.total ?? 0;
  const sessionCost = sessionUsage?.cost_usd ?? null;
  const sessionModel = sessionUsage?.model ?? "—";
  const ctxPct = sessionUsage?.context_percent ?? null;

  return (
    <div
      ref={popoverRef}
      role="dialog"
      aria-label="Uso de tokens"
      className="absolute right-0 top-full z-30 mt-2 w-[380px] max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-background shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Coins className="size-3.5 text-[#6C4FD6]" />
          <span className="text-xs font-semibold uppercase tracking-wider text-foreground">
            Uso de tokens
          </span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>

      <div className="max-h-[60vh] overflow-y-auto px-4 py-3">
        {loading && (
          <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            <span>Cargando datos...</span>
          </div>
        )}

        {error && !loading && (
          <div className="rounded border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="mb-3">
              <div className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                <Database className="size-3" />
                <span>Esta conversación</span>
              </div>
              {sessionUsage ? (
                <div className="rounded border border-border bg-muted/20 px-3 py-2">
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="truncate font-mono text-foreground" title={sessionModel}>
                      {sessionModel}
                    </span>
                    <span className="ml-2 shrink-0 font-mono text-muted-foreground">
                      {formatTokens(sessionTotal)} tokens · {formatCost(sessionCost)}
                    </span>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                    <div className="flex justify-between">
                      <span>Entrada:</span>
                      <span className="font-mono">{formatTokens(sessionUsage.input)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Salida:</span>
                      <span className="font-mono">{formatTokens(sessionUsage.output)}</span>
                    </div>
                    {sessionUsage.cache_read > 0 && (
                      <div className="flex justify-between">
                        <span>Cache leído:</span>
                        <span className="font-mono">{formatTokens(sessionUsage.cache_read)}</span>
                      </div>
                    )}
                    {sessionUsage.cache_write > 0 && (
                      <div className="flex justify-between">
                        <span>Cache escrito:</span>
                        <span className="font-mono">{formatTokens(sessionUsage.cache_write)}</span>
                      </div>
                    )}
                    {sessionUsage.reasoning > 0 && (
                      <div className="flex justify-between">
                        <span>Razonamiento:</span>
                        <span className="font-mono">{formatTokens(sessionUsage.reasoning)}</span>
                      </div>
                    )}
                    {sessionUsage.calls > 0 && (
                      <div className="flex justify-between">
                        <span>Llamadas API:</span>
                        <span className="font-mono">{sessionUsage.calls}</span>
                      </div>
                    )}
                  </div>
                  {ctxPct != null && sessionUsage.context_max && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted/40">
                        <div
                          className="h-full bg-[#6C4FD6] transition-all"
                          style={{ width: ctxPct + "%" }}
                        />
                      </div>
                      <span className="text-[10px] font-mono text-muted-foreground">
                        {ctxPct}% del contexto
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="rounded border border-dashed border-border px-3 py-2 text-[11px] text-muted-foreground">
                  Sin datos de esta conversación todavía.
                </div>
              )}
            </div>

            <div>
              <div className="mb-1.5 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                <span>Acumulado por modelo</span>
                {usageByModel && (
                  <span className="font-mono">
                    {formatTokens(usageByModel.total_tokens)} · {formatCost(usageByModel.total_cost_usd)}
                  </span>
                )}
              </div>
              <div className="divide-y divide-border/60">
                {usageByModel && usageByModel.models.length > 0 ? (
                  usageByModel.models.map((m) => (
                    <ModelRow
                      key={m.model}
                      model={m.model}
                      tokens={m.total_tokens}
                      cost={m.cost_usd}
                      sessions={m.sessions_count}
                    />
                  ))
                ) : (
                  <div className="py-2 text-[11px] text-muted-foreground">
                    Sin uso registrado todavía.
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
