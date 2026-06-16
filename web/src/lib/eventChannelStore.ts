/**
 * Tiny module-level store publishing the live event channel id.
 *
 * The embedded ChatPage owns a PTY whose TUI gateway publishes JSON-RPC
 * events to `/api/pub?channel=<id>`; anyone holding the channel id can
 * subscribe to the mirrored feed at `/api/events?channel=<id>`.  The channel
 * id is generated inside ChatPage (per mount / per resume), so pages that
 * want the same live feed (Visualization) read it from here instead of
 * spawning a second PTY.
 *
 * Deliberately not React context: ChatPage renders in a persistent host
 * outside <Routes>, and a module store avoids threading a provider through
 * App.tsx. Consumers use the `useActiveEventChannel()` hook below.
 */

import { useSyncExternalStore } from "react";

let activeChannel: string | null = null;

const listeners = new Set<() => void>();

export function setActiveEventChannel(channel: string | null): void {
  if (activeChannel === channel) return;
  activeChannel = channel;
  for (const l of listeners) l();
}

export function getActiveEventChannel(): string | null {
  return activeChannel;
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** React hook — re-renders when the chat's event channel appears/changes. */
export function useActiveEventChannel(): string | null {
  return useSyncExternalStore(subscribe, getActiveEventChannel);
}
