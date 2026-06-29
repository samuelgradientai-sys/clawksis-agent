/**
 * ChatModern — Modo "moderno" del chat con sidebar de sesiones (Fase 2.7)
 * + file picker funcional en el composer (Fase 2.8 B1).
 *
 * Layout: sidebar 240px + body flex-1.
 * Composer: textarea + chips de archivos adjuntos arriba + botones (Paperclip
 * funcional, Mic placeholder).
 */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { useTokenUsage } from "./hooks/useTokenUsage";
import { TokenUsagePopover } from "./TokenUsagePopover";
import { useAttachments, type Attachment } from "./hooks/useAttachments";
import { useCitations, type Citation } from "./hooks/useCitations";
import { useVoiceInput } from "./hooks/useVoiceInput";
import { useImageAttachments } from "./hooks/useImageAttachments";
import { useCommandHistory } from "./hooks/useCommandHistory";
import { SessionSidebar } from "./SessionSidebar";
import { ModelSelectorMenu } from "./ModelSelectorMenu";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { SlashPopover, type SlashPopoverHandle } from "@/components/SlashPopover";
import { ModelPickerDialog } from "@/components/ModelPickerDialog";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import type { GatewayClient } from "@/lib/gatewayClient";

interface ChatHeaderProps {
  status: ConnectionStatus;
  model: string | null;
  modelProvider: string | null;
  sessionId: string | null;
  tokensUsed: number;
  tokensMax: number;
  /** Título de la conversación que se está viendo. */
  title?: string;
  /** Click handler para abrir el popover de uso de tokens */
  onTokensClick?: () => void;
  /** Ref del botón de tokens para anclar el popover */
  tokensRef?: React.RefObject<HTMLButtonElement | null>;
}

function ChatHeader({
  status,
  model,
  modelProvider,
  sessionId,
  tokensUsed,
  tokensMax,
  title,
  onTokensClick,
  tokensRef,
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

  const tokenPercent =
    tokensMax > 0
      ? Math.min(100, Math.round((tokensUsed / tokensMax) * 100))
      : null;

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

      <button
        type="button"
        ref={tokensRef}
        onClick={onTokensClick}
        disabled={!onTokensClick}
        title={"Ver desglose de uso de tokens · sesión " + shortSession}
        className="hidden md:flex items-center gap-2 rounded-lg border border-[#6C4FD6]/40 bg-[#6C4FD6]/10 px-3 py-1.5 text-xs text-foreground shadow-sm transition-colors hover:border-[#6C4FD6]/70 hover:bg-[#6C4FD6]/20 disabled:cursor-default disabled:opacity-60"
        aria-label="Abrir menú de uso de tokens"
      >
        <Brain className="size-3.5 text-[#6C4FD6]" />
        <span className="font-medium">Uso de tokens</span>
        <span className="hidden text-muted-foreground lg:inline">·</span>
        <span className="font-mono text-foreground/90">{tokensLabel}</span>
        {tokenPercent !== null && (
          <span className="rounded bg-background/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            {tokenPercent}%
          </span>
        )}
        <ChevronRight className="size-3 rotate-90 text-muted-foreground" />
      </button>
    </div>
  );
}


function ProjectCreateDialog({
  open,
  error,
  onClose,
  onCreate,
}: {
  open: boolean;
  error: string | null;
  onClose: () => void;
  onCreate: (name: string) => void;
}) {
  const [name, setName] = useState("");

  useEffect(() => {
    if (open) {
      setName("");
    }
  }, [open]);

  if (!open) return null;

  const submit = () => {
    const cleanName = name.trim();
    if (!cleanName) return;
    onCreate(cleanName);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 px-4 backdrop-blur-sm">
      <div className="w-full max-w-md overflow-hidden rounded-2xl border border-[#6C4FD6]/40 bg-popover text-popover-foreground shadow-2xl shadow-[#6C4FD6]/20">
        <div className="border-b border-border px-5 py-4">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-full bg-[#6C4FD6]/20 text-[#6C4FD6]">
              <span className="text-sm font-bold">C</span>
            </div>
            <div>
              <div className="text-sm font-semibold text-foreground">
                Nuevo proyecto
              </div>
              <div className="text-xs text-muted-foreground">
                Crea un espacio separado para conversaciones relacionadas.
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-3 px-5 py-4">
          <label className="block text-xs font-medium text-muted-foreground">
            Nombre del proyecto
          </label>

          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
              if (e.key === "Escape") onClose();
            }}
            placeholder="Ej. Agencia, Inventario, Clientes..."
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-[#6C4FD6] focus:ring-2 focus:ring-[#6C4FD6]/25"
          />

          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border bg-muted/10 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-border bg-background px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground"
          >
            Cancelar
          </button>

          <button
            type="button"
            onClick={submit}
            disabled={!name.trim()}
            className="rounded-lg bg-[#6C4FD6] px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-[#5a40c2] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Crear proyecto
          </button>
        </div>
      </div>
    </div>
  );
}

// Auto-render de media en resultados de tools (image_generate / video_generate
// / cualquier tool que devuelva una imagen o video): así "generá una imagen de
// X" muestra la imagen sola en el chat, sin depender de que el agente la embeba
// en markdown.
const _TOOL_IMG_RE = /\.(png|jpe?g|gif|webp|svg|bmp|avif)(?:[?#]|$)/i;
const _TOOL_VID_RE = /\.(mp4|webm|mov|m4v|ogv|ogg)(?:[?#]|$)/i;

function _toolMediaSrc(raw: string): string | null {
  const s = raw.trim();
  // Solo lo definitivamente servible: http(s) y same-origin /artifacts|/api.
  // Los archivos locales generados llegan ya como /artifacts/download?path=…
  // (el backend los copia a ~/clawksis_exports); NO intentamos servir paths
  // locales crudos para no mostrar imágenes rotas (403 fuera de exports).
  if (/^https?:\/\//i.test(s)) return s;
  if (s.startsWith("/artifacts/") || s.startsWith("/api/")) return s;
  return null;
}

function extractToolMedia(result: unknown): { src: string; video: boolean }[] {
  let obj: unknown = result;
  if (typeof result === "string") {
    try {
      obj = JSON.parse(result);
    } catch {
      return [];
    }
  }
  if (!obj || typeof obj !== "object") return [];
  const rec = obj as Record<string, unknown>;
  if (rec.success === false) return [];

  const candidates: string[] = [];
  for (const k of ["image", "video", "url", "chat_url", "host_image"]) {
    if (typeof rec[k] === "string") candidates.push(rec[k] as string);
  }
  if (Array.isArray(rec.images)) {
    for (const im of rec.images) {
      const u = (im as Record<string, unknown>)?.url;
      if (typeof u === "string") candidates.push(u);
    }
  }

  const out: { src: string; video: boolean }[] = [];
  const seen = new Set<string>();
  for (const c of candidates) {
    const probe = c.includes("path=")
      ? decodeURIComponent(c.split("path=")[1] ?? "")
      : c;
    const isVid = _TOOL_VID_RE.test(c) || _TOOL_VID_RE.test(probe);
    const isImg = _TOOL_IMG_RE.test(c) || _TOOL_IMG_RE.test(probe);
    if (!isVid && !isImg) continue;
    const src = _toolMediaSrc(c);
    if (!src || seen.has(src)) continue;
    seen.add(src);
    out.push({ src, video: isVid });
  }
  return out;
}

function ToolCallRow({ toolCall }: { toolCall: ToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = toolCall.status === "running";
  const argsPreview = Object.entries(toolCall.args)
    .map(([k, v]) => k + "=" + (typeof v === "string" ? v : JSON.stringify(v)))
    .join(" ")
    .slice(0, 120);
  const media = useMemo(
    () => (isRunning ? [] : extractToolMedia(toolCall.result)),
    [isRunning, toolCall.result],
  );

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

      {media.length > 0 && (
        <div className="ml-5 flex flex-wrap gap-2">
          {media.map((m, idx) =>
            m.video ? (
              <video
                key={idx}
                src={m.src}
                controls
                preload="metadata"
                className="max-h-80 max-w-full rounded-lg border border-border"
              />
            ) : (
              <img
                key={idx}
                src={m.src}
                loading="lazy"
                alt="resultado generado"
                className="max-h-80 max-w-full rounded-lg border border-border"
              />
            ),
          )}
        </div>
      )}

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
  // (Init desde `streaming`: cubre el caso normal — el panel aparece cuando llega
  // el primer reasoning.delta, con streaming=true.)
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

// Indicador "pensando…" mientras la respuesta del asistente está en streaming
// pero todavía no llegó el primer token (ni reasoning ni tool calls). Sin esto
// la burbuja queda vacía (solo el avatar) y el chat "se siente colgado" aunque
// el time-to-first-token sea igual al del modo Terminal (que sí muestra spinner).
function TypingDots() {
  return (
    <div
      className="flex items-center gap-1 py-1.5"
      role="status"
      aria-label="Pensando…"
    >
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.3s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.15s]" />
      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
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
  const isCommand = message.content.trim().startsWith("/");
  const isSlashOutput =
    message.role === "assistant" && message.id.startsWith("slash-");

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
        {message.images && message.images.length > 0 && (
          <div className="flex max-w-[85%] flex-wrap justify-end gap-2">
            {message.images.map((img, i) => (
              <img
                key={i}
                src={img.previewUrl}
                alt={img.name}
                loading="lazy"
                className="max-h-48 max-w-[12rem] rounded-lg border border-border object-cover"
              />
            ))}
          </div>
        )}
        <div
          className={
            "max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-2.5 text-sm leading-relaxed text-foreground " +
            (isCommand
              ? "border border-[#6C4FD6]/30 bg-[#6C4FD6]/10 font-mono"
              : "bg-muted/50")
          }
        >
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
        <span className="text-xs font-bold leading-none">C</span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {isSlashOutput ? (
          <SlashOutput content={message.content} />
        ) : message.streaming &&
          !message.content &&
          message.toolCalls.length === 0 &&
          !message.reasoning ? (
          <TypingDots />
        ) : (
          <div className="text-[15px] leading-relaxed text-foreground">
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

const SLASH_OUTPUT_COLLAPSE_CHARS = 1200;
const SLASH_OUTPUT_COLLAPSE_LINES = 18;

/** Salida de un comando slash: borde de acento + colapso de salidas largas. */
function SlashOutput({ content }: { content: string }) {
  const long =
    content.length > SLASH_OUTPUT_COLLAPSE_CHARS ||
    content.split("\n").length > SLASH_OUTPUT_COLLAPSE_LINES;
  const [expanded, setExpanded] = useState(false);
  const collapsed = long && !expanded;
  return (
    <div className="rounded-md border-l-2 border-[#6C4FD6]/40 bg-muted/20 py-1.5 pl-3 pr-2">
      <div
        className={
          "text-[15px] leading-relaxed text-foreground" +
          (collapsed
            ? " max-h-72 overflow-hidden [mask-image:linear-gradient(to_bottom,black_70%,transparent)]"
            : "")
        }
      >
        <Markdown content={content} streaming={false} />
      </div>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-1 text-xs font-medium text-[#6C4FD6] hover:underline"
        >
          {expanded ? "Mostrar menos" : "Mostrar más"}
        </button>
      )}
    </div>
  );
}

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
  resuming: boolean;
  onSend: (text: string, images?: { previewUrl: string; name: string }[]) => void;
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
  resuming,
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
  // Historial de inputs (↑/↓ tipo terminal) + flag para reposicionar el caret.
  const history = useCommandHistory();
  const caretToEndRef = useRef(false);
  const voice = useVoiceInput();
  // Slash-command autocomplete (mismo backend que el terminal: complete.slash).
  const slashRef = useRef<SlashPopoverHandle>(null);
  const slashGw = useMemo(
    () =>
      ({
        request: (m: string, p?: Record<string, unknown>) => sendRpc(m, p),
      }) as unknown as GatewayClient,
    [sendRpc],
  );
  const {
    attachments,
    addFiles,
    removeAttachment,
    clear: clearAttachments,
    error: attachError,
    buildPromptWithAttachments,
  } = useAttachments();
  const {
    images,
    addImage,
    removeImage,
    clear: clearImages,
    error: imgError,
  } = useImageAttachments(sendRpc, sessionId);
  const [dragging, setDragging] = useState(false);

  // Pegar / soltar: imágenes → adjunto de imagen (upload + image.attach);
  // documentos de texto → adjunto inline (useAttachments).
  const handleIncomingFiles = async (files: File[]) => {
    const textFiles: File[] = [];
    for (const f of files) {
      if (f.type.startsWith("image/")) await addImage(f);
      else textFiles.push(f);
    }
    if (textFiles.length) await addFiles(textFiles);
  };

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData?.files ?? []);
    if (files.length > 0) {
      e.preventDefault();
      void handleIncomingFiles(files);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer?.files ?? []);
    if (files.length > 0) void handleIncomingFiles(files);
  };

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
      citations.length > 0 ||
      images.length > 0) &&
    !busy &&
    !disabled;

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
  }, [value]);

  // Tras recuperar una entrada del historial, poner el caret al final.
  useEffect(() => {
    if (!caretToEndRef.current) return;
    caretToEndRef.current = false;
    const ta = textareaRef.current;
    if (ta) ta.selectionStart = ta.selectionEnd = ta.value.length;
  }, [value]);

  const handleSubmit = () => {
    if (!canSend) return;
    if (voice.listening) voice.stop();
    let finalPrompt = buildPromptWithAttachments(buildPromptWithQuotes(value));
    // Solo imágenes (sin texto): el prompt quedaría vacío y el backend
    // descartaría el turno, dejando la imagen huérfana. Mandamos un prompt mínimo.
    if (!finalPrompt.trim() && images.length > 0) {
      finalPrompt = "¿Qué ves en esta imagen?";
    }
    if (!finalPrompt.trim()) return;
    history.push(value);
    onSend(
      finalPrompt,
      images.map((i) => ({ previewUrl: i.previewUrl, name: i.name })),
    );
    setValue("");
    clearAttachments();
    onClearCitations();
    // Las imágenes ya están stageadas en la sesión (image.attach); el backend
    // las consume en este turno. Limpiamos los chips locales.
    clearImages();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // El popover de comandos consume Arrow/Tab/Escape cuando está visible.
    if (slashRef.current?.handleKey(e)) return;

    // ↑/↓ navegan el historial de inputs cuando el caret está en la primera/
    // última línea (no interfiere con edición multilínea ni con el popover).
    const pos = e.currentTarget.selectionStart ?? 0;
    if (e.key === "ArrowUp" && !value.slice(0, pos).includes("\n")) {
      const entry = history.prev(value);
      if (entry !== null) {
        e.preventDefault();
        caretToEndRef.current = true;
        setValue(entry);
        return;
      }
    }
    if (e.key === "ArrowDown" && !value.slice(pos).includes("\n")) {
      const entry = history.next();
      if (entry !== null) {
        e.preventDefault();
        caretToEndRef.current = true;
        setValue(entry);
        return;
      }
    }

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
      await handleIncomingFiles(Array.from(files));
    }
    // Reset input para que se pueda seleccionar el mismo archivo otra vez
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="border-t border-border px-4 py-3">
      <div
        className="relative mx-auto w-full max-w-3xl"
        onDragOver={(e) => {
          e.preventDefault();
          if (!dragging) setDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          // Ignorar el dragleave que cruza hacia un hijo (textarea/botones):
          // si no, el overlay parpadea al mover el mouse por dentro.
          if (e.currentTarget.contains(e.relatedTarget as Node)) return;
          setDragging(false);
        }}
        onDrop={handleDrop}
      >
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-2xl border-2 border-dashed border-[#6C4FD6] bg-[#6C4FD6]/10 text-sm font-medium text-foreground">
            Soltá para adjuntar (imágenes o documentos)
          </div>
        )}
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

      {/* Chips de imágenes (pegadas / arrastradas) */}
      {images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {images.map((img) => (
            <div key={img.id} className="group relative">
              <img
                src={img.previewUrl}
                alt={img.name}
                title={img.name}
                className="size-14 rounded-md border border-border object-cover"
              />
              <button
                type="button"
                onClick={() => removeImage(img.id)}
                aria-label={"Quitar " + img.name}
                className="absolute -right-1.5 -top-1.5 rounded-full bg-destructive p-0.5 text-white opacity-0 transition-opacity group-hover:opacity-100"
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Error de adjuntar / voz / imagen */}
      {(attachError || voice.error || imgError) && (
        <div className="mb-2 flex items-center gap-2 rounded border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          <AlertCircle className="size-3 shrink-0" />
          <span>{attachError ?? voice.error ?? imgError}</span>
        </div>
      )}

      {/* Input file oculto */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".txt,.md,.markdown,.json,.yaml,.yml,.toml,.xml,.py,.ts,.tsx,.js,.jsx,.mjs,.cjs,.rs,.go,.java,.kt,.rb,.php,.swift,.c,.cpp,.h,.hpp,.cs,.sh,.bash,.zsh,.fish,.html,.css,.scss,.sass,.csv,.tsv,.sql,.env,.ini,.conf,.cfg,.log,.vue,.svelte,.graphql,.gql,text/*,image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp"
        title="Adjuntar archivo de texto o imagen"
        onChange={handleFileInputChange}
        className="hidden"
      />

      {/* Composer principal — layout tipo Claude: textarea arriba, controles abajo */}
      <div className="relative rounded-2xl border border-border bg-muted/20 px-3 py-2.5 focus-within:border-[#6C4FD6]/60 transition-colors">
        {/* Autocomplete de slash commands (/) — flota sobre el composer. */}
        <SlashPopover ref={slashRef} input={value} gw={slashGw} onApply={setValue} />
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            history.resetNav();
          }}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={
            resuming
              ? "Preparando conversación…"
              : disabled
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
            title="Adjuntar documento o imagen (también podés pegar o arrastrar)"
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
          <span className="text-sm font-bold leading-none text-[#6C4FD6]">C</span>
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


type SidebarActivityOverride = {
  started_at?: number;
  preview?: string;
  message_count?: number;
  model?: string;
  model_provider?: string;
  title?: string;
};

const SIDEBAR_ACTIVITY_CACHE_KEY = "clawksis.chat.sidebarActivityOverrides.v1";

function readSidebarActivityOverrides(): Record<string, SidebarActivityOverride> {
  try {
    if (typeof window === "undefined") return {};
    const raw = window.localStorage.getItem(SIDEBAR_ACTIVITY_CACHE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeSidebarActivityOverrides(
  value: Record<string, SidebarActivityOverride>,
): void {
  try {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_ACTIVITY_CACHE_KEY, JSON.stringify(value));
  } catch {
    // No bloquear el chat si localStorage está lleno o deshabilitado.
  }
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
    liveStatus,
    clearError,
    sendRpc,
    readyForRpc,
    switchSession,
    resuming,
    regenerateLast,
  } = useChatGateway();

  const {
    sessions,
    projects,
    loading: sessionsLoading,
    error: sessionsError,
    createSession,
    deleteSession,
    createProject,
    moveSessionToProject,
    refresh: refreshSessions,
  } = useSessions(sendRpc, readyForRpc);

  const {
    sessionUsage,
    usageByModel,
    loading: tokenUsageLoading,
    error: tokenUsageError,
    refresh: refreshTokenUsage,
  } = useTokenUsage(sendRpc, readyForRpc);

  const tokensButtonRef = useRef<HTMLButtonElement>(null);
  const [tokensPopoverOpen, setTokensPopoverOpen] = useState(false);
  const didAutoOpenSidebarTopRef = useRef(false);
  // ID solo visual para resaltar el sidebar. No se usa para enviar mensajes.
  const [visualActiveSessionId, setVisualActiveSessionId] = useState<string | null>(null);
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [projectDialogError, setProjectDialogError] = useState<string | null>(null);

  // Comandos interactivos interceptados: en el worker headless (sin TTY) el
  // picker de /model y los modales de confirmación destructivos se cuelgan, así
  // que los resolvemos con UI nativa de React.
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [destructiveConfirm, setDestructiveConfirm] = useState<{
    command: string;
    raw: string;
  } | null>(null);
  // Adapter mínimo sobre sendRpc para los diálogos que esperan un GatewayClient.
  const gwForDialogs = useMemo(
    () =>
      ({
        request: (method: string, params?: Record<string, unknown>) =>
          sendRpc(method, params),
      }) as unknown as GatewayClient,
    [sendRpc],
  );

  // optimistic-new-chat-sidebar-v1
  // Conversaciones creadas localmente que aún no aparecen en session.list.
  const [optimisticSessions, setOptimisticSessions] = useState<
    Array<(typeof sessions)[number]>
  >([]);

  // sidebar-recency-override-v1
  // Actividad local reciente: mueve conversaciones viejas arriba inmediatamente
  // al enviar un mensaje, incluso antes de que session.list persista/ordene.
  const [sidebarActivityOverrides, setSidebarActivityOverrides] = useState<
    Record<string, SidebarActivityOverride>
  >(() => readSidebarActivityOverrides());

  // sidebarSessions incluye filas optimistas y actividad local reciente.
  // Así "+ Nueva conversación" aparece sin esperar recarga y una conversación
  // vieja sube arriba inmediatamente al enviar un mensaje.
  const sidebarSessionMap = new Map<string, (typeof sessions)[number]>();

  for (const real of sessions) {
    const rawOverride = sidebarActivityOverrides[real.id] ?? {};
    const { title, model, model_provider, ...safeOverride } = rawOverride;

    sidebarSessionMap.set(real.id, {
      ...real,
      ...safeOverride,
      ...(typeof title === "string" ? { title } : {}),
      ...(typeof model === "string" ? { model } : {}),
      ...(typeof model_provider === "string" ? { model_provider } : {}),
    });
  }

  for (const optimistic of optimisticSessions) {
    const existing = sidebarSessionMap.get(optimistic.id);
    sidebarSessionMap.set(optimistic.id, {
      ...(existing ?? optimistic),
      ...optimistic,
    });
  }

  const sidebarSessions = Array.from(sidebarSessionMap.values()).sort(
    (a, b) => (b.started_at || 0) - (a.started_at || 0),
  );

  useEffect(() => {
    writeSidebarActivityOverrides(sidebarActivityOverrides);
  }, [sidebarActivityOverrides]);

  const sessionIdExistsInSidebar =
    !!session.sessionId && sidebarSessions.some((s) => s.id === session.sessionId);

  const newestListedSessionId = sidebarSessions[0]?.id ?? null;

  // ID visual para resaltar y consultar métricas persistidas.
  // session.sessionId sigue siendo el ID operativo vivo para backend.
  const sidebarActiveSessionId =
    visualActiveSessionId ?? (sessionIdExistsInSidebar ? session.sessionId : null);

  // sidebar-auto-open-top-on-boot-v1
  // Si localStorage reordenó el sidebar por actividad reciente, abrimos esa
  // conversación de verdad. Esto evita que el header/sidebar muestren una sesión
  // mientras el body todavía pertenece a otra sesión viva del gateway.
  useEffect(() => {
    if (didAutoOpenSidebarTopRef.current) return;
    if (!readyForRpc || sessionsLoading || resuming || busy) return;
    if (!newestListedSessionId) return;

    didAutoOpenSidebarTopRef.current = true;
    setVisualActiveSessionId(newestListedSessionId);

    if (newestListedSessionId !== session.sessionId) {
      void switchSession(newestListedSessionId);
    }
  }, [
    readyForRpc,
    sessionsLoading,
    resuming,
    busy,
    newestListedSessionId,
    session.sessionId,
    switchSession,
  ]);

  useEffect(() => {
    if (
      !visualActiveSessionId &&
      session.sessionId &&
      sessions.some((s) => s.id === session.sessionId)
    ) {
      setVisualActiveSessionId(session.sessionId);
    }
  }, [visualActiveSessionId, session.sessionId, sessions]);

  useEffect(() => {
    if (optimisticSessions.length === 0) return;
    setOptimisticSessions((prev) =>
      prev.filter((opt) => !sessions.some((real) => real.id === opt.id)),
    );
  }, [sessions, optimisticSessions.length]);


  // tokens-refresh-on-active-session-v1
  // Rehidrata el contador del header al recargar la página o cambiar de sesión.
  useEffect(() => {
    if (!readyForRpc || !sidebarActiveSessionId) return;
    void refreshTokenUsage(sidebarActiveSessionId);
  }, [readyForRpc, sidebarActiveSessionId, refreshTokenUsage]);

  // tokens-refresh-after-message-v1
  // Después de una respuesta, session.usage puede tardar un poco en persistir.
  // Refrescamos para que conversaciones nuevas no se queden en 0 tokens.
  useEffect(() => {
    if (!readyForRpc || busy || !sidebarActiveSessionId || messages.length === 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      void refreshTokenUsage(sidebarActiveSessionId);
    }, 800);

    return () => window.clearTimeout(timer);
  }, [readyForRpc, busy, messages.length, sidebarActiveSessionId, refreshTokenUsage]);



  const handleTokensClick = () => {
    const willOpen = !tokensPopoverOpen;
    setTokensPopoverOpen(willOpen);
    if (willOpen) {
      void refreshTokenUsage(sidebarActiveSessionId ?? session.sessionId);
    }
  };

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
  const composerDisabled =
    status !== "connected" || !session.sessionId || resuming;

  const handleSelectSession = (targetId: string) => {
    if (targetId === sidebarActiveSessionId) return;
    setVisualActiveSessionId(targetId);
    void switchSession(targetId);
  };

  const handleSend = (
    text: string,
    images?: { previewUrl: string; name: string }[],
  ) => {
    const trimmed = text.trim();

    // Comandos interactivos que cuelgan el worker headless (sin TTY): los
    // resolvemos con UI nativa de React en vez de mandarlos al worker.
    if (trimmed.startsWith("/")) {
      const base = trimmed.slice(1).split(/\s+/)[0].toLowerCase();
      const rest = trimmed.slice(1 + base.length).trim();
      // /model SIN args → picker React. Con args ("/model opus") va directo al
      // worker (es un config.set, funciona headless).
      if (base === "model" && !rest) {
        setModelPickerOpen(true);
        return;
      }
      // Destructivos → confirmación React; al confirmar añadimos el token de
      // skip ("now") para que el worker no abra su propio modal y cuelgue.
      if (
        (base === "new" || base === "reset" || base === "clear") &&
        !/(^|\s)(now|--yes|-y)(\s|$)/i.test(rest)
      ) {
        setDestructiveConfirm({ command: base, raw: trimmed });
        return;
      }
    }

    const activeId = sidebarActiveSessionId ?? session.sessionId;

    if (activeId && trimmed) {
      const current = sidebarSessions.find((s) => s.id === activeId);

      setSidebarActivityOverrides((prev) => ({
        ...prev,
        [activeId]: {
          started_at: Date.now() / 1000,
          preview: trimmed,
          message_count: Math.max((current?.message_count ?? 0) + 1, 1),
          model: session.model ?? current?.model ?? undefined,
        },
      }));

      setVisualActiveSessionId(activeId);
    }

    sendMessage(text, images);
  };

  const handleNewChat = async (projectId: string | null = null) => {
    const newId = await createSession();
    if (newId) {
      const project = projectId
        ? projects.find((p) => p.id === projectId) ?? null
        : null;

      setVisualActiveSessionId(newId);
      setOptimisticSessions((prev) => [
        {
          id: newId,
          title: project ? "Nuevo chat en " + project.name : "Nueva conversación",
          preview: "",
          source: "dashboard",
          started_at: Date.now() / 1000,
          message_count: 0,
          model: session.model,
          model_provider: session.modelProvider,
          project_id: project?.id ?? null,
          project_name: project?.name ?? null,
          project_archived: false,
        } as (typeof sessions)[number],
        ...prev.filter((s) => s.id !== newId),
      ]);

      if (projectId) {
        await moveSessionToProject(newId, projectId);
      }

      await switchSession(newId, { assumeLive: true });
      void refreshSessions();
      window.setTimeout(() => {
        void refreshSessions();
      }, 800);
      window.setTimeout(() => {
        void refreshSessions();
      }, 2000);
    }
  };

  const handleDeleteSession = async (id: string) => {
    if (!window.confirm("¿Borrar esta conversación? No se puede deshacer.")) return;
    // Si es la conversación activa, el gateway rechaza borrarla mientras está
    // viva. Soltamos la sesión (cambiando a otra / nueva) ANTES de borrarla.
    if (id === sidebarActiveSessionId) {
      const fallback = sessions.find((s) => s.id !== id);
      if (fallback) {
          setVisualActiveSessionId(fallback.id);
          await switchSession(fallback.id);
        }
      else await handleNewChat();
    }
    setSidebarActivityOverrides((prev) => {
      if (!(id in prev)) return prev;
      const next = { ...prev };
      delete next[id];
      return next;
    });
    await deleteSession(id);
  };

  const handleCreateProject = () => {
    setProjectDialogError(null);
    setProjectDialogOpen(true);
  };

  const handleSubmitProjectCreate = async (name: string) => {
    setProjectDialogError(null);

    const project = await createProject(name);
    if (!project) {
      setProjectDialogError("No se pudo crear el proyecto. Revisa si el nombre ya existe.");
      return;
    }

    setProjectDialogOpen(false);
    void refreshSessions();
  };

  const handleMoveSessionToProject = async (
    sessionId: string,
    projectId: string | null,
  ) => {
    await moveSessionToProject(sessionId, projectId);
    void refreshSessions();
  };

  // Título de la conversación que se está viendo (para el header).
  // Priorizamos session.title del gateway (en vivo, llega con session.info),
  // luego deriveTitle del listado (que tiene el title de la DB), y finalmente
  // null → el header muestra "Nueva conversación" como placeholder.
  const activeSession = sidebarSessions.find((s) => s.id === sidebarActiveSessionId);
  const headerTokensUsed =
    sessionUsage && sessionUsage.total > 0
      ? sessionUsage.total
      : session.tokensUsed;

  const headerTokensMax =
    sessionUsage && sessionUsage.context_max && sessionUsage.context_max > 0
      ? sessionUsage.context_max
      : session.tokensMax;

  // popover-token-fallback-v1
  // El header puede tener tokens restaurados aunque session.usage no tenga
  // desglose persistido. En ese caso mostramos al menos el total en el popover.
  const popoverSessionUsage =
    sessionUsage ??
    (headerTokensUsed > 0
      ? {
          model: session.model,
          provider: session.modelProvider,
          calls: 0,
          input: 0,
          output: 0,
          cache_read: 0,
          cache_write: 0,
          reasoning: 0,
          total: headerTokensUsed,
          cost_usd: null,
          cost_status: null,
          context_used: headerTokensUsed,
          context_max: headerTokensMax > 0 ? headerTokensMax : null,
          context_percent:
            headerTokensMax > 0
              ? Math.min(100, Math.round((headerTokensUsed / headerTokensMax) * 100))
              : null,
          compressions: 0,
        }
      : null);
  const activeTitle =
    session.title ??
    (activeSession ? deriveTitle(activeSession) : null);

  // Si el último turno fue un slash command, no ofrecer "Regenerar" (re-correría
  // el comando y session.undo borraría el turno real previo).
  const lastUserIsSlash = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user")
        return messages[i].content.trim().startsWith("/");
    }
    return false;
  })();

  return (
    <>
      <ProjectCreateDialog
        open={projectDialogOpen}
        error={projectDialogError}
        onClose={() => setProjectDialogOpen(false)}
        onCreate={handleSubmitProjectCreate}
      />

      {modelPickerOpen && (
        <ModelPickerDialog
          gw={gwForDialogs}
          sessionId={session.sessionId ?? undefined}
          onSubmit={(slashCommand) => {
            setModelPickerOpen(false);
            sendMessage(slashCommand);
          }}
          onClose={() => setModelPickerOpen(false)}
        />
      )}

      <ConfirmDialog
        open={!!destructiveConfirm}
        destructive
        title={`/${destructiveConfirm?.command ?? ""} — descarta la conversación`}
        description="Esto borra el estado de la conversación actual. ¿Continuar?"
        confirmLabel="Continuar"
        cancelLabel="Cancelar"
        onCancel={() => setDestructiveConfirm(null)}
        onConfirm={() => {
          const c = destructiveConfirm;
          setDestructiveConfirm(null);
          if (c) sendMessage(`${c.raw} now`);
        }}
      />

      <div className="flex h-full min-h-0 flex-row rounded-lg border border-border bg-background overflow-hidden">
      <SessionSidebar
        sessions={sidebarSessions}
        projects={projects}
        activeSessionId={sidebarActiveSessionId}
        loading={sessionsLoading}
        error={sessionsError}
        onSelectSession={handleSelectSession}
        onNewChat={() => handleNewChat(null)}
        onNewChatInProject={(projectId) => {
          void handleNewChat(projectId);
        }}
        onCreateProject={handleCreateProject}
        onDeleteSession={handleDeleteSession}
        onMoveSessionToProject={handleMoveSessionToProject}
      />

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="relative">
          <ChatHeader
            status={status}
            model={session.model}
            modelProvider={session.modelProvider}
            sessionId={session.sessionId}
            tokensUsed={headerTokensUsed}
            tokensMax={headerTokensMax}
            title={activeTitle ?? undefined}
            onTokensClick={handleTokensClick}
            tokensRef={tokensButtonRef}
          />
          <TokenUsagePopover
            open={tokensPopoverOpen}
            onClose={() => setTokensPopoverOpen(false)}
            loading={tokenUsageLoading}
            error={tokenUsageError}
            sessionUsage={popoverSessionUsage}
            usageByModel={usageByModel}
            anchorRef={tokensButtonRef}
          />
        </div>

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
          {resuming && messages.length === 0 ? (
            <div className="flex h-full items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Cargando conversación…
            </div>
          ) : messages.length === 0 && !isConnecting ? (
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
                      onRegenerate={
                        isLast && !lastUserIsSlash ? regenerateLast : undefined
                      }
                      canRegenerate={isLast && !busy}
                      onQuote={handleQuote}
                    />
                  </ErrorBoundary>
                );
              })}
              {liveStatus && busy && (
                <div className="flex items-center gap-2 px-1 py-2 text-xs text-muted-foreground">
                  <Loader2 className="size-3 shrink-0 animate-spin text-[#6C4FD6]" />
                  <span className="min-w-0 flex-1 break-words">{liveStatus}</span>
                </div>
              )}
            </div>
          )}
        </div>

        <Composer
          busy={busy}
          disabled={composerDisabled}
          resuming={resuming}
          onSend={handleSend}
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
    </>
  );
}
