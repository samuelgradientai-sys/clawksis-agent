/**
 * Gateway-event → pixel-agents message translator.
 *
 * The vendored pixel-agents office (web/public/pixel-office, an iframe)
 * consumes the exact postMessage protocol its VS Code extension speaks:
 * agentCreated / agentToolStart / agentToolDone / agentToolsClear /
 * agentStatus / subagentToolStart / subagentClear / agentClosed.
 * (Contract: pixel-agents webview-ui/src/hooks/useExtensionMessages.ts.)
 *
 * This bridge maps the Clawksis TUI-gateway event stream onto that protocol:
 *
 *   tool.start        → agentToolStart   (raw toolName + Telegram-style
 *                       "emoji + context" label, e.g. "📖 config.py")
 *   tool.complete     → agentToolDone
 *   subagent.start    → agentToolStart   (toolName "Task", "Subtask: goal")
 *                       — pixel-agents auto-spawns a sub-character for it
 *   subagent.tool     → subagentToolStart (under the parent's task tool)
 *   subagent.complete → agentToolDone + subagentClear
 *   message.start     → agentStatus active + a synthetic "💭 Pensando…"
 *                       activity (the Telegram "typing…" analog) shown until
 *                       the first real tool runs or the turn ends
 *   message.complete  → agentToolsClear + agentStatus waiting (turn end,
 *                       only when no tools remain in flight) + agentTokenUsage
 *                       (fuel gauge) when the turn reports usage
 *   clarify/approval  → agentToolPermission (the amber "…" bubble + chime —
 *                       the agent is blocked waiting on the user)
 *
 * Activity labels carry a per-tool emoji (Telegram chat-action style) and a
 * human, Spanish context line. The raw tool name still rides on `toolName` so
 * the office picks the right read/type animation; the emoji never leaks into
 * the animation key.
 *
 * pixel-agents agent ids are NUMBERS; gateway sessions are string ids, so
 * the bridge keeps a stable sid→int mapping. A roster API lets the page add
 * idle characters for sessions that exist but don't publish events yet
 * (Telegram/WhatsApp/cron) so the office honestly shows them as present.
 *
 * The event feed is best-effort (frames can drop), so a per-agent idle
 * timer clears stuck tool animations after a quiet period — the same
 * defensive pattern pixel-agents itself uses.
 */

import type { GatewayEvent } from "./gatewayFeed";

export type PixelPost = (msg: Record<string, unknown>) => void;

const MAIN_SESSION_KEY = "__main__";
const MAX_AGENTS = 12;
const IDLE_CLEAR_MS = 8000;

/** Synthetic tool id for the "thinking" activity synthesized on message.start. */
const THINKING_TOOL_ID = "__thinking__";
/** Max characters of context kept in an activity label (the office truncates further). */
const LABEL_CONTEXT_MAX = 48;

interface AgentEntry {
  id: number;
  label: string;
  activeTools: Set<string>;
  /** toolIds of synthetic Task tools (one per live delegated subagent). */
  activeTasks: Set<string>;
  /** Per-subagent rolling tool id (to mark the previous one done). */
  lastSubagentTool: Map<string, string>;
  idleTimer: ReturnType<typeof setTimeout> | null;
  fromRoster: boolean;
  /** True while a synthetic "💭 Pensando…" activity is in flight (between
   *  message.start and the first real tool / turn end). */
  thinking: boolean;
}

function asString(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

// ── Tool → Telegram-style activity (emoji + Spanish verb) ──────────────────
// Clawksis tools are snake_case (read_file, web_search, terminal, …). Each maps
// to an emoji "chat action" and a fallback verb used when the gateway doesn't
// ship a human context preview. Prefix groups (browser_*, kanban_*, …) catch
// the long tails. The emoji shows in the office's always-on activity label.
interface ToolVisual {
  emoji: string;
  verb: string;
}

const TOOL_VISUALS: Record<string, ToolVisual> = {
  read_file: { emoji: "📖", verb: "Leyendo" },
  write_file: { emoji: "✍️", verb: "Escribiendo" },
  edit_file: { emoji: "✏️", verb: "Editando" },
  patch: { emoji: "✏️", verb: "Editando" },
  terminal: { emoji: "💻", verb: "Ejecutando" },
  bash: { emoji: "💻", verb: "Ejecutando" },
  process: { emoji: "💻", verb: "Ejecutando" },
  execute_code: { emoji: "💻", verb: "Ejecutando código" },
  web_search: { emoji: "🔎", verb: "Buscando en la web" },
  web_extract: { emoji: "🌐", verb: "Leyendo la web" },
  delegate_task: { emoji: "🤝", verb: "Delegando" },
  clarify: { emoji: "❓", verb: "Preguntando" },
  cronjob: { emoji: "⏰", verb: "Programando" },
  schedule: { emoji: "⏰", verb: "Programando" },
  memory: { emoji: "🧠", verb: "Recordando" },
  image_generate: { emoji: "🎨", verb: "Generando imagen" },
  agent_message: { emoji: "💬", verb: "Mensajeando" },
  send_message: { emoji: "💬", verb: "Enviando mensaje" },
  agent_inbox: { emoji: "📥", verb: "Revisando la bandeja" },
  save_credential: { emoji: "🔑", verb: "Guardando credencial" },
  computer_use: { emoji: "🖱️", verb: "Usando la PC" },
  claude_code: { emoji: "🤖", verb: "Programando (CLI)" },
  codex_exec: { emoji: "🤖", verb: "Programando (CLI)" },
  opencode_run: { emoji: "🤖", verb: "Programando (CLI)" },
  mirofish: { emoji: "🤖", verb: "Programando (CLI)" },
  mixture_of_agents: { emoji: "🧩", verb: "Consultando modelos" },
  discord: { emoji: "💬", verb: "Discord" },
  todo: { emoji: "✅", verb: "Planificando" },
  Task: { emoji: "🤝", verb: "Delegando" }, // upstream Claude-style name
};

const DEFAULT_VISUAL: ToolVisual = { emoji: "🛠️", verb: "Trabajando" };
const THINKING_VISUAL: ToolVisual = { emoji: "💭", verb: "Pensando…" };

function visualFor(toolName: string): ToolVisual {
  if (TOOL_VISUALS[toolName]) return TOOL_VISUALS[toolName];
  const key = toolName.toLowerCase();
  if (TOOL_VISUALS[key]) return TOOL_VISUALS[key];
  if (key.startsWith("browser_")) return { emoji: "🧭", verb: "Navegando" };
  if (key.startsWith("kanban_")) return { emoji: "📋", verb: "Kanban" };
  if (key.startsWith("feishu_")) return { emoji: "📄", verb: "Feishu" };
  if (key.startsWith("ha_")) return { emoji: "🏠", verb: "Casa inteligente" };
  if (key.startsWith("cron")) return { emoji: "⏰", verb: "Programando" };
  if (key.includes("search")) return { emoji: "🔎", verb: "Buscando" };
  if (key.includes("read") || key.includes("get") || key.includes("list")) {
    return { emoji: "📖", verb: "Consultando" };
  }
  if (key.includes("write") || key.includes("create") || key.includes("send")) {
    return { emoji: "✍️", verb: "Escribiendo" };
  }
  return DEFAULT_VISUAL;
}

/** "📖 config.py" — emoji + the gateway's human context (or the fallback verb). */
function activityLabel(toolName: string, context: string): string {
  const v = visualFor(toolName);
  let ctx = context.trim();
  if (ctx.length > LABEL_CONTEXT_MAX) ctx = `${ctx.slice(0, LABEL_CONTEXT_MAX - 1)}…`;
  return `${v.emoji} ${ctx || v.verb}`;
}


export class PixelBridge {
  private post: PixelPost;
  private agents = new Map<string, AgentEntry>();
  private nextId = 1;
  private subagentToolSeq = 1;
  private warnedFull = false;
  // session key -> {title, source, model}, accumulated from event payloads.
  private meta = new Map<string, { title?: string; source?: string; model?: string }>();

  constructor(post: PixelPost) {
    this.post = post;
  }

  /** Number of characters currently in the office. */
  get agentCount(): number {
    return this.agents.size;
  }

  /** Reverse lookup: office character id → the session key it represents.
   *  Lets the host translate an in-office click (which carries the numeric
   *  character id) back to a session so the Agent Inspector can select it. */
  sessionKeyForId(id: number): string | null {
    for (const [key, entry] of this.agents) {
      if (entry.id === id) return key;
    }
    return null;
  }

  dispose(): void {
    for (const entry of this.agents.values()) {
      if (entry.idleTimer) clearTimeout(entry.idleTimer);
    }
    this.agents.clear();
  }

  // ── Roster (sessions that exist but may not stream events) ──────────────

  syncRoster(sessions: Array<{ key: string; label: string }>): void {
    const seen = new Set(sessions.map((s) => s.key));

    // Remove roster-created characters whose session vanished. Event-created
    // agents (the live chat) are kept — their lifecycle is the event stream.
    for (const [key, entry] of this.agents) {
      if (entry.fromRoster && !seen.has(key)) {
        this.removeAgent(key);
      }
    }

    for (const s of sessions) {
      if (!this.agents.has(s.key)) {
        this.ensureAgent(s.key, s.label, true);
      }
    }
  }

  // ── Event translation ────────────────────────────────────────────────────

  handleEvent(ev: GatewayEvent): void {
    const p = ev.payload;
    const sid = ev.sessionId ?? MAIN_SESSION_KEY;

    // Session metadata (real title + model + channel) may ride on any event —
    // store it and refresh the desk label so it shows the session name + model
    // instead of the raw id.
    const mTitle = asString(p.session_title);
    const mSource = asString(p.session_source);
    const mModel = asString(p.session_model);
    if (mTitle || mSource || mModel) {
      this.applyMeta(sid, { title: mTitle, source: mSource, model: mModel });
    }

    switch (ev.type) {
      case "tool.start": {
        const entry = this.ensureAgent(sid, this.defaultLabel(sid));
        if (!entry) return;
        // A real tool means reasoning is over — retire the "thinking" activity.
        this.endThinking(entry);
        const toolId = asString(p.tool_id) || `tool-${ev.id}`;
        const name = asString(p.name) || "Tool";
        const context = asString(p.context);
        const label = activityLabel(name, context);
        entry.activeTools.add(toolId);
        this.post({
          type: "agentToolStart",
          id: entry.id,
          toolId,
          toolName: name, // raw name → office picks read/type animation
          status: label,
          label,
        });
        this.bumpIdle(sid);
        break;
      }

      case "tool.complete": {
        const entry = this.agents.get(sid);
        if (!entry) return;
        const toolId = asString(p.tool_id);
        if (toolId) {
          entry.activeTools.delete(toolId);
          this.post({ type: "agentToolDone", id: entry.id, toolId });
        }
        this.bumpIdle(sid);
        break;
      }

      case "subagent.start":
      case "subagent.spawn_requested": {
        const entry = this.ensureAgent(sid, this.defaultLabel(sid));
        if (!entry) return;
        this.endThinking(entry);
        const subId = asString(p.subagent_id) || `sub-${ev.id}`;
        const taskToolId = `task-${subId}`;
        if (entry.activeTasks.has(taskToolId)) return; // spawn_requested then start
        entry.activeTasks.add(taskToolId);
        const goal = asString(p.goal) || "delegated task";
        // toolName "Task" + non-"hook-" toolId makes pixel-agents spawn a
        // sub-character; the "Subtask:" prefix (status) becomes its label, while
        // `label` is the parent's own activity line (🤝 + goal).
        this.post({
          type: "agentToolStart",
          id: entry.id,
          toolId: taskToolId,
          toolName: "Task",
          status: `Subtask: ${goal}`,
          label: `🤝 ${goal}`,
        });
        this.bumpIdle(sid);
        break;
      }

      case "subagent.tool":
      case "subagent.thinking": {
        const entry = this.agents.get(sid);
        if (!entry) return;
        const subId = asString(p.subagent_id);
        if (!subId) return;
        const taskToolId = `task-${subId}`;
        if (!entry.activeTasks.has(taskToolId)) return;
        const subToolName =
          ev.type === "subagent.thinking" ? THINKING_TOOL_ID : asString(p.tool_name);
        const label =
          ev.type === "subagent.thinking"
            ? `${THINKING_VISUAL.emoji} ${THINKING_VISUAL.verb}`
            : activityLabel(subToolName, asString(p.text));
        // Mark the previous sub-tool done so the sub-character shows one
        // live activity at a time (we don't get per-sub-tool completes).
        const prev = entry.lastSubagentTool.get(taskToolId);
        if (prev) {
          this.post({
            type: "subagentToolDone",
            id: entry.id,
            parentToolId: taskToolId,
            toolId: prev,
          });
        }
        const toolId = `sat-${this.subagentToolSeq++}`;
        entry.lastSubagentTool.set(taskToolId, toolId);
        this.post({
          type: "subagentToolStart",
          id: entry.id,
          parentToolId: taskToolId,
          toolId,
          toolName: subToolName, // raw name → office picks read/type animation
          status: label,
          label,
        });
        this.bumpIdle(sid);
        break;
      }

      case "subagent.complete": {
        const entry = this.agents.get(sid);
        if (!entry) return;
        const subId = asString(p.subagent_id);
        if (!subId) return;
        const taskToolId = `task-${subId}`;
        entry.activeTasks.delete(taskToolId);
        entry.lastSubagentTool.delete(taskToolId);
        this.post({ type: "agentToolDone", id: entry.id, toolId: taskToolId });
        this.post({ type: "subagentClear", id: entry.id, parentToolId: taskToolId });
        this.bumpIdle(sid);
        break;
      }

      case "message.start": {
        const entry = this.ensureAgent(sid, this.defaultLabel(sid));
        if (!entry) return;
        // New turn: drop any stale "needs you" bubble, go active, and show the
        // Telegram-style "thinking" activity until the first tool runs.
        this.post({ type: "agentToolPermissionClear", id: entry.id });
        this.post({ type: "agentStatus", id: entry.id, status: "active" });
        this.beginThinking(entry);
        this.bumpIdle(sid);
        break;
      }

      case "message.complete": {
        const entry = this.agents.get(sid);
        if (!entry) return;
        this.emitUsage(entry, p.usage);
        if (entry.activeTools.size === 0 && entry.activeTasks.size === 0) {
          this.finishTurn(sid);
        } else {
          this.endThinking(entry);
          this.bumpIdle(sid);
        }
        break;
      }

      case "clarify.request":
      case "approval.request": {
        const entry = this.ensureAgent(sid, this.defaultLabel(sid));
        if (!entry) return;
        // Blocked on the user → the amber "…" permission bubble (+ chime),
        // which reads as "your turn" far better than the green done-check.
        this.endThinking(entry);
        this.post({ type: "agentToolPermission", id: entry.id });
        this.bumpIdle(sid);
        break;
      }

      default:
        // Unknown event types are fine — keep the idle timer warm so an
        // actively-streaming agent isn't cleared mid-turn.
        if (this.agents.has(sid)) this.bumpIdle(sid);
        break;
    }
  }

  // ── Internals ─────────────────────────────────────────────────────────────

  private defaultLabel(sid: string): string {
    if (sid === MAIN_SESSION_KEY) return "Chat";
    // Platform sessions look like "telegram:12345" / "cron:job" — make them
    // readable as "Telegram · 12345".
    const idx = sid.indexOf(":");
    if (idx > 0) {
      const platform = sid.slice(0, idx);
      const id = sid.slice(idx + 1);
      const cap = platform.charAt(0).toUpperCase() + platform.slice(1);
      return `${cap} · ${id.slice(0, 10)}`;
    }
    return `Session ${sid.slice(0, 8)}`;
  }

  private ensureAgent(key: string, label: string, fromRoster = false): AgentEntry | null {
    const existing = this.agents.get(key);
    if (existing) return existing;

    // At capacity: reclaim the oldest idle event-created desk so an active
    // session still gets one, instead of permanently leaking map entries
    // (event-created agents are never closed otherwise) and silently dropping
    // the newcomer. Map iteration is insertion order → oldest first.
    if (this.agents.size >= MAX_AGENTS && !this.evictOneIdle()) {
      if (!this.warnedFull) {
        this.warnedFull = true;
        console.warn(
          `PixelBridge: office full at ${String(MAX_AGENTS)} active agents — ` +
            `not showing session ${key}`,
        );
      }
      return null;
    }

    const entry: AgentEntry = {
      id: this.nextId++,
      label,
      activeTools: new Set(),
      activeTasks: new Set(),
      lastSubagentTool: new Map(),
      idleTimer: null,
      fromRoster,
      thinking: false,
    };
    this.agents.set(key, entry);
    this.post({
      type: "agentCreated",
      id: entry.id,
      folderName: this.folderNameFor(key, label),
      model: this.modelLineFor(key),
    });
    return entry;
  }

  /** Desk title — the real session title if known, else the fallback label. */
  private folderNameFor(key: string, fallback: string): string {
    return this.meta.get(key)?.title || fallback;
  }

  /** The "CHANNEL · model" line under the desk title (undefined if unknown). */
  private modelLineFor(key: string): string | undefined {
    const m = this.meta.get(key);
    if (!m) return undefined;
    const parts: string[] = [];
    if (m.source) parts.push(m.source.toUpperCase()); // e.g. TELEGRAM
    if (m.model) parts.push(m.model); // exact model id, e.g. deepseek-v4-flash
    return parts.length ? parts.join(" · ") : undefined;
  }

  /** Store/refresh session metadata; update an existing desk's label + model. */
  private applyMeta(
    key: string,
    m: { title?: string; source?: string; model?: string },
  ): void {
    const prev = this.meta.get(key) ?? {};
    const next = {
      title: m.title || prev.title,
      source: m.source || prev.source,
      model: m.model || prev.model,
    };
    // No change → skip the post.
    if (next.title === prev.title && next.source === prev.source && next.model === prev.model) {
      return;
    }
    this.meta.set(key, next);
    const entry = this.agents.get(key);
    if (entry) {
      this.post({
        type: "agentMeta",
        id: entry.id,
        folderName: this.folderNameFor(key, entry.label),
        model: this.modelLineFor(key),
      });
    }
  }

  /** Evict the oldest idle event-created desk; returns true if one was freed. */
  private evictOneIdle(): boolean {
    for (const [key, entry] of this.agents) {
      if (
        !entry.fromRoster &&
        entry.activeTools.size === 0 &&
        entry.activeTasks.size === 0 &&
        entry.idleTimer === null
      ) {
        this.removeAgent(key);
        return true;
      }
    }
    return false;
  }

  private removeAgent(key: string): void {
    const entry = this.agents.get(key);
    if (!entry) return;
    if (entry.idleTimer) clearTimeout(entry.idleTimer);
    this.agents.delete(key);
    this.post({ type: "agentClosed", id: entry.id });
  }

  private finishTurn(key: string): void {
    const entry = this.agents.get(key);
    if (!entry) return;
    if (entry.idleTimer) {
      clearTimeout(entry.idleTimer);
      entry.idleTimer = null;
    }
    entry.thinking = false;
    entry.activeTools.clear();
    entry.activeTasks.clear();
    entry.lastSubagentTool.clear();
    // agentToolsClear drops the office's currentTool, which also clears the
    // "💭 thinking" bubble (the office ties it to the thinking activity).
    this.post({ type: "agentToolsClear", id: entry.id });
    this.post({ type: "agentStatus", id: entry.id, status: "waiting" });
  }

  // ── Thinking activity (the Telegram "typing…" analog) ──────────────────────

  /** Synthesize a "💭 Pensando…" activity while the agent reasons pre-tool. */
  private beginThinking(entry: AgentEntry): void {
    if (entry.thinking) return;
    // Only when truly idle — never paper over a real tool already in flight.
    if (entry.activeTools.size > 0 || entry.activeTasks.size > 0) return;
    entry.thinking = true;
    const label = `${THINKING_VISUAL.emoji} ${THINKING_VISUAL.verb}`;
    this.post({
      type: "agentToolStart",
      id: entry.id,
      toolId: THINKING_TOOL_ID,
      toolName: THINKING_TOOL_ID, // office shows the 💭 bubble + a calm pose
      status: label,
      label,
    });
  }

  private endThinking(entry: AgentEntry): void {
    if (!entry.thinking) return;
    entry.thinking = false;
    this.post({ type: "agentToolDone", id: entry.id, toolId: THINKING_TOOL_ID });
  }

  /** Emit per-turn token usage so the office can draw the context fuel gauge. */
  private emitUsage(entry: AgentEntry, usage: unknown): void {
    if (!usage || typeof usage !== "object") return;
    const u = usage as Record<string, unknown>;
    const input = Number(u.input ?? u.prompt ?? u.input_tokens ?? 0) || 0;
    const output = Number(u.output ?? u.completion ?? u.output_tokens ?? 0) || 0;
    if (input <= 0 && output <= 0) return;
    this.post({
      type: "agentTokenUsage",
      id: entry.id,
      inputTokens: input,
      outputTokens: output,
    });
  }

  /**
   * Defensive idle sweep: the publisher drops frames under pressure, so a
   * missed tool.complete would otherwise leave a character typing forever.
   */
  private bumpIdle(key: string): void {
    const entry = this.agents.get(key);
    if (!entry) return;
    if (entry.idleTimer) clearTimeout(entry.idleTimer);
    entry.idleTimer = setTimeout(() => {
      entry.idleTimer = null;
      this.finishTurn(key);
    }, IDLE_CLEAR_MS);
  }
}
