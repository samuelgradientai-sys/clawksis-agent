import { Brain, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ConnectionStatus } from "./hooks/useChatGateway";
import { ChatViewTabs } from "./ChatViewTabs";
import { ChatDrawerButton } from "./ChatSessionDrawer";

interface ChatHeaderProps {
  status: ConnectionStatus;
  model: string | null;
  modelProvider: string | null;
  sessionId: string | null;
  tokensUsed: number;
  tokensMax: number;
  /** Título de la conversación que se está viendo. */
  title?: string;
  /** Click handler para abrir el popover de uso de tokens */
  onTokensClick?: () => void;
  /** Ref del botón de tokens para anclar el popover */
  tokensRef?: React.RefObject<HTMLButtonElement | null>;
}

const STATUS_DOT: Record<ConnectionStatus, string> = {
  connected: "bg-success",
  connecting: "bg-warning animate-pulse",
  idle: "bg-destructive",
  disconnected: "bg-destructive",
  error: "bg-destructive",
};

function tokensText(used: number, max: number): string {
  return max > 0
    ? used.toLocaleString() + "/" + (max / 1000).toFixed(1) + "k tokens"
    : used.toLocaleString() + " tokens";
}

/** Barra superior del chat moderno: título y modelo a la izquierda (se recortan
 *  antes de invadir lo de la derecha), uso de tokens y pestañas de vista a la derecha. */
export function ChatHeader({
  status,
  model,
  modelProvider,
  sessionId,
  tokensUsed,
  tokensMax,
  title,
  onTokensClick,
  tokensRef,
}: ChatHeaderProps) {
  const tokenPercent = tokensMax > 0 ? Math.min(100, Math.round((tokensUsed / tokensMax) * 100)) : null;
  const modelLabel = model ? model + (modelProvider ? " · " + modelProvider : "") : "";

  return (
    <div className="flex items-center gap-2 border-b border-white/10 bg-background/28 px-2.5 py-2 backdrop-blur-xl sm:gap-3 sm:px-4 sm:py-3">
      <ChatDrawerButton />
      <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
        <span className={cn("size-2 shrink-0 rounded-full", STATUS_DOT[status])} />
        <span className="min-w-0 truncate text-sm font-semibold text-foreground" title={title}>
          {title || (status === "connecting" ? "Conectando..." : "Nueva conversación")}
        </span>
        {modelLabel && (
          <span className="hidden min-w-0 items-center gap-1 text-xs text-muted-foreground xl:flex" title={modelLabel}>
            <span aria-hidden>·</span>
            <span className="truncate">{modelLabel}</span>
          </span>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          ref={tokensRef}
          onClick={onTokensClick}
          disabled={!onTokensClick}
          title={"Ver desglose de uso de tokens · sesión " + (sessionId ? sessionId.slice(0, 8) : "—")}
          className="clawk-liquid-chip flex min-h-11 items-center gap-2 rounded-2xl border border-[#6C4FD6]/35 bg-[#6C4FD6]/10 px-2.5 py-2 text-xs text-foreground shadow-sm shadow-[#6C4FD6]/10 transition-all hover:border-[#8B6DFF]/70 hover:bg-[#6C4FD6]/20 disabled:cursor-default disabled:opacity-60 sm:min-h-0 sm:px-3.5"
          aria-label="Abrir menú de uso de tokens"
        >
          <Brain className="size-3.5 text-[#6C4FD6]" />
          <span className="hidden font-medium 2xl:inline">Uso de tokens</span>
          <span className="hidden text-muted-foreground 2xl:inline">·</span>
          {/* Phones keep just the gauge: the full count lives in the popover. */}
          <span className={cn("font-mono text-foreground/90", tokenPercent !== null && "hidden md:inline")}>
            {tokensText(tokensUsed, tokensMax)}
          </span>
          {tokenPercent !== null && (
            <span className="rounded bg-background/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {tokenPercent}%
            </span>
          )}
          <ChevronRight className="hidden size-3 rotate-90 text-muted-foreground sm:block" />
        </button>

        {/* Pestañas de vista junto a "Uso de tokens": el chat moderno gana la
            altura de la banda que antes vivía arriba (ChatRouter). */}
        <ChatViewTabs />
      </div>
    </div>
  );
}
