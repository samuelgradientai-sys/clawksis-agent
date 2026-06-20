// Static flowing SVG paths used as the dashboard backdrop.
//
// History: was framer-motion (pulled 122KB vendor-motion), then a CSS version
// that animated `stroke-dashoffset` on 72 full-screen paths EVERY frame. That
// property is not GPU-compositable, so it forced a continuous full-screen
// repaint of this `fixed inset-0` layer behind the whole dashboard — visible as
// flicker + stutter.
//
// This version draws the paths STATICALLY (zero per-frame paint) and adds only a
// slow opacity "breath" on the WRAPPER element. Opacity on a single element is
// GPU-composited (the compositor adjusts layer alpha; it does not repaint the
// SVG contents), so the cost is ~nil. Honors prefers-reduced-motion.
// Stroke colour = Clawksis purple #6C4FD6.

const BREATHE_CSS = `
@keyframes clawk-bg-breathe { 0%, 100% { opacity: 0.55; } 50% { opacity: 0.9; } }
.clawk-bg-wrap { animation: clawk-bg-breathe 16s ease-in-out infinite; will-change: opacity; }
@media (prefers-reduced-motion: reduce) { .clawk-bg-wrap { animation: none; opacity: 0.6; } }
`;

function FloatingPaths({ position }: { position: number }) {
  const paths = Array.from({ length: 36 }, (_, i) => ({
    id: i,
    d: `M-${380 - i * 5 * position} -${189 + i * 6}C-${
      380 - i * 5 * position
    } -${189 + i * 6} -${312 - i * 5 * position} ${216 - i * 6} ${
      152 - i * 5 * position
    } ${343 - i * 6}C${616 - i * 5 * position} ${470 - i * 6} ${
      684 - i * 5 * position
    } ${875 - i * 6} ${684 - i * 5 * position} ${875 - i * 6}`,
    width: 0.5 + i * 0.03,
  }));

  return (
    <svg
      className="h-full w-full"
      fill="none"
      preserveAspectRatio="xMidYMid slice"
      viewBox="0 0 696 316"
    >
      {paths.map((path) => (
        <path
          d={path.d}
          key={path.id}
          stroke="currentColor"
          strokeOpacity={0.08 + path.id * 0.025}
          strokeWidth={path.width}
        />
      ))}
    </svg>
  );
}

export function BackgroundPaths() {
  return (
    <div
      aria-hidden
      className="clawk-bg-wrap pointer-events-none fixed inset-0 z-[2] overflow-hidden"
      style={{ color: "#6C4FD6" }}
    >
      <style>{BREATHE_CSS}</style>
      <FloatingPaths position={1} />
      <FloatingPaths position={-1} />
    </div>
  );
}
