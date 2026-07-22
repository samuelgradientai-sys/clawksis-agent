/**
 * useChatMode — Hook para gestionar la preferencia de modo de chat.
 *
 * Estado a nivel módulo (useSyncExternalStore) para que TODAS las instancias
 * del hook en la misma pestaña se sincronicen — la barra de pestañas vive en
 * el header del chat moderno Y en la banda del modo terminal, y ambas tienen
 * que reaccionar al mismo cambio. Persiste en localStorage (clave
 * "clawksis:chat-mode") y se sincroniza entre pestañas del navegador vía el
 * evento storage.
 *
 * Default: "terminal" — para no romper la UX de usuarios existentes.
 */

import { useSyncExternalStore } from "react";

export type ChatMode = "terminal" | "modern";

const STORAGE_KEY = "clawksis:chat-mode";
const DEFAULT_MODE: ChatMode = "terminal";

function readMode(): ChatMode {
  if (typeof window === "undefined") return DEFAULT_MODE;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw === "modern" || raw === "terminal") return raw;
    return DEFAULT_MODE;
  } catch {
    return DEFAULT_MODE;
  }
}

let current: ChatMode = readMode();

const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

export function setChatMode(mode: ChatMode): void {
  current = mode;
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const onStorage = (e: StorageEvent) => {
    if (e.key !== STORAGE_KEY) return;
    if (e.newValue === "modern" || e.newValue === "terminal") {
      current = e.newValue;
      emit();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useChatMode(): [ChatMode, (mode: ChatMode) => void] {
  const mode = useSyncExternalStore(subscribe, () => current, () => DEFAULT_MODE);
  return [mode, setChatMode];
}
