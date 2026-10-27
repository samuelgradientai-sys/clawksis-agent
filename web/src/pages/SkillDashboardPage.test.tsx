// @vitest-environment jsdom
// A skill's mini dashboard renders the snapshot the backend serves: stats,
// tables (formatted cells, tone dots), lessons, and a clear empty state
// before the skill's first run.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";
import type { SkillDashboardDetail } from "@/lib/api-skill-dashboards";
import SkillDashboardPage from "./SkillDashboardPage";

const get = vi.fn<(name: string) => Promise<SkillDashboardDetail>>();
vi.mock("@/lib/api-skill-dashboards", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-skill-dashboards")>()),
  skillDashboardsApi: { list: vi.fn(), get: (name: string) => get(name) },
}));

vi.mock("@/lib/api-skill-settings", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-skill-settings")>()),
  skillSettingsApi: { get: vi.fn().mockResolvedValue({ name: "kronos", fields: [] }), save: vi.fn() },
}));

const base: Omit<SkillDashboardDetail, "snapshot" | "error"> = {
  name: "kronos",
  title: "Kronos",
  description: "Trades and lessons",
  category: "finance",
  emoji: "",
  enabled: true,
  modified_at: "",
  snapshot_file: "~/.clawksis/dashboards/kronos.json",
};

let container: HTMLDivElement;
let root: Root;
const setTitle = vi.fn();

async function render() {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () =>
    root.render(
      <I18nProvider>
        <PageHeaderContext.Provider value={{ setTitle, setEnd: () => {}, setAfterTitle: () => {} }}>
          <MemoryRouter initialEntries={["/skills/dashboards/kronos"]}>
            <Routes>
              <Route path="/skills/dashboards/:name" element={<SkillDashboardPage />} />
            </Routes>
          </MemoryRouter>
        </PageHeaderContext.Provider>
      </I18nProvider>,
    ),
  );
}

beforeEach(() => {
  get.mockReset();
  setTitle.mockReset();
  localStorage.setItem("clawk-locale", "en");
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
});

describe("SkillDashboardPage", () => {
  it("renders the snapshot panels", async () => {
    get.mockResolvedValue({
      ...base,
      error: null,
      snapshot: {
        version: 1,
        title: "Kronos",
        subtitle: "eToro demo",
        updated_at: "",
        panels: [
          { id: "s", type: "stats", title: "Today", description: "", width: "full", items: [{ label: "Orders", value: 2, hint: "of 5", tone: "neutral" }] },
          {
            id: "b",
            type: "table",
            title: "Bought",
            description: "",
            width: "half",
            empty: "",
            columns: [
              { key: "symbol", label: "Symbol", align: "left", format: "text" },
              { key: "usd", label: "Amount", align: "right", format: "money" },
            ],
            rows: [{ symbol: "NVDA", usd: 100, _tone: "positive" }],
          },
          { id: "l", type: "list", title: "What it learned", description: "", width: "full", empty: "", items: [{ title: "TSLA: 2/7 right", body: "Don't trade it on the forecast alone.", meta: "", tone: "warning" }] },
        ],
      },
    });
    await render();
    expect(get).toHaveBeenCalledWith("kronos");
    const text = container.textContent ?? "";
    expect(text).toContain("eToro demo");
    expect(text).toContain("Orders");
    expect(text).toContain("NVDA");
    expect(text).toContain("$100.00");
    expect(text).toContain("Don't trade it on the forecast alone.");
    expect(setTitle).toHaveBeenLastCalledWith("Kronos");
  });

  it("explains where the data comes from before the first snapshot", async () => {
    get.mockResolvedValue({ ...base, snapshot: null, error: null });
    await render();
    expect(container.textContent).toContain("hasn't written its dashboard yet");
    expect(container.textContent).toContain("~/.clawksis/dashboards/kronos.json");
  });

  it("shows a broken snapshot as a message, not a blank page", async () => {
    get.mockResolvedValue({ ...base, snapshot: null, error: "the snapshot is not valid JSON" });
    await render();
    expect(container.textContent).toContain("the snapshot is not valid JSON");
  });
});
