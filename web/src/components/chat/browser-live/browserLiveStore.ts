/**
 * Which browser session the chat wants to watch, the agent's recent browser actions (from its
 * browser_* tool calls), and the one-time auto-open of the "Navegador" panel: the first browser tool
 * of a conversation opens it; closing it is respected afterwards.
 */

import { useSyncExternalStore } from "react";
import { setSidePanel } from "../sidePanelStore";

const MAX_ACTIONS = 6;

let preferredKey: string | null = null;
let actions: string[] = [];
const autoOpened = new Set<string>();
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
  if (autoOpened.has(key)) return;
  autoOpened.add(key);
  setSidePanel("browser");
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
  autoOpened.clear();
}
