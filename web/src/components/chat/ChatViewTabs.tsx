/**
 * ChatViewTabs — la barra segmentada Modern · Terminal · Visualización ·
 * Media · Tareas, autocontenida (lee/escribe los stores de modo y panel
 * directamente).
 *
 * Vive en DOS lugares con el mismo componente: junto a "Uso de tokens" en el
 * header del chat moderno (para no robarle altura al chat) y en la banda
 * superior del modo terminal. useChatMode/useSidePanel son stores a nivel
 * módulo, así que todas las instancias quedan sincronizadas.
 *
 * Con el panel lateral abierto el header pierde ~430px de ancho y las 5
 * pestañas no entran: la barra colapsa a una hamburguesa con menú
 * desplegable (mismas entradas, mismo estado activo).
 */

import { useEffect, useRef, useState } from "react";
import {
  Activity,
  Images,
  Menu,
  MessageSquare,
  SquareKanban,
  Terminal,
} from "lucide-react";
import { useChatMode } from "./hooks/useChatMode";
import {
  setSidePanel,
  toggleSidePanel,
  useSidePanel,
  type SidePanelTab,
} from "./sidePanelStore";

interface TabEntry {
  key: string;
  label: string;
  title: string;
  icon: React.ReactNode;
  active: boolean;
  onSelect: () => void;
}

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
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const openPanel = (tab: SidePanelTab) => {
    // El panel vive en el chat moderno: desde terminal, primero cambiamos y
    // ABRIMOS (setSidePanel, no toggle) — si el panel quedó persistido en esta
    // misma pestaña, un toggle lo cerraría y terminaríamos en modern sin panel.
    if (mode !== "modern") {
      setMode("modern");
      setSidePanel(tab);
      return;
    }
    toggleSidePanel(tab);
  };

  // Con el panel abierto, la barra colapsa a hamburguesa para no apretar el
  // header (el panel le roba ~430px de ancho al chat). Solo aplica en modo
  // moderno: el panel NO se renderiza en modo terminal, así que ahí no roba
  // ancho y las 5 pestañas entran — colapsar sería gratuito y confuso.
  const collapsed = mode === "modern" && sidePanel !== null;

  useEffect(() => {
    if (!collapsed) {
      // El menú no existe colapsado=false; limpiar al expandir. Diferido para
      // no encadenar setState sincrónico dentro del render del effect.
      const t = window.setTimeout(() => setMenuOpen(false), 0);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [collapsed]);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  const entries: TabEntry[] = [
    {
      key: "modern",
      label: "Modern",
      title: "Modo moderno — burbujas tipo chat",
      icon: <MessageSquare className="size-3.5" />,
      active: mode === "modern",
      onSelect: () => setMode("modern"),
    },
    {
      key: "terminal",
      label: "Terminal",
      title: "Modo terminal — interfaz CLI clásica",
      icon: <Terminal className="size-3.5" />,
      active: mode === "terminal",
      onSelect: () => setMode("terminal"),
    },
    {
      key: "viz",
      label: "Visualización",
      title: "Visualización — mirá a los agentes trabajar en vivo",
      icon: <Activity className="size-3.5" />,
      active: mode === "modern" && sidePanel === "viz",
      onSelect: () => openPanel("viz"),
    },
    {
      key: "media",
      label: "Media",
      title: "Media — todo el contenido generado (imágenes/videos)",
      icon: <Images className="size-3.5" />,
      active: mode === "modern" && sidePanel === "media",
      onSelect: () => openPanel("media"),
    },
    {
      key: "tasks",
      label: "Tareas",
      title: "Tareas — kanban simple de la conversación",
      icon: <SquareKanban className="size-3.5" />,
      active: mode === "modern" && sidePanel === "tasks",
      onSelect: () => openPanel("tasks"),
    },
  ];

  if (collapsed) {
    const activeEntry = entries.find((e) => e.active);
    return (
      <div ref={menuRef} className="relative">
        {/* Disclosure simple (no un menú ARIA completo): botón que expande un
            popover de botones nativos. Tab/Enter alcanzan; cada item expone
            aria-pressed para reflejar el activo. */}
        <button
          type="button"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
          title="Vistas del chat"
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-foreground/10 bg-background/40 px-2.5 text-xs text-foreground shadow-sm supports-[backdrop-filter]:backdrop-blur-xl"
        >
          <Menu className="size-4" />
          {activeEntry && (
            <span className="hidden items-center gap-1 text-muted-foreground sm:inline-flex">
              {activeEntry.icon}
              {activeEntry.label}
            </span>
          )}
        </button>
        {menuOpen && (
          <div className="absolute right-0 top-full z-40 mt-1 w-44 rounded-lg border border-border/60 bg-popover p-1 shadow-lg">
            {entries.map((e) => (
              <button
                key={e.key}
                type="button"
                aria-pressed={e.active}
                title={e.title}
                onClick={() => {
                  setMenuOpen(false);
                  e.onSelect();
                }}
                className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition-colors ${
                  e.active
                    ? "bg-[#6C4FD6]/20 text-foreground"
                    : "text-muted-foreground hover:bg-muted/30 hover:text-foreground"
                }`}
              >
                {e.icon}
                {e.label}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label="Vista del chat"
      className="inline-flex items-center gap-0.5 rounded-lg border border-foreground/10 bg-background/40 p-1 shadow-sm supports-[backdrop-filter]:backdrop-blur-xl"
    >
      {entries.slice(0, 2).map((e) => (
        <TabChip
          key={e.key}
          active={e.active}
          onClick={e.onSelect}
          title={e.title}
          icon={e.icon}
          label={e.label}
        />
      ))}
      <span className="mx-1 h-4 w-px bg-foreground/10" aria-hidden />
      {entries.slice(2).map((e) => (
        <TabChip
          key={e.key}
          active={e.active}
          onClick={e.onSelect}
          title={e.title}
          icon={e.icon}
          label={e.label}
        />
      ))}
    </div>
  );
}
