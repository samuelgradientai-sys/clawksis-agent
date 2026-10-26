// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentCursor } from "./AgentCursor";
import type { LiveBrowser } from "./useLiveBrowser";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
const meta = { deviceWidth: 1280, deviceHeight: 720 };

function show(cursor: LiveBrowser["cursor"]) {
  act(() => root.render(<AgentCursor cursor={cursor} meta={meta} />));
  return host.querySelector<HTMLElement>('[data-testid="agent-cursor"]');
}

beforeEach(() => {
  vi.useFakeTimers();
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.useRealTimers();
});

describe("the agent's cursor over the live frame", () => {
  it("sits where the agent's pointer landed, as a share of the page", () => {
    const el = show({ kind: "click", x: 640, y: 180, at: 1 });
    expect(el?.style.left).toBe("50%");
    expect(el?.style.top).toBe("25%");
    expect(el?.textContent).toContain("Agente");
  });

  it("says it is typing when keys land in a field", () => {
    expect(show({ kind: "type", x: 10, y: 10, at: 2 })?.textContent).toContain("Escribiendo");
  });

  it("fades out once the agent has been still for a while", () => {
    expect(show({ kind: "move", x: 10, y: 10, at: 3 })).not.toBeNull();
    act(() => vi.advanceTimersByTime(4000));
    expect(host.querySelector('[data-testid="agent-cursor"]')).toBeNull();
  });
});
