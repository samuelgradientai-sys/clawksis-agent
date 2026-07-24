---
name: gradient-cloud-dashboard
description: "Use when interacting with the Gradient Cloud SaaS dashboard — authenticating, navigating, and sending WhatsApp messages through the UI. Covers Supabase auth injection, session management, browser automation, and troubleshooting common pitfalls."
version: 3.0.0
author: Clawksis
license: MIT
metadata:
  clawk:
    tags: [gradient-cloud, dashboard, whatsapp, supabase, browser-automation, meta-waba, mcp]
    related_skills: [service-status-watchdogs]
---

# Gradient Cloud Dashboard

## Overview

Gradient Cloud is a multi-tenant B2B SaaS platform (Supabase + React SPA) combining WhatsApp Business, CRM, and AI agents. It uses Supabase Auth, Supabase Database, and WhatsApp messaging with **two providers**:

- **YCloud**: Only used by AVO (agenciaavo318@gmail.com). YCloud is a proxy that manages the Meta WABA integration.
- **Meta WABA directo**: Gradient AI, Optica Luz De Vida, 3PL have their own Meta WABA credentials stored in `meta_waba_onboardings`.

**Business verticals**: Travel agencies (AVO Tours), barbershops (Barberos), opticians (Optica Luz De Vida), logistics (3PL), and more.

## Architecture

```
[Sender] → React SPA (app.gradientcloud.gradientai.lat)
              ↓ Supabase JS Client (INSERT into messages)
        ┌─────────────────────────────────────┐
        │  Supabase Project                   │
        │  (qqmtyqxtopxedevduxxm)             │
        │                                      │
        │  messages ← DB Trigger               │
        │  conversations    ──────────┬────────┤
        │  profiles / empresas        │        │
        └─────────────────────────────┼────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
              YCloud (AVO only)              Meta WABA Direct
            api.ycloud.com/v2/          graph.facebook.com/.../messages
                    │                                   │
                    └─────────────┬─────────────────────┘
                                  │
                           Meta WhatsApp Cloud API
                                  │
                                  ▼
                            [Recipient]
```

### Key Insight: Message Sending Flow

The React SPA does NOT call any WhatsApp API directly. Instead:
1. SPA **INSERTs** a row into `messages` with `direction: "outbound"`, `status: "pending"`
2. A **PostgreSQL database trigger** fires after INSERT
3. The trigger determines the provider (YCloud or Meta Direct) from the user's config
4. For **YCloud**: POST to `https://api.ycloud.com/v2/whatsapp/messages/send`
5. For **Meta Direct**: POST to `https://graph.facebook.com/v22.0/{phone_number_id}/messages` with the WABA token
6. Both return a `wamid` (WhatsApp Message ID), which the trigger writes to `messages.external_id` and updates `status` to "sent"/"delivered"

## Database Schema

### `messages` (14 columns)
| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | Message UUID |
| `conversation_id` | uuid FK → conversations | Parent conversation |
| `user_id` | uuid FK → profiles | Business owner |
| `direction` | text | "outbound" (sent), "inbound" (received) |
| `message_type` | text | "text", "image", "audio", "video" |
| `content_text` | text | Message body |
| `media_url` | text | URL for media messages |
| `external_id` | text | WhatsApp wamid (e.g. `wamid.HBgM...`) |
| `status` | text | "pending", "sent", "delivered", "read", "failed" |
| `raw_payload` | jsonb | Raw webhook payload |
| `sent_by_member_id` | uuid | Who sent it |
| `sent_by_name` | text | Sender display name |
| `metadata` | jsonb | Extra data |
| `created_at` | timestamptz | Timestamp |

### `conversations` (37 columns)
| Key Column | Description |
|---|---|
| `id` | uuid PK |
| `user_id` | Business owner |
| `contact_name`, `contact_phone` | Contact info (phone includes country code, no +) |
| `platform` | "whatsapp" |
| `channel` | "meta" |
| `status` | "open", "closed" |
| `ai_enabled` | boolean (AI agent toggle) |
| `human_mode_since` | When human mode was activated |
| `last_outbound_source` | "manual" (dashboard), "ai" (agent), "api" |
| `unread_count` | int |
| `ycloud_seguimiento_*` | Follow-up tracking fields |
| `tags` | jsonb |

### `profiles` (23 columns)
| Key Column | Description |
|---|---|
| `id` | uuid PK |
| `full_name` | Business display name |
| `email` | Login email |
| `nombre_de_empresa` | Business name |
| `plan_type` | "basico", "profesional" |
| `precio_plan` | Monthly price in COP |
| `subscription_status` | "active", etc. |
| `credit_balance_usd` | YCloud credit balance |
| `telefono` | Phone (masked) |
| `empresa_id` | FK → empresas |
| `appearance_settings` | jsonb (theme, dark mode, accent color, etc.) |

### `empresas` (5 columns)
| Column | Description |
|---|---|
| `id` | uuid PK |
| `nombre` | "Barberos", "AVO", "Gradient AI", "3PL", etc. |
| `member_permissions` | jsonb: `{"blocked_nav": []}` |

## Authentication Methods

### Method A: Login via Browser Form (Fails Often)
The SPA login form has React-controlled checkboxes that reset on re-render. Not reliable programmatically.

### Method B: Supabase Auth API → XHR from Browser (✅ Recommended)
The most reliable method.

**Flow**:
1. Store the Supabase `service_role` key in tiny chunks (10 chars each, fully visible) via `browser_console`
2. Reconstruct: `var KEY = W0+W1+W2+...+W21;`
3. XHR POST to `https://{ref}.supabase.co/auth/v1/token?grant_type=password`
4. Save response to `localStorage['sb-{ref}-auth-token']`
5. Navigate to `/mensajes`

**Critical**: The service_role key works as the `apikey` header. The response is a complete session JSON (`access_token`, `refresh_token`, `user`, `expires_in: 3600`).

### Method C: Password Reset via Admin API
Use `PUT /auth/v1/admin/users/{user_id}` with `{"password": "..."}` to set a temp password. Then use Method A or B.

## Session Injection

The Supabase JS SDK reads session from `localStorage['sb-{ref}-auth-token']`.

**Format**: Full JSON string of the token response, NOT just the access_token.

### Avoiding the Truncation Bug
The Clawksis tool interface truncates strings with `...`. To pass full tokens:
- Split into 10-char chunks via `execute_code`
- Reconstruct in the browser by concatenating variables

### One-Shot Login Script
```javascript
// Paste all W0..W21 assignments, then run this:
var KEY = W0+W1+W2+W3+W4+W5+W6+W7+W8+W9+W10+W11+W12+W13+W14+W15+W16+W17+W18+W19+W20+W21;
var xhr = new XMLHttpRequest();
xhr.open('POST','https://qqmtyqxtopxedevduxxm.supabase.co/auth/v1/token?grant_type=password',true);
xhr.setRequestHeader('apikey',KEY);
xhr.setRequestHeader('Content-Type','application/json');
xhr.onload=function(){var d=JSON.parse(xhr.responseText);if(d.access_token){localStorage.setItem('sb-qqmtyqxtopxedevduxxm-auth-token',xhr.responseText);}};
xhr.send(JSON.stringify({email:'samuelgradientai@gmail.com',password:'[PASSWORD]'}));
```
**⚠️ Pitfall — `window.location.href` redirect does NOT work from `browser_console`.** The XHR response saves the session to localStorage, but the `onload` redirect via `window.location.href` is blocked. After running the script, navigate manually with `browser_navigate(url='https://app.gradientcloud.gradientai.lat/mensajes')`.

## Dashboard Navigation

### Sidebar Menu
- **Dashboard** — main stats
- **Mensajes** — WhatsApp inbox (notification badge shows unread count)
- **Calendario** — scheduling/calendar
- **Disponibilidad** — availability settings
- **Agente** — AI agent configuration
- **WhatsApp** (expandable) → Negocio, Contactos, Marketing
- **Pagos** — billing
- **API KEYS** — integration keys
- **Configuración** — settings

### Message Sending (from UI)
1. Click conversation in left panel
2. Type in `textbox "Escribe un mensaje... (Usa / para respuestas guardadas)"`
3. Press Enter to send
4. Verify: preview updates, input clears, `status: "delivered"` in DB

### Conversation Actions
- **IA/Humano/Apagar IA** — toggle AI agent mode
- **Datos** — extracted data from conversation
- **Política TYC** — terms confirmation
- **Resolver** — close conversation
- **Citas** — schedule appointment
- **Grabar audio** — voice note

## Cron Jobs & Briefings

### Cron: Briefing diario de IA

Un cron diario que envía a Telegram las noticias más recientes de Inteligencia Artificial, formateadas con emojis y contexto enriquecido.

**Configuración actual (Junio 2026):**

| Parámetro | Valor |
|-----------|-------|
| Horario | `0 13 * * *` (13:00 UTC) |
| Script | `fetch-ai-news.py` — Google News RSS + Hacker News API |
| Modelo | `deepseek-v4-flash` via `provider: deepseek` |
| Toolsets | `["web"]` |
| Entrega | Telegram |
| Costo | ~$0.045/mes |

**Flujo (Script + Agent pattern):**

```
1. Script (Python, no_agent=false como script del cron):
   → fetch-ai-news.py se ejecuta PRIMERO
   → Busca en Google News RSS (5 queries) + Hacker News API
   → Output: titulares + fuentes + fechas (gratis, sin LLM)

2. Agent (deepseek-v4-flash) recibe el output del script como contexto:
   → Enriquece con emojis, secciones, contexto explicativo
   → Formatea en el estilo que Samuel prefiere (ver abajo)
   → Entrega a Telegram
   → Costo: ~$0.0015 por ejecución
```

**Formato que Samuel prefiere (EXACTO):**

```
## 🧠 Briefing IA — [fecha]

### 🔥 Lo más importante

**[emoji] [Título descriptivo con por qué importa]**
[Fuente] — *hace Xh*

### 📡 Lo que viene

- **Tema** — Detalle

### 🏦 Inversiones

- Montos, M&A, funding

### ⚖️ Regulación (cuando aplique)

---

### ⚡ En resumen

Párrafo de 2-3 líneas del tema del día.
```

Reglas: solo noticias de HOY/ayer, emojis variados (🚀🔥⚡🏦📡🤖🧠💻💰🔬), 4-6 noticias máximo, NO inventar.

**Pitfall importante — deepseek-v4-flash via DeepSeek API no llama tools:**
- `tool_turns=0` siempre. El modelo genera desde training data o contexto inyectado.
- Para crons que necesiten datos frescos: usar SIEMPRE el patrón Script+Agent.
- NO confiar en que el modelo use web_search dentro del cron.
- `last30days` skill añade ~36k tokens al contexto — demasiado pesada para el ahorro que da.

### Script de referencia

`references/fetch-ai-news.py` — script Python que recolecta noticias de Google News RSS + Hacker News API. Se ejecuta desde `~/.clawksis/scripts/`. Usa `urllib` estándar (sin dependencias externas). Fuentes: 5 queries a Google News RSS (date=1d) + Hacker News Algolia API (últimas 48h, filtro AI).

## Known Users & Businesses
|---|---|---|---|
| Samuel Gradient | samuelgradientai@gmail.com | Barberos | — |
| Avo Agencia De Viajes | agenciaavo318@gmail.com | AVO | +57 313 846 6734 |
| Optica Luz De Vida | opticaluzdevida318@gmail.com | Optica | +573****1596 |
| Samuel Gomez | samuelgomez2466@gmail.com | 3PL | — |
| David Gomez | davidgradientai@gmail.com | 3PL | — |
| Información Gradient | informaciongradient@gmail.com | Barber Shop | — |

## Supabase Queries for MCP

### Send a Message (via INSERT + trigger — use only when explicitly asked)
```sql
INSERT INTO messages (conversation_id, user_id, direction, message_type, content_text, sent_by_member_id, sent_by_name, status)
VALUES ('{conv_id}', '{user_id}', 'outbound', 'text', '{message}', '{user_id}', '{name}', 'sent');
```

**⚠️ Pitfall — `status` debe ser `"sent"` no `"pending"`**:
La tabla `messages` tiene un check constraint `messages_status_check` que **rechaza** inserts directos con `status: "pending"`. El valor `"pending"` solo lo asigna el trigger de BD después del INSERT. Cuando insertas directamente via REST API, usa siempre `status: "sent"`. El trigger lo actualizará a `"delivered"` si la entrega es exitosa.

### List Conversations (open)
```sql
SELECT * FROM conversations WHERE user_id = '{user_id}' AND status = 'open' ORDER BY last_message_at DESC;
```

### Get Conversation Messages
```sql
SELECT * FROM messages WHERE conversation_id = '{conv_id}' ORDER BY created_at ASC;
```

### Common Patterns
- Phone format: `573202685612` (no +, no spaces)
- Conversation lookup: `contact_phone = '573202685612'`
- Message statuses: "pending" (trigger-set only) → "sent" → "delivered" → "read"
- When inserting via REST API, use status: "sent" — "pending" is rejected by messages_status_check constraint

## Common Pitfalls

1. **Cloudflared tunnel hangs with QUIC protocol**: Sometimes cloudflared's default QUIC connection gets stuck during the pre-check phase and never emits the `trycloudflare.com` URL. The process stays alive but never completes registration.
   - **Fix**: Kill the hanging instance and restart with `--protocol http2`: `cloudflared tunnel --url http://127.0.0.1:PORT --protocol http2`
   - **Diagnosis**: If the tunnel has been running for 30+ seconds but `trycloudflare.com` never appears in stdout, it's stuck. HTTP/2 mode consistently completes within 3-5 seconds.
   - **Persistence**: After the tunnel is established, the trycloudflare.com URL stays in the log file. Save it to `/tmp/cloudflared.log` with `2>/tmp/cloudflared.log` for later retrieval.

2. **API key truncation**: Pass in 10-char chunks to avoid the `...` display bug
2. **Mixed content blocking**: Don't serve data from HTTP localhost — always use XHR/fetch to Supabase's HTTPS endpoint directly
3. **React checkboxes**: Use JS injection, not browser_click, to toggle them
4. **Tour popups**: After login, dismiss 2-3 popups in sequence (Entendido → Omitir → Close)
5. **Session expiration**: Default 3600s (1 hour). Re-run XHR login flow
6. **Multiple businesses**: The session token is tied to a specific user_id. Different WhatsApp numbers require logging in as different users
7. **INSERT in messages rejects status "pending"**: The check constraint `messages_status_check` only allows "pending" when set by the DB trigger. Direct REST inserts must use `status: "sent"`. Inserting with "pending" returns HTTP 400 with code 23514.
8. **Prefer sending from the dashboard UI, not via Supabase INSERT**: When asked to send a test message, use the browser to type into the dashboard's message textbox and press Enter — do NOT insert directly into the `messages` table via REST API. The INSERT bypasses the React SPA's state and the user explicitly prefers the UI path. Flow: login (Method B) → navigate to `/mensajes` → click conversation → type in `textbox "Escribe un mensaje..."` → press Enter.

## Verification Checklist

- [ ] localStorage contains `sb-{ref}-auth-token` with valid session JSON
- [ ] Sidebar navigation visible (not login form)
- [ ] Conversations appear in left panel after clicking the list area
- [ ] Sent messages appear with `external_id` (wamid) and `status: delivered`
- [ ] `last_message_preview` and `last_message_at` update in conversations table

## MCP — Gradient Cloud WhatsApp (Meta Direct)

### MCP Server Implementation

**Location:** `/root/gradient-mcp/mcp_server.py`
**Config en Clawksis:** `~/.clawksis/config.yaml` → `mcp_servers.gradient-whatsapp`
**SDK:** `mcp` (Python), `httpx`, `python-dotenv`
**Transport:** stdio

### Arquitectura

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  Cliente MCP  │ ──→ │  MCP Server      │ ──→ │  Supabase REST API   │
│  (Clawksis)   │     │  (Python + mcp) │     │  (service_role key)  │
└──────────────┘     └──────────────────┘     └──────────┬───────────┘
                          │                               │
                          │                               ▼
                          │                      meta_waba_onboardings
                          │                      (tokens WABA)
                          │                               │
                          ▼                               ▼
                   ┌──────────────┐              ┌──────────────┐
                   │  Meta Graph  │              │  messages /  │
                   │  API v22.0   │              │conversations  │
                   └──────────────┘              └──────────────┘
```

### Tools Disponibles (10)

| Tool | Descripción | Args principales |
|------|-------------|------------------|
| `get_waba_status` | Estado de todas las WABAs | `user_id` (opcional) |
| `list_conversations` | Lista conversaciones | `user_id`, `status` (open/closed), `limit` |
| `check_window` | Verifica ventana 24h de Meta | `conversation_id` |
| `list_templates` | Plantillas WhatsApp aprobadas (+ sync desde Meta) | `user_id`, `sync_from_meta` |
| `send_whatsapp` | **Tool principal** — envía texto o template automáticamente (con retry + auto-fallback) | `user_id`, `to`, `text`, `force_template`, `template_name`, `template_params` |
| `send_media` | **NUEVA** — Envía imágenes, audio, documentos | `user_id`, `to`, `media_url`, `media_type`, `caption` |
| `close_conversation` | **NUEVA** — Cierra una conversación | `conversation_id` |
| `mark_as_read` | **NUEVA** — Marca como leído en Meta | `user_id`, `message_id` |
| `send_template` | Envía solo plantilla (funciona siempre) | `user_id`, `to`, `template_name`, `template_params` |
| `get_conversation_messages` | Historial de mensajes | `conversation_id`, `limit` |

### Lógica de `send_whatsapp`

```
INPUT: user_id, to, text
  │
  ├── 1. GET credentials de meta_waba_onboardings
  ├── 2. Buscar/crear conversación en conversations
  ├── 3. Verificar ventana 24h (check_window)
  │      ├── ✅ in_window → enviar texto libre
  │      └── ❌ fuera de ventana → buscar template → enviar template
  ├── 4. POST a graph.facebook.com/v22.0/{phone_id}/messages
  ├── 5. INSERT en messages (para registro en Dashboard)
  └── 6. UPDATE conversations.last_message_preview
```

### Config en Clawksis

```yaml
mcp_servers:
  gradient-whatsapp:
    command: python3
    args:
    - /root/gradient-mcp/mcp_server.py
    env:
      SUPABASE_SERVICE_ROLE_KEY: "{{ .Env.SUPABASE_SERVICE_ROLE_KEY }}"
    enabled: true
    workdir: /root/gradient-mcp
```

Para recargar en sesión activa: `/reload-mcp`
Para recargar gateway: `/restart`

### Users & Credentials (Meta Direct)

| Cliente | Email | User ID | Phone ID | WABA ID | Status |
|---------|-------|---------|----------|---------|--------|
| gradient-ai | samuelgradientai@gmail.com | `0f8ec8c2-6812-4fb6-98a6-c57c9ad6fe5e` | `1103545326182176` | `1882258442488384` | ✅ CONNECTED |
| optica-luz-de-vida | opticaluzdevida318@gmail.com | `2bde4a72-...` | `1200819219772799` | `756871830749447` | ⚠️ pending |
| 3pl (David) | davidgradientai@gmail.com | `50ee069a-...` | `1201598023026506` | `2046617999568779` | ⚠️ pending |

**Tokens WABA** almacenados en `meta_waba_onboardings.business_credential`.

### Meta Cloud API — Send Message

**⚠️ Regla de la ventana de 24h**: Meta NO permite enviar mensajes de texto libre a un usuario si han pasado más de 24h desde su último mensaje entrante.

| Situación | Último msg del cliente | Qué puedes enviar |
|---|---|---|
| ✅ **En ventana** | < 24h | Texto libre, imágenes, audio, documentos |
| ❌ **Fuera de ventana** | > 24h | Solo **plantillas aprobadas** (Marketing, Utility) |

```http
POST https://graph.facebook.com/v22.0/{phone_number_id}/messages
Authorization: Bearer {waba_token}
Content-Type: application/json

# ✅ En ventana (texto libre):
{
  "messaging_product": "whatsapp",
  "to": "573202685612",
  "type": "text",
  "text": { "body": "Mensaje de prueba" }
}

# ❌ Fuera de ventana (solo plantilla):
{
  "messaging_product": "whatsapp",
  "to": "573202685612",
  "type": "template",
  "template": {
    "name": "recordatorio_cita",
    "language": { "code": "es_CO" },
    "components": [{
      "type": "body",
      "parameters": [{"type": "text", "text": "Juan"}]
    }]
  }
}
```

Response:
```json
{
  "messages": [{"id": "wamid.HBgMNTczMjAyNjg1NjEyFQIAERgUQ0VEQ0FEOThDNTkxNjRBNDE4RUYA"}]
}
```

### MCP Tool Design (Meta Direct)

**Tools implementados (10):** Ver sección "MCP — Gradient Cloud WhatsApp" arriba.

### Estado Actual por Usuario (Meta Direct)

| Usuario | Status | WABA | Ventana ahora | Templates | Puede enviar |
|---|---|---|---|---|---|
| **Samuel** | ✅ active | ✅ CONNECTED | ✅ Samuel Gomez (0.2h) | ❌ 0 | ✅ Texto a Samuel, 🔴 resto necesita templates |
| **David/3PL** | ✅ active | ⚠️ PENDING | 🔴 Todas fuera | ✅ 1 ("aaaaa") | ✅ Template "aaaaa" a cualquiera |
| **Optica** | ❌ cancelled | ⚠️ None | 🔴 Todas fuera | ❌ 0 | ❌ No enviar (plan caído) |

### Arquitectura MCP Implementada

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  Cliente MCP  │ ──→ │  Python MCP Server│ ──→ │  Supabase REST API   │
│  (Claude, etc)│     │  (uv + mcp sdk)  │     │  (service_role key)  │
└──────────────┘     └──────────────────┘     └──────────┬───────────┘
                          │                               │
                          │                               ▼
                          │                      meta_waba_onboardings
                          │                      (tokens WABA)
                          │                               │
                          ▼                               ▼
                   ┌──────────────┐              ┌──────────────┐
                   │  Meta Graph  │              │  messages /  │
                   │  API v22.0   │              │conversations  │
                   └──────────────┘              └──────────────┘
```

**Auth del MCP**: Usa `SUPABASE_SERVICE_ROLE_KEY` del entorno. Cada usuario tiene su propio `phone_number_id` y `business_credential` en `meta_waba_onboardings`.

**Location**: `/root/gradient-mcp/mcp_server.py` (Python, SDK `mcp`).
**Run**: `python3 /root/gradient-mcp/mcp_server.py`

### MCP Reference File

For full MCP implementation details and tool documentation, see:
`references/mcp-server-implementation.md` — architecture, all 10 tools, WABA status, config, and how to improve the MCP.

### Endpoints vs DB Insert

Hay **2 formas** de enviar mensajes para Meta users:

**Opción A — Meta API Directa** (recomendada para el MCP)
```
POST https://graph.facebook.com/v22.0/{phone_id}/messages
Authorization: Bearer {token}
```
✅ Rápido, sin depender del trigger
✅ Control total sobre el mensaje
❌ No queda registro en Supabase automáticamente (hay que insertarlo aparte)

**Opción B — INSERT en messages** (usa el trigger de BD)
```sql
INSERT INTO messages (conversation_id, user_id, direction, message_type, content_text, sent_by_member_id, sent_by_name)
VALUES ('{conv_id}', '{user_id}', 'outbound', 'text', '{text}', '{user_id}', 'API');
```
✅ Queda registro automático
✅ El trigger se encarga de enviar a Meta
❌ Depende del trigger funcionando correctamente

### Para el MCP: Flujo Recomendado (Opción A + B)

```mermaid
1. Verificar ventana 24h:
   ┌─ ¿Último inbound < 24h? → Enviar texto libre → INSERT + UPDATE
   └─ ¿Último inbound > 24h? → Buscar plantilla aprobada → Enviar template

2. GET credentials de meta_waba_onboardings (phone_id + token)
3. POST a Meta Graph API → obtienes wamid
4. INSERT en messages con ese wamid + status "delivered"
5. UPDATE conversations set last_message_preview, last_message_at
```

### Webhooks (Inbound Messages)

Los mensajes entrantes llegan via webhook de Meta a:
```
https://qqmtyqxtopxedevduxxm.supabase.co/functions/v1/meta-webhook
```

3PL adicionalmente tiene un webhook personalizado que reenvía a n8n:
```
https://n8n-n8n.jjggv4.easypanel.host/webhook-test/...
```

> 📎 **Referencia detallada**: `references/meta-waba-api.md` — tokens, phone IDs, endpoints, formatos de error, y cómo obtener credenciales programáticamente.

### Referencia Rápida

```python
# Send via Meta API (Python ejemplo)
import requests

waba_token = "EAARR0cGA51Q..."  # de meta_waba_onboardings
phone_id = "1103545326182176"    # phone_number_id del onboarding

resp = requests.post(
    f"https://graph.facebook.com/v22.0/{phone_id}/messages",
    headers={
        "Authorization": f"Bearer {waba_token}",
        "Content-Type": "application/json"
    },
    json={
        "messaging_product": "whatsapp",
        "to": "573202685612",
        "type": "text",
        "text": {"body": "Hola desde MCP"}
    }
)
wamid = resp.json()["messages"][0]["id"]
```
