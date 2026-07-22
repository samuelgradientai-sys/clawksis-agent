/**
 * useMessageQueue — cola FIFO estilo Telegram para el Modern Chat.
 *
 * El usuario puede escribir y "enviar" varios mensajes mientras el agente
 * responde: cada uno queda en espera y se dispara automáticamente cuando el
 * turno anterior termina. El backend rechaza un segundo `prompt.submit` con
 * error 4009 ("session busy"), así que el drenado SOLO ocurre cuando el agente
 * está libre — nunca en paralelo.
 *
 * Debounce del drenado: un turno del backend puede emitir VARIOS segmentos
 * (p.ej. continuación de /goal o notificaciones de procesos) — `busy` baja a
 * false entre segmentos. Si drenáramos en ese flanco, mandaríamos el mensaje en
 * cola a mitad de turno (carrera con el `running` del backend → 4009 y mensaje
 * perdido). Por eso esperamos `drainDelayMs` de inactividad sostenida: si llega
 * un nuevo segmento (busy vuelve a true) dentro de la ventana, se cancela el
 * disparo. El re-chequeo en el disparo evita perder el ítem si la sesión cambió.
 *
 * El estado de la cola vive acá, fuera del camino caliente del streaming, para
 * no re-renderizar la lista de mensajes al encolar.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface QueuedMessage {
  id: string;
  text: string;
  createdAt: number;
}

interface UseMessageQueueArgs {
  /** true mientras un turno está en curso (del gateway). */
  busy: boolean;
  /** true cuando es seguro enviar (WebSocket conectado). */
  ready: boolean;
  /** true cuando hay una sesión activa. */
  hasSession: boolean;
  /** Envía un mensaje al gateway (setea busy sincrónicamente). */
  send: (text: string) => void;
  /** Inactividad sostenida (ms) antes de drenar el siguiente ítem. */
  drainDelayMs?: number;
}

export interface UseMessageQueueResult {
  /** Mensajes esperando turno, en orden FIFO. */
  queued: QueuedMessage[];
  /** Encola un mensaje (para cuando el agente está ocupado). */
  enqueue: (text: string) => void;
  /** Cancela un mensaje pendiente antes de que se envíe. */
  cancel: (id: string) => void;
  /** Vacía la cola (al cambiar de sesión). */
  clear: () => void;
}

let seq = 0;

export function useMessageQueue({
  busy,
  ready,
  hasSession,
  send,
  // 700ms > el gap del poller de continuación (~500ms): si el turno re-arranca
  // un segmento (continuación /goal o notificación de proceso), su message.start
  // pone busy=true y cancela este disparo ANTES de que venza → no mandamos el
  // mensaje en cola a mitad de turno (evita la carrera con `running` → 4009).
  drainDelayMs = 700,
}: UseMessageQueueArgs): UseMessageQueueResult {
  const [queued, setQueued] = useState<QueuedMessage[]>([]);
  const queuedRef = useRef<QueuedMessage[]>(queued);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    queuedRef.current = queued;
  }, [queued]);

  const enqueue = useCallback((text: string) => {
    if (!text.trim()) return;
    setQueued((q) => [...q, { id: "q-" + ++seq, text, createdAt: Date.now() }]);
  }, []);

  const cancel = useCallback((id: string) => {
    setQueued((q) => q.filter((item) => item.id !== id));
  }, []);

  const clear = useCallback(() => {
    // Cancelamos un disparo en vuelo además de vaciar (defensivo: que un timer
    // viejo no dispare tras cambiar de sesión, aunque el re-chequeo ya lo cubre).
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    setQueued((q) => (q.length ? [] : q));
  }, []);

  // Drenado debounced. El efecto re-corre con cada cambio de busy/ready/
  // hasSession/queued; mientras no se cumplan las condiciones (o llegue otro
  // segmento que vuelve a poner busy=true) se cancela cualquier disparo pendiente.
  useEffect(() => {
    const clearTimer = () => {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    if (busy || !ready || !hasSession || queued.length === 0) {
      clearTimer();
      return;
    }
    if (timerRef.current != null) return; // ya hay un disparo programado

    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      // Re-chequeo en el disparo: la cola pudo vaciarse mientras esperábamos.
      const items = queuedRef.current;
      if (items.length === 0) return;
      const next = items[0];
      setQueued((q) => (q[0]?.id === next.id ? q.slice(1) : q));
      send(next.text); // setea busy=true sincrónicamente → no re-dispara
    }, drainDelayMs);

    return clearTimer;
  }, [busy, ready, hasSession, queued, send, drainDelayMs]);

  // Limpieza en unmount.
  useEffect(
    () => () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  return { queued, enqueue, cancel, clear };
}
