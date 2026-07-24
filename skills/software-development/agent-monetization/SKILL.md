---
name: agent-monetization
description: Monetizar coding agents (OpenCode, Claude Code, Codex) mediante publicidad durante los ciclos de "thinking" — wrapper de terminal, integración con Kickbacks, servidor VS Code Web, y modelo de impresiones.
category: software-development
triggers:
  - "quiero ganar dinero con AI coding agents"
  - "cómo monetizar opencode/claude code"
  - "kickbacks"
  - "ads en espera de agente"
  - "publicidad en coding agents"
---

# Agent Monetization

Monetizar coding agents mostrando anuncios durante el tiempo de "thinking" que el agente pasa procesando un prompt. El dev gana ~$3.50/1,000 impresiones (70% del revenue publicitario).

## Arquitectura

```
Usuario escribe prompt en wrapper
       │
       ▼
Wrapper ejecuta coding agent (OpenCode / Claude Code)
       │
       ▼
Mientras el agente "piensa", cada 5s se muestra un anuncio
       │
       ▼
Cada anuncio = 1 impresión = ~$0.0035 (neto 70%)
       │
       ▼
Impresión reportada al ad server (Kickbacks / propio)
       │
       ▼
Ad server paga vía Stripe cuando se acumula mínimo
```

## Kickbacks API (ad provider externo)

## ⚠️ REALIDAD DE KICKBACKS EN 2026

### Kickbacks NO tiene anunciantes aún

Al llamar su API incluso estando autenticado, devuelve:
```json
{"serving": {"mode": "demo", "serving": false, "reason": "no_inventory"}, "inventory": {"ads": []}}
```

No hay inventario de anuncios. La plataforma es demasiado nueva (junio 2026) y no tiene anunciantes comprando espacio. No se puede ganar dinero real con Kickbacks hoy — no hay de dónde.

### La API NO es accesible desde CLI directo

El OAuth de Kickbacks usa PKCE (Proof Key for Code Exchange) atado al client ID de la extensión VS Code. Aunque tengas el `refresh_token` en `~/.kickbacks/auth.json`, llamar al endpoint desde Python da:

```
POST /v1/auth/extension/refresh → 401 invalid_grant
POST /v1/extension/sync (signed_in) → 401 invalid_grant
```

La única forma de obtener anuncios es desde dentro del proceso de VS Code (SecretStorage). El token de accesso vive en `ctx.secrets.get('kickbacks.access')`, no es accesible desde terminal.

### La extensión solo funciona con VS Code targets

| Target | Path que busca | Resultado |
|--------|---------------|-----------|
| Claude Code VS Code ext | `anthropic.claude-code-*` → `webview/index.js` | Solo si instalada |
| Codex VS Code ext | `openai.chatgpt-*` → `webview/assets/thinking-shimmer-*.js` | Solo si instalada |
| Claude CLI | `~/.claude/settings.json` (vía `ClaudeCliStatuslineAdapter`) | Funciona parcialmente |
| Codex CLI | `/usr/local/bin/codex` (vía wrapper.sh) | Funciona parcialmente |

Si no hay targets compatibles, `boot.cycle.done` retorna `{"ok":false,"reason":"off"}` y no se inyectan anuncios.

### Diagnóstico desde debug.log

```bash
cat ~/.vibe-ads/debug.log
# Señales clave:
# auth.signin {"ok":true}  — sesión iniciada
# preflight {"compatible":false,"reason":"target not found"} — nada que parchear
# session.state {"signedIn":true,"injectionOn":false,"hasAd":false} — sin anuncios
# boot.cycle.done {"ok":false,"reason":"off"} — serving gate cerrado
```

## Backend API (solo documentación, no funcional para CLI)

```
URL base: https://disciplined-reindeer-288.convex.site
Endpoint: POST /v1/extension/sync
POST /v1/auth/extension/refresh
POST /v1/extension/events
```

### Payload de sync

```json
{
  "extension_version": "0.3.175",
  "target": {"host": "claude_code", "version": "1.0.0"},
  "client_id": "<stable-device-id>",
  "traffic_mode": "demo"
}
```

### Respuesta del server (cuando hay anuncios)

```json
{
  "inventory": {
    "ads": [{
      "ad_id": "xxx", "campaign_id": "yyy",
      "title_text": "Vercel — Despliega tu app",
      "click_url": "https://vercel.com",
      "session_token": "zzz"
    }],
    "queue_id": "qqq"
  },
  "serving": {"mode": "demo"},
  "earnings": {"mode": "signed_in", "lifetime_usd": "12.50", "today_usd": "0.42"}
}
```

### Estructura real de auth.json

```json
{"clientId": "3e33368aab1d24f3451cc7bc", "refresh": "plain:1:kr_ojZkhEtC6o37IBqurMfsNg5Lw7fbG2B-BEq6CIAHmd4"}
```

El `clientId` es el ID anónimo del dispositivo (16 chars hex, no el Google ID). El `refresh` token tiene formato `plain:1:<base64-bytes>`. NO hay `access_token` en el archivo — vive en VS Code SecretStorage.

## ad-opencode wrapper (referencia)

Script Python que envuelve `opencode run` y muestra anuncios durante el procesamiento. Ver `references/ad-opencode-wrapper.md`.

### Mecanismo

1. Ejecuta `opencode run <prompt> --model <modelo>` en subprocess
2. Timer que cada 5s muestra un anuncio (línea de estado en terminal)
3. Cuenta impresiones y calcula ganancia estimada
4. Guarda sesión en `~/.ad-opencode/sessions.jsonl`
5. Opcional: envía a Supabase para dashboard

### Variables de entorno

| Variable | Propósito |
|----------|-----------|
| `AD_MODEL` | Modelo para OpenCode (ej: `ollama/phi3:3.8b`) |
| `AD_WORKDIR` | Directorio de trabajo |
| `AD_OPTS` | Anuncios custom (JSON array) |
| `SUPABASE_SERVICE_ROLE_KEY` | Para persistir sesiones |

## Modelo de ingresos

| Métrica | Valor |
|---------|-------|
| CPM (Costo por 1,000 impresiones) | $5.00 |
| Split al dev (Kickbacks) | 70% |
| Ganancia neta por 1,000 imp. | ~$3.50 |
| Visibilidad por impresión | 5 segundos |
| Impresiones típicas por prompt | 15-30 (depende del modelo) |
| RPM (impresiones/minuto) | ~12 |

### Escenarios

| Setup | Impresiones/día | Ganancia/día |
|-------|-----------------|-------------|
| 1 dev con uso casual (2h) | ~800 | ~$2.80 |
| 1 dev uso intensivo (8h) | ~3,200 | ~$11.20 |
| 10 devs | ~32,000 | ~$112 |
| 100 devs | ~320,000 | ~$1,120 |

## VS Code Server + Cloudflare

Para probar extensiones como Kickbacks sin instalarlas localmente:

```bash
# Servir VS Code Web
code serve-web --accept-server-license-terms --without-connection-token --port 8765 --server-data-dir /root/.vscode-serve

# Exponer con Cloudflare tunnel
cloudflared tunnel --url http://localhost:8765

# Instalar extensión .vsix
code --install-extension /ruta/extension.vsix --force
```

## Skills de seguridad relacionadas

El modelo de monetización por impresiones se puede combinar con skills de ciberseguridad donde el agente revisa código y durante la revisión muestra anuncios. Ver skills relacionadas:
- `github-code-review` — code review
- `requesting-code-review` — quality gates

## Referencias

| Archivo | Contenido |
|---------|-----------|
| `references/ad-opencode-wrapper.md` | Código completo del wrapper, conexión a Kickbacks API, ejemplos de uso |
| `references/vscode-server-setup.md` | Setup de VS Code Server + Cloudflare tunnel + instalación de extensiones |

## Mecanismo de signal files (sentinel)

La extensión Kickbacks verifica archivos en `~/.vibe-ads/` para decidir qué adaptadores activar:

| Signal file | Variable env alternativa | Efecto |
|-------------|------------------------|--------|
| `~/.vibe-ads/codex.enabled` | `KICKBACKS_CODEX=1` | Activa detección de Codex VS Code ext |
| `~/.vibe-ads/codex-cli.enabled` | `KICKBACKS_CODEX_CLI=1` | Activa Codex CLI wrapper |
| `~/.vibe-ads/debug.enabled` | `KICKBACKS_DEBUG=1` | Activa debug logging |
| `~/.vibe-ads/cli.off` (ausencia = on) | — | `cliMode()` retorna "off" si existe |

Crear estos files no es suficiente si no hay targets compatibles instalados. La extensión necesita:
1. Los signal files (para habilitar los adapters CLI)
2. Que el usuario haya abierto VS Code Web al menos una vez (para que el extension host se active)
3. Un target real instalado (Claude Code VS Code ext o Codex VS Code ext)
4. Inventario de anuncios en el servidor de Kickbacks

## ~/.claude/settings.json manual (solo simulación, no conecta a Kickbacks)

Se puede configurar `~/.claude/settings.json` manualmente con:
```json
{
  "spinnerVerbs": ["ad· Estás ganando con Kickbacks"],
  "statusLineDelay": 3000
}
```
Pero esto solo cambia los verbos del spinner de Claude Code CLI. No tiene ninguna conexión con Kickbacks, no reporta impresiones, y no genera ingresos. Es solo cosmético.

## Interpretación de debug.log

```bash
# Ver señal de sign-in exitoso
cat ~/.vibe-ads/debug.log | grep "auth.signin"
# → {"ok":true}

# Ver si la inyección está activa
cat ~/.vibe-ads/debug.log | grep "session.state"
# → {"injectionOn":false,"hasAd":false}  ← NO hay anuncios

# Ver si hay targets compatibles
cat ~/.vibe-ads/debug.log | grep "preflight"
# → {"compatible":false,"reason":"target not found"}

# Ver ciclo de boot
cat ~/.vibe-ads/debug.log | grep "boot.cycle"
# → {"ok":false,"reason":"off"}  ← serving gate cerrado
```

## Ciclo de vida de la extensión

1. Extension host se inicia (cuando alguien visita VS Code Web)
2. `activate()` — detecta targets (Claude Code / Codex)
3. `loadCached()` — busca tokens de auth (SecretStorage → file fallback)
4. Si hay refresh token, intenta `refresh()` → obtiene access token
5. `boot.cycle` — inicia polling del portfolio API cada N segundos
6. Cada tick: `fetchPortfolio()` → si hay anuncio, lo inyecta en targets compatibles
7. CLI adapters (`syncCli()`) — cada segundo, parchea `~/.claude/settings.json` con el anuncio actual

Si no hay targets compatibles desde el paso 2, el ciclo nunca inicia (boot.cycle retorna inmediatamente con `reason: "off"`).

## Pitfalls

- ❗ Kickbacks no soporta OpenCode nativamente — hay que hacer wrapper manual
- ❗ Los anuncios en modo demo NO generan ganancias reales
- ❗ **La API de Kickbacks NO es accesible desde CLI** — el OAuth usa PKCE atado a la extensión VS Code. Llamadas directas dan `401 invalid_grant`
- ❗ **Kickbacks NO tiene anunciantes aún** — su API devuelve `serving: false, reason: "no_inventory"` (junio 2026). No hay de dónde pagar
- ❗ El `auth.json` NO contiene `access_token` — solo `clientId` + `refresh` con formato `plain:1:...`. El access token está en VS Code SecretStorage
- ❗ La extensión solo detecta targets si están instalados como extensiones VS Code (`anthropic.claude-code-*` o `openai.chatgpt-*`), no detecta el CLI solo
- ❗ Kickbacks depende de la UI de VS Code — el wrapper en terminal no cuenta para su tracking real
- ❗ OpenCode consume tokens de OpenRouter si no se usa modelo local gratuito
- ❗ Modelos locales lentos (CPU) generan más impresiones por prompt pero menos prompts/día
- ❗ `--extensions-dir` flag da error en `code serve-web` — no usarlo
- ❗ El ciclo de boot de la extensión falla con `"reason": "off"` si no hay targets compatibles — incluso estando logueado
- ❗ Los signal files (`codex.enabled`, `codex-cli.enabled`) no activan nada si el usuario no ha abierto VS Code Web para iniciar el extension host
- ❗ La extensión busca targets en `readdirSync` de las extensiones VS Code — necesita que `anthropic.claude-code-*` o `openai.chatgpt-*` estén instalados, no solo el CLI binario
- ❗ `OpenCode` (`opencode.exe`) no es detectado por Kickbacks porque no hay un adapter para él. No hay plan de soporte anunciado
- ❗ Restaurar `opencode.exe` requiere reinstalar npm: `npm uninstall -g @opencode-ai/cli && npm install -g @opencode-ai/cli@X.Y.Z` — el binario original es ELF 64-bit (~167MB) en `/usr/local/lib/node_modules/opencode-ai/bin/opencode.exe`
