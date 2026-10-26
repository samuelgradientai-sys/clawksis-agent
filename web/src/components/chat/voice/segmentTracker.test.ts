import { describe, expect, it } from "vitest";
import { SegmentTracker, type SegmentEvent } from "./segmentTracker";
import { EnergyGate } from "./energySegmenter";

const FRAME_MS = 32;
const frame = (value: number) => new Float32Array(4).fill(value);

function run(tracker: SegmentTracker, pattern: string): SegmentEvent[] {
  // "s" = speech frame, "." = silence; the frame's samples carry its index.
  return [...pattern].flatMap((c, i) => tracker.push(frame(i), c === "s"));
}

const tracker = () =>
  new SegmentTracker({ frameMs: FRAME_MS, preSpeechPadMs: 64, minSpeechMs: 96, redemptionMs: 320, maxSpeechMs: 30_000 });

describe("utterance segmentation", () => {
  it("delivers the utterance with its onset pad once the user stays quiet long enough", () => {
    const events = run(tracker(), "....sss.s" + ".".repeat(10));
    expect(events.map((e) => e.type)).toEqual(["start", "confirmed", "end"]);
    const end = events[2] as Extract<SegmentEvent, { type: "end" }>;
    const indices = [...new Set(end.audio)];
    expect(indices[0]).toBe(2); // two frames (64 ms) of pre-speech pad
    expect(indices).toContain(8); // the second burst belongs to the same utterance
    expect(indices.at(-1)).toBeLessThan(18); // most of the trailing silence is cut
  });

  it("keeps listening through a pause shorter than the silence window", () => {
    const events = run(tracker(), "sss" + ".".repeat(8) + "sss");
    expect(events.map((e) => e.type)).toEqual(["start", "confirmed"]);
  });

  it("calls a burst shorter than the minimum speech a misfire, not an utterance", () => {
    const events = run(tracker(), "ss" + ".".repeat(12));
    expect(events.map((e) => e.type)).toEqual(["start", "misfire"]);
  });
});

describe("energy gate (fallback VAD)", () => {
  it("learns the room and keeps the reply's bleed from passing for the user", () => {
    const gate = new EnergyGate(null);
    for (let i = 0; i < 30; i++) gate.isSpeech(0.004); // quiet room
    expect(gate.isSpeech(0.03)).toBe(true);
    gate.setPlaybackActive(true);
    expect(gate.isSpeech(0.03)).toBe(false); // speaker bleed level
    expect(gate.isSpeech(0.2)).toBe(true); // a real voice still gets through
  });
});
