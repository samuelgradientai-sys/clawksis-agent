// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import { dispatchChatEvent, type ChatEventContext } from "../hooks/chatEvents";
import { setSidePanel } from "../sidePanelStore";
import { resetBrowserLiveStore } from "./browserLiveStore";

/** The open side-panel tab, as the store persists it. */
const panel = () => window.localStorage.getItem("clawksis-chat-side-panel");

function chat(selectedKey: string | null) {
  const ctx = {
    setMessages: () => undefined,
    setLiveStatus: () => undefined,
    setBusy: () => undefined,
    setErrorMessage: () => undefined,
    turn: { started: false, submitsInFlight: 0 },
    ids: { liveSid: { current: "live-1" }, selectedKey: { current: selectedKey } },
  } as unknown as ChatEventContext;
  return (name: string) =>
    dispatchChatEvent(ctx, { type: "tool.start", session_id: "live-1", payload: { name, tool_id: name } });
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

  it("respects the user closing it for the rest of that conversation", () => {
    const toolStarts = chat("chat-1");
    toolStarts("browser_navigate");
    setSidePanel(null);
    toolStarts("browser_click");
    expect(panel()).toBeNull();

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
