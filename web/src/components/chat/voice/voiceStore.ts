/**
 * Whether voice mode is open, outside ChatModern: the composer's start button
 * opens it, the overlay (mounted once) renders it. Opening also starts the
 * audio inside the tap itself (voiceAudio.beginVoiceAudio), which iOS needs.
 */

import { useSyncExternalStore } from "react";
import { beginVoiceAudio, releaseVoiceAudio, type PendingVoiceAudio } from "./voiceAudio";
import { describeVoiceError, type VoiceProblem } from "./voiceErrors";

export interface VoiceModeState {
  open: boolean;
  /** The conversation's audio, begun in the opening tap (null if that failed). */
  audio: PendingVoiceAudio | null;
  /** Why it could not even start (no HTTPS, no Web Audio). */
  problem: VoiceProblem | null;
}

const CLOSED: VoiceModeState = { open: false, audio: null, problem: null };
let state: VoiceModeState = CLOSED;
const listeners = new Set<() => void>();

function set(next: VoiceModeState): void {
  state = next;
  listeners.forEach((listener) => listener());
}

/** Call from the click/tap handler (not an effect): see voiceAudio. */
export function openVoiceMode(): void {
  if (state.open) return;
  try {
    set({ open: true, audio: beginVoiceAudio(), problem: null });
  } catch (err) {
    set({ open: true, audio: null, problem: describeVoiceError(err) });
  }
}

export function closeVoiceMode(): void {
  if (!state.open) return;
  if (state.audio) releaseVoiceAudio(state.audio);
  set(CLOSED);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useVoiceMode(): VoiceModeState {
  return useSyncExternalStore(subscribe, () => state, () => CLOSED);
}
