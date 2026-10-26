import { describe, expect, it, vi } from "vitest";
import { openReplySpeech, type SpeechSocket } from "./replySpeech";

class FakeSocket implements SpeechSocket {
  readyState = 0;
  binaryType: BinaryType = "blob";
  sent: Array<Record<string, unknown>> = [];
  closed = false;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.closed = true;
  }
  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  control(frame: object) {
    this.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent);
  }
  pcm(bytes: number[]) {
    this.onmessage?.({ data: new Uint8Array(bytes).buffer } as MessageEvent);
  }
}

/** Just enough of an AudioContext to see what got scheduled, at what rate. */
function fakeAudio() {
  const scheduled: Array<{ at: number; samples: number[]; rate: number; stopped: boolean }> = [];
  const context = {
    currentTime: 0,
    createBuffer: (_channels: number, length: number, rate: number) => {
      const data = new Float32Array(length);
      return { duration: length / rate, sampleRate: rate, getChannelData: () => data } as unknown as AudioBuffer;
    },
    createBufferSource: () => {
      const listeners: Array<() => void> = [];
      const node = {
        buffer: null as AudioBuffer | null,
        onended: null as null | (() => void),
        connect: vi.fn(),
        addEventListener: (_: string, cb: () => void) => listeners.push(cb),
        start(at: number) {
          const buffer = this.buffer!;
          const entry = { at, samples: Array.from(buffer.getChannelData(0)), rate: buffer.sampleRate, stopped: false };
          scheduled.push(entry);
          (node as unknown as { entry: typeof entry }).entry = entry;
        },
        stop() {
          (node as unknown as { entry: { stopped: boolean } }).entry.stopped = true;
          node.onended?.();
          listeners.forEach((cb) => cb());
        },
        end() {
          node.onended?.();
          listeners.forEach((cb) => cb());
        },
      };
      created.push(node);
      return node as unknown as AudioBufferSourceNode;
    },
    decodeAudioData: async (bytes: ArrayBuffer) =>
      context.createBuffer(1, new Uint8Array(bytes).length, 8_000) as AudioBuffer,
  };
  const created: Array<{ end: () => void }> = [];
  return { context: context as unknown as BaseAudioContext, scheduled, created };
}

function setup(synthesize = vi.fn(async (text: string) => new TextEncoder().encode(text).buffer as ArrayBuffer)) {
  const socket = new FakeSocket();
  const audio = fakeAudio();
  const events = { onAudioStart: vi.fn(), onError: vi.fn() };
  const reply = openReplySpeech(
    { context: audio.context, destination: {} as AudioNode, openSocket: async () => socket, synthesize },
    events,
  );
  return { socket, audio, events, reply, synthesize };
}

const tick = () => new Promise((r) => setTimeout(r, 0));

describe("reply speech over /api/audio/speak-stream", () => {
  it("sends each complete sentence once, queued until the socket opens, then done", async () => {
    const { socket, reply } = setup();
    reply.append("Hola, ¿cómo ");
    reply.append("estás? Hoy hace un día precioso en Buenos Aires. Y mañana");
    await tick();
    socket.open();
    expect(socket.sent).toEqual([{ text: "Hola, ¿cómo estás? Hoy hace un día precioso en Buenos Aires.\n\n" }]);

    reply.append(" va a llover.");
    reply.finish();
    expect(socket.sent.slice(1)).toEqual([{ text: "Y mañana va a llover.\n\n" }, { done: true }]);
    expect(reply.spokenText()).toContain("Y mañana va a llover.");
  });

  it("does not wait for the end of a long run-on paragraph to start speaking", async () => {
    const { socket, reply } = setup();
    await tick();
    socket.open();
    const words = Array.from({ length: 60 }, (_, i) => `palabra${i}`);
    reply.append(words.join(" "));
    expect(socket.sent).toHaveLength(1);
    const first = String(socket.sent[0].text);
    expect(first.startsWith("palabra0 palabra1")).toBe(true);
    expect(first.trim().endsWith("palabra")).toBe(false); // cut between words, never inside one
    reply.finish();
    const spoken = socket.sent.filter((f) => f.text).map((f) => String(f.text).trim());
    expect(spoken.join(" ")).toBe(words.join(" "));
  });

  it("speaks a narration tail on flush without ending the reply", async () => {
    const { socket, reply } = setup();
    await tick();
    socket.open();
    reply.append("Dejame revisar eso");
    reply.flush();
    expect(socket.sent).toEqual([{ text: "Dejame revisar eso\n\n" }]);
  });

  it("plays int16 PCM at the announced rate, carrying an odd byte across chunks", async () => {
    const { socket, reply, audio, events } = setup();
    await tick();
    socket.open();
    reply.append("Una respuesta lo bastante larga para hablar.");
    socket.control({ type: "start", sample_rate: 16_000 });
    socket.pcm([0x00, 0x40, 0x00]); // 0x4000 = 0.5, plus half a sample
    socket.pcm([0xc0]); // completes 0xc000 = -0.5
    expect(audio.scheduled.map((s) => [s.rate, s.samples])).toEqual([
      [16_000, [0.5]],
      [16_000, [-0.5]],
    ]);
    expect(audio.scheduled[1].at).toBeCloseTo(audio.scheduled[0].at + 1 / 16_000);
    expect(events.onAudioStart).toHaveBeenCalledTimes(1);
    expect(reply.isPlaying()).toBe(true);
  });

  it("barge-in tells the server to stop and silences what was scheduled", async () => {
    const { socket, reply, audio } = setup();
    await tick();
    socket.open();
    reply.append("Una respuesta lo bastante larga para hablar.");
    socket.control({ type: "start", sample_rate: 24_000 });
    socket.pcm([0x00, 0x10]);
    reply.stop();
    expect(socket.sent.at(-1)).toEqual({ stop: true });
    expect(socket.closed).toBe(true);
    expect(audio.scheduled[0].stopped).toBe(true);
    await expect(reply.done).resolves.toBe("stopped");
  });

  it("falls back to POST /api/audio/speak per sentence when the stream has no audio", async () => {
    const { socket, reply, audio, synthesize } = setup();
    await tick();
    socket.open();
    reply.append("Primera oración, con **markdown** de por medio. ");
    socket.control({ type: "fallback" });
    reply.append("Segunda oración que también se tiene que decir.");
    reply.finish();
    await vi.waitFor(() => expect(audio.created.length).toBe(1));
    expect(synthesize).toHaveBeenNthCalledWith(1, "Primera oración, con markdown de por medio.");
    audio.created[0].end();
    await vi.waitFor(() => expect(audio.created.length).toBe(2));
    expect(synthesize).toHaveBeenNthCalledWith(2, "Segunda oración que también se tiene que decir.");
    audio.created[1].end();
    await expect(reply.done).resolves.toBe("done");
    expect(socket.sent.some((f) => "done" in f)).toBe(false);
  });

  it("reports a TTS failure and ends the reply instead of hanging", async () => {
    const failing = vi.fn(async () => {
      throw new Error("No TTS provider available");
    });
    const { socket, reply, events } = setup(failing);
    await tick();
    socket.onclose?.(new Event("close") as CloseEvent); // dropped before any audio
    reply.append("Una oración que no se va a poder decir.");
    reply.finish();
    await expect(reply.done).resolves.toBe("done");
    expect(events.onError).toHaveBeenCalledWith(expect.objectContaining({ message: "No TTS provider available" }));
  });
});
