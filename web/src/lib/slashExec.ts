/**
 * Slash command execution pipeline for the web chat.
 *
 * Mirrors the Ink TUI's createSlashHandler.ts:
 *
 *   1. Parse the command into `name` + `arg`.
 *   2. Try `slash.exec` — covers every registry-backed command the terminal
 *      UI knows about (/help, /resume, /compact, /model, …). It answers plain
 *      worker output (`{output}`) or, for the commands it reroutes to
 *      `command.dispatch` (/retry /undo /goal /plan /steer /queue …, and the
 *      worker's /prompt seeds), that method's typed directive.
 *   3. If `slash.exec` errors (command rejected, unknown, or needs client
 *      behaviour), fall back to `command.dispatch` which returns a typed
 *      directive: `exec` | `plugin` | `alias` | `skill` | `send` | `prefill`.
 *   4. Each directive is dispatched to the appropriate callback, whichever
 *      method produced it.
 *
 * Keeping the pipeline here (instead of inline in ChatPage) lets future
 * clients (SwiftUI, Android) implement the same logic by reading the same
 * contract.
 */

/**
 * Minimal gateway surface `executeSlash` needs. Satisfied both by the
 * `GatewayClient` class and by a thin adapter over `useChatGateway`'s
 * `sendRpc`, so every client (web Modern chat, Ink TUI, future native apps)
 * shares this exact dispatch pipeline.
 */
export interface SlashGateway {
  request<T = unknown>(
    method: string,
    params?: Record<string, unknown>,
  ): Promise<T>;
}

export interface SlashExecResponse {
  output?: string;
  warning?: string;
}

export type CommandDispatchResponse =
  | { type: "exec" | "plugin"; output?: string }
  | { type: "alias"; target: string }
  | { type: "skill"; name: string; message?: string }
  | { type: "send" | "prefill"; message: string; notice?: string };

export interface SlashSendOptions {
  /** The view was reloaded from the server, so the typed command bubble is
   *  gone: show the submitted text as the user's turn. */
  asUserTurn?: boolean;
}

export interface SlashExecCallbacks {
  /** Render a transcript system message. */
  sys(text: string): void;
  /** Submit a user message to the agent (prompt.submit). */
  send(message: string, options?: SlashSendOptions): Promise<void> | void;
  /** Put text in the composer for the user to edit and resend (`/undo`). */
  prefill?(text: string): void;
  /** Reload the transcript from the server: the command rewound it. */
  refresh?(): Promise<void> | void;
}

export interface SlashExecOptions {
  /** Raw command including the leading slash (e.g. "/model opus-4.6"). */
  command: string;
  /** Session id. If empty the call is still issued — some commands are session-less. */
  sessionId: string;
  gw: SlashGateway;
  callbacks: SlashExecCallbacks;
}

export type SlashExecResult = "done" | "sent" | "error";

/** Commands that rewind the stored transcript server-side before answering
 *  (tui_gateway/methods_tools.py `_cmd_retry` / `_cmd_undo`). */
const REWINDING_COMMANDS = new Set(["retry", "undo"]);

type SlashExecReply = (SlashExecResponse & Record<string, unknown>) | null;

/**
 * Run a slash command. Returns the terminal state so callers can decide
 * whether to clear the composer, queue retries, etc.
 */
export async function executeSlash(options: SlashExecOptions): Promise<SlashExecResult> {
  const { command, sessionId, gw, callbacks } = options;
  const { name, arg } = parseSlash(command);

  if (!name) {
    callbacks.sys("empty slash command");
    return "error";
  }

  // Primary dispatcher.
  let reply: SlashExecReply | undefined;
  try {
    reply = await gw.request<SlashExecReply>("slash.exec", {
      command: command.replace(/^\/+/, ""),
      session_id: sessionId,
    });
  } catch {
    reply = undefined; // fall through to command.dispatch
  }

  if (reply !== undefined) {
    const directive = parseCommandDispatch(reply);
    if (directive) return runDirective(directive, name, arg, options);
    const body = reply?.output || `/${name}: no output`;
    callbacks.sys(reply?.warning ? `warning: ${reply.warning}\n${body}` : body);
    return "done";
  }

  try {
    const d = parseCommandDispatch(
      await gw.request<unknown>("command.dispatch", {
        name,
        arg,
        session_id: sessionId,
      }),
    );
    if (!d) {
      callbacks.sys("error: invalid response: command.dispatch");
      return "error";
    }
    return await runDirective(d, name, arg, options);
  } catch (err) {
    callbacks.sys(`error: ${err instanceof Error ? err.message : String(err)}`);
    return "error";
  }
}

async function runDirective(
  d: CommandDispatchResponse,
  name: string,
  arg: string,
  options: SlashExecOptions,
): Promise<SlashExecResult> {
  const { sys, send, prefill, refresh } = options.callbacks;
  const rewound = REWINDING_COMMANDS.has(name.toLowerCase());
  if (d.type === "send" || d.type === "prefill") {
    // The server already cut the turn: show what it now holds before acting.
    if (rewound) await refresh?.();
    if (d.notice?.trim()) sys(d.notice);
  }

  switch (d.type) {
    case "exec":
    case "plugin":
      sys(d.output ?? "(no output)");
      return "done";

    case "alias":
      return executeSlash({ ...options, command: `/${d.target}${arg ? ` ${arg}` : ""}` });

    case "prefill":
      if (d.message) prefill?.(d.message);
      return "done";

    case "skill":
    case "send": {
      const msg = d.message?.trim() ?? "";
      if (!msg) {
        sys(`/${name}: ${d.type === "skill" ? "skill payload missing message" : "empty message"}`);
        return "error";
      }
      if (d.type === "skill") sys(`⚡ loading skill: ${d.name}`);
      await send(msg, { asUserTurn: rewound });
      return "sent";
    }
  }
}

export function parseSlash(command: string): { name: string; arg: string } {
  const m = command.replace(/^\/+/, "").match(/^(\S+)\s*(.*)$/);
  return m ? { name: m[1], arg: m[2].trim() } : { name: "", arg: "" };
}

function parseCommandDispatch(raw: unknown): CommandDispatchResponse | null {
  if (!raw || typeof raw !== "object") return null;

  const r = raw as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === "string" ? v : undefined);

  switch (r.type) {
    case "exec":
    case "plugin":
      return { type: r.type, output: str(r.output) };

    case "alias":
      return typeof r.target === "string"
        ? { type: "alias", target: r.target }
        : null;

    case "skill":
      return typeof r.name === "string"
        ? { type: "skill", name: r.name, message: str(r.message) }
        : null;

    case "send":
    case "prefill":
      return typeof r.message === "string"
        ? { type: r.type, message: r.message, notice: str(r.notice) }
        : null;

    default:
      return null;
  }
}
