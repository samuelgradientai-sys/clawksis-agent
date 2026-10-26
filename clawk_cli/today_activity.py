"""What the agent did on one calendar day, for one profile: the data behind the dashboard's "Hoy" page.

Read-only over the profile's ``state.db``. Sessions are preselected from the ``sessions`` table
(started before the day ends, still active after it starts — a small table), then only their
messages inside the day are read through ``idx_messages_session(session_id, timestamp)``, so the
cost follows the day's activity, never the size of the history. Child sessions (delegations,
compression continuations) fold into the conversation they belong to.

Token/cost numbers are the ``sessions`` counters of the sessions *started* that day — the same
attribution the Analytics page's daily chart uses (``/api/analytics/usage``).
"""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from clawk_cli import today_sources as sources
from clawk_cli import today_tools as tt

_SQL_CHUNK = 900  # SQLITE_MAX_VARIABLE_NUMBER floor on old builds
TEXT_PREVIEW_CHARS = 600
MAX_COMMANDS = 25
MAX_ERRORS = 50
MAX_FILES = 300


@dataclass(frozen=True)
class DayWindow:
    date: str
    tz: str  # IANA name, "" = the server's local zone
    start: float
    end: float


def _zone(tz: Optional[str]) -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(tz) if tz else None
    except (ZoneInfoNotFoundError, ValueError):
        return None


def day_window(
    day: Optional[str], tz: Optional[str], now: Optional[float] = None
) -> DayWindow:
    """``[start, end)`` of the calendar ``day`` (YYYY-MM-DD, default today) in zone ``tz``.

    An unknown zone falls back to the server's local one; a malformed day raises ValueError."""
    zone = _zone(tz)
    when = datetime.fromtimestamp(now if now is not None else time.time(), tz=zone)
    target = Date.fromisoformat(day) if day else when.date()

    def midnight(d: Date) -> float:
        return datetime(d.year, d.month, d.day, tzinfo=zone).timestamp()

    return DayWindow(
        target.isoformat(),
        tz if zone else "",
        midnight(target),
        midnight(target + timedelta(days=1)),
    )


# ── state.db reads ───────────────────────────────────────────────────────────

_CANDIDATES_SQL = """
SELECT id, source, created_source, title, model, cwd, parent_session_id,
       started_at, ended_at
FROM sessions
WHERE started_at < :end
  AND (COALESCE(last_activity_at, started_at) >= :start OR ended_at >= :start OR ended_at IS NULL)
"""

_MESSAGES_SQL = """
SELECT id, session_id, role, timestamp, tool_calls, tool_call_id,
       CASE WHEN role = 'tool'
            THEN substr(COALESCE(content, ''), 1, 1500) || char(10) || substr(COALESCE(content, ''), -300)
            ELSE substr(COALESCE(content, ''), 1, {preview}) END AS text
FROM messages
WHERE session_id IN ({marks}) AND timestamp >= ? AND timestamp < ?
  AND (active = 1 OR compacted = 1) AND COALESCE(_compressed_summary, 0) = 0
ORDER BY timestamp, id
"""

_USAGE_SQL = """
SELECT COUNT(*) AS sessions,
       COALESCE(SUM(input_tokens), 0) AS input_tokens,
       COALESCE(SUM(output_tokens), 0) AS output_tokens,
       COALESCE(SUM(cache_read_tokens), 0) AS cache_read_tokens,
       COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
       COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
       COALESCE(SUM(actual_cost_usd), 0) AS actual_cost_usd,
       COALESCE(SUM(api_call_count), 0) AS api_calls
FROM sessions WHERE started_at >= ? AND started_at < ?
"""


def _rows(conn, sql: str, params) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _day_messages(conn, session_ids: list[str], window: DayWindow) -> list[dict]:
    rows: list[dict] = []
    for i in range(0, len(session_ids), _SQL_CHUNK):
        chunk = session_ids[i : i + _SQL_CHUNK]
        sql = _MESSAGES_SQL.format(
            marks=",".join("?" * len(chunk)), preview=TEXT_PREVIEW_CHARS
        )
        rows.extend(_rows(conn, sql, (*chunk, window.start, window.end)))
    rows.sort(key=lambda r: (r["timestamp"], r["id"]))
    return rows


def effective_source(row: dict) -> str:
    """Interactive local sessions are stored as ``local`` with the surface in ``created_source``."""
    source = row.get("source") or ""
    return (row.get("created_source") or source) if source == "local" else source


_MARKDOWN_MARKS = re.compile(r"\*\*|`+|^#+\s*")


def _clean_text(text: Optional[str], limit: int = 220) -> str:
    """One plain line: whitespace collapsed, bold/code/heading markers dropped, clipped."""
    one_line = _MARKDOWN_MARKS.sub("", " ".join((text or "").split()))
    return one_line[:limit] + ("…" if len(one_line) > limit else "")


# ── per-session accumulation ─────────────────────────────────────────────────


@dataclass
class _SessionDay:
    row: dict
    first_at: float = 0.0
    last_at: float = 0.0
    messages: int = 0
    tool_calls: int = 0
    commands: int = 0
    errors: int = 0
    tools: Counter = field(default_factory=Counter)
    files: set = field(default_factory=set)
    ask: str = ""
    outcome: str = ""
    first_error: str = ""

    def see(self, ts: float) -> None:
        self.first_at = min(self.first_at, ts) if self.first_at else ts
        self.last_at = max(self.last_at, ts)


@dataclass
class _Pending:
    call: tt.ToolCall
    session: _SessionDay
    at: float


class _DayLedger:
    """Folds the day's message rows (oldest first) into files, commands, skills and errors."""

    def __init__(self, sessions: dict[str, dict]):
        self.sessions = {sid: _SessionDay(row) for sid, row in sessions.items()}
        self.pending: dict[str, _Pending] = {}
        self.files: dict[str, dict] = {}
        self.skills: dict[str, dict] = {}
        self.commands: list[dict] = []
        self.errors: list[dict] = []
        self.git_dirs: set[str] = set()  # where a command wrote git history
        self.user_messages = 0

    def add(self, row: dict) -> None:
        day = self.sessions[row["session_id"]]
        day.see(row["timestamp"])
        handler = _ROLE_HANDLERS.get(row["role"])
        if handler:
            handler(self, day, row)

    def _user(self, day: _SessionDay, row: dict) -> None:
        day.messages += 1
        self.user_messages += 1
        if not day.ask:
            day.ask = _clean_text(row["text"])

    def _assistant(self, day: _SessionDay, row: dict) -> None:
        text = _clean_text(row["text"])
        if text:
            day.messages += 1
            day.outcome = text
        for call in tt.iter_calls(row.get("tool_calls")):
            day.tool_calls += 1
            day.tools[call.name] += 1
            if call.call_id:
                self.pending[call.call_id] = _Pending(call, day, row["timestamp"])
            else:
                self._apply(_Pending(call, day, row["timestamp"]), "")

    def _tool(self, day: _SessionDay, row: dict) -> None:
        pending = self.pending.pop(row.get("tool_call_id") or "", None)
        if pending is not None:
            self._apply(pending, row["text"] or "")

    def flush(self) -> None:
        """Calls whose result fell outside the day (or was never written) count as done."""
        for pending in self.pending.values():
            self._apply(pending, "")
        self.pending.clear()

    def _command(self, p: _Pending, result: str, failed: bool) -> None:
        """A shell command counts even when it failed (it still ran)."""
        command = tt.command_text(p.call)
        if not command:
            return
        p.session.commands += 1
        self.commands.append(
            {
                "command": command,
                "at": p.at,
                "session_id": p.session.row["id"],
                "exit_code": tt.result_exit_code(result),
                "failed": failed,
            }
        )
        git_dir = tt.git_work_dir(p.call.args["command"], p.session.row.get("cwd"))
        if git_dir and not failed:
            self.git_dirs.add(git_dir)

    def _apply(self, p: _Pending, result: str) -> None:
        sid = p.session.row["id"]
        error = tt.result_error(result)
        self._command(p, result, bool(error))
        if error:  # a failed write/skill op changed nothing
            p.session.errors += 1
            p.session.first_error = (
                p.session.first_error or f"{p.call.name}: {error[:200]}"
            )
            if len(self.errors) < MAX_ERRORS:
                self.errors.append(
                    {
                        "at": p.at,
                        "session_id": sid,
                        "tool": p.call.name,
                        "message": error[:300],
                    }
                )
            return
        for path, action in tt.file_targets(p.call):
            resolved = (
                tt.result_resolved_path(result) if p.call.name == "write_file" else None
            )
            self._file(
                resolved or tt.absolute_path(path, p.session.row.get("cwd")),
                action,
                p,
                sid,
            )
        for name, action in tt.skill_changes(p.call):
            self._skill(name, action, p.at, sid)

    def _file(self, path: str, action: str, p: _Pending, sid: str) -> None:
        p.session.files.add(path)
        entry = self.files.get(path)
        if entry is None:
            self.files[path] = {
                "path": path,
                "action": "created" if action in ("written", "created") else action,
                "count": 1,
                "first_at": p.at,
                "last_at": p.at,
                "session_id": sid,
            }
            return
        entry["count"] += 1
        entry["last_at"] = p.at
        entry["session_id"] = sid
        if action == "deleted" or entry["action"] == "deleted":
            entry["action"] = "deleted" if action == "deleted" else "edited"

    def _skill(self, name: str, action: str, at: float, sid: str) -> None:
        entry = self.skills.get(name)
        if entry is None:
            self.skills[name] = {
                "name": name,
                "action": action,
                "count": 1,
                "at": at,
                "session_id": sid,
            }
            return
        entry["count"] += 1
        entry["at"], entry["session_id"] = at, sid
        if (
            action == "deleted" or entry["action"] == "deleted"
        ):  # the first touch names it, unless deleted
            entry["action"] = action


_ROLE_HANDLERS = {
    "user": _DayLedger._user,
    "assistant": _DayLedger._assistant,
    "tool": _DayLedger._tool,
}


# ── conversations (lineage roots) ────────────────────────────────────────────


def _root_of(sid: str, active: dict[str, _SessionDay]) -> str:
    seen = {sid}
    while True:
        parent = active[sid].row.get("parent_session_id")
        if not parent or parent not in active or parent in seen:
            return sid
        seen.add(parent)
        sid = parent


def _conversation(root: _SessionDay, members: list[_SessionDay]) -> dict:
    tools: Counter = Counter()
    files: set = set()
    for m in members:
        tools.update(m.tools)
        files |= m.files
    tip = max(members, key=lambda m: m.last_at)
    asks = [m for m in sorted(members, key=lambda m: m.first_at) if m.ask]
    outcomes = [m for m in sorted(members, key=lambda m: m.last_at) if m.outcome]
    titled = [m.row.get("title") for m in [root, tip, *members] if m.row.get("title")]
    error_samples = [m.first_error for m in members if m.first_error]
    return {
        "id": root.row["id"],
        "open_id": tip.row["id"],
        "title": titled[0] if titled else "",
        "source": effective_source(root.row),
        "model": tip.row.get("model") or "",
        "started_at": min(m.first_at for m in members),
        "ended_at": max(m.last_at for m in members),
        "messages": sum(m.messages for m in members),
        "tool_calls": sum(m.tool_calls for m in members),
        "commands": sum(m.commands for m in members),
        "errors": sum(m.errors for m in members),
        "files": len(files),
        "file_names": sorted({Path(f).name for f in files})[:4],
        "error_sample": error_samples[0] if error_samples else "",
        "children": len(members) - 1,
        "top_tools": tools.most_common(4),
        "ask": asks[0].ask if asks else "",
        "outcome": outcomes[-1].outcome if outcomes else "",
    }


def _conversations(active: dict[str, _SessionDay]) -> list[dict]:
    lineages: dict[str, list[_SessionDay]] = {}
    for sid, day in active.items():
        lineages.setdefault(_root_of(sid, active), []).append(day)
    return sorted(
        (_conversation(active[root], members) for root, members in lineages.items()),
        key=lambda c: c["started_at"],
    )


# ── cron + git enrichment ────────────────────────────────────────────────────


def _attach_cron_sessions(
    db, runs: list[dict], cron_convs: list[dict], jobs: dict
) -> list[dict]:
    """Point each ledger run at its transcript; a cron session no ledger row names is its own run."""
    by_execution = {r["execution_id"]: r for r in runs if r["execution_id"]}
    for conv in cron_convs:
        identity = db.cron_run_identity(conv["id"]) or {}
        run = by_execution.get(identity.get("cron_execution_id") or "")
        if run is None:
            run = _closest_run(runs, identity.get("cron_job_id"), conv["started_at"])
        if run is not None:
            run["session_id"] = conv["open_id"]
            continue
        job_id = identity.get("cron_job_id") or ""
        runs.append(
            {
                "execution_id": "",
                "job_id": job_id,
                "job_name": sources.job_label(jobs.get(job_id), job_id)
                or conv["title"],
                "status": "unknown",
                "at": conv["started_at"],
                "finished_at": conv["ended_at"],
                "error": None,
                "session_id": conv["open_id"],
            }
        )
    return sorted(runs, key=lambda r: r["at"])


def _closest_run(runs: list[dict], job_id: Optional[str], at: float) -> Optional[dict]:
    candidates = [
        r for r in runs if job_id and r["job_id"] == job_id and not r["session_id"]
    ]
    return min(candidates, key=lambda r: abs(r["at"] - at), default=None)


def _repos(files: list[dict], git_dirs: set[str]) -> list[str]:
    """Work trees the agent worked in — it wrote files there or committed there (a session that
    merely ran inside a repo is not one); also stamps each file with its ``project`` folder."""
    cache: dict[str, Optional[str]] = {}
    repos: list[str] = []
    for entry in files:
        root = sources.project_root(str(Path(entry["path"]).parent), cache)
        entry["project"] = root or str(Path(entry["path"]).parent)
        entry["in_repo"] = root is not None
        if root:
            repos.append(root)
    repos += [r for d in sorted(git_dirs) if (r := sources.project_root(d, cache))]
    return repos


# ── assembly ─────────────────────────────────────────────────────────────────


def _stats(convs, ledger: _DayLedger, cron_runs, usage: dict) -> dict:
    files = ledger.files.values()
    skills = ledger.skills.values()
    return {
        "conversations": len(convs),
        "messages": sum(d.messages for d in ledger.sessions.values()),
        "user_messages": ledger.user_messages,
        "tool_calls": sum(d.tool_calls for d in ledger.sessions.values()),
        "files_created": sum(1 for f in files if f["action"] == "created"),
        "files_edited": sum(1 for f in files if f["action"] == "edited"),
        "files_deleted": sum(1 for f in files if f["action"] == "deleted"),
        "commands": len(ledger.commands),
        "errors": sum(d.errors for d in ledger.sessions.values()),
        "cron_ok": sum(1 for r in cron_runs if r["status"] == "ok"),
        "cron_failed": sum(1 for r in cron_runs if r["status"] == "failed"),
        "cron_other": sum(1 for r in cron_runs if r["status"] not in ("ok", "failed")),
        "skills_created": sum(1 for s in skills if s["action"] == "created"),
        "skills_updated": sum(1 for s in skills if s["action"] == "updated"),
        **usage,
    }


def fingerprint(stats: dict) -> str:
    """Changes whenever the day gains activity — a cached summary older than it is stale."""
    return f"{stats['messages']}:{stats['tool_calls']}:{stats['cron_ok'] + stats['cron_failed'] + stats['cron_other']}"


_NO_USAGE = {
    "sessions": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_tokens": 0,
    "reasoning_tokens": 0,
    "estimated_cost_usd": 0,
    "actual_cost_usd": 0,
    "api_calls": 0,
}


def _read_store(db, window: DayWindow) -> tuple[_DayLedger, dict]:
    if db is None:  # the profile has not initialized its session store yet
        return _DayLedger({}), dict(_NO_USAGE)
    conn = db._conn
    candidates = {
        r["id"]: r
        for r in _rows(
            conn, _CANDIDATES_SQL, {"start": window.start, "end": window.end}
        )
    }
    ledger = _DayLedger(candidates)
    for row in _day_messages(conn, list(candidates), window):
        ledger.add(row)
    ledger.flush()
    return ledger, _rows(conn, _USAGE_SQL, (window.start, window.end))[0]


def collect_day(db, window: DayWindow, home: Path) -> dict[str, Any]:
    """The day's activity for the profile whose home is ``home``; ``db`` is its open read-only
    ``SessionDB``, or None when it has no session store yet."""
    ledger, usage = _read_store(db, window)
    active = {sid: d for sid, d in ledger.sessions.items() if d.last_at}
    all_convs = _conversations(active)
    convs = [c for c in all_convs if c["source"] != "cron"]

    jobs = sources.read_cron_jobs(home)
    runs = sources.cron_runs(home, jobs, window.start, window.end)
    cron_convs = [c for c in all_convs if c["source"] == "cron"]
    if cron_convs:
        runs = _attach_cron_sessions(db, runs, cron_convs, jobs)

    files = sorted(ledger.files.values(), key=lambda f: f["last_at"], reverse=True)[
        :MAX_FILES
    ]
    repos = _repos(files, ledger.git_dirs)
    stats = _stats(convs, ledger, runs, usage)
    return {
        "date": window.date,
        "tz": window.tz,
        "start": window.start,
        "end": window.end,
        "stats": stats,
        "fingerprint": fingerprint(stats),
        "conversations": convs,
        "files": files,
        "commands": ledger.commands[-MAX_COMMANDS:],
        "skills": sorted(ledger.skills.values(), key=lambda s: s["at"]),
        "errors": ledger.errors,
        "cron_runs": runs,
        "cron_jobs_created": sources.cron_jobs_created(jobs, window.start, window.end),
        "commits": sources.git_commits(repos, window.start, window.end),
    }
