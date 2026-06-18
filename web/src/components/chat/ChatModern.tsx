/**
 * ChatModern — Modo "moderno" del chat con sidebar de sesiones (Fase 2.7).
 *
 * Layout: sidebar 240px + body flex-1.
 * Sidebar incluye lista de sesiones y botón "Nueva conversación".
 * Click en sesión → switchSession del gateway.
 */

import { useEffect, useRef, useState } from "react";
import {
  Paperclip,
  Mic,
  ArrowUp,
  Copy,
  RotateCw,
  Pencil,
  ChevronRight,
  Zap,
  CheckCircle2,
  Loader2,
  AlertCircle,
  WifiOff,
  Square,
} from "lucide-react";
import { Markdown } from "../Markdown";
import {
  useChatGateway,
  type ChatMessage,
  type ConnectionStatus,
  type ToolCall,
} from "./hooks/useChatGateway";
import { useSessions } from "./hooks/useSessions";
import { SessionSidebar } from "./SessionSidebar";

interface ChatHeaderProps {
  status: ConnectionStatus;
  model: string | null;
  modelProvider: string | null;
  sessionId: string | null;
  tokensUsed: number;
  tokensMax: number;
}

function ChatHeader({
  status,
  model,
  modelProvider,
  sessionId,
  tokensUsed,
  tokensMax,
}: ChatHeaderProps) {
  const statusColor =
    status === "connected"
      ? "bg-success"
      : status === "connecting"
        ? "bg-warning animate-pulse"
        : "bg-destructive";

  const shortSession = sessionId ? sessionId.slice(0, 8) : "—";
  const tokensLabel =
    tokensMax > 0
      ? tokensUsed.toLocaleString() + "/" + (tokensMax / 1000).toFixed(1) + "k tokens"
      : tokensUsed.toLocaleString() + " tokens";

  return (
    <div className="flex items-center justify-between border-b border-border px-4 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <span className={"size-2 rounded-full shrink-0 " + statusColor} />
        <span className="text-sm font-semibold text-foreground truncate">
          {model || (status === "connecting" ? "Connecting..." : "—")}
        </span>
        {modelProvider && (
          <>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">{modelProvider}</span>
          </>
        )}
      </div>

      <div className="hidden md:flex items-center gap-3 text-xs text-muted-foreground">
        <span>Session</span>
        <span className="font-mono text-foreground/80">{shortSession}</span>
        <span>·</span>
        <span>{tokensLabel}</span>
      </div>
    </div>
  );
}

function Avatar({ role }: { role: "user" | "assistant" }) {
  if (role === "user") {
    return (
      <div className="flex size-7 shrink-0 items-center justify-center rounded bg-[#2a4a4a] font-mono text-xs text-foreground">
        A
      </div>
    );
  }
  return (
    <div className="flex size-7 shrink-0 items-center justify-center rounded bg-[#6C4FD6] text-white">
      <Zap className="size-3.5" />
    </div>
  );
}

function ToolCallRow({ toolCall }: { toolCall: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = toolCall.status === "running";
  const argsPreview = Object.entries(toolCall.args)
    .map(([k, v]) => k + "=" + (typeof v === "string" ? v : JSON.stringify(v)))
    .join(" ")
    .slice(0, 120);

  return (
    <div className="flex flex-col gap-1">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className={
          "group flex w-full items-center gap-2 rounded border px-3 py-1.5 text-left transition-colors " +
          (isRunning
            ? "border-[#6C4FD6]/60 bg-[#6C4FD6]/5"
            : "border-border bg-muted/20 hover:bg-muted/30")
        }
      >
        <ChevronRight
          className={
            "size-3 text-muted-foreground transition-transform " +
            (expanded ? "rotate-90" : "")
          }
        />
        <span className="font-mono text-xs text-warning">{toolCall.name}</span>
        <span className="truncate text-xs text-muted-foreground">
          {argsPreview}
        </span>
        <span className="ml-auto flex items-center gap-1 text-xs">
          {isRunning ? (
            <>
              <Loader2 className="size-3 animate-spin text-[#6C4FD6]" />
              <span className="text-muted-foreground">running</span>
            </>
          ) : (
            <>
              <CheckCircle2 className="size-3 text-success" />
              <span className="text-success">
                {toolCall.duration_s
                  ? toolCall.duration_s.toFixed(1) + "s"
                  : "done"}
              </span>
            </>
          )}
        </span>
      </button>

      {expanded && toolCall.result !== undefined && (
        <pre className="ml-5 max-h-64 overflow-auto rounded border border-border bg-muted/20 p-2 text-xs text-muted-foreground">
          {typeof toolCall.result === "string"
            ? toolCall.result
            : JSON.stringify(toolCall.result, null, 2)}
        </pre>
      )}
    </div>
  );
}

function MessageActions({ content }: { content: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="flex items-center gap-3 opacity-0 transition-opacity group-hover:opacity-100">
      <button
        type="button"
        onClick={handleCopy}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Copy className="size-3" />
        {copied ? "Copied" : "Copy"}
      </button>
      <button
        type="button"
        disabled
        title="Regenerate — disponible en Nivel 2"
        className="flex items-center gap-1 text-xs text-muted-foreground opacity-40 cursor-not-allowed"
      >
        <RotateCw className="size-3" />
        Regenerate
      </button>
      <button
        type="button"
        disabled
        title="Edit — disponible en Nivel 2"
        className="flex items-center gap-1 text-xs text-muted-foreground opacity-40 cursor-not-allowed"
      >
        <Pencil className="size-3" />
        Edit
      </button>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className="group flex gap-3 px-4 py-3">
      <Avatar role={message.role} />

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {isUser ? "You" : "Clawksis"}
          </span>
        </div>

        {isUser ? (
          <div className="rounded-md bg-muted/40 px-4 py-2.5 text-sm text-foreground whitespace-pre-wrap">
            {message.content}
          </div>
        ) : (
          <div className="text-sm text-foreground">
            <Markdown content={message.content} streaming={message.streaming} />
          </div>
        )}

        {message.toolCalls.length > 0 && (
          <div className="mt-1 flex flex-col gap-1.5">
            {message.toolCalls.map((tc) => (
              <ToolCallRow key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {!isUser && !message.streaming && (
          <MessageActions content={message.content} />
        )}
      </div>
    </div>
  );
}

interface ComposerProps {
  busy: boolean;
  disabled: boolean;
  onSend: (text: string) => void;
  onInterrupt: () => void;
}

function Composer({ busy, disabled, onSend, onInterrupt }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const canSend = value.trim().length > 0 && !busy && !disabled;

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [value]);

  const handleSubmit = () => {
    if (!canSend) return;
    onSend(value);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-border px-4 py-3">
      <div className="flex items-end gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 focus-within:border-[#6C4FD6]/60 transition-colors">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            disabled
              ? "Esperando conexión..."
              : "Mensaje a Clawksis... (Shift+Enter para nueva línea)"
          }
          rows={1}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none disabled:opacity-50"
        />
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Adjuntar archivo"
            title="Adjuntar archivo — disponible en Nivel 2"
            disabled
            className="rounded p-1.5 text-muted-foreground opacity-40 cursor-not-allowed"
          >
            <Paperclip className="size-4" />
          </button>
          <button
            type="button"
            aria-label="Grabar voz"
            title="Grabar voz — disponible en Nivel 2"
            disabled
            className="rounded p-1.5 text-muted-foreground opacity-40 cursor-not-allowed"
          >
            <Mic className="size-4" />
          </button>

          {busy ? (
            <button
              type="button"
              onClick={onInterrupt}
              aria-label="Interrumpir"
              className="ml-1 flex size-7 items-center justify-center rounded bg-destructive text-white hover:bg-destructive/80 transition-colors"
            >
              <Square className="size-3 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSend}
              aria-label="Enviar mensaje"
              className={
                "ml-1 flex size-7 items-center justify-center rounded transition-colors " +
                (canSend
                  ? "bg-[#6C4FD6] text-white hover:bg-[#5a40c2]"
                  : "bg-muted/40 text-muted-foreground cursor-not-allowed")
              }
            >
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ConnectionBanner({
  status,
  errorMessage,
}: {
  status: ConnectionStatus;
  errorMessage: string | null;
}) {
  if (status === "connected") return null;

  const isError = status === "error" || (errorMessage && status === "disconnected");
  const isConnecting = status === "connecting" || status === "idle";

  if (isConnecting) {
    return (
      <div className="flex items-center gap-2 border-b border-border bg-muted/20 px-4 py-2 text-xs text-muted-foreground">
        <Loader2 className="size-3 animate-spin" />
        <span>Conectando al gateway...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-xs text-destructive">
      {isError ? <AlertCircle className="size-3" /> : <WifiOff className="size-3" />}
      <span>
        {errorMessage ?? "Conexión perdida. Recargá la página para reintentar."}
      </span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-1 items-center justify-center px-4 py-12">
      <div className="flex max-w-md flex-col items-center gap-3 text-center">
        <div className="flex size-12 items-center justify-center rounded-lg bg-[#6C4FD6]/10">
          <Zap className="size-6 text-[#6C4FD6]" />
        </div>
        <h2 className="text-base font-semibold text-foreground">
          Empezá una conversación
        </h2>
        <p className="text-sm text-muted-foreground">
          Escribí un mensaje abajo para empezar a chatear con Clawksis.
        </p>
      </div>
    </div>
  );
}

export default function ChatModern() {
  const {
    status,
    session,
    messages,
    busy,
    sendMessage,
    interrupt,
    errorMessage,
    sendRpc,
    readyForRpc,
    switchSession,
  } = useChatGateway();

  const {
    sessions,
    loading: sessionsLoading,
    error: sessionsError,
    createSession,
  } = useSessions(sendRpc, readyForRpc);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  const isConnecting = status === "connecting" || status === "idle";
  const composerDisabled = status !== "connected" || !session.sessionId;

  const handleSelectSession = (targetId: string) => {
    if (targetId === session.sessionId) return;
    void switchSession(targetId);
  };

  const handleNewChat = async () => {
    const newId = await createSession();
    if (newId) {
      await switchSession(newId);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-row rounded-lg border border-border bg-background overflow-hidden">
      <SessionSidebar
        sessions={sessions}
        activeSessionId={session.sessionId}
        loading={sessionsLoading}
        error={sessionsError}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
      />

      <div className="flex min-h-0 flex-1 flex-col">
        <ChatHeader
          status={status}
          model={session.model}
          modelProvider={session.modelProvider}
          sessionId={session.sessionId}
          tokensUsed={session.tokensUsed}
          tokensMax={session.tokensMax}
        />

        <ConnectionBanner status={status} errorMessage={errorMessage} />

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {messages.length === 0 && !isConnecting ? (
            <EmptyState />
          ) : (
            <div className="mx-auto flex w-full max-w-none flex-col">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
            </div>
          )}
        </div>

        <Composer
          busy={busy}
          disabled={composerDisabled}
          onSend={sendMessage}
          onInterrupt={interrupt}
        />
      </div>
    </div>
  );
}
