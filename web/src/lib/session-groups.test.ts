import { describe, expect, it } from "vitest";

import { groupSessionsByDate } from "./session-groups";

// Local noon on 2026-10-26, so "today" spans the whole local day around it.
const NOW = new Date(2026, 9, 26, 12, 0, 0);
const at = (y: number, m: number, d: number, h = 10) => new Date(y, m, d, h).getTime() / 1000;
const row = (id: string, last_active: number, pinned = false) => ({ id, last_active, started_at: last_active, pinned });

describe("groupSessionsByDate", () => {
  it("buckets by local day of last activity, keeping the list order inside a bucket", () => {
    const groups = groupSessionsByDate(
      [
        row("now", at(2026, 9, 26, 11)),
        row("early-today", at(2026, 9, 26, 0)),
        row("yesterday", at(2026, 9, 25, 23)),
        row("this-week", at(2026, 9, 21)),
        row("this-month", at(2026, 9, 1)),
        row("old", at(2026, 6, 1)),
      ],
      NOW,
    );

    expect(groups.map((g) => [g.key, g.sessions.map((s) => s.id)])).toEqual([
      ["today", ["now", "early-today"]],
      ["yesterday", ["yesterday"]],
      ["week", ["this-week"]],
      ["month", ["this-month"]],
      ["older", ["old"]],
    ]);
  });

  it("puts pinned rows in their own group on top and drops empty groups", () => {
    const groups = groupSessionsByDate([row("a", at(2026, 6, 1)), row("pin", at(2026, 6, 2), true)], NOW);

    expect(groups.map((g) => g.key)).toEqual(["pinned", "older"]);
    expect(groups[0].sessions.map((s) => s.id)).toEqual(["pin"]);
  });

  it("falls back to started_at when a row has no last_active", () => {
    const groups = groupSessionsByDate([{ id: "x", last_active: null, started_at: at(2026, 9, 26, 9) }], NOW);
    expect(groups[0].key).toBe("today");
  });
});
