import { describe, expect, it } from "vitest";

import type { LogFileInfo } from "./api-logs";
import { isNearBottom, logFileOptions } from "./log-files";

const file = (name: string, exists: boolean): LogFileInfo => ({
  name,
  filename: `${name}.log`,
  exists,
  size: exists ? 10 : null,
  mtime: exists ? 1 : null,
  root_home: false,
});

describe("logFileOptions", () => {
  it("offers the core logs always and any other log only once it exists", () => {
    const inventory = [file("agent", true), file("errors", false), file("gateway", false), file("gui", true), file("mcp", false)];

    expect(logFileOptions(inventory, "agent")).toEqual(["agent", "errors", "gateway", "gui"]);
  });

  it("keeps a deep-linked selection visible even before that log exists", () => {
    expect(logFileOptions([file("agent", true), file("mcp", false)], "mcp")).toEqual(["agent", "mcp"]);
    expect(logFileOptions(null, "update")).toEqual(["agent", "errors", "gateway", "update"]);
  });
});

describe("isNearBottom", () => {
  it("follows the tail only when the reader is at the bottom", () => {
    expect(isNearBottom({ scrollTop: 600, scrollHeight: 1000, clientHeight: 400 })).toBe(true);
    expect(isNearBottom({ scrollTop: 100, scrollHeight: 1000, clientHeight: 400 })).toBe(false);
  });
});
