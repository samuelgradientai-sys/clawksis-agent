import { describe, expect, it, vi } from "vitest";
import { PendingRpcs, routeGatewayFrame } from "./gatewayWire";

describe("pending calls", () => {
  it("settle with their response frame", async () => {
    const pending = new PendingRpcs();
    const sent: string[] = [];
    const call = pending.call("session.history", { session_id: "s" }, (f) => sent.push(f));
    const { id } = JSON.parse(sent[0]);
    expect(pending.settle({ id, result: { messages: [] } })).toBe(true);
    await expect(call).resolves.toEqual({ messages: [] });
  });

  it("are all rejected when the socket closes, so nothing awaits forever", async () => {
    const pending = new PendingRpcs();
    const resume = pending.call("session.resume", { session_id: "s" }, () => undefined);
    const attach = pending.call("image.attach", {}, () => undefined);
    pending.rejectAll("WebSocket closed");
    await expect(resume).rejects.toThrow("WebSocket closed");
    await expect(attach).rejects.toThrow("WebSocket closed");
    expect(pending.size).toBe(0);
  });
});

describe("frame routing", () => {
  const handlers = () => ({ onEvent: vi.fn(), onRequest: vi.fn(), onResponse: vi.fn() });

  it("hands a server→client request to onRequest instead of dropping it", () => {
    const h = handlers();
    routeGatewayFrame(JSON.stringify({ jsonrpc: "2.0", id: "srq-a", method: "approval", params: { session_id: "s" } }), h);
    expect(h.onRequest).toHaveBeenCalledWith("srq-a", "approval", { session_id: "s" });
    expect(h.onResponse).not.toHaveBeenCalled();
  });

  it("routes events and responses", () => {
    const h = handlers();
    routeGatewayFrame(JSON.stringify({ jsonrpc: "2.0", method: "event", params: { type: "message.delta", payload: { text: "x" } } }), h);
    routeGatewayFrame(JSON.stringify({ jsonrpc: "2.0", id: 4, result: {} }), h);
    routeGatewayFrame("not json", h);
    expect(h.onEvent).toHaveBeenCalledWith({ type: "message.delta", payload: { text: "x" } });
    expect(h.onResponse).toHaveBeenCalledWith({ jsonrpc: "2.0", id: 4, result: {} });
  });
});
