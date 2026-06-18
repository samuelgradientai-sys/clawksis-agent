/**
 * ChatRouter — Wrapper que renderiza el modo terminal o moderno según la
 * preferencia del usuario (persistida en localStorage).
 *
 * Fase 2.6.4-fix-v4: el toggle vuelve a ser banda arriba (NO overlay),
 * porque overlay siempre tapaba algo importante (MODEL/TOOLS o sidebar).
 * Trade-off: ~28px menos de altura para el chat, pero sin solapamiento.
 *
 * Para el modo terminal: el ChatPage usa todo el alto restante con flex-1.
 * Para el modo moderno: el ChatModern también flex-1.
 */

import { lazy, Suspense, type ComponentType } from "react";
import { useChatMode } from "./hooks/useChatMode";
import { ChatModeToggle } from "./ChatModeToggle";

const ChatTerminal = lazy(() => import("@/pages/ChatPage")) as ComponentType<{
  isActive?: boolean;
}>;
const ChatModern = lazy(() => import("./ChatModern"));

interface ChatRouterProps {
  isActive?: boolean;
}

function ModeFallback() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      Cargando chat...
    </div>
  );
}

export default function ChatRouter({ isActive = true }: ChatRouterProps) {
  const [mode, setMode] = useChatMode();

  return (
    <div className="flex flex-1 min-h-0 min-w-0 flex-col gap-1">
      {/* Banda arriba con el toggle — no roba mucha altura */}
      <div className="flex shrink-0 items-center justify-end">
        <ChatModeToggle mode={mode} onChange={setMode} />
      </div>

      {/* Cuerpo del chat ocupa el resto del espacio */}
      <div className="flex flex-1 min-h-0 min-w-0 flex-col">
        <Suspense fallback={<ModeFallback />}>
          {mode === "terminal" ? (
            <ChatTerminal isActive={isActive} />
          ) : (
            <ChatModern />
          )}
        </Suspense>
      </div>
    </div>
  );
}
