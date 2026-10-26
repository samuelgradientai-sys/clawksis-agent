import { describe, expect, it } from "vitest";

import { buildCleanupRequest, parsePruneDays } from "./session-cleanup";

const empty = { source: "", model: "", days: "", maxMessages: "" };

describe("buildCleanupRequest", () => {
  it("refuses a filterless cleanup (the backend would delete by nothing)", () => {
    expect(buildCleanupRequest(empty, true)).toBeNull();
    expect(buildCleanupRequest({ ...empty, model: "   ", days: "abc" }, true)).toBeNull();
  });

  it("sends only the filters that are set, with whole numbers", () => {
    expect(buildCleanupRequest({ ...empty, source: "cron", days: "7" }, false)).toEqual({
      source: "cron",
      older_than_days: 7,
      dry_run: false,
    });
    expect(buildCleanupRequest({ ...empty, maxMessages: "0", model: " gpt " }, true)).toEqual({
      model: "gpt",
      max_messages: 0,
      dry_run: true,
    });
  });
});

describe("parsePruneDays", () => {
  it("accepts whole days >= 1 only", () => {
    expect(parsePruneDays("90")).toBe(90);
    expect(parsePruneDays("0")).toBeNull();
    expect(parsePruneDays("-3")).toBeNull();
    expect(parsePruneDays("1.5")).toBeNull();
  });
});
