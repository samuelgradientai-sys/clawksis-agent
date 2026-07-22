import { defineConfig, type Plugin } from "vite";

import react from "@vitejs/plugin-react";

import tailwindcss from "@tailwindcss/vite";

import path from "path";



const BACKEND = process.env.CLAWK_DASHBOARD_URL ?? "http://127.0.0.1:9119";



/**

 * In production the Python `clawk dashboard` server injects a one-shot

 * session token into `index.html` (see `clawk_cli/web_server.py`). The

 * Vite dev server serves its own `index.html`, so unless we forward that

 * token, every protected `/api/*` call 401s.

 *

 * This plugin fetches the running dashboard's `index.html` on each dev page

 * load, scrapes the `window.__CLAWK_SESSION_TOKEN__` assignment, and

 * re-injects it into the dev HTML. No-op in production builds.

 */

function clawkDevToken(): Plugin {

  const TOKEN_RE = /window\.__CLAWK_SESSION_TOKEN__\s*=\s*"([^"]+)"/;

  const EMBEDDED_RE =

    /window\.__CLAWK_DASHBOARD_EMBEDDED_CHAT__\s*=\s*(true|false)/;



  return {

    name: "clawk:dev-session-token",

    apply: "serve",

    async transformIndexHtml() {

      try {

        const res = await fetch(BACKEND, { headers: { accept: "text/html" } });

        const html = await res.text();

        const match = html.match(TOKEN_RE);

        if (!match) {

          console.warn(

            `[clawk] Could not find session token in ${BACKEND} — ` +

              `is \`clawk dashboard\` running? /api calls will 401.`,

          );

          return;

        }

        const embeddedMatch = html.match(EMBEDDED_RE);

        const embeddedJs = embeddedMatch ? embeddedMatch[1] : "true";

        return [

          {

            tag: "script",

            injectTo: "head",

            children:

              `window.__CLAWK_SESSION_TOKEN__="${match[1]}";` +

              `window.__CLAWK_DASHBOARD_EMBEDDED_CHAT__=${embeddedJs};`,

          },

        ];

      } catch (err) {

        console.warn(

          `[clawk] Dashboard at ${BACKEND} unreachable — ` +

            `start it with \`clawk dashboard\` or set CLAWK_DASHBOARD_URL. ` +

            `(${(err as Error).message})`,

        );

      }

    },

  };

}



export default defineConfig({

  plugins: [react(), tailwindcss(), clawkDevToken()],

  resolve: {

    alias: {

      "@": path.resolve(__dirname, "./src"),

    },

    // When @nous-research/ui is symlinked via `file:../../design-language`,

    // Node's module resolution would pick up shared deps from

    // design-language/node_modules/*, giving us two copies + breaking

    // hooks (useRef-of-null), webgl contexts, etc. Force everything that

    // exists in BOTH places to use the dashboard's copy.

    //

    // Don't list packages here that only exist in the DS (nanostores,

    // @nanostores/react) — Vite dedupe errors out when it can't find

    // them at the project root.

    dedupe: [

      "react",

      "react-dom",

    ],

  },

  build: {

    outDir: "../clawk_cli/web_dist",

    emptyOutDir: true,

    // Pages are route-split via React.lazy (see App.tsx). On top of that, pull
    // the always-loaded vendor libs into their own cacheable chunks so the app
    // shell stays small and these rarely-changing deps survive redeploys in the
    // browser cache. We DON'T list lazy-only heavy deps (recharts, xterm) here —
    // forcing them into a manual chunk would hoist them back into the eager load;
    // Rollup already keeps them inside their dynamic page chunk.

    chunkSizeWarningLimit: 800,

    rollupOptions: {

      output: {

        manualChunks(id) {

          if (

            /[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(

              id,

            )

          ) {

            return "vendor-react";

          }

          if (/[\\/]node_modules[\\/]motion[\\/]/.test(id)) {

            return "vendor-motion";

          }

          // The design system + icon set are large and change rarely; keeping
          // them in their own chunk stops every app-shell edit from busting
          // ~405KB of cache on each `clawk update`.
          if (
            /[\\/]node_modules[\\/](@nous-research[\\/]ui|lucide-react)[\\/]/.test(id)
          ) {
            return "vendor-ui";
          }

        },

      },

    },

  },

  server: {

    proxy: {

      "/api": {

        target: BACKEND,

        ws: true,

      },

      // Same host as `clawk dashboard` must serve these; Vite has no

      // dashboard-plugins/* files, so without this, plugin scripts 404

      // or receive index.html in dev.

      "/dashboard-plugins": BACKEND,

    },

  },

});

