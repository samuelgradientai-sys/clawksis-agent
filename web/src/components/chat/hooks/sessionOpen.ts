/**
 * Attaching the chat to a conversation: which session to open on connect, the
 * transcript a resume hands back, and the header state it implies. Pure or
 * RPC-parameterised so the hook only sequences them.
 */

import { api } from "@/lib/api";
import { mapHistoryMessages } from "./chatHistory";
import { withInflight, type InflightSnapshot } from "./chatTranscript";
import { applySessionInfo } from "./sessionInfo";
import type { ChatMessage, SessionInfo } from "./useChatGateway";

type Row = Record<string, unknown>;
export type Rpc = (method: string, params?: Record<string, unknown>) => Promise<unknown>;

/** `session.resume` / `session.create` result fields the chat reads. */
export interface ResumeResult {
  session_id?: string;
  stored_session_id?: string;
  messages?: Row[];
  messages_omitted?: boolean;
  info?: Row;
  running?: boolean;
  inflight?: InflightSnapshot | null;
  open_requests?: unknown;
  pending_approval?: unknown;
}

export interface OpenedSession {
  /** Live sid: what prompt.submit / slash.exec address. */
  sid: string;
  /** Stored (DB) key: what a reconnect resumes and the sidebar highlights. */
  storedKey: string | null;
  resume: ResumeResult | null;
}

export async function resumeStored(rpc: Rpc, key: string): Promise<OpenedSession> {
  const r = ((await rpc("session.resume", { session_id: key })) ?? {}) as ResumeResult;
  return { sid: r.session_id || key, storedKey: key, resume: r };
}

/** Mint a fresh conversation. Its stored key comes from the create result: a
 *  reconnect resumes by stored key, and the live sid is not one (#9). */
export async function createSession(rpc: Rpc): Promise<OpenedSession | null> {
  const created = ((await rpc("session.create", { source: "dashboard" })) ?? {}) as ResumeResult;
  if (!created.session_id) return null;
  return { sid: created.session_id, storedKey: created.stored_session_id || null, resume: created };
}

/** The conversation to show on (re)connect: the one already selected, else the
 *  most recent one with messages, else a new one. */
export async function openInitialSession(rpc: Rpc, selectedKey: string | null): Promise<OpenedSession | null> {
  if (selectedKey) {
    try {
      return await resumeStored(rpc, selectedKey);
    } catch (err) {
      console.warn("[useChatGateway] re-resume of selected session failed", err);
    }
  }
  try {
    const recent = (await rpc("session.most_recent", { min_messages: 1 })) as { session_id?: string } | null;
    if (recent?.session_id) return await resumeStored(rpc, recent.session_id);
  } catch (err) {
    console.warn("[useChatGateway] most recent session could not be resumed", err);
  }
  return createSession(rpc);
}

/** The transcript to show for an opened session: the resume's own messages
 *  when it carried them, else `session.history`; plus any turn still running. */
export async function loadTranscript(rpc: Rpc, opened: OpenedSession, idPrefix: string): Promise<ChatMessage[]> {
  const r = opened.resume;
  if (r && Array.isArray(r.messages) && !r.messages_omitted) {
    return withInflight(mapHistoryMessages(r.messages, idPrefix), r.inflight);
  }
  try {
    const history = (await rpc("session.history", { session_id: opened.sid })) as { messages?: Row[] } | null;
    return withInflight(mapHistoryMessages(history?.messages ?? [], idPrefix), r?.inflight);
  } catch (err) {
    console.warn("[useChatGateway] session.history failed (empty session)", err);
    return withInflight([], r?.inflight);
  }
}

/** The stored transcript over REST: shown at once while the (slow) resume
 *  builds the agent. Best effort — the resume brings the messages anyway. */
export async function fastHistory(storedId: string): Promise<ChatMessage[]> {
  try {
    const page = await api.getSessionMessages(storedId);
    return mapHistoryMessages((page?.messages ?? []) as unknown as Row[], "hist-" + storedId);
  } catch {
    return [];
  }
}

/** A resumed conversation is busy while its turn runs (queue, not 4009). */
export function resumeIsBusy(r: ResumeResult | null): boolean {
  const inflight = r?.inflight;
  return Boolean(r?.running || (inflight && (inflight.streaming || inflight.assistant)));
}

export function sessionFromResume(prev: SessionInfo, opened: OpenedSession): SessionInfo {
  const base = { ...prev, sessionId: opened.sid, sessionKey: opened.storedKey ?? prev.sessionKey };
  return applySessionInfo(base, opened.resume?.info ?? {}, opened.sid);
}

/** Header reset while a conversation switch is in flight. */
export function switchingSession(prev: SessionInfo, liveSid: string | null, key: string): SessionInfo {
  return {
    ...prev,
    sessionId: liveSid,
    sessionKey: key,
    model: null,
    modelProvider: null,
    tokensUsed: 0,
    tokensMax: 0,
    title: null,
    reasoningEffort: undefined,
  };
}

/** `session.usage` totals for the header; the first id that knows the session wins. */
export async function readUsage(rpc: Rpc, ids: string[]): Promise<{ total: number; max: number } | null> {
  for (const sid of [...new Set(ids)].filter(Boolean)) {
    try {
      const usage = ((await rpc("session.usage", { session_id: sid })) ?? {}) as Row;
      const total = Number(usage.total ?? usage.total_tokens ?? usage.tokens_used ?? 0) || 0;
      const max = Number(usage.context_max ?? usage.tokens_max ?? 0) || 0;
      if (total > 0 || max > 0) return { total, max };
    } catch (err) {
      console.warn("[useChatGateway] session.usage failed during token restore", sid, err);
    }
  }
  return null;
}

/** The friendlier copy for "the gateway no longer has that session". */
export function sessionErrorText(err: unknown, fallback: string, goneText: string): string {
  const raw = err instanceof Error ? err.message : fallback;
  return /4007|session not found/i.test(raw) ? goneText : raw.replace(/^\d+:\s*/, "");
}
