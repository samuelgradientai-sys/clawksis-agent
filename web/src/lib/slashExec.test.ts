import { describe, expect, it, vi } from "vitest";
import { executeSlash, type SlashExecCallbacks } from "./slashExec";

function run(command: string, replies: Record<string, unknown>) {
  const calls: string[] = [];
  const gw = {
    request: vi.fn(async (method: string) => {
      calls.push(method);
      const reply = replies[method];
      if (reply instanceof Error) throw reply;
      return reply as never;
    }),
  };
  const order: string[] = [];
  const callbacks: Required<SlashExecCallbacks> = {
    sys: vi.fn((t: string) => void order.push("sys:" + t)),
    send: vi.fn(async (m: string, o?: { asUserTurn?: boolean }) => void order.push(`send:${m}:${o?.asUserTurn ? "user" : "-"}`)),
    prefill: vi.fn((t: string) => void order.push("prefill:" + t)),
    refresh: vi.fn(async () => void order.push("refresh")),
  };
  return { result: executeSlash({ command, sessionId: "s1", gw, callbacks }), callbacks, calls, order };
}

describe("slash.exec directives", () => {
  it("/retry: reloads the rewound transcript, then resends the turn as the user's", async () => {
    const { result, order, calls } = run("/retry", { "slash.exec": { type: "send", message: "explica X" } });
    expect(await result).toBe("sent");
    expect(order).toEqual(["refresh", "send:explica X:user"]);
    expect(calls).toEqual(["slash.exec"]);
  });

  it("/undo: reloads, shows the notice and puts the removed text in the composer", async () => {
    const { result, order } = run("/undo", {
      "slash.exec": { type: "prefill", message: "texto previo", notice: "↶ Undid 1 turn" },
    });
    expect(await result).toBe("done");
    expect(order).toEqual(["refresh", "sys:↶ Undid 1 turn", "prefill:texto previo"]);
  });

  it("/goal: a send directive submits without reloading the view", async () => {
    const { result, order } = run("/goal ship it", {
      "slash.exec": { type: "send", message: "Goal: ship it", notice: "Goal set" },
    });
    expect(await result).toBe("sent");
    expect(order).toEqual(["sys:Goal set", "send:Goal: ship it:-"]);
  });

  it("plain worker output still renders as before", async () => {
    const { result, order } = run("/status", { "slash.exec": { output: "Model: x" } });
    expect(await result).toBe("done");
    expect(order).toEqual(["sys:Model: x"]);
  });

  it("falls back to command.dispatch when slash.exec refuses", async () => {
    const { result, order, calls } = run("/resumen", {
      "slash.exec": new Error("4018: skill command"),
      "command.dispatch": { type: "skill", name: "resumen", message: "SKILL BODY" },
    });
    expect(await result).toBe("sent");
    expect(calls).toEqual(["slash.exec", "command.dispatch"]);
    expect(order).toEqual(["sys:⚡ loading skill: resumen", "send:SKILL BODY:-"]);
  });
});
