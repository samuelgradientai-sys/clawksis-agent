"""Cross-process agent tool-activity log (best-effort, non-blocking).

Every agent — the dashboard chat PTY, the platform gateway (Telegram/WhatsApp),
and cron/batch subprocesses — runs its tools through
``model_tools.handle_function_call``. That dispatcher emits a ``start`` and a
``complete`` event here, so a single shared SQLite log under
``$CLAWK_HOME/agent_events.db`` captures what EVERY agent is doing, regardless of
which OS process it runs in. The dashboard reads this log (in-process) to drive
the Visualization office for all agents, not just the chat session.

Design constraints (the writes happen on the tool hot-path, so this must never
slow it down or raise):

* ``emit_tool_start`` / ``emit_tool_complete`` only enqueue onto an in-memory
  queue (``put_nowait``, dropped when full) and return immediately. A single
  daemon thread drains the queue to SQLite, so no agent thread ever blocks on
  disk I/O. Any failure is swallowed.
* WAL mode lets the long-lived gateway/chat processes and short-lived cron
  subprocesses append concurrently to the same file.
* We store only the tool NAME plus a short, truncated context string — never raw
  arguments or results — to keep the log small and avoid spilling sensitive data
  to disk.
* The writer prunes old rows so the table stays bounded.
"""

from __future__ import annotations

import logging
import os
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Bounded in-memory queue: drop events rather than ever block a tool call.
_QUEUE_MAX = 1024
# Keep the table small — prune to this many most-recent rows periodically.
_RETENTION_ROWS = 4000
_PRUNE_EVERY = 200  # rows written between prune passes
_SUMMARY_MAX = 200

_q: "queue.Queue[Optional[dict]]" = queue.Queue(maxsize=_QUEUE_MAX)
_worker: Optional[threading.Thread] = None
_worker_lock = threading.Lock()
_disabled = os.environ.get("CLAWK_DISABLE_AGENT_EVENTS", "").strip().lower() in {
    "1",
    "true",
    "yes",
}


def _db_path() -> Path:
    try:
        from clawk_constants import get_clawk_home

        home = get_clawk_home()
    except Exception:
        home = Path(os.path.expanduser("~/.clawksis"))
    home.mkdir(parents=True, exist_ok=True)
    return home / "agent_events.db"


def _ensure_worker() -> None:
    """Start the drain thread once, lazily, on first emit."""
    global _worker
    if _disabled or (_worker is not None and _worker.is_alive()):
        return
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return
        t = threading.Thread(target=_drain, name="clawk-agent-events", daemon=True)
        t.start()
        _worker = t


def _drain() -> None:
    """Daemon loop: open the DB once, write queued events, prune periodically."""
    try:
        conn = sqlite3.connect(str(_db_path()), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                session_id TEXT NOT NULL,
                task_id TEXT,
                tool_call_id TEXT,
                kind TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                summary TEXT,
                ok INTEGER
            )
            """
        )
        conn.commit()
    except Exception:
        logger.warning("agent_events writer failed to open DB", exc_info=True)
        return

    written = 0
    while True:
        item = _q.get()
        if item is None:  # shutdown sentinel (not normally used; daemon thread)
            break
        try:
            conn.execute(
                "INSERT INTO agent_events "
                "(ts, session_id, task_id, tool_call_id, kind, tool_name, summary, ok) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.get("ts", time.time()),
                    item.get("session_id") or "",
                    item.get("task_id"),
                    item.get("tool_call_id"),
                    item.get("kind") or "",
                    item.get("tool_name") or "",
                    item.get("summary"),
                    item.get("ok"),
                ),
            )
            conn.commit()
            written += 1
            if written % _PRUNE_EVERY == 0:
                _prune(conn)
        except Exception:
            logger.debug("agent_events write failed", exc_info=True)


def _prune(conn: sqlite3.Connection) -> None:
    try:
        conn.execute(
            "DELETE FROM agent_events WHERE id <= "
            "(SELECT MAX(id) FROM agent_events) - ?",
            (_RETENTION_ROWS,),
        )
        conn.commit()
    except Exception:
        logger.debug("agent_events prune failed", exc_info=True)


def _truncate(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    s = str(text)
    return s if len(s) <= _SUMMARY_MAX else s[: _SUMMARY_MAX - 1] + "…"


def _enqueue(item: dict) -> None:
    if _disabled:
        return
    try:
        _ensure_worker()
        _q.put_nowait(item)
    except queue.Full:
        pass  # best-effort: drop under pressure
    except Exception:
        pass  # never let logging break a tool call


def emit_tool_start(
    *,
    session_id: Optional[str],
    tool_name: str,
    task_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    context: Optional[str] = None,
) -> None:
    """Record that an agent began running a tool. Non-blocking, never raises."""
    _enqueue({
        "ts": time.time(),
        "session_id": session_id or "",
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "kind": "start",
        "tool_name": tool_name or "",
        "summary": _truncate(context),
        "ok": None,
    })


def emit_tool_complete(
    *,
    session_id: Optional[str],
    tool_name: str,
    task_id: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    ok: Optional[bool] = None,
    summary: Optional[str] = None,
) -> None:
    """Record that an agent finished running a tool. Non-blocking, never raises."""
    _enqueue({
        "ts": time.time(),
        "session_id": session_id or "",
        "task_id": task_id,
        "tool_call_id": tool_call_id,
        "kind": "complete",
        "tool_name": tool_name or "",
        "summary": _truncate(summary),
        "ok": (1 if ok else 0) if ok is not None else None,
    })


def read_recent(limit: int = 300, since_id: Optional[int] = None) -> list:
    """Dashboard helper: recent events across all agents, oldest-first.

    Oldest-first so the consumer can replay them into the office in order.
    Returns [] on any error (e.g. the log doesn't exist yet).
    """
    try:
        path = _db_path()
        if not path.exists():
            return []
        conn = sqlite3.connect(str(path), timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        sql = (
            "SELECT id, ts, session_id, task_id, tool_call_id, kind, tool_name, summary, ok "
            "FROM agent_events"
        )
        params: list = []
        if since_id is not None:
            sql += " WHERE id > ?"
            params.append(int(since_id))
        # Take the newest N, then return them oldest-first.
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    except Exception:
        logger.warning("read_recent agent_events failed", exc_info=True)
        return []

    rows = list(reversed(rows))
    return [
        {
            "id": r[0],
            "ts": r[1],
            "session_id": r[2],
            "task_id": r[3],
            "tool_call_id": r[4],
            "kind": r[5],
            "tool_name": r[6],
            "summary": r[7],
            "ok": r[8],
        }
        for r in rows
    ]
