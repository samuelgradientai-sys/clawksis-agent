#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.28.1", "mcp>=1.27.2", "python-dotenv>=1.2.2"]
# ///
"""MCP server — Gradient Cloud WhatsApp (Meta Direct).

Exposes tools to send WhatsApp messages via the Meta Graph API, manage
conversations, check the Meta 24h service window, and list/sync templates.
Credentials (per-user WABA token + phone id) are read from Supabase
(``meta_waba_onboardings``); the server itself only needs the Supabase
service-role key in ``SUPABASE_SERVICE_ROLE_KEY``.

Namespace: ``whatsapp`` (the transactional core of the Gradient platform).
Tools carry MCP annotations (readOnly / openWorld / destructive / idempotent)
so the client can gate confirmations — every tool that reaches Meta (spends
quota / reputation) is marked ``openWorldHint``; state changes are marked
``destructiveHint``.

This is the polished single-tenant service-role server (stdio). The public
multi-tenant OAuth gateway (budget caps, per-tenant scoping, edge-function
backing) is a separate roadmap item — see the platform MCP catalog design.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from mcp.server import FastMCP

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_REF = os.environ.get("SUPABASE_PROJECT_REF", "qqmtyqxtopxedevduxxm")
SUPABASE_URL = f"https://{SUPABASE_REF}.supabase.co"
META_API_VERSION = os.environ.get("META_API_VERSION", "v22.0")
META_BASE = f"https://graph.facebook.com/{META_API_VERSION}"
DEFAULT_TEMPLATE_LANG = os.environ.get("WA_TEMPLATE_LANG", "es_CO")
WINDOW_HOURS = 24
HTTP_TIMEOUT = 15
META_TIMEOUT = 30

mcp = FastMCP("gradient-whatsapp", log_level="INFO")
logger = logging.getLogger("mcp.whatsapp")

_last_send_time = 0.0  # simple client-side rate limit (1 msg/sec)


def _require_key() -> Optional[dict]:
    """Return an error dict if the service-role key is missing, else None."""
    if not SUPABASE_KEY:
        return {
            "success": False,
            "error": "SUPABASE_SERVICE_ROLE_KEY no está configurada. "
            "Definila en ~/.clawksis/.env o el entorno del MCP.",
        }
    return None


def _sb_headers(accept_only: bool = False) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    h["Accept" if accept_only else "Content-Type"] = "application/json"
    return h


# ── Supabase REST helpers ───────────────────────────────────────────


def _sb_get(table: str, params: Optional[dict] = None) -> list:
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_sb_headers(accept_only=True),
        params=params,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _sb_post(table: str, data: dict) -> Any:
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_sb_headers(),
        json=data,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() if resp.text else {}


def _sb_patch(table: str, data: dict, filters: dict) -> Any:
    query = "&".join(f"{k}=eq.{v}" for k, v in filters.items())
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{query}",
        headers=_sb_headers(),
        json=data,
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() if resp.text else {}


# ── Domain helpers ──────────────────────────────────────────────────


def _normalize_phone(phone: str) -> str:
    """Normalize a phone to E.164 digits only (no ``+``/spaces/dashes)."""
    if not phone:
        return ""
    cleaned = phone.replace("+", "").replace(" ", "").replace("-", "")
    return cleaned if cleaned.isdigit() else ""


def _get_waba_creds(user_id: str) -> Optional[dict]:
    rows = _sb_get(
        "meta_waba_onboardings",
        {
            "user_id": f"eq.{user_id}",
            "select": "phone_number_id,business_credential,display_number,"
            "last_known_status,client,waba_id",
        },
    )
    return rows[0] if rows else None


def _get_or_create_conversation(
    user_id: str, contact_phone: str, contact_name: Optional[str] = None
) -> Optional[str]:
    phone = _normalize_phone(contact_phone)
    convs = _sb_get(
        "conversations",
        {
            "user_id": f"eq.{user_id}",
            "contact_phone": f"eq.{phone}",
            "select": "id,status",
        },
    )
    if convs:
        if convs[0].get("status") == "closed":
            _sb_patch("conversations", {"status": "open"}, {"id": convs[0]["id"]})
        return convs[0]["id"]

    _sb_post(
        "conversations",
        {
            "user_id": user_id,
            "contact_name": contact_name or phone,
            "contact_phone": phone,
            "platform": "whatsapp",
            "channel": "meta",
            "status": "open",
        },
    )
    # Supabase POST returns no body by default → fetch the id back.
    convs = _sb_get(
        "conversations",
        {
            "user_id": f"eq.{user_id}",
            "contact_phone": f"eq.{phone}",
            "select": "id",
            "order": "created_at.desc",
            "limit": "1",
        },
    )
    return convs[0]["id"] if convs else None


def _check_window(conversation_id: str) -> dict:
    convs = _sb_get(
        "conversations",
        {
            "id": f"eq.{conversation_id}",
            "select": "last_message_at,status,contact_name,contact_phone,user_id",
        },
    )
    if not convs:
        return {"in_window": False, "error": "Conversación no encontrada"}

    conv = convs[0]
    last_at_str = conv.get("last_message_at")
    now = datetime.now(timezone.utc)

    if not last_at_str:
        return {
            "in_window": False,
            "reason": "Sin mensajes previos",
            "contact": conv.get("contact_name"),
            "status": conv.get("status"),
        }

    try:
        last = datetime.fromisoformat(
            last_at_str.replace("Z", "+00:00").replace(" ", "T")
        )
    except ValueError:
        last = now - timedelta(hours=WINDOW_HOURS + 1)

    diff_hours = (now - last).total_seconds() / 3600
    in_window = diff_hours < WINDOW_HOURS
    return {
        "in_window": in_window,
        "hours_since_last": round(diff_hours, 1),
        "window_expires_in_hours": round(WINDOW_HOURS - diff_hours, 1)
        if in_window
        else 0,
        "status": conv.get("status"),
        "contact": conv.get("contact_name"),
        "last_message_at": last_at_str,
    }


def _rate_limit() -> None:
    global _last_send_time
    now = time.time()
    if now - _last_send_time < 1:
        time.sleep(1 - (now - _last_send_time))
    _last_send_time = time.time()


def _meta_post(url: str, token: str, payload: dict, retries: int = 3):
    """POST to Meta with exponential backoff on 5xx / transient (131000)."""
    delay = 1
    for i in range(retries):
        try:
            _rate_limit()
            resp = httpx.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=META_TIMEOUT,
            )
            data = resp.json()
            if resp.status_code == 200 and "error" not in data:
                return resp, data

            err = data.get("error", {})
            if resp.status_code >= 500 or err.get("code") == 131000:
                logger.warning("Retry Meta API attempt %s: %s", i + 1, err)
                time.sleep(delay)
                delay *= 2
                continue
            return resp, data
        except httpx.TimeoutException:
            logger.warning("Timeout Meta API attempt %s", i + 1)
            time.sleep(delay)
            delay *= 2
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as an error dict
            logger.error("Meta API error: %s", exc)
            return None, {"error": {"message": str(exc)}}
    return None, {"error": {"message": "Max retries reached"}}


def _register_message(
    conversation_id: str,
    user_id: str,
    text: str,
    wamid: str,
    sent_by_name: str = "MCP",
    message_type: str = "text",
) -> bool:
    try:
        _sb_post(
            "messages",
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "direction": "outbound",
                "message_type": message_type,
                "content_text": text,
                "external_id": wamid,
                "status": "sent",
                "sent_by_member_id": user_id,
                "sent_by_name": sent_by_name,
            },
        )
        _sb_patch(
            "conversations",
            {
                "last_message_preview": (text or "")[:100],
                "last_message_at": datetime.now(timezone.utc).isoformat(),
            },
            {"id": conversation_id},
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_message failed: %s", exc)
        return False


def _build_template_payload(
    to: str, template_name: str, template_params: Optional[list], text: str = ""
) -> dict:
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": DEFAULT_TEMPLATE_LANG},
        },
    }
    params = template_params
    if not params and text and text.strip() and text.strip() != template_name:
        params = [text]
    if params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            }
        ]
    return payload


def _meta_error(resp, data: dict, **extra) -> dict:
    err = data.get("error", {}) if isinstance(data, dict) else {}
    return {
        "success": False,
        "error": err.get("message", str(data)),
        "code": err.get("code"),
        "error_subcode": err.get("error_subcode"),
        **extra,
    }


# ── Tools: reads ────────────────────────────────────────────────────


@mcp.tool(annotations={"title": "Estado de líneas WABA", "readOnlyHint": True})
def get_waba_status(user_id: Optional[str] = None) -> dict:
    """Estado de las líneas WhatsApp Business (WABA): todas o la de un usuario."""
    if err := _require_key():
        return err
    params = {
        "select": "user_id,client,display_number,last_known_status,"
        "phone_number_id,waba_id"
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
    rows = _sb_get("meta_waba_onboardings", params)
    if not rows:
        return {"success": True, "wabas": [], "total": 0, "message": "Sin WABAs"}
    wabas = [
        {
            "user_id": r.get("user_id"),
            "cliente": r.get("client"),
            "numero": r.get("display_number") or "—",
            "status": r.get("last_known_status") or "pending",
            "phone_id": r.get("phone_number_id"),
            "waba_id": r.get("waba_id"),
        }
        for r in rows
    ]
    return {"success": True, "wabas": wabas, "total": len(wabas)}


@mcp.tool(annotations={"title": "Listar conversaciones", "readOnlyHint": True})
def list_conversations(
    user_id: Optional[str] = None, status: str = "open", limit: int = 20
) -> dict:
    """Lista conversaciones de WhatsApp (status open|closed), más recientes primero."""
    if err := _require_key():
        return err
    params = {
        "select": "id,user_id,contact_name,contact_phone,status,last_message_at,"
        "last_message_preview,last_outbound_at,unread_count",
        "status": f"eq.{status}",
        "order": "last_message_at.desc.nullslast",
        "limit": str(min(max(limit, 1), 50)),
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
    rows = _sb_get("conversations", params)
    return {"success": True, "conversations": rows, "total": len(rows)}


@mcp.tool(annotations={"title": "Historial de conversación", "readOnlyHint": True})
def get_conversation_messages(conversation_id: str, limit: int = 50) -> dict:
    """Historial de mensajes de una conversación (orden cronológico)."""
    if err := _require_key():
        return err
    rows = _sb_get(
        "messages",
        {
            "conversation_id": f"eq.{conversation_id}",
            "select": "id,direction,message_type,content_text,external_id,status,"
            "created_at,sent_by_name,media_url",
            "order": "created_at.asc",
            "limit": str(min(max(limit, 1), 200)),
        },
    )
    return {"success": True, "messages": rows, "total": len(rows)}


@mcp.tool(annotations={"title": "Ventana 24h de Meta", "readOnlyHint": True})
def check_window(conversation_id: str) -> dict:
    """Verifica la ventana de 24h de Meta.

    ``in_window=True`` → se puede enviar texto libre; ``False`` → solo plantillas.
    """
    if err := _require_key():
        return err
    return {"success": True, **_check_window(conversation_id)}


@mcp.tool(annotations={"title": "Estado de un mensaje", "readOnlyHint": True})
def get_message_status(wamid: str) -> dict:
    """Estado de entrega de un mensaje por su WhatsApp message id (external_id)."""
    if err := _require_key():
        return err
    rows = _sb_get(
        "messages",
        {
            "external_id": f"eq.{wamid}",
            "select": "id,conversation_id,direction,status,content_text,created_at",
            "limit": "1",
        },
    )
    if not rows:
        return {"success": False, "error": "Mensaje no encontrado", "wamid": wamid}
    return {"success": True, **rows[0]}


@mcp.tool(
    annotations={
        "title": "Listar/sincronizar plantillas",
        "readOnlyHint": True,
        "openWorldHint": True,
    }
)
def list_templates(user_id: Optional[str] = None, sync_from_meta: bool = False) -> dict:
    """Lista plantillas de WhatsApp. Con ``sync_from_meta=True`` consulta Meta en vivo.

    Args:
        user_id: filtra por usuario (requerido para sync_from_meta).
        sync_from_meta: si True, trae las plantillas directo desde la Graph API.
    """
    if err := _require_key():
        return err
    if sync_from_meta:
        if not user_id:
            return {"success": False, "error": "user_id requerido para sync_from_meta"}
        waba = _get_waba_creds(user_id)
        if not waba:
            return {"success": False, "error": f"Sin WABA para user_id={user_id}"}
        try:
            resp = httpx.get(
                f"{META_BASE}/{waba['waba_id']}/message_templates",
                headers={"Authorization": f"Bearer {waba['business_credential']}"},
                timeout=20,
            )
            return {
                "success": True,
                "source": "meta",
                "templates": resp.json().get("data", []),
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": str(exc)}

    params = {
        "select": "name,category,status,language,components,meta_template_id,user_id"
    }
    if user_id:
        params["user_id"] = f"eq.{user_id}"
    rows = _sb_get("wa_templates", params)
    templates = [
        {
            "name": t["name"],
            "category": t.get("category"),
            "status": t.get("status"),
            "language": t.get("language"),
            "meta_id": t.get("meta_template_id"),
        }
        for t in rows
    ]
    return {
        "success": True,
        "source": "db",
        "templates": templates,
        "total": len(templates),
    }


# ── Tools: sends (reach Meta → openWorldHint) ───────────────────────


@mcp.tool(
    annotations={
        "title": "Enviar WhatsApp (auto texto/plantilla)",
        "openWorldHint": True,
    }
)
def send_whatsapp(
    user_id: str,
    to: str,
    text: str,
    conversation_id: Optional[str] = None,
    force_template: bool = False,
    template_name: Optional[str] = None,
    template_params: Optional[list] = None,
    sent_by_name: str = "MCP",
) -> dict:
    """Envía un WhatsApp por la Graph API, eligiendo texto libre o plantilla.

    Herramienta principal: dentro de la ventana de 24h envía texto libre; fuera
    de ventana (o con ``force_template``) usa una plantilla aprobada. Si Meta
    rechaza el texto por ventana (131056), reintenta como plantilla.

    Args:
        user_id: UUID del dueño de la WABA.
        to: teléfono destino E.164 sin ``+`` (ej: 573202685612).
        text: texto (mensaje libre, o primer parámetro del body de la plantilla).
        conversation_id: opcional, si ya lo conocés.
        force_template: fuerza envío como plantilla.
        template_name: nombre de la plantilla (si no, se elige una aprobada).
        template_params: parámetros del body de la plantilla.
        sent_by_name: nombre del remitente para el registro.
    """
    if err := _require_key():
        return err
    waba = _get_waba_creds(user_id)
    if not waba:
        return {
            "success": False,
            "error": f"Sin credenciales WABA para user_id={user_id}",
        }
    if (
        waba.get("last_known_status") != "CONNECTED"
        and waba.get("client") != "gradient-ai"
    ):
        return {
            "success": False,
            "error": f"WABA no CONNECTED (status: {waba.get('last_known_status', 'unknown')})",
            "cliente": waba.get("client"),
        }

    to_clean = _normalize_phone(to)
    if not to_clean:
        return {"success": False, "error": "Teléfono inválido"}

    conv_id = conversation_id or _get_or_create_conversation(
        user_id, to_clean, text[:30]
    )
    window = _check_window(conv_id) if conv_id else {"in_window": False}

    use_template = force_template or (
        not window["in_window"] and window.get("reason") != "Sin mensajes previos"
    )

    if use_template and not template_name:
        rows = _sb_get(
            "wa_templates",
            {"user_id": f"eq.{user_id}", "select": "name,status"},
        )
        approved = [t for t in rows if t.get("status") in ("APPROVED", "PENDING")]
        pick = approved or rows
        if not pick:
            return {
                "success": False,
                "error": "Fuera de ventana de 24h y sin plantillas disponibles. "
                "Creá una plantilla en el Manager de Meta.",
                "window": window,
                "client": waba.get("client"),
            }
        template_name = pick[0]["name"]

    if use_template:
        payload = _build_template_payload(
            to_clean, template_name, template_params, text
        )
    else:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

    resp, data = _meta_post(
        f"{META_BASE}/{waba['phone_number_id']}/messages",
        waba["business_credential"],
        payload,
    )
    if resp is None:
        return {"success": False, "error": data.get("error", {}).get("message")}

    if resp.status_code != 200 or "error" in data:
        # Fuera de ventana (131056) → reintentar como plantilla una vez.
        if data.get("error", {}).get("code") == 131056 and not use_template:
            return send_whatsapp(
                user_id,
                to,
                text,
                conv_id,
                True,
                template_name,
                template_params,
                sent_by_name,
            )
        return _meta_error(
            resp,
            data,
            window=window,
            method_used="template" if use_template else "text",
            client=waba.get("client"),
        )

    wamid = data.get("messages", [{}])[0].get("id")
    registered = bool(
        conv_id
        and wamid
        and _register_message(
            conv_id,
            user_id,
            text,
            wamid,
            sent_by_name,
            "template" if use_template else "text",
        )
    )
    return {
        "success": True,
        "wamid": wamid,
        "client": waba.get("client"),
        "conversation_id": conv_id,
        "method_used": "template" if use_template else "text",
        "template_name": template_name if use_template else None,
        "registered_in_db": registered,
        "window": window,
    }


@mcp.tool(annotations={"title": "Enviar plantilla", "openWorldHint": True})
def send_template(
    user_id: str,
    to: str,
    template_name: str,
    template_params: Optional[list] = None,
    conversation_id: Optional[str] = None,
) -> dict:
    """Envía una plantilla aprobada (funciona incluso fuera de la ventana de 24h)."""
    if err := _require_key():
        return err
    waba = _get_waba_creds(user_id)
    if not waba:
        return {"success": False, "error": f"Sin credenciales WABA para {user_id}"}

    to_clean = _normalize_phone(to)
    if not to_clean:
        return {"success": False, "error": "Teléfono inválido"}

    payload = _build_template_payload(to_clean, template_name, template_params)
    resp, data = _meta_post(
        f"{META_BASE}/{waba['phone_number_id']}/messages",
        waba["business_credential"],
        payload,
    )
    if resp is None or resp.status_code != 200 or "error" in data:
        return _meta_error(resp, data, template_name=template_name)

    wamid = data.get("messages", [{}])[0].get("id")
    conv_id = conversation_id or _get_or_create_conversation(
        user_id, to_clean, f"[Template: {template_name}]"
    )
    if conv_id and wamid:
        _register_message(
            conv_id, user_id, f"[Template: {template_name}]", wamid, "MCP", "template"
        )
    return {
        "success": True,
        "wamid": wamid,
        "template_name": template_name,
        "conversation_id": conv_id,
    }


@mcp.tool(annotations={"title": "Enviar media", "openWorldHint": True})
def send_media(
    user_id: str,
    to: str,
    media_url: str,
    media_type: str,
    caption: Optional[str] = None,
) -> dict:
    """Envía media (image|audio|document|video) por WhatsApp (dentro de ventana 24h)."""
    if err := _require_key():
        return err
    waba = _get_waba_creds(user_id)
    if not waba:
        return {"success": False, "error": "Sin WABA"}

    to_clean = _normalize_phone(to)
    if not to_clean:
        return {"success": False, "error": "Teléfono inválido"}

    conv_id = _get_or_create_conversation(user_id, to_clean)
    window = _check_window(conv_id) if conv_id else {"in_window": False}
    if not window.get("in_window"):
        return {"success": False, "error": "Fuera de ventana de 24h", "window": window}

    payload = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": media_type,
        media_type: {"link": media_url},
    }
    if caption and media_type in ("image", "document", "video"):
        payload[media_type]["caption"] = caption

    resp, data = _meta_post(
        f"{META_BASE}/{waba['phone_number_id']}/messages",
        waba["business_credential"],
        payload,
    )
    if resp is None or resp.status_code != 200 or "error" in data:
        return _meta_error(resp, data)

    wamid = data.get("messages", [{}])[0].get("id")
    if conv_id and wamid:
        _register_message(
            conv_id, user_id, caption or f"[{media_type}]", wamid, "MCP", media_type
        )
    return {"success": True, "wamid": wamid, "conversation_id": conv_id}


@mcp.tool(
    annotations={
        "title": "Marcar como leído",
        "openWorldHint": True,
        "idempotentHint": True,
    }
)
def mark_as_read(user_id: str, message_id: str) -> dict:
    """Marca un mensaje entrante como leído en Meta (idempotente)."""
    if err := _require_key():
        return err
    waba = _get_waba_creds(user_id)
    if not waba:
        return {"success": False, "error": "Sin WABA"}
    resp, data = _meta_post(
        f"{META_BASE}/{waba['phone_number_id']}/messages",
        waba["business_credential"],
        {"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
    )
    if resp is None or resp.status_code != 200:
        return _meta_error(resp, data)
    return {"success": True}


@mcp.tool(annotations={"title": "Cerrar conversación", "destructiveHint": True})
def close_conversation(conversation_id: str) -> dict:
    """Cierra una conversación (status=closed). Se reabre sola con el próximo mensaje."""
    if err := _require_key():
        return err
    try:
        _sb_patch("conversations", {"status": "closed"}, {"id": conversation_id})
        return {"success": True}
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": str(exc)}


# ── Resources (read-only context) ───────────────────────────────────


@mcp.resource("gradient://templates/{user_id}")
def templates_resource(user_id: str) -> str:
    """Plantillas aprobadas del usuario (contexto read-only para el modelo)."""
    import json

    if not SUPABASE_KEY:
        return "SUPABASE_SERVICE_ROLE_KEY no configurada."
    rows = _sb_get(
        "wa_templates",
        {
            "user_id": f"eq.{user_id}",
            "select": "name,category,status,language,components",
        },
    )
    return json.dumps(rows, ensure_ascii=False, indent=2)


@mcp.resource("gradient://line/{user_id}")
def line_resource(user_id: str) -> str:
    """Estado/config de la línea WABA del usuario (contexto read-only)."""
    import json

    if not SUPABASE_KEY:
        return "SUPABASE_SERVICE_ROLE_KEY no configurada."
    waba = _get_waba_creds(user_id) or {}
    waba.pop("business_credential", None)  # nunca exponer el token
    return json.dumps(waba, ensure_ascii=False, indent=2)


# ── Prompts (slash-command flows) ───────────────────────────────────


@mcp.prompt()
def triage_conversation(user_id: str) -> str:
    """Flujo: revisar conversaciones abiertas y priorizar respuestas."""
    return (
        f"Revisá las conversaciones de WhatsApp abiertas del usuario {user_id}. "
        "Usá list_conversations para listarlas, check_window para ver cuáles siguen "
        "dentro de la ventana de 24h, y get_conversation_messages para el contexto "
        "de las que requieran respuesta. Resumí las que necesitan atención primero."
    )


@mcp.prompt()
def send_flow() -> str:
    """Flujo seguro para enviar un WhatsApp."""
    return (
        "Para enviar un WhatsApp: 1) confirmá el user_id (dueño de la WABA) y el "
        "teléfono destino en E.164 sin '+'. 2) Verificá la ventana con check_window. "
        "3) Dentro de ventana → send_whatsapp con texto; fuera de ventana → send_template "
        "con una plantilla aprobada (list_templates). Mostrame el mensaje antes de enviar."
    )


# ── Run ─────────────────────────────────────────────────────────────


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
