/** Agent-driven page changes: the `dashboard_open` tool emits a `dashboard.navigate` gateway event
 * on the open chat's socket; the chat relays it on `window` and the router bridge follows it. */

export const DASHBOARD_NAVIGATE_EVENT = "clawk:dashboard-navigate";

/** An in-app route such as "/cron", or null for anything else (absolute URL, "//host", junk). */
export function dashboardRoute(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const path = raw.trim();
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) {
    return null;
  }
  return path;
}

/** Re-broadcast a `dashboard.navigate` payload on `window` for the router bridge. */
export function relayDashboardNavigate(payload: Record<string, unknown>): void {
  const path = dashboardRoute(payload.path);
  if (path) {
    window.dispatchEvent(
      new CustomEvent(DASHBOARD_NAVIGATE_EVENT, { detail: path }),
    );
  }
}
