# gradient-whatsapp (optional MCP)

WhatsApp Business (Meta directo) para la plataforma **Gradient/Clawksis**. Server
propio bundleado en este repo (`mcp_server.py`); el `manifest.yaml` lo registra en
el catálogo de MCPs opcionales del fork.

Instalá con `clawk mcp install gradient-whatsapp` (o desde el picker). Requiere
`uv` en PATH — `uv run` resuelve las deps inline del script (PEP 723).

## Qué expone (namespace `whatsapp`)

Reads (ON por default): `get_waba_status`, `list_conversations`,
`get_conversation_messages`, `check_window`, `get_message_status`, `list_templates`.

Envíos (OFF por default — gastan cuota/reputación de Meta): `send_whatsapp`
(auto texto/plantilla según ventana 24h), `send_template`, `send_media`,
`mark_as_read`. Estado: `close_conversation` (destructivo).

Cada tool lleva anotaciones MCP (`readOnlyHint` / `openWorldHint` /
`destructiveHint` / `idempotentHint`) para que el cliente gatee confirmaciones.

Resources read-only: `gradient://templates/{user_id}`, `gradient://line/{user_id}`.
Prompts: `triage_conversation`, `send_flow`.

## Credenciales

- `SUPABASE_SERVICE_ROLE_KEY` (requerida) — lee credenciales WABA por-usuario
  desde Supabase (`meta_waba_onboardings`) y envía por la Graph API. Va a
  `~/.clawksis/.env`.
- Opcionales: `SUPABASE_PROJECT_REF`, `META_API_VERSION` (def `v22.0`),
  `WA_TEMPLATE_LANG` (def `es_CO`).

## Nota de arquitectura

Este es el server single-tenant service-role (stdio). El gateway MCP público
multi-tenant (OAuth 2.1, budget caps, scoping por tenant, backed por edge
functions) es un ítem de roadmap aparte, no este server.
