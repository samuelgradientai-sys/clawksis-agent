/**
 * sidePanelStore — estado compartido del panel lateral del chat
 * (Visualización / Media), fuera de ChatModern.
 *
 * Vive a nivel módulo para que la barra de pestañas unificada del ChatRouter
 * (Modern · Terminal · Visualización · Media) pueda abrir/cerrar el panel
 * aunque ChatModern todavía no esté montado — p.ej. estando en modo terminal,
 * click en "Visualización" cambia a Modern Y abre el panel. Persistido en
 * localStorage (misma clave que usaba ChatModern).
 */

import { useSyncExternalStore } from "react";

export type SidePanelTab = "viz" | "media";

const STORAGE_KEY = "clawksis-chat-side-panel";

function read(): SidePanelTab | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === "viz" || v === "media" ? v : null;
  } catch {
    return null;
  }
}

let current: SidePanelTab | null = read();

const listeners = new Set<() => void>();

export function setSidePanel(tab: SidePanelTab | null): void {
  current = tab;
  try {
    if (tab) window.localStorage.setItem(STORAGE_KEY, tab);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* sin persistencia */
  }
  for (const l of listeners) l();
}

export function toggleSidePanel(tab: SidePanelTab): void {
  setSidePanel(current === tab ? null : tab);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): SidePanelTab | null {
  return current;
}

export function useSidePanel(): SidePanelTab | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}
