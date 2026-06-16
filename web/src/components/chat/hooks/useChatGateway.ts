/**
 * useChatGateway — Hook para conexión JSON-RPC con el gateway de Clawksis.
 *
 * Fase 2.6.3-fix: corregido el manejo de session init.
 * Si session.most_recent retorna un ID que ya no existe en disco,
 * caemos a session.create automáticamente.
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
        const assistantMsgId = "asst-" + Date.now();
        setMessages((prev) => [
          ...prev,
          {
            id: assistantMsgId,
            role: "assistant",
            content: "",
            toolCalls: [],
            streaming: true,
            timestamp: Date.now(),
          },
        ]);
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

      case "message.complete":
        setMessages((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          if (last.role !== "assistant" || !last.streaming) return prev;
          return [...prev.slice(0, -1), { ...last, streaming: false }];
        });
        setBusy(false);
        break;

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
        break;
      }

      default:
        break;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    // Helper: intenta resume, si falla crea sesión nueva
    async function resolveSession(): Promise<string | null> {
      // 1. Intentar la sesión más reciente (puede que no exista)
      try {
        const recent = (await sendRpc("session.most_recent")) as {
          session_id?: string;
        } | null;
        const sid = recent?.session_id;
        if (sid) {
          // Intentar resumir esa sesión
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
            // Cae a crear sesión nueva abajo
          }
        }
      } catch (err) {
        console.warn("[useChatGateway] session.most_recent failed", err);
      }

      // 2. Crear sesión nueva
      try {
        const created = (await sendRpc("session.create", {
          source: "dashboard",
        })) as { session_id?: string };
        const newSid = created?.session_id;
        if (newSid) {
          console.log("[useChatGateway] created new session", newSid);
          // Activar la sesión recién creada
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

            // Cargar history (tolerante a errores)
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
                  content: (m.content as string) ?? "",
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
              // No es fatal — sesión nueva no tiene history
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

  return {
    status,
    session,
    messages,
    busy,
    sendMessage,
    interrupt,
    errorMessage,
  };
}
