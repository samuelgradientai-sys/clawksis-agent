import { defineConfig, type Plugin } from "vite";
import babel from "@rolldown/plugin-babel";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";

/** React Compiler preset scoped to modules that can actually contain
 *  components/hooks (JSX syntax or a react-ish import). The preset's default
 *  code filter matches any PascalCase/use* declaration — effectively every TS
 *  module — which made the babel pass parse the whole codebase. */
function compilerPreset() {
  const preset = reactCompilerPreset();
  preset.rolldown.filter.code = /\/>|<\/|from\s*['"][^'"]*react/;
  return preset;
}
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const configDir: string = fileURLToPath(new URL(".", import.meta.url));

const BACKEND = process.env.CLAWK_DASHBOARD_URL ?? "http://127.0.0.1:9119";

/**
 * In production the Python `clawk dashboard` server injects a one-shot
 * session token into `index.html` (see `clawk_cli/web_server.py`). The
 * Vite dev server serves its own `index.html`, so unless we forward that
 * token, every protected `/api/*` call 401s.
 *
 * This plugin fetches the running dashboard's `index.html` on each dev page
 * load and forwards its runtime bootstrap values into the dev HTML. No-op in
 * production builds.
 */
function clawkDevToken(): Plugin {
  const TOKEN_RE = /window\.__CLAWK_SESSION_TOKEN__\s*=\s*"([^"]+)"/;
  const EMBEDDED_RE =
    /window\.__CLAWK_DASHBOARD_EMBEDDED_CHAT__\s*=\s*(true|false)/;
  const INITIAL_PROFILE_RE =
    /window\.__CLAWK_INITIAL_PROFILE__\s*=\s*("(?:\\.|[^"\\])*")/;

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
        const initialProfileMatch = html.match(INITIAL_PROFILE_RE);
        const initialProfileJs = initialProfileMatch?.[1] ?? '""';
        return [
          {
            tag: "script",
            injectTo: "head",
            children:
              `window.__CLAWK_SESSION_TOKEN__="${match[1]}";` +
              `window.__CLAWK_DASHBOARD_EMBEDDED_CHAT__=${embeddedJs};` +
              `window.__CLAWK_INITIAL_PROFILE__=${initialProfileJs};`,
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

/**
 * Voice mode's Silero VAD model and AudioWorklet, served same-origin from
 * `/voice-vad/` (never a CDN): emitted into the build, served from
 * node_modules in dev. They are fetched by fixed name (vad-web's
 * `baseAssetPath`), so they cannot be hashed assets; the ONNX runtime's wasm
 * is, via a `?url` import in sileroSegmenter.ts.
 */
const requireFromConfig = createRequire(import.meta.url);

/** vad-web `require`s ORT's CJS build, which loads its wasm glue with a
 *  runtime `import()` of a separate .mjs; the ESM bundle build embeds it, so
 *  voice mode never depends on fetching (or failing to fetch) another module. */
const ORT_WASM_BUNDLE = path.join(
  path.dirname(requireFromConfig.resolve("onnxruntime-web/wasm")),
  "ort.wasm.bundle.min.mjs",
);

function voiceVadAssets(): Plugin {
  const files = ["silero_vad_v5.onnx", "vad.worklet.bundle.min.js"];
  const dist = path.join(path.dirname(requireFromConfig.resolve("@ricky0123/vad-web/package.json")), "dist");
  const types: Record<string, string> = { onnx: "application/octet-stream", js: "text/javascript" };
  return {
    name: "clawk:voice-vad-assets",
    configureServer(server) {
      server.middlewares.use("/voice-vad", (req, res, next) => {
        const name = (req.url ?? "").replace(/^\//, "").split("?")[0];
        if (!files.includes(name)) return next();
        res.setHeader("Content-Type", types[name.split(".").pop() ?? ""] ?? "application/octet-stream");
        res.end(readFileSync(path.join(dist, name)));
      });
    },
    generateBundle() {
      for (const name of files) {
        this.emitFile({ type: "asset", fileName: `voice-vad/${name}`, source: readFileSync(path.join(dist, name)) });
      }
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    babel({ presets: [compilerPreset()] }),
    tailwindcss(),
    clawkDevToken(),
    voiceVadAssets(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(configDir, "./src"),
      "@clawk/shared": path.resolve(configDir, "../apps/shared/src"),
      "onnxruntime-web/wasm": ORT_WASM_BUNDLE,
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
      "@react-three/fiber",
      "@observablehq/plot",
      "three",
      "leva",
      "gsap",
    ],
  },
  build: {
    outDir: "../clawk_cli/web_dist",
    emptyOutDir: true,
    // Shell stays a bit over Vite's 500 kB default after vendor splits;
    // page/xterm chunks load on demand. Keep a modest ceiling so a true
    // regression still warns.
    chunkSizeWarningLimit: 600,
    // Split heavy vendors so the first dashboard paint does not download
    // xterm/three/plot/etc. until a route actually needs them. Lazy page
    // imports in App.tsx create the route boundaries; these groups keep
    // shared node_modules out of every page chunk.
    rolldownOptions: {
      output: {
        codeSplitting: {
          minSize: 20_000,
          groups: [
            {
              name: "react-vendor",
              test: /node_modules[\\/](react|react-dom|scheduler|react-router|react-router)([\\/]|$)/,
            },
            {
              name: "xterm",
              test: /node_modules[\\/]@xterm[\\/]/,
            },
            {
              name: "three",
              test: /node_modules[\\/](three|@react-three)([\\/]|$)/,
            },
            {
              name: "plot",
              test: /node_modules[\\/]@observablehq[\\/]plot([\\/]|$)/,
            },
            {
              name: "motion",
              test: /node_modules[\\/](motion|framer-motion)([\\/]|$)/,
            },
            {
              name: "ui",
              test: /node_modules[\\/]@nous-research[\\/]ui([\\/]|$)/,
            },
            {
              // Voice mode's VAD runtime: loaded on the first voice conversation only.
              name: "voice-vad",
              test: /node_modules[\\/](@ricky0123[\\/]vad-web|onnxruntime-web|onnxruntime-common)[\\/]/,
            },
            {
              name: "vendor",
              test: /node_modules[\\/]/,
            },
          ],
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
