import { AudioLines } from "lucide-react";
import { ComposerMicButton } from "../ComposerMicButton";
import type { useVoiceInput } from "../hooks/useVoiceInput";
import { openVoiceMode } from "./voiceStore";

type Dictation = ReturnType<typeof useVoiceInput>;

/** Opens voice mode. The open runs inside the tap on purpose: iOS only lets
 *  audio started in a user gesture play (voiceAudio.beginVoiceAudio). */
export function StartVoiceButton({ disabled, dictation }: { disabled: boolean; dictation: Dictation }) {
  return (
    <button
      type="button"
      onClick={() => {
        if (dictation.listening) dictation.stop();
        openVoiceMode();
      }}
      disabled={disabled}
      aria-label="Modo voz"
      title="Modo voz — hablá con Clawksis y te responde en voz alta"
      className="flex size-11 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent sm:size-8 sm:rounded-lg"
    >
      <AudioLines className="size-4" />
    </button>
  );
}

interface ComposerVoiceControlsProps {
  voice: Dictation;
  disabled: boolean;
  /** Dictation into the composer (the mic button). */
  onMic: () => void;
}

/** The composer's voice buttons: dictation, then the voice conversation mode. */
export function ComposerVoiceControls({ voice, disabled, onMic }: ComposerVoiceControlsProps) {
  return (
    <>
      <ComposerMicButton voice={voice} disabled={disabled} onClick={onMic} />
      <StartVoiceButton disabled={disabled} dictation={voice} />
    </>
  );
}
