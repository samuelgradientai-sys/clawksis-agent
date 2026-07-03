/**
 * ChatRouter — Wrapper que renderiza el modo terminal o moderno según la
 * preferencia del usuario (persistida en localStorage).
 *
 * La barra de pestañas (Modern · Terminal · Visualización · Media) es el
 * componente ChatViewTabs. En modo MODERNO vive dentro del header del chat
 * (junto a "Uso de tokens") para no robarle altura al chat; acá solo se
 * renderiza la banda cuando el modo es TERMINAL, que no tiene header propio.
 */

import { lazy, Suspense, type ComponentType } from "react";
import { useChatMode } from "./hooks/useChatMode";
import { ChatViewTabs } from "./ChatViewTabs";
import { ErrorBoundary } from "@/components/ErrorBoundary";

function ChatCrashFallback() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-sm text-muted-foreground">
        El chat tuvo un error y se detuvo, pero el resto del panel sigue
        funcionando.
      </p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="rounded-md bg-[#6C4FD6] px-3 py-1.5 text-sm text-white hover:bg-[#5a40c2] transition-colors"
      >
        Recargar
      </button>
    </div>
  );
}

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
  const [mode] = useChatMode();

  return (
    <div className="flex flex-1 min-h-0 min-w-0 flex-col gap-2">
      {/* En modo terminal las pestañas van en banda (no hay header propio);
          en modo moderno viven junto a "Uso de tokens" — chat más alto. */}
      {mode === "terminal" && (
        <div className="flex shrink-0 items-center justify-end">
          <ChatViewTabs />
        </div>
      )}

      {/* Cuerpo del chat ocupa el resto del espacio */}
      <div className="flex flex-1 min-h-0 min-w-0 flex-col">
        <ErrorBoundary resetKey={mode} fallback={<ChatCrashFallback />}>
          <Suspense fallback={<ModeFallback />}>
            {mode === "terminal" ? (
              <ChatTerminal isActive={isActive} />
            ) : (
              <ChatModern />
            )}
          </Suspense>
        </ErrorBoundary>
      </div>
    </div>
  );
}
