/** What went wrong in voice mode, in the chat's own words (es-AR voseo). */

export interface VoiceProblem {
  message: string;
  /** The conversation cannot go on (no mic, no STT); otherwise it keeps listening. */
  fatal: boolean;
  /** Fixed in the dashboard's Config page (stt.* / tts.*). */
  configHint: boolean;
}

/** A setup precondition the browser does not meet (no secure context, no API). */
export class VoiceSetupError extends Error {
  readonly reason: "insecure" | "unsupported";

  constructor(reason: "insecure" | "unsupported") {
    super(reason);
    this.name = "VoiceSetupError";
    this.reason = reason;
  }
}

const SETUP_COPY: Record<VoiceSetupError["reason"], string> = {
  insecure:
    "El modo voz necesita el micrófono, y el navegador solo lo habilita en una conexión segura. " +
    "Abrí el dashboard por https:// (o en localhost).",
  unsupported: "Este navegador no permite capturar audio. Probá con Chrome, Edge o Safari actualizados.",
};

const MEDIA_ERROR_COPY: Record<string, string> = {
  NotAllowedError:
    "Permiso de micrófono denegado. Habilitalo para este sitio en la configuración del navegador y volvé a intentar.",
  SecurityError:
    "Permiso de micrófono denegado. Habilitalo para este sitio en la configuración del navegador y volvé a intentar.",
  NotFoundError: "No se encontró ningún micrófono. Conectá uno y volvé a intentar.",
  OverconstrainedError: "No se encontró ningún micrófono. Conectá uno y volvé a intentar.",
  NotReadableError: "El micrófono está ocupado por otra aplicación. Cerrala y volvé a intentar.",
  AbortError: "El micrófono se cortó al iniciar. Volvé a intentar.",
};

// tools/transcription_tools.py / tools/tts_tool.py refusals when nothing is configured.
const STT_MISSING = /no stt provider|stt is disabled/i;
const TTS_MISSING = /no tts provider|tts is disabled/i;

function messageOf(err: unknown): string {
  if (err instanceof Error) return err.message || err.name;
  return typeof err === "string" ? err : String(err);
}

export function describeVoiceError(err: unknown): VoiceProblem {
  if (err instanceof VoiceSetupError) return { message: SETUP_COPY[err.reason], fatal: true, configHint: false };
  const name = err instanceof Error ? err.name : "";
  if (MEDIA_ERROR_COPY[name]) return { message: MEDIA_ERROR_COPY[name], fatal: true, configHint: false };
  const text = messageOf(err);
  if (STT_MISSING.test(text)) {
    return {
      message: "No hay un proveedor de voz a texto (STT) configurado. Elegí uno en Config → stt (por ejemplo groq o local).",
      fatal: true,
      configHint: true,
    };
  }
  if (TTS_MISSING.test(text)) {
    return {
      message:
        "No hay un proveedor de texto a voz (TTS) configurado: las respuestas se muestran como texto. Elegí uno en Config → tts.",
      fatal: false,
      configHint: true,
    };
  }
  return { message: "Voz: " + text, fatal: false, configHint: false };
}

/** Throws when this page cannot capture the microphone at all. */
export function assertCanCapture(): void {
  if (typeof window !== "undefined" && window.isSecureContext === false) throw new VoiceSetupError("insecure");
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new VoiceSetupError(window.isSecureContext ? "unsupported" : "insecure");
  }
}
