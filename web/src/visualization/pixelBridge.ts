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
 *   tool.start        → agentToolStart   (toolName, "name: context" status)
 *   tool.complete     → agentToolDone
 *   subagent.start    → agentToolStart   (toolName "Task", "Subtask: goal")
 *                       — pixel-agents auto-spawns a sub-character for it
 *   subagent.tool     → subagentToolStart (under the parent's task tool)
 *   subagent.complete → agentToolDone + subagentClear
 *   message.start     → agentStatus active
 *   message.complete  → agentToolsClear + agentStatus waiting (turn end,
 *                       only when no tools remain in flight)
 *   clarify/approval  → agentStatus waiting
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
}

function asString(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

export class PixelBridge {
  private post: PixelPost;
  private agents = new Map<string, AgentEntry>();
  private nextId = 1;
  private subagentToolSeq = 1;
  private warnedFull = false;

  constructor(post: PixelPost) {
    this.post = post;
  }

  /** Number of characters currently in the office. */
  get agentCount(): number {
    return this.agents.size;
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

    switch (ev.type) {
      case "tool.start": {
        const entry = this.ensureAgent(sid, this.defaultLabel(sid));
        if (!entry) return;
        const toolId = asString(p.tool_id) || `tool-${ev.id}`;
        const name = asString(p.name) || "Tool";
        const context = asString(p.context);
        entry.activeTools.add(toolId);
        this.post({
          type: "agentToolStart",
          id: entry.id,
          toolId,
          toolName: name,
          status: context ? `${name}: ${context}` : name,
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
        const subId = asString(p.subagent_id) || `sub-${ev.id}`;
        const taskToolId = `task-${subId}`;
        if (entry.activeTasks.has(taskToolId)) return; // spawn_requested then start
        entry.activeTasks.add(taskToolId);
        const goal = asString(p.goal) || "delegated task";
        // toolName "Task" + non-"hook-" toolId makes pixel-agents spawn a
        // sub-character; the "Subtask:" prefix becomes its label.
        this.post({
          type: "agentToolStart",
          id: entry.id,
          toolId: taskToolId,
          toolName: "Task",
          status: `Subtask: ${goal}`,
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
        const label =
          ev.type === "subagent.thinking"
            ? "Thinking"
            : asString(p.tool_name) || asString(p.text) || "Working";
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
          status: label,
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
        this.post({ type: "agentStatus", id: entry.id, status: "active" });
        this.bumpIdle(sid);
        break;
      }

      case "message.complete": {
        const entry = this.agents.get(sid);
        if (!entry) return;
        if (entry.activeTools.size === 0 && entry.activeTasks.size === 0) {
          this.finishTurn(sid);
        } else {
          this.bumpIdle(sid);
        }
        break;
      }

      case "clarify.request":
      case "approval.request": {
        const entry = this.ensureAgent(sid, this.defaultLabel(sid));
        if (!entry) return;
        this.post({ type: "agentStatus", id: entry.id, status: "waiting" });
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
    };
    this.agents.set(key, entry);
    this.post({ type: "agentCreated", id: entry.id, folderName: label });
    return entry;
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
    entry.activeTools.clear();
    entry.activeTasks.clear();
    entry.lastSubagentTool.clear();
    this.post({ type: "agentToolsClear", id: entry.id });
    this.post({ type: "agentStatus", id: entry.id, status: "waiting" });
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
