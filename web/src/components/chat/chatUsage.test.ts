import { describe, expect, it } from "vitest";
import type { SessionInfo } from "./hooks/useChatGateway";
import type { SessionUsage } from "./hooks/useTokenUsage";
import { headerUsage } from "./chatUsage";

const session: SessionInfo = {
  sessionId: "live",
  sessionKey: "db",
  model: "m",
  modelProvider: "p",
  tokensUsed: 900,
  tokensMax: 32000,
  title: null,
};

function usage(fields: Partial<SessionUsage>): SessionUsage {
  return {
    model: "m", provider: "p", calls: 3, input: 0, output: 0, cache_read: 0, cache_write: 0, reasoning: 0,
    total: 0, cost_usd: null, cost_status: null, context_used: null, context_max: null, context_percent: null,
    compressions: 0, ...fields,
  };
}

describe("headerUsage", () => {
  it("gauges context in use against the window, not the cumulative total", () => {
    const result = headerUsage(usage({ total: 90000, context_used: 12000, context_max: 32000 }), session);
    expect([result.used, result.max]).toEqual([12000, 32000]);
  });

  it("shows the cumulative total when no window is known", () => {
    const result = headerUsage(usage({ total: 5000 }), { ...session, tokensMax: 0 });
    expect([result.used, result.max]).toEqual([5000, 0]);
  });

  it("builds a popover from the header numbers when the session has no breakdown", () => {
    const result = headerUsage(null, session);
    expect(result.popover).toMatchObject({ total: 900, context_used: 900, context_max: 32000, context_percent: 3 });
    expect(headerUsage(null, { ...session, tokensUsed: 0 }).popover).toBeNull();
  });
});
