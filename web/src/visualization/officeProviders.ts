/**
 * Office visual providers — the "Pixel Office" tab is swappable.
 *
 * There are several open-source "agents in a virtual office" visualizers; this
 * registry lets the user pick which one renders the office. Each provider is a
 * standalone web build served as a static iframe under the dashboard.
 *
 * To add another office visual:
 *   1. Drop its standalone build under `web/public/<id>/` (with an index.html).
 *   2. Add an entry here.
 *   3. If it speaks the pixel-agents postMessage protocol (agentCreated /
 *      agentToolStart / agentStatus / subagent*), set `protocol: 'pixel-agents'`
 *      and it gets the live event bridge + layout persistence for free.
 *      Otherwise set `protocol: 'none'` and it renders as a static iframe (it
 *      must source its own data).
 *
 * The selected provider is persisted in localStorage so it sticks across
 * visits.
 */

export type OfficeProtocol = "pixel-agents" | "none";

export interface OfficeProvider {
  id: string;
  label: string;
  /** Path (under CLAWK_BASE_PATH) to the provider's index.html. */
  src: string;
  /** Whether the live gateway→office bridge applies to this provider. */
  protocol: OfficeProtocol;
  /** Short attribution / description shown under the picker. */
  credit?: string;
}

export const OFFICE_PROVIDERS: OfficeProvider[] = [
  {
    id: "pixel-agents",
    label: "Pixel Office",
    src: "/pixel-office/index.html",
    protocol: "pixel-agents",
    credit: "pixel-agents (MIT) · Metro City sprites (CC0)",
  },
  // Example slot for a second visual (uncomment + ship a build to add it):
  // {
  //   id: "my-office",
  //   label: "My Office",
  //   src: "/my-office/index.html",
  //   protocol: "none",
  //   credit: "your attribution here",
  // },
];

export const DEFAULT_OFFICE_PROVIDER_ID = OFFICE_PROVIDERS[0].id;

const STORAGE_KEY = "clawksis.viz.officeProvider";

export function loadOfficeProviderId(): string {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && OFFICE_PROVIDERS.some((p) => p.id === saved)) return saved;
  } catch {
    // localStorage unavailable (private mode / sandbox) — use default.
  }
  return DEFAULT_OFFICE_PROVIDER_ID;
}

export function saveOfficeProviderId(id: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Best-effort persistence.
  }
}

export function getOfficeProvider(id: string): OfficeProvider {
  return OFFICE_PROVIDERS.find((p) => p.id === id) ?? OFFICE_PROVIDERS[0];
}
