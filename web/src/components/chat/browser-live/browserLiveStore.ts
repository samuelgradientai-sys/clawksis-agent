/**
 * Which browser session the chat wants to watch, the agent's recent browser actions (from its
 * browser_* tool calls), and the auto-open of the "Navegador" panel: the first browser tool of a
 * TURN opens it (on phones too, where the panel is an overlay); if the user closes it during that
 * turn it stays closed until the next turn starts browsing.
 */

import { useSyncExternalStore } from "react";
import { setSidePanel } from "../sidePanelStore";

const MAX_ACTIONS = 6;

let preferredKey: string | null = null;
let actions: string[] = [];
// Conversations whose current turn already opened the panel.
const openedThisTurn = new Set<string>();
const listeners = new Set<() => void>();

export function isBrowserTool(name: unknown): boolean {
  return typeof name === "string" && name.startsWith("browser_");
}

/** Browser tool ``toolName`` started in the conversation stored as ``sessionKey``. */
export function noteBrowserActivity(sessionKey: string | null, toolName: string): void {
  const key = sessionKey ?? "";
  if (preferredKey !== sessionKey) actions = [];
  preferredKey = sessionKey;
  actions = [...actions.slice(1 - MAX_ACTIONS), toolName];
  for (const l of listeners) l();
  if (openedThisTurn.has(key)) return;
  openedThisTurn.add(key);
  setSidePanel("browser");
}

/** The conversation's turn ended: its next browser tool may open the panel again. */
export function noteTurnEnded(sessionKey: string | null): void {
  openedThisTurn.delete(sessionKey ?? "");
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePreferredBrowserKey(): string | null {
  return useSyncExternalStore(subscribe, () => preferredKey, () => null);
}

const NO_ACTIONS: string[] = [];

/** The agent's latest browser tool calls in the watched conversation, oldest first. */
export function useBrowserActions(): string[] {
  return useSyncExternalStore(subscribe, () => actions, () => NO_ACTIONS);
}

/** Test seam: forget what was auto-opened. */
export function resetBrowserLiveStore(): void {
  preferredKey = null;
  actions = [];
  openedThisTurn.clear();
}
