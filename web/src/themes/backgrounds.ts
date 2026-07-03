/**
 * Catálogo de fondos del dashboard, seleccionable de forma independiente al
 * tema (igual que las fuentes). El id se persiste en localStorage y el
 * `<Backdrop />` renderiza la capa correspondiente.
 *
 * `THEME_DEFAULT_BACKGROUND_ID` ("theme") = usar el fondo por defecto del
 * tema (hoy, los paths animados de marca). Local-only, sin backend.
 */
export type BackgroundChoice = {
  id: string;
  label: string;
  description: string;
};

/** Sentinel: usar el fondo por defecto del tema (los paths de marca). */
export const THEME_DEFAULT_BACKGROUND_ID = "theme";

/** Order = display order in the picker. */
export const BACKGROUND_CHOICES: BackgroundChoice[] = [
  { id: "none", label: "Ninguno", description: "Fondo sólido, sin animación" },
  { id: "smoke", label: "Humo morado", description: "Humo WebGL — como la landing" },
  { id: "aurora", label: "Aurora", description: "Manchas moradas difuminadas que derivan" },
  { id: "beams", label: "Haces", description: "Haces de luz diagonales que se deslizan" },
  { id: "grid", label: "Grilla", description: "Grilla sutil tipo blueprint" },
  { id: "dots", label: "Puntos", description: "Grilla de puntos que respira" },
];

const BG_BY_ID: Record<string, BackgroundChoice> = Object.fromEntries(
  BACKGROUND_CHOICES.map((b) => [b.id, b]),
);

/** Look up a background by id. Returns undefined for the theme-default
 *  sentinel and for any unknown id. */
export function getBackgroundChoice(
  id: string | null | undefined,
): BackgroundChoice | undefined {
  if (!id || id === THEME_DEFAULT_BACKGROUND_ID) return undefined;
  return BG_BY_ID[id];
}

/** Whether an id refers to a real catalog background (vs theme-default). */
export function isOverrideBackground(id: string | null | undefined): boolean {
  return getBackgroundChoice(id) !== undefined;
}
