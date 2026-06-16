/**
 * ChatRouter — Wrapper que renderiza el modo terminal o moderno según la
 * preferencia del usuario (persistida en localStorage).
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
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="flex items-center justify-end px-1">
        <ChatModeToggle mode={mode} onChange={setMode} />
      </div>

      <div className="flex-1 min-h-0">
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
