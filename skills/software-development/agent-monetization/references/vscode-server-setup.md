# VS Code Server + Extension Ecosystem

## Servir VS Code Web

```bash
code serve-web --accept-server-license-terms --without-connection-token \
  --port 8765 \
  --server-data-dir /root/.vscode-serve
```

Nota: NO usar `--extensions-dir` — da error `unexpected argument`. Las extensiones se instalan en el `server-data-dir` automáticamente.

## Exponer con Cloudflare tunnel

```bash
cloudflared tunnel --url http://localhost:8765
```

Sale una URL tipo `https://xxx.trycloudflare.com`. Sin auth necesaria para tunnels quick.

## Instalar extensiones .vsix

```bash
code --install-extension /ruta/extension.vsix --force
```

Las extensiones quedan en `/root/.vscode-serve/extensions/`.

## Extensiones de anuncios identificadas

| Extensión | Modelo | Split al dev |
|-----------|--------|-------------|
| **Kickbacks.dev** v0.3.175 | Ads en spinner de Claude Code / Codex | 70% |
| **AI Better Call** | Ads en barra de estado | 60% |
| **RuntimeWire** | Noticias patrocinadas en status bar | No especificado |

## Debug y troubleshooting

```bash
# Log de la extensión Kickbacks
cat ~/.vibe-ads/debug.log

# Señales clave en el log:
# "auth.signin {"ok":true}"         → sesión iniciada correctamente
# "auth.loadCached {"signedIn":true}" → sesión recuperada al reiniciar
# "preflight {"compatible":false...}" → target (CC/Codex) no encontrado
# "injectionOn":false"               → no se están inyectando anuncios
# "boot.cycle.done {"ok":false}"     → ciclo principal falló

# Location de auth tokens
cat ~/.kickbacks/auth.json          # refresh token + clientId

# Archivo de sentinelas / config
ls -la ~/.vibe-ads/
```

## ¿La extensión no muestra anuncios? Causas comunes

| Síntoma | Causa | Solución |
|---------|-------|----------|
| `target not found` | Claude Code / Codex VS Code ext no instaladas | Instalar las extensiones VS Code |
| `no_inventory` | Kickbacks no tiene anunciantes (muy nuevo) | Esperar o usar ads propios |
| `injectionOn: false` | Serving gate cerrado | No hay targets compatibles |
| `reason: "off"` | Boot cycle no activó serving | Depende de targets disponibles |
| 401 en API desde CLI | PKCE bindings del OAuth | Solo funciona desde VS Code |

## Kickbacks — Archivos relevantes en disco

| Ruta | Propósito |
|------|-----------|
| `/root/.vscode-serve/extensions/kickbacks.kickbacks-dev-0.3.175/dist/extension.js` | Código principal (262KB, minificado) |
| `/root/.vscode-serve/extensions/kickbacks.kickbacks-dev-0.3.175/dist/adapters/` | Adapters para Claude CLI, Claude Code, Codex, Codex CLI |
| `~/.kickbacks/auth.json` | Tokens de autenticación (se crea al hacer sign in) |
| `~/.kickbacks/debug.log` | Log de debug |
| `~/.vibe-ads/` | Directorio legacy (config, cache, auth) |
| `~/.vibe-ads/config.json` | Configuración (backendBaseUrl, etc.) |

## Instalar desde marketplace (sin .vsix)

```bash
code --install-extension kickbacks.kickbacks-dev
```

## Proceso completo para probar una extensión

```bash
# 1. Iniciar VS Code Server
code serve-web --accept-server-license-terms --without-connection-token \
  --port 8765 --server-data-dir /root/.vscode-serve &

# 2. Exponer con Cloudflare
cloudflared tunnel --url http://localhost:8765 &

# 3. Instalar extensión
code --install-extension kickbacks.kickbacks-dev --force

# 4. Abrir URL en navegador, iniciar sesión con GitHub
# 5. Desde VS Code Web: ejecutar comando "Kickbacks: Sign in"
```
