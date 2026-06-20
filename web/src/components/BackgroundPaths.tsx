// Animated flowing SVG paths used as the dashboard backdrop — CSS-only.
//
// Previously animated with the `motion` package, which pulled a ~122KB lib
// (vendor-motion) into the dashboard BOOT path just for a decorative layer.
// This version uses a single CSS @keyframes (stroke-dashoffset flow + opacity
// shimmer); `pathLength={1}` normalizes every path so one keyframe fits all
// lengths, and per-path `animationDuration` keeps the field out of lockstep.
// Honors prefers-reduced-motion. Stroke colour = Clawksis purple #6C4FD6.

const FLOW_CSS = `
@keyframes clawk-bg-flow {
  0%   { stroke-dashoffset: 0;  opacity: 0.2; }
  50%  { stroke-dashoffset: -1; opacity: 0.5; }
  100% { stroke-dashoffset: -2; opacity: 0.2; }
}
.clawk-bg-path {
  stroke-dasharray: 0.3 0.7;
  animation: clawk-bg-flow linear infinite;
  will-change: stroke-dashoffset, opacity;
}
@media (prefers-reduced-motion: reduce) {
  .clawk-bg-path { animation: none; opacity: 0.32; }
}
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
          className="clawk-bg-path"
          d={path.d}
          key={path.id}
          pathLength={1}
          stroke="currentColor"
          strokeOpacity={0.08 + path.id * 0.025}
          strokeWidth={path.width}
          // Deterministic per-path variance (10–14s) so the field shimmers
          // without every line moving in lockstep.
          style={{ animationDuration: `${10 + (path.id % 5)}s` }}
        />
      ))}
    </svg>
  );
}

export function BackgroundPaths() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[2] overflow-hidden"
      style={{ color: "#6C4FD6" }}
    >
      <style>{FLOW_CSS}</style>
      <FloatingPaths position={1} />
      <FloatingPaths position={-1} />
    </div>
  );
}
