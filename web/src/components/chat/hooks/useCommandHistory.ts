/**
 * useCommandHistory — historial de inputs enviados, navegable con ↑/↓.
 *
 * Comportamiento tipo terminal/REPL:
 *   - `push(entry)` al enviar (deduplica consecutivos, cap, persiste).
 *   - `prev(draft)` (↑): la primera vez guarda el borrador actual y va al último
 *     enviado; siguientes ↑ retroceden en el historial.
 *   - `next()` (↓): avanza hacia entradas más recientes; al pasar el final
 *     restaura el borrador guardado.
 *   - `resetNav()` se llama al editar manualmente: el próximo ↑ arranca de cero.
 *
 * Persiste en localStorage para sobrevivir recargas. Todo en refs: navegar no
 * dispara re-render (sólo el setValue del composer lo hace).
 */
import { useCallback, useRef } from "react";

const STORAGE_KEY = "clawk-chat-input-history-v1";
const CAP = 100;

function load(): string[] {
  try {
    if (typeof window === "undefined") return [];
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const arr: unknown = JSON.parse(raw);
    return Array.isArray(arr)
      ? arr.filter((x): x is string => typeof x === "string")
      : [];
  } catch {
    return [];
  }
}

export interface CommandHistory {
  /** Registrar un input enviado. */
  push(entry: string): void;
  /** ↑ — entrada anterior (o null si no hay historial). `draft` = valor actual. */
  prev(draft: string): string | null;
  /** ↓ — entrada siguiente o el borrador; null si no se está navegando. */
  next(): string | null;
  /** Resetear la navegación (al editar manualmente). */
  resetNav(): void;
}

export function useCommandHistory(): CommandHistory {
  const entriesRef = useRef<string[]>(load());
  const indexRef = useRef<number>(-1); // -1 = editando el borrador en vivo
  const draftRef = useRef<string>("");

  const push = useCallback((entry: string) => {
    indexRef.current = -1;
    draftRef.current = "";
    const e = entry.trim();
    if (!e) return;
    const arr = entriesRef.current;
    if (arr[arr.length - 1] === e) return; // no duplicar consecutivos
    arr.push(e);
    if (arr.length > CAP) arr.splice(0, arr.length - CAP);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(arr));
    } catch {
      /* localStorage lleno/deshabilitado: el historial sigue en memoria */
    }
  }, []);

  const prev = useCallback((draft: string): string | null => {
    const arr = entriesRef.current;
    if (arr.length === 0) return null;
    if (indexRef.current === -1) {
      draftRef.current = draft;
      indexRef.current = arr.length - 1;
    } else if (indexRef.current > 0) {
      indexRef.current -= 1;
    }
    return arr[indexRef.current] ?? null;
  }, []);

  const next = useCallback((): string | null => {
    if (indexRef.current === -1) return null;
    const arr = entriesRef.current;
    indexRef.current += 1;
    if (indexRef.current >= arr.length) {
      indexRef.current = -1;
      return draftRef.current;
    }
    return arr[indexRef.current] ?? null;
  }, []);

  const resetNav = useCallback(() => {
    indexRef.current = -1;
  }, []);

  return { push, prev, next, resetNav };
}
