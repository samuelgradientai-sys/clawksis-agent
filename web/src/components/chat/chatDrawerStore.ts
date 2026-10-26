/**
 * Whether the conversation list is open as a drawer (phones). Module-level so
 * the header's button and the drawer share it without threading props through
 * ChatModern. Desktop ignores it: there the list is always inline.
 */

import { useSyncExternalStore } from "react";

let open = false;
const listeners = new Set<() => void>();

export function setChatDrawerOpen(next: boolean): void {
  if (open === next) return;
  open = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useChatDrawerOpen(): boolean {
  return useSyncExternalStore(subscribe, () => open, () => false);
}

/** True while `query` matches (e.g. a phone-width layout). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** Below Tailwind's `md`: the chat's phone layout. */
export const PHONE_QUERY = "(max-width: 767px)";
