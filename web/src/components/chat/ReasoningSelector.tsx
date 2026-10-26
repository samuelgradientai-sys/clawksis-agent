/**
 * Modo de respuesta: Rápida / Normal / Pensar — the open session's reasoning
 * effort. It shows what the session runs (`session.info.reasoning_effort`) and
 * a pick is session-scoped (`config.set reasoning` with the session id). With
 * no session there is nothing to set: the chat never rewrites the global
 * `agent.reasoning_effort` (config.set without a session would).
 */

import { useState } from "react";
import { Brain, ChevronDown, Gauge, Zap } from "lucide-react";
import { modeForEffort } from "./hooks/sessionInfo";

const REASONING_MODES = [
  {
    value: "minimal",
    label: "Rápida",
    icon: Zap,
    hint: "Respuesta directa, sin razonamiento largo — ideal para preguntas simples",
  },
  { value: "medium", label: "Normal", icon: Gauge, hint: "Equilibrado (por defecto)" },
  { value: "high", label: "Pensar", icon: Brain, hint: "Razonamiento profundo para tareas difíciles" },
] as const;

export function ReasoningSelector({
  sendRpc,
  sessionId,
  reasoningEffort,
  disabled,
}: {
  sendRpc: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  sessionId: string | null;
  reasoningEffort?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  // The pick shows at once; the session.info that config.set emits confirms it.
  const [pending, setPending] = useState<string | null>(null);
  const mode = pending ?? modeForEffort(reasoningEffort);
  const current = REASONING_MODES.find((m) => m.value === mode) ?? REASONING_MODES[1];
  const CurrentIcon = current.icon;

  const apply = async (value: string) => {
    setOpen(false);
    if (!sessionId) return;
    setPending(value);
    try {
      await sendRpc("config.set", { key: "reasoning", value, session_id: sessionId });
    } catch (err) {
      console.warn("[ReasoningSelector] config.set reasoning failed", err);
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        disabled={disabled || !sessionId}
        onClick={() => setOpen((v) => !v)}
        title={current.hint}
        aria-label={"Modo de respuesta: " + current.label}
        className="flex min-h-11 items-center gap-1 rounded-lg px-1.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 sm:min-h-0"
      >
        <CurrentIcon className="size-4" />
        <span className="hidden sm:inline">{current.label}</span>
        <ChevronDown className="size-3 opacity-60" />
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-label="Cerrar"
            className="fixed inset-0 z-20 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute bottom-full left-0 z-30 mb-1 w-64 max-w-[calc(100vw-2rem)] overflow-hidden rounded-md border border-border bg-popover p-1 text-xs text-popover-foreground shadow-lg">
            {REASONING_MODES.map((m) => {
              const Icon = m.icon;
              const active = m.value === mode;
              return (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => void apply(m.value)}
                  className={
                    "flex w-full items-start gap-2 rounded px-2 py-2 text-left hover:bg-muted " +
                    (active ? "bg-[#6C4FD6]/15" : "")
                  }
                >
                  <Icon className={"mt-0.5 size-3.5 shrink-0 " + (active ? "text-[#6C4FD6]" : "text-muted-foreground")} />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">{m.label}</span>
                    <span className="block text-[10px] text-muted-foreground">{m.hint}</span>
                  </span>
                  {active && <span className="text-[10px] text-[#6C4FD6]">✓</span>}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
