// Mi Chrome — service worker. Connects OUT to the paired Clawksis dashboard (so it works behind
// NAT, no tunnels) and relays Chrome DevTools Protocol traffic for the user's own tabs through
// chrome.debugger. The dashboard turns that tab-level relay into a browser-level CDP endpoint the
// agent's browser tools drive. Tabs the agent opens land in a "Clawksis" tab group; while a tab is
// attached Chrome shows its own "started debugging this browser" bar, and pressing Cancel there
// pauses Mi Chrome until the user reconnects from the popup.

import { PROTOCOL, parsePairing, reconnectDelayMs, socketUrl } from "./lib/pairing.js";
import { GROUP_TITLE, tabInfo } from "./lib/tabs.js";

const CDP_VERSION = "1.3";
const PING_MS = 20000; // WebSocket traffic keeps an MV3 service worker alive (Chrome 116+)
const ALARM = "clawk-mychrome-reconnect";
// Close codes the dashboard sends after accepting: no automatic reconnect for these.
const FINAL_CLOSES = {
  4401: "El panel revocó este emparejamiento. Generá un código nuevo en Mi Chrome.",
  4403: "Mi Chrome está apagado en el panel. Encendelo y tocá Reconectar.",
  4409: "Otro Chrome se conectó con este mismo código. Tocá Reconectar para volver a usar este.",
};

let socket = null;
let failures = 0;
let reconnectTimer = 0;
let pingTimer = 0;
const attached = new Set();
const attaching = new Map();
const agentGroups = new Set();

// ── status ───────────────────────────────────────────────────────────────────

function setStatus(state, detail = "") {
  void chrome.storage.session.set({ status: { state, detail, at: Date.now() } });
  const [text, color] = { connected: ["ON", "#16a34a"], connecting: ["…", "#d97706"] }[state] ?? ["", "#6b7280"];
  void chrome.action.setBadgeText({ text });
  void chrome.action.setBadgeBackgroundColor({ color });
}

function send(message) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(message));
  }
}

// ── connection ───────────────────────────────────────────────────────────────

async function connect() {
  clearTimeout(reconnectTimer);
  if (socket && socket.readyState <= WebSocket.OPEN) {
    return;
  }
  const { pairing, paused } = await chrome.storage.local.get(["pairing", "paused"]);
  if (!pairing) {
    setStatus("unpaired");
    return;
  }
  if (paused) {
    setStatus("paused", paused === true ? "" : String(paused));
    return;
  }
  setStatus("connecting");
  const ws = new WebSocket(socketUrl(pairing.base), [PROTOCOL, pairing.token]);
  socket = ws;
  ws.onopen = () => {
    failures = 0;
    setStatus("connected", new URL(pairing.base).host);
    startPing();
    void sendHello();
  };
  ws.onmessage = (event) => void onServerMessage(event.data);
  ws.onclose = (event) => {
    if (socket !== ws) {
      return; // closed on purpose: pause, forget or a new pairing
    }
    socket = null;
    stopPing();
    void detachAll();
    void onClosed(event.code);
  };
}

async function onClosed(code) {
  const final = FINAL_CLOSES[code];
  if (final) {
    await chrome.storage.local.set({ paused: final });
    setStatus("paused", final);
    return;
  }
  failures += 1;
  // A refused handshake (bad or revoked code, panel off) reaches the browser as a bare 1006.
  setStatus(
    failures >= 3 ? "error" : "connecting",
    failures >= 3 ? "No se pudo conectar con el panel. ¿Está encendido? Si generaste un código nuevo, pegalo acá." : "",
  );
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => void connect(), reconnectDelayMs(failures));
}

function closeSocket() {
  const ws = socket;
  socket = null;
  stopPing();
  ws?.close(1000);
}

async function pause(detail) {
  await chrome.storage.local.set({ paused: detail || true });
  closeSocket();
  await detachAll();
  setStatus("paused", detail);
}

function startPing() {
  stopPing();
  pingTimer = setInterval(() => send({ type: "ping" }), PING_MS);
}

function stopPing() {
  clearInterval(pingTimer);
}

function productName() {
  const match = /(?:Chrome|Chromium)\/([\d.]+)/.exec(navigator.userAgent);
  return match ? `Chrome/${match[1]}` : "Chrome";
}

async function sendHello() {
  await refreshAgentGroups();
  const tabs = await chrome.tabs.query({});
  send({
    type: "hello",
    version: chrome.runtime.getManifest().version,
    product: productName(),
    userAgent: navigator.userAgent,
    tabs: tabs.map((tab) => tabInfo(tab, agentGroups)),
  });
}

// ── commands from the dashboard ──────────────────────────────────────────────

const COMMANDS = {
  cdp: (msg) => sendCdp(msg),
  attach: (msg) => ensureAttached(msg.tabId),
  detach: (msg) => detach(msg.tabId),
  create_tab: (msg) => createAgentTab(msg.url || "about:blank", msg.active !== false),
  close_tab: (msg) => chrome.tabs.remove(msg.tabId).then(() => ({})),
  activate_tab: (msg) => activateTab(msg.tabId),
};

function cdpError(err) {
  const text = String(err?.message ?? err);
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed.message === "string") {
      return { code: parsed.code ?? -32000, message: parsed.message };
    }
  } catch {
    // chrome.runtime.lastError text that is not a CDP error object
  }
  return { code: -32000, message: text };
}

async function onServerMessage(data) {
  let msg;
  try {
    msg = JSON.parse(data);
  } catch {
    return;
  }
  const run = COMMANDS[msg?.type];
  if (!run || msg.id === undefined) {
    return;
  }
  try {
    send({ type: "result", id: msg.id, result: (await run(msg)) ?? {} });
  } catch (err) {
    send({ type: "error", id: msg.id, error: cdpError(err) });
  }
}

async function ensureAttached(tabId) {
  if (attached.has(tabId)) {
    return {};
  }
  if (!attaching.has(tabId)) {
    const pending = chrome.debugger
      .attach({ tabId }, CDP_VERSION)
      .catch((err) => {
        // A service-worker restart forgets the set while Chrome keeps the attachment.
        if (!/already attached/i.test(String(err?.message ?? err))) {
          throw err;
        }
      })
      .then(() => {
        attached.add(tabId);
      })
      .finally(() => attaching.delete(tabId));
    attaching.set(tabId, pending);
  }
  await attaching.get(tabId);
  return {};
}

async function sendCdp({ tabId, sessionId, method, params }) {
  if (!sessionId) {
    await ensureAttached(tabId);
  }
  const target = sessionId ? { tabId, sessionId } : { tabId };
  return (await chrome.debugger.sendCommand(target, method, params ?? {})) ?? {};
}

async function detach(tabId) {
  if (!attached.delete(tabId)) {
    return {};
  }
  try {
    await chrome.debugger.detach({ tabId });
  } catch {
    // the tab closed or Chrome already detached it
  }
  return {};
}

async function detachAll() {
  await Promise.all([...attached].map((tabId) => detach(tabId)));
}

async function targetWindowId() {
  try {
    return (await chrome.windows.getLastFocused({ windowTypes: ["normal"] })).id;
  } catch {
    return null;
  }
}

async function addToAgentGroup(tab) {
  const [existing] = await chrome.tabGroups.query({ title: GROUP_TITLE, windowId: tab.windowId });
  const groupId = await chrome.tabs.group(
    existing ? { tabIds: [tab.id], groupId: existing.id } : { tabIds: [tab.id], createProperties: { windowId: tab.windowId } },
  );
  agentGroups.add(groupId);
  if (!existing) {
    await chrome.tabGroups.update(groupId, { title: GROUP_TITLE, color: "purple" });
  }
}

async function createAgentTab(url, active) {
  const windowId = await targetWindowId();
  const tab =
    windowId === null
      ? (await chrome.windows.create({ url, focused: active })).tabs[0]
      : await chrome.tabs.create({ url, active, windowId });
  await addToAgentGroup(tab);
  return { tab: tabInfo(await chrome.tabs.get(tab.id), agentGroups) };
}

async function activateTab(tabId) {
  const tab = await chrome.tabs.update(tabId, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true });
  return {};
}

// ── Chrome events → dashboard ────────────────────────────────────────────────

chrome.debugger.onEvent.addListener((source, method, params) => {
  send({ type: "event", tabId: source.tabId, sessionId: source.sessionId, method, params });
});

chrome.debugger.onDetach.addListener((source, reason) => {
  attached.delete(source.tabId);
  send({ type: "detached", tabId: source.tabId, reason });
  if (reason === "canceled_by_user") {
    void pause("Cancelaste la depuración desde Chrome. Tocá Reconectar para que el agente vuelva a usar tus pestañas.");
  }
});

async function refreshAgentGroups() {
  const groups = await chrome.tabGroups.query({ title: GROUP_TITLE });
  agentGroups.clear();
  for (const group of groups) {
    agentGroups.add(group.id);
  }
}

const reportTab = (event, tab) => send({ type: "tab", event, tab: tabInfo(tab, agentGroups) });

chrome.tabs.onCreated.addListener((tab) => reportTab("created", tab));
chrome.tabs.onUpdated.addListener((_tabId, change, tab) => {
  if (change.url !== undefined || change.title !== undefined || change.groupId !== undefined) {
    reportTab("updated", tab);
  }
});
chrome.tabs.onActivated.addListener(({ tabId, windowId }) => send({ type: "tab", event: "activated", tabId, windowId }));
chrome.tabs.onRemoved.addListener((tabId) => {
  attached.delete(tabId);
  send({ type: "tab", event: "removed", tabId });
});
chrome.tabs.onReplaced.addListener((addedTabId, removedTabId) => {
  attached.delete(removedTabId);
  send({ type: "tab", event: "removed", tabId: removedTabId });
  chrome.tabs.get(addedTabId).then((tab) => reportTab("created", tab), () => undefined);
});
for (const groupEvent of [chrome.tabGroups.onCreated, chrome.tabGroups.onUpdated, chrome.tabGroups.onRemoved]) {
  groupEvent.addListener(() => void refreshAgentGroups());
}

// ── popup ────────────────────────────────────────────────────────────────────

async function popupStatus() {
  const [{ status }, { pairing, paused }, tabs] = await Promise.all([
    chrome.storage.session.get("status"),
    chrome.storage.local.get(["pairing", "paused"]),
    chrome.tabs.query({}),
  ]);
  return {
    status: status ?? { state: pairing ? "connecting" : "unpaired", detail: "" },
    host: pairing ? new URL(pairing.base).host : null,
    paused: Boolean(paused),
    tabCount: tabs.length,
  };
}

const POPUP = {
  status: () => popupStatus(),
  pair: async (msg) => {
    const pairing = parsePairing(msg.code);
    closeSocket();
    await detachAll();
    await chrome.storage.local.set({ pairing, paused: false });
    failures = 0;
    await connect();
    return popupStatus();
  },
  disconnect: async () => {
    await pause("");
    return popupStatus();
  },
  reconnect: async () => {
    await chrome.storage.local.set({ paused: false });
    failures = 0;
    await connect();
    return popupStatus();
  },
  forget: async () => {
    closeSocket();
    await detachAll();
    await chrome.storage.local.remove(["pairing", "paused"]);
    setStatus("unpaired");
    return popupStatus();
  },
};

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  const run = sender.id === chrome.runtime.id ? POPUP[msg?.type] : undefined;
  if (!run) {
    return false;
  }
  run(msg).then(reply, (err) => reply({ error: String(err?.message ?? err) }));
  return true;
});

// ── lifecycle ────────────────────────────────────────────────────────────────

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM) {
    void connect();
  }
});
chrome.runtime.onInstalled.addListener(() => void chrome.alarms.create(ALARM, { periodInMinutes: 1 }));
chrome.runtime.onStartup.addListener(() => void connect());
void connect();
