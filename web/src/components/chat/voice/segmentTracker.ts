/**
 * Utterance segmentation over fixed-size audio frames already labelled
 * speech / not-speech: the same contract as Silero VAD's frame processor
 * (pre-speech pad, minimum speech, redemption window), so the energy fallback
 * and the neural VAD produce identical events for the conversation loop.
 */

export interface SegmentTrackerOptions {
  /** Duration of one frame. */
  frameMs: number;
  /** Audio kept from before the first speech frame (the onset of the first word). */
  preSpeechPadMs: number;
  /** Speech shorter than this is a misfire (a cough, a door), never an utterance. */
  minSpeechMs: number;
  /** Silence that ends the utterance. */
  redemptionMs: number;
  /** Hard cap on one utterance. */
  maxSpeechMs: number;
}

export type SegmentEvent =
  | { type: "start" }
  /** Speech lasted `minSpeechMs`: a real utterance (barge-in trips here). */
  | { type: "confirmed" }
  | { type: "end"; audio: Float32Array }
  | { type: "misfire" };

const frames = (ms: number, frameMs: number) => Math.max(1, Math.round(ms / frameMs));

/** Silence kept after the last speech frame, so a soft final syllable survives. */
const TAIL_MS = 200;

function concat(chunks: Float32Array[]): Float32Array {
  const out = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

export class SegmentTracker {
  private readonly padFrames: number;
  private readonly minFrames: number;
  private readonly redemptionFrames: number;
  private readonly maxFrames: number;
  private readonly tailFrames: number;
  private pad: Float32Array[] = [];
  private segment: Float32Array[] = [];
  private speaking = false;
  private confirmed = false;
  private speechFrames = 0;
  private silentFrames = 0;

  constructor(options: SegmentTrackerOptions) {
    this.padFrames = frames(options.preSpeechPadMs, options.frameMs);
    this.minFrames = frames(options.minSpeechMs, options.frameMs);
    this.redemptionFrames = frames(options.redemptionMs, options.frameMs);
    this.maxFrames = frames(options.maxSpeechMs, options.frameMs);
    this.tailFrames = frames(TAIL_MS, options.frameMs);
  }

  /** Feed one frame; returns what it changed. */
  push(frame: Float32Array, isSpeech: boolean): SegmentEvent[] {
    if (!this.speaking) {
      if (!isSpeech) {
        this.pad.push(frame);
        if (this.pad.length > this.padFrames) this.pad.shift();
        return [];
      }
      this.speaking = true;
      this.segment = [...this.pad, frame];
      this.pad = [];
      this.speechFrames = 1;
      this.silentFrames = 0;
      return this.minFrames <= 1 ? this.confirm([{ type: "start" }]) : [{ type: "start" }];
    }
    this.segment.push(frame);
    const events: SegmentEvent[] = [];
    if (isSpeech) {
      this.speechFrames++;
      this.silentFrames = 0;
      if (!this.confirmed && this.speechFrames >= this.minFrames) this.confirm(events);
    } else {
      this.silentFrames++;
    }
    if (this.silentFrames >= this.redemptionFrames || this.segment.length >= this.maxFrames) events.push(this.close());
    return events;
  }

  /** Drop any half-heard utterance (mute, barge reset). */
  reset(): void {
    this.pad = [];
    this.segment = [];
    this.speaking = false;
    this.confirmed = false;
    this.speechFrames = 0;
    this.silentFrames = 0;
  }

  private confirm(events: SegmentEvent[]): SegmentEvent[] {
    this.confirmed = true;
    events.push({ type: "confirmed" });
    return events;
  }

  private close(): SegmentEvent {
    const real = this.confirmed;
    // Most of the redemption window is silence after the user stopped talking.
    const trailing = Math.max(0, this.silentFrames - this.tailFrames);
    const audio = concat(this.segment.slice(0, this.segment.length - trailing));
    this.reset();
    return real ? { type: "end", audio } : { type: "misfire" };
  }
}
