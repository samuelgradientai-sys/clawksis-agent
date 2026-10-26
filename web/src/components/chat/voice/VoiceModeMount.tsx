import { lazy, Suspense, type ComponentType } from "react";
import type { VoiceGateway } from "./useVoiceConversation";
import { closeVoiceMode, useVoiceMode, type VoiceModeState } from "./voiceStore";

interface OverlayProps {
  state: VoiceModeState;
  gateway: VoiceGateway;
}

function OverlayUnavailable() {
  closeVoiceMode();
  return null;
}

// The overlay (and, from it, the VAD runtime) loads on the first open only.
const VoiceOverlay = lazy(
  (): Promise<{ default: ComponentType<OverlayProps> }> =>
    import("./VoiceOverlay").catch((err: unknown) => {
      console.error("[voice] overlay failed to load", err);
      return { default: OverlayUnavailable };
    }),
);

/** Voice mode's single mount point in the chat; renders nothing while closed. */
export function VoiceModeMount({ gateway }: { gateway: VoiceGateway }) {
  const state = useVoiceMode();
  if (!state.open) return null;
  return (
    <Suspense fallback={null}>
      <VoiceOverlay state={state} gateway={gateway} />
    </Suspense>
  );
}
