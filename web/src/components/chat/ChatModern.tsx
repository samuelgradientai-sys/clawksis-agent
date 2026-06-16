import { useState } from "react";
import {
  Paperclip,
  Mic,
  ArrowUp,
  Copy,
  RotateCw,
  Pencil,
  ChevronRight,
  Plus,
  Zap,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { Markdown } from "../Markdown";

/**
 * ChatModern — Modo "moderno" del chat (Fase 2 del plan visual).
 *
 * Inspiración visual: Linear / Vercel
 * - Tipografía sans-serif (no monoespaciada)
 * - Burbuja sutil para mensajes del usuario, sin burbuja para asistente
 * - Avatar cuadrado pequeño (22-26px) con icono
 * - Tool calls plegadas mostrando nombre + estado
 * - Botones de acción visibles solo en hover
 * - Full-width con padding lateral
 * - Timestamps solo en hover
 *
 * Estado actual (Fase 2.1):
 * - Estructura visual completa con datos hardcoded
 * - SIN lógica de WebSocket / streaming real (eso viene en Fase 2.6)
 * - NO está enchufado al ruteo del dashboard aún
 *
 * Para ver este componente, importarlo manualmente en alguna página de prueba
 * o reemplazar temporalmente el body de ChatPage. NO está conectado por default.
 */

// ---------------------------------------------------------------------------
// Tipos
// ---------------------------------------------------------------------------

type MessageRole = "user" | "assistant";
type ToolCallStatus = "running" | "done" | "error";

interface ToolCall {
  id: string;
  name: string;
  args: string;
  status: ToolCallStatus;
}

interface Message {
  id: string;
  role: MessageRole;
  content: string;
  toolCalls?: ToolCall[];
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Datos hardcoded de ejemplo (se reemplazarán con datos reales en Fase 2.6)
// ---------------------------------------------------------------------------

const SAMPLE_MESSAGES: Message[] = [
  {
    id: "m1",
    role: "user",
    content:
      "Necesito un cron que me mande un resumen de ventas todos los lunes a las 9am por Telegram",
    timestamp: "12:41 PM",
  },
  {
    id: "m2",
    role: "assistant",
    content:
      "Perfecto. Para crear ese cron necesito revisar tu configuración de Telegram y el catálogo de skills de ventas que tienes disponibles.",
    toolCalls: [
      {
        id: "t1",
        name: "read_file",
        args: "~/.clawksis/.env",
        status: "done",
      },
      {
        id: "t2",
        name: "list_skills",
        args: "category=business_ops",
        status: "done",
      },
      {
        id: "t3",
        name: "cron_create",
        args: 'schedule="0 9 * * 1" channel=telegram',
        status: "done",
      },
    ],
    timestamp: "12:42 PM",
  },
  {
    id: "m3",
    role: "assistant",
    content: `Listo. Creé el cron job con estas características:

- **ID:** \`weekly-sales-mon\`
- **Schedule:** \`0 9 * * 1\` (lunes 9:00 AM)
- **Canal:** Telegram → tu chat directo
- **Skill:** \`business_ops/weekly-sales-report\`

El próximo lunes a las 9:00 AM recibirás el primer reporte. Puedes probar el envío ahora con \`clawk cron run weekly-sales-mon\`.`,
    timestamp: "12:43 PM",
  },
  {
    id: "m4",
    role: "user",
    content:
      "Perfecto, ahora prueba que funciona enviando un mensaje de test ahora mismo",
    timestamp: "12:44 PM",
  },
  {
    id: "m5",
    role: "assistant",
    content: "Voy a ejecutar un test enviando un mensaje de prueba",
    toolCalls: [
      {
        id: "t4",
        name: "cron_run",
        args: "weekly-sales-mon --test",
        status: "running",
      },
    ],
    timestamp: "12:44 PM",
  },
];

// ---------------------------------------------------------------------------
// Sub-componentes
// ---------------------------------------------------------------------------

function ChatHeader() {
  return (
    <div className="flex items-center justify-between border-b border-border px-4 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <span className="size-2 rounded-full bg-success shrink-0" />
        <span className="text-sm font-semibold text-foreground truncate">
          deepseek-v4-flash
        </span>
        <span className="text-xs text-muted-foreground">·</span>
        <span className="text-xs text-muted-foreground">Gradient AI</span>
      </div>

      <div className="hidden md:flex items-center gap-3 text-xs text-muted-foreground">
        <span>Session</span>
        <span className="font-mono text-foreground/80">07770308</span>
        <span>·</span>
        <span>0/65.5k tokens</span>
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden lg:inline text-xs text-muted-foreground">
          26 tools · 67 skills
        </span>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded border border-border bg-transparent px-2.5 py-1 text-xs text-foreground hover:bg-muted/30 transition-colors"
        >
          <Plus className="size-3" />
          New
        </button>
      </div>
    </div>
  );
}

function Avatar({ role }: { role: MessageRole }) {
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

  return (
    <button
      type="button"
      onClick={() => setExpanded(!expanded)}
      className={`group flex w-full items-center gap-2 rounded border px-3 py-1.5 text-left transition-colors ${
        isRunning
          ? "border-[#6C4FD6]/60 bg-[#6C4FD6]/5"
          : "border-border bg-muted/20 hover:bg-muted/30"
      }`}
    >
      <ChevronRight
        className={`size-3 text-muted-foreground transition-transform ${
          expanded ? "rotate-90" : ""
        }`}
      />
      <span className="font-mono text-xs text-warning">{toolCall.name}</span>
      <span className="truncate text-xs text-muted-foreground">
        {toolCall.args}
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
            <span className="text-success">done</span>
          </>
        )}
      </span>
    </button>
  );
}

function MessageActions({ timestamp }: { timestamp: string }) {
  return (
    <div className="flex items-center gap-3 opacity-0 transition-opacity group-hover:opacity-100">
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Copy className="size-3" />
        Copy
      </button>
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <RotateCw className="size-3" />
        Regenerate
      </button>
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <Pencil className="size-3" />
        Edit
      </button>
      <span className="text-xs text-muted-foreground/60">·</span>
      <span className="text-xs text-muted-foreground/60">{timestamp}</span>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
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

        {/* Burbuja sutil solo para usuario, sin burbuja para asistente */}
        {isUser ? (
          <div className="rounded-md bg-muted/40 px-4 py-2.5 text-sm text-foreground">
            {message.content}
          </div>
        ) : (
          <div className="text-sm text-foreground">
            <Markdown content={message.content} />
          </div>
        )}

        {/* Tool calls plegadas */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-1 flex flex-col gap-1.5">
            {message.toolCalls.map((tc) => (
              <ToolCallRow key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}

        {/* Acciones (visibles solo en hover) */}
        {!isUser && <MessageActions timestamp={message.timestamp} />}
      </div>
    </div>
  );
}

function Composer() {
  const [value, setValue] = useState("");
  const canSend = value.trim().length > 0;

  return (
    <div className="border-t border-border px-4 py-3">
      <div className="flex items-end gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 focus-within:border-[#6C4FD6]/60 transition-colors">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Mensaje a Clawksis... (Shift+Enter para nueva línea)"
          rows={1}
          className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none"
        />
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Adjuntar archivo"
            className="rounded p-1.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors"
          >
            <Paperclip className="size-4" />
          </button>
          <button
            type="button"
            aria-label="Grabar voz"
            className="rounded p-1.5 text-muted-foreground hover:bg-muted/40 hover:text-foreground transition-colors"
          >
            <Mic className="size-4" />
          </button>
          <button
            type="button"
            disabled={!canSend}
            aria-label="Enviar mensaje"
            className={`ml-1 flex size-7 items-center justify-center rounded transition-colors ${
              canSend
                ? "bg-[#6C4FD6] text-white hover:bg-[#5a40c2]"
                : "bg-muted/40 text-muted-foreground cursor-not-allowed"
            }`}
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Componente principal
// ---------------------------------------------------------------------------

export default function ChatModern() {
  return (
    <div className="flex h-full min-h-0 flex-col rounded-lg border border-border bg-background">
      <ChatHeader />

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-none flex-col">
          {SAMPLE_MESSAGES.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
        </div>
      </div>

      <Composer />
    </div>
  );
}
