/**
 * Voice mode settings, read from the profile's `voice.*` config (`/api/config`)
 * against `/api/config/defaults`: `/api/config` merges the defaults in, so a
 * key the user never touched arrives with the backend default, and only a value
 * that differs from it overrides the web voice loop's own tuning.
 */

export type VoiceChatMode = "chained" | "gpt-live";

/** `voice.stop_phrases`: the built-in list, the user's own list, or off (`[]`). */
export type StopPhraseConfig =
  | { mode: "default" }
  | { mode: "custom"; phrases: readonly string[] }
  | { mode: "disabled" };

export interface VoiceSettings {
  /** `voice.barge_in`: talking over the reply interrupts it (on unless false). */
  bargeIn: boolean;
  /** `voice.barge_in_grace_seconds`: no barge-in right after the reply starts. */
  bargeInGraceMs: number;
  /** `voice.barge_in_threshold_multiplier`; null = the stock sensitivity. */
  bargeInMultiplier: number | null;
  /** End-of-turn silence (`voice.silence_duration` when the user changed it). */
  silenceMs: number;
  stopPhrases: StopPhraseConfig;
  /** `voice.voice_chat_mode`. */
  chatMode: VoiceChatMode;
}

type ConfigPayload = Record<string, unknown> | null | undefined;

/** The backend default `voice.silence_duration` (3 s) is the CLI's push-to-talk
 *  hold; a conversation answers after a natural pause. */
const WEB_SILENCE_MS = 1_000;
const BACKEND_SILENCE_SECONDS = 3;
const BACKEND_GRACE_SECONDS = 0.5;
const BACKEND_STOP_PHRASES: readonly string[] = ["stop"];

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  bargeIn: true,
  bargeInGraceMs: BACKEND_GRACE_SECONDS * 1_000,
  bargeInMultiplier: null,
  silenceMs: WEB_SILENCE_MS,
  stopPhrases: { mode: "default" },
  chatMode: "chained",
};

function voiceSection(config: ConfigPayload): Record<string, unknown> {
  const voice = config?.voice;
  return voice && typeof voice === "object" ? (voice as Record<string, unknown>) : {};
}

/** A positive finite number, or null (`true` from a YAML typo is not 1). */
function positiveNumber(raw: unknown): number | null {
  const value = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw) : NaN;
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** Like the backend's `_load_voice_stop_phrases`: a bare string is one phrase,
 *  non-text entries are skipped, anything else means "default" (null). */
function phraseList(raw: unknown): string[] | null {
  const list = typeof raw === "string" ? [raw] : Array.isArray(raw) ? raw : null;
  return (
    list
      ?.filter((entry) => typeof entry === "string" || typeof entry === "number")
      .map((entry) => String(entry).trim())
      .filter(Boolean) ?? null
  );
}

function stopPhraseConfig(config: ConfigPayload, defaults: ConfigPayload): StopPhraseConfig {
  const phrases = phraseList(voiceSection(config).stop_phrases);
  if (phrases === null) return { mode: "default" };
  if (phrases.length === 0) return { mode: "disabled" };
  const base = phraseList(voiceSection(defaults).stop_phrases) ?? BACKEND_STOP_PHRASES;
  const same = phrases.length === base.length && phrases.every((p, i) => p.toLowerCase() === base[i].toLowerCase());
  return same ? { mode: "default" } : { mode: "custom", phrases };
}

export function voiceSettingsFromConfig(config: ConfigPayload, defaults?: ConfigPayload): VoiceSettings {
  const voice = voiceSection(config);
  const silence = positiveNumber(voice.silence_duration);
  const defaultSilence = positiveNumber(voiceSection(defaults).silence_duration) ?? BACKEND_SILENCE_SECONDS;
  const grace = typeof voice.barge_in_grace_seconds === "number" ? voice.barge_in_grace_seconds : NaN;
  const mode = String(voice.voice_chat_mode ?? "").trim().toLowerCase().replace(/_/g, "-");
  return {
    bargeIn: voice.barge_in !== false,
    bargeInGraceMs: Number.isFinite(grace) && grace >= 0 ? grace * 1_000 : DEFAULT_VOICE_SETTINGS.bargeInGraceMs,
    bargeInMultiplier: positiveNumber(voice.barge_in_threshold_multiplier),
    silenceMs: silence !== null && silence !== defaultSilence ? silence * 1_000 : WEB_SILENCE_MS,
    stopPhrases: stopPhraseConfig(config, defaults),
    chatMode: ["gpt-live", "gptlive", "live"].includes(mode) ? "gpt-live" : "chained",
  };
}

// ── Spoken stop phrases ─────────────────────────────────────────────────────

/** Built-in list while `voice.stop_phrases` is the backend default: Spanish
 *  first (this dashboard's users), then the desktop's English set. Only a WHOLE
 *  utterance matches, so "pará el contenedor" still goes to the agent. */
const BUILTIN_STOP_PHRASES: readonly string[] = [
  "basta",
  "pará",
  "para",
  "detente",
  "detenete",
  "silencio",
  "chau",
  "chao",
  "adiós",
  "hasta luego",
  "terminar",
  "terminamos",
  "fin de la conversación",
  "eso es todo",
  "nada más",
  "cancelar",
  "stop",
  "stop listening",
  "that's all",
  "never mind",
  "goodbye",
  "bye",
  "cancel",
];

const ADDRESS_PREFIXES: readonly string[] = ["hey clawk", "clawk", "clawksis", "ok", "okay", "oye", "che"];

/** NFKC, lowercase, punctuation of any script → space ("¡Basta!" = "basta"). */
function normalizePhrase(text: string): string {
  return text
    .normalize("NFKC")
    .toLowerCase()
    .replace(/\p{P}+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function withoutAddress(text: string): string {
  const prefix = ADDRESS_PREFIXES.find((p) => text.startsWith(p + " "));
  return prefix ? text.slice(prefix.length + 1).trim() : text;
}

const BUILTIN_NORMALIZED = BUILTIN_STOP_PHRASES.map(normalizePhrase);

/** True when the whole transcript is a stop command (optionally "clawk, …"). */
export function isStopPhrase(transcript: string, config: StopPhraseConfig): boolean {
  if (config.mode === "disabled") return false;
  const phrases = config.mode === "custom" ? config.phrases.map(normalizePhrase) : BUILTIN_NORMALIZED;
  const said = normalizePhrase(transcript);
  return !!said && (phrases.includes(said) || phrases.includes(withoutAddress(said)));
}
