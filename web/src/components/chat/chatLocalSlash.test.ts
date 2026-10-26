import { describe, expect, it } from "vitest";
import { localSlashAction } from "./chatLocalSlash";

describe("slash commands the page answers itself", () => {
  it("/new, /reset and /clear start a new conversation (with or without a skip token)", () => {
    for (const cmd of ["/new", "/new now", "/reset", "/CLEAR", "/new Mi tema"]) {
      expect(localSlashAction(cmd, false)).toBe("new-chat");
    }
  });

  it("/model alone opens the picker; with an argument it goes to the gateway", () => {
    expect(localSlashAction("/model", false)).toBe("model-picker");
    expect(localSlashAction("/model opus", false)).toBeNull();
  });

  it("/stop interrupts only while a turn runs", () => {
    expect(localSlashAction("/stop", true)).toBe("interrupt");
    expect(localSlashAction("/stop", false)).toBeNull();
  });

  it("everything else is not local", () => {
    expect(localSlashAction("/retry", false)).toBeNull();
    expect(localSlashAction("hola /new", false)).toBeNull();
  });
});
