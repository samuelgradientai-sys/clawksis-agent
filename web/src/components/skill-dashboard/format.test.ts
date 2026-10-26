import { describe, expect, it } from "vitest";
import { formatCell, relativeTime } from "./format";

describe("formatCell", () => {
  it("formats numbers by column format", () => {
    expect(formatCell(50.5, "money", "en")).toBe("$50.50");
    expect(formatCell(12.345, "percent", "en")).toBe("12.3%");
    expect(formatCell("7", "number", "en")).toBe("7");
    expect(formatCell(1234.5, "number", "en")).toBe("1,234.5");
  });

  it("keeps empty, boolean and unparseable cells readable", () => {
    expect(formatCell(null, "money", "en")).toBe("—");
    expect(formatCell("", "text", "en")).toBe("—");
    expect(formatCell(true, "text", "en")).toBe("✓");
    expect(formatCell("n/a", "money", "en")).toBe("n/a");
    expect(formatCell("not a date", "datetime", "en")).toBe("not a date");
  });

  it("renders ISO timestamps as local dates", () => {
    expect(formatCell("2026-10-26T14:31:00Z", "datetime", "en")).toMatch(/Oct 26, 2026/);
  });
});

describe("relativeTime", () => {
  const now = Date.parse("2026-10-26T15:00:00Z");

  it("describes the past in the largest whole unit", () => {
    expect(relativeTime("2026-10-26T14:55:00Z", "en", now)).toBe("5 minutes ago");
    expect(relativeTime("2026-10-24T15:00:00Z", "en", now)).toBe("2 days ago");
  });

  it("reads a writer clock that runs ahead as now, and bad input as empty", () => {
    expect(relativeTime("2026-10-26T15:03:00Z", "en", now)).toBe("now");
    expect(relativeTime("", "en", now)).toBe("");
    expect(relativeTime("yesterday", "en", now)).toBe("");
  });
});
