"""Agent-callable credential persistence.

Lets the agent durably save a secret the user provides in chat (API key,
token, password, connection string) into ``~/.clawksis/.env`` — the one store
that survives a gateway restart AND is reloaded by cron jobs before every run
(``cron/scheduler.py`` calls ``load_dotenv(..., override=True)`` per job).

Why a dedicated tool is needed: the agent CANNOT write ``.env`` via file_tools
(it is on ``agent/file_safety.py``'s write denylist) and terminal redirects to
it are gated too. Without this tool, a key the user types in chat evaporates
when the conversation ends, so a later cron job searches ``.env`` and reports
"credential not found". ``clawk_cli.config.save_env_value`` already validates
the variable name, rejects denylisted names, strips newlines, and writes
atomically with 0600 perms — this tool is a thin, safe wrapper around it.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


SAVE_CREDENTIAL_SCHEMA = {
    "name": "save_credential",
    "description": (
        "Persist a secret the USER provided (API key, access token, password, "
        "connection string) to ~/.clawksis/.env so it survives gateway "
        "restarts and is available to cron jobs and future sessions.\n\n"
        "Call this the moment a user gives you a credential in chat. Do NOT "
        "store secrets in memory files, and do NOT rely on conversation "
        "context — a scheduled cron job runs in a fresh session and cannot see "
        "this chat. After saving, the value is available to the current "
        "process and to the next cron run (crons reload .env before each job).\n\n"
        "`name` must be an ENV-VAR style name (e.g. SUPABASE_SERVICE_ROLE_KEY, "
        "OPENAI_API_KEY) — pick the conventional name for that service. Never "
        "echo the secret value back to the user."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Environment-variable name (UPPER_SNAKE_CASE: letters, "
                    "digits, underscores; must not start with a digit)."
                ),
            },
            "value": {
                "type": "string",
                "description": "The secret value to store. Never logged or echoed.",
            },
        },
        "required": ["name", "value"],
    },
}


def save_credential_tool(name: str, value: str) -> str:
    """Persist ``name=value`` to ~/.clawksis/.env and the current environment.

    Returns a human-readable status string. The secret value is never logged
    or returned.
    """

    name = (name or "").strip()

    if not name:
        return "Error: 'name' is required (an env-var name like SUPABASE_SERVICE_ROLE_KEY)."

    if not value:
        return "Error: 'value' is required (the secret to store)."

    try:
        from clawk_cli.config import save_env_value
    except Exception as exc:  # pragma: no cover - import-time environment issue
        logger.warning("save_credential: storage unavailable: %s", exc)

        return f"Error: credential storage is unavailable ({type(exc).__name__})."

    # Managed deployments set credentials via the operator, not the agent.
    try:
        from clawk_cli.config import is_managed

        if is_managed():
            return (
                "Error: this is a managed deployment — credentials are set by "
                "the operator. Ask the user to add it in the dashboard's "
                "environment settings instead."
            )

    except Exception:
        pass

    try:
        save_env_value(name, value)

    except ValueError as exc:
        # Invalid/denylisted name — surface the reason WITHOUT the value.
        return f"Error: could not save credential — {exc}"

    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("save_credential failed for %r: %s", name, exc)

        return f"Error: could not save credential ({type(exc).__name__})."

    # Make it usable immediately in-process (same scope as the .env that is
    # loaded into os.environ at startup). Cron jobs reload .env with
    # override=True before each run, so they pick it up on the next tick.
    os.environ[name] = value

    return (
        f"Saved {name} to ~/.clawksis/.env (value redacted). It is now "
        "available to tools in this session and to the next cron run. "
        "If a long-running gateway feature still can't see it, restart the gateway."
    )


# --- Registry ---
from tools.registry import registry  # noqa: E402

registry.register(
    name="save_credential",
    toolset="credentials",
    schema=SAVE_CREDENTIAL_SCHEMA,
    handler=lambda args, **kw: save_credential_tool(
        name=args.get("name", ""),
        value=args.get("value", ""),
    ),
    emoji="🔑",
)
