/**
 * The audio side of one voice conversation: ONE AudioContext (mic analysis,
 * VAD and reply playback all run on it) and the microphone stream.
 *
 * `beginVoiceAudio` must run synchronously inside the tap that opens voice
 * mode: iOS Safari only lets a context created/resumed in a user gesture make
 * sound, and asking for the mic in the same gesture keeps the permission
 * prompt attached to it. Everything after that may be async.
 */

import { assertCanCapture } from "./voiceErrors";

/** Echo cancellation keeps the reply out of the mic; the rest is what makes a
 *  phone in a noisy room usable. */
const MIC_CONSTRAINTS: MediaStreamConstraints = {
  audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
};

export interface PendingVoiceAudio {
  context: AudioContext;
  mic: Promise<MediaStream>;
}

export interface VoiceAudioSession {
  context: AudioContext;
  stream: MediaStream;
  /** The mic as an audio node (VAD input). */
  micSource: MediaStreamAudioSourceNode;
  /** Where reply audio goes (metered, then the speakers). */
  output: AudioNode;
  micLevel(): number;
  outputLevel(): number;
  close(): void;
}

type AudioContextCtor = typeof AudioContext;

function audioContextCtor(): AudioContextCtor | null {
  const w = window as unknown as { AudioContext?: AudioContextCtor; webkitAudioContext?: AudioContextCtor };
  return w.AudioContext ?? w.webkitAudioContext ?? null;
}

/** Call from the click/tap handler itself. Throws a VoiceSetupError when the
 *  page cannot capture audio (no HTTPS, no API). */
export function beginVoiceAudio(): PendingVoiceAudio {
  assertCanCapture();
  const Ctor = audioContextCtor();
  if (!Ctor) throw new DOMException("Web Audio no disponible", "NotSupportedError");
  // Safari 17+: one session that both records and plays, on the loudspeaker.
  const session = (navigator as unknown as { audioSession?: { type: string } }).audioSession;
  if (session) session.type = "play-and-record";
  const context = new Ctor();
  void context.resume();
  // A silent sample started inside the gesture unlocks output on older iOS.
  const unlock = context.createBufferSource();
  unlock.buffer = context.createBuffer(1, 1, context.sampleRate);
  unlock.connect(context.destination);
  unlock.start();
  const mic = navigator.mediaDevices.getUserMedia(MIC_CONSTRAINTS);
  // The rejection is handled where it is awaited; keep it from surfacing as unhandled first.
  mic.catch(() => undefined);
  return { context, mic };
}

function levelMeter(analyser: AnalyserNode): () => number {
  const data = new Float32Array(analyser.fftSize);
  return () => {
    analyser.getFloatTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
    return Math.sqrt(sum / data.length);
  };
}

export async function finishVoiceAudio(pending: PendingVoiceAudio): Promise<VoiceAudioSession> {
  const { context } = pending;
  const stream = await pending.mic;
  if (context.state === "suspended") await context.resume().catch(() => undefined);
  const micSource = context.createMediaStreamSource(stream);
  const micAnalyser = context.createAnalyser();
  micAnalyser.fftSize = 1024;
  micSource.connect(micAnalyser);
  const output = context.createGain();
  const outputAnalyser = context.createAnalyser();
  outputAnalyser.fftSize = 1024;
  output.connect(outputAnalyser);
  outputAnalyser.connect(context.destination);
  return {
    context,
    stream,
    micSource,
    output,
    micLevel: levelMeter(micAnalyser),
    outputLevel: levelMeter(outputAnalyser),
    close: () => releaseVoiceAudio(pending, stream),
  };
}

/** Stop the mic and close the context (also for a session that never finished). */
export function releaseVoiceAudio(pending: PendingVoiceAudio, stream?: MediaStream): void {
  const stopTracks = (s: MediaStream) => s.getTracks().forEach((track) => track.stop());
  if (stream) stopTracks(stream);
  else pending.mic.then(stopTracks, () => undefined);
  if (pending.context.state !== "closed") void pending.context.close().catch(() => undefined);
}
