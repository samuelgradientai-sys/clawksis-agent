/**
 * Slash commands the web chat answers itself instead of sending to the
 * gateway's headless slash worker (which has no TTY and no notion of this
 * page's conversation list), like Ink's local handlers
 * (ui-tui/src/app/slash/commands/core.ts):
 *
 *   /new, /reset, /clear → start a new conversation here; on the worker they
 *     reset its own state or answer "terminal-only", leaving this chat as is.
 *   /model (no args)     → the React model picker (the worker's picker hangs).
 *   /stop, /interrupt    → while a turn runs: the same interrupt as the stop
 *     button (the worker's /stop does not cut a turn in flight).
 */

export type LocalSlashAction = "new-chat" | "model-picker" | "interrupt";

const NEW_CHAT_COMMANDS = new Set(["new", "reset", "clear"]);
const INTERRUPT_COMMANDS = new Set(["stop", "interrupt"]);

export function localSlashAction(text: string, busy: boolean): LocalSlashAction | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("/")) return null;
  const [rawName = "", ...rest] = trimmed.slice(1).split(/\s+/);
  const name = rawName.toLowerCase();
  if (NEW_CHAT_COMMANDS.has(name)) return "new-chat";
  if (name === "model" && !rest.join("").trim()) return "model-picker";
  if (busy && INTERRUPT_COMMANDS.has(name)) return "interrupt";
  return null;
}
