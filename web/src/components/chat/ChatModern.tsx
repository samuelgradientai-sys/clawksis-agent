/**
 * ChatModern — Modo "moderno" del chat con sidebar de sesiones (Fase 2.7)
 * + file picker funcional en el composer (Fase 2.8 B1).
 *
 * Layout: sidebar 240px + body flex-1.
 * Composer: textarea + chips de archivos adjuntos arriba + botones (Paperclip
 * funcional, Mic placeholder).
 */

import { memo, useCallback, useEffect, useRef, useState } from "react";
import {
  Paperclip,
  Mic,
  ArrowUp,
  Copy,
  RotateCw,
  Pencil,
  Quote,
  Brain,
  ChevronRight,
  Zap,
  CheckCircle2,
  Loader2,
  AlertCircle,
  WifiOff,
  Square,
  X,
  FileText,
} from "lucide-react";
import { Markdown } from "../Markdown";
import {
  useChatGateway,
  type ChatMessage,
  type ConnectionStatus,
  type ToolCall,
} from "./hooks/useChatGateway";
import { useSessions, deriveTitle, type RpcSender } from "./hooks/useSessions";
import { useAttachments, type Attachment } from "./hooks/useAttachments";
import { useCitations, type Citation } from "./hooks/useCitations";
import { useVoiceInput } from "./hooks/useVoiceInput";
import { SessionSidebar } from "./SessionSidebar";
import { ModelSelectorMenu } from "./ModelSelectorMenu";
import { ErrorBoundary } from "@/components/ErrorBoundary";

interface ChatHeaderProps {
  status: ConnectionStatus;
  model: string | null;
  modelProvider: string | null;
  sessionId: string | null;
  tokensUsed: number;
  tokensMax: number;
  /** Título de la conversación que se está viendo. */
  title?: string | null;
}

function ChatHeader({
  status,
  model,
  modelProvider,
  sessionId,
  tokensUsed,
  tokensMax,
  title,
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
      <div className="flex min-w-0 items-center gap-2">
        <span className={"size-2 rounded-full shrink-0 " + statusColor} />
        <span className="truncate text-sm font-semibold text-foreground">
          {title || (status === "connecting" ? "Conectando..." : "Nueva conversación")}
        </span>
        {model && (
          <span className="hidden shrink-0 items-center gap-1 text-xs text-muted-foreground sm:flex">
            <span>·</span>
            <span className="max-w-[180px] truncate">
              {model}
              {modelProvider ? " · " + modelProvider : ""}
            </span>
          </span>
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

function MessageActions({
  content,
  role,
  onRegenerate,
  canRegenerate,
  onQuote,
}: {
  content: string;
  role: "user" | "assistant";
  onRegenerate?: () => void;
  canRegenerate?: boolean;
  onQuote?: () => void;
}) {
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
        {copied ? "Copiado" : "Copiar"}
      </button>
      {onQuote && (
        <button
          type="button"
          onClick={onQuote}
          title="Citar este mensaje como contexto"
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <Quote className="size-3" />
          Citar
        </button>
      )}
      {onRegenerate && (
        <button
          type="button"
          onClick={onRegenerate}
          disabled={!canRegenerate}
          title={
            canRegenerate
              ? "Regenerar respuesta"
              : "Esperá a que termine la respuesta"
          }
          className={
            "flex items-center gap-1 text-xs transition-colors " +
            (canRegenerate
              ? "text-muted-foreground hover:text-foreground"
              : "text-muted-foreground opacity-40 cursor-not-allowed")
          }
        >
          <RotateCw className="size-3" />
          Regenerar
        </button>
      )}
      {role === "assistant" && (
        <button
          type="button"
          disabled
          title="Editar — disponible próximamente"
          className="flex items-center gap-1 text-xs text-muted-foreground opacity-40 cursor-not-allowed"
        >
          <Pencil className="size-3" />
          Editar
        </button>
      )}
    </div>
  );
}

// Panel colapsable con el "pensamiento" de modelos thinking (reasoning.delta).
function ReasoningPanel({
  text,
  streaming,
}: {
  text: string;
  streaming?: boolean;
}) {
  // Abierto mientras piensa (para ver el razonamiento en vivo); colapsable a mano.
  // Los turnos cargados del historial llegan con streaming=false → colapsados.
  const [open, setOpen] = useState(!!streaming);
  return (
    <div className="rounded-lg border border-border/60 bg-muted/15">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronRight
          className={"size-3 transition-transform " + (open ? "rotate-90" : "")}
        />
        <Brain className="size-3 text-[#6C4FD6]" />
        <span>{streaming ? "Pensando…" : "Razonamiento"}</span>
      </button>
      {open && (
        <div className="max-h-64 overflow-auto whitespace-pre-wrap border-t border-border/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
          {text}
        </div>
      )}
    </div>
  );
}

// memo: durante el streaming, message.delta crea un nuevo objeto SOLO para el
// último mensaje (los anteriores conservan su referencia), así que con props
// estables (onRegenerate/onQuote/canRegenerate) solo re-renderiza el mensaje
// que está llegando — no toda la conversación.
const MessageBubble = memo(function MessageBubble({
  message,
  onRegenerate,
  canRegenerate,
  onQuote,
}: {
  message: ChatMessage;
  onRegenerate?: () => void;
  canRegenerate?: boolean;
  onQuote?: (message: ChatMessage) => void;
}) {
  const isUser = message.role === "user";

  const actions = !message.streaming ? (
    <MessageActions
      content={message.content}
      role={message.role}
      onRegenerate={onRegenerate}
      canRegenerate={canRegenerate}
      onQuote={onQuote ? () => onQuote(message) : undefined}
    />
  ) : null;

  // Usuario: burbuja a la derecha (estilo Claude).
  if (isUser) {
    return (
      <div className="group flex flex-col items-end gap-1.5 py-3">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-muted/50 px-4 py-2.5 text-sm leading-relaxed text-foreground">
          {message.content}
        </div>
        {actions}
      </div>
    );
  }

  // Asistente: texto flush con avatar mínimo.
  return (
    <div className="group flex gap-3 py-4">
      <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[#6C4FD6] text-white">
        <Zap className="size-3.5" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="text-[15px] leading-relaxed text-foreground">
          <Markdown content={message.content} streaming={message.streaming} />
        </div>

        {message.toolCalls.length > 0 && (
          <div className="mt-1 flex flex-col gap-1.5">
            {message.toolCalls.map((tc) => (
              <ToolCallRow key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {message.reasoning && (
          <ReasoningPanel
            text={message.reasoning}
            streaming={message.streaming}
          />
        )}

        {actions}
      </div>
    </div>
  );
});

function AttachmentChip({
  attachment,
  onRemove,
}: {
  attachment: Attachment;
  onRemove: () => void;
}) {
  const sizeKb = (attachment.size / 1024).toFixed(1);
  return (
    <div className="flex items-center gap-1.5 rounded border border-border bg-muted/30 px-2 py-1 text-xs">
      <FileText className="size-3 shrink-0 text-[#6C4FD6]" />
      <span className="max-w-[180px] truncate font-mono text-foreground" title={attachment.name}>
        {attachment.name}
      </span>
      <span className="text-muted-foreground">· {sizeKb}KB</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={"Quitar " + attachment.name}
        className="ml-0.5 rounded p-0.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive transition-colors"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}

function CitationChip({
  citation,
  onRemove,
}: {
  citation: Citation;
  onRemove: () => void;
}) {
  const who = citation.role === "user" ? "Tú" : "Clawksis";
  return (
    <div className="flex items-center gap-1.5 rounded border border-[#6C4FD6]/40 bg-[#6C4FD6]/10 px-2 py-1 text-xs">
      <Quote className="size-3 shrink-0 text-[#6C4FD6]" />
      <span className="shrink-0 text-muted-foreground">{who}:</span>
      <span
        className="max-w-[200px] truncate text-foreground"
        title={citation.excerpt}
      >
        {citation.excerpt}
      </span>
      <button
        type="button"
        onClick={onRemove}
        aria-label="Quitar cita"
        className="ml-0.5 rounded p-0.5 text-muted-foreground hover:bg-destructive/20 hover:text-destructive transition-colors"
      >
        <X className="size-3" />
      </button>
    </div>
  );
}

interface ComposerProps {
  busy: boolean;
  disabled: boolean;
  onSend: (text: string) => void;
  onInterrupt: () => void;
  sendRpc: RpcSender;
  ready: boolean;
  sessionId: string | null;
  currentModel: string | null;
  citations: Citation[];
  onRemoveCitation: (id: string) => void;
  onClearCitations: () => void;
  buildPromptWithQuotes: (text: string) => string;
}

function Composer({
  busy,
  disabled,
  onSend,
  onInterrupt,
  sendRpc,
  ready,
  sessionId,
  currentModel,
  citations,
  onRemoveCitation,
  onClearCitations,
  buildPromptWithQuotes,
}: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const voice = useVoiceInput();
  const {
    attachments,
    addFiles,
    removeAttachment,
    clear: clearAttachments,
    error: attachError,
    buildPromptWithAttachments,
  } = useAttachments();

  const handleMic = () => {
    if (voice.listening) {
      voice.stop();
      return;
    }
    // Lo dictado se agrega después de lo ya escrito (en vivo con Web Speech).
    const base = value.trim().length > 0 ? value.replace(/\s+$/, "") + " " : "";
    void voice.start((t) => setValue(base + t));
  };

  const canSend =
    (value.trim().length > 0 ||
      attachments.length > 0 ||
      citations.length > 0) &&
    !busy &&
    !disabled;

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [value]);

  const handleSubmit = () => {
    if (!canSend) return;
    if (voice.listening) voice.stop();
    const finalPrompt = buildPromptWithAttachments(buildPromptWithQuotes(value));
    onSend(finalPrompt);
    setValue("");
    clearAttachments();
    onClearCitations();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handlePaperclipClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await addFiles(files);
    }
    // Reset input para que se pueda seleccionar el mismo archivo otra vez
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="border-t border-border px-4 py-3">
      <div className="mx-auto w-full max-w-3xl">
      {/* Chips de citas */}
      {citations.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {citations.map((c) => (
            <CitationChip
              key={c.id}
              citation={c}
              onRemove={() => onRemoveCitation(c.id)}
            />
          ))}
        </div>
      )}

      {/* Chips de archivos adjuntos */}
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {attachments.map((att) => (
            <AttachmentChip
              key={att.id}
              attachment={att}
              onRemove={() => removeAttachment(att.id)}
            />
          ))}
        </div>
      )}

      {/* Error de adjuntar / voz */}
      {(attachError || voice.error) && (
        <div className="mb-2 flex items-center gap-2 rounded border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          <AlertCircle className="size-3 shrink-0" />
          <span>{attachError ?? voice.error}</span>
        </div>
      )}

      {/* Input file oculto */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".txt,.md,.markdown,.json,.yaml,.yml,.toml,.xml,.py,.ts,.tsx,.js,.jsx,.mjs,.cjs,.rs,.go,.java,.kt,.rb,.php,.swift,.c,.cpp,.h,.hpp,.cs,.sh,.bash,.zsh,.fish,.html,.css,.scss,.sass,.csv,.tsv,.sql,.env,.ini,.conf,.cfg,.log,.vue,.svelte,.graphql,.gql,text/*"
        onChange={handleFileInputChange}
        className="hidden"
      />

      {/* Composer principal — layout tipo Claude: textarea arriba, controles abajo */}
      <div className="rounded-2xl border border-border bg-muted/20 px-3 py-2.5 focus-within:border-[#6C4FD6]/60 transition-colors">
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
          className="w-full resize-none bg-transparent px-1 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground outline-none disabled:opacity-50"
        />
        <div className="mt-1.5 flex items-center gap-1">
          <button
            type="button"
            onClick={handlePaperclipClick}
            disabled={disabled}
            aria-label="Adjuntar archivo"
            title="Adjuntar archivo de texto (.txt, .md, .py, .ts, etc — máx 100KB)"
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
          >
            <Paperclip className="size-4" />
          </button>
          <ModelSelectorMenu
            sendRpc={sendRpc}
            ready={ready}
            sessionId={sessionId}
            currentModel={currentModel}
            disabled={disabled || busy}
          />

          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={handleMic}
              disabled={disabled || !voice.supported || voice.transcribing}
              aria-label={
                voice.listening ? "Detener grabación" : "Dictar por voz"
              }
              title={
                !voice.supported
                  ? "Tu navegador no soporta dictado por voz"
                  : voice.transcribing
                    ? "Transcribiendo…"
                    : voice.listening
                      ? "Detener (hablá y se transcribe en vivo)"
                      : voice.live
                        ? "Dictar por voz — transcripción en vivo"
                        : "Dictar por voz — se transcribe al soltar"
              }
              className={
                "rounded-lg p-1.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent " +
                (voice.listening
                  ? "bg-destructive/15 text-destructive animate-pulse"
                  : "text-muted-foreground hover:bg-muted/40 hover:text-foreground")
              }
            >
              {voice.transcribing ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Mic className="size-4" />
              )}
            </button>

            {busy ? (
              <button
                type="button"
                onClick={onInterrupt}
                aria-label="Interrumpir"
                className="flex size-8 items-center justify-center rounded-lg bg-destructive text-white hover:bg-destructive/80 transition-colors"
              >
                <Square className="size-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSend}
                aria-label="Enviar mensaje"
                className={
                  "flex size-8 items-center justify-center rounded-lg transition-colors " +
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
    clearError,
    sendRpc,
    readyForRpc,
    switchSession,
    regenerateLast,
  } = useChatGateway();

  const {
    sessions,
    loading: sessionsLoading,
    error: sessionsError,
    createSession,
    deleteSession,
  } = useSessions(sendRpc, readyForRpc);

  const {
    citations,
    addCitation,
    removeCitation,
    clear: clearCitations,
    buildPromptWithQuotes,
  } = useCitations();

  // Estable para que memo(MessageBubble) no re-renderice toda la lista.
  const handleQuote = useCallback(
    (m: ChatMessage) => addCitation({ role: m.role, content: m.content }),
    [addCitation],
  );

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

  const handleDeleteSession = async (id: string) => {
    if (!window.confirm("¿Borrar esta conversación? No se puede deshacer.")) return;
    const wasActive = id === session.sessionId;
    const fallback = sessions.find((s) => s.id !== id);
    await deleteSession(id);
    if (wasActive) {
      if (fallback) await switchSession(fallback.id);
      else await handleNewChat();
    }
  };

  // Título de la conversación que se está viendo (para el header).
  const activeSession = sessions.find((s) => s.id === session.sessionId);
  const activeTitle = activeSession ? deriveTitle(activeSession) : null;

  return (
    <div className="flex h-full min-h-0 flex-row rounded-lg border border-border bg-background overflow-hidden">
      <SessionSidebar
        sessions={sessions}
        activeSessionId={session.sessionId}
        loading={sessionsLoading}
        error={sessionsError}
        onSelectSession={handleSelectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
      />

      <div className="flex min-h-0 flex-1 flex-col">
        <ChatHeader
          status={status}
          model={session.model}
          modelProvider={session.modelProvider}
          sessionId={session.sessionId}
          tokensUsed={session.tokensUsed}
          tokensMax={session.tokensMax}
          title={activeTitle}
        />

        <ConnectionBanner status={status} errorMessage={errorMessage} />

        {/* Error a mitad de turno (conectado): el agente falló — mostralo en
            vez de quedar colgado en "Pensando...". Descartable. */}
        {status === "connected" && errorMessage && (
          <div className="flex items-center gap-2 border-b border-destructive/40 bg-destructive/10 px-4 py-2 text-xs text-destructive">
            <AlertCircle className="size-3 shrink-0" />
            <span className="min-w-0 flex-1 break-words">{errorMessage}</span>
            <button
              type="button"
              onClick={clearError}
              aria-label="Descartar error"
              className="shrink-0 rounded p-0.5 transition-colors hover:bg-destructive/20"
            >
              <X className="size-3" />
            </button>
          </div>
        )}

        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {messages.length === 0 && !isConnecting ? (
            <EmptyState />
          ) : (
            <div className="mx-auto flex w-full max-w-3xl flex-col px-4 py-2">
              {messages.map((msg, idx) => {
                const isLast =
                  idx === messages.length - 1 && msg.role === "assistant";
                return (
                  <ErrorBoundary key={msg.id} resetKey={msg.content}>
                    <MessageBubble
                      message={msg}
                      onRegenerate={isLast ? regenerateLast : undefined}
                      canRegenerate={isLast && !busy}
                      onQuote={handleQuote}
                    />
                  </ErrorBoundary>
                );
              })}
            </div>
          )}
        </div>

        <Composer
          busy={busy}
          disabled={composerDisabled}
          onSend={sendMessage}
          onInterrupt={interrupt}
          sendRpc={sendRpc}
          ready={readyForRpc}
          sessionId={session.sessionId}
          currentModel={session.model}
          citations={citations}
          onRemoveCitation={removeCitation}
          onClearCitations={clearCitations}
          buildPromptWithQuotes={buildPromptWithQuotes}
        />
      </div>
    </div>
  );
}
