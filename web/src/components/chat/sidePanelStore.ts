/**
 * sidePanelStore — estado compartido del panel lateral del chat
 * (Visualización / Media / Tareas), fuera de ChatModern.
 *
 * Vive a nivel módulo para que la barra de pestañas unificada del ChatRouter
 * (Modern · Terminal · Visualización · Media · Tareas) pueda abrir/cerrar el
 * panel aunque ChatModern todavía no esté montado — p.ej. estando en modo
 * terminal, click en "Visualización" cambia a Modern Y abre el panel.
 * Persistido en localStorage (misma clave que usaba ChatModern).
 *
 * También guarda el ANCHO del panel (drag-resize en desktop), persistido
 * aparte para que sobreviva a abrir/cerrar.
 */

import { useSyncExternalStore } from "react";

export type SidePanelTab = "viz" | "media" | "tasks";

const STORAGE_KEY = "clawksis-chat-side-panel";

const WIDTH_STORAGE_KEY = "clawksis-chat-side-panel-width";

export const PANEL_MIN_WIDTH = 320;

export const PANEL_DEFAULT_WIDTH = 432;

export function panelMaxWidth(): number {
  if (typeof window === "undefined") return 1024;
  return Math.round(window.innerWidth * 0.7);
}

function clampWidth(w: number): number {
  return Math.min(Math.max(Math.round(w), PANEL_MIN_WIDTH), panelMaxWidth());
}

function read(): SidePanelTab | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === "viz" || v === "media" || v === "tasks" ? v : null;
  } catch {
    return null;
  }
}

function readWidth(): number {
  try {
    const v = Number(window.localStorage.getItem(WIDTH_STORAGE_KEY));
    return Number.isFinite(v) && v >= PANEL_MIN_WIDTH ? clampWidth(v) : PANEL_DEFAULT_WIDTH;
  } catch {
    return PANEL_DEFAULT_WIDTH;
  }
}

let current: SidePanelTab | null = read();

let currentWidth: number = readWidth();

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

export function setSidePanelWidth(width: number): void {
  currentWidth = clampWidth(width);
  try {
    window.localStorage.setItem(WIDTH_STORAGE_KEY, String(currentWidth));
  } catch {
    /* sin persistencia */
  }
  for (const l of listeners) l();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): SidePanelTab | null {
  return current;
}

function getWidthSnapshot(): number {
  return currentWidth;
}

export function useSidePanel(): SidePanelTab | null {
  return useSyncExternalStore(subscribe, getSnapshot, () => null);
}

export function useSidePanelWidth(): number {
  return useSyncExternalStore(subscribe, getWidthSnapshot, () => PANEL_DEFAULT_WIDTH);
}
