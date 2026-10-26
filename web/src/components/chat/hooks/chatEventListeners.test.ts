import { describe, expect, it, vi } from "vitest";
import { dispatchChatEvent, type ChatEventContext, type GatewayEventFrame } from "./chatEvents";
import { subscribeChatEvents } from "./chatEventListeners";

function context(liveSid: string): ChatEventContext {
  return {
    setMessages: () => undefined,
    setSession: () => undefined,
    setBusy: vi.fn(),
    setErrorMessage: () => undefined,
    setLiveStatus: () => undefined,
    bumpSessions: () => undefined,
    ids: { liveSid: { current: liveSid }, selectedKey: { current: null } },
    deltas: { push: () => undefined, take: () => "" },
    turn: { started: false, submitsInFlight: 0 },
    requests: { cancel: () => undefined, cancelApprovals: () => undefined },
  };
}

describe("chat event listeners", () => {
  it("see the open conversation's events after the chat handled them, never another session's", () => {
    const ctx = context("live-1");
    const seen: Array<[string, boolean]> = [];
    const stop = subscribeChatEvents((event) => seen.push([event.type, ctx.turn.started]));
    dispatchChatEvent(ctx, { type: "message.delta", session_id: "live-1", payload: { text: "hola" } });
    dispatchChatEvent(ctx, { type: "message.delta", session_id: "cron-7", payload: { text: "ajeno" } });
    dispatchChatEvent(ctx, { type: "sessions.changed" });
    stop();
    dispatchChatEvent(ctx, { type: "message.complete", session_id: "live-1", payload: {} });
    expect(seen).toEqual([
      ["message.delta", true], // the handler already marked the turn started
      ["sessions.changed", true],
    ]);
  });

  it("a failing listener does not stop the transcript or the other listeners", () => {
    const ctx = context("live-1");
    const after: GatewayEventFrame[] = [];
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const stopBad = subscribeChatEvents(() => {
      throw new Error("boom");
    });
    const stopGood = subscribeChatEvents((event) => after.push(event));
    dispatchChatEvent(ctx, { type: "message.complete", session_id: "live-1", payload: { text: "fin" } });
    stopBad();
    stopGood();
    errors.mockRestore();
    expect(ctx.setBusy).toHaveBeenCalledWith(false);
    expect(after.map((e) => e.type)).toEqual(["message.complete"]);
  });
});
