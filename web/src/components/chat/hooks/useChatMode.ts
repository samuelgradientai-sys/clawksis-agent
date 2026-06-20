/**
 * useChatMode — Hook para gestionar la preferencia de modo de chat.
 *
 * Persiste en localStorage (clave "clawksis:chat-mode") y se sincroniza
 * entre pestañas mediante el evento storage.
 *
 * Default: "terminal" — para no romper la UX de usuarios existentes que
 * están acostumbrados al chat actual con xterm. Los usuarios que prefieran
 * el modo moderno deben elegirlo explícitamente con el toggle.
 */

import { useCallback, useEffect, useState } from "react";

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

function writeMode(mode: ChatMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function useChatMode(): [ChatMode, (mode: ChatMode) => void] {
  const [mode, setMode] = useState<ChatMode>(readMode);

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      const next = e.newValue;
      if (next === "modern" || next === "terminal") {
        setMode(next);
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const updateMode = useCallback((next: ChatMode) => {
    writeMode(next);
    setMode(next);
  }, []);

  return [mode, updateMode];
}
