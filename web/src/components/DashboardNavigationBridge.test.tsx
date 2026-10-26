// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { dispatchChatEvent, type ChatEventContext } from "./chat/hooks/chatEvents";
import { DashboardNavigationBridge } from "./DashboardNavigationBridge";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>;
}

const where = () => document.querySelector('[data-testid="where"]')!.textContent;

/** Just enough chat context for the dispatcher; navigation touches none of it. */
const chat = { ids: { liveSid: { current: "live-1" }, selectedKey: { current: null } } } as unknown as ChatEventContext;

const agentOpens = (path: unknown, sid = "live-1") =>
  act(() => dispatchChatEvent(chat, { type: "dashboard.navigate", session_id: sid, payload: { path } }));

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() =>
    root.render(
      <MemoryRouter initialEntries={["/chat"]}>
        <DashboardNavigationBridge />
        <Where />
      </MemoryRouter>,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("the agent's dashboard_open drives the router", () => {
  it("opens the page the open conversation's agent asked for", () => {
    agentOpens("/cron");
    expect(where()).toBe("/cron");

    agentOpens("/skills/dashboards/kronos");
    expect(where()).toBe("/skills/dashboards/kronos");
  });

  it("ignores a conversation that is not on screen", () => {
    agentOpens("/cron", "background-7");
    expect(where()).toBe("/chat");
  });

  it.each(["https://evil.example/x", "//evil.example", "/\\evil", "cron", 42, null])(
    "never leaves the app for %s",
    (path) => {
      agentOpens(path);
      expect(where()).toBe("/chat");
    },
  );
});
