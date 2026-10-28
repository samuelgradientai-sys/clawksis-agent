// @vitest-environment jsdom
// Finanzas gathers every finance skill: dashboards as tabs (the first one by
// default, or the one in the URL) and the other finance skills listed below.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";
import type { SkillDashboardSummary } from "@/lib/api-skill-dashboards";
import type { SkillInfo } from "@/lib/api";
import FinancePage from "./FinancePage";

const dashboards: SkillDashboardSummary[] = [];
const skills: SkillInfo[] = [];
vi.mock("@/hooks/useSkillDashboards", () => ({ useSkillDashboards: () => dashboards }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: { getSkills: () => Promise.resolve(skills) },
}));
vi.mock("./SkillDashboardPage", () => ({
  SkillDashboardView: ({ name }: { name: string }) => <div data-testid="board">{name}</div>,
}));

function board(name: string, title: string, category = "finance"): SkillDashboardSummary {
  return { name, title, enabled: true, description: "", category, emoji: "", modified_at: "", snapshot_file: "" };
}

let container: HTMLDivElement;
let root: Root;
const setTitle = vi.fn();

async function render(path = "/finanzas") {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () =>
    root.render(
      <I18nProvider>
        <PageHeaderContext.Provider value={{ setTitle, setEnd: () => {}, setAfterTitle: () => {} }}>
          <MemoryRouter initialEntries={[path]}>
            <Routes>
              <Route path="/finanzas" element={<FinancePage />} />
              <Route path="/finanzas/:name" element={<FinancePage />} />
            </Routes>
          </MemoryRouter>
        </PageHeaderContext.Provider>
      </I18nProvider>,
    ),
  );
}

const shown = () => container.querySelector('[data-testid="board"]')?.textContent;

beforeEach(() => {
  localStorage.setItem("clawk-locale", "es");
  dashboards.splice(0, dashboards.length, board("kronos", "Kronos"), board("cartera", "Cartera"), board("notes", "Notes", "productivity"));
  skills.splice(
    0,
    skills.length,
    { name: "kronos", description: "Pronósticos y trading", category: "finance", enabled: true },
    { name: "stocks", description: "Cotizaciones de Yahoo", category: "finance", enabled: false },
    { name: "notes", description: "Notas", category: "productivity", enabled: true },
  );
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
});

describe("FinancePage", () => {
  it("opens the first finance dashboard and offers the others as tabs", async () => {
    await render();
    expect(shown()).toBe("kronos");
    const tabs = [...container.querySelectorAll('[role="tab"]')].map((t) => t.textContent);
    expect(tabs).toEqual(["Kronos", "Cartera"]);
    expect(setTitle).toHaveBeenLastCalledWith("Finanzas");
  });

  it("opens the dashboard named in the URL", async () => {
    await render("/finanzas/cartera");
    expect(shown()).toBe("cartera");
  });

  it("lists the finance skills without a dashboard", async () => {
    await render();
    const text = container.textContent ?? "";
    expect(text).toContain("Otras skills de finanzas");
    expect(text).toContain("stocks");
    expect(text).not.toContain("Notas");
  });
});
