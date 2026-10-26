import { describe, expect, it, vi } from "vitest";
import { loadTranscript, openInitialSession, resumeIsBusy } from "./sessionOpen";

function fakeRpc(replies: Record<string, unknown>) {
  return vi.fn(async (method: string) => {
    const reply = replies[method];
    if (reply instanceof Error) throw reply;
    return reply;
  });
}

describe("opening a conversation on connect", () => {
  it("remembers the stored key of a freshly created session, not its live sid", async () => {
    const rpc = fakeRpc({
      "session.most_recent": { session_id: null },
      "session.create": { session_id: "live-9", stored_session_id: "20261026_db9", messages: [], info: {} },
    });
    const opened = await openInitialSession(rpc, null);
    expect(opened).toMatchObject({ sid: "live-9", storedKey: "20261026_db9" });
    expect(rpc).not.toHaveBeenCalledWith("session.resume", expect.anything());
  });

  it("re-resumes the selected conversation before looking at the most recent one", async () => {
    const rpc = fakeRpc({ "session.resume": { session_id: "live-1", messages: [] } });
    const opened = await openInitialSession(rpc, "db-1");
    expect(opened).toMatchObject({ sid: "live-1", storedKey: "db-1" });
    expect(rpc).toHaveBeenCalledTimes(1);
  });

  it("uses the resume's own messages and adds the turn still running", async () => {
    const rpc = fakeRpc({});
    const view = await loadTranscript(
      rpc,
      {
        sid: "live-1",
        storedKey: "db-1",
        resume: {
          messages: [{ role: "user", text: "antes" }, { role: "assistant", text: "ok" }],
          inflight: { user: "ahora", assistant: "pensando", streaming: true },
          running: true,
        },
      },
      "h",
    );
    expect(view.map((m) => [m.role, m.content, m.streaming])).toEqual([
      ["user", "antes", false],
      ["assistant", "ok", false],
      ["user", "ahora", false],
      ["assistant", "pensando", true],
    ]);
    expect(rpc).not.toHaveBeenCalled();
    expect(resumeIsBusy({ running: true })).toBe(true);
    expect(resumeIsBusy({ running: false })).toBe(false);
  });
});
