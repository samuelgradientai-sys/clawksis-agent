/** Pure helpers for the live browser view: picking the session, mapping pointer/keys to the
 * stream's input events (same shapes agent-browser's own dashboard sends), labelling actions. */

import type { LiveBrowserSession, LiveFrameMetadata } from "@/lib/api-browser-live";

const ownsKey = (id: string, key: string) =>
  id === key || id.startsWith(`${key}@`) || id.startsWith(`${key}::`);

/** Delegated subagents browse under their own task id (`sa-<index>-<id>`). */
const isSubagentKey = (id: string) => /^sa-\d+-/.test(id);

/** "Agente" for the conversation's own browser, "Subagente n" for delegated helpers, the server's
 *  own label when it sends one ("Mi Chrome"), "Navegador n" for anything else. */
export function sessionLabels(sessions: LiveBrowserSession[], preferred: string | null): Map<string, string> {
  const labels = new Map<string, string>();
  const counts = { Subagente: 0, Navegador: 0 };
  for (const { task_id: id, label } of sessions) {
    if (label) {
      labels.set(id, label);
      continue;
    }
    if (preferred && ownsKey(id, preferred)) {
      labels.set(id, "Agente");
      continue;
    }
    const kind = isSubagentKey(id) ? "Subagente" : "Navegador";
    labels.set(id, `${kind} ${++counts[kind]}`);
  }
  return labels;
}

/** The conversation's own browser (its key, or a variant of it: `<key>@<profile>`, `<key>::local`),
 *  else the user's own Chrome (a conversation running on it is folded into that entry), else the
 *  most recently opened one. */
export function pickSession(sessions: LiveBrowserSession[], preferred: string | null): string | null {
  const ids = sessions.map((s) => s.task_id);
  const own = preferred ? ids.filter((id) => ownsKey(id, preferred)) : [];
  const mine = sessions.filter((s) => s.kind === "my_chrome").map((s) => s.task_id);
  return own.at(-1) ?? mine.at(-1) ?? ids.at(-1) ?? null;
}

/** Whether the shown browser is the user's own Chrome (Mi Chrome) rather than the server's. */
export function isUsersChrome(sessions: LiveBrowserSession[], taskId: string | null): boolean {
  return sessions.some((s) => s.task_id === taskId && s.kind === "my_chrome");
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Client coordinates over an `object-contain` image → page viewport pixels, or null in the letterbox. */
export function toViewport(
  clientX: number,
  clientY: number,
  box: Box,
  meta: LiveFrameMetadata,
): { x: number; y: number } | null {
  const scale = Math.min(box.width / meta.deviceWidth, box.height / meta.deviceHeight);
  if (!(scale > 0)) return null;
  const offsetX = (box.width - meta.deviceWidth * scale) / 2;
  const offsetY = (box.height - meta.deviceHeight * scale) / 2;
  const x = (clientX - box.left - offsetX) / scale;
  const y = (clientY - box.top - offsetY) / scale;
  if (x < 0 || y < 0 || x > meta.deviceWidth || y > meta.deviceHeight) return null;
  return { x: Math.round(x), y: Math.round(y) };
}

interface Modifiable {
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
}

export function modifiers(e: Modifiable): number {
  return (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.metaKey ? 4 : 0) | (e.shiftKey ? 8 : 0);
}

const BUTTONS = ["left", "middle", "right"] as const;

export function mouseEvent(
  eventType: "mousePressed" | "mouseReleased" | "mouseMoved",
  point: { x: number; y: number },
  e: Modifiable & { button: number },
) {
  return {
    type: "input_mouse",
    eventType,
    x: point.x,
    y: point.y,
    button: BUTTONS[e.button] ?? "none",
    clickCount: eventType === "mousePressed" ? 1 : 0,
    modifiers: modifiers(e),
  };
}

export function wheelEvent(point: { x: number; y: number }, deltaX: number, deltaY: number) {
  return { type: "input_mouse", eventType: "mouseWheel", x: point.x, y: point.y, deltaX, deltaY };
}

export function keyboardEvent(eventType: "keyDown" | "keyUp", e: Modifiable & { key: string; code: string }) {
  const printable = e.key.length === 1;
  return {
    type: "input_keyboard",
    eventType,
    key: e.key,
    code: e.code,
    text: eventType === "keyDown" && printable ? e.key : undefined,
    windowsVirtualKeyCode: printable ? e.key.toUpperCase().charCodeAt(0) : 0,
    modifiers: modifiers(e),
  };
}

const ACTION_LABELS: Record<string, string> = {
  browser_navigate: "Abre una página",
  browser_click: "Hace clic",
  browser_type: "Escribe",
  browser_press: "Pulsa una tecla",
  browser_scroll: "Se desplaza",
  browser_back: "Vuelve atrás",
  browser_snapshot: "Lee la página",
  browser_vision: "Mira la página",
  browser_get_images: "Revisa las imágenes",
  browser_console: "Revisa la consola",
  browser_dialog: "Responde un diálogo",
  browser_cdp: "Usa el navegador a bajo nivel",
  browser_exec: "Ejecuta un paso en el navegador",
  browser_vault_fill: "Completa un inicio de sesión",
};

/** A Spanish label for a browser tool call; unknown tools show their name without the prefix. */
export function actionLabel(tool: string): string {
  return ACTION_LABELS[tool] ?? tool.replace(/^browser_/, "");
}
