import { describe, expect, it, vi } from "vitest";
import {
  deliverAnswer,
  isServerRequestFrame,
  parseServerRequest,
  requestsFromResume,
  responseFrame,
  unhandledReply,
} from "./serverRequests";

describe("server→client requests", () => {
  it("parses an approval frame and answers with the {choice} result frame", () => {
    const frame = {
      jsonrpc: "2.0",
      id: "srq-0123456789ab",
      method: "approval",
      params: {
        session_id: "live-1",
        request_id: "appr-1",
        command: "rm -rf /tmp/x",
        description: "recursive delete",
        choices: ["once", "session", "always", "deny"],
      },
    };
    expect(isServerRequestFrame(frame)).toBe(true);
    const req = parseServerRequest(frame.id, frame.method, frame.params);
    expect(req).toMatchObject({ kind: "approval", sessionId: "live-1", requestId: "appr-1", choices: ["once", "session", "always", "deny"] });
    expect(JSON.parse(responseFrame(frame.id, { choice: "once" }))).toEqual({
      jsonrpc: "2.0",
      id: "srq-0123456789ab",
      result: { choice: "once" },
    });
  });

  it("drops the permanent choice when the server forbids it", () => {
    const req = parseServerRequest("srq-1", "approval", { session_id: "s", allow_permanent: false });
    expect(req?.kind === "approval" && req.choices).toEqual(["once", "session", "deny"]);
  });

  it("does not mistake our own responses or events for requests", () => {
    expect(isServerRequestFrame({ jsonrpc: "2.0", id: 3, result: {} })).toBe(false);
    expect(isServerRequestFrame({ jsonrpc: "2.0", method: "event", params: { type: "x" } })).toBe(false);
  });

  it("answers a method it has no card for with -32601 at once", () => {
    expect(parseServerRequest("srq-2", "preview.read", { session_id: "s" })).toBeNull();
    expect(JSON.parse(unhandledReply("srq-2", "preview.read"))).toMatchObject({ id: "srq-2", error: { code: -32601 } });
  });

  it("keeps a clarify's questions and the answers already locked", () => {
    const req = parseServerRequest("srq-3", "clarify", {
      session_id: "s",
      questions: [{ qid: "q1", question: "¿Color?", choices: ["rojo", "azul"], multi_select: false }, { qid: "", question: "x" }],
      answers: { q1: "rojo", q2: null },
    });
    expect(req).toMatchObject({
      kind: "clarify",
      questions: [{ qid: "q1", question: "¿Color?", choices: ["rojo", "azul"], multiSelect: false }],
      answers: { q1: "rojo" },
    });
  });

  it("restores open requests from a resume, plus a frameless queue approval", () => {
    const reqs = requestsFromResume({
      session_id: "live-2",
      open_requests: [{ id: "srq-4", method: "sudo", params: { session_id: "live-2", command: "sudo ls" } }],
      pending_approval: { request_id: "appr-9", command: "rm -rf x", choices: ["once", "deny"] },
    });
    expect(reqs.map((r) => [r.kind, r.id, r.replayed])).toEqual([
      ["sudo", "srq-4", true],
      ["approval", "pending-approval:appr-9", true],
    ]);
    expect(reqs[1]).toMatchObject({ viaRpc: true, sessionId: "live-2", requestId: "appr-9", choices: ["once", "deny"] });
  });

  it("does not duplicate a pending approval already open as a request", () => {
    const reqs = requestsFromResume({
      open_requests: [{ id: "srq-5", method: "approval", params: { session_id: "s", request_id: "appr-1" } }],
      pending_approval: { request_id: "appr-1" },
    });
    expect(reqs.map((r) => r.id)).toEqual(["srq-5"]);
  });

  it("answers a frameless approval through approval.respond", async () => {
    const [req] = requestsFromResume({ session_id: "live-3", pending_approval: { request_id: "appr-2" } });
    const rpc = vi.fn().mockResolvedValue({ resolved: 1 });
    const sendFrame = vi.fn();
    await deliverAnswer(req, { choice: "deny" }, { rpc, sendFrame });
    expect(rpc).toHaveBeenCalledWith("approval.respond", { session_id: "live-3", choice: "deny", request_id: "appr-2" });
    expect(sendFrame).not.toHaveBeenCalled();
  });

  it("fails loudly when the socket is gone", async () => {
    const req = parseServerRequest("srq-6", "secret", { session_id: "s", env_var: "TOKEN", prompt: "p" })!;
    await expect(deliverAnswer(req, { value: "x" }, { rpc: vi.fn(), sendFrame: () => false })).rejects.toThrow();
  });
});
