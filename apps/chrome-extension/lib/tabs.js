// Tab facts the dashboard relay needs. Pure module (tested in tests-js).

export const GROUP_TITLE = "Clawksis";

// chrome.debugger cannot attach to browser UI pages, other extensions or the Web Store.
const UNDEBUGGABLE_PREFIXES = [
  "chrome://",
  "chrome-extension://",
  "chrome-untrusted://",
  "chrome-search://",
  "devtools://",
  "edge://",
  "brave://",
  "opera://",
  "vivaldi://",
  "view-source:",
  "https://chrome.google.com/webstore",
  "https://chromewebstore.google.com",
];

export function isDebuggableUrl(url) {
  const text = String(url ?? "");
  return text !== "" && !UNDEBUGGABLE_PREFIXES.some((prefix) => text.startsWith(prefix));
}

/** What the relay is told about one tab; `agentGroups` holds the ids of "Clawksis" tab groups. */
export function tabInfo(tab, agentGroups) {
  return {
    id: tab.id,
    windowId: tab.windowId,
    index: tab.index,
    url: tab.url || tab.pendingUrl || "",
    title: tab.title || "",
    active: Boolean(tab.active),
    agent: tab.groupId !== undefined && tab.groupId !== -1 && agentGroups.has(tab.groupId),
    openerTabId: tab.openerTabId ?? null,
  };
}
