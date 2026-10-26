import { describe, expect, it } from "vitest";
import type { TodayConversation, TodayFile } from "@/lib/api-today";
import {
  boldSegments,
  budgetGroups,
  buildTimeline,
  clock,
  dailyCron,
  dailyTime,
  defaultDeliver,
  dayRelation,
  filesPageLink,
  groupFilesByProject,
  isoDay,
  isValidDay,
  parseSummary,
  shiftDay,
  timeSpan,
} from "./today-model";

function file(path: string, project: string, lastAt: number, extra: Partial<TodayFile> = {}): TodayFile {
  return {
    path,
    project,
    in_repo: true,
    action: "edited",
    count: 1,
    first_at: lastAt,
    last_at: lastAt,
    session_id: "s",
    ...extra,
  };
}

describe("calendar days", () => {
  it("names the viewer's day, not the server's", () => {
    // 02:30 UTC on the 27th is still the 26th in Buenos Aires (UTC-3).
    const instant = new Date(Date.UTC(2026, 9, 27, 2, 30));
    expect(isoDay(instant, "America/Argentina/Buenos_Aires")).toBe("2026-10-26");
    expect(isoDay(instant, "UTC")).toBe("2026-10-27");
  });

  it("steps across month, year and DST boundaries", () => {
    expect(shiftDay("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftDay("2026-12-31", 1)).toBe("2027-01-01");
    expect(shiftDay("2026-03-08", 1)).toBe("2026-03-09");
  });

  it("validates YYYY-MM-DD and relates days to today", () => {
    expect(isValidDay("2026-02-30")).toBe(false);
    expect(isValidDay("26/10/2026")).toBe(false);
    expect(isValidDay("2026-10-26")).toBe(true);
    expect(dayRelation("2026-10-26", "2026-10-26")).toBe("today");
    expect(dayRelation("2026-10-25", "2026-10-26")).toBe("yesterday");
    expect(dayRelation("2026-10-01", "2026-10-26")).toBe("past");
    expect(dayRelation("2026-10-27", "2026-10-26")).toBe("future");
  });

  it("formats clock times in the given zone", () => {
    const ts = Date.UTC(2026, 9, 26, 12, 5) / 1000;
    expect(clock(ts, "UTC", "es")).toBe("12:05");
    expect(clock(ts, "America/Argentina/Buenos_Aires", "es")).toBe("09:05");
    expect(timeSpan(ts, ts + 20, "UTC", "es")).toBe("12:05");
    expect(timeSpan(ts, ts + 1800, "UTC", "es")).toBe("12:05–12:35");
  });
});

describe("groupFilesByProject", () => {
  it("buckets files by project, most recently touched project and file first", () => {
    const groups = groupFilesByProject([
      file("/w/app/src/a.ts", "/w/app", 10),
      file("/w/site/index.html", "/w/site", 30),
      file("/w/app/README.md", "/w/app", 20),
      file("/tmp/notas.txt", "/tmp", 5, { in_repo: false }),
    ]);
    expect(groups.map((g) => [g.name, g.files.map((f) => f.rel)])).toEqual([
      ["site", ["index.html"]],
      ["app", ["README.md", "src/a.ts"]],
      ["tmp", ["notas.txt"]],
    ]);
    expect(groups[2].inRepo).toBe(false);
  });

  it("spends a row budget across groups in order", () => {
    const groups = groupFilesByProject([
      file("/a/1", "/a", 9),
      file("/a/2", "/a", 8),
      file("/b/1", "/b", 7),
      file("/c/1", "/c", 6),
    ]);
    expect(budgetGroups(groups, 3).map((g) => [g.group.name, g.limit])).toEqual([
      ["a", 2],
      ["b", 1],
    ]);
    expect(budgetGroups(groups, Infinity)).toHaveLength(3);
  });

  it("links a file to its folder in the Files page", () => {
    expect(filesPageLink("/w/app/src/a.ts")).toBe("/files?path=%2Fw%2Fapp%2Fsrc");
  });
});

describe("buildTimeline", () => {
  const conversation = { id: "c1", started_at: 100 } as TodayConversation;

  it("merges every kind of event oldest first, a conversation before what it caused", () => {
    const items = buildTimeline({
      conversations: [conversation],
      cron_runs: [{ execution_id: "e1", at: 50 } as never],
      commits: [{ sha: "abc", repo: "/r", at: 100 } as never],
      skills: [{ name: "kronos", at: 100 } as never],
      cron_jobs_created: [],
      dashboards: [{ name: "kronos", at: 300 } as never],
    });
    expect(items.map((i) => i.kind)).toEqual(["cron", "conversation", "skill", "commit", "dashboard"]);
    expect(new Set(items.map((i) => i.key)).size).toBe(items.length);
  });
});

describe("parseSummary", () => {
  it("splits a headline from its bullets", () => {
    expect(parseSummary("## Arreglé el login\n\n- Edité **auth.py**\n* Corrí los tests\n1. Commit")).toEqual({
      headline: "Arreglé el login",
      bullets: ["Edité **auth.py**", "Corrí los tests", "Commit"],
    });
  });

  it("keeps a bullets-only reply without inventing a headline", () => {
    expect(parseSummary("- uno\n- dos")).toEqual({ headline: "", bullets: ["uno", "dos"] });
    expect(parseSummary("   ")).toEqual({ headline: "", bullets: [] });
  });

  it("marks bold runs", () => {
    expect(boldSegments("Edité **auth.py** y **db.py**")).toEqual([
      { text: "Edité ", bold: false },
      { text: "auth.py", bold: true },
      { text: " y ", bold: false },
      { text: "db.py", bold: true },
    ]);
  });
});

describe("dailyCron", () => {
  it("turns HH:MM into a daily cron expression", () => {
    expect(dailyCron("22:00")).toBe("0 22 * * *");
    expect(dailyCron("7:05")).toBe("5 7 * * *");
    expect(dailyCron("24:00")).toBeNull();
    expect(dailyCron("noche")).toBeNull();
  });

  it("delivers to the first messaging platform with a home channel, never Bot Chat by default", () => {
    const local = { id: "local", home_target_set: true };
    const origin = { id: "origin", home_target_set: true };
    const botChat = { id: "bot-chat:default", home_target_set: true };
    expect(defaultDeliver([local, origin, botChat])).toBe("origin");
    expect(defaultDeliver([local, { id: "discord", home_target_set: false }, { id: "telegram", home_target_set: true }, botChat])).toBe(
      "telegram",
    );
  });

  it("reads a daily expression back as a time, and nothing else", () => {
    expect(dailyTime("0 22 * * *")).toBe("22:00");
    expect(dailyTime("5 7 * * *")).toBe("07:05");
    expect(dailyTime("0 22 * * 1-5")).toBeNull();
    expect(dailyTime(undefined)).toBeNull();
  });
});
