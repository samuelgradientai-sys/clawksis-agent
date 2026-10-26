// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import { dispatchChatEvent, type ChatEventContext } from "../hooks/chatEvents";
import { setSidePanel } from "../sidePanelStore";
import { resetBrowserLiveStore } from "./browserLiveStore";

/** The open side-panel tab, as the store persists it. */
const panel = () => window.localStorage.getItem("clawksis-chat-side-panel");

function chatContext(selectedKey: string | null) {
  return {
    setMessages: () => undefined,
    setSession: () => undefined,
    setLiveStatus: () => undefined,
    setBusy: () => undefined,
    setErrorMessage: () => undefined,
    deltas: { push: () => undefined, take: () => "" },
    turn: { started: false, submitsInFlight: 0 },
    ids: { liveSid: { current: "live-1" }, selectedKey: { current: selectedKey } },
  } as unknown as ChatEventContext;
}

function chat(selectedKey: string | null, ctx = chatContext(selectedKey)) {
  return (name: string) =>
    dispatchChatEvent(ctx, { type: "tool.start", session_id: "live-1", payload: { name, tool_id: name } });
}

function endTurn(ctx: ChatEventContext) {
  dispatchChatEvent(ctx, { type: "message.complete", session_id: "live-1", payload: { text: "listo" } });
}

describe("the Navegador panel opens itself when the agent starts browsing", () => {
  beforeEach(() => {
    resetBrowserLiveStore();
    setSidePanel(null);
  });

  it("opens on the first browser tool of a conversation", () => {
    const toolStarts = chat("chat-1");
    toolStarts("terminal");
    expect(panel()).toBeNull();
    toolStarts("browser_navigate");
    expect(panel()).toBe("browser");
  });

  it("opens once per turn: a user close holds until the next turn starts browsing", () => {
    const ctx = chatContext("chat-1");
    const toolStarts = chat("chat-1", ctx);
    toolStarts("browser_navigate");
    setSidePanel(null);
    toolStarts("browser_click");
    expect(panel()).toBeNull();

    endTurn(ctx);
    toolStarts("browser_exec");
    expect(panel()).toBe("browser");
  });

  it("another conversation's first browser tool opens it too", () => {
    chat("chat-1")("browser_navigate");
    setSidePanel(null);
    chat("chat-2")("browser_navigate");
    expect(panel()).toBe("browser");
  });
});

describe("subagents browsing open the panel too", () => {
  beforeEach(() => {
    resetBrowserLiveStore();
    setSidePanel(null);
  });

  it("opens on a subagent's browser tool", () => {
    const ctx = {
      ids: { liveSid: { current: "live-1" }, selectedKey: { current: "chat-9" } },
    } as unknown as ChatEventContext;
    dispatchChatEvent(ctx, { type: "subagent.tool", session_id: "live-1", payload: { tool_name: "web_search" } });
    expect(panel()).toBeNull();
    dispatchChatEvent(ctx, { type: "subagent.tool", session_id: "live-1", payload: { tool_name: "browser_navigate" } });
    expect(panel()).toBe("browser");
  });
});
