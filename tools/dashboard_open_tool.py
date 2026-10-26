#!/usr/bin/env python3
"""Open a Clawksis web-dashboard page for the user (``dashboard.navigate`` via ``desktop_ui``).

The dashboard's Modern chat stays mounted across pages, so the agent can act (cron job, skill,
config change) and then take the user to the page that shows the result while the chat keeps going.
"""

import re

from tools import desktop_ui
from tools.registry import registry, tool_error

PAGES = {
    "chat": "/chat",
    "sessions": "/sessions",
    "models": "/models",
    "media": "/media",
    "files": "/files",
    "cookbook": "/cookbook",
    "logs": "/logs",
    "cron": "/cron",
    "skills": "/skills",
    "skill_dashboards": "/skills/dashboards",
    "plugins": "/plugins",
    "mcp": "/mcp",
    "channels": "/channels",
    "webhooks": "/webhooks",
    "pairing": "/pairing",
    "profiles": "/profiles",
    "config": "/config",
    "keys": "/env",
    "system": "/system",
    "analytics": "/analytics",
    "docs": "/docs",
}

_SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def dashboard_path(page: str, skill: str = "") -> str:
    """The route for ``page`` (or ``skill``'s mini dashboard); ValueError when it names nothing."""
    name = (skill or "").strip()
    if name:
        if not _SKILL_NAME.match(name):
            raise ValueError(f"invalid skill name: {name!r}")
        return f"/skills/dashboards/{name}"
    route = PAGES.get((page or "").strip().lower())
    if route is None:
        raise ValueError(f"page must be one of: {', '.join(PAGES)}.")
    return route


def dashboard_open_tool(page: str = "", skill: str = "") -> str:
    """Ask the web dashboard to show ``page`` (or a skill's mini dashboard)."""
    try:
        path = dashboard_path(page, skill)
    except ValueError as exc:
        return tool_error(str(exc))
    return desktop_ui.emit_or_error(
        "dashboard.navigate",
        {"path": path},
        f"Failed to open {path}: ",
        "dashboard_open only works in the Clawksis web dashboard chat.",
        {"success": True, "path": path},
    )


registry.register(
    name="dashboard_open",
    toolset="dashboard_ui",
    schema={
        "name": "dashboard_open",
        "description": (
            "Take the user to a page of the Clawksis web dashboard (the chat keeps running). "
            "Use it after you create or change something they will want to see — a cron job "
            "(cron), a skill (skills), a model setting (models), a config change (config) — "
            "or when they ask to see a page. Pass `skill` to open that skill's mini dashboard "
            "(e.g. skill='kronos')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "enum": list(PAGES),
                    "description": "Dashboard page to open.",
                },
                "skill": {
                    "type": "string",
                    "description": "Open this skill's mini dashboard instead of a page.",
                },
            },
        },
    },
    handler=lambda args, **kw: dashboard_open_tool(
        page=args.get("page", ""), skill=args.get("skill", "")
    ),
    emoji="🧭",
)
