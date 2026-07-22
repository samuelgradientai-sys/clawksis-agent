import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
// `fonts.css` + `globals.css` are pulled in via CSS `@import` inside
// `index.css` (NOT here): Tailwind v4 only resolves `@apply` against the
// design system when the DS stylesheet shares the same CSS root as
// `@import 'tailwindcss'`. Importing them as separate JS modules gives them
// an isolated context where `@apply p-4` errors with "unknown utility class".
import "./index.css";
import App from "./App";
import { SystemActionsProvider } from "./contexts/SystemActions";
import { I18nProvider } from "./i18n";
import { exposePluginSDK } from "./plugins";
import { ThemeProvider } from "./themes";
import { CLAWK_BASE_PATH } from "./lib/api";

// Expose the plugin SDK before rendering so plugins loaded via <script>
// can access React, components, etc. immediately.
exposePluginSDK();

// Recover open tabs after a server-side rebuild (`clawk update` / auto-mejora):
// hashed chunk filenames change and the old ones are deleted, so a pending
// lazy route import 404s and the router transition never commits — the URL
// changes but the view stays frozen until a manual refresh. Vite emits
// `vite:preloadError` for exactly this; reload once to pick up the fresh
// index.html. The timestamp guard prevents a reload loop when the server is
// genuinely broken (let the error surface instead).
window.addEventListener("vite:preloadError", (event) => {
  const KEY = "clawk-chunk-reload-at";
  const last = Number(window.sessionStorage.getItem(KEY) || 0);
  if (Date.now() - last < 30_000) return;
  window.sessionStorage.setItem(KEY, String(Date.now()));
  event.preventDefault();
  window.location.reload();
});

createRoot(document.getElementById("root")!).render(
  <BrowserRouter basename={CLAWK_BASE_PATH || undefined}>
    <I18nProvider>
      <ThemeProvider>
        <SystemActionsProvider>
          <App />
        </SystemActionsProvider>
      </ThemeProvider>
    </I18nProvider>
  </BrowserRouter>,
);
