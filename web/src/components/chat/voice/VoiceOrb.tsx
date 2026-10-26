import { useEffect, useRef } from "react";
import type { VoicePhase } from "./voiceConversation";

interface VoiceOrbProps {
  phase: VoicePhase;
  muted: boolean;
  /** Live level (RMS) of whatever is audible now: the mic or the reply. */
  level: () => number;
}

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

/** The animated sphere at the centre of voice mode. It breathes while the agent
 *  thinks and follows the voice (yours or its) otherwise; still under
 *  prefers-reduced-motion, where only its colour says what is happening. */
export function VoiceOrb({ phase, muted, level }: VoiceOrbProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const still = typeof window.matchMedia === "function" && window.matchMedia(REDUCED_MOTION).matches;
    if (still) return;
    let frame = 0;
    let smooth = 0;
    const tick = () => {
      // Speech RMS rarely passes 0.2: scale it into 0..1, ease toward it.
      const target = Math.min(1, Math.sqrt(level()) * 2.2);
      smooth += (target - smooth) * (target > smooth ? 0.35 : 0.12);
      ref.current?.style.setProperty("--orb-level", smooth.toFixed(3));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [level]);

  return (
    <div ref={ref} className="voice-orb" data-phase={phase} data-muted={muted} aria-hidden="true">
      <div className="voice-orb__glow" />
      <div className="voice-orb__core">
        <div className="voice-orb__swirl" />
      </div>
    </div>
  );
}
