/**
 * Full-screen voice mode (ChatGPT-style): the orb, live captions, and three
 * controls — mute, hang up, switch to text. The turns themselves are normal
 * chat turns, so closing the overlay leaves the whole exchange in the chat.
 */

import { useCallback, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router";
import { AlertCircle, AudioLines, Keyboard, Mic, MicOff, PhoneOff, X, type LucideIcon } from "lucide-react";
import "./voiceOverlay.css";
import { useVoiceConversation, type VoiceGateway } from "./useVoiceConversation";
import type { VoicePhase, VoiceSnapshot } from "./voiceConversation";
import type { VoiceProblem } from "./voiceErrors";
import type { StopPhraseConfig } from "./voiceSettings";
import { closeVoiceMode, type VoiceModeState } from "./voiceStore";
import { VoiceOrb } from "./VoiceOrb";

const STATUS: Record<VoicePhase, string> = {
  idle: "Modo voz detenido",
  connecting: "Preparando el micrófono…",
  listening: "Te escucho…",
  transcribing: "Transcribiendo…",
  thinking: "Pensando…",
  speaking: "Hablando…",
};

function statusLine(snapshot: VoiceSnapshot): string {
  if (snapshot.muted && snapshot.phase === "listening") return "Micrófono silenciado";
  return STATUS[snapshot.phase];
}

function hintLine(snapshot: VoiceSnapshot, stopPhrases: StopPhraseConfig): string {
  if (snapshot.phase === "speaking") return snapshot.muted ? "Micrófono silenciado" : "Hablá encima para interrumpir";
  if (snapshot.phase !== "listening" || snapshot.muted || snapshot.userCaption) return "";
  const stop = stopPhrases.mode === "custom" ? stopPhrases.phrases[0] : stopPhrases.mode === "default" ? "basta" : "";
  return stop ? `Hablá con naturalidad. Decí «${stop}» para terminar.` : "Hablá con naturalidad.";
}

/** Put the cursor back in the chat composer (after "pasar a texto"). */
function focusComposer(): void {
  requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>(".clawk-liquid-composer textarea")?.focus());
}

interface RoundButtonProps {
  label: string;
  caption: string;
  icon: LucideIcon;
  onClick: () => void;
  tone?: "plain" | "danger" | "active";
  autoFocus?: boolean;
}

const TONES: Record<NonNullable<RoundButtonProps["tone"]>, string> = {
  plain: "bg-white/10 text-white hover:bg-white/20",
  active: "bg-white text-[#1b1040] hover:bg-white/90",
  danger: "size-[72px] bg-red-500 text-white shadow-lg shadow-red-950/40 hover:bg-red-400",
};

function RoundButton({ label, caption, icon: Icon, onClick, tone = "plain", autoFocus }: RoundButtonProps) {
  return (
    <div className="flex w-20 flex-col items-center gap-2">
      <button
        type="button"
        onClick={onClick}
        aria-label={label}
        title={label}
        autoFocus={autoFocus}
        aria-pressed={tone === "active" ? true : undefined}
        className={
          "flex size-14 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white " +
          TONES[tone]
        }
      >
        <Icon className={tone === "danger" ? "size-7" : "size-6"} />
      </button>
      <span className="text-xs text-white/60">{caption}</span>
    </div>
  );
}

function ProblemNote({ problem, onOpenConfig }: { problem: VoiceProblem; onOpenConfig: () => void }) {
  return (
    <div
      role="alert"
      className="flex max-w-md items-start gap-2 rounded-2xl border border-amber-300/30 bg-amber-300/10 px-4 py-3 text-left text-sm text-amber-50"
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-amber-300" />
      <div className="flex flex-col gap-2">
        <span>{problem.message}</span>
        {problem.configHint && (
          <button type="button" onClick={onOpenConfig} className="self-start font-medium text-amber-200 underline underline-offset-4">
            Abrir Config
          </button>
        )}
      </div>
    </div>
  );
}

/** An approval / question card is waiting in the chat, under this overlay. */
function WaitingOnUser({ onShow }: { onShow: () => void }) {
  return (
    <div role="alert" className="flex max-w-md flex-col items-center gap-2 rounded-2xl bg-white/10 px-4 py-3 text-sm">
      <span>Clawksis está esperando que confirmes algo en el chat.</span>
      <button type="button" onClick={onShow} className="font-medium text-[#cbbcff] underline underline-offset-4">
        Ver en el chat
      </button>
    </div>
  );
}

function Header({ engineNote }: { engineNote: string }) {
  return (
    <header className="flex items-center justify-between px-4 pt-3">
      <div className="flex items-center gap-2 text-sm font-medium text-white/80">
        <AudioLines className="size-4 text-[#b9a6ff]" />
        Modo voz
        {engineNote && <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/60">{engineNote}</span>}
      </div>
      <button
        type="button"
        onClick={closeVoiceMode}
        aria-label="Cerrar modo voz"
        className="flex size-11 items-center justify-center rounded-full text-white/70 hover:bg-white/10 hover:text-white"
      >
        <X className="size-5" />
      </button>
    </header>
  );
}

function useCloseOnEnd(snapshot: VoiceSnapshot): void {
  useEffect(() => {
    if (snapshot.ended === "hangup" || snapshot.ended === "stop-phrase") closeVoiceMode();
  }, [snapshot.ended]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeVoiceMode();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

function VoiceSession({ pending, gateway }: { pending: NonNullable<VoiceModeState["audio"]>; gateway: VoiceGateway }) {
  const view = useVoiceConversation(pending, gateway);
  const { snapshot } = view;
  const navigate = useNavigate();
  const viewRef = useRef(view);
  useEffect(() => {
    viewRef.current = view;
  });
  useCloseOnEnd(snapshot);
  const { phase, muted } = snapshot;
  const level = useCallback(() => {
    if (phase === "speaking") return viewRef.current.outputLevel();
    return phase === "listening" && !muted ? viewRef.current.micLevel() : 0;
  }, [phase, muted]);
  const openConfig = () => {
    closeVoiceMode();
    navigate("/config");
  };
  const toText = () => {
    closeVoiceMode();
    focusComposer();
  };
  const hint = hintLine(snapshot, view.settings().stopPhrases);
  return (
    <>
      <Header engineNote={snapshot.engine === "energy" ? "detección básica" : ""} />
      <main className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
        <VoiceOrb phase={phase} muted={muted} level={level} />
        <div className="flex flex-col items-center gap-1" aria-live="polite">
          <p className="text-xl font-medium tracking-tight">{statusLine(snapshot)}</p>
          {hint && <p className="text-sm text-white/55">{hint}</p>}
        </div>
        <div className="flex w-full max-w-xl flex-col gap-3">
          {snapshot.userCaption && <p className="text-sm text-white/55">“{snapshot.userCaption}”</p>}
          {snapshot.replyCaption && (
            <p className="voice-caption-reply text-base leading-relaxed text-white/90">{snapshot.replyCaption}</p>
          )}
        </div>
        {snapshot.problem && <ProblemNote problem={snapshot.problem} onOpenConfig={openConfig} />}
        {gateway.waitingOnUser && <WaitingOnUser onShow={toText} />}
      </main>
      <footer className="voice-controls flex items-end justify-center gap-6 pt-4 sm:gap-10">
        <RoundButton
          label={muted ? "Activar micrófono" : "Silenciar micrófono"}
          caption={muted ? "Activar" : "Silenciar"}
          icon={muted ? MicOff : Mic}
          tone={muted ? "active" : "plain"}
          onClick={view.toggleMute}
        />
        <RoundButton label="Colgar" caption="Colgar" icon={PhoneOff} tone="danger" onClick={closeVoiceMode} autoFocus />
        <RoundButton label="Pasar a texto" caption="Texto" icon={Keyboard} onClick={toText} />
      </footer>
    </>
  );
}

function SetupProblem({ problem }: { problem: VoiceProblem | null }) {
  const navigate = useNavigate();
  return (
    <>
      <Header engineNote="" />
      <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
        <MicOff className="size-12 text-white/40" />
        {problem && (
          <ProblemNote
            problem={problem}
            onOpenConfig={() => {
              closeVoiceMode();
              navigate("/config");
            }}
          />
        )}
      </main>
      <footer className="voice-controls flex justify-center pt-4">
        <RoundButton label="Cerrar modo voz" caption="Cerrar" icon={X} onClick={closeVoiceMode} autoFocus />
      </footer>
    </>
  );
}

export default function VoiceOverlay({ state, gateway }: { state: VoiceModeState; gateway: VoiceGateway }) {
  return createPortal(
    <div role="dialog" aria-modal="true" aria-label="Modo voz" className="voice-overlay fixed inset-0 z-[90] flex flex-col text-white">
      {state.audio ? <VoiceSession pending={state.audio} gateway={gateway} /> : <SetupProblem problem={state.problem} />}
    </div>,
    document.body,
  );
}
