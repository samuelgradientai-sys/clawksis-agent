/**
 * Observers of the open conversation's gateway events, beside the handler
 * table (chatEvents). A feature that follows a turn — voice mode speaks the
 * reply as it streams — subscribes here instead of growing useChatGateway or
 * ChatModern. Listeners see exactly what the transcript sees: events of the
 * conversation on screen and global ones, after the chat state handled them.
 */

import type { GatewayEventFrame } from "./chatEvents";

export type ChatEventListener = (event: GatewayEventFrame) => void;

const listeners = new Set<ChatEventListener>();

/** Start observing; the returned function stops it. */
export function subscribeChatEvents(listener: ChatEventListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function notifyChatEventListeners(event: GatewayEventFrame): void {
  for (const listener of [...listeners]) {
    // An observer's bug must not stop the transcript from rendering the turn.
    try {
      listener(event);
    } catch (err) {
      console.error("[chatEventListeners] listener failed", err);
    }
  }
}
