// Pure helpers for the "Mi Chrome" page: what the status means and how a tab is labelled.

import type { MyChromeStatus, MyChromeTab } from "@/lib/api-my-chrome";
import { fill, type MyChromeCopy } from "./copy";

export type MyChromeState = "connected" | "waiting" | "unpaired" | "off";

export interface StatusView {
  state: MyChromeState;
  label: string;
  detail: string;
  /** Tailwind class for the status dot. */
  dot: string;
}

const DOTS: Record<MyChromeState, string> = {
  connected: "bg-emerald-400 motion-safe:animate-pulse",
  waiting: "bg-amber-400",
  unpaired: "bg-muted-foreground/50",
  off: "bg-muted-foreground/50",
};

export function myChromeState(status: MyChromeStatus): MyChromeState {
  if (!status.enabled) return "off";
  if (status.connected) return "connected";
  return status.paired ? "waiting" : "unpaired";
}

function clock(epochSeconds: number, locale: string): string {
  return new Date(epochSeconds * 1000).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" });
}

/** The status pill and the line under it. */
export function statusView(status: MyChromeStatus, copy: MyChromeCopy, locale = "es"): StatusView {
  const state = myChromeState(status);
  const labels: Record<MyChromeState, [string, string]> = {
    connected: [
      copy.statusConnected,
      fill(copy.connectedDetail, {
        browser: status.browser ?? "Chrome",
        time: status.connected_at ? clock(status.connected_at, locale) : "—",
      }),
    ],
    waiting: [copy.statusWaiting, copy.waitingDetail],
    unpaired: [copy.statusUnpaired, copy.unpairedDetail],
    off: [copy.statusOff, copy.offDetail],
  };
  const [label, detail] = labels[state];
  return { state, label, detail, dot: DOTS[state] };
}

export function hostOf(url: string): string {
  try {
    return new URL(url).host || url;
  } catch {
    return url;
  }
}

/** Badges for one tab, most telling first. */
export function tabBadges(tab: MyChromeTab, copy: MyChromeCopy): string[] {
  const badges: Array<[boolean, string]> = [
    [tab.attached, copy.tabAttached],
    [tab.agent, copy.tabAgent],
    [tab.active, copy.tabActive],
  ];
  return badges.filter(([on]) => on).map(([, label]) => label);
}
