// Fondos animados solo-CSS (estilo 21st.dev / Aceternity), morado de marca.
// Todos animan transform/opacity (compuestos por GPU, sin repaint por frame) y
// respetan prefers-reduced-motion. z-2, como el resto de los fondos.

const CSS = `
.clawk-bg-layer { position: fixed; inset: 0; z-index: 2; pointer-events: none; overflow: hidden; }

/* Aurora: manchas moradas difuminadas que derivan lento. */
.clawk-aurora { position: absolute; inset: -25%;
  background:
    radial-gradient(40% 50% at 20% 30%, rgba(108,79,214,0.38), transparent 70%),
    radial-gradient(45% 55% at 82% 22%, rgba(139,108,245,0.30), transparent 70%),
    radial-gradient(55% 60% at 60% 82%, rgba(76,55,160,0.32), transparent 70%);
  filter: blur(44px); will-change: transform;
  animation: clawk-aurora-drift 26s ease-in-out infinite alternate; }
@keyframes clawk-aurora-drift {
  0% { transform: translate3d(-3%, -2%, 0) scale(1.05); }
  100% { transform: translate3d(3%, 3%, 0) scale(1.16); } }

/* Beams: haces de luz diagonales que se deslizan. */
.clawk-beams { position: absolute; top: -10%; left: -30%; width: 160%; height: 120%;
  background: repeating-linear-gradient(115deg,
    transparent 0 70px, rgba(108,79,214,0.07) 70px 73px, transparent 73px 150px);
  mix-blend-mode: screen; will-change: transform;
  animation: clawk-beams-slide 22s linear infinite; }
@keyframes clawk-beams-slide { from { transform: translate3d(0,0,0); } to { transform: translate3d(150px,0,0); } }

/* Dots: grilla de puntos con respiración de opacidad. */
.clawk-dots { position: absolute; inset: 0;
  background-image: radial-gradient(rgba(108,79,214,0.40) 1.2px, transparent 1.4px);
  background-size: 22px 22px; will-change: opacity;
  -webkit-mask-image: radial-gradient(ellipse at 50% 40%, #000 40%, transparent 82%);
  mask-image: radial-gradient(ellipse at 50% 40%, #000 40%, transparent 82%);
  animation: clawk-dots-breathe 13s ease-in-out infinite; }
@keyframes clawk-dots-breathe { 0%,100% { opacity: 0.5; } 50% { opacity: 0.85; } }

@media (prefers-reduced-motion: reduce) {
  .clawk-aurora, .clawk-beams { animation: none; }
  .clawk-dots { animation: none; opacity: 0.6; }
}
`;

function Layer({ inner }: { inner: string }) {
  return (
    <div aria-hidden className="clawk-bg-layer">
      <style>{CSS}</style>
      <div className={inner} />
    </div>
  );
}

export function AuroraBackdrop() {
  return <Layer inner="clawk-aurora" />;
}

export function BeamsBackdrop() {
  return <Layer inner="clawk-beams" />;
}

export function DotsBackdrop() {
  return <Layer inner="clawk-dots" />;
}
