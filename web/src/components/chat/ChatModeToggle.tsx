/**
 * ChatModeToggle — Switch segmentado para alternar entre modo terminal y moderno.
 */

import { Terminal, MessageSquare } from "lucide-react";
import type { ChatMode } from "./hooks/useChatMode";

interface ChatModeToggleProps {
  mode: ChatMode;
  onChange: (mode: ChatMode) => void;
  showLabels?: boolean;
}

export function ChatModeToggle({
  mode,
  onChange,
  showLabels = true,
}: ChatModeToggleProps) {
  return (
    <div
      role="group"
      aria-label="Modo de chat"
      className="inline-flex h-7 items-center rounded-md border border-border bg-muted/20 p-0.5"
    >
      <button
        type="button"
        aria-pressed={mode === "terminal"}
        onClick={() => onChange("terminal")}
        title="Modo terminal — interfaz CLI clásica"
        className={
          "flex h-6 items-center gap-1.5 rounded px-2 text-xs transition-colors " +
          (mode === "terminal"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground")
        }
      >
        <Terminal className="size-3" />
        {showLabels && <span>Terminal</span>}
      </button>
      <button
        type="button"
        aria-pressed={mode === "modern"}
        onClick={() => onChange("modern")}
        title="Modo moderno — burbujas tipo chat"
        className={
          "flex h-6 items-center gap-1.5 rounded px-2 text-xs transition-colors " +
          (mode === "modern"
            ? "bg-background text-foreground shadow-sm"
            : "text-muted-foreground hover:text-foreground")
        }
      >
        <MessageSquare className="size-3" />
        {showLabels && <span>Modern</span>}
      </button>
    </div>
  );
}
