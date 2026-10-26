/**
 * Stored transcript rows → chat bubbles. Two producers feed this: the gateway's
 * `session.history` / `session.resume` projection (`text`, `row_id`,
 * `display_kind`, tool `args`) and the REST `/api/sessions/{id}/messages` page
 * (raw `content`, which is an OpenAI parts array for an image turn, numeric `id`,
 * assistant `tool_calls`). Both arrive here so a bubble's `content` is always a
 * string — MessageBubble and the composer call string methods on it.
 */

import type { ChatImagePreview, ChatMessage, ToolCall } from "./useChatGateway";

type Row = Record<string, unknown>;

// Nota interna que el resume-pending del gateway antepone al prompt del
// usuario re-despachado ("[A previous request was interrupted... Please finish
// processing...]"). Es para el MODELO, no para la vista.
const RESUME_NOTE_RE =
  /^\s*\[(?:session resumed|a previous request|please finish)[^\]]*\]\s*/i;

// Bloques internos que el gateway agrega para que el modelo pueda resolver
// imágenes vía vision_analyze: útiles para el modelo, no para la vista.
const IMAGE_INTERNAL_NOTE_RE =
  /^\s*\[The user attached an image(?: but analysis failed\.|:\n[\s\S]*?)\]\s*/i;
const IMAGE_INTERNAL_HINT_RE =
  /^\s*\[You can examine it with vision_analyze using image_url:[^\]]+\]\s*/i;
const IMAGE_URL_PATH_RE = /image_url:\s*([^\]\n\r]+)/i;
// Native vision: the gateway projects each attached image as an `@image:<path>`
// line (tui_gateway/session_history.py `_user_image_display_text`); the stored
// text carries `[Image attached at: <path>]` hints instead.
const IMAGE_REF_LINE_RE = /^@image:(`[^`\n]+`|"[^"\n]+"|'[^'\n]+'|\S+)\s*$/;
const IMAGE_HINT_LINE_RE = /^\[Image attached at: ([^\n\]]+)\]\s*$/;
// Model-facing user rows a renderer must not show as something the user typed:
// the crash-recovery note (`auto_continue`) and the untyped `[System: …]` scaffolds.
const SYSTEM_NOTE_RE = /^\s*\[System(?: note)?:/;
// Typed user rows that ARE the user's words (`/skill args`, a mid-turn steer).
const USER_DISPLAY_KINDS = new Set(["skill_invocation", "steer"]);

export function localImagePreviewUrl(path: string): string {
  return "/media/local?path=" + encodeURIComponent(path);
}

function imageNameFromPath(path: string): string {
  const clean = path.split(/[?#]/)[0] || "";
  return clean.split("/").filter(Boolean).pop() || "imagen adjunta";
}

function pathPreview(path: string): ChatImagePreview {
  return { previewUrl: localImagePreviewUrl(path), name: imageNameFromPath(path) };
}

function unquote(ref: string): string {
  return /^[`"']/.test(ref) ? ref.slice(1, -1) : ref;
}

function partText(part: Row): string {
  if (typeof part.text === "string") return part.text;
  return typeof part.content === "string" ? part.content : "";
}

function partImageUrl(part: Row): string {
  const raw = part.image_url ?? part.url;
  if (typeof raw === "string") return raw;
  const nested = raw && typeof raw === "object" ? (raw as Row).url : undefined;
  return typeof nested === "string" ? nested : "";
}

/** The visible text and inline images of a stored `content`: a string, an
 *  OpenAI parts array (`text` / `image_url`), or a single part object. */
export function contentToText(content: unknown): { text: string; images: ChatImagePreview[] } {
  if (typeof content === "string") return { text: content, images: [] };
  const parts = Array.isArray(content) ? content : content && typeof content === "object" ? [content] : [];
  const texts: string[] = [];
  const images: ChatImagePreview[] = [];
  for (const raw of parts) {
    if (typeof raw === "string") {
      texts.push(raw);
      continue;
    }
    if (!raw || typeof raw !== "object") continue;
    const part = raw as Row;
    const url = String(part.type ?? "").includes("image") ? partImageUrl(part) : "";
    if (url) images.push({ previewUrl: url, name: "imagen adjunta" });
    else texts.push(partText(part));
  }
  return { text: texts.filter(Boolean).join("\n"), images };
}

/** Pull `@image:<path>` refs and `[Image attached at: <path>]` hints out of a
 *  user turn's text; each becomes a preview served by `/media/local`. */
export function extractImageRefs(text: string): { text: string; paths: string[] } {
  const paths: string[] = [];
  const kept = text.split("\n").filter((line) => {
    const ref = line.match(IMAGE_REF_LINE_RE) ?? line.match(IMAGE_HINT_LINE_RE);
    if (!ref) return true;
    paths.push(unquote(ref[1].trim()));
    return false;
  });
  return { text: kept.join("\n").trimEnd(), paths };
}

function sanitizeUserContent(content: string, inline: ChatImagePreview[]): {
  content: string;
  images?: ChatImagePreview[];
} {
  let next = content.replace(RESUME_NOTE_RE, "");
  const hintPath = next.match(IMAGE_URL_PATH_RE)?.[1]?.trim();
  const hadImageNote = IMAGE_INTERNAL_NOTE_RE.test(next);
  next = next.replace(IMAGE_INTERNAL_NOTE_RE, "").replace(IMAGE_INTERNAL_HINT_RE, "").trimStart();
  const refs = extractImageRefs(next);
  next = refs.text;
  // An inline data/http image already shows the attachment; a path is the fallback.
  const paths = inline.length ? [] : [...refs.paths, ...(hintPath ? [hintPath] : [])];
  const images = [...inline, ...paths.map(pathPreview)];
  if (!next.trim() && (hadImageNote || images.length)) next = "Imagen adjunta";
  return { content: next, images: images.length ? images : undefined };
}

function rowText(m: Row): { text: string; images: ChatImagePreview[] } {
  return typeof m.text === "string" ? { text: m.text, images: [] } : contentToText(m.content);
}

function rowIdOf(m: Row): number | undefined {
  const raw = m.row_id ?? m.id;
  return typeof raw === "number" && Number.isFinite(raw) ? raw : undefined;
}

/** Stored timestamps are Unix seconds; bubbles keep milliseconds. */
function timestampOf(m: Row, fallback: number): number {
  const ts = m.timestamp;
  if (typeof ts !== "number" || !Number.isFinite(ts) || ts <= 0) return fallback;
  return ts < 1e12 ? ts * 1000 : ts;
}

function isHiddenUserRow(m: Row, text: string): boolean {
  const kind = typeof m.display_kind === "string" ? m.display_kind : "";
  if (kind && !USER_DISPLAY_KINDS.has(kind)) return true;
  return !kind && SYSTEM_NOTE_RE.test(text);
}

function parseArgs(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) return raw as Record<string, unknown>;
  if (typeof raw !== "string") return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

/** REST rows name a tool row's call only through the assistant's `tool_calls`. */
function rememberToolCalls(m: Row, calls: Map<string, { name: string; args: Record<string, unknown> }>): void {
  if (!Array.isArray(m.tool_calls)) return;
  for (const raw of m.tool_calls) {
    const call = (raw && typeof raw === "object" ? raw : {}) as Row;
    const fn = (call.function && typeof call.function === "object" ? call.function : {}) as Row;
    if (typeof call.id === "string" && typeof fn.name === "string") {
      calls.set(call.id, { name: fn.name, args: parseArgs(fn.arguments) });
    }
  }
}

function toolCallFromRow(
  m: Row,
  id: string,
  calls: Map<string, { name: string; args: Record<string, unknown> }>,
): ToolCall {
  const known = typeof m.tool_call_id === "string" ? calls.get(m.tool_call_id) : undefined;
  const name = m.name ?? m.tool_name ?? known?.name ?? "tool";
  const args = parseArgs(m.args);
  return {
    id,
    name: String(name),
    args: Object.keys(args).length ? args : known?.args ?? {},
    status: "done",
    summary: typeof m.context === "string" ? m.context : undefined,
  };
}

function reasoningOf(m: Row): string | undefined {
  const raw =
    (typeof m.reasoning === "string" && m.reasoning) ||
    (typeof m.reasoning_content === "string" && m.reasoning_content) ||
    "";
  return raw.trim() ? raw : undefined;
}

/** Rebuild COMPLETE bubbles from stored rows: tool rows attach as `toolCalls` to
 *  their turn's assistant (the "ver pasos" steps), persisted reasoning rides in
 *  `reasoning`, so steps and thinking survive a reload. */
export function mapHistoryMessages(raw: Array<Record<string, unknown>>, idPrefix: string): ChatMessage[] {
  const out: ChatMessage[] = [];
  const calls = new Map<string, { name: string; args: Record<string, unknown> }>();
  let pendingTools: ToolCall[] = [];
  const base = Date.now() - 1000 * (raw.length + 1);
  raw.forEach((m, i) => {
    if (m.role === "tool") {
      pendingTools.push(toolCallFromRow(m, idPrefix + "-tc-" + i, calls));
      return;
    }
    if (m.role !== "user" && m.role !== "assistant") return;
    if (m.role === "assistant") rememberToolCalls(m, calls);
    const { text, images } = rowText(m);
    if (m.role === "user" && isHiddenUserRow(m, text)) return;
    const user = m.role === "user" ? sanitizeUserContent(text, images) : null;
    const content = user ? user.content : text;
    const reasoning = reasoningOf(m);
    if (!content.trim() && (user || (!reasoning && !pendingTools.length))) return;
    out.push({
      id: idPrefix + "-" + i,
      role: m.role,
      content,
      reasoning,
      toolCalls: m.role === "assistant" ? pendingTools : [],
      streaming: false,
      timestamp: timestampOf(m, base + i * 1000),
      images: user?.images,
      rowId: rowIdOf(m),
    });
    if (m.role === "assistant") pendingTools = [];
  });
  return out;
}
