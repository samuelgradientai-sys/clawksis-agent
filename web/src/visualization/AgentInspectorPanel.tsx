/**
 * Agent Inspector — a right-side dock (ctrl/bulletproof.sh-style) that lists
 * every agent currently in the event feed and, on click, shows that agent's
 * detail: model / channel, status, turns, tools run, token usage and a live
 * scroll of the tools it has executed.
 *
 * Everything is derived from the SAME merged event feed that drives the pixel
 * office (no extra backend, no dependency on clicking a sprite inside the
 * iframe). An agent === a gateway session id; its title/model/channel are
 * accumulated from the `session_*` fields the bridge already ships on events,
 * mirroring PixelBridge.applyMeta. Activity rows reuse ActivityFeedView's
 * `describe()` so the labels match the global feed exactly.
 */

import { useMemo, useState } from "react";

import { describe, TONE_CLASS } from "./ActivityFeedView";
import type { GatewayEvent, GatewayFeed } from "./gatewayFeed";

const MAIN_SESSION_KEY = "__main__";
/** An agent counts as "active" if it emitted any event within this window. */
const ACTIVE_WINDOW_MS = 10_000;
/** Cap the per-agent activity list so a busy session can't blow up the DOM. */
const MAX_ACTIVITY_ROWS = 120;

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

/** Same readable fallback PixelBridge uses for sessions without a real title. */
function fallbackLabel(key: string): string {
  if (key === MAIN_SESSION_KEY) return "Chat";
  const idx = key.indexOf(":");
  if (idx > 0) {
    const platform = key.slice(0, idx);
    const id = key.slice(idx + 1);
    const cap = platform.charAt(0).toUpperCase() + platform.slice(1);
    return `${cap} · ${id.slice(0, 10)}`;
  }
  return `Sesión ${key.slice(0, 8)}`;
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

interface AgentInfo {
  key: string;
  title: string;
  model: string;
  source: string;
  tools: number;
  turns: number;
  inputTokens: number;
  outputTokens: number;
  lastTs: number;
  active: boolean;
  events: GatewayEvent[];
}

/** Fold the flat event ring buffer into one entry per agent (session). */
function buildAgents(events: GatewayEvent[], now: number): AgentInfo[] {
  const map = new Map<string, AgentInfo>();
  for (const ev of events) {
    const key = ev.sessionId ?? MAIN_SESSION_KEY;
    let a = map.get(key);
    if (!a) {
      a = {
        key,
        title: "",
        model: "",
        source: "",
        tools: 0,
        turns: 0,
        inputTokens: 0,
        outputTokens: 0,
        lastTs: 0,
        active: false,
        events: [],
      };
      map.set(key, a);
    }
    const p = ev.payload;
    const title = str(p.session_title);
    const source = str(p.session_source);
    const model = str(p.session_model);
    if (title) a.title = title;
    if (source) a.source = source;
    if (model) a.model = model;

    if (ev.type === "tool.start") a.tools += 1;
    else if (ev.type === "message.start") a.turns += 1;
    else if (ev.type === "message.complete") {
      const u =
        p.usage && typeof p.usage === "object" ? (p.usage as Record<string, unknown>) : {};
      a.inputTokens += Number(u.input ?? u.prompt ?? u.input_tokens ?? 0) || 0;
      a.outputTokens += Number(u.output ?? u.completion ?? u.output_tokens ?? 0) || 0;
    }

    if (ev.ts > a.lastTs) a.lastTs = ev.ts;
    a.events.push(ev);
  }

  const list = [...map.values()];
  for (const a of list) {
    if (!a.title) a.title = fallbackLabel(a.key);
    a.active = now - a.lastTs < ACTIVE_WINDOW_MS;
  }
  // Active agents first, then most-recently-seen.
  list.sort(
    (x, y) => Number(y.active) - Number(x.active) || y.lastTs - x.lastTs,
  );
  return list;
}

interface AgentInspectorPanelProps {
  feed: GatewayFeed;
  className?: string;
}

export function AgentInspectorPanel({ feed, className }: AgentInspectorPanelProps) {
  // Re-fold on every feed change; cheap (the ring buffer is ≤500 events) and
  // keeps the "active" dot honest without a separate timer.
  const agents = useMemo(() => buildAgents(feed.events, Date.now()), [feed.events]);
  // Nothing is selected until the user clicks an agent — the detail dock stays
  // closed until then (no auto-select), per the "click an agent to inspect" UX.
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const selected = agents.find((a) => a.key === selectedKey) ?? null;

  const activity = useMemo(() => {
    if (!selected) return [];
    return selected.events.slice(-MAX_ACTIVITY_ROWS).map(describe).reverse();
  }, [selected]);

  const wrap = `flex min-h-0 flex-col rounded-lg border border-border bg-card/40 ${className ?? ""}`;

  if (agents.length === 0) {
    return (
      <aside className={wrap}>
        <div className="flex h-full items-center justify-center p-4 text-center text-xs text-muted-foreground">
          Cuando un agente trabaje, aparecerá acá. Hacé clic en uno para ver qué
          herramientas ejecutó y qué hizo.
        </div>
      </aside>
    );
  }

  return (
    <aside className={wrap}>
      {/* Agent list */}
      <div className="shrink-0 border-b border-border px-3 py-2 text-xs font-semibold text-muted-foreground">
        Agentes ({agents.length})
      </div>
      <ul className="max-h-[34%] shrink-0 overflow-y-auto p-1">
        {agents.map((a) => {
          const isSel = a.key === selectedKey;
          return (
            <li key={a.key}>
              <button
                type="button"
                onClick={() => setSelectedKey(a.key)}
                className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                  isSel
                    ? "bg-[var(--color-primary)]/15 text-foreground"
                    : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
                }`}
              >
                <span
                  className={`inline-block h-2 w-2 shrink-0 rounded-full ${
                    a.active ? "bg-emerald-500" : "bg-muted-foreground/40"
                  }`}
                  title={a.active ? "Activo" : "Inactivo"}
                />
                <span className="min-w-0 flex-1 truncate font-medium">{a.title}</span>
                {a.tools > 0 && (
                  <span className="shrink-0 tabular-nums text-muted-foreground/70">
                    {a.tools} 🛠️
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {/* Selected-agent detail — only after the user clicks an agent. */}
      {!selected && (
        <div className="flex min-h-0 flex-1 items-center justify-center border-t border-border p-4 text-center text-xs text-muted-foreground">
          Hacé clic en un agente para ver su modelo, herramientas y actividad.
        </div>
      )}
      {selected && (
        <div className="flex min-h-0 flex-1 flex-col border-t border-border">
          <div className="shrink-0 px-3 pt-2">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm font-semibold" title={selected.title}>
                {selected.title}
              </span>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
                  selected.active
                    ? "bg-emerald-500/15 text-emerald-400"
                    : "bg-muted-foreground/10 text-muted-foreground"
                }`}
              >
                {selected.active ? "Activo" : "Inactivo"}
              </span>
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <Stat label="Modelo" value={selected.model || "—"} />
              <Stat label="Canal" value={selected.source ? selected.source.toUpperCase() : "—"} />
              <Stat label="Turnos" value={String(selected.turns)} />
              <Stat label="Tools" value={String(selected.tools)} />
              <Stat
                label="Tokens"
                value={
                  selected.inputTokens || selected.outputTokens
                    ? `${fmtTokens(selected.inputTokens)} in · ${fmtTokens(selected.outputTokens)} out`
                    : "—"
                }
              />
            </dl>
          </div>

          <div className="mt-2 shrink-0 px-3 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Actividad
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-1 font-mono text-[11px]">
            {activity.length === 0 ? (
              <div className="py-3 text-muted-foreground">Sin actividad todavía.</div>
            ) : (
              <ul className="space-y-1">
                {activity.map((r) => (
                  <li key={r.ev.id} className="flex items-start gap-2 leading-relaxed">
                    <span className="tabular-nums text-muted-foreground/60">
                      {new Date(r.ev.ts).toLocaleTimeString()}
                    </span>
                    <span className={TONE_CLASS[r.tone]}>{r.icon}</span>
                    <span className="font-semibold">{r.title}</span>
                    {r.detail && (
                      <span className="truncate text-muted-foreground" title={r.detail}>
                        {r.detail}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wide text-muted-foreground/60">{label}</dt>
      <dd className="truncate text-foreground" title={value}>
        {value}
      </dd>
    </div>
  );
}
