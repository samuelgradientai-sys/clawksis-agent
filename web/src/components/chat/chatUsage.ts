import type { SessionInfo } from "./hooks/useChatGateway";
import type { SessionUsage } from "./hooks/useTokenUsage";

export interface HeaderUsage {
  used: number;
  max: number;
  popover: SessionUsage | null;
}

/** What the header's token gauge shows. With a known context window the gauge
 *  is context in use over that window (never the session's cumulative total,
 *  which keeps growing past the window turn after turn); without one it is
 *  the cumulative total. The popover falls back to that number when the
 *  session has no persisted breakdown. */
export function headerUsage(usage: SessionUsage | null, session: SessionInfo): HeaderUsage {
  const max = usage?.context_max && usage.context_max > 0 ? usage.context_max : session.tokensMax;
  const used =
    max > 0
      ? (usage?.context_used ?? session.tokensUsed)
      : usage && usage.total > 0
        ? usage.total
        : session.tokensUsed;
  if (usage || used <= 0) return { used, max, popover: usage };
  return {
    used,
    max,
    popover: {
      model: session.model,
      provider: session.modelProvider,
      calls: 0,
      input: 0,
      output: 0,
      cache_read: 0,
      cache_write: 0,
      reasoning: 0,
      total: used,
      cost_usd: null,
      cost_status: null,
      context_used: used,
      context_max: max > 0 ? max : null,
      context_percent: max > 0 ? Math.min(100, Math.round((used / max) * 100)) : null,
      compressions: 0,
    },
  };
}
