/** Voice mode's calls to the dashboard backend (clawk_cli/web_routers/audio.py),
 *  all on the dashboard's own auth like every other `/api/*` route. */

import { api, buildWsUrl, fetchJSON } from "@/lib/api";
import type { SpeechSocket } from "./replySpeech";
import { voiceSettingsFromConfig, DEFAULT_VOICE_SETTINGS, type VoiceSettings } from "./voiceSettings";
import { blobToDataUrl } from "./wav";

/** Warm-up lease name on the server's STT / TTS engines. */
export const VOICE_LEASE = "web:voice-conversation";

type RpcSender = (method: string, params?: Record<string, unknown>) => Promise<unknown>;

const JSON_POST = { method: "POST", headers: { "Content-Type": "application/json" } } as const;

export async function transcribeUtterance(audio: Blob): Promise<string> {
  const result = await api.transcribeAudio(await blobToDataUrl(audio), audio.type || "audio/wav");
  return result.transcript ?? "";
}

function dataUrlBytes(dataUrl: string): ArrayBuffer {
  const binary = atob(dataUrl.slice(dataUrl.indexOf(",") + 1));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

/** One sentence through the server's TTS provider chain (`POST /api/audio/speak`). */
export async function synthesizeSentence(text: string): Promise<ArrayBuffer> {
  const result = await fetchJSON<{ data_url: string }>("/api/audio/speak", {
    ...JSON_POST,
    body: JSON.stringify({ text }),
  });
  return dataUrlBytes(result.data_url);
}

export async function openSpeakSocket(): Promise<SpeechSocket> {
  return new WebSocket(await buildWsUrl("/api/audio/speak-stream"));
}

/** Warm the local STT/TTS models for the conversation, release them after. */
export function setVoiceLeases(active: boolean): void {
  for (const path of ["/api/audio/stt-lease", "/api/audio/tts-lease"]) {
    fetchJSON(path, { ...JSON_POST, body: JSON.stringify({ lease: VOICE_LEASE, active }), keepalive: !active }).catch(
      (err: unknown) => console.warn("[voice] lease update failed", path, err),
    );
  }
}

export async function loadVoiceSettings(): Promise<VoiceSettings> {
  try {
    const [config, defaults] = await Promise.all([api.getConfig(), api.getDefaults().catch(() => null)]);
    return voiceSettingsFromConfig(config, defaults);
  } catch (err) {
    console.warn("[voice] could not read voice.* config, using defaults", err);
    return DEFAULT_VOICE_SETTINGS;
  }
}

/** False only when the backend says no STT provider can run (`stt.enabled:
 *  false`, unknown provider); an older backend or a failed probe says nothing. */
export async function sttAvailable(sendRpc: RpcSender): Promise<boolean> {
  try {
    const status = (await sendRpc("voice.toggle", { action: "status" })) as { stt_available?: boolean } | null;
    return status?.stt_available !== false;
  } catch {
    return true;
  }
}
