/**
 * ChatViewTabs — la barra segmentada Modern · Terminal · Visualización ·
 * Media, autocontenida (lee/escribe los stores de modo y panel directamente).
 *
 * Vive en DOS lugares con el mismo componente: junto a "Uso de tokens" en el
 * header del chat moderno (para no robarle altura al chat) y en la banda
 * superior del modo terminal. useChatMode/useSidePanel son stores a nivel
 * módulo, así que todas las instancias quedan sincronizadas.
 */

import { Activity, Images, MessageSquare, Terminal } from "lucide-react";
import { useChatMode } from "./hooks/useChatMode";
import {
  toggleSidePanel,
  useSidePanel,
  type SidePanelTab,
} from "./sidePanelStore";

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
      <span className="hidden lg:inline">{label}</span>
    </button>
  );
}

export function ChatViewTabs() {
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
  );
}
