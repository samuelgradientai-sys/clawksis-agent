/**
 * Visualization section — watch agents work, live.
 *
 * One live event feed (the dashboard chat's gateway channel) drives three
 * swappable visuals:
 *   - Pixel Office  : the vendored pixel-agents office, characters animate as
 *                     agents use tools (iframe at /pixel-office).
 *   - Activity Feed : a chronological stream of tool calls / subagent steps.
 *   - Comms Graph   : a delegation + inter-agent-message graph.
 *
 * The feed comes from the embedded ChatPage's PTY gateway (published to the
 * module store by ChatPage). If no chat session is live yet, we show an
 * empty state pointing the user to open Chat — that's what stands up the
 * event channel today. New visuals can be added by dropping another tab.
 */

import { useEffect, useState } from "react";

import { fetchJSON } from "@/lib/api";
import { useActiveEventChannel } from "@/lib/eventChannelStore";

import { ActivityFeedView } from "../visualization/ActivityFeedView";
import type { AgentMessage } from "../visualization/CommsGraphView";
import { CommsGraphView } from "../visualization/CommsGraphView";
import { useGatewayFeed } from "../visualization/gatewayFeed";
import {
  getOfficeProvider,
  loadOfficeProviderId,
  OFFICE_PROVIDERS,
  saveOfficeProviderId,
} from "../visualization/officeProviders";
import { PixelOfficeView } from "../visualization/PixelOfficeView";

const MSG_POLL_MS = 6000;

type VisualId = "office" | "activity" | "graph";

const VISUALS: { id: VisualId; label: string; hint: string }[] = [
  { id: "office", label: "Pixel Office", hint: "Agents as characters using their tools" },
  { id: "activity", label: "Activity Feed", hint: "Live stream of tool calls" },
  { id: "graph", label: "Comms Graph", hint: "Delegations & agent-to-agent messages" },
];

export default function VisualizationPage() {
  const channel = useActiveEventChannel();
  const feed = useGatewayFeed(channel);
  const [active, setActive] = useState<VisualId>("office");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [officeProviderId, setOfficeProviderId] = useState<string>(loadOfficeProviderId);
  const officeProvider = getOfficeProvider(officeProviderId);

  const onPickProvider = (id: string) => {
    setOfficeProviderId(id);
    saveOfficeProviderId(id);
  };

  // Poll persisted peer-to-peer agent messages while the graph is visible.
  useEffect(() => {
    if (active !== "graph") return;
    let stopped = false;
    const poll = async () => {
      try {
        const res = await fetchJSON<{ messages?: AgentMessage[] }>(
          "/api/visualization/agent-messages?limit=200",
        );
        if (!stopped) setMessages(res.messages ?? []);
      } catch {
        // Endpoint may 404 on older servers, or the toolset never ran.
      }
    };
    void poll();
    const t = setInterval(() => void poll(), MSG_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(t);
    };
  }, [active]);

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Visualization</h1>
          <p className="text-sm text-muted-foreground">
            Watch your agents work with their tools, live.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              feed.connected ? "bg-emerald-500" : "bg-muted-foreground/50"
            }`}
          />
          <span className="text-muted-foreground">
            {feed.connected ? "Live" : channel ? "Connecting…" : "No live session"}
          </span>
        </div>
      </header>

      <nav className="flex flex-wrap gap-2">
        {VISUALS.map((v) => (
          <button
            key={v.id}
            type="button"
            onClick={() => setActive(v.id)}
            title={v.hint}
            className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${
              active === v.id
                ? "border-[var(--color-primary)] bg-[var(--color-primary)]/15 text-[var(--color-foreground)]"
                : "border-border bg-card/40 text-muted-foreground hover:text-foreground"
            }`}
          >
            {v.label}
          </button>
        ))}
      </nav>

      <div className="relative min-h-0 flex-1">
        {!channel ? (
          <EmptyState />
        ) : (
          <div className="h-full">
            {active === "office" && (
              <div className="flex h-full flex-col gap-2">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <label htmlFor="office-visual" className="font-medium">
                    Visual:
                  </label>
                  <select
                    id="office-visual"
                    value={officeProviderId}
                    onChange={(e) => onPickProvider(e.target.value)}
                    className="rounded-md border border-border bg-card/60 px-2 py-1 text-foreground"
                  >
                    {OFFICE_PROVIDERS.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  {officeProvider.credit && (
                    <span className="opacity-70">· {officeProvider.credit}</span>
                  )}
                </div>
                <div className="min-h-0 flex-1">
                  <PixelOfficeView
                    key={officeProvider.id}
                    provider={officeProvider}
                    feed={feed}
                  />
                </div>
              </div>
            )}
            {active === "activity" && <ActivityFeedView feed={feed} />}
            {active === "graph" && <CommsGraphView feed={feed} messages={messages} />}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card/30 text-center">
      <p className="text-base font-medium">No live agent session yet</p>
      <p className="max-w-md text-sm text-muted-foreground">
        Open <span className="font-semibold">Chat</span> and send a message to
        start a session. Its tool activity will stream here in real time — as
        animated characters, an activity feed, or a delegation graph.
      </p>
    </div>
  );
}
