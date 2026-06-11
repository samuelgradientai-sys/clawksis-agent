"""``agent_message`` / ``agent_inbox`` — minimal agent-to-agent messaging.

The fork has delegation (parent→child) and the kanban board (task hand-off),
but no peer-to-peer "agent A leaves a note for agent B" primitive. This adds
one, backed by a tiny SQLite table at ``$CLAWK_HOME/agent_comms.db``, so the
Visualization dashboard's Comms Graph can show real agent-to-agent links and
so independently-running agents can actually coordinate.

Off by default; enable in ``clawk tools`` → Agent Messaging. Tools:

* ``agent_message(to, text)`` — leave a message for another agent (``to`` is
  the recipient's name/id, or ``"all"`` to broadcast).
* ``agent_inbox(limit=, since_id=)`` — read recent messages addressed to me
  (or to ``"all"``), newest first.

Sender identity is best-effort: ``CLAWK_AGENT_NAME`` / ``CLAWK_AGENT_ID`` env
if set, else ``"agent"``. The dashboard reads the same table via
``GET /api/visualization/agent-messages``.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Optional

from tools.registry import registry, tool_result

logger = logging.getLogger(__name__)


def _db_path() -> Path:
    try:
        from clawk_constants import get_clawk_home

        home = get_clawk_home()
    except Exception:
        home = Path(os.path.expanduser("~/.clawksis"))
    home.mkdir(parents=True, exist_ok=True)
    return home / "agent_comms.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            text TEXT NOT NULL
        )
        """
    )
    return conn


def my_identity() -> str:
    for var in ("CLAWK_AGENT_NAME", "CLAWK_AGENT_ID", "CLAWK_PROFILE"):
        val = (os.environ.get(var) or "").strip()
        if val:
            return val
    return "agent"


# ── handlers ──────────────────────────────────────────────────────────────────


def _handle_agent_message(args, **kw):
    to = (args.get("to") or "").strip()
    text = (args.get("text") or "").strip()
    if not to:
        return tool_result(
            ok=False, error="`to` (recipient agent name, or 'all') is required."
        )
    if not text:
        return tool_result(ok=False, error="`text` is required.")

    sender = my_identity()
    try:
        conn = _connect()
        with conn:
            cur = conn.execute(
                "INSERT INTO agent_messages (ts, from_agent, to_agent, text) VALUES (?, ?, ?, ?)",
                (time.time(), sender, to, text),
            )
        msg_id = cur.lastrowid
        conn.close()
    except Exception as exc:  # pragma: no cover - defensive
        return tool_result(ok=False, error=f"failed to store message: {exc}")

    return tool_result(ok=True, message_id=msg_id, from_agent=sender, to=to)


def _handle_agent_inbox(args, **kw):
    try:
        limit = int(args.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))
    since_id = args.get("since_id")
    me = my_identity()

    try:
        conn = _connect()
        params: list = [me]
        sql = (
            "SELECT id, ts, from_agent, to_agent, text FROM agent_messages "
            "WHERE (to_agent = ? OR to_agent = 'all')"
        )
        if since_id is not None:
            try:
                sql += " AND id > ?"
                params.append(int(since_id))
            except (TypeError, ValueError):
                pass
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    except Exception as exc:  # pragma: no cover - defensive
        return tool_result(ok=False, error=f"failed to read inbox: {exc}")

    messages = [
        {"id": r[0], "ts": r[1], "from": r[2], "to": r[3], "text": r[4]} for r in rows
    ]
    return tool_result(ok=True, agent=me, count=len(messages), messages=messages)


AGENT_MESSAGE_SCHEMA = {
    "name": "agent_message",
    "description": (
        "Send a message to another agent (peer-to-peer). Use this to coordinate "
        "with a teammate agent by name — leave a note, ask for a hand-off, or "
        "share a result. The recipient reads it with agent_inbox. Use to='all' "
        "to broadcast to every agent."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient agent name/id, or 'all' to broadcast.",
            },
            "text": {"type": "string", "description": "The message body."},
        },
        "required": ["to", "text"],
    },
}

AGENT_INBOX_SCHEMA = {
    "name": "agent_inbox",
    "description": (
        "Read recent messages other agents sent to you (or broadcast to 'all'), "
        "newest first. Pass since_id to only get messages after one you've "
        "already seen."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max messages (default 20, max 100).",
                "minimum": 1,
            },
            "since_id": {
                "type": "integer",
                "description": "Only return messages with id greater than this.",
            },
        },
        "required": [],
    },
}


registry.register(
    name="agent_message",
    toolset="agent_comms",
    schema=AGENT_MESSAGE_SCHEMA,
    handler=_handle_agent_message,
    emoji="💬",
    max_result_size_chars=4000,
)

registry.register(
    name="agent_inbox",
    toolset="agent_comms",
    schema=AGENT_INBOX_SCHEMA,
    handler=_handle_agent_inbox,
    emoji="📥",
    max_result_size_chars=20000,
)


def read_recent_messages(limit: int = 100, since_id: Optional[int] = None) -> list:
    """Dashboard helper: return recent messages across all agents (newest first)."""
    try:
        conn = _connect()
        sql = "SELECT id, ts, from_agent, to_agent, text FROM agent_messages"
        params: list = []
        if since_id is not None:
            sql += " WHERE id > ?"
            params.append(int(since_id))
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    except Exception:
        logger.warning("read_recent_messages failed", exc_info=True)
        return []
    return [
        {"id": r[0], "ts": r[1], "from": r[2], "to": r[3], "text": r[4]} for r in rows
    ]
