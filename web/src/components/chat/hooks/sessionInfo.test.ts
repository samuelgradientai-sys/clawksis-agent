import { describe, expect, it } from "vitest";
import type { SessionInfo } from "./useChatGateway";
import { applySessionInfo, storedSessionKey, titleFromEvent, trackSessionIds } from "./sessionInfo";

const empty: SessionInfo = {
  sessionId: null,
  sessionKey: null,
  model: null,
  modelProvider: null,
  tokensUsed: 0,
  tokensMax: 0,
  title: null,
};

describe("applySessionInfo", () => {
  it("reads the field names the gateway's session.info actually sends", () => {
    const next = applySessionInfo(
      empty,
      {
        model: "fake-model",
        provider: "custom",
        stored_session_id: "20261026_013428_b01603",
        title: "Saludo",
        usage: { context_used: 1200, context_max: 32768 },
      },
      "live-1",
    );
    expect(next).toEqual({
      sessionId: "live-1",
      sessionKey: "20261026_013428_b01603",
      model: "fake-model",
      modelProvider: "custom",
      tokensUsed: 1200,
      tokensMax: 32768,
      title: "Saludo",
    });
  });

  it("keeps what it had when a field is empty", () => {
    const prev = { ...empty, model: "m", title: "Old", tokensMax: 100 };
    expect(applySessionInfo(prev, { title: "", model: "", usage: {} }, null)).toEqual(prev);
  });
});

describe("session event helpers", () => {
  it("prefers stored_session_id and trims announced titles", () => {
    expect(storedSessionKey({ stored_session_id: "db", session_id: "old" })).toBe("db");
    expect(storedSessionKey({ session_id: "legacy" })).toBe("legacy");
    expect(titleFromEvent({ title: "  Plan de viaje " })).toBe("Plan de viaje");
    expect(titleFromEvent({ title: "   " })).toBeNull();
  });

  it("tracks the live sid and the stored key once", () => {
    const refs = { liveSid: { current: null as string | null }, selectedKey: { current: null as string | null } };
    expect(trackSessionIds(refs, "live-1", { stored_session_id: "db-1" })).toBe("live-1");
    expect(refs).toEqual({ liveSid: { current: "live-1" }, selectedKey: { current: "db-1" } });
    trackSessionIds(refs, "live-1", { stored_session_id: "db-2" });
    expect(refs.selectedKey.current).toBe("db-1");
  });
});
