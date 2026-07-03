/**
 * useChatGateway — Hook para conexión JSON-RPC con el gateway de Clawksis.
 *
 * Fase 2.7 — versión completa con switchSession para sidebar de sesiones.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, CLAWK_BASE_PATH, buildWsAuthParam } from "@/lib/api";
import { executeSlash } from "@/lib/slashExec";

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
}

export interface SessionInfo {
  sessionId: string | null;
  model: string | null;
  modelProvider: string | null;
  tokensUsed: number;
  tokensMax: number;
  title: string | null;
}

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params?: Record<string, unknown>;
}

interface JsonRpcEvent {
  jsonrpc: "2.0";
  method: "event";
  params: {
    type: string;
    /** Live session id (sid) del gateway que emitió el evento. */
    session_id?: string;
    payload?: Record<string, unknown>;
  };
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

type IncomingMessage = JsonRpcEvent | JsonRpcResponse;

interface UseChatGatewayResult {
  status: ConnectionStatus;
  session: SessionInfo;
  messages: ChatMessage[];
  busy: boolean;
  sendMessage: (text: string, images?: ChatImagePreview[]) => void;
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
  switchSession: (targetId: string, options?: { assumeLive?: boolean }) => Promise<void>;
  /** true mientras se resume una sesión (el agente se está construyendo). */
  resuming: boolean;
  /** Regenera la última respuesta: session.undo (borra último turno user+assistant) + re-submit del último prompt. */
  regenerateLast: () => Promise<void>;
  /** Editar un mensaje del usuario y reenviar al agente (estilo ChatGPT). */
  editAndResubmit: (messageId: string, newText: string) => Promise<void>;
}

export function useChatGateway(): UseChatGatewayResult {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  // Espejo de `messages` para callbacks estables (editAndResubmit) que no deben
  // recrearse en cada delta de streaming (romperían el memo de las burbujas).
  const messagesRef = useRef<ChatMessage[]>([]);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  const [session, setSession] = useState<SessionInfo>({
    sessionId: null,
    model: null,
    modelProvider: null,
    tokensUsed: 0,
    tokensMax: 0,
    title: null,
  });
  // Sid VIVO de la conversación abierta, como ref para que handleEvent (estable)
  // pueda filtrar eventos de OTRAS sesiones sin re-suscribirse. El WS trae los
  // eventos de todas las sesiones del gateway (chats paralelos, crons).
  const liveSidRef = useRef<string | null>(null);
  // KEY (id de DB) de la conversación que el usuario tiene abierta. En una
  // reconexión se re-reanuda ESTA sesión — no session.most_recent, que puede
  // ser un cron u otro chat recién corrido y pisaría el transcript en pantalla.
  const selectedKeyRef = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);
  // Progreso en vivo del turno (retry / cambio de fallback / rate-limit). El
  // loop del agente lo reporta por eventos status.update; sin esto el Modern no
  // mostraba NADA durante la cascada de fallback (que dura minutos) y parecía
  // colgado. El Terminal sí los renderiza.
  const [liveStatus, setLiveStatus] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const nextIdRef = useRef(1);
  const pendingRef = useRef<Map<number, (resp: JsonRpcResponse) => void>>(
    new Map(),
  );

  // Coalescing de message.delta: deepseek (y cualquier modelo rápido) escupe
  // tokens a gran velocidad; aplicar setMessages por CADA token reparsea el
  // markdown completo (O(n^2)) y reflowea el scroll por token → tirones. Igual
  // que el TUI (turnController.scheduleStreaming), buffereamos los deltas y los
  // volcamos en UN render por frame (requestAnimationFrame). El buffer pendiente
  // se vuelca sí o sí en message.complete para no perder los últimos tokens.
  const deltaBufferRef = useRef("");
  const flushHandleRef = useRef<number | null>(null);

  const flushDeltas = useCallback(() => {
    flushHandleRef.current = null;
    const buffered = deltaBufferRef.current;
    if (!buffered) return;
    deltaBufferRef.current = "";
    setMessages((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      if (last.role !== "assistant" || !last.streaming) return prev;
      return [
        ...prev.slice(0, -1),
        { ...last, content: last.content + buffered },
      ];
    });
  }, []);

  const sendRpc = useCallback(
    (method: string, params?: Record<string, unknown>): Promise<unknown> => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        return Promise.reject(new Error("WebSocket not connected"));
      }
      const id = nextIdRef.current++;
      const req: JsonRpcRequest = { jsonrpc: "2.0", id, method, params };
      return new Promise((resolve, reject) => {
        pendingRef.current.set(id, (resp) => {
          if (resp.error) {
            reject(new Error(resp.error.code + ": " + resp.error.message));
          } else {
            resolve(resp.result);
          }
        });
        ws.send(JSON.stringify(req));
      });
    },
    [],
  );

  const handleEvent = useCallback((event: JsonRpcEvent) => {
    const { type, payload = {} } = event.params;

    // Multi-conversación: ignorar eventos de sesiones AJENAS. Sin este filtro,
    // un turno corriendo en la conversación A (o un cron) streamea sus mensajes
    // sobre la conversación B que está abierta — los "chats mezclados". Los
    // eventos sin session_id (p.ej. gateway.ready) pasan siempre.
    const evtSid = event.params.session_id;
    if (evtSid && liveSidRef.current && evtSid !== liveSidRef.current) {
      return;
    }

    switch (type) {
      case "gateway.ready":
        break;

      case "session.info":
        setSession((prev) => ({
          ...prev,
          sessionId: (payload.session_id as string) ?? prev.sessionId,
          model: (payload.model as string) ?? prev.model,
          modelProvider:
            (payload.model_provider as string) ?? prev.modelProvider,
          tokensUsed: (payload.tokens_used as number) ?? prev.tokensUsed,
          tokensMax: (payload.tokens_max as number) ?? prev.tokensMax,
        }));
        break;

      case "message.start": {
        setMessages((prev) => {
          // Si reasoning.delta ya creó el bubble del assistant, reusarlo
          // (los modelos thinking razonan ANTES de empezar a responder).
          const last = prev[prev.length - 1];
          if (last && last.role === "assistant" && last.streaming) return prev;
          return [
            ...prev,
            {
              id: "asst-" + Date.now(),
              role: "assistant",
              content: "",
              reasoning: "",
              toolCalls: [],
              streaming: true,
              timestamp: Date.now(),
            },
          ];
        });
        setBusy(true);
        break;
      }

      case "reasoning.delta":
      case "thinking.delta": {
        const text = (payload.text as string) ?? "";
        if (!text) break;
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === "assistant" && last.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, reasoning: (last.reasoning ?? "") + text },
            ];
          }
          return [
            ...prev,
            {
              id: "asst-" + Date.now(),
              role: "assistant",
              content: "",
              reasoning: text,
              toolCalls: [],
              streaming: true,
              timestamp: Date.now(),
            },
          ];
        });
        setBusy(true);
        break;
      }

      case "message.delta": {
        const text = (payload.text as string) ?? "";
        if (!text) break;
        // Llegó contenido real → limpiar el progreso en vivo (retry/fallback).
        setLiveStatus(null);
        deltaBufferRef.current += text;
        if (flushHandleRef.current == null) {
          flushHandleRef.current = requestAnimationFrame(flushDeltas);
        }
        break;
      }

      case "message.complete": {
        // Volcar cualquier delta pendiente del buffer ANTES de cerrar el
        // streaming, si no se pierden los últimos tokens.
        if (flushHandleRef.current != null) {
          cancelAnimationFrame(flushHandleRef.current);
          flushHandleRef.current = null;
        }
        const buffered = deltaBufferRef.current;
        deltaBufferRef.current = "";
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role !== "assistant" || !last.streaming) return prev;
          return [
            ...prev.slice(0, -1),
            {
              ...last,
              content: last.content + buffered,
              streaming: false,
              reasoning: (payload.reasoning as string) || last.reasoning,
            },
          ];
        });
        setBusy(false);
        setLiveStatus(null);
        // El usage del backend (_get_usage) es el total ACUMULADO de la sesión
        // (session_*_tokens), no un delta por turno: por eso se ASIGNA, no se
        // suma (sumar inflaba el contador en cada respuesta).
        const u =
          payload.usage && typeof payload.usage === "object"
            ? (payload.usage as Record<string, unknown>)
            : {};
        const inTok = Number(u.input ?? u.prompt ?? u.input_tokens ?? 0) || 0;
        const outTok =
          Number(u.output ?? u.completion ?? u.output_tokens ?? 0) || 0;
        const totalTok =
          Number(u.total ?? u.total_tokens ?? 0) || inTok + outTok;
        if (totalTok) {
          setSession((prev) => ({ ...prev, tokensUsed: totalTok }));
        }
        break;
      }

      case "tool.start": {
        const toolId = (payload.tool_id as string) ?? "tool-" + Date.now();
        const name = (payload.name as string) ?? "unknown";
        const args = (payload.args as Record<string, unknown>) ?? {};
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role !== "assistant") return prev;
          const newToolCall: ToolCall = {
            id: toolId,
            name,
            args,
            status: "running",
          };
          return [
            ...prev.slice(0, -1),
            { ...last, toolCalls: [...last.toolCalls, newToolCall] },
          ];
        });
        break;
      }

      case "tool.complete": {
        const toolId = payload.tool_id as string;
        const result = payload.result;
        const summary = payload.summary as string | undefined;
        const duration_s = payload.duration_s as number | undefined;
        setMessages((prev) => {
          return prev.map((msg) => {
            if (msg.role !== "assistant") return msg;
            const idx = msg.toolCalls.findIndex((tc) => tc.id === toolId);
            if (idx === -1) return msg;
            const updatedToolCalls = [...msg.toolCalls];
            updatedToolCalls[idx] = {
              ...updatedToolCalls[idx],
              status: "done",
              result,
              summary,
              duration_s,
            };
            return { ...msg, toolCalls: updatedToolCalls };
          });
        });
        break;
      }

      case "error": {
        const msg = (payload.message as string) ?? "Unknown error";
        setErrorMessage(msg);
        setLiveStatus(null);
        // Desatascar la UI: el agente falló a mitad de turno, así que liberamos
        // el "busy" y finalizamos el mensaje en streaming para que no quede
        // colgado en "Pensando..." para siempre.
        setBusy(false);
        // Volcar/limpiar el buffer de deltas: preserva el parcial y evita que se
        // filtre al próximo turno.
        if (flushHandleRef.current != null) {
          cancelAnimationFrame(flushHandleRef.current);
          flushHandleRef.current = null;
        }
        const buffered = deltaBufferRef.current;
        deltaBufferRef.current = "";
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role === "assistant" && last.streaming) {
            const content = last.content + buffered;
            const empty =
              !content.trim() &&
              last.toolCalls.length === 0 &&
              !(last.reasoning ?? "").trim();
            // Error antes de cualquier contenido → dropear la burbuja vacía
            // (si no, queda un avatar huérfano al lado del banner de error).
            if (empty) return prev.slice(0, -1);
            return [...prev.slice(0, -1), { ...last, content, streaming: false }];
          }
          return prev;
        });
        break;
      }

      case "status.update": {
        // El loop del agente reporta progreso y errores de retry/fallback/
        // billing SOLO por status.update. El Modern los ignoraba → durante la
        // cascada de fallback (minutos) quedaba en spinner sin mostrar nada.
        const text = (payload.text as string) ?? "";
        const kind = (payload.kind as string) ?? "";
        if (!text) break;

        const isTerminal = kind === "error" || text.trimStart().startsWith("❌");

        if (isTerminal) {
          // Fallo terminal (sin créditos / billing / fallbacks agotados):
          // tratarlo como FIN de turno — mostrar el error y parar el spinner
          // ya, sin esperar el message.complete final (que tarda minutos).
          setLiveStatus(null);
          setErrorMessage(text.replace(/^❌\s*/, ""));
          setBusy(false);
          if (flushHandleRef.current != null) {
            cancelAnimationFrame(flushHandleRef.current);
            flushHandleRef.current = null;
          }
          const buffered = deltaBufferRef.current;
          deltaBufferRef.current = "";
          setMessages((prev) => {
            if (prev.length === 0) return prev;
            const last = prev[prev.length - 1];
            if (last.role === "assistant" && last.streaming) {
              const content = last.content + buffered;
              const empty =
                !content.trim() &&
                last.toolCalls.length === 0 &&
                !(last.reasoning ?? "").trim();
              if (empty) return prev.slice(0, -1);
              return [
                ...prev.slice(0, -1),
                { ...last, content, streaming: false },
              ];
            }
            return prev;
          });
        } else {
          // Progreso no-terminal (reintentando, cambiando de proveedor,
          // rate-limit transitorio): mostrarlo en vivo para no parecer colgado.
          setLiveStatus(text);
        }
        break;
      }

      default:
        break;
    }
  }, [flushDeltas]);

  useEffect(() => {
    let cancelled = false;
    // Auto-reconexión con backoff exponencial: la conexión al gateway puede
    // parpadear (túnel SSH que se cae, red móvil, restart del server). Sin
    // esto, un solo drop dejaba el chat muerto en "Conectando..." hasta un
    // F5 manual. El backoff se resetea en cada conexión exitosa.
    let reconnectDelay = 1_000;
    let reconnectTimer: number | undefined;

    async function resolveSession(): Promise<string | null> {
      try {
        const recent = (await sendRpc("session.most_recent")) as {
          session_id?: string;
        } | null;
        const sid = recent?.session_id;
        if (sid) {
          try {
            const resumeResult = (await sendRpc("session.resume", { session_id: sid })) as { session_id?: string; resumed?: string };
            const liveSid = resumeResult?.session_id ?? sid;
            selectedKeyRef.current = sid;
            console.log("[useChatGateway] resumed session", sid, "→ live sid", liveSid);
            return liveSid;
          } catch (resumeErr) {
            console.warn(
              "[useChatGateway] resume failed, creating new session",
              resumeErr,
            );
          }
        }
      } catch (err) {
        console.warn("[useChatGateway] session.most_recent failed", err);
      }

      try {
        const created = (await sendRpc("session.create", {
          source: "dashboard",
        })) as { session_id?: string };
        const newSid = created?.session_id;
        if (newSid) {
          selectedKeyRef.current = newSid;
          console.log("[useChatGateway] created new session", newSid);
          try {
            const resumeResult = (await sendRpc("session.resume", { session_id: newSid })) as { session_id?: string };
            const liveSid = resumeResult?.session_id ?? newSid;
            return liveSid;
          } catch (err) {
            console.warn(
              "[useChatGateway] resume after create failed (continuing anyway)",
              err,
            );
            return newSid;
          }
        }
      } catch (err) {
        console.error("[useChatGateway] session.create failed", err);
        throw err;
      }

      return null;
    }

    async function connect() {
      setStatus("connecting");
      setErrorMessage(null);
      try {
        const [authName, authValue] = await buildWsAuthParam();
        if (cancelled) return;

        const proto =
          window.location.protocol === "https:" ? "wss:" : "ws:";
        const qs = new URLSearchParams({ [authName]: authValue });
        const url =
          proto +
          "//" +
          window.location.host +
          CLAWK_BASE_PATH +
          "/api/ws?" +
          qs.toString();

        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = async () => {
          if (cancelled) return;
          reconnectDelay = 1_000; // conexión sana → resetear el backoff
          setStatus("connected");
          // Si el usuario cambia de conversación mientras esta init corre,
          // switchSession avanza el seq → abortamos antes de pisar SU vista.
          const seqAtOpen = switchSeqRef.current;
          try {
            // Con una conversación abierta (reconexión, o carrera con un
            // switch), re-reanudar ESA sesión — session.most_recent puede ser
            // un cron u otro chat y escribiría su transcript encima.
            let sid: string | null = null;
            const preferredKey = selectedKeyRef.current;
            if (preferredKey) {
              try {
                const r = (await sendRpc("session.resume", {
                  session_id: preferredKey,
                })) as { session_id?: string; running?: boolean };
                sid = r?.session_id ?? preferredKey;
                if (!cancelled && seqAtOpen === switchSeqRef.current) {
                  setBusy(Boolean(r?.running));
                }
              } catch (resumeErr) {
                console.warn(
                  "[useChatGateway] re-resume of selected session failed",
                  resumeErr,
                );
                sid = null;
              }
            }
            if (!sid) sid = await resolveSession();
            if (cancelled) return;
            if (!sid) {
              setErrorMessage("No se pudo crear/obtener sesión");
              return;
            }
            if (seqAtOpen !== switchSeqRef.current) return; // hubo switch: no pisar

            try {
              const history = (await sendRpc("session.history", {
                session_id: sid,
              })) as { messages?: Array<Record<string, unknown>> };
              if (cancelled || seqAtOpen !== switchSeqRef.current) return;

              const initialMessages: ChatMessage[] = (history?.messages ?? [])
                .filter((m) => m.role === "user" || m.role === "assistant")
                .map((m, i) => ({
                  id: "hist-" + i,
                  role: m.role as "user" | "assistant",
                  content: (m.text as string) ?? (m.content as string) ?? "",
                  toolCalls: [],
                  streaming: false,
                  timestamp:
                    (m.timestamp as number) ?? Date.now() - 1000 * (1000 - i),
                }));
              setMessages(initialMessages);
            } catch (histErr) {
              console.warn(
                "[useChatGateway] session.history failed (empty session)",
                histErr,
              );
              if (seqAtOpen === switchSeqRef.current) setMessages([]);
            }

            liveSidRef.current = sid;
            setSession((prev) => ({ ...prev, sessionId: sid }));
          } catch (err) {
            console.error("[useChatGateway] session init failed", err);
            setErrorMessage(
              err instanceof Error ? err.message : "Session init failed",
            );
          }
        };

        ws.onmessage = (ev) => {
          if (typeof ev.data !== "string") return;
          let parsed: IncomingMessage;
          try {
            parsed = JSON.parse(ev.data);
          } catch {
            return;
          }
          if ("method" in parsed && parsed.method === "event") {
            handleEvent(parsed);
            return;
          }
          if ("id" in parsed && parsed.id != null) {
            const cb = pendingRef.current.get(parsed.id);
            if (cb) {
              pendingRef.current.delete(parsed.id);
              cb(parsed);
            }
          }
        };

        ws.onclose = () => {
          if (cancelled) return;
          setStatus("disconnected");
          setBusy(false);
          // Reintentar solo: resolveSession() reanuda la sesión más reciente
          // al reabrir, así la conversación en curso vuelve sin F5.
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

    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
      pendingRef.current.clear();
    };
  }, [handleEvent, sendRpc]);

  const sendMessage = useCallback(
    (text: string, images?: ChatImagePreview[]) => {
      if (!text.trim()) return;
      if (!session.sessionId) {
        setErrorMessage("No hay sesión activa todavía");
        return;
      }
      // Nuevo turno: limpiar cualquier error previo + progreso en vivo.
      setErrorMessage(null);
      setLiveStatus(null);
      const userMsgId = "usr-" + Date.now();
      setMessages((prev) => [
        ...prev,
        {
          id: userMsgId,
          role: "user",
          content: text,
          toolCalls: [],
          streaming: false,
          timestamp: Date.now(),
          images: images && images.length ? images : undefined,
        },
      ]);

      // Slash command (/model, /help, /status, skills, …): dispatcher unificado.
      // executeSlash intenta slash.exec y, si el backend lo rechaza (skills,
      // comandos pending-input como /retry /queue /goal /undo /steer, o alias),
      // cae a command.dispatch — el mismo contrato que la TUI. Sin esto, las
      // skills aparecían en el autocomplete pero fallaban al ejecutarse, y los
      // comandos pending-input daban error 4018 en el chat Modern. Los comandos
      // con efectos (model/new/stop) emiten eventos que el chat ya procesa.
      if (text.trim().startsWith("/")) {
        const appendSystem = (out: string) => {
          if (!out) return;
          setMessages((prev) => [
            ...prev,
            {
              id: "slash-" + Date.now(),
              role: "assistant",
              content: out,
              toolCalls: [],
              streaming: false,
              timestamp: Date.now(),
            },
          ]);
        };
        const submitToAgent: (msg: string) => void = (msg) => {
          void sendRpc("prompt.submit", {
            session_id: session.sessionId,
            text: msg,
          }).catch((err) => {
            console.error("[useChatGateway] prompt.submit failed", err);
            setErrorMessage(
              err instanceof Error ? err.message : "Failed to send message",
            );
          });
        };
        void executeSlash({
          command: text.trim(),
          sessionId: session.sessionId,
          gw: {
            request<T = unknown>(
              method: string,
              params?: Record<string, unknown>,
            ): Promise<T> {
              return sendRpc(method, params) as Promise<T>;
            },
          },
          callbacks: { sys: appendSystem, send: submitToAgent },
        }).catch((err) => {
          console.error("[useChatGateway] executeSlash failed", err);
          setErrorMessage(
            err instanceof Error
              ? err.message.replace(/^\d+:\s*/, "")
              : "El comando falló",
          );
        });
        return;
      }

      // Marcamos busy de inmediato (no esperando message.start) para que la cola
      // de mensajes tenga un gate confiable: sin esto, en la ventana del
      // round-trip busy=false y el siguiente mensaje en cola se dispararía sobre
      // una sesión que ya está por ocuparse (→ 4009 / mensaje perdido).
      setBusy(true);
      sendRpc("prompt.submit", {
        session_id: session.sessionId,
        text,
      }).catch((err) => {
        console.error("[useChatGateway] prompt.submit failed", err);
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to send message",
        );
        // El submit falló (p.ej. 4009 session busy): liberamos para no colgar.
        setBusy(false);
      });
    },
    [session.sessionId, sendRpc],
  );

  const interrupt = useCallback(() => {
    if (!session.sessionId) return;
    sendRpc("session.interrupt", { session_id: session.sessionId }).catch(
      (err) => {
        console.error("[useChatGateway] session.interrupt failed", err);
      },
    );
  }, [session.sessionId, sendRpc]);

  const switchSeqRef = useRef(0);
  const switchSession = useCallback(
    async (targetId: string, options?: { assumeLive?: boolean }): Promise<void> => {
      if (!targetId) return;
      const mySeq = ++switchSeqRef.current;
      setMessages([]);
      setBusy(false);
      setResuming(true);
      setErrorMessage(null);
      // Mostrar ya el header/asociación de la sesión; el composer queda
      // deshabilitado por `resuming` hasta que el resume (build del agente) termine.
      // Provisional hasta que el resume devuelva el sid vivo: alcanza para que
      // el filtro de handleEvent descarte los eventos de la conversación anterior.
      liveSidRef.current = targetId;
      selectedKeyRef.current = targetId;
      setSession((prev) => ({
        ...prev,
        sessionId: targetId,
        model: null,
        modelProvider: null,
        tokensUsed: 0,
        tokensMax: 0,
      }));

      // new-chat-assume-live
      // session.create ya devuelve una sesión viva. Para una conversación nueva
      // NO hacemos session.resume porque puede fallar con "session not found".
      // El resume se reserva para sesiones históricas del sidebar.
      if (options?.assumeLive) {
        setResuming(false);
        return;
      }

      // 1) Historial al INSTANTE: lee del DB por HTTP (no construye el agente),
      //    así la conversación aparece sin esperar el build lento del resume.
      try {
        const fast = await api.getSessionMessages(targetId);
        if (mySeq !== switchSeqRef.current) return;
        const fastMsgs: ChatMessage[] = (fast?.messages ?? [])
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m, i) => ({
            id: "hist-" + targetId + "-" + i,
            role: m.role as "user" | "assistant",
            content: m.content ?? "",
            toolCalls: [],
            streaming: false,
            timestamp: Date.now() - 1000 * (1000 - i),
          }));
        if (fastMsgs.length) setMessages(fastMsgs);
      } catch {
        // best-effort: el resume de abajo igual trae los mensajes.
      }

      // 2) Resume: construye el agente (lento) y deja la sesión VIVA para poder
      //    enviar. El historial ya se mostró en el paso 1.
      try {
        const resumeResult = (await sendRpc("session.resume", {
          session_id: targetId,
        })) as {
          session_id?: string;
          messages?: Array<Record<string, unknown>>;
          info?: Record<string, unknown>;
          running?: boolean;
        };
        if (mySeq !== switchSeqRef.current) return;
        const liveSid = resumeResult?.session_id ?? targetId;
        liveSidRef.current = liveSid;
        // Conversación reanudada con un turno EN VUELO (sobrevive al navegar):
        // restaurar busy para que el composer entre en modo cola ("Agregar a la
        // cola", estilo Telegram) en vez de chocar con 4009 session busy.
        setBusy(Boolean(resumeResult?.running));
        const historyMessages = resumeResult?.messages ?? [];
        if (historyMessages.length) {
          const initialMessages: ChatMessage[] = historyMessages
            .filter((m) => m.role === "user" || m.role === "assistant")
            .map((m, i) => ({
              id: "hist-" + Date.now() + "-" + i,
              role: m.role as "user" | "assistant",
              content: (m.text as string) ?? (m.content as string) ?? "",
              toolCalls: [],
              streaming: false,
              timestamp:
                (m.timestamp as number) ?? Date.now() - 1000 * (1000 - i),
            }));
          setMessages(initialMessages);
        }
        if (mySeq !== switchSeqRef.current) return;
        // Tokens por conversación + modelo de la sesión resumida.
        const info = resumeResult?.info ?? {};

        // tokens-hydrate-on-switch-v2
        // Al cambiar de conversación, rehidratamos el contador del header.
        // Importante: NO cambiamos sessionId visual aquí; sessionId debe seguir
        // siendo liveSid para que prompt.submit/slash.exec no fallen.
        const infoForTokens = info as Record<string, unknown>;

        let restoredTokensUsed =
          Number(
            infoForTokens.tokens_used ??
              infoForTokens.total_tokens ??
              infoForTokens.total ??
              0,
          ) || 0;

        let restoredTokensMax =
          Number(
            infoForTokens.tokens_max ??
              infoForTokens.context_max ??
              0,
          ) || 0;

        const tryReadUsageSnapshot = async (sid: string) => {
          try {
            const usage = (await sendRpc("session.usage", {
              session_id: sid,
            })) as Record<string, unknown> | null;

            return {
              ok: true,
              total:
                Number(
                  usage?.total ??
                    usage?.total_tokens ??
                    usage?.tokens_used ??
                    0,
                ) || 0,
              max:
                Number(
                  usage?.context_max ??
                    usage?.tokens_max ??
                    0,
                ) || 0,
            };
          } catch (usageErr) {
            console.warn(
              "[useChatGateway] session.usage failed during token restore",
              sid,
              usageErr,
            );
            return { ok: false, total: 0, max: 0 };
          }
        };

        // Para métricas persistidas puede servir targetId; para sesión viva puede
        // servir liveSid. Probamos ambos, sin romper el switch si usage falla.
        for (const sid of Array.from(new Set([targetId, liveSid])).filter(Boolean)) {
          const usage = await tryReadUsageSnapshot(sid);
          if (usage.ok && (usage.total > 0 || usage.max > 0)) {
            restoredTokensUsed = usage.total;
            restoredTokensMax = usage.max;
            break;
          }
        }
        setSession((prev) => ({
          ...prev,
          sessionId: liveSid,
          model: (info.model as string) ?? null,
          modelProvider: (info.model_provider as string) ?? null,
          tokensUsed: restoredTokensUsed,
          tokensMax: restoredTokensMax,
          // El backend devuelve title en info — si no llega, prev.title queda null
          // del paso inmediato anterior, lo cual está bien.
          title: ((info.title as string) || null) ?? prev.title,
        }));
      } catch (err) {
        console.error("[useChatGateway] switchSession failed", err);
        if (mySeq === switchSeqRef.current) {
          setErrorMessage(
            err instanceof Error ? err.message : "Failed to switch session",
          );
        }
      } finally {
        if (mySeq === switchSeqRef.current) setResuming(false);
      }
    },
    [sendRpc],
  );

  const regenerateLast = useCallback(async (): Promise<void> => {
    if (busy) return;
    const sid = session.sessionId;
    if (!sid) return;

    // El último mensaje user es el prompt que produjo la última respuesta.
    let lastUserText: string | null = null;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        lastUserText = messages[i].content;
        break;
      }
    }
    if (lastUserText == null) return;
    // Si el último turno fue un slash command, NO regenerar: re-ejecutaría el
    // comando y session.undo borraría el turno real previo (los slash no quedan
    // en el history del backend).
    if (lastUserText.trim().startsWith("/")) return;

    // Sacar localmente el último turno (desde el último user, inclusive). El
    // backend hace lo mismo con session.undo; re-enviamos el prompt para
    // generar una respuesta fresca sin duplicar el turno.
    setMessages((prev) => {
      let cut = prev.length;
      for (let i = prev.length - 1; i >= 0; i--) {
        if (prev[i].role === "user") {
          cut = i;
          break;
        }
      }
      return prev.slice(0, cut);
    });

    try {
      await sendRpc("session.undo", { session_id: sid });
    } catch (err) {
      console.error("[useChatGateway] session.undo failed", err);
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to regenerate",
      );
      return;
    }

    sendMessage(lastUserText);
  }, [busy, session.sessionId, messages, sendRpc, sendMessage]);

  // Editar un mensaje del usuario y reenviar desde ahí (estilo ChatGPT): trunca
  // el historial ANTES de ese mensaje user y reenvía el texto editado. El backend
  // (prompt.submit + truncate_before_user_ordinal) reescribe history y DB, así que
  // sobrevive a navegar/recargar. El ordinal indexa la sublista de mensajes user
  // del backend, que NO incluye los slash (van por executeSlash, no por
  // prompt.submit) → contamos solo users que no empiezan con "/".
  const editAndResubmit = useCallback(
    async (messageId: string, newText: string): Promise<void> => {
      if (busy) return;
      const sid = session.sessionId;
      if (!sid || !newText.trim()) return;
      if (newText.trim().startsWith("/")) return; // no editar a un slash command

      const msgs = messagesRef.current;
      const idx = msgs.findIndex((m) => m.id === messageId);
      if (idx < 0 || msgs[idx].role !== "user") return;

      // ordinal = cantidad de mensajes user NO-slash antes de idx (alinea con
      // user_indices del backend, que filtra los slash).
      let ordinal = 0;
      for (let i = 0; i < idx; i++) {
        if (msgs[i].role === "user" && !msgs[i].content.trim().startsWith("/")) {
          ordinal++;
        }
      }

      // Truncado local: dejar lo previo + el mensaje user editado; la respuesta
      // nueva llega por streaming y se appendea encima (igual que regenerateLast).
      const editedMsg: ChatMessage = {
        ...msgs[idx],
        id: "usr-" + Date.now(),
        content: newText,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev.slice(0, idx), editedMsg]);

      // Gate de cola sincrónico antes del RPC (igual que sendMessage).
      setBusy(true);
      try {
        await sendRpc("prompt.submit", {
          session_id: sid,
          text: newText,
          truncate_before_user_ordinal: ordinal,
        });
      } catch (err) {
        console.error("[useChatGateway] editAndResubmit failed", err);
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to edit message",
        );
        setBusy(false);
      }
    },
    [busy, session.sessionId, sendRpc],
  );

  const clearError = useCallback(() => setErrorMessage(null), []);

  return {
    status,
    session,
    messages,
    busy,
    sendMessage,
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
  };
}
