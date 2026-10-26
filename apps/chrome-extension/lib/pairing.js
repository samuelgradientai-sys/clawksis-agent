// Pairing string -> connection settings. Pure module: the service worker, the popup and the
// tests (tests-js/chrome-extension-pairing.test.mjs) import it.
//
// The dashboard shows ONE string that carries both where to connect and the device token:
//   clawk-mychrome:<base64url(JSON {"v":1,"u":"https://host[:port][/base]","t":"mc1.<secret>"})>
// The token travels as a WebSocket subprotocol (never in the URL, so it never lands in an
// access log) and the extension only ever connects to the dashboard it was paired with.

export const PAIRING_PREFIX = "clawk-mychrome:";
export const PROTOCOL = "clawk-mychrome.v1";
export const SOCKET_PATH = "/api/my-chrome/connect";

const TOKEN_RE = /^mc1\.[A-Za-z0-9_-]{43}$/;
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

function decodeBase64Url(text) {
  const padded = text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4);
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** The dashboard's base URL (origin + optional path prefix), or throws: https://, or plain
 *  http:// only for this same machine. */
export function dashboardBase(url) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("La dirección del panel no es válida.");
  }
  const secure = parsed.protocol === "https:";
  const loopback = parsed.protocol === "http:" && LOOPBACK_HOSTS.has(parsed.hostname);
  if (!secure && !loopback) {
    throw new Error("El panel tiene que usar https:// (o estar en esta misma compu: localhost).");
  }
  return `${parsed.origin}${parsed.pathname.replace(/\/+$/, "")}`;
}

/** `{ base, token }` from the string the dashboard showed, or throws an Error to show the user. */
export function parsePairing(raw) {
  const text = String(raw ?? "").trim();
  if (!text.startsWith(PAIRING_PREFIX)) {
    throw new Error("Ese no es un código de Mi Chrome. Copialo de nuevo desde el panel.");
  }
  let data;
  try {
    data = JSON.parse(decodeBase64Url(text.slice(PAIRING_PREFIX.length)));
  } catch {
    throw new Error("El código está incompleto. Copialo entero desde el panel.");
  }
  if (!data || data.v !== 1 || typeof data.u !== "string" || typeof data.t !== "string") {
    throw new Error("El código no es de esta versión de Mi Chrome. Generá uno nuevo en el panel.");
  }
  if (!TOKEN_RE.test(data.t)) {
    throw new Error("El código está incompleto. Copialo entero desde el panel.");
  }
  return { base: dashboardBase(data.u), token: data.t };
}

/** The WebSocket URL of the paired dashboard's extension endpoint (wss:// unless loopback). */
export function socketUrl(base) {
  const url = new URL(`${dashboardBase(base)}${SOCKET_PATH}`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

/** Reconnect delay after `failures` consecutive failed attempts: 1s doubling, capped at 30s. */
export function reconnectDelayMs(failures) {
  return Math.min(30000, 1000 * 2 ** Math.max(0, Math.min(failures, 5)));
}
