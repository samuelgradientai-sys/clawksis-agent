/**
 * useChatGateway — Hook para conexión JSON-RPC con el gateway de Clawksis.
 *
 * Fase 2.7 — versión completa con switchSession para sidebar de sesiones.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CLAWK_BASE_PATH, buildWsAuthParam } from "@/lib/api";

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

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Cadena de razonamiento de modelos "thinking" (reasoning.delta). */
  reasoning?: string;
  toolCalls: ToolCall[];
  streaming: boolean;
  timestamp: number;
}

export interface SessionInfo {
  sessionId: string | null;
  model: string | null;
  modelProvider: string | null;
  tokensUsed: number;
  tokensMax: number;
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
  sendMessage: (text: string) => void;
  interrupt: () => void;
  errorMessage: string | null;
  /** Descartar el error visible (lo dispara el banner de error). */
  clearError: () => void;
  /** Para hooks satélite que necesitan reusar la conexión (ej: useSessions) */
  sendRpc: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  /** true cuando es seguro usar sendRpc (WebSocket conectado) */
  readyForRpc: boolean;
  /** Cambiar a otra sesión: limpia mensajes, carga history, actualiza sessionId */
  switchSession: (targetId: string) => Promise<void>;
  /** Regenera la última respuesta: session.undo (borra último turno user+assistant) + re-submit del último prompt. */
  regenerateLast: () => Promise<void>;
}

export function useChatGateway(): UseChatGatewayResult {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [session, setSession] = useState<SessionInfo>({
    sessionId: null,
    model: null,
    modelProvider: null,
    tokensUsed: 0,
    tokensMax: 0,
  });
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const nextIdRef = useRef(1);
  const pendingRef = useRef<Map<number, (resp: JsonRpcResponse) => void>>(
    new Map(),
  );

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
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role !== "assistant" || !last.streaming) return prev;
          const updated = { ...last, content: last.content + text };
          return [...prev.slice(0, -1), updated];
        });
        break;
      }

      case "message.complete": {
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role !== "assistant" || !last.streaming) return prev;
          return [
            ...prev.slice(0, -1),
            {
              ...last,
              streaming: false,
              reasoning: (payload.reasoning as string) || last.reasoning,
            },
          ];
        });
        setBusy(false);
        // Acumular tokens del usage para el contador del header. El backend no
        // emite session.info por turno, así que sin esto quedaban en 0.
        const u =
          payload.usage && typeof payload.usage === "object"
            ? (payload.usage as Record<string, unknown>)
            : {};
        const inTok = Number(u.input ?? u.prompt ?? u.input_tokens ?? 0) || 0;
        const outTok =
          Number(u.output ?? u.completion ?? u.output_tokens ?? 0) || 0;
        if (inTok || outTok) {
          setSession((prev) => ({
            ...prev,
            tokensUsed: prev.tokensUsed + inTok + outTok,
          }));
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
        // Desatascar la UI: el agente falló a mitad de turno, así que liberamos
        // el "busy" y finalizamos el mensaje en streaming para que no quede
        // colgado en "Pensando..." para siempre.
        setBusy(false);
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role === "assistant" && last.streaming) {
            return [...prev.slice(0, -1), { ...last, streaming: false }];
          }
          return prev;
        });
        break;
      }

      default:
        break;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

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
          setStatus("connected");
          try {
            const sid = await resolveSession();
            if (cancelled) return;
            if (!sid) {
              setErrorMessage("No se pudo crear/obtener sesión");
              return;
            }

            try {
              const history = (await sendRpc("session.history", {
                session_id: sid,
              })) as { messages?: Array<Record<string, unknown>> };
              if (cancelled) return;

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
              setMessages([]);
            }

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
          if (!cancelled) {
            setStatus("disconnected");
            setBusy(false);
          }
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
    (text: string) => {
      if (!text.trim()) return;
      if (!session.sessionId) {
        setErrorMessage("No hay sesión activa todavía");
        return;
      }
      // Nuevo turno: limpiar cualquier error previo.
      setErrorMessage(null);
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
        },
      ]);

      // Slash command (/model, /help, /status, …): ejecutarlo vía slash.exec —
      // como el terminal — en lugar de mandarlo al modelo. El output se muestra
      // como respuesta; los comandos con efectos (model/new/stop) emiten eventos
      // que el chat ya procesa.
      if (text.trim().startsWith("/")) {
        sendRpc("slash.exec", {
          session_id: session.sessionId,
          command: text.trim(),
        })
          .then((res) => {
            const output = (res as { output?: string })?.output ?? "";
            if (output) {
              setMessages((prev) => [
                ...prev,
                {
                  id: "slash-" + Date.now(),
                  role: "assistant",
                  content: output,
                  toolCalls: [],
                  streaming: false,
                  timestamp: Date.now(),
                },
              ]);
            }
          })
          .catch((err) => {
            console.error("[useChatGateway] slash.exec failed", err);
            setErrorMessage(
              err instanceof Error
                ? err.message.replace(/^\d+:\s*/, "")
                : "El comando falló",
            );
          });
        return;
      }

      sendRpc("prompt.submit", {
        session_id: session.sessionId,
        text,
      }).catch((err) => {
        console.error("[useChatGateway] prompt.submit failed", err);
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to send message",
        );
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
    async (targetId: string): Promise<void> => {
      if (!targetId) return;
      const mySeq = ++switchSeqRef.current;
      setMessages([]);
      setBusy(false);
      try {
        const resumeResult = (await sendRpc("session.resume", {
          session_id: targetId,
        })) as {
          session_id?: string;
          messages?: Array<Record<string, unknown>>;
          info?: Record<string, unknown>;
        };
        if (mySeq !== switchSeqRef.current) return;
        const liveSid = resumeResult?.session_id ?? targetId;
        // session.resume ya retorna messages en la respuesta
        // — NO necesitamos llamar session.history aparte
        const historyMessages = resumeResult?.messages ?? [];
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
        if (mySeq !== switchSeqRef.current) return;
        // Tokens por conversación: resetear al cambiar para no arrastrar el
        // total del chat anterior. El modelo lo tomamos del info de la sesión
        // resumida (si el gateway lo manda).
        const info = resumeResult?.info ?? {};
        setSession((prev) => ({
          ...prev,
          sessionId: liveSid,
          model: (info.model as string) || prev.model,
          modelProvider: (info.model_provider as string) ?? prev.modelProvider,
          tokensUsed: 0,
          tokensMax: 0,
        }));
        console.log(
          "[useChatGateway] switched to session",
          targetId,
          "→ live sid",
          liveSid,
        );
      } catch (err) {
        console.error("[useChatGateway] switchSession failed", err);
        if (mySeq === switchSeqRef.current) {
          setErrorMessage(
            err instanceof Error ? err.message : "Failed to switch session",
          );
        }
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

  const clearError = useCallback(() => setErrorMessage(null), []);

  return {
    status,
    session,
    messages,
    busy,
    sendMessage,
    interrupt,
    errorMessage,
    clearError,
    sendRpc,
    readyForRpc: status === "connected",
    switchSession,
    regenerateLast,
  };
}
