// @vitest-environment jsdom

import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setChatMode } from "@/components/chat/hooks/useChatMode";
import { setSidePanel } from "@/components/chat/sidePanelStore";
import { shouldShowPill } from "./activity";
import { MyChromeActivityPill } from "./MyChromeActivityPill";

const activity = vi.fn();
vi.mock("@/lib/api-my-chrome", () => ({ myChromeApi: { activity: () => activity() } }));
vi.mock("@/contexts/useProfileScope", () => ({ useProfileScope: () => ({ profile: "default" }) }));

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
const seen = { path: "" };

function Where() {
  const { pathname } = useLocation();
  useEffect(() => {
    seen.path = pathname;
  }, [pathname]);
  return null;
}

async function mount(at: string) {
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[at]}>
        <MyChromeActivityPill />
        <Where />
      </MemoryRouter>,
    );
  });
  await act(async () => Promise.resolve());
}

const pill = () => host.querySelector('[role="status"]');

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  setSidePanel(null);
  setChatMode("terminal");
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  activity.mockReset();
});

describe("the 'El agente está usando tu Chrome' pill", () => {
  it("shows on another page while the agent drives the user's Chrome and opens the live view", async () => {
    activity.mockResolvedValue({ connected: true, active: true });
    await mount("/cron");
    expect(pill()?.textContent).toContain("El agente está usando tu Chrome");

    const open = [...host.querySelectorAll("button")].find((b) => b.textContent === "Ver en vivo");
    await act(async () => open?.click());

    expect(seen.path).toBe("/chat");
    expect(window.localStorage.getItem("clawksis-chat-side-panel")).toBe("browser");
    expect(window.localStorage.getItem("clawksis:chat-mode")).toBe("modern");
    expect(pill()).toBeNull(); // the live view is on screen now
  });

  it("stays away while the agent is not using it", async () => {
    activity.mockResolvedValue({ connected: true, active: false });
    await mount("/cron");
    expect(pill()).toBeNull();
  });
});

describe("shouldShowPill", () => {
  const base = { active: true, dismissed: false, pathname: "/skills", chatMode: "modern" as const };

  it("shows on other pages, never on the modern chat (its panel is one tap away), not once dismissed", () => {
    expect(shouldShowPill(base)).toBe(true);
    expect(shouldShowPill({ ...base, pathname: "/chat" })).toBe(false);
    expect(shouldShowPill({ ...base, pathname: "/chat", chatMode: "terminal" })).toBe(true);
    expect(shouldShowPill({ ...base, dismissed: true })).toBe(false);
    expect(shouldShowPill({ ...base, active: false })).toBe(false);
  });
});
