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

import { useCallback, useEffect, useRef, useState } from "react";

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

function friendlySpeechError(code?: string): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "Voz: el micrófono está bloqueado por el navegador.";
    case "audio-capture":
      return "Voz: no se detectó un micrófono disponible.";
    case "network":
      return "Voz: error de red al iniciar el dictado.";
    case "language-not-supported":
      return "Voz: idioma de dictado no soportado por el navegador.";
    case "no-speech":
    case "aborted":
      return "";
    default:
      return code ? "Voz: " + code : "Error de reconocimiento de voz";
  }
}

function friendlyMicError(err: unknown): string {
  if (err instanceof DOMException) {
    if (err.name === "NotAllowedError" || err.name === "SecurityError") {
      return "Voz: el micrófono está bloqueado por el navegador.";
    }

    if (err.name === "NotFoundError") {
      return "Voz: no se detectó un micrófono disponible.";
    }
  }

  return err instanceof Error
    ? "Voz: " + err.message
    : "No se pudo acceder al micrófono";
}

export function useVoiceInput(): UseVoiceInputResult {
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const finalRef = useRef("");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const errorTimerRef = useRef<number | null>(null);

  const clearVoiceError = useCallback(() => {
    if (errorTimerRef.current != null && typeof window !== "undefined") {
      window.clearTimeout(errorTimerRef.current);
      errorTimerRef.current = null;
    }
    setError(null);
  }, []);

  const setTransientError = useCallback((message: string) => {
    if (!message) return;

    if (errorTimerRef.current != null && typeof window !== "undefined") {
      window.clearTimeout(errorTimerRef.current);
      errorTimerRef.current = null;
    }

    setError(message);

    if (typeof window !== "undefined") {
      errorTimerRef.current = window.setTimeout(() => {
        setError(null);
        errorTimerRef.current = null;
      }, 5500);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (errorTimerRef.current != null && typeof window !== "undefined") {
        window.clearTimeout(errorTimerRef.current);
      }
    };
  }, []);

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
        try {
          let interim = "";
          for (let i = e.resultIndex; i < e.results.length; i++) {
            const res = e.results[i];
            const txt = res[0]?.transcript ?? "";
            if (res.isFinal) finalRef.current += txt;
            else interim += txt;
          }
          onText((finalRef.current + interim).trim());
        } catch (err) {
          console.error("[useVoiceInput] onresult", err);
        }
      };
      rec.onerror = (ev) => {
        if (ev?.error === "no-speech" || ev?.error === "aborted") return;

        if (ev?.error === "not-allowed" || ev?.error === "service-not-allowed") {
          setListening(false);
          recognitionRef.current = null;
          try {
            rec.abort();
          } catch {
            /* ignore */
          }
        }

        setTransientError(friendlySpeechError(ev?.error));
      };
      rec.onend = () => {
        setListening(false);
        recognitionRef.current = null;
      };
      recognitionRef.current = rec;
      clearVoiceError();
      setListening(true);
      try {
        rec.start();
      } catch {
        /* ya iniciado */
      }
    },
    [clearVoiceError, setTransientError],
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
          setTransientError(
            err instanceof Error ? "Voz: " + err.message : "Falló la transcripción",
          );
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorderRef.current = mr;
      clearVoiceError();
      setListening(true);
      mr.start();
    } catch (err) {
      setTransientError(friendlyMicError(err));
      setListening(false);
    }
  }, [clearVoiceError, setTransientError]);

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
      setTransientError("Tu navegador no soporta entrada de voz.");
    },
    [listening, hasMedia, startWebSpeech, startFallback, setTransientError],
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
