// Mi Chrome popup: paste the pairing code once, see whether the agent can reach your tabs, and
// disconnect at any time. All state lives in the service worker (background.js).

const STATES = {
  connected: ["Conectado", "on"],
  connecting: ["Conectando…", "wait"],
  paused: ["Desconectado", "off"],
  error: ["Desconectado", "off"],
  unpaired: ["Sin emparejar", "off"],
};

const $ = (id) => document.getElementById(id);

function showError(message) {
  $("error").textContent = message || "";
  $("error").hidden = !message;
}

function detailFor(info) {
  const { state, detail } = info.status;
  if (detail && state !== "connected") {
    return detail;
  }
  if (state === "connected") {
    return "El agente puede ver y usar tus pestañas abiertas, y completar las compras que le pidas (después te muestra el comprobante). Para aprobar cada pago, activá «Pedirme confirmación antes de pagar» en el panel.";
  }
  if (state === "paused") {
    return "Pausado: el agente no puede usar tus pestañas.";
  }
  return "Conectando con tu panel…";
}

function render(info) {
  const [label, tone] = STATES[info.status.state] ?? STATES.connecting;
  $("pill").textContent = label;
  $("pill").className = `pill ${tone}`;
  $("host").textContent = info.host ?? "Clawksis";
  $("pair").hidden = Boolean(info.host);
  $("paired").hidden = !info.host;
  if (!info.host) {
    return;
  }
  $("detail").textContent = detailFor(info);
  const connected = info.status.state === "connected";
  $("tabs").textContent = connected ? `Pestañas abiertas en este Chrome: ${info.tabCount}.` : "";
  $("disconnectBtn").hidden = !connected && info.paused;
  $("reconnectBtn").hidden = connected;
}

async function call(type, extra = {}) {
  const result = await chrome.runtime.sendMessage({ type, ...extra });
  if (result?.error) {
    throw new Error(result.error);
  }
  return result;
}

async function act(type, extra) {
  showError("");
  try {
    render(await call(type, extra));
  } catch (err) {
    showError(err.message);
  }
}

$("pairBtn").addEventListener("click", () => void act("pair", { code: $("code").value }));
$("disconnectBtn").addEventListener("click", () => void act("disconnect"));
$("reconnectBtn").addEventListener("click", () => void act("reconnect"));
$("forgetBtn").addEventListener("click", () => void act("forget"));
chrome.storage.session.onChanged.addListener(() => void act("status"));
void act("status");
