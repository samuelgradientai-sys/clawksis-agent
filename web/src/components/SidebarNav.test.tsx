// @vitest-environment jsdom
// The Plugins ("Complementos") group gathers everything that extends the
// agent: Skills, each enabled skill's mini dashboard right under it, MCP,
// and plugin tabs at the end.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { Cpu, MessageSquare, Package, Plug, Puzzle, Star } from "lucide-react";

import { I18nProvider } from "@/i18n";
import { en } from "@/i18n/en";
import type { SkillDashboardSummary } from "@/lib/api-skill-dashboards";
import { SidebarNav, type NavItem } from "./SidebarNav";

const dashboards: SkillDashboardSummary[] = [];
vi.mock("@/hooks/useSkillDashboards", () => ({ useSkillDashboards: () => dashboards }));

const core: NavItem[] = [
  { path: "/sessions", label: "Sessions", icon: MessageSquare },
  { path: "/models", label: "Models", icon: Cpu },
  { path: "/skills", label: "Skills", icon: Package },
  { path: "/plugins", label: "Plugins", icon: Puzzle },
  { path: "/mcp", label: "MCP", icon: Plug },
];
const pluginTabs: NavItem[] = [{ path: "/achievements", label: "Achievements", icon: Star }];

function board(name: string, title: string, enabled = true): SkillDashboardSummary {
  return { name, title, enabled, description: "", category: "finance", emoji: "", modified_at: "", snapshot_file: "" };
}

let container: HTMLDivElement;
let root: Root;

async function render(collapsed = false) {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () =>
    root.render(
      <I18nProvider>
        <MemoryRouter initialEntries={["/skills/dashboards/kronos"]}>
          <SidebarNav
            closeMobile={() => {}}
            collapsed={collapsed}
            coreItems={core}
            pluginItems={pluginTabs}
            t={en}
            tooltipWarmRef={{ current: 0 }}
          />
        </MemoryRouter>
      </I18nProvider>,
    ),
  );
}

const links = () => [...container.querySelectorAll("a")].map((a) => a.getAttribute("href"));

beforeEach(() => {
  localStorage.clear();
  dashboards.splice(0, dashboards.length, board("kronos", "Kronos"), board("old", "Old", false));
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
});

describe("SidebarNav", () => {
  it("puts enabled skill dashboards under Skills inside the Plugins group", async () => {
    await render();
    expect(links()).toEqual([
      "/sessions",
      "/models",
      "/plugins",
      "/skills",
      "/skills/dashboards/kronos",
      "/mcp",
      "/achievements",
    ]);
    const active = container.querySelector('a[aria-current="page"]');
    expect(active?.getAttribute("href")).toBe("/skills/dashboards/kronos");
  });

  it("lists every entry flat when the sidebar is collapsed", async () => {
    await render(true);
    expect(links()).toContain("/skills/dashboards/kronos");
    expect(links()).not.toContain("/skills/dashboards/old");
    expect(links()).toContain("/achievements");
  });
});
