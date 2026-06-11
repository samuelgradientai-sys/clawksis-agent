import { motion } from "motion/react";

// Animated flowing SVG paths used as the dashboard backdrop. Adapted from a
// Next.js/shadcn snippet to Vite + the `motion` package: the demo title and
// button were dropped — here it is purely a background layer that sits behind
// the app content (pointer-events-none, fixed inset-0). Stroke colour is the
// Clawksis brand purple #6C4FD6 via `currentColor`.

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
        <motion.path
          animate={{
            opacity: [0.2, 0.5, 0.2],
            pathLength: 1,
            pathOffset: [0, 1, 0],
          }}
          d={path.d}
          initial={{ opacity: 0.5, pathLength: 0.3 }}
          key={path.id}
          stroke="currentColor"
          strokeOpacity={0.08 + path.id * 0.025}
          strokeWidth={path.width}
          transition={{
            // Deterministic per-path variance (no Math.random) so the field
            // shimmers without every line moving in lockstep.
            duration: 20 + (path.id % 10),
            ease: "linear",
            repeat: Number.POSITIVE_INFINITY,
          }}
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
      <FloatingPaths position={1} />
      <FloatingPaths position={-1} />
    </div>
  );
}
