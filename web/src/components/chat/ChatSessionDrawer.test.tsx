// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("./SessionSidebar", () => ({
  SessionSidebar: (props: { onSelectSession: (id: string) => void; onNewChat: () => void }) => (
    <aside data-testid="list">
      <button type="button" onClick={() => props.onSelectSession("s-2")}>
        Conversación 2
      </button>
      <button type="button" onClick={() => props.onNewChat()}>
        Nueva
      </button>
    </aside>
  ),
}));

import { ChatDrawerButton, ChatSessionDrawer } from "./ChatSessionDrawer";

function mockViewport(phone: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: phone && query.includes("max-width"),
    media: query,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  })) as unknown as typeof window.matchMedia;
}

let host: HTMLDivElement;
let root: Root;
const onSelectSession = vi.fn();
const onNewChat = vi.fn();

function render() {
  const props = {
    sessions: [],
    projects: [],
    activeSessionId: null,
    activeBusy: false,
    loading: false,
    error: null,
    onSelectSession,
    onNewChat,
    onNewChatInProject: vi.fn(),
    onCreateProject: vi.fn(),
    onConfigureProject: vi.fn(),
    onDeleteSession: vi.fn(),
    onMoveSessionToProject: vi.fn(),
    onRenameSession: vi.fn(),
  } as unknown as Parameters<typeof ChatSessionDrawer>[0];
  act(() => {
    root.render(
      <>
        <ChatDrawerButton />
        <ChatSessionDrawer {...props} />
      </>,
    );
  });
}

const drawer = () => document.querySelector('[data-testid="list"]')!.parentElement!;
const click = (label: string) =>
  act(() => {
    [...document.querySelectorAll("button")].find((b) => b.textContent === label || b.getAttribute("aria-label") === label)!.click();
  });

beforeEach(() => {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  onSelectSession.mockReset();
  onNewChat.mockReset();
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("conversation list on a phone", () => {
  it("is a drawer: closed until the header button opens it", () => {
    mockViewport(true);
    render();
    expect(drawer().className).toContain("invisible");
    click("Conversaciones");
    expect(drawer().className).toContain("visible translate-x-0");
    expect(document.querySelector('[aria-label="Cerrar conversaciones"]')).not.toBeNull();
  });

  it("closes when a conversation is picked or a new one started", () => {
    mockViewport(true);
    render();
    click("Conversaciones");
    click("Conversación 2");
    expect(onSelectSession).toHaveBeenCalledWith("s-2");
    expect(drawer().className).toContain("invisible");
    click("Conversaciones");
    click("Nueva");
    expect(onNewChat).toHaveBeenCalled();
    expect(drawer().className).toContain("invisible");
  });

  it("closes on Escape and on a tap outside", () => {
    mockViewport(true);
    render();
    click("Conversaciones");
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(drawer().className).toContain("invisible");
    click("Conversaciones");
    click("Cerrar conversaciones");
    expect(drawer().className).toContain("invisible");
  });
});

describe("conversation list on a wide screen", () => {
  it("stays inline beside the chat, with no overlay", () => {
    mockViewport(false);
    render();
    expect(host.querySelector('[data-testid="list"]')).not.toBeNull();
    expect(document.querySelector('[aria-label="Cerrar conversaciones"]')).toBeNull();
  });
});
