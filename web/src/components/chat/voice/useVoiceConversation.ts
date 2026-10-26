/**
 * useVoiceConversation — runs one VoiceConversation for as long as the voice
 * overlay is mounted: browser mic + VAD, `/api/audio/*` for STT/TTS, and the
 * chat's own gateway connection for the turns (they show up in the chat
 * history like typed ones). Mounted per open, so `pending` is fixed.
 */

import { useEffect, useState, useSyncExternalStore } from "react";
import { subscribeChatEvents } from "../hooks/chatEventListeners";
import { openReplySpeech } from "./replySpeech";
import { createSpeechSegmenter } from "./speechSegmenter";
import { finishVoiceAudio, type PendingVoiceAudio, type VoiceAudioSession } from "./voiceAudio";
import {
  loadVoiceSettings,
  openSpeakSocket,
  setVoiceLeases,
  sttAvailable,
  synthesizeSentence,
  transcribeUtterance,
} from "./voiceApi";
import { VoiceConversation, type VoiceConversationDeps, type VoiceSnapshot } from "./voiceConversation";
import { DEFAULT_VOICE_SETTINGS, type VoiceSettings } from "./voiceSettings";
import { holdScreenAwake } from "./wakeLock";

/** What voice mode needs from the chat (useChatGateway). */
export interface VoiceGateway {
  sessionId: string | null;
  busy: boolean;
  sendVoiceTurn: (text: string, interrupted?: boolean) => void;
  interrupt: () => void;
  sendRpc: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  /** The agent asked something (approval, clarify) that is answered in the chat. */
  waitingOnUser: boolean;
}

export interface VoiceConversationView {
  snapshot: VoiceSnapshot;
  settings: () => VoiceSettings;
  micLevel: () => number;
  outputLevel: () => number;
  toggleMute: () => void;
  hangUp: () => void;
}

function createRuntime(pending: PendingVoiceAudio, initialGateway: VoiceGateway) {
  let audio: VoiceAudioSession | null = null;
  // The conversation's long-lived callbacks read the latest gateway props.
  const gateway = { current: initialGateway };
  const deps: VoiceConversationDeps = {
    settings: DEFAULT_VOICE_SETTINGS,
    createSegmenter: async (events) => {
      const [settings, canTranscribe] = await Promise.all([loadVoiceSettings(), sttAvailable(gateway.current.sendRpc)]);
      deps.settings = settings;
      if (!canTranscribe) throw new Error("No STT provider available");
      audio = await finishVoiceAudio(pending);
      return createSpeechSegmenter(audio, settings, events);
    },
    openReply: (events) =>
      openReplySpeech(
        {
          context: pending.context,
          destination: audio?.output ?? pending.context.destination,
          openSocket: openSpeakSocket,
          synthesize: synthesizeSentence,
        },
        events,
      ),
    transcribe: transcribeUtterance,
    submit: (text, interrupted) => {
      if (!gateway.current.sessionId) return false;
      gateway.current.sendVoiceTurn(text, interrupted);
      return true;
    },
    interrupt: () => gateway.current.interrupt(),
    setLeases: setVoiceLeases,
  };
  return {
    voice: new VoiceConversation(deps),
    setGateway: (next: VoiceGateway) => {
      gateway.current = next;
    },
    settings: () => deps.settings,
    micLevel: () => audio?.micLevel() ?? 0,
    outputLevel: () => audio?.outputLevel() ?? 0,
  };
}

export function useVoiceConversation(pending: PendingVoiceAudio, gateway: VoiceGateway): VoiceConversationView {
  const [runtime] = useState(() => createRuntime(pending, gateway));
  const { voice } = runtime;
  useEffect(() => runtime.setGateway(gateway));
  const snapshot = useSyncExternalStore(voice.subscribe, voice.getSnapshot, voice.getSnapshot);

  useEffect(() => voice.setBusy(gateway.busy), [voice, gateway.busy]);

  useEffect(() => {
    const unsubscribe = subscribeChatEvents((event) => voice.handleEvent(event));
    const releaseWakeLock = holdScreenAwake();
    // A backgrounded tab loses the mic anyway (iOS cuts it): end cleanly instead.
    const onVisibility = () => {
      if (document.visibilityState === "hidden") voice.stop("hangup");
    };
    document.addEventListener("visibilitychange", onVisibility);
    void voice.start();
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      unsubscribe();
      releaseWakeLock();
      voice.stop("hangup");
    };
  }, [voice]);

  return {
    snapshot,
    settings: runtime.settings,
    micLevel: runtime.micLevel,
    outputLevel: runtime.outputLevel,
    toggleMute: () => voice.toggleMute(),
    hangUp: () => voice.stop("hangup"),
  };
}
