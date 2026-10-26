// "Mi Chrome" API (clawk_cli/web_routers/my_chrome.py): the agent drives the user's own Chrome
// through a paired extension. Status, the on/off switch and pairing are per profile, so these
// routes ride the management-profile scope like every other profile-owned family.

import { CLAWK_BASE_PATH, authedFetch, fetchJSON } from "./api";
import { apiErrorFromResponse } from "./api-error";

export interface MyChromeTab {
  id: string;
  title: string;
  url: string;
  /** Chrome is showing it (the active tab of its window). */
  active: boolean;
  /** The agent opened it (it sits in the "Clawksis" tab group). */
  agent: boolean;
  /** The agent is attached to it right now. */
  attached: boolean;
}

export interface MyChromeStatus {
  enabled: boolean;
  /** The user asked to approve every payment (off: the agent pays what they asked for). */
  confirm_payments: boolean;
  paired: boolean;
  paired_at: number | null;
  connected: boolean;
  /** An agent driver sent a command in the last few seconds (the live view does not count). */
  active: boolean;
  connected_at: number | null;
  browser: string | null;
  extension_version: string | null;
  tabs: MyChromeTab[];
}

export interface MyChromeActivity {
  connected: boolean;
  active: boolean;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

/** The dashboard as this browser reaches it: what the extension will connect back to. */
export function dashboardUrl(): string {
  return `${window.location.origin}${CLAWK_BASE_PATH}`;
}

export const myChromeApi = {
  status: () => fetchJSON<MyChromeStatus>("/api/my-chrome/status"),
  activity: () => fetchJSON<MyChromeActivity>("/api/my-chrome/activity"),
  /** The user's switches; omitted ones keep their value. */
  saveSettings: (settings: { enabled?: boolean; confirm_payments?: boolean }) =>
    fetchJSON<MyChromeStatus>("/api/my-chrome/settings", {
      method: "PUT",
      headers: JSON_HEADERS,
      body: JSON.stringify(settings),
    }),
  pair: () =>
    fetchJSON<{ pairing: string }>("/api/my-chrome/pairing", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ url: dashboardUrl() }),
    }),
  revoke: () => fetchJSON<{ revoked: boolean }>("/api/my-chrome/pairing", { method: "DELETE" }),
  async extensionZip(): Promise<Blob> {
    const res = await authedFetch("/api/my-chrome/extension.zip");
    if (!res.ok) throw apiErrorFromResponse(res.status, await res.text().catch(() => ""), res.url);
    return res.blob();
  },
};
