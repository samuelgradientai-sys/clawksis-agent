import { describe, expect, it, vi } from "vitest";
import { createDeltaBuffer, dispatchChatEvent, isOwnEvent, type ChatEventContext } from "./chatEvents";
import type { ChatMessage, SessionInfo } from "./useChatGateway";

function harness(liveSid: string | null = "live-1") {
  const state = {
    messages: [] as ChatMessage[],
    session: { sessionId: liveSid, sessionKey: null, model: null, modelProvider: null, tokensUsed: 0, tokensMax: 0, title: null } as SessionInfo,
    busy: true,
    error: null as string | null,
    live: null as string | null,
    cancelled: [] as string[],
    cancelledApprovals: [] as string[][],
    revisions: 0,
  };
  const ctx: ChatEventContext = {
    setMessages: (u) => (state.messages = u(state.messages)),
    setSession: (u) => (state.session = u(state.session)),
    setBusy: (b) => (state.busy = b),
    setErrorMessage: (m) => (state.error = m),
    setLiveStatus: (t) => (state.live = t),
    bumpSessions: () => state.revisions++,
    ids: { liveSid: { current: liveSid }, selectedKey: { current: "db-1" } },
    deltas: { push: () => undefined, take: () => "" },
    turn: { started: false, submitsInFlight: 0 },
    requests: {
      cancel: (id) => state.cancelled.push(id),
      cancelApprovals: (ids) => state.cancelledApprovals.push(ids),
    },
  };
  const emit = (type: string, payload: Record<string, unknown> = {}, sid: string | undefined = liveSid ?? undefined) =>
    dispatchChatEvent(ctx, { type, session_id: sid, payload });
  return { state, ctx, emit };
}

describe("only a real turn end releases the composer", () => {
  it("keeps busy through a failed stream open that a fallback may recover from", () => {
    const { state, emit } = harness();
    emit("message.start");
    emit("status.update", { kind: "error", text: "❌ Could not open a stream to provider X" });
    expect(state.busy).toBe(true);
    expect(state.live).toContain("Could not open a stream");
    emit("message.complete", { text: "respuesta del fallback", status: "complete" });
    expect(state.busy).toBe(false);
    expect(state.messages[state.messages.length - 1].content).toBe("respuesta del fallback");
  });

  it("keeps busy on an out-of-band error during a turn", () => {
    const { state, emit } = harness();
    emit("message.start");
    emit("error", { message: "compression failed: boom" });
    expect(state.error).toBe("compression failed: boom");
    expect(state.busy).toBe(true);
  });

  it("releases on an error that refused the submit before any turn event", () => {
    const { state, emit } = harness();
    emit("error", { message: "Turn cancelled before the agent was ready" });
    expect(state.busy).toBe(false);
  });

  it("ends the turn on running:false, but not while our submit is unanswered", () => {
    const { state, ctx, emit } = harness();
    ctx.turn.submitsInFlight = 1;
    emit("session.info", { running: false, model: "m" });
    expect(state.busy).toBe(true);
    expect(state.session.model).toBe("m");
    ctx.turn.submitsInFlight = 0;
    emit("session.info", { running: false });
    expect(state.busy).toBe(false);
  });
});

describe("events of other conversations", () => {
  it("never touch the transcript or the header", () => {
    const { state, emit } = harness("live-1");
    emit("message.start", {}, "other");
    emit("session.info", { model: "foreign-model", running: false }, "other");
    expect(state.messages).toEqual([]);
    expect(state.session.model).toBeNull();
    expect(state.busy).toBe(true);
  });

  it("still withdraw their question cards and refresh the list", () => {
    const { state, emit } = harness("live-1");
    emit("request.cancel", { id: "srq-9", method: "approval", reason: "timeout" }, "other");
    emit("session.title", { title: "Otra" }, "other");
    expect(state.cancelled).toEqual(["srq-9"]);
    expect(state.revisions).toBe(1);
    expect(state.session.title).toBeNull();
  });

  it("are all foreign while no live sid is known (connecting or switching)", () => {
    expect(isOwnEvent(null, "any")).toBe(false);
    expect(isOwnEvent(null, undefined)).toBe(true);
    expect(isOwnEvent("a", "a")).toBe(true);
  });

  it("approval.cancelled (a global broadcast) withdraws the approval cards", () => {
    const { state, emit } = harness();
    emit("approval.cancelled", { session_id: "live-1", stored_session_id: "db", reason: "interrupt", cancelled_count: 1, request_ids: ["r1"] }, undefined);
    expect(state.cancelledApprovals).toEqual([["r1"]]);
  });
});

describe("delta buffer", () => {
  it("coalesces into one flush and hands back what a completion takes first", () => {
    const flushed: string[] = [];
    let scheduled: (() => void) | null = null;
    const cancel = vi.fn();
    const buf = createDeltaBuffer((t) => flushed.push(t), (cb) => ((scheduled = cb), 1), cancel);
    buf.push("ho");
    buf.push("la");
    scheduled!();
    expect(flushed).toEqual(["hola"]);
    buf.push(" mundo");
    expect(buf.take()).toBe(" mundo");
    expect(cancel).toHaveBeenCalledWith(1);
  });
});
