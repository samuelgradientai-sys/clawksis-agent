// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  getSessions: vi.fn(),
  getSessionMessages: vi.fn(),
  getEmptySessionsCount: vi.fn(),
  getStatus: vi.fn(),
  searchSessions: vi.fn(),
  setSessionFlags: vi.fn(),
  getProfiles: vi.fn(),
  getActiveProfile: vi.fn(),
  getSessionStats: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiMocks,
  setManagementProfile: vi.fn(),
  getManagementProfile: vi.fn(() => ""),
}));
vi.mock("@/components/PlatformsCard", () => ({ PlatformsCard: () => null }));

let container: HTMLDivElement;
let root: Root;
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

async function waitFor(cond: () => boolean, timeoutMs = 5000) {
  const start = Date.now();
  while (!cond()) {
    if (Date.now() - start > timeoutMs) throw new Error("waitFor: condition never became true");
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
  }
}

const text = () => document.body.textContent ?? "";
const button = (label: string) => document.querySelector(`button[aria-label="${label}"]`);
const now = Date.now() / 1000;

function row(id: string, lastActive: number, extra: Record<string, unknown> = {}) {
  return {
    id, profile: "work", source: "cli", model: null, title: `Title ${id}`, started_at: lastActive, ended_at: lastActive,
    last_active: lastActive, is_active: false, message_count: 2, tool_call_count: 0, input_tokens: 1,
    output_tokens: 1, preview: "p", ...extra,
  };
}

async function renderPage() {
  const [{ default: SessionsPage }, { I18nProvider }, { SystemActionsProvider }, { ProfileProvider }, { PageHeaderProvider }] =
    await Promise.all([
      import("./SessionsPage"),
      import("@/i18n"),
      import("@/contexts/SystemActions"),
      import("@/contexts/ProfileProvider"),
      import("@/contexts/PageHeaderProvider"),
    ]);
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () =>
    root.render(
      <I18nProvider>
        <MemoryRouter>
          <SystemActionsProvider>
            <ProfileProvider>
              <PageHeaderProvider pluginTabs={[]}>
                <SessionsPage />
              </PageHeaderProvider>
            </ProfileProvider>
          </SystemActionsProvider>
        </MemoryRouter>
      </I18nProvider>,
    ),
  );
}

beforeEach(() => {
  for (const fn of Object.values(apiMocks)) fn.mockReset();
  apiMocks.getStatus.mockResolvedValue({});
  apiMocks.getEmptySessionsCount.mockResolvedValue({ count: 0 });
  apiMocks.getProfiles.mockResolvedValue({ profiles: [] });
  apiMocks.getActiveProfile.mockResolvedValue({ current: "default", active: "default" });
  apiMocks.getSessionStats.mockResolvedValue({ total: 3, active_store: 2, archived: 1, messages: 6, by_source: { cli: 3 } });
  apiMocks.setSessionFlags.mockResolvedValue({ ok: true });
  vi.stubGlobal("ResizeObserver", class { disconnect() {} observe() {} unobserve() {} });
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => cb(0), 0) as unknown as number);
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id));
  vi.stubGlobal("matchMedia", () => ({ addEventListener() {}, matches: false, media: "", removeEventListener() {} }));
});

afterEach(async () => {
  await act(async () => root?.unmount());
  container?.remove();
  vi.unstubAllGlobals();
});

describe("Sessions page organization", () => {
  it("groups the history by day of last activity, newest activity first", async () => {
    apiMocks.getSessions.mockImplementation(async (limit: number) => ({
      sessions: limit >= 50 ? [] : [row("today", now - 60), row("old", now - 90 * 86400)],
      total: limit >= 50 ? 0 : 2,
      limit,
      offset: 0,
    }));
    await renderPage();
    await waitFor(() => text().includes("Title today"));

    expect(text()).toContain("Today");
    expect(text()).toContain("Older");
    expect(text().indexOf("Today")).toBeLessThan(text().indexOf("Older"));
    // The list asks for recent-activity order so the groups are coherent.
    expect(apiMocks.getSessions.mock.calls.some(([limit, , opts]) => limit === 20 && opts.order === "recent")).toBe(true);
  });

  it("shows a load failure as an error with a retry, not as an empty store", async () => {
    apiMocks.getSessions.mockRejectedValue(new Error("Session store is busy"));
    await renderPage();
    await waitFor(() => Boolean(document.querySelector('[role="alert"]')));

    expect(text()).toContain("Session store is busy");
    expect(text()).not.toContain("No sessions yet");
  });

  it("archives a row through its owning profile and lists archived sessions on demand", async () => {
    apiMocks.getSessions.mockImplementation(async (limit: number, _offset: number, opts: { archived?: string }) => ({
      sessions: limit >= 50 ? [] : opts.archived === "only" ? [row("arch", now - 60, { archived: true })] : [row("live", now - 60)],
      total: limit >= 50 ? 0 : 1,
      limit,
      offset: 0,
    }));
    await renderPage();
    await waitFor(() => Boolean(button("Archive")));

    await act(async () => button("Archive")!.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(apiMocks.setSessionFlags).toHaveBeenCalledWith("live", { archived: true }, "work");

    const archivedToggle = Array.from(document.querySelectorAll("button[aria-pressed]")).find((b) => b.textContent === "Archived");
    await act(async () => archivedToggle!.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await waitFor(() => text().includes("Title arch"));
    expect(button("Restore from archive")).not.toBeNull();
  });
});
