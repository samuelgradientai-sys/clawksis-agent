import { describe, expect, it, vi } from "vitest";
import type { ReplySpeech, ReplySpeechEvents } from "./replySpeech";
import { VoiceConversation, type SegmenterEvents, type VoicePhase } from "./voiceConversation";
import { DEFAULT_VOICE_SETTINGS, type VoiceSettings } from "./voiceSettings";

/** A reply speech double that records what the controller asked it to say. */
function fakeReply(events: ReplySpeechEvents) {
  let resolve: (v: "done" | "stopped") => void = () => undefined;
  const said: string[] = [];
  const calls: string[] = [];
  const reply: ReplySpeech & { said: string[]; calls: string[]; events: ReplySpeechEvents; end: () => void } = {
    said,
    calls,
    events,
    done: new Promise((r) => (resolve = r)),
    append: (t) => said.push(t),
    flush: () => calls.push("flush"),
    finish: () => calls.push("finish"),
    stop: () => {
      calls.push("stop");
      resolve("stopped");
    },
    spokenText: () => said.join(""),
    isPlaying: () => true,
    end: () => resolve("done"),
  };
  return reply;
}

function harness(settings: Partial<VoiceSettings> = {}) {
  let mic!: SegmenterEvents;
  let clock = 1_000;
  const replies: ReturnType<typeof fakeReply>[] = [];
  const transcripts: string[] = [];
  const deps = {
    settings: { ...DEFAULT_VOICE_SETTINGS, ...settings },
    createSegmenter: vi.fn(async (events: SegmenterEvents) => {
      mic = events;
      return {
        engine: "energy" as const,
        segmenter: {
          setPaused: vi.fn(),
          setPlaybackActive: vi.fn(),
          destroy: vi.fn(),
        },
      };
    }),
    openReply: (events: ReplySpeechEvents) => {
      const reply = fakeReply(events);
      replies.push(reply);
      return reply;
    },
    transcribe: vi.fn(async () => transcripts.shift() ?? ""),
    submit: vi.fn<(text: string, interrupted: boolean) => boolean>(() => true),
    interrupt: vi.fn(),
    setLeases: vi.fn(),
    now: () => clock,
  };
  const voice = new VoiceConversation(deps);
  const phase = (): VoicePhase => voice.getSnapshot().phase;
  const say = async (text: string) => {
    transcripts.push(text);
    mic.onSpeechStart();
    mic.onSpeechEnd(new Blob(["pcm"]));
    await vi.waitFor(() => expect(deps.transcribe).toHaveBeenCalled());
    await flush();
  };
  const emit = (type: string, payload: Record<string, unknown> = {}) => voice.handleEvent({ type, payload });
  const advance = (ms: number) => (clock += ms);
  return { voice, deps, phase, say, emit, replies, advance, mic: () => mic };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("voice conversation loop", () => {
  it("walks listening → transcribing → thinking → speaking → listening as one normal turn", async () => {
    const h = harness();
    await h.voice.start();
    expect(h.phase()).toBe("listening");
    expect(h.deps.setLeases).toHaveBeenCalledWith(true);

    await h.say("¿Qué hora es?");
    expect(h.deps.submit).toHaveBeenCalledWith("¿Qué hora es?", false);
    expect(h.phase()).toBe("thinking");
    h.voice.setBusy(true);

    h.emit("message.delta", { text: "Son las " });
    h.emit("message.delta", { text: "**diez**." });
    const [reply] = h.replies;
    expect(reply.said).toEqual(["Son las ", "**diez**."]); // the server strips markdown per sentence
    expect(h.phase()).toBe("thinking"); // text, but nothing audible yet
    reply.events.onAudioStart();
    expect(h.phase()).toBe("speaking");
    expect(h.voice.getSnapshot().replyCaption).toBe("Son las diez.");

    h.emit("message.complete", { text: "Son las diez." });
    expect(reply.calls).toContain("finish");
    h.voice.setBusy(false);
    reply.end();
    await flush();
    expect(h.phase()).toBe("listening");
  });

  it("speaks a narration line before a tool runs, and a non-streamed reply at the end", async () => {
    const h = harness();
    await h.voice.start();
    await h.say("revisá el disco");
    h.emit("message.delta", { text: "Déjame revisar" });
    h.emit("tool.start", { name: "terminal" });
    expect(h.replies[0].calls).toEqual(["flush"]);

    h.replies[0].end();
    await flush();
    await h.say("y la memoria");
    h.emit("message.complete", { text: "Tenés 8 GB libres." });
    expect(h.replies[1].said).toEqual(["Tenés 8 GB libres."]);
    expect(h.replies[1].calls).toEqual(["finish"]);
  });

  it("goes back to listening when the turn ends without a reply", async () => {
    const h = harness();
    await h.voice.start();
    await h.say("hola");
    h.voice.setBusy(true);
    h.voice.setBusy(false); // refused / interrupted: no message.complete
    expect(h.phase()).toBe("listening");
    expect(h.replies).toHaveLength(0);
  });

  it("joins two utterances heard during one transcription into a single turn", async () => {
    const h = harness();
    await h.voice.start();
    let release!: (t: string) => void;
    h.deps.transcribe.mockImplementationOnce(() => new Promise<string>((r) => (release = r)));
    h.deps.transcribe.mockImplementationOnce(async () => "mañana a las nueve");
    h.mic().onSpeechEnd(new Blob(["a"]));
    expect(h.phase()).toBe("transcribing");
    h.mic().onSpeechEnd(new Blob(["b"]));
    release("Poneme una alarma");
    await vi.waitFor(() => expect(h.deps.submit).toHaveBeenCalled());
    expect(h.deps.submit).toHaveBeenCalledWith("Poneme una alarma mañana a las nueve", false);
  });

  it("ends the conversation on a spoken stop phrase instead of sending it", async () => {
    const h = harness();
    await h.voice.start();
    await h.say("¡Basta!");
    expect(h.deps.submit).not.toHaveBeenCalled();
    expect(h.voice.getSnapshot()).toMatchObject({ phase: "idle", ended: "stop-phrase" });
    expect(h.deps.setLeases).toHaveBeenLastCalledWith(false);
  });

  it("does not listen while muted", async () => {
    const h = harness();
    await h.voice.start();
    h.voice.toggleMute();
    h.mic().onSpeechEnd(new Blob(["x"]));
    await flush();
    expect(h.deps.transcribe).not.toHaveBeenCalled();
    expect(h.voice.getSnapshot().muted).toBe(true);
  });

  it("stops with a config hint when no speech-to-text provider is configured", async () => {
    const h = harness();
    await h.voice.start();
    h.deps.transcribe.mockRejectedValueOnce(new Error("No STT provider available. Install faster-whisper"));
    h.mic().onSpeechEnd(new Blob(["x"]));
    await vi.waitFor(() => expect(h.phase()).toBe("idle"));
    expect(h.voice.getSnapshot().ended).toBe("error");
    expect(h.voice.getSnapshot().problem).toMatchObject({ fatal: true, configHint: true });
  });
});

describe("barge-in", () => {
  async function speaking(settings: Partial<VoiceSettings> = {}) {
    const h = harness(settings);
    await h.voice.start();
    await h.say("contame un cuento largo");
    h.voice.setBusy(true);
    h.emit("message.delta", { text: "Había una vez un dragón que vivía en una montaña muy alta." });
    h.replies[0].events.onAudioStart();
    return h;
  }

  it("talking over the reply silences it, stops the turn and sends the next turn as interrupted", async () => {
    const h = await speaking();
    h.advance(2_000);
    h.mic().onSpeechStart();
    expect(h.replies[0].calls).toContain("stop");
    expect(h.deps.interrupt).toHaveBeenCalledTimes(1);
    expect(h.phase()).toBe("listening");

    h.deps.transcribe.mockResolvedValueOnce("mejor contame un chiste");
    h.mic().onSpeechEnd(new Blob(["x"]));
    await flush();
    expect(h.deps.submit).not.toHaveBeenCalledTimes(2); // waits for the interrupted turn
    h.voice.setBusy(false);
    await vi.waitFor(() => expect(h.deps.submit).toHaveBeenLastCalledWith("mejor contame un chiste", true));
  });

  it("ignores speech in the grace window right after the reply becomes audible", async () => {
    const h = await speaking({ bargeInGraceMs: 500 });
    h.advance(200);
    h.mic().onSpeechStart();
    expect(h.replies[0].calls).not.toContain("stop");
    expect(h.phase()).toBe("speaking");
  });

  it("drops a transcript that is the reply heard back through the speakers", async () => {
    const h = await speaking();
    h.advance(2_000);
    h.mic().onSpeechStart();
    h.deps.transcribe.mockResolvedValueOnce("un dragón que vivía en una montaña");
    h.mic().onSpeechEnd(new Blob(["x"]));
    h.voice.setBusy(false);
    await flush();
    await flush();
    expect(h.deps.submit).toHaveBeenCalledTimes(1); // only the original turn
    expect(h.phase()).toBe("listening");
  });

  it("stays off when voice.barge_in is false", async () => {
    const h = await speaking({ bargeIn: false });
    h.advance(2_000);
    h.mic().onSpeechStart();
    expect(h.replies[0].calls).not.toContain("stop");
    expect(h.deps.interrupt).not.toHaveBeenCalled();
  });

  it("interrupts a turn that is still thinking when the user starts talking", async () => {
    const h = harness();
    await h.voice.start();
    await h.say("buscá vuelos a Madrid");
    h.voice.setBusy(true);
    h.mic().onSpeechStart();
    expect(h.deps.interrupt).toHaveBeenCalledTimes(1);
    h.emit("message.delta", { text: "Buscando…" }); // the stale reply never speaks
    expect(h.replies).toHaveLength(0);
  });
});
