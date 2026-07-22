/**
 * Grilla morada sutil tipo blueprint. CSS puro (sin JS por-frame), con un
 * masque radial para que se desvanezca en los bordes. z-2, como el resto de
 * los fondos.
 */
export function GridBackdrop() {
  const mask = "radial-gradient(ellipse at 50% 38%, #000 38%, transparent 82%)";
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[2]"
      style={{
        backgroundImage:
          "linear-gradient(to right, rgba(108,79,214,0.11) 1px, transparent 1px)," +
          "linear-gradient(to bottom, rgba(108,79,214,0.11) 1px, transparent 1px)",
        backgroundSize: "44px 44px",
        maskImage: mask,
        WebkitMaskImage: mask,
      }}
    />
  );
}
