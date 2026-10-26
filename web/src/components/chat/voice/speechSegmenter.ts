/** Picks the voice activity detector: Silero (neural, loaded on demand) when
 *  the browser can run it, the energy detector otherwise. */

import { createEnergySegmenter, type SegmenterOptions } from "./energySegmenter";
import type { SegmenterEvents, SpeechSegmenter, VoiceEngine } from "./voiceConversation";
import type { VoiceAudioSession } from "./voiceAudio";

export async function createSpeechSegmenter(
  audio: VoiceAudioSession,
  options: SegmenterOptions,
  events: SegmenterEvents,
): Promise<{ segmenter: SpeechSegmenter; engine: VoiceEngine }> {
  try {
    const { createSileroSegmenter } = await import("./sileroSegmenter");
    return { segmenter: await createSileroSegmenter(audio, options, events), engine: "silero" };
  } catch (err) {
    console.warn("[voice] Silero VAD unavailable, falling back to the energy detector", err);
    return { segmenter: createEnergySegmenter(audio, options, events), engine: "energy" };
  }
}
