# MCP Server — Gradient Cloud WhatsApp

## Overview

Full Meta Direct WhatsApp MCP server. 10 tools, Python, stdio transport.

**Location:** `/root/gradient-mcp/mcp_server.py`
**Config:** `~/.clawksis/config.yaml` → `mcp_servers.gradient-whatsapp`
**Deps:** `mcp`, `httpx`, `python-dotenv` (via `uv`)
**Run:** `python3 /root/gradient-mcp/mcp_server.py`

## 10 Tools

| Tool | Description |
|------|-------------|
| `get_waba_status` | Estado de WABAs (user_id opcional) |
| `list_conversations` | Conversaciones abiertas/cerradas |
| `check_window` | Ventana 24h de Meta |
| `list_templates` | Plantillas (+ sync from Meta API) |
| `send_whatsapp` | Envía texto o template según ventana. **Auto-fallback** a template si fuera de 24h. Retry. |
| `send_media` | Imágenes, audio, documentos vía link |
| `close_conversation` | Cierra conversación en Supabase |
| `mark_as_read` | Marca como leído en Meta |
| `send_template` | Envía solo plantilla |
| `get_conversation_messages` | Historial de mensajes |

## Key Improvements (OpenCode v2)

- Retry con exponential backoff (errores 5xx, 131000, timeouts)
- Auto-fallback a template en error 131056 (fuera de ventana)
- Rate limiting (1s entre envíos vía `_last_send_time`)
- Validación de teléfonos E.164
- Logging con logging estándar
- Media support (image/audio/document via link)

## How to improve

- Añadir upload flow: POST /{phone_id}/media con multipart
- Idempotencia y dedup
- Logs estructurados a Supabase
- Manejo de webhooks entrantes
