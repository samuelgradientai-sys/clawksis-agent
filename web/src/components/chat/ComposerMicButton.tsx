import { Loader2, Mic } from "lucide-react";
import type { useVoiceInput } from "./hooks/useVoiceInput";

type Voice = Pick<ReturnType<typeof useVoiceInput>, "supported" | "live" | "listening" | "transcribing">;

function micTitle(voice: Voice): string {
  if (!voice.supported) return "Tu navegador no soporta dictado por voz";
  if (voice.transcribing) return "Transcribiendo…";
  if (voice.listening) return "Detener (hablá y se transcribe en vivo)";
  return voice.live ? "Dictar por voz — transcripción en vivo" : "Dictar por voz — se transcribe al soltar";
}

/** The composer's dictation button (start / stop / transcribing). */
export function ComposerMicButton({
  voice,
  disabled,
  onClick,
}: {
  voice: Voice;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || !voice.supported || voice.transcribing}
      aria-label={voice.listening ? "Detener grabación" : "Dictar por voz"}
      title={micTitle(voice)}
      className={
        "flex size-10 items-center justify-center rounded-xl transition-colors disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent sm:size-8 sm:rounded-lg " +
        (voice.listening
          ? "bg-destructive/15 text-destructive animate-pulse"
          : "text-muted-foreground hover:bg-muted/40 hover:text-foreground")
      }
    >
      {voice.transcribing ? <Loader2 className="size-4 animate-spin" /> : <Mic className="size-4" />}
    </button>
  );
}
