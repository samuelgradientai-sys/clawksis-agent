/**
 * Pure transitions of the chat transcript (a `ChatMessage[]`), one per gateway
 * event or user action. Kept out of the hook so each can be tested on its own
 * and the hook stays a thin owner of state.
 */

import type { ChatMessage } from "./useChatGateway";

type Msgs = ChatMessage[];
type Payload = Record<string, unknown>;

let seq = 0;
const uid = (prefix: string) => prefix + "-" + Date.now() + "-" + ++seq;

export function assistantBubble(fields: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: uid("asst"),
    role: "assistant",
    content: "",
    toolCalls: [],
    streaming: true,
    timestamp: Date.now(),
    ...fields,
  };
}

export function userBubble(content: string, fields: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: uid("usr"),
    role: "user",
    content,
    toolCalls: [],
    streaming: false,
    timestamp: Date.now(),
    ...fields,
  };
}

function openAssistant(prev: Msgs): ChatMessage | undefined {
  const last = prev[prev.length - 1];
  return last && last.role === "assistant" && last.streaming ? last : undefined;
}

function replaceLast(prev: Msgs, next: ChatMessage): Msgs {
  return [...prev.slice(0, -1), next];
}

/** `message.start`: reuse the bubble a `reasoning.delta` already opened. */
export function withStreamingBubble(prev: Msgs): Msgs {
  return openAssistant(prev) ? prev : [...prev, assistantBubble({ reasoning: "" })];
}

export function appendReasoning(prev: Msgs, text: string): Msgs {
  const last = openAssistant(prev);
  if (!last) return [...prev, assistantBubble({ reasoning: text })];
  return replaceLast(prev, { ...last, reasoning: (last.reasoning ?? "") + text });
}

/** Buffered `message.delta` text. With no open bubble we joined a stream that
 *  started before we looked (a conversation running in the background). */
export function appendContent(prev: Msgs, text: string): Msgs {
  if (!text) return prev;
  const last = openAssistant(prev);
  if (!last) return [...prev, assistantBubble({ content: text })];
  return replaceLast(prev, { ...last, content: last.content + text });
}

function isEmptyBubble(m: ChatMessage): boolean {
  return !m.content.trim() && m.toolCalls.length === 0 && !(m.reasoning ?? "").trim();
}

/** Close the open bubble without a final payload (a turn that will never
 *  complete here); an empty one is dropped rather than left as a bare avatar. */
export function sealStreaming(prev: Msgs, buffered: string): Msgs {
  const last = openAssistant(prev);
  if (!last) return prev;
  const sealed = { ...last, content: last.content + buffered, streaming: false };
  return isEmptyBubble(sealed) ? prev.slice(0, -1) : replaceLast(prev, sealed);
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** The reply a `message.complete` settles on. Streamed text wins, except when
 *  the backend rewrote it (`response_transformed`) or nothing streamed — a
 *  non-streaming provider, or a failed turn whose account rides only in `text`
 *  (tui_gateway/prompt_turn.py `_turn_outcome`). */
export function finalReplyText(streamed: string, payload: Payload): string {
  const text = str(payload.text);
  if (payload.response_reused) return streamed;
  if (text.trim() && (payload.response_transformed || !streamed.trim())) return text;
  if (!streamed.trim() && payload.status === "error") return str(payload.error).trim();
  return streamed;
}

function persistedTurn(payload: Payload): { user?: number; assistant?: number } {
  const turn = payload.persisted_turn;
  if (!turn || typeof turn !== "object") return {};
  const t = turn as Payload;
  const num = (v: unknown) => (typeof v === "number" ? v : undefined);
  return { user: num(t.user_row_id), assistant: num(t.final_assistant_row_id) };
}

/** Give the newest user bubble without a durable id the row the turn wrote. */
export function bindLastUserRowId(prev: Msgs, rowId: number | undefined): Msgs {
  if (rowId === undefined || prev.some((m) => m.rowId === rowId)) return prev;
  for (let i = prev.length - 1; i >= 0; i--) {
    if (prev[i].role !== "user") continue;
    if (prev[i].rowId !== undefined) return prev;
    return prev.map((m, j) => (j === i ? { ...m, rowId } : m));
  }
  return prev;
}

/** `message.complete`: seal the open bubble with the authoritative reply, or
 *  create the final message when the turn finished out of view. */
export function completeTurn(prev: Msgs, buffered: string, payload: Payload): Msgs {
  const ids = persistedTurn(payload);
  const reasoning = str(payload.reasoning) || undefined;
  const last = openAssistant(prev);
  let next: Msgs;
  if (last) {
    const content = finalReplyText(last.content + buffered, payload);
    next = replaceLast(prev, {
      ...last,
      content,
      streaming: false,
      reasoning: reasoning || last.reasoning,
      rowId: ids.assistant ?? last.rowId,
    });
    if (isEmptyBubble(next[next.length - 1])) next = next.slice(0, -1);
  } else {
    const content = finalReplyText(buffered, payload).trim();
    next = content
      ? [...prev, assistantBubble({ content, streaming: false, reasoning, rowId: ids.assistant })]
      : prev;
  }
  return bindLastUserRowId(next, ids.user);
}

export function startTool(prev: Msgs, payload: Payload): Msgs {
  const last = prev[prev.length - 1];
  if (!last || last.role !== "assistant") return prev;
  const args = payload.args && typeof payload.args === "object" ? (payload.args as Record<string, unknown>) : {};
  return replaceLast(prev, {
    ...last,
    toolCalls: [
      ...last.toolCalls,
      { id: str(payload.tool_id) || uid("tool"), name: str(payload.name) || "unknown", args, status: "running" },
    ],
  });
}

export function finishTool(prev: Msgs, payload: Payload): Msgs {
  const toolId = str(payload.tool_id);
  return prev.map((msg) => {
    const idx = msg.role === "assistant" ? msg.toolCalls.findIndex((tc) => tc.id === toolId) : -1;
    if (idx === -1) return msg;
    const toolCalls = [...msg.toolCalls];
    toolCalls[idx] = {
      ...toolCalls[idx],
      status: payload.error ? "error" : "done",
      result: payload.result,
      summary: typeof payload.summary === "string" ? payload.summary : undefined,
      duration_s: typeof payload.duration_s === "number" ? payload.duration_s : undefined,
    };
    return { ...msg, toolCalls };
  });
}

export interface InflightSnapshot {
  user?: string;
  assistant?: string;
  streaming?: boolean;
}

/** A turn still running when we (re)attached: the stored history does not hold
 *  it yet, the gateway's snapshot does (prompt + text so far). */
export function withInflight(prev: Msgs, inflight: InflightSnapshot | null | undefined): Msgs {
  if (!inflight || !(inflight.streaming || inflight.assistant)) return prev;
  const next = [...prev];
  const inflightUser = (inflight.user || "").trim();
  const lastUser = [...next].reverse().find((m) => m.role === "user");
  if (inflightUser && lastUser?.content !== inflightUser) next.push(userBubble(inflightUser));
  next.push(assistantBubble({ content: inflight.assistant || "" }));
  return next;
}

/** Everything from the newest user bubble on (that bubble included). */
export function dropLastExchange(prev: Msgs): Msgs {
  for (let i = prev.length - 1; i >= 0; i--) {
    if (prev[i].role === "user") return prev.slice(0, i);
  }
  return prev;
}

export function setRowId(prev: Msgs, messageId: string, rowId: number | undefined): Msgs {
  if (rowId === undefined) return prev;
  return prev.map((m) => (m.id === messageId ? { ...m, rowId } : m));
}

/** A slash command's output, rendered as a system note (MessageBubble keys on the `slash-` id). */
export function slashOutputBubble(content: string): ChatMessage {
  return assistantBubble({ id: uid("slash"), content, streaming: false });
}

const isSlash = (m: ChatMessage) => m.role === "user" && String(m.content).trim().startsWith("/");

/**
 * The `prompt.submit` that replaces the user turn `messageId` with `newText`
 * (tui_gateway/methods_prompt.py truncation consent): the cut is aimed by the
 * turn's durable row and needs `confirm_truncate`; cutting before the first
 * turn would empty the transcript (`confirm_empty_truncate`); a cut that drops
 * later turns too is a deep one (`confirm_deep_truncate`). Null when the bubble
 * has no durable row yet — the caller looks it up first.
 */
export function editResubmitParams(
  messages: Msgs,
  messageId: string,
  newText: string,
): { index: number; params: Record<string, unknown> } | null {
  const index = messages.findIndex((m) => m.id === messageId);
  const target = messages[index];
  if (!target || target.role !== "user" || target.rowId === undefined) return null;
  const isTurn = (m: ChatMessage) => m.role === "user" && !isSlash(m);
  const params: Record<string, unknown> = {
    text: newText,
    truncate_before_row_id: target.rowId,
    confirm_truncate: true,
  };
  if (!messages.slice(0, index).some(isTurn)) params.confirm_empty_truncate = true;
  if (messages.slice(index + 1).some(isTurn)) params.confirm_deep_truncate = true;
  return { index, params };
}

/** The durable row of local bubble `index`, read from a fresh server
 *  transcript: the same text at the same occurrence among user turns. */
export function matchUserRowId(local: Msgs, index: number, fresh: Msgs): number | undefined {
  const text = String(local[index]?.content ?? "").trim();
  const occurrence = local.slice(0, index).filter((m) => m.role === "user" && String(m.content).trim() === text).length;
  const matches = fresh.filter((m) => m.role === "user" && String(m.content).trim() === text);
  return matches[occurrence]?.rowId;
}

/** True when the newest user bubble is a slash command the client ran (the
 *  stored history has no such turn, so regenerating it would undo the turn
 *  before it). */
export function lastUserIsSlash(messages: Msgs): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") return String(messages[i].content).trim().startsWith("/");
  }
  return false;
}
