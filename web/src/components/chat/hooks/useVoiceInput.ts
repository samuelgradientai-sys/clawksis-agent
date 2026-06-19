/**
 * useVoiceInput — dictado por voz para el composer.
 *
 * Camino principal: Web Speech API (SpeechRecognition) → transcripción EN VIVO
 * (interim results) que se va escribiendo en el input mientras el usuario habla.
 * Disponible en Chrome/Edge (y Safari con prefijo).
 *
 * Fallback (Firefox u otros sin Web Speech): graba con MediaRecorder y al
 * soltar manda el audio (base64) a POST /api/audio/transcribe (Whisper, batch
 * — el texto aparece al terminar, no en vivo).
 *
 * El consumidor pasa un callback onText(transcript) a start(); el hook lo llama
 * con la transcripción acumulada en cada update.
 */

import { useCallback, useRef, useState } from "react";

import { api } from "@/lib/api";

// Tipos mínimos de Web Speech API (no están en el lib.dom de este tsconfig).
interface SpeechRecognitionAlternativeLike {
  transcript: string;
}
interface SpeechRecognitionResultLike {
  0: SpeechRecognitionAlternativeLike;
  isFinal: boolean;
  length: number;
}
interface SpeechRecognitionResultListLike {
  length: number;
  [index: number]: SpeechRecognitionResultLike;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: SpeechRecognitionResultListLike;
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: { error?: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

type OnText = (transcript: string) => void;

interface UseVoiceInputResult {
  /** true si hay alguna vía de voz (Web Speech o getUserMedia). */
  supported: boolean;
  /** true si la transcripción es en vivo (Web Speech), false si es batch. */
  live: boolean;
  listening: boolean;
  transcribing: boolean;
  error: string | null;
  start: (onText: OnText) => Promise<void>;
  stop: () => void;
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(r.error ?? new Error("FileReader error"));
    r.readAsDataURL(blob);
  });
}

export function useVoiceInput(): UseVoiceInputResult {
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalRef = useRef("");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const hasWebSpeech = getSpeechRecognition() != null;
  const hasMedia =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";
  const supported = hasWebSpeech || hasMedia;

  const startWebSpeech = useCallback(
    (Ctor: SpeechRecognitionCtor, onText: OnText) => {
      const rec = new Ctor();
      rec.lang = navigator.language || "es-ES";
      rec.continuous = true;
      rec.interimResults = true;
      finalRef.current = "";
      rec.onresult = (e) => {
        let interim = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const res = e.results[i];
          const txt = res[0]?.transcript ?? "";
          if (res.isFinal) finalRef.current += txt;
          else interim += txt;
        }
        onText((finalRef.current + interim).trim());
      };
      rec.onerror = (ev) => {
        if (ev?.error === "no-speech" || ev?.error === "aborted") return;
        setError(ev?.error ? "Voz: " + ev.error : "Error de reconocimiento de voz");
      };
      rec.onend = () => {
        setListening(false);
        recognitionRef.current = null;
      };
      recognitionRef.current = rec;
      setError(null);
      setListening(true);
      try {
        rec.start();
      } catch {
        /* ya iniciado */
      }
    },
    [],
  );

  const startFallback = useCallback(async (onText: OnText) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, {
          type: mr.mimeType || "audio/webm",
        });
        if (blob.size === 0) return;
        setTranscribing(true);
        try {
          const dataUrl = await blobToDataUrl(blob);
          const res = await api.transcribeAudio(dataUrl, blob.type);
          if (res?.transcript) onText(res.transcript.trim());
        } catch (err) {
          setError(err instanceof Error ? err.message : "Falló la transcripción");
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorderRef.current = mr;
      setError(null);
      setListening(true);
      mr.start();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "No se pudo acceder al micrófono",
      );
      setListening(false);
    }
  }, []);

  const start = useCallback(
    async (onText: OnText) => {
      if (listening) return;
      const Ctor = getSpeechRecognition();
      if (Ctor) {
        startWebSpeech(Ctor, onText);
        return;
      }
      if (hasMedia) {
        await startFallback(onText);
        return;
      }
      setError("Tu navegador no soporta entrada de voz.");
    },
    [listening, hasMedia, startWebSpeech, startFallback],
  );

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        /* ignore */
      }
      return; // onend pone listening=false
    }
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        /* ignore */
      }
      mediaRecorderRef.current = null;
    }
    setListening(false);
  }, []);

  return {
    supported,
    live: hasWebSpeech,
    listening,
    transcribing,
    error,
    start,
    stop,
  };
}
