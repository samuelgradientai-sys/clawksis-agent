export { ThemeProvider, useTheme } from "./context";
export { BUILTIN_THEMES, defaultTheme } from "./presets";
export {
  FONT_CHOICES,
  THEME_DEFAULT_FONT_ID,
  getFontChoice,
  isOverrideFont,
} from "./fonts";
export type { FontChoice, FontCategory } from "./fonts";
export {
  BACKGROUND_CHOICES,
  THEME_DEFAULT_BACKGROUND_ID,
  getBackgroundChoice,
  isOverrideBackground,
} from "./backgrounds";
export type { BackgroundChoice } from "./backgrounds";
export type { DashboardTheme, ThemeLayer, ThemeListEntry, ThemeListResponse, ThemePalette } from "./types";
