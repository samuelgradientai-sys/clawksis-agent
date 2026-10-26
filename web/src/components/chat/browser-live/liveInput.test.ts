import { describe, expect, it } from "vitest";
import { actionLabel, keyboardEvent, mouseEvent, pickSession, toViewport } from "./liveInput";

const meta = { deviceWidth: 1280, deviceHeight: 720 };

describe("pointer → page coordinates over a letterboxed frame", () => {
  it("maps the image box to viewport pixels", () => {
    const box = { left: 100, top: 50, width: 640, height: 360 };
    expect(toViewport(100, 50, box, meta)).toEqual({ x: 0, y: 0 });
    expect(toViewport(420, 230, box, meta)).toEqual({ x: 640, y: 360 });
  });

  it("accounts for the letterbox and ignores clicks on it", () => {
    // 640×640 box: the 16:9 frame is 640×360, centred with 140px bands above and below.
    const box = { left: 0, top: 0, width: 640, height: 640 };
    expect(toViewport(320, 320, box, meta)).toEqual({ x: 640, y: 360 });
    expect(toViewport(320, 100, box, meta)).toBeNull();
  });
});

describe("input events match agent-browser's stream protocol", () => {
  const plain = { altKey: false, ctrlKey: false, metaKey: false, shiftKey: true };

  it("sends text only on keyDown of printable keys, with modifier bits", () => {
    expect(keyboardEvent("keyDown", { ...plain, key: "a", code: "KeyA" })).toMatchObject({
      type: "input_keyboard",
      eventType: "keyDown",
      text: "a",
      windowsVirtualKeyCode: 65,
      modifiers: 8,
    });
    expect(keyboardEvent("keyUp", { ...plain, key: "a", code: "KeyA" }).text).toBeUndefined();
    expect(keyboardEvent("keyDown", { ...plain, key: "Enter", code: "Enter" }).text).toBeUndefined();
  });

  it("counts a click only on press", () => {
    const e = { ...plain, button: 0 };
    expect(mouseEvent("mousePressed", { x: 1, y: 2 }, e)).toMatchObject({ button: "left", clickCount: 1 });
    expect(mouseEvent("mouseReleased", { x: 1, y: 2 }, e).clickCount).toBe(0);
  });
});

describe("which session to watch", () => {
  const sessions = [{ task_id: "old" }, { task_id: "chat-7" }, { task_id: "newest" }];

  it("prefers the open conversation, else the most recent browser", () => {
    expect(pickSession(sessions, "chat-7")).toBe("chat-7");
    expect(pickSession(sessions, "gone")).toBe("newest");
    expect(pickSession([], "chat-7")).toBeNull();
  });

  it("recognises the conversation's profile-scoped and local-sidecar browsers", () => {
    const scoped = [{ task_id: "chat-7@a1b2::local" }, { task_id: "chat-70" }];
    expect(pickSession(scoped, "chat-7")).toBe("chat-7@a1b2::local");
  });
});

it("labels the agent's browser tools in Spanish, passing unknown ones through", () => {
  expect(actionLabel("browser_click")).toBe("Hace clic");
  expect(actionLabel("browser_exec")).toBe("Ejecuta un paso en el navegador");
  expect(actionLabel("browser_new_thing")).toBe("new_thing");
});
