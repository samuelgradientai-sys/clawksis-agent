/**
 * useAutoScroll — autoscroll "inteligente" para el Modern Chat.
 *
 * Problema del enfoque anterior: re-pegaba al fondo en CADA token (forzaba un
 * reflow sincrónico por token y secuestraba el scroll — no podías subir a leer
 * mientras el agente respondía).
 *
 * Acá sólo seguimos al fondo si el usuario YA está cerca del fondo. Si scrolleó
 * hacia arriba, lo dejamos quieto y exponemos `showJump` para mostrar un pill
 * "saltar a lo último". El listener de scroll es passive y sólo toca un ref +
 * un boolean de estado (sin re-render por cada píxel).
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

export interface UseAutoScrollResult {
  /** true cuando el usuario scrolleó hacia arriba (mostrar pill). */
  showJump: boolean;
  /** Baja al fondo y re-engancha el autoscroll. */
  scrollToBottom: (smooth?: boolean) => void;
}

export function useAutoScroll(
  scrollRef: React.RefObject<HTMLElement | null>,
  /** Cambia cuando crece el contenido (p.ej. el array de mensajes). */
  contentSignal: unknown,
  /** Cambia al reemplazar la conversación (p.ej. sessionId) → re-anclar al fondo. */
  resetSignal?: unknown,
  threshold = 80,
): UseAutoScrollResult {
  const atBottomRef = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const recompute = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = dist <= threshold;
    atBottomRef.current = atBottom;
    setShowJump((prev) => (prev === !atBottom ? prev : !atBottom));
  }, [scrollRef, threshold]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", recompute, { passive: true });
    return () => el.removeEventListener("scroll", recompute);
  }, [scrollRef, recompute]);

  const scrollToBottom = useCallback(
    (smooth = false) => {
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({
        top: el.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
      atBottomRef.current = true;
      setShowJump(false);
    },
    [scrollRef],
  );

  // Seguir el contenido SOLO si estamos anclados al fondo. Cuando el usuario
  // subió, ni leemos ni escribimos layout (cero reflow).
  useLayoutEffect(() => {
    if (!atBottomRef.current) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [contentSignal, scrollRef]);

  // Al cambiar de conversación, re-anclar al fondo (el historial arranca abajo)
  // y recalcular el pill en el próximo frame. Recalculamos vía rAF (no en el
  // cuerpo síncrono del efecto) porque en una conversación corta fijar scrollTop
  // no dispara 'scroll', y el pill quedaría pegado de la sesión anterior.
  useLayoutEffect(() => {
    atBottomRef.current = true;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    const id = requestAnimationFrame(() => recompute());
    return () => cancelAnimationFrame(id);
  }, [resetSignal, scrollRef, recompute]);

  return { showJump, scrollToBottom };
}
