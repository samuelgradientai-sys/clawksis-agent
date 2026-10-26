/**
 * Speaks ONE assistant reply while it streams: sentences go to the
 * `/api/audio/speak-stream` socket as they complete, the int16 PCM that comes
 * back is queued gap-free on the conversation's AudioContext, so speech
 * overlaps generation. Protocol (clawk_cli/web_routers/audio.py):
 *
 *   client → {text} per sentence, {done:true} at the end, {stop:true} on barge-in
 *   server → {type:"start", sample_rate}, binary PCM, {type:"end"} | {type:"fallback"}
 *
 * When the socket answers `fallback` or drops before any audio, each sentence
 * is synthesized with `POST /api/audio/speak` and played in order instead.
 */

import { cutSentences, sanitizeTextForSpeech } from "@clawk/shared/voice/speech-text";

/** The part of a WebSocket the session uses (a fake in tests). */
export interface SpeechSocket {
  readonly readyState: number;
  binaryType: BinaryType;
  send(data: string): void;
  close(): void;
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  onclose: ((ev: CloseEvent) => void) | null;
}

export interface ReplySpeechDeps {
  context: BaseAudioContext;
  /** Where reply audio is played (the output meter's input). */
  destination: AudioNode;
  openSocket: () => Promise<SpeechSocket>;
  /** One sentence through `POST /api/audio/speak`, as encoded audio bytes. */
  synthesize: (text: string) => Promise<ArrayBuffer>;
}

export interface ReplySpeechEvents {
  /** The first sample of this reply is about to be heard. */
  onAudioStart: () => void;
  onError: (err: unknown) => void;
}

export interface ReplySpeech {
  /** More reply text (raw deltas; sentences are cut here). */
  append(text: string): void;
  /** Speak the incomplete tail now (a tool started after a narration line). */
  flush(): void;
  /** No more text: resolves `done` once the audio drains. */
  finish(): void;
  /** Barge-in: silence now and tell the server to drop the rest. */
  stop(): void;
  /** Everything handed to TTS so far (what the mic may hear back). */
  spokenText(): string;
  isPlaying(): boolean;
  done: Promise<"done" | "stopped">;
}

const SOCKET_OPEN = 1;
/** Lead time so the first buffer is never scheduled in the past. */
const SCHEDULE_LEAD_S = 0.05;
const DEFAULT_RATE = 24_000;
/** A run-on reply (no sentence punctuation) is cut at a word past this, so
 *  speech never waits for the end of a long paragraph. */
const MAX_PENDING_CHARS = 200;

class StreamedReply implements ReplySpeech {
  readonly done: Promise<"done" | "stopped">;
  private resolveDone: (outcome: "done" | "stopped") => void = () => undefined;
  /** Reply text not yet cut into a sentence. */
  private pending = "";
  private readonly sent: string[] = [];
  private readonly outbox: string[] = [];
  private readonly sources = new Set<AudioScheduledSourceNode>();
  private socket: SpeechSocket | null = null;
  private finished = false;
  private settled = false;
  private started = false;
  private fallback = false;
  private rate = DEFAULT_RATE;
  private nextStartAt = 0;
  private carry: Uint8Array | null = null;
  private fallbackQueue: string[] = [];
  private pumping = false;
  private readonly deps: ReplySpeechDeps;
  private readonly events: ReplySpeechEvents;

  constructor(deps: ReplySpeechDeps, events: ReplySpeechEvents) {
    this.deps = deps;
    this.events = events;
    this.done = new Promise((resolve) => (this.resolveDone = resolve));
    deps.openSocket().then(
      (socket) => this.attach(socket),
      () => this.enterFallback(),
    );
  }

  append(text: string): void {
    if (this.finished || this.settled || !text) return;
    this.pending += text;
    this.queue(this.cut(false));
  }

  flush(): void {
    if (!this.finished && !this.settled) this.queue(this.cut(true));
  }

  finish(): void {
    if (this.finished || this.settled) return;
    this.queue(this.cut(true));
    this.finished = true;
    if (!this.sent.length) return this.settle("done");
    if (this.fallback) this.settleIfDrained();
    else this.send({ done: true });
  }

  stop(): void {
    if (this.settled) return;
    if (this.socket?.readyState === SOCKET_OPEN) this.socket.send(JSON.stringify({ stop: true }));
    this.settle("stopped");
  }

  spokenText(): string {
    return this.sent.join(" ");
  }

  isPlaying(): boolean {
    return !this.settled && this.sources.size > 0;
  }

  private cut(flush: boolean): string[] {
    const { sentences, rest } = cutSentences(this.pending, flush);
    this.pending = rest;
    const at = rest.length > MAX_PENDING_CHARS ? rest.lastIndexOf(" ") : -1;
    if (at > 0) {
      sentences.push(rest.slice(0, at).trim());
      this.pending = rest.slice(at + 1);
    }
    return sentences;
  }

  private queue(sentences: string[]): void {
    for (const sentence of sentences) {
      if (!sentence.trim()) continue;
      this.sent.push(sentence);
      if (this.fallback) {
        this.fallbackQueue.push(sentence);
        void this.pumpFallback();
      } else {
        // A blank line is a boundary for the server's SentenceChunker too, so it speaks
        // exactly this sentence now (a forced word cut or a "…" ending is not one).
        this.send({ text: sentence.trimEnd() + "\n\n" });
      }
    }
  }

  private send(frame: object): void {
    if (this.fallback || this.settled) return;
    const data = JSON.stringify(frame);
    if (this.socket?.readyState === SOCKET_OPEN) this.socket.send(data);
    else this.outbox.push(data);
  }

  private attach(socket: SpeechSocket): void {
    if (this.settled || this.fallback) return socket.close();
    this.socket = socket;
    socket.binaryType = "arraybuffer";
    const drainOutbox = () => this.outbox.splice(0).forEach((data) => socket.send(data));
    socket.onopen = drainOutbox;
    socket.onmessage = (ev) =>
      typeof ev.data === "string" ? this.onControl(ev.data) : this.schedule(ev.data as ArrayBuffer);
    socket.onerror = () => this.onDrop();
    socket.onclose = () => this.onDrop();
    if (socket.readyState === SOCKET_OPEN) drainOutbox();
  }

  private onControl(raw: string): void {
    let frame: { type?: string; sample_rate?: number };
    try {
      frame = JSON.parse(raw) as typeof frame;
    } catch {
      return;
    }
    if (frame.type === "start") this.rate = frame.sample_rate || DEFAULT_RATE;
    else if (frame.type === "end") this.drainThenDone();
    else if (frame.type === "fallback") this.onDrop();
  }

  /** The stream ended early: before any audio, speak through POST instead;
   *  after audio, what played is the reply (replaying it would stutter). */
  private onDrop(): void {
    if (this.settled || this.fallback) return;
    if (this.started) this.drainThenDone();
    else this.enterFallback();
  }

  private schedule(data: ArrayBuffer): void {
    if (this.settled || this.fallback) return;
    // Provider chunks are not sample-aligned: carry an odd byte over.
    let bytes = new Uint8Array(data);
    if (this.carry) {
      const joined = new Uint8Array(this.carry.length + bytes.length);
      joined.set(this.carry);
      joined.set(bytes, this.carry.length);
      bytes = joined;
      this.carry = null;
    }
    const usable = bytes.length - (bytes.length % 2);
    if (usable !== bytes.length) this.carry = bytes.slice(usable);
    if (!usable) return;
    const pcm = new Int16Array(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + usable));
    const buffer = this.deps.context.createBuffer(1, pcm.length, this.rate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32_768;
    this.play(buffer, Math.max(this.deps.context.currentTime + SCHEDULE_LEAD_S, this.nextStartAt));
  }

  private play(buffer: AudioBuffer, at: number): AudioBufferSourceNode {
    const source = this.deps.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.deps.destination);
    source.onended = () => this.sources.delete(source);
    this.sources.add(source);
    source.start(at);
    this.nextStartAt = at + buffer.duration;
    if (!this.started) {
      this.started = true;
      this.events.onAudioStart();
    }
    return source;
  }

  private drainThenDone(): void {
    const remaining = Math.max(0, this.nextStartAt - this.deps.context.currentTime);
    setTimeout(() => this.settle("done"), remaining * 1_000 + 100);
  }

  private enterFallback(): void {
    if (this.settled || this.fallback) return;
    this.fallback = true;
    this.socket?.close();
    this.fallbackQueue = [...this.sent];
    void this.pumpFallback();
  }

  /** Plays the queued sentences in order, synthesizing the next while one plays. */
  private async pumpFallback(): Promise<void> {
    if (this.pumping) return;
    this.pumping = true;
    try {
      let next = this.takeSynthesis();
      while (next && !this.settled) {
        const audio = await next;
        if (this.settled) return;
        next = this.takeSynthesis();
        if (audio) await this.playToEnd(await this.deps.context.decodeAudioData(audio));
        next ??= this.takeSynthesis();
      }
    } catch (err) {
      this.events.onError(err);
      this.settle("done");
      return;
    } finally {
      this.pumping = false;
    }
    this.settleIfDrained();
  }

  private takeSynthesis(): Promise<ArrayBuffer | null> | null {
    while (this.fallbackQueue.length) {
      const text = sanitizeTextForSpeech(this.fallbackQueue.shift() ?? "");
      if (text) return this.deps.synthesize(text);
    }
    return null;
  }

  private playToEnd(buffer: AudioBuffer): Promise<void> {
    return new Promise((resolve) => {
      if (this.settled) return resolve();
      const source = this.play(buffer, this.deps.context.currentTime + SCHEDULE_LEAD_S);
      source.addEventListener("ended", () => resolve(), { once: true });
    });
  }

  private settleIfDrained(): void {
    if (this.finished && !this.pumping && !this.fallbackQueue.length) this.settle("done");
  }

  private settle(outcome: "done" | "stopped"): void {
    if (this.settled) return;
    this.settled = true;
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // never started or already ended: nothing left to silence
      }
    }
    this.sources.clear();
    this.socket?.close();
    this.resolveDone(outcome);
  }
}

export function openReplySpeech(deps: ReplySpeechDeps, events: ReplySpeechEvents): ReplySpeech {
  return new StreamedReply(deps, events);
}
