/**
 * Fallback voice activity detection when the Silero model cannot load (old
 * browser, blocked wasm): mic energy against a calibrated quiet-room floor,
 * the desktop's approach. Same events as the neural VAD (segmentTracker), and
 * the same playback-phase clamp, so speaker bleed alone cannot pass for speech.
 */

import { SegmentTracker } from "./segmentTracker";
import type { SegmenterEvents, SpeechSegmenter } from "./voiceConversation";
import type { VoiceAudioSession } from "./voiceAudio";
import { FrameResampler, VAD_SAMPLE_RATE, encodeWav, rms } from "./wav";

export interface SegmenterOptions {
  silenceMs: number;
  /** `voice.barge_in_threshold_multiplier` (null = stock). */
  bargeInMultiplier: number | null;
}

const FRAME_SAMPLES = 512; // 32 ms at 16 kHz, Silero v5's frame
const FRAME_MS = (FRAME_SAMPLES / VAD_SAMPLE_RATE) * 1_000;
// Float RMS levels with the browser's AGC + noise suppression on.
const MIN_TRIGGER = 0.015;
const FLOOR_MULTIPLIER = 3.5;
const PLAYBACK_MIN_TRIGGER = 0.04;
const TRIGGER_CEILING = 0.15;
/** The backend's default `voice.barge_in_threshold_multiplier`, which the levels above assume. */
const DEFAULT_MULTIPLIER = 3;
const FLOOR_SAMPLES = 90; // ~3 s of quiet frames

export const SEGMENT_TIMING = { preSpeechPadMs: 400, minSpeechMs: 250, maxSpeechMs: 30_000 };

/** Speech/not-speech per frame against an ambient floor learned from quiet frames. */
export class EnergyGate {
  private floor: number[] = [];
  private playback = false;
  private readonly scale: number;

  constructor(multiplier: number | null) {
    this.scale = multiplier && multiplier > 0 ? multiplier / DEFAULT_MULTIPLIER : 1;
  }

  setPlaybackActive(active: boolean): void {
    this.playback = active;
  }

  isSpeech(level: number): boolean {
    const sorted = [...this.floor].sort((a, b) => a - b);
    const median = sorted[sorted.length >> 1] ?? 0;
    let trigger = Math.max(MIN_TRIGGER, median * FLOOR_MULTIPLIER * this.scale);
    // While the reply plays the floor is held and the trigger clamped up (bleed
    // must not trip it) but capped, so a real voice can always interrupt.
    if (this.playback) trigger = Math.min(Math.max(trigger, PLAYBACK_MIN_TRIGGER * this.scale), TRIGGER_CEILING);
    const speech = level >= trigger;
    if (!speech && !this.playback) {
      this.floor.push(level);
      if (this.floor.length > FLOOR_SAMPLES) this.floor.shift();
    }
    return speech;
  }
}

export function createEnergySegmenter(
  audio: VoiceAudioSession,
  options: SegmenterOptions,
  events: SegmenterEvents,
): SpeechSegmenter {
  const { context } = audio;
  const gate = new EnergyGate(options.bargeInMultiplier);
  const tracker = new SegmentTracker({ frameMs: FRAME_MS, redemptionMs: options.silenceMs, ...SEGMENT_TIMING });
  const resampler = new FrameResampler(context.sampleRate, FRAME_SAMPLES);
  // ScriptProcessor (not a worklet): available everywhere, including old iOS.
  const tap = context.createScriptProcessor(2048, 1, 1);
  const sink = context.createGain();
  sink.gain.value = 0; // a processor only runs when connected to the destination
  let paused = false;

  tap.onaudioprocess = (ev) => {
    if (paused) return;
    for (const frame of resampler.push(ev.inputBuffer.getChannelData(0))) {
      for (const event of tracker.push(frame, gate.isSpeech(rms(frame)))) {
        if (event.type === "confirmed") events.onSpeechStart();
        else if (event.type === "end") events.onSpeechEnd(encodeWav(event.audio, VAD_SAMPLE_RATE));
      }
    }
  };
  audio.micSource.connect(tap);
  tap.connect(sink);
  sink.connect(context.destination);

  return {
    setPaused: (value) => {
      paused = value;
      if (value) tracker.reset();
    },
    setPlaybackActive: (active) => gate.setPlaybackActive(active),
    destroy: () => {
      tap.onaudioprocess = null;
      audio.micSource.disconnect(tap);
      tap.disconnect();
      sink.disconnect();
    },
  };
}
