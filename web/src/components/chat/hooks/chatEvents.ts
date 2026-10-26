/**
 * Gateway `event` notifications → chat state, as a table of per-event handlers
 * (the repo's table-driven dispatch, instead of one switch inside the hook).
 *
 * Turn-end discipline: `busy` (the composer's queue gate) clears only when the
 * turn really ended — `message.complete`, or `session.info` reporting
 * `running: false` once no submit of ours is still in flight. A status line,
 * a stream-open retry ("❌ Could not open a stream" before a fallback) or an
 * out-of-turn `error` never ends a turn; treating them as one let the local
 * queue fire a plain `prompt.submit` into the live turn and redirect it.
 */

import { notifyChatEventListeners } from "./chatEventListeners";
import { applySessionInfo, titleFromEvent, trackSessionIds } from "./sessionInfo";
import {
  appendReasoning,
  completeTurn,
  finishTool,
  sealStreaming,
  startTool,
  withStreamingBubble,
} from "./chatTranscript";
import type { ChatMessage, SessionInfo } from "./useChatGateway";
import { relayDashboardNavigate } from "@/lib/dashboard-navigation";
import { isBrowserTool, noteBrowserActivity } from "../browser-live/browserLiveStore";

type Payload = Record<string, unknown>;
type Update<T> = (update: (prev: T) => T) => void;

export interface GatewayEventFrame {
  type: string;
  /** Live session id (sid) the event belongs to; absent on global events. */
  session_id?: string;
  payload?: Payload;
}

/** Coalesces `message.delta` text into one render per animation frame. */
export interface DeltaBuffer {
  push(text: string): void;
  /** Cancel the pending flush and hand back what was buffered. */
  take(): string;
}

export function createDeltaBuffer(
  flush: (text: string) => void,
  schedule: (cb: () => void) => number = (cb) => requestAnimationFrame(cb),
  cancel: (handle: number) => void = (handle) => cancelAnimationFrame(handle),
): DeltaBuffer {
  let buffered = "";
  let handle: number | null = null;
  const take = () => {
    if (handle !== null) cancel(handle);
    handle = null;
    const text = buffered;
    buffered = "";
    return text;
  };
  return {
    push(text) {
      buffered += text;
      if (handle === null) handle = schedule(() => flush(take()));
    },
    take,
  };
}

/** What the gateway knows about the current turn, as the events tell it. */
export interface TurnTracker {
  /** A turn event (start, delta, tool) arrived since the last completion. */
  started: boolean;
  /** prompt.submit calls of ours the server has not answered yet. */
  submitsInFlight: number;
}

export interface ChatEventContext {
  setMessages: Update<ChatMessage[]>;
  setSession: Update<SessionInfo>;
  setBusy: (busy: boolean) => void;
  setErrorMessage: (message: string | null) => void;
  setLiveStatus: (text: string | null) => void;
  bumpSessions: () => void;
  ids: { liveSid: { current: string | null }; selectedKey: { current: string | null } };
  deltas: DeltaBuffer;
  turn: TurnTracker;
  requests: {
    cancel: (id: string) => void;
    cancelApprovals: (requestIds: string[]) => void;
  };
}

type Handler = (ctx: ChatEventContext, payload: Payload, evtSid: string | undefined) => void;

const text = (payload: Payload, key = "text") => (typeof payload[key] === "string" ? (payload[key] as string) : "");

function markStarted(ctx: ChatEventContext): void {
  ctx.turn.started = true;
  ctx.setBusy(true);
}

function endTurn(ctx: ChatEventContext): void {
  ctx.turn.started = false;
  ctx.setBusy(false);
  ctx.setLiveStatus(null);
}

/** The cumulative session total a `message.complete` carries (assigned, not summed). */
function usageTotal(usage: unknown): number {
  const u = (usage && typeof usage === "object" ? usage : {}) as Payload;
  const num = (v: unknown) => Number(v ?? 0) || 0;
  return num(u.total ?? u.total_tokens) || num(u.input ?? u.prompt) + num(u.output ?? u.completion);
}

const bump: Handler = (ctx) => ctx.bumpSessions();
const cancelRequest: Handler = (ctx, payload) => ctx.requests.cancel(text(payload, "id"));

const onReasoning: Handler = (ctx, payload) => {
  const chunk = text(payload);
  if (!chunk) return;
  ctx.setMessages((prev) => appendReasoning(prev, chunk));
  markStarted(ctx);
};

export const CHAT_EVENT_HANDLERS: Record<string, Handler> = {
  "session.info": (ctx, payload, evtSid) => {
    const liveId = trackSessionIds(ctx.ids, evtSid, payload);
    ctx.setSession((prev) => applySessionInfo(prev, payload, liveId));
    if (payload.running === false && ctx.turn.submitsInFlight === 0) endTurn(ctx);
  },
  // The backend titles the conversation (first message, then the model's summary).
  "session.title": (ctx, payload) => {
    ctx.setSession((prev) => ({ ...prev, title: titleFromEvent(payload) ?? prev.title }));
    ctx.bumpSessions();
  },
  "sessions.changed": bump,
  "message.start": (ctx) => {
    ctx.setMessages(withStreamingBubble);
    markStarted(ctx);
  },
  "reasoning.delta": onReasoning,
  "thinking.delta": onReasoning,
  "message.delta": (ctx, payload) => {
    const chunk = text(payload);
    if (!chunk) return;
    ctx.turn.started = true;
    ctx.setLiveStatus(null);
    ctx.deltas.push(chunk);
  },
  "message.complete": (ctx, payload) => {
    const buffered = ctx.deltas.take();
    ctx.setMessages((prev) => completeTurn(prev, buffered, payload));
    endTurn(ctx);
    const total = usageTotal(payload.usage);
    if (total) ctx.setSession((prev) => ({ ...prev, tokensUsed: total }));
  },
  "tool.start": (ctx, payload) => {
    ctx.setMessages((prev) => startTool(prev, payload));
    markStarted(ctx);
    if (isBrowserTool(payload.name)) noteBrowserActivity(ctx.ids.selectedKey.current, payload.name as string);
  },
  "tool.complete": (ctx, payload) => ctx.setMessages((prev) => finishTool(prev, payload)),
  // A delegated subagent browsing (a mass search fans out to several): open the live panel too.
  "subagent.tool": (ctx, payload) => {
    if (isBrowserTool(payload.tool_name)) noteBrowserActivity(ctx.ids.selectedKey.current, payload.tool_name as string);
  },
  // A session-level failure. Before any turn event it is the refusal of the
  // submit we just made (ownership, cancelled before the agent was ready): that
  // turn never runs, so release the composer. Mid-turn it is out of band.
  error: (ctx, payload) => {
    ctx.setErrorMessage(text(payload, "message") || "Unknown error");
    ctx.setLiveStatus(null);
    if (ctx.turn.started) return;
    const buffered = ctx.deltas.take();
    ctx.setMessages((prev) => sealStreaming(prev, buffered));
    endTurn(ctx);
  },
  // Retry / fallback / rate-limit progress (also "❌ …" lines, which a fallback
  // may still recover from): shown live, never treated as the end of the turn.
  "status.update": (ctx, payload) => {
    const line = text(payload);
    if (line) ctx.setLiveStatus(line);
  },
  "request.cancel": cancelRequest,
  // The agent's dashboard_open: follow it only for the conversation on screen.
  "dashboard.navigate": (_ctx, payload) => relayDashboardNavigate(payload),
  "approval.cancelled": (ctx, payload) => {
    const ids = Array.isArray(payload.request_ids) ? payload.request_ids.filter((v) => typeof v === "string") : [];
    ctx.requests.cancelApprovals(ids as string[]);
  },
};

/** Events of a conversation that is not the one on screen still matter for the
 *  list and for a withdrawn question card; nothing else of theirs may render. */
const FOREIGN_EVENT_HANDLERS: Record<string, Handler> = {
  "session.title": bump,
  "sessions.changed": bump,
  "request.cancel": cancelRequest,
};

/** The WebSocket carries every session bound to it (parallel chats, crons, a
 *  conversation switched away from). Only the open conversation's events — and
 *  global ones without a `session_id` — reach the transcript; while no live sid
 *  is known (connecting, switching) every session-scoped event is foreign. */
export function isOwnEvent(liveSid: string | null, evtSid: string | undefined): boolean {
  return !evtSid || (!!liveSid && evtSid === liveSid);
}

export function dispatchChatEvent(ctx: ChatEventContext, event: GatewayEventFrame): void {
  const own = isOwnEvent(ctx.ids.liveSid.current, event.session_id);
  const handler = (own ? CHAT_EVENT_HANDLERS : FOREIGN_EVENT_HANDLERS)[event.type];
  handler?.(ctx, event.payload ?? {}, event.session_id);
  if (own) notifyChatEventListeners(event);
}
