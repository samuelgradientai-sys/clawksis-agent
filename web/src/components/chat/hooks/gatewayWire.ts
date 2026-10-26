/**
 * The chat's side of the gateway WebSocket wire: routing inbound frames, and
 * the client→server calls waiting for their response frame.
 *
 * Every call settles exactly once: with its response, or rejected when the
 * socket that carried it closes — a reply can never arrive on a new socket, and
 * a call left pending froze whatever awaited it (a conversation switch stuck
 * "Preparando conversación…", an image upload stuck uploading).
 */

import { isServerRequestFrame } from "./serverRequests";
import type { GatewayEventFrame } from "./chatEvents";

export interface FrameHandlers {
  onEvent: (event: GatewayEventFrame) => void;
  /** A server→client request (`srq-…` id): the agent asking the user. */
  onRequest: (id: string, method: string, params: unknown) => void;
  onResponse: (frame: RpcResponseFrame) => void;
}

/** Route one text frame: event notification, server→client request, or the
 *  response to one of our calls (numeric id). Anything else is dropped. */
export function routeGatewayFrame(data: unknown, handlers: FrameHandlers): void {
  if (typeof data !== "string") return;
  let frame: Record<string, unknown>;
  try {
    frame = JSON.parse(data);
  } catch {
    return;
  }
  if (!frame || typeof frame !== "object") return;
  const params = frame.params as GatewayEventFrame | undefined;
  if (frame.method === "event" && params && typeof params.type === "string") {
    handlers.onEvent(params);
  } else if (isServerRequestFrame(frame)) {
    handlers.onRequest(frame.id, frame.method, frame.params);
  } else if (typeof frame.id === "number") {
    handlers.onResponse(frame as unknown as RpcResponseFrame);
  }
}

export interface RpcResponseFrame {
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

interface Waiter {
  resolve: (result: unknown) => void;
  reject: (error: Error) => void;
}

export class PendingRpcs {
  private next = 1;
  private waiters = new Map<number, Waiter>();

  /** Register a call; `send` writes the request frame for the id it is given. */
  call(method: string, params: Record<string, unknown> | undefined, send: (frame: string) => void): Promise<unknown> {
    const id = this.next++;
    return new Promise((resolve, reject) => {
      this.waiters.set(id, { resolve, reject });
      try {
        send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
      } catch (err) {
        this.waiters.delete(id);
        reject(err instanceof Error ? err : new Error(String(err)));
      }
    });
  }

  /** Route a response frame; false when no call waits for that id. */
  settle(frame: RpcResponseFrame): boolean {
    const waiter = this.waiters.get(frame.id);
    if (!waiter) return false;
    this.waiters.delete(frame.id);
    if (frame.error) waiter.reject(new Error(frame.error.code + ": " + frame.error.message));
    else waiter.resolve(frame.result);
    return true;
  }

  /** The socket is gone: fail every call still waiting. */
  rejectAll(reason: string): void {
    const waiting = [...this.waiters.values()];
    this.waiters.clear();
    for (const waiter of waiting) waiter.reject(new Error(reason));
  }

  get size(): number {
    return this.waiters.size;
  }
}

/** Write one frame on a socket that may already be gone (an answer to a
 *  question the backend withdrew meanwhile is harmless to lose). */
export function trySend(ws: WebSocket | null, frame: string): boolean {
  if (!ws || ws.readyState !== WebSocket.OPEN) return false;
  try {
    ws.send(frame);
    return true;
  } catch {
    return false;
  }
}
