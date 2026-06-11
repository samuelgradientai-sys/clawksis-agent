/**
 * Live tool-activity feed — a chronological stream of what agents are doing
 * with their tools, derived from the same gateway event feed that drives the
 * pixel office. This is the "read the raw activity" companion to the office's
 * "watch the characters" view.
 */

import { useMemo } from "react";

import type { GatewayEvent, GatewayFeed } from "./gatewayFeed";

interface Row {
  ev: GatewayEvent;
  icon: string;
  title: string;
  detail: string;
  tone: "tool" | "subagent" | "message" | "wait" | "other";
}

function str(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

function describe(ev: GatewayEvent): Row {
  const p = ev.payload;
  switch (ev.type) {
    case "tool.start":
      return {
        ev,
        icon: "▶",
        title: str(p.name) || "Tool",
        detail: str(p.context) || str(p.args_text),
        tone: "tool",
      };
    case "tool.complete":
      return {
        ev,
        icon: "✓",
        title: `${str(p.name) || "Tool"} done`,
        detail: str(p.summary) || (p.duration_s ? `${str(p.duration_s)}s` : ""),
        tone: "tool",
      };
    case "subagent.spawn_requested":
    case "subagent.start":
      return {
        ev,
        icon: "⑂",
        title: "Subagent started",
        detail: str(p.goal),
        tone: "subagent",
      };
    case "subagent.tool":
      return {
        ev,
        icon: "↳",
        title: "Subagent tool",
        detail: `${str(p.tool_name)} ${str(p.tool_preview) || str(p.text)}`.trim(),
        tone: "subagent",
      };
    case "subagent.complete":
      return {
        ev,
        icon: "✓",
        title: "Subagent done",
        detail: str(p.summary),
        tone: "subagent",
      };
    case "message.start":
      return { ev, icon: "✎", title: "Thinking / replying", detail: "", tone: "message" };
    case "message.complete":
      return { ev, icon: "■", title: "Turn complete", detail: "", tone: "message" };
    case "clarify.request":
    case "approval.request":
      return {
        ev,
        icon: "?",
        title: ev.type === "clarify.request" ? "Asking a question" : "Awaiting approval",
        detail: str(p.text) || str(p.prompt),
        tone: "wait",
      };
    case "agent.message":
    case "inter_agent.utterance":
      return {
        ev,
        icon: "💬",
        title: `Agent → ${str(p.to) || "agent"}`,
        detail: str(p.text) || str(p.body),
        tone: "subagent",
      };
    default:
      return { ev, icon: "•", title: ev.type, detail: "", tone: "other" };
  }
}

const TONE_CLASS: Record<Row["tone"], string> = {
  tool: "text-[var(--color-primary)]",
  subagent: "text-amber-400",
  message: "text-muted-foreground",
  wait: "text-rose-400",
  other: "text-muted-foreground",
};

interface ActivityFeedViewProps {
  feed: GatewayFeed;
}

export function ActivityFeedView({ feed }: ActivityFeedViewProps) {
  const rows = useMemo(
    () =>
      feed.events
        .map(describe)
        .reverse()
        .slice(0, 200),
    [feed.events],
  );

  return (
    <div className="h-full overflow-y-auto rounded-lg border border-border bg-card/40 p-3 font-mono text-xs">
      {rows.length === 0 ? (
        <div className="flex h-full items-center justify-center text-muted-foreground">
          No activity yet — agent tool calls will appear here live.
        </div>
      ) : (
        <ul className="space-y-1">
          {rows.map((r) => (
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
  );
}
