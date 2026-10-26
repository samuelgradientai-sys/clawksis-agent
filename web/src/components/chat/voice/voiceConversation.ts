/**
 * One voice conversation, from the tap that opens it to hang-up: the state
 * machine idle → connecting → listening → transcribing → thinking → speaking
 * → listening, plus barge-in. Plain TypeScript with every side effect
 * injected (mic, STT, TTS, the gateway), so the whole loop runs in tests; the
 * React hook only wires it to the page.
 *
 * Turns are normal chat turns (`prompt.submit` with `voice_turn`), so they land
 * in the conversation's history like typed ones. The reply is spoken while it
 * streams; the mic stays live the whole time so the user can talk over it.
 */

import { sanitizeTextForSpeech } from "@clawk/shared/voice/speech-text";
import { isTtsEcho } from "@clawk/shared/voice/tts-echo";
import type { GatewayEventFrame } from "../hooks/chatEvents";
import type { ReplySpeech, ReplySpeechEvents } from "./replySpeech";
import { describeVoiceError, type VoiceProblem } from "./voiceErrors";
import { isStopPhrase, type VoiceSettings } from "./voiceSettings";

export type VoicePhase = "idle" | "connecting" | "listening" | "transcribing" | "thinking" | "speaking";
export type VoiceEngine = "silero" | "energy";
/** Why the conversation ended: the overlay closes itself unless it was an error. */
export type VoiceEnd = "hangup" | "stop-phrase" | "error";

export interface VoiceSnapshot {
  phase: VoicePhase;
  muted: boolean;
  /** The user's last turn, as transcribed. */
  userCaption: string;
  /** The reply as it streams (its tail). */
  replyCaption: string;
  problem: VoiceProblem | null;
  engine: VoiceEngine | null;
  ended: VoiceEnd | null;
}

/** Mic + voice activity detection, already listening: delivers whole utterances. */
export interface SpeechSegmenter {
  /** Mute: no speech events until unpaused (a half-heard utterance is dropped). */
  setPaused(paused: boolean): void;
  /** The reply is audible: be stricter, so its bleed cannot pass for the user. */
  setPlaybackActive(active: boolean): void;
  destroy(): void;
}

export interface SegmenterEvents {
  /** Speech confirmed (long enough not to be a cough): barge-in trips here. */
  onSpeechStart(): void;
  /** The utterance, from its first syllable, once the user went quiet. */
  onSpeechEnd(audio: Blob): void;
}

export interface VoiceConversationDeps {
  settings: VoiceSettings;
  createSegmenter(events: SegmenterEvents): Promise<{ segmenter: SpeechSegmenter; engine: VoiceEngine }>;
  openReply(events: ReplySpeechEvents): ReplySpeech;
  transcribe(audio: Blob): Promise<string>;
  /** Submit a spoken turn; false when there is no conversation to submit to. */
  submit(text: string, interrupted: boolean): boolean;
  /** Stop the running turn (`session.interrupt`). */
  interrupt(): void;
  /** Warm (true) / release (false) the server's STT and TTS models. */
  setLeases(active: boolean): void;
  now?: () => number;
}

/** How long a barge-in waits for the interrupted turn to settle before submitting anyway. */
const INTERRUPT_SETTLE_MS = 5_000;
const CAPTION_CHARS = 280;

const IDLE: VoiceSnapshot = {
  phase: "idle",
  muted: false,
  userCaption: "",
  replyCaption: "",
  problem: null,
  engine: null,
  ended: null,
};

/** The tail of the reply as it is spoken (no markdown, code or tables). */
function captionTail(text: string): string {
  const clean = sanitizeTextForSpeech(text);
  if (clean.length <= CAPTION_CHARS) return clean;
  const cut = clean.slice(-CAPTION_CHARS);
  return "…" + cut.slice(Math.max(0, cut.indexOf(" ") + 1));
}

type Payload = Record<string, unknown>;
const str = (v: unknown) => (typeof v === "string" ? v : "");

export class VoiceConversation {
  private snapshot: VoiceSnapshot = IDLE;
  private readonly subscribers = new Set<() => void>();
  private segmenter: SpeechSegmenter | null = null;
  private reply: ReplySpeech | null = null;
  /** Bumped by stop(): async work of an older conversation drops out. */
  private epoch = 0;
  private running = false;
  private leased = false;
  private busy = false;
  private idleWaiters: Array<() => void> = [];
  /** A turn we submitted is still producing its reply. */
  private awaitingReply = false;
  private streamedText = "";
  /** TTS failed this turn: the rest of the reply stays text (no retry per delta). */
  private speechFailed = false;
  private audioStartedAt = 0;
  private interruptedNext = false;
  /** What was being spoken when the user barged in: a transcript of it is echo. */
  private echoSource = "";
  /** Transcriptions in flight, in the order the user spoke. */
  private transcripts: Promise<string>[] = [];

  private static readonly EVENTS: Record<string, (c: VoiceConversation, payload: Payload) => void> = {
    "message.delta": (c, p) => c.onReplyText(str(p.text)),
    // A tool runs next: speak the narration line before it now, not after the tool.
    "tool.start": (c) => c.reply?.flush(),
    "message.complete": (c, p) => c.onReplyComplete(str(p.text)),
    error: (c, p) => c.awaitingReply && c.update({ problem: describeVoiceError(str(p.message) || "error") }),
  };

  private readonly deps: VoiceConversationDeps;

  constructor(deps: VoiceConversationDeps) {
    this.deps = deps;
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    this.subscribers.add(listener);
    return () => {
      this.subscribers.delete(listener);
    };
  };

  readonly getSnapshot = (): VoiceSnapshot => this.snapshot;

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;
    const epoch = this.epoch;
    this.update({ ...IDLE, phase: "connecting" });
    try {
      const { segmenter, engine } = await this.deps.createSegmenter(this.segmenterEvents(epoch));
      if (epoch !== this.epoch) return segmenter.destroy();
      this.segmenter = segmenter;
      this.leased = true;
      this.deps.setLeases(true);
      this.update({ phase: "listening", engine });
    } catch (err) {
      if (epoch === this.epoch) this.report(err, true);
    }
  }

  /** End the conversation. A reply still generating keeps going as text. */
  stop(reason: VoiceEnd = "hangup"): void {
    if (!this.running) return;
    this.running = false;
    this.epoch++;
    const reply = this.reply;
    this.reply = null;
    reply?.stop();
    this.segmenter?.destroy();
    this.segmenter = null;
    if (this.leased) this.deps.setLeases(false);
    this.leased = false;
    this.awaitingReply = false;
    this.transcripts = [];
    this.idleWaiters.splice(0).forEach((wake) => wake());
    this.update({ phase: "idle", ended: reason });
  }

  toggleMute(): void {
    const muted = !this.snapshot.muted;
    this.segmenter?.setPaused(muted);
    this.update({ muted });
  }

  /** The chat's turn gate (useChatGateway `busy`). */
  setBusy(busy: boolean): void {
    const settled = this.busy && !busy;
    this.busy = busy;
    if (!settled) return;
    this.idleWaiters.splice(0).forEach((wake) => wake());
    // Our turn ended without message.complete (interrupted, refused).
    if (this.awaitingReply) this.endReplyStream();
  }

  /** The open conversation's gateway events (chatEventListeners). */
  handleEvent(event: GatewayEventFrame): void {
    if (this.running) VoiceConversation.EVENTS[event.type]?.(this, event.payload ?? {});
  }

  private update(patch: Partial<VoiceSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    this.subscribers.forEach((listener) => listener());
  }

  private now(): number {
    return this.deps.now?.() ?? Date.now();
  }

  private report(err: unknown, forceFatal = false): void {
    const problem = describeVoiceError(err);
    this.update({ problem });
    if (problem.fatal || forceFatal) this.stop("error");
  }

  private resumeListening(): void {
    if (this.running) this.update({ phase: "listening" });
  }

  // ── the user's side ──────────────────────────────────────────────────────

  private segmenterEvents(epoch: number): SegmenterEvents {
    const live = () => epoch === this.epoch && !this.snapshot.muted;
    return {
      onSpeechStart: () => {
        if (live()) this.onSpeechStart();
      },
      onSpeechEnd: (audio) => {
        if (live()) void this.onUtterance(audio, epoch);
      },
    };
  }

  private onSpeechStart(): void {
    const { phase } = this.snapshot;
    if (!this.deps.settings.bargeIn) return;
    if (phase === "speaking" && this.now() - this.audioStartedAt >= this.deps.settings.bargeInGraceMs) {
      this.bargeIn();
    } else if (phase === "thinking") {
      this.bargeIn();
    }
  }

  /** The user talked over the reply (or the model still thinking): silence it,
   *  stop the turn, and let what they are saying become the next turn. */
  private bargeIn(): void {
    const reply = this.reply;
    this.echoSource = reply && this.snapshot.phase === "speaking" ? reply.spokenText() : "";
    this.reply = null;
    reply?.stop();
    this.segmenter?.setPlaybackActive(false);
    if (this.busy) this.deps.interrupt();
    this.awaitingReply = false;
    this.interruptedNext = true;
    this.update({ phase: "listening" });
  }

  private async onUtterance(audio: Blob, epoch: number): Promise<void> {
    const { phase } = this.snapshot;
    if (phase !== "listening" && phase !== "transcribing") return;
    this.transcripts.push(
      this.deps.transcribe(audio).then(
        (text) => text.trim(),
        (err: unknown) => {
          if (epoch === this.epoch) this.report(err);
          return "";
        },
      ),
    );
    // A pause mid-sentence makes two utterances: the first loop joins them.
    if (this.transcripts.length > 1) return;
    this.update({ phase: "transcribing" });
    const parts: string[] = [];
    while (this.transcripts.length) {
      parts.push(await this.transcripts[0]);
      if (epoch !== this.epoch) return;
      this.transcripts.shift();
    }
    await this.onTranscript(parts.filter(Boolean).join(" "), epoch);
  }

  private async onTranscript(text: string, epoch: number): Promise<void> {
    const echoSource = this.echoSource;
    this.echoSource = "";
    if (!text) return this.resumeListening();
    if (isStopPhrase(text, this.deps.settings.stopPhrases)) return this.stop("stop-phrase");
    // Over speakers the reply bleeds into the mic: hearing ourselves is silence.
    if (echoSource && isTtsEcho(text, echoSource)) {
      this.interruptedNext = false;
      return this.resumeListening();
    }
    await this.whenIdle();
    if (epoch === this.epoch) this.submit(text);
  }

  /** Resolves once the interrupted turn settled (or after a bounded wait). */
  private whenIdle(): Promise<void> {
    if (!this.busy) return Promise.resolve();
    return new Promise((resolve) => {
      const wake = () => {
        clearTimeout(timer);
        resolve();
      };
      const timer = setTimeout(wake, INTERRUPT_SETTLE_MS);
      this.idleWaiters.push(wake);
    });
  }

  private submit(text: string): void {
    const interrupted = this.interruptedNext;
    this.interruptedNext = false;
    this.streamedText = "";
    this.speechFailed = false;
    this.awaitingReply = true;
    if (!this.deps.submit(text, interrupted)) {
      this.awaitingReply = false;
      this.update({ problem: describeVoiceError("No hay una conversación abierta todavía.") });
      return this.resumeListening();
    }
    this.update({ phase: "thinking", userCaption: text, replyCaption: "", problem: null });
  }

  // ── the reply ────────────────────────────────────────────────────────────

  private onReplyText(chunk: string): void {
    if (!this.awaitingReply || !chunk) return;
    this.streamedText += chunk;
    this.update({ replyCaption: captionTail(this.streamedText) });
    if (!this.speechFailed) this.ensureReply().append(chunk);
  }

  private onReplyComplete(finalText: string): void {
    if (!this.awaitingReply) return;
    // A provider that does not stream hands the whole reply over at the end.
    if (!this.streamedText.trim() && finalText.trim()) {
      this.streamedText = finalText;
      this.update({ replyCaption: captionTail(finalText) });
      if (!this.speechFailed) this.ensureReply().append(finalText);
    }
    this.endReplyStream();
  }

  private endReplyStream(): void {
    this.awaitingReply = false;
    if (this.reply) this.reply.finish();
    else if (this.snapshot.phase === "thinking") this.resumeListening();
  }

  private ensureReply(): ReplySpeech {
    if (this.reply) return this.reply;
    const reply = this.deps.openReply({
      onAudioStart: () => {
        if (this.reply !== reply) return;
        this.audioStartedAt = this.now();
        this.segmenter?.setPlaybackActive(true);
        this.update({ phase: "speaking" });
      },
      onError: (err) => {
        if (this.reply !== reply) return;
        this.speechFailed = true;
        this.report(err);
      },
    });
    this.reply = reply;
    void reply.done.then(() => {
      // Barged or stopped: whoever replaced the reply owns the phase now.
      if (this.reply !== reply) return;
      this.reply = null;
      this.segmenter?.setPlaybackActive(false);
      if (!this.awaitingReply) this.resumeListening();
    });
    return reply;
  }
}
