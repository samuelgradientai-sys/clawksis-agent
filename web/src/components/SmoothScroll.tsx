import { useEffect } from "react";

/**
 * Scroll suave (momentum) para el dashboard — el "feeling" del scroll de la
 * landing, sin dependencias (mini-Lenis casero).
 *
 * El dashboard no tiene un scroll de página único (cada panel —chat, sesiones,
 * sidebar— scrollea por su cuenta), así que esto es GLOBAL: intercepta la
 * rueda y suaviza el contenedor scrollable que esté bajo el cursor.
 *
 * - Opt-in y OFF por defecto (`localStorage["clawksis-dashboard-smooth-scroll"]`).
 * - Respeta `prefers-reduced-motion`.
 * - Sólo vertical; si el gesto es horizontal o hay pinch-zoom, no interfiere.
 * - Si nada es scrollable bajo el cursor, deja el scroll nativo.
 */
const KEY = "clawksis-dashboard-smooth-scroll";
export const SMOOTH_EVENT = "clawk-smoothscroll-change";

export function isSmoothScrollOn(): boolean {
  return typeof window !== "undefined" && window.localStorage.getItem(KEY) === "1";
}

export function setSmoothScrollOn(on: boolean): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, on ? "1" : "0");
  window.dispatchEvent(new Event(SMOOTH_EVENT));
}

export function SmoothScroll() {
  useEffect(() => {
    let cleanup: (() => void) | null = null;

    const setup = () => {
      cleanup?.();
      cleanup = null;

      if (!isSmoothScrollOn()) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

      let activeEl: HTMLElement | null = null;
      let current = 0;
      let target = 0;
      let raf = 0;
      let animating = false;

      // Contenedor scrollable más cercano (bajo el cursor) que pueda moverse
      // en la dirección del gesto.
      const findScrollable = (
        node: EventTarget | null,
        dy: number,
      ): HTMLElement | null => {
        let n = node as HTMLElement | null;
        while (n && n !== document.body && n !== document.documentElement) {
          if (n.nodeType === 1 && n.scrollHeight > n.clientHeight + 1) {
            const oy = getComputedStyle(n).overflowY;
            if (oy === "auto" || oy === "scroll") {
              if (dy > 0 && n.scrollTop + n.clientHeight < n.scrollHeight - 1) return n;
              if (dy < 0 && n.scrollTop > 0) return n;
            }
          }
          n = n.parentElement;
        }
        return null;
      };

      const tick = () => {
        if (!activeEl) {
          animating = false;
          return;
        }
        current += (target - current) * 0.14;
        if (Math.abs(target - current) < 0.4) {
          current = target;
          animating = false;
        }
        activeEl.scrollTop = current;
        if (animating) raf = requestAnimationFrame(tick);
      };

      const onWheel = (e: WheelEvent) => {
        if (e.ctrlKey) return; // pinch-zoom
        if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) return; // gesto horizontal
        const sc = findScrollable(e.target, e.deltaY);
        if (!sc) return; // nada scrollable → nativo
        e.preventDefault();
        if (sc !== activeEl || !animating) {
          activeEl = sc;
          current = sc.scrollTop;
          target = sc.scrollTop;
        }
        const max = Math.max(0, sc.scrollHeight - sc.clientHeight);
        target = Math.max(0, Math.min(max, target + e.deltaY));
        if (!animating) {
          animating = true;
          raf = requestAnimationFrame(tick);
        }
      };

      window.addEventListener("wheel", onWheel, { passive: false });
      cleanup = () => {
        window.removeEventListener("wheel", onWheel);
        cancelAnimationFrame(raf);
      };
    };

    setup();
    window.addEventListener(SMOOTH_EVENT, setup);
    window.addEventListener("storage", setup);
    return () => {
      cleanup?.();
      window.removeEventListener(SMOOTH_EVENT, setup);
      window.removeEventListener("storage", setup);
    };
  }, []);

  return null;
}
