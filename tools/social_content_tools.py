"""Agent-callable social media content generation for travel agencies.

Lets the agent generate publishable content for Instagram, TikTok, and YouTube
based on a persistent ``business_profile`` (set up once per user) — no need
to re-explain the agency's tone, destinations, or hashtags on every request.

Pipeline (per request):
  1. Load business_profile from ``state.db`` (table ``business_profiles``)
  2. Generate caption + hashtags using LLM with profile context
  3. Search Unsplash for a relevant background photo
  4. Render text overlay with PIL + DejaVu Sans Bold
  5. Resize for each target network (IG 1080×1350, TikTok 1080×1920, YT 1280×720)
  6. Package as .zip in outputs/ + return download link

Design references:
  • docs/feature-redes-sociales-2026-06.md (brief + 5 decisions)
  • docs/concept-images/bali-concept-validated-2026-06-30.jpg (visual ref)
  • Schema: clawk_state.SCHEMA_SQL → table ``business_profiles`` (23 cols)

This file (PASO B): stubs for the 4 main tools. Implementation lands in PASO C
(setup/get) and PASO D (generate). Each stub returns a "TODO" message so the
registry registers them and the agent can SEE them — but they don't do work yet.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# HELPERS internos (privados — no se exponen al agente)
# ============================================================================

def _get_db():
    """Obtener conexión a state.db usando SessionDB del estado central."""
    from clawk_state import SessionDB
    db = SessionDB()
    return db


def _get_profile_for_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Buscar perfil del usuario. Devuelve dict con columnas o None."""
    import sqlite3

    db_path = os.path.expanduser("~/.clawksis/state.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT * FROM business_profiles WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _json_safe(value: Any) -> str:
    """Serializar a JSON o string vacío si None."""
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


# ============================================================================
# TOOL 1: setup_business_profile (stub)
# ============================================================================

SETUP_BUSINESS_PROFILE_SCHEMA = {
    "name": "setup_business_profile",
    "description": (
        "Create or update the user's business profile for content generation. "
        "Call this when the user wants to configure their business for the first "
        "time, OR when they want to update existing data (e.g. add a new "
        "destination, change tone).\n\n"
        "The profile persists across sessions and is used by generate_social_content "
        "to produce on-brand posts WITHOUT re-asking the same context every time.\n\n"
        "Required: at least ``name``. Other fields can be added incrementally."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Business name (e.g. 'Viajes Caribe Express')",
            },
            "description": {
                "type": "string",
                "description": "Brief description of what the business does",
            },
            "tone": {
                "type": "string",
                "enum": ["casual", "formal", "playful", "elegant"],
                "description": "Overall tone of voice for content",
            },
            "destinations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Typical destinations the agency works with",
            },
            "hashtags_core": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Hashtags that should appear in EVERY post (brand hashtags)",
            },
            "networks": {
                "type": "array",
                "items": {"type": "string", "enum": ["instagram", "tiktok", "youtube"]},
                "description": "Target social networks",
            },
            "target_audience": {
                "type": "string",
                "description": "Target audience description (e.g. 'couples 30-45, mid-high income')",
            },
        },
        "required": ["name"],
    },
}


def setup_business_profile_tool(
    name: str = "",
    description: str = "",
    tone: str = "",
    destinations: Optional[list] = None,
    hashtags_core: Optional[list] = None,
    networks: Optional[list] = None,
    target_audience: str = "",
) -> str:
    """STUB: por implementar en PASO C."""
    return (
        "TODO (PASO C): setup_business_profile will INSERT or UPDATE the "
        "business_profiles row for this user. For now this is a stub — the "
        "schema exists in state.db and the parameters are validated by the "
        "registry. Implementation lands next session."
    )


# ============================================================================
# TOOL 2: get_business_profile (stub)
# ============================================================================

GET_BUSINESS_PROFILE_SCHEMA = {
    "name": "get_business_profile",
    "description": (
        "Retrieve the current business profile for the user. Returns the "
        "stored configuration (name, tone, destinations, hashtags, etc.) so "
        "you can show it to the user OR use it as context for other tools.\n\n"
        "Returns 'No profile yet' if the user hasn't configured one."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def get_business_profile_tool() -> str:
    """STUB: por implementar en PASO C."""
    return (
        "TODO (PASO C): get_business_profile will SELECT and return the user's "
        "profile from business_profiles. For now this is a stub."
    )


# ============================================================================
# TOOL 3: generate_social_content (stub)
# ============================================================================

GENERATE_SOCIAL_CONTENT_SCHEMA = {
    "name": "generate_social_content",
    "description": (
        "Generate a social media post (caption + image + hashtags) for the user's "
        "business based on a given topic. The post is auto-styled using the "
        "user's business_profile (tone, destinations, hashtags). The image is "
        "composed from a real Unsplash photo + text overlay.\n\n"
        "Requires the user to have a business_profile set up first "
        "(use setup_business_profile if not). Returns a download link to a .zip "
        "containing images sized for IG, TikTok, and YouTube + captions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Topic of the post (e.g. 'Bali all-inclusive 7 nights')",
            },
        },
        "required": ["topic"],
    },
}


def generate_social_content_tool(topic: str = "") -> str:
    """STUB: por implementar en PASO D."""
    return (
        f"TODO (PASO D): generate_social_content will produce a .zip with "
        f"IG/TikTok/YouTube posts about '{topic}'. Implementation lands after "
        f"setup_business_profile is functional."
    )


# ============================================================================
# TOOL 4: list_recent_generations (stub)
# ============================================================================

LIST_RECENT_GENERATIONS_SCHEMA = {
    "name": "list_recent_generations",
    "description": (
        "List the user's recent content generations (last 10 by default). "
        "Returns metadata: topic, date, networks, download link (if still valid)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max number of generations to return (default: 10)",
                "default": 10,
            },
        },
        "required": [],
    },
}


def list_recent_generations_tool(limit: int = 10) -> str:
    """STUB: por implementar después de PASO D (requiere tabla de historial)."""
    return (
        "TODO (post-PASO D): list_recent_generations will query a history table "
        "of past generations. Not implemented yet."
    )


# ============================================================================
# REGISTRY — registra los 4 tools en el toolset "social_content"
# ============================================================================

from tools.registry import registry  # noqa: E402

registry.register(
    name="setup_business_profile",
    toolset="social_content",
    schema=SETUP_BUSINESS_PROFILE_SCHEMA,
    handler=lambda args, **kw: setup_business_profile_tool(
        name=args.get("name", ""),
        description=args.get("description", ""),
        tone=args.get("tone", ""),
        destinations=args.get("destinations"),
        hashtags_core=args.get("hashtags_core"),
        networks=args.get("networks"),
        target_audience=args.get("target_audience", ""),
    ),
    emoji="🏢",
)

registry.register(
    name="get_business_profile",
    toolset="social_content",
    schema=GET_BUSINESS_PROFILE_SCHEMA,
    handler=lambda args, **kw: get_business_profile_tool(),
    emoji="📋",
)

registry.register(
    name="generate_social_content",
    toolset="social_content",
    schema=GENERATE_SOCIAL_CONTENT_SCHEMA,
    handler=lambda args, **kw: generate_social_content_tool(
        topic=args.get("topic", ""),
    ),
    emoji="✨",
)

registry.register(
    name="list_recent_generations",
    toolset="social_content",
    schema=LIST_RECENT_GENERATIONS_SCHEMA,
    handler=lambda args, **kw: list_recent_generations_tool(
        limit=int(args.get("limit", 10)),
    ),
    emoji="📚",
)
