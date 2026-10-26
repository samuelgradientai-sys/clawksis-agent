/**
 * The agent asking the user something: server→client JSON-RPC requests
 * (tui_gateway/server_requests.py). A frame `{jsonrpc, id: "srq-…", method,
 * params: {session_id, …}}` is answered with `{jsonrpc, id, result}` carrying
 * the result shape tui_gateway/contracts/server_requests.py declares:
 *
 *   approval → {choice: "once" | "session" | "always" | "deny"}
 *   clarify  → {answers: {qid: answer | null}}  ({} cancels every question)
 *   sudo / secret → {value}  ('' = skipped)
 *
 * A method this chat cannot answer gets `-32601` at once, so the tool fails fast
 * instead of waiting out its deadline. The backend only sends these to a
 * WebSocket client that advertised `client.capabilities {server_requests: true}`.
 */

import { useCallback, useState } from "react";

type Params = Record<string, unknown>;

export type ApprovalChoice = "once" | "session" | "always" | "deny";

export interface ClarifyQuestionView {
  qid: string;
  question: string;
  choices: string[] | null;
  multiSelect: boolean;
}

interface RequestBase {
  id: string;
  /** Live sid the question belongs to (may be a conversation not on screen). */
  sessionId: string;
  /** Re-delivered from a resume's `open_requests` rather than a live frame. */
  replayed: boolean;
}

export type ChatServerRequest =
  | (RequestBase & {
      kind: "approval";
      command: string;
      description: string;
      choices: ApprovalChoice[];
      /** The approval queue entry; set when the answer goes through `approval.respond`. */
      requestId?: string;
      viaRpc?: boolean;
    })
  | (RequestBase & { kind: "clarify"; questions: ClarifyQuestionView[]; answers: Record<string, string> })
  | (RequestBase & { kind: "sudo"; command: string })
  | (RequestBase & { kind: "secret"; envVar: string; prompt: string });

export const JSON_RPC_METHOD_NOT_FOUND = -32601;
const APPROVAL_CHOICES: ApprovalChoice[] = ["once", "session", "always", "deny"];

const str = (v: unknown): string => (typeof v === "string" ? v : "");

/** A request frame: a string id (`srq-…`, never one of our numeric ids) plus a method. */
export function isServerRequestFrame(frame: unknown): frame is { id: string; method: string; params?: Params } {
  if (!frame || typeof frame !== "object") return false;
  const f = frame as Params;
  return typeof f.id === "string" && typeof f.method === "string" && f.method !== "event";
}

function approvalChoices(p: Params): ApprovalChoice[] {
  const listed = Array.isArray(p.choices) ? p.choices.filter((c): c is ApprovalChoice => APPROVAL_CHOICES.includes(c as ApprovalChoice)) : [];
  if (listed.length) return APPROVAL_CHOICES.filter((c) => listed.includes(c));
  return p.allow_permanent === false ? ["once", "session", "deny"] : APPROVAL_CHOICES;
}

function clarifyQuestions(p: Params): ClarifyQuestionView[] {
  const raw = Array.isArray(p.questions) ? p.questions : [];
  return raw
    .map((q) => (q && typeof q === "object" ? (q as Params) : {}))
    .filter((q) => str(q.qid) && str(q.question).trim())
    .map((q) => ({
      qid: str(q.qid),
      question: str(q.question).trim(),
      choices: Array.isArray(q.choices) && q.choices.length ? q.choices.filter((c): c is string => typeof c === "string") : null,
      multiSelect: q.multi_select === true,
    }));
}

function lockedAnswers(p: Params): Record<string, string> {
  const raw = p.answers && typeof p.answers === "object" ? (p.answers as Params) : {};
  return Object.fromEntries(Object.entries(raw).filter((e): e is [string, string] => typeof e[1] === "string"));
}

type Parser = (base: RequestBase, p: Params) => ChatServerRequest;

const PARSERS: Record<string, Parser> = {
  approval: (base, p) => ({
    ...base,
    kind: "approval",
    command: str(p.command),
    description: str(p.description) || "Comando potencialmente peligroso",
    choices: approvalChoices(p),
    requestId: str(p.request_id) || undefined,
  }),
  clarify: (base, p) => ({ ...base, kind: "clarify", questions: clarifyQuestions(p), answers: lockedAnswers(p) }),
  sudo: (base, p) => ({ ...base, kind: "sudo", command: str(p.command) }),
  secret: (base, p) => ({ ...base, kind: "secret", envVar: str(p.env_var), prompt: str(p.prompt) }),
};

/** The request this chat can show, or null when it has no card for the method. */
export function parseServerRequest(id: string, method: string, params: unknown, replayed = false): ChatServerRequest | null {
  const parse = PARSERS[method];
  if (!parse) return null;
  const p = params && typeof params === "object" ? (params as Params) : {};
  return parse({ id, sessionId: str(p.session_id), replayed }, p);
}

export function responseFrame(id: string, result: Params): string {
  return JSON.stringify({ jsonrpc: "2.0", id, result });
}

export function errorFrame(id: string, code: number, message: string): string {
  return JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } });
}

/** The questions still waiting on a session we (re)attached to: the resume
 *  result's `open_requests`, plus a queue approval that has no request frame
 *  (`pending_approval`), answered through `approval.respond`. */
export function requestsFromResume(result: unknown): ChatServerRequest[] {
  const r = (result && typeof result === "object" ? result : {}) as Params;
  const open = Array.isArray(r.open_requests) ? r.open_requests : [];
  const out: ChatServerRequest[] = [];
  for (const raw of open) {
    const e = (raw && typeof raw === "object" ? raw : {}) as Params;
    const req = parseServerRequest(str(e.id), str(e.method), e.params, true);
    if (req && req.id) out.push(req);
  }
  const pending = r.pending_approval && typeof r.pending_approval === "object" ? (r.pending_approval as Params) : null;
  const requestId = pending ? str(pending.request_id) : "";
  const covered = out.some((q) => q.kind === "approval" && (!requestId || q.requestId === requestId));
  if (pending && !covered) {
    const req = parseServerRequest("pending-approval:" + (requestId || "oldest"), "approval", { ...pending, session_id: str(r.session_id) }, true);
    if (req?.kind === "approval") out.push({ ...req, viaRpc: true });
  }
  return out;
}

/** Answer a request the chat could not show (no card for that method). */
export function unhandledReply(id: string, method: string): string {
  return errorFrame(id, JSON_RPC_METHOD_NOT_FOUND, "no handler for server request: " + method);
}

export interface AnswerTransport {
  /** Write a frame on the live socket; false when it is gone. */
  sendFrame: (frame: string) => boolean;
  rpc: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
}

/** Deliver the user's answer: the response frame for a request frame, or
 *  `approval.respond` for a queue approval replayed without one. */
export async function deliverAnswer(request: ChatServerRequest, result: Params, io: AnswerTransport): Promise<void> {
  if (request.kind === "approval" && request.viaRpc) {
    await io.rpc("approval.respond", {
      session_id: request.sessionId,
      choice: result.choice,
      ...(request.requestId ? { request_id: request.requestId } : {}),
    });
    return;
  }
  if (!io.sendFrame(responseFrame(request.id, result))) throw new Error("WebSocket not connected");
}

export interface ServerRequestQueue {
  requests: ChatServerRequest[];
  /** Show a request (a live frame or a replay); a re-delivered id replaces its card. */
  add: (request: ChatServerRequest) => void;
  /** The backend withdrew it (`request.cancel`), or we answered it. */
  remove: (id: string) => void;
  /** `approval.cancelled`: the queue entries behind these approval ids are gone. */
  removeApprovals: (requestIds: string[]) => void;
  /** The socket closed: a reconnect's resume re-delivers what is still open. */
  clear: () => void;
}

export function useServerRequestQueue(): ServerRequestQueue {
  const [requests, setRequests] = useState<ChatServerRequest[]>([]);
  const add = useCallback((request: ChatServerRequest) => {
    setRequests((prev) => [...prev.filter((r) => r.id !== request.id), request]);
  }, []);
  const remove = useCallback((id: string) => {
    setRequests((prev) => (prev.some((r) => r.id === id) ? prev.filter((r) => r.id !== id) : prev));
  }, []);
  const removeApprovals = useCallback((requestIds: string[]) => {
    const ids = new Set(requestIds);
    setRequests((prev) => {
      const next = prev.filter((r) => r.kind !== "approval" || !r.requestId || !ids.has(r.requestId));
      return next.length === prev.length ? prev : next;
    });
  }, []);
  const clear = useCallback(() => setRequests((prev) => (prev.length ? [] : prev)), []);
  return { requests, add, remove, removeApprovals, clear };
}
