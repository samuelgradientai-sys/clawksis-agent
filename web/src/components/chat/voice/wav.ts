/** PCM helpers for voice mode: utterances leave the browser as 16 kHz mono WAV
 *  (every STT provider and `POST /api/audio/transcribe` take it, unlike the
 *  per-browser MediaRecorder containers). */

export const VAD_SAMPLE_RATE = 16_000;

/** 16-bit PCM mono WAV. */
export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const ascii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  ascii(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

/** Streaming resampler from the AudioContext's rate down to 16 kHz, cut into
 *  fixed frames (linear interpolation; speech has nothing above 8 kHz to lose). */
export class FrameResampler {
  private readonly step: number;
  private position = 0;
  private pending: number[] = [];
  private readonly frameSize: number;

  constructor(inputRate: number, frameSize: number) {
    this.step = inputRate / VAD_SAMPLE_RATE;
    this.frameSize = frameSize;
  }

  /** Feed one input block; returns the complete output frames it produced. */
  push(input: Float32Array): Float32Array[] {
    const out: Float32Array[] = [];
    // `position` indexes this block's input samples; its fractional remainder
    // carries over to the next block.
    while (this.position < input.length) {
      const i = Math.floor(this.position);
      const frac = this.position - i;
      const a = input[i];
      const b = i + 1 < input.length ? input[i + 1] : a;
      this.pending.push(a + (b - a) * frac);
      if (this.pending.length === this.frameSize) {
        out.push(Float32Array.from(this.pending));
        this.pending = [];
      }
      this.position += this.step;
    }
    this.position -= input.length;
    return out;
  }
}

/** Root-mean-square level of one frame (0..1 for float PCM). */
export function rms(frame: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
  return frame.length ? Math.sqrt(sum / frame.length) : 0;
}

export function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("No se pudo leer el audio"));
    reader.readAsDataURL(blob);
  });
}
