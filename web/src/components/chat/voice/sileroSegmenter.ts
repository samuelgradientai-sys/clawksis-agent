/**
 * Neural voice activity detection (Silero VAD v5 on ONNX Runtime wasm, via
 * @ricky0123/vad-web), loaded only when voice mode opens. Every asset comes
 * from this dashboard, never a CDN: the runtime's wasm is a hashed build asset
 * (`?url`), the model and the AudioWorklet are copied to `/voice-vad/` by the
 * Vite build (vite.config.ts `voiceVadAssets`).
 */

import { MicVAD } from "@ricky0123/vad-web";
import ortWasmUrl from "onnxruntime-web/ort-wasm-simd-threaded.wasm?url";
import { CLAWK_BASE_PATH } from "@/lib/api";
import { EnergyGate, SEGMENT_TIMING, type SegmenterOptions } from "./energySegmenter";
import type { SegmenterEvents, SpeechSegmenter } from "./voiceConversation";
import type { VoiceAudioSession } from "./voiceAudio";
import { VAD_SAMPLE_RATE, encodeWav, rms } from "./wav";

const VAD_ASSETS = `${CLAWK_BASE_PATH}/voice-vad/`;
const THRESHOLDS = { positiveSpeechThreshold: 0.5, negativeSpeechThreshold: 0.35 };
/** While the reply plays: surer speech, and loud enough not to be its bleed. */
const PLAYBACK_THRESHOLDS = { positiveSpeechThreshold: 0.8, negativeSpeechThreshold: 0.5 };
const ENERGY_WINDOW = 10; // frames (~320 ms)

/** A root-relative build asset behind a path-prefix proxy. */
const withBase = (url: string) => (url.startsWith("/") ? CLAWK_BASE_PATH + url : url);

export async function createSileroSegmenter(
  audio: VoiceAudioSession,
  options: SegmenterOptions,
  events: SegmenterEvents,
): Promise<SpeechSegmenter> {
  const gate = new EnergyGate(options.bargeInMultiplier);
  const loud: boolean[] = [];
  let playback = false;
  const vad = await MicVAD.new({
    model: "v5",
    baseAssetPath: VAD_ASSETS,
    onnxWASMBasePath: VAD_ASSETS,
    ortConfig: (ort) => {
      ort.env.logLevel = "error";
      // No cross-origin isolation here, so no SharedArrayBuffer threads.
      ort.env.wasm.numThreads = 1;
      ort.env.wasm.wasmPaths = { wasm: withBase(ortWasmUrl) };
    },
    audioContext: audio.context,
    getStream: async () => audio.stream,
    pauseStream: async () => undefined,
    resumeStream: async (stream) => stream,
    startOnLoad: false,
    ...THRESHOLDS,
    redemptionMs: options.silenceMs,
    preSpeechPadMs: SEGMENT_TIMING.preSpeechPadMs,
    minSpeechMs: SEGMENT_TIMING.minSpeechMs,
    submitUserSpeechOnPause: false,
    onFrameProcessed: (_probabilities, frame) => {
      loud.push(gate.isSpeech(rms(frame)));
      if (loud.length > ENERGY_WINDOW) loud.shift();
    },
    onSpeechRealStart: () => {
      const loudFrames = loud.filter(Boolean).length;
      if (!playback || loudFrames * 2 >= loud.length) events.onSpeechStart();
    },
    onSpeechEnd: (samples) => events.onSpeechEnd(encodeWav(samples, VAD_SAMPLE_RATE)),
  });
  try {
    await vad.start();
  } catch (err) {
    await vad.destroy();
    throw err;
  }
  return {
    setPaused: (paused) => void (paused ? vad.pause() : vad.start()),
    setPlaybackActive: (active) => {
      playback = active;
      gate.setPlaybackActive(active);
      vad.setOptions(active ? PLAYBACK_THRESHOLDS : THRESHOLDS);
    },
    destroy: () => void vad.destroy(),
  };
}
