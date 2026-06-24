/**
 * useChatGateway — Hook para conexión JSON-RPC con el gateway de Clawksis.
 *
 * Fase 2.7 — versión completa con switchSession para sidebar de sesiones.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, CLAWK_BASE_PATH, buildWsAuthParam } from "@/lib/api";

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
  /** Cambiar a otra sesión: muestra el historial al instante y resume en 2do plano. */
  switchSession: (targetId: string, options?: { assumeLive?: boolean }) => Promise<void>;
  /** true mientras se resume una sesión (el agente se está construyendo). */
  resuming: boolean;
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
    title: null,
  });
  const [busy, setBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [resuming, setResuming] = useState(false);

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
        // Desatascar la UI: el agente falló a mitad de turno, así que liberamos
        // el "busy" y finalizamos el mensaje en streaming para que no quede
        // colgado en "Pensando..." para siempre.
        setBusy(false);
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role === "assistant" && last.streaming) {
            const empty =
              !last.content.trim() &&
              last.toolCalls.length === 0 &&
              !(last.reasoning ?? "").trim();
            // Error antes de cualquier contenido → dropear la burbuja vacía
            // (si no, queda un avatar huérfano al lado del banner de error).
            if (empty) return prev.slice(0, -1);
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
    async (targetId: string, options?: { assumeLive?: boolean }): Promise<void> => {
      if (!targetId) return;
      const mySeq = ++switchSeqRef.current;
      setMessages([]);
      setBusy(false);
      setResuming(true);
      setErrorMessage(null);
      // Mostrar ya el header/asociación de la sesión; el composer queda
      // deshabilitado por `resuming` hasta que el resume (build del agente) termine.
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
        };
        if (mySeq !== switchSeqRef.current) return;
        const liveSid = resumeResult?.session_id ?? targetId;
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
    resuming,
    regenerateLast,
  };
}
