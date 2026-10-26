/**
 * useChatGateway — Hook para conexión JSON-RPC con el gateway de Clawksis.
 *
 * Owns the chat's state and sequences the gateway calls; the per-event
 * handling (chatEvents), transcript transitions (chatTranscript), history
 * mapping (chatHistory), session attach (sessionOpen), the wire (gatewayWire)
 * and the agent's questions (serverRequests) live in sibling modules.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CLAWK_BASE_PATH, buildWsAuthParam } from "@/lib/api";
import { executeSlash, type SlashExecCallbacks } from "@/lib/slashExec";
import { mapHistoryMessages } from "./chatHistory";
import { createDeltaBuffer, dispatchChatEvent, type GatewayEventFrame, type TurnTracker } from "./chatEvents";
import {
  appendContent,
  dropLastExchange,
  editResubmitParams,
  lastUserIsSlash,
  matchUserRowId,
  setRowId,
  slashOutputBubble,
  userBubble,
} from "./chatTranscript";
import { PendingRpcs, routeGatewayFrame, trySend } from "./gatewayWire";
import {
  deliverAnswer,
  parseServerRequest,
  requestsFromResume,
  unhandledReply,
  useServerRequestQueue,
  type ChatServerRequest,
} from "./serverRequests";
import {
  fastHistory,
  loadTranscript,
  openInitialSession,
  readUsage,
  resumeIsBusy,
  sessionErrorText,
  sessionFromResume,
  switchingSession,
  type OpenedSession,
  type ResumeResult,
} from "./sessionOpen";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

export type ToolCallStatus = "running" | "done" | "error";

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: ToolCallStatus;
  result?: unknown;
  summary?: string;
  duration_s?: number;
}

export interface ChatImagePreview {
  previewUrl: string;
  name: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Cadena de razonamiento de modelos "thinking" (reasoning.delta). */
  reasoning?: string;
  toolCalls: ToolCall[];
  streaming: boolean;
  timestamp: number;
  /** Miniaturas de imágenes adjuntadas por el usuario (data URL local). */
  images?: ChatImagePreview[];
  /** Durable state.db row (history `row_id`, prompt.submit `user_row_id`):
   *  what an edit's truncation is aimed by. */
  rowId?: number;
}

export interface SessionInfo {
  sessionId: string | null;
  sessionKey: string | null;
  model: string | null;
  modelProvider: string | null;
  tokensUsed: number;
  tokensMax: number;
  title: string | null;
  /** The session's `reasoning_effort` ("" = configured default). */
  reasoningEffort?: string;
}

/** A composer prefill (`/undo` hands back the text of the turn it removed). */
export interface ComposerPrefill {
  text: string;
  seq: number;
}

interface UseChatGatewayResult {
  status: ConnectionStatus;
  session: SessionInfo;
  messages: ChatMessage[];
  busy: boolean;
  sendMessage: (text: string, images?: ChatImagePreview[]) => void;
  /** Drain one locally queued message: held by the server if a turn still runs. */
  sendQueued: (text: string) => void;
  interrupt: () => void;
  errorMessage: string | null;
  /** Progreso en vivo del turno (retry / cambio de fallback / rate-limit). */
  liveStatus: string | null;
  /** Descartar el error visible (lo dispara el banner de error). */
  clearError: () => void;
  /** Para hooks satélite que necesitan reusar la conexión (ej: useSessions) */
  sendRpc: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  /** true cuando es seguro usar sendRpc (WebSocket conectado) */
  readyForRpc: boolean;
  /** Cambiar a otra sesión: muestra el historial al instante y resume en 2do plano. */
  switchSession: (
    targetId: string,
    options?: { assumeLive?: boolean; sessionKey?: string | null },
  ) => Promise<void>;
  /** true mientras se resume una sesión (el agente se está construyendo). */
  resuming: boolean;
  /** Regenera la última respuesta: session.undo (borra último turno user+assistant) + re-submit del último prompt. */
  regenerateLast: () => Promise<void>;
  /** Editar un mensaje del usuario y reenviar al agente (estilo ChatGPT). */
  editAndResubmit: (messageId: string, newText: string) => Promise<void>;
  /** Contador que sube cuando el gateway anuncia sessions.changed / session.title. */
  sessionsRevision: number;
  /** Questions the agent is waiting on (approval, clarify, sudo, secret). */
  serverRequests: ChatServerRequest[];
  answerServerRequest: (request: ChatServerRequest, result: Record<string, unknown>) => void;
  prefill: ComposerPrefill | null;
}

const EMPTY_SESSION: SessionInfo = {
  sessionId: null,
  sessionKey: null,
  model: null,
  modelProvider: null,
  tokensUsed: 0,
  tokensMax: 0,
  title: null,
};

const SESSION_GONE_SEND =
  "La sesión activa ya no está disponible. Vuelve a seleccionar la conversación o crea una nueva.";
const SESSION_GONE_SWITCH =
  "No se pudo reabrir esta conversación en el gateway. Selecciónala de nuevo o crea una conversación nueva.";

function wsUrl(authName: string, authValue: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const qs = new URLSearchParams({ [authName]: authValue });
  return proto + "//" + window.location.host + CLAWK_BASE_PATH + "/api/ws?" + qs.toString();
}

export function useChatGateway(): UseChatGatewayResult {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Espejo de `messages` para callbacks estables (editAndResubmit) que no deben
  // recrearse en cada delta de streaming (romperían el memo de las burbujas).
  const messagesRef = useRef<ChatMessage[]>([]);
  const sessionMessagesCacheRef = useRef<Map<string, ChatMessage[]>>(new Map());

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  const [session, setSession] = useState<SessionInfo>(EMPTY_SESSION);
  // Sid VIVO de la conversación abierta: handleEvent (estable) filtra con él los
  // eventos de OTRAS sesiones (chats paralelos, crons). null mientras conecta o
  // cambia de conversación: entonces ningún evento con session_id es nuestro.
  const liveSidRef = useRef<string | null>(null);
  // KEY (id de DB) de la conversación que el usuario tiene abierta. En una
  // reconexión se re-reanuda ESTA sesión — no session.most_recent, que puede
  // ser un cron u otro chat recién corrido y pisaría el transcript en pantalla.
  const selectedKeyRef = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);
  // Sube con cada cambio de sesiones que anuncia el gateway (título nuevo, sesión
  // creada/borrada): el listado lo usa para refrescarse.
  const [sessionsRevision, setSessionsRevision] = useState(0);
  const [liveStatus, setLiveStatus] = useState<string | null>(null);
  const [prefill, setPrefill] = useState<ComposerPrefill | null>(null);
  const {
    requests: serverRequests,
    add: addRequest,
    remove: removeRequest,
    removeApprovals,
    clear: clearRequests,
  } = useServerRequestQueue();

  const wsRef = useRef<WebSocket | null>(null);
  const pendingRef = useRef(new PendingRpcs());
  const turnRef = useRef<TurnTracker>({ started: false, submitsInFlight: 0 });
  const switchSeqRef = useRef(0);
  // message.delta coalescing: one render per frame instead of a markdown
  // re-parse per token (deepseek & co. stream very fast).
  const [deltas] = useState(() => createDeltaBuffer((text) => setMessages((prev) => appendContent(prev, text))));

  const sendRpc = useCallback(
    (method: string, params?: Record<string, unknown>): Promise<unknown> => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return Promise.reject(new Error("WebSocket not connected"));
      }
      return pendingRef.current.call(method, params, (frame) => ws.send(frame));
    },
    [],
  );

  const handleEvent = useCallback(
    (event: GatewayEventFrame) =>
      dispatchChatEvent(
        {
          setMessages,
          setSession,
          setBusy,
          setErrorMessage,
          setLiveStatus,
          bumpSessions: () => setSessionsRevision((n) => n + 1),
          ids: { liveSid: liveSidRef, selectedKey: selectedKeyRef },
          deltas,
          turn: turnRef.current,
          requests: { cancel: removeRequest, cancelApprovals: removeApprovals },
        },
        event,
      ),
    [deltas, removeRequest, removeApprovals],
  );

  const handleServerRequest = useCallback(
    (id: string, method: string, params: unknown) => {
      const request = parseServerRequest(id, method, params);
      if (request) addRequest(request);
      else trySend(wsRef.current, unhandledReply(id, method));
    },
    [addRequest],
  );

  /** Show an opened conversation: transcript, live turn state, header, and
   *  the questions it still waits on. False when a newer switch superseded it. */
  const showOpened = useCallback(
    async (opened: OpenedSession, isCurrent: () => boolean): Promise<boolean> => {
      const view = await loadTranscript(sendRpc, opened, "hist-" + Date.now());
      if (!isCurrent()) return false;
      setMessages(view);
      for (const key of [opened.storedKey, opened.sid]) {
        if (key) sessionMessagesCacheRef.current.set(key, view);
      }
      liveSidRef.current = opened.sid;
      if (opened.storedKey) selectedKeyRef.current = opened.storedKey;
      setBusy(resumeIsBusy(opened.resume));
      setSession((prev) => sessionFromResume(prev, opened));
      requestsFromResume(opened.resume).forEach(addRequest);
      return true;
    },
    [sendRpc, addRequest],
  );

  useEffect(() => {
    let cancelled = false;
    // Auto-reconexión con backoff exponencial (túnel SSH, red móvil, restart).
    let reconnectDelay = 1_000;
    let reconnectTimer: number | undefined;

    async function attach() {
      // Si el usuario cambia de conversación mientras esta init corre,
      // switchSession avanza el seq → abortamos antes de pisar SU vista.
      const seqAtOpen = switchSeqRef.current;
      const isCurrent = () => !cancelled && seqAtOpen === switchSeqRef.current;
      try {
        const opened = await openInitialSession(sendRpc, selectedKeyRef.current);
        if (!isCurrent()) return;
        if (!opened) {
          setErrorMessage("No se pudo crear/obtener sesión");
          return;
        }
        await showOpened(opened, isCurrent);
      } catch (err) {
        console.error("[useChatGateway] session init failed", err);
        if (!cancelled) setErrorMessage(err instanceof Error ? err.message : "Session init failed");
      }
    }

    async function connect() {
      setStatus("connecting");
      setErrorMessage(null);
      try {
        const [authName, authValue] = await buildWsAuthParam();
        if (cancelled) return;
        const ws = new WebSocket(wsUrl(authName, authValue));
        wsRef.current = ws;

        ws.onopen = () => {
          if (cancelled) return;
          reconnectDelay = 1_000; // conexión sana → resetear el backoff
          setStatus("connected");
          setResuming(false);
          // Before anything else on this connection: we answer server→client
          // requests. Without it the backend withdraws every approval/clarify
          // for this socket as coming from an app too old to answer.
          void sendRpc("client.capabilities", { server_requests: true }).catch(() => undefined);
          void attach();
        };

        ws.onmessage = (ev) =>
          routeGatewayFrame(ev.data, {
            onEvent: handleEvent,
            onRequest: handleServerRequest,
            onResponse: (frame) => pendingRef.current.settle(frame),
          });

        ws.onclose = () => {
          // Nothing that waited on this socket can be answered any more.
          pendingRef.current.rejectAll("WebSocket closed");
          clearRequests();
          if (cancelled) return;
          // `busy` stays: the turn keeps running server-side, and the
          // reconnect's resume reports whether it still does.
          setStatus("disconnected");
          const delay = reconnectDelay;
          reconnectDelay = Math.min(reconnectDelay * 2, 15_000);
          reconnectTimer = window.setTimeout(() => {
            if (!cancelled) void connect();
          }, delay);
        };

        ws.onerror = () => {
          if (!cancelled) {
            setStatus("error");
            setErrorMessage("Connection error");
          }
        };
      } catch (err) {
        if (!cancelled) {
          setStatus("error");
          setErrorMessage(err instanceof Error ? err.message : "Unknown error");
        }
      }
    }

    void connect();

    const pending = pendingRef.current;
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
      wsRef.current = null;
      pending.rejectAll("WebSocket closed");
    };
  }, [handleEvent, handleServerRequest, sendRpc, showOpened, clearRequests]);

  /** prompt.submit with the bookkeeping every submit needs: the in-flight count
   *  that keeps a stale `running: false` from ending the turn, the durable row
   *  the server wrote for the bubble, and error reporting. False on failure. */
  const submitPrompt = useCallback(
    async (params: Record<string, unknown>, bubbleId?: string): Promise<boolean> => {
      turnRef.current.submitsInFlight++;
      try {
        const r = (await sendRpc("prompt.submit", params)) as { user_row_id?: number } | null;
        if (bubbleId) setMessages((prev) => setRowId(prev, bubbleId, r?.user_row_id));
        return true;
      } catch (err) {
        console.error("[useChatGateway] prompt.submit failed", err);
        setErrorMessage(sessionErrorText(err, "Failed to send message", SESSION_GONE_SEND));
        setLiveStatus(null);
        setBusy(false);
        return false;
      } finally {
        turnRef.current.submitsInFlight--;
      }
    },
    [sendRpc],
  );

  /** Reload the transcript from the server (a slash command rewound it). */
  const reloadTranscript = useCallback(async () => {
    const sid = liveSidRef.current;
    if (!sid) return;
    try {
      const history = (await sendRpc("session.history", { session_id: sid })) as {
        messages?: Array<Record<string, unknown>>;
      } | null;
      if (liveSidRef.current === sid) setMessages(mapHistoryMessages(history?.messages ?? [], "hist-" + Date.now()));
    } catch (err) {
      console.warn("[useChatGateway] session.history reload failed", err);
    }
  }, [sendRpc]);

  // Slash command (/model, /help, /status, skills, /retry, /undo …): the shared
  // dispatcher (slashExec) — same contract as the TUI.
  const runSlash = useCallback(
    (command: string, sid: string) => {
      setMessages((prev) => [...prev, userBubble(command)]);
      const callbacks: SlashExecCallbacks = {
        sys: (out) => out && setMessages((prev) => [...prev, slashOutputBubble(out)]),
        send: async (message, options) => {
          const bubble = options?.asUserTurn ? userBubble(message) : null;
          if (bubble) setMessages((prev) => [...prev, bubble]);
          setBusy(true);
          await submitPrompt({ session_id: sid, text: message }, bubble?.id);
        },
        prefill: (text) => setPrefill({ text, seq: Date.now() }),
        refresh: reloadTranscript,
      };
      executeSlash({ command, sessionId: sid, gw: { request: (m, p) => sendRpc(m, p) as never }, callbacks }).catch(
        (err) => setErrorMessage(err instanceof Error ? err.message.replace(/^\d+:\s*/, "") : "El comando falló"),
      );
    },
    [sendRpc, submitPrompt, reloadTranscript],
  );

  const submitText = useCallback(
    (text: string, images: ChatImagePreview[] | undefined, extra: Record<string, unknown>) => {
      if (!text.trim()) return;
      const sid = session.sessionId;
      if (!sid) {
        setErrorMessage("No hay sesión activa todavía");
        return;
      }
      // Nuevo turno: limpiar cualquier error previo + progreso en vivo.
      setErrorMessage(null);
      setLiveStatus(null);
      if (text.trim().startsWith("/")) return runSlash(text.trim(), sid);
      const bubble = userBubble(text, { images: images && images.length ? images : undefined });
      setMessages((prev) => [...prev, bubble]);
      // busy de inmediato (no esperando message.start): gate confiable para la cola.
      setBusy(true);
      void submitPrompt({ session_id: sid, text, ...extra }, bubble.id);
    },
    [session.sessionId, runSlash, submitPrompt],
  );

  const sendMessage = useCallback(
    (text: string, images?: ChatImagePreview[]) => submitText(text, images, {}),
    [submitText],
  );
  // `queued: true`: a turn the client believes ended may still be running; the
  // server then holds this message instead of redirecting the live turn.
  const sendQueued = useCallback((text: string) => submitText(text, undefined, { queued: true }), [submitText]);

  const interrupt = useCallback(() => {
    if (!session.sessionId) return;
    sendRpc("session.interrupt", { session_id: session.sessionId }).catch((err) => {
      console.error("[useChatGateway] session.interrupt failed", err);
    });
  }, [session.sessionId, sendRpc]);

  const answerServerRequest = useCallback(
    (request: ChatServerRequest, result: Record<string, unknown>) => {
      removeRequest(request.id);
      deliverAnswer(request, result, { sendFrame: (f) => trySend(wsRef.current, f), rpc: sendRpc }).catch((err) =>
        setErrorMessage("No se pudo enviar la respuesta: " + (err instanceof Error ? err.message : String(err))),
      );
    },
    [removeRequest, sendRpc],
  );

  const switchSession = useCallback(
    async (
      targetId: string,
      options?: { assumeLive?: boolean; sessionKey?: string | null },
    ): Promise<void> => {
      if (!targetId) return;
      const assumeLive = Boolean(options?.assumeLive);
      // new-chat-stored-session-contract-v1: targetId is the LIVE sid when
      // assumeLive (a fresh session.create); visualKey is the stored DB id.
      const visualKey = (options?.sessionKey || targetId).trim();
      const cache = sessionMessagesCacheRef.current;
      const currentKey = selectedKeyRef.current || liveSidRef.current;
      if (currentKey && messagesRef.current.length > 0) cache.set(currentKey, messagesRef.current);

      const mySeq = ++switchSeqRef.current;
      const isCurrent = () => mySeq === switchSeqRef.current;
      const cached = cache.get(visualKey) ?? cache.get(targetId);
      setMessages(cached ? [...cached] : []);
      setBusy(false);
      setErrorMessage(null);
      setLiveStatus(null);
      liveSidRef.current = assumeLive ? targetId : null;
      selectedKeyRef.current = visualKey;
      setSession((prev) => switchingSession(prev, assumeLive ? targetId : null, visualKey));
      // A session.create result is already live: nothing to resume.
      if (assumeLive) {
        setResuming(false);
        return;
      }
      setResuming(true);

      // 1) Historial al INSTANTE por HTTP (no construye el agente).
      const fastMsgs = await fastHistory(targetId);
      if (!isCurrent()) return;
      if (fastMsgs.length) {
        cache.set(targetId, fastMsgs);
        setMessages(fastMsgs);
      }

      // 2) Resume: construye el agente (lento) y deja la sesión VIVA.
      try {
        const r = ((await sendRpc("session.resume", { session_id: targetId })) ?? {}) as ResumeResult;
        const opened: OpenedSession = { sid: r.session_id || targetId, storedKey: targetId, resume: r };
        if (!(await showOpened(opened, isCurrent))) return;
        // session.usage puede tardar: no bloquea el cambio de chat.
        void readUsage(sendRpc, [targetId, opened.sid]).then((usage) => {
          if (usage && isCurrent()) setSession((prev) => ({ ...prev, tokensUsed: usage.total, tokensMax: usage.max }));
        });
      } catch (err) {
        console.error("[useChatGateway] switchSession failed", err);
        if (isCurrent()) {
          setSession((prev) => ({ ...prev, sessionId: null, sessionKey: targetId }));
          setErrorMessage(sessionErrorText(err, "Failed to switch session", SESSION_GONE_SWITCH));
        }
      } finally {
        if (isCurrent()) setResuming(false);
      }
    },
    [sendRpc, showOpened],
  );

  const regenerateLast = useCallback(async (): Promise<void> => {
    const sid = session.sessionId;
    if (busy || !sid) return;
    const before = messagesRef.current;
    // El último mensaje user es el prompt que produjo la última respuesta. Un
    // slash no se regenera: el history del backend no tiene ese turno, así que
    // session.undo borraría el turno real previo.
    const lastUser = [...before].reverse().find((m) => m.role === "user");
    if (!lastUser || lastUserIsSlash(before)) return;
    setMessages(dropLastExchange(before));
    try {
      await sendRpc("session.undo", { session_id: sid });
    } catch (err) {
      console.error("[useChatGateway] session.undo failed", err);
      setMessages(before);
      setErrorMessage(err instanceof Error ? err.message : "Failed to regenerate");
      return;
    }
    sendMessage(lastUser.content);
  }, [busy, session.sessionId, sendRpc, sendMessage]);

  /** The durable row of a bubble the server has written but we never learned
   *  (a submit whose receipt lacked it): read it back from session.history. */
  const lookUpRowId = useCallback(
    async (sid: string, local: ChatMessage[], index: number): Promise<number | undefined> => {
      try {
        const history = (await sendRpc("session.history", { session_id: sid })) as {
          messages?: Array<Record<string, unknown>>;
        } | null;
        return matchUserRowId(local, index, mapHistoryMessages(history?.messages ?? [], "lookup"));
      } catch {
        return undefined;
      }
    },
    [sendRpc],
  );

  // Editar un mensaje del usuario y reenviar desde ahí (estilo ChatGPT): el
  // backend (prompt.submit + truncate_before_row_id) reescribe history y DB, así
  // que sobrevive a navegar/recargar. Si el servidor rechaza, la vista vuelve.
  const editAndResubmit = useCallback(
    async (messageId: string, newText: string): Promise<void> => {
      const sid = session.sessionId;
      if (busy || !sid || !newText.trim() || newText.trim().startsWith("/")) return;
      let before = messagesRef.current;
      const index = before.findIndex((m) => m.id === messageId);
      if (index < 0 || before[index].role !== "user") return;
      if (before[index].rowId === undefined) {
        before = setRowId(before, messageId, await lookUpRowId(sid, before, index));
      }
      const plan = editResubmitParams(before, messageId, newText);
      if (!plan) {
        setErrorMessage("No se pudo ubicar ese mensaje en el historial guardado. Recarga la conversación e intenta de nuevo.");
        return;
      }
      const edited = userBubble(newText, { images: before[index].images });
      setMessages([...before.slice(0, plan.index), edited]);
      setBusy(true);
      if (!(await submitPrompt({ session_id: sid, ...plan.params }, edited.id))) setMessages(before);
    },
    [busy, session.sessionId, lookUpRowId, submitPrompt],
  );

  const clearError = useCallback(() => setErrorMessage(null), []);

  return {
    status,
    session,
    messages,
    busy,
    sendMessage,
    sendQueued,
    interrupt,
    errorMessage,
    liveStatus,
    clearError,
    sendRpc,
    readyForRpc: status === "connected",
    switchSession,
    resuming,
    regenerateLast,
    editAndResubmit,
    sessionsRevision,
    serverRequests,
    answerServerRequest,
    prefill,
  };
}
