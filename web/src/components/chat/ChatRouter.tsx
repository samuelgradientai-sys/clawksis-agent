/**
 * ChatRouter — Wrapper que renderiza el modo terminal o moderno según la
 * preferencia del usuario (persistida en localStorage).
 *
 * La banda superior es UNA sola barra de pestañas segmentada — Modern ·
 * Terminal · Visualización · Media — todas al mismo nivel y con el mismo
 * lenguaje visual. Modern/Terminal cambian el modo del chat; Visualización/
 * Media abren el panel lateral (y si estás en terminal, primero te llevan a
 * Modern, donde vive el panel).
 */

import { lazy, Suspense, type ComponentType } from "react";
import { Activity, Images, MessageSquare, Terminal } from "lucide-react";
import { useChatMode } from "./hooks/useChatMode";
import {
  toggleSidePanel,
  useSidePanel,
  type SidePanelTab,
} from "./sidePanelStore";
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

/** Chip de la barra unificada — mismo estilo para modos y paneles. */
function TabChip({
  active,
  onClick,
  title,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      title={title}
      className={
        "flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs transition-all duration-150 " +
        (active
          ? "bg-[#6C4FD6]/20 text-foreground shadow-sm ring-1 ring-[#6C4FD6]/40"
          : "text-muted-foreground hover:bg-muted/30 hover:text-foreground")
      }
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}

export default function ChatRouter({ isActive = true }: ChatRouterProps) {
  const [mode, setMode] = useChatMode();
  const sidePanel = useSidePanel();

  const openPanel = (tab: SidePanelTab) => {
    // El panel vive en el chat moderno: desde terminal, primero cambiamos.
    if (mode !== "modern") {
      setMode("modern");
      toggleSidePanel(tab);
      return;
    }
    toggleSidePanel(tab);
  };

  return (
    <div className="flex flex-1 min-h-0 min-w-0 flex-col gap-2">
      {/* Barra de pestañas unificada — modos y paneles al mismo nivel. */}
      <div className="flex shrink-0 items-center justify-end">
        <div
          role="group"
          aria-label="Vista del chat"
          className="inline-flex items-center gap-0.5 rounded-lg border border-foreground/10 bg-background/40 p-1 shadow-sm supports-[backdrop-filter]:backdrop-blur-xl"
        >
          <TabChip
            active={mode === "modern"}
            onClick={() => setMode("modern")}
            title="Modo moderno — burbujas tipo chat"
            icon={<MessageSquare className="size-3.5" />}
            label="Modern"
          />
          <TabChip
            active={mode === "terminal"}
            onClick={() => setMode("terminal")}
            title="Modo terminal — interfaz CLI clásica"
            icon={<Terminal className="size-3.5" />}
            label="Terminal"
          />
          <span className="mx-1 h-4 w-px bg-foreground/10" aria-hidden />
          <TabChip
            active={mode === "modern" && sidePanel === "viz"}
            onClick={() => openPanel("viz")}
            title="Visualización — mirá a los agentes trabajar en vivo"
            icon={<Activity className="size-3.5" />}
            label="Visualización"
          />
          <TabChip
            active={mode === "modern" && sidePanel === "media"}
            onClick={() => openPanel("media")}
            title="Media — todo el contenido generado (imágenes/videos)"
            icon={<Images className="size-3.5" />}
            label="Media"
          />
        </div>
      </div>

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
