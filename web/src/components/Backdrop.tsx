import { useGpuTier } from "@nous-research/ui/hooks/use-gpu-tier";

import { useTheme } from "@/themes";
import { BackgroundPaths } from "./BackgroundPaths";
import { SmokeBackdrop } from "./backgrounds/SmokeBackdrop";
import { GridBackdrop } from "./backgrounds/GridBackdrop";
import {
  AuroraBackdrop,
  BeamsBackdrop,
  DotsBackdrop,
} from "./backgrounds/CssBackdrops";

/** Renders the background layer the user selected in the "Fondo" picker.
 *  The theme-default / unknown ids fall back to the brand paths. */
function SelectedBackground({ bgId }: { bgId: string }) {
  switch (bgId) {
    case "none":
      return null;
    case "smoke":
      return <SmokeBackdrop />;
    case "grid":
      return <GridBackdrop />;
    case "aurora":
      return <AuroraBackdrop />;
    case "beams":
      return <BeamsBackdrop />;
    case "dots":
      return <DotsBackdrop />;
    default:
      return <BackgroundPaths />;
  }
}

/**
 * Replicates the visual layer stack of `<Overlays dark />` from
 * `@nous-research/ui` without pulling in its leva / gsap / three peer deps.
 *
 * Defaults match the Clawksis teal dark preset; the deep canvas and the warm
 * vignette both read theme-switchable CSS custom properties so `ThemeProvider`
 * can repaint the stack without remounting.
 *
 *   z-1   bg = `var(--background-base)`, mix-blend-mode driven by
 *         `--component-backdrop-bg-blend-mode` (default `difference`).
 *   z-2   animated Clawksis background paths (replaces the old filler-bg
 *         WebP image — see <BackgroundPaths />).
 *   z-99  warm top-left vignette (`var(--warm-glow)`), opacity 0.22, lighten
 *   z-200 FG inversion = `var(--foreground)` (opaque white in inverted
 *         themes, alpha-0 in the dark default), mix-blend-mode: difference.
 *         The layer that flips the dashboard into "light mode" for inverted
 *         themes; for normal dark themes its alpha is 0 so it's a no-op.
 *         Placed above every UI overlay z-index so portaled elements get
 *         inverted along with the rest of the page.
 *   z-201 noise grain (SVG, ~55% opacity × `--noise-opacity-mul`,
 *         color-dodge) — gated on GPU tier. Sits above the inversion layer
 *         by design so the grain is not flipped.
 *
 * `useGpuTier` returns 0 when WebGL is unavailable, the renderer is a
 * software rasterizer (SwiftShader/llvmpipe), or the user has
 * `prefers-reduced-motion: reduce` set. We skip the animated noise layer
 * in that case so low-power / accessibility-conscious sessions stay crisp.
 */
export function Backdrop() {
  const gpuTier = useGpuTier();
  const { bgId } = useTheme();

  return (
    <>
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-[1]"
        style={
          {
            backgroundColor: "var(--background-base)",
            mixBlendMode: "var(--component-backdrop-bg-blend-mode, difference)",
          } as unknown as React.CSSProperties
        }
      />

      {/* Fondo seleccionable (picker "Fondo"): paths / humo / grilla / ninguno. */}
      <SelectedBackground bgId={bgId} />

      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-[99]"
        style={{
          background:
            "radial-gradient(ellipse at 0% 0%, transparent 60%, var(--warm-glow) 100%)",
          mixBlendMode: "lighten",
          opacity: 0.22,
        }}
      />

      {/* Foreground inversion layer. With `--foreground-alpha: 0` (dark
          default) the layer is fully transparent and contributes nothing; with
          alpha 1 + opaque white it inverts the entire stack below it,
          producing the inverted "light mode" look without altering any
          downstream component code.

          z-200 (not 100) so it sits above every portaled UI overlay —
          sidebar tooltips, dropUp dropdowns, and modal dialogs all use
          z-[100]; portals append at the end of <body>, so equal z-index +
          later DOM order means they'd paint on top of the inversion and skip
          the flip. Inlined z-index because Tailwind's JIT scan sometimes
          drops non-default z utilities. */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0"
        style={{
          backgroundColor: "var(--foreground)",
          mixBlendMode: "difference",
          zIndex: 200,
        }}
      />

      {gpuTier > 0 && (
        <div
          aria-hidden
          className="pointer-events-none fixed inset-0 z-[201]"
          style={{
            backgroundImage:
              "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 512 512' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' fill='%23eaeaea' filter='url(%23n)' opacity='0.6'/%3E%3C/svg%3E\")",
            backgroundSize: "512px 512px",
            mixBlendMode: "color-dodge",
            opacity: "calc(0.55 * var(--noise-opacity-mul, 1))",
          }}
        />
      )}
    </>
  );
}
