// Copy for "Mi Chrome" (Spanish, rioplatense voseo like the rest of the dashboard).

export const myChromeCopy = {
  pageTitle: "Mi Chrome",
  heroTitle: "Tu agente, en tu propio Chrome",
  heroBody:
    "El agente corre en tu VPS, pero con Mi Chrome usa el Chrome de tu compu: tus pestañas abiertas y tus cuentas con sesión iniciada. Pedile «reservame un pasaje a Cancún» y lo hace solo, pago incluido; después te muestra qué compró, cuánto pagó y el comprobante.",
  enabledLabel: "Activado",
  enabledHint: "Apagado, el panel rechaza la extensión y el agente usa el navegador del VPS.",
  loadWhat: "el estado de Mi Chrome",
  // status
  statusConnected: "Conectado",
  statusWaiting: "Esperando la extensión",
  statusUnpaired: "Sin emparejar",
  statusOff: "Apagado",
  connectedDetail: "{browser} · desde las {time}",
  waitingDetail: "Abrí la extensión en tu Chrome y tocá Reconectar si hace falta.",
  unpairedDetail: "Seguí los pasos de abajo para conectar tu Chrome.",
  offDetail: "Encendelo para que el agente pueda usar tu Chrome.",
  // setup
  setupTitle: "Conectalo en 4 pasos",
  step1Title: "Descargá la extensión",
  step1Body: "Descomprimí el .zip en una carpeta que no vayas a borrar.",
  step1Action: "Descargar extensión",
  step2Title: "Cargala en Chrome",
  step2Body:
    "Abrí chrome://extensions (también sirve Edge o Brave), activá «Modo de desarrollador», tocá «Cargar descomprimida» y elegí la carpeta clawksis-mi-chrome.",
  step3Title: "Generá el código de emparejamiento",
  step3Body: "Es como una contraseña: no lo compartas.",
  step3Action: "Generar código",
  step3Again: "Generar otro código",
  step3Once: "Se muestra una sola vez. Si lo perdés, generá otro: el anterior deja de funcionar.",
  step3Copy: "Copiar código",
  step3Copied: "¡Copiado!",
  step3Paired: "Ya hay un Chrome emparejado (desde {date}). Generar otro código lo reemplaza.",
  step4Title: "Pegalo en la extensión",
  step4Body: "Tocá el ícono de Mi Chrome en la barra de Chrome, pegá el código y tocá «Conectar».",
  // tabs
  tabsTitle: "Pestañas que ve el agente",
  tabsEmpty: "Cuando la extensión esté conectada, vas a ver acá tus pestañas.",
  tabsNone: "No hay pestañas que el agente pueda usar (las páginas chrome:// no cuentan).",
  tabAgent: "Del agente",
  tabActive: "En pantalla",
  tabAttached: "En uso",
  // payments
  paymentsTitle: "Pagos",
  confirmLabel: "Pedirme confirmación antes de pagar",
  paymentsAutonomous:
    "Apagado: el agente completa solo las compras, pagos y reservas que le pedís, y al terminar te muestra qué compró, el monto, el comercio, el código de confirmación y una captura del comprobante.",
  paymentsConfirm:
    "Encendido: antes del pago final frena, te muestra el resumen (qué, total, fechas, pasajeros) y espera tu «sí».",
  paymentsOwner: "Este ajuste es solo tuyo: el agente lo lee, nunca lo cambia.",
  paymentsInjection:
    "Solo gasta en lo que vos le pedís: nunca paga, agrega tarjetas, cambia datos de tu cuenta o de envío ni transfiere plata porque una página, un mail o un documento se lo pida.",
  paymentsAuth:
    "Si tu banco pide un código (3-D Secure, SMS) o la tarjeta pide el CVV, te lo pregunta por el chat, lo usa una vez y no lo guarda.",
  // safety
  safetyTitle: "Seguridad y límites",
  safetyStop:
    "Mientras usa una pestaña, Chrome muestra una barra avisando que «Clawksis — Mi Chrome» está depurando el navegador. Tocá «Cancelar» ahí, o «Desconectar» en la extensión, para frenarlo al instante.",
  safetyTabs: "Las pestañas que abre quedan en el grupo «Clawksis». Nunca cierra las tuyas.",
  safetyLimits:
    "No puede usar páginas chrome:// ni la Chrome Web Store, ni ventanas de incógnito. Tu compu tiene que estar prendida con Chrome abierto.",
  revoke: "Revocar emparejamiento",
  revokeTitle: "Revocar el emparejamiento",
  revokeBody: "La extensión se desconecta y su código deja de funcionar. Para volver a usarla, generá uno nuevo.",
  revoked: "Emparejamiento revocado",
  // errors
  toggleFailed: "No pude cambiar Mi Chrome",
  pairFailed: "No pude generar el código",
  revokeFailed: "No pude revocar el emparejamiento",
  downloadFailed: "No pude descargar la extensión",
  // browser panel
  panelHint: "¿Querés que use tu propio Chrome, con tus sesiones iniciadas?",
  panelLink: "Conectá Mi Chrome",
  badgeMyChrome: "Usando tu Chrome",
  badgeServer: "Navegador del servidor",
  // activity pill (any dashboard page)
  pillText: "El agente está usando tu Chrome",
  pillAction: "Ver en vivo",
  pillDismiss: "Ocultar aviso",
} as const;

export type MyChromeCopy = typeof myChromeCopy;

/** `fill("desde {time}", { time: "10:00" })` → "desde 10:00". */
export function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => values[key] ?? match);
}
