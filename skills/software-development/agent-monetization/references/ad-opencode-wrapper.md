# ad-opencode Wrapper — Referencia de Implementación

Wrapper Python que ejecuta `opencode run` con modelo local y muestra anuncios durante el procesamiento.

## Código completo

El wrapper vive en `/usr/local/bin/ad-opencode`. Es un script Python que:

1. Ejecuta OpenCode en subprocess con pipe de stdout
2. Mientras el agente procesa, cada 5s itera sobre la lista de anuncios
3. Al terminar, muestra resumen de impresiones y ganancia estimada
4. Guarda sesión en `~/.ad-opencode/sessions.jsonl`

## Conexión a Kickbacks (modo demo)

Para obtener anuncios reales de Kickbacks (sin auth, solo vista previa):

```python
import urllib.request, json

BASE = "https://disciplined-reindeer-288.convex.site"
CLIENT_ID = "dispositivo-id-unico"

body = {
    "extension_version": "0.3.175",
    "target": {"host": "codex", "version": "1.0.0"},
    "client_id": CLIENT_ID,
    "traffic_mode": "demo"
}

req = urllib.request.Request(
    f"{BASE}/v1/extension/sync",
    data=json.dumps(body).encode(),
    headers={"content-type": "application/json"}
)
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
ad = data["inventory"]["ads"][0]
print(f"📢 {ad['title_text']} — {ad['click_url']}")
```

## ⚠️ Conexión a Kickbacks — NO FUNCIONAL desde CLI

**Hallazgo real (junio 2026):** La API de Kickbacks usa PKCE (Proof Key for Code Exchange)
atado al client ID de la extensión VS Code. Incluso estando logueado, las llamadas desde
Python/CLI fallan con `401 invalid_grant`.

### Estructura real de auth.json

```json
{"clientId":"3e33368aab1d24f3451cc7bc","refresh":"plain:1:kr_ojZkhEtC6o37IBqurMfsNg5Lw7fbG2B-BEq6CIAHmd4"}
```

- `clientId`: ID anónimo del dispositivo (16 chars hex)
- `refresh`: refresh token con formato `plain:1:<bytes>` 
- **NO hay `access_token`** — vive en VS Code SecretStorage (`ctx.secrets.get('kickbacks.access')`)

### Llamada que devuelve 401

```python
# refresh endpoint → 401 invalid_grant
body = {"refresh_token": "plain:1:..."}
resp = POST /v1/auth/extension/refresh

# sync endpoint con refresh en body → 401 invalid_grant
body = {"traffic_mode": "signed_in", "refresh_token": "plain:1:...", ...}
resp = POST /v1/extension/sync
```

### Demo mode (funciona pero sin anuncios)

```python
body = {
    "extension_version": "0.3.175",
    "target": {"host": "codex", "version": "codex/0.0.1"},
    "client_id": "3e33368aab1d24f3451cc7bc",
    "traffic_mode": "demo"
}
# → 200 OK, pero:
# {"serving": {"mode": "demo", "serving": false, "reason": "no_inventory"}, "inventory": {"ads": []}}
```

Kickbacks NO tiene anunciantes aún en junio 2026 — no hay inventario que mostrar.

### VS Code Server: cómo se autentica uno

```bash
# 1. Iniciar VS Code Web (extensión Kickbacks pre-instalada)
code serve-web --accept-server-license-terms --without-connection-token \
  --port 8765 --server-data-dir /root/.vscode-serve

# 2. Exponer con Cloudflare tunnel
cloudflared tunnel --url http://localhost:8765

# 3. Abrir URL en navegador, iniciar sesión GitHub (para Copilot)
# 4. Ctrl+Shift+P → "Kickbacks: Sign in" → Google OAuth
# 5. auth.json se genera automáticamente

# Verificar estado de la extensión
cat ~/.vibe-ads/debug.log
# Buscar: auth.signin {"ok":true}
```

## Estructura de ~/.ad-opencode/

```
~/.ad-opencode/
├── device_id          # ID único del dispositivo (16 chars hex)
└── sessions.jsonl     # Historial de sesiones (JSON lines)
```

### Formato de sessions.jsonl

```json
{"ts": "2026-06-25T20:04:00Z", "session_id": "abc123", "device_id": "def456", "prompt": "say hello", "model": "ollama/qwen2.5-coder:1.5b", "seconds": 85, "impressions": 17, "earnings": 0.0595}
```

## Comandos útiles

```bash
# Probar que funciona
ad-opencode "say hello"

# Usar con modelo diferente
AD_MODEL="ollama/phi3:3.8b" ad-opencode "tu prompt"

# Anuncios custom (para promocionar servicios propios)
AD_OPTS='[{"text":"Mi servicio","url":"https://..."}]' ad-opencode "prompt"

# Ver historial
cat ~/.ad-opencode/sessions.jsonl

# Calcular ganancia total
cat ~/.ad-opencode/sessions.jsonl | python3 -c "import sys,json; print(sum(j['earnings'] for j in (json.loads(l) for l in sys.stdin)))"
```
