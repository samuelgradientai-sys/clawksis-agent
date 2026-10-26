"""The "Hoy" page's sources outside ``state.db``: cron history, git commits, skill dashboards.

Every reader takes the profile's home explicitly (the caller resolved it inside the request's
profile scope) and only reads: the cron execution ledger is opened ``mode=ro`` and ``jobs.json``
is parsed directly, so browsing a day never creates a profile's cron store as the cron module's
own accessors would.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Ledger rows are pruned to ~1000 terminal attempts (cron/executions.py MAX_TERMINAL_EXECUTIONS).
_LEDGER_SCAN_LIMIT = 2000
_MAX_REPOS = 6
_COMMITS_PER_REPO = 20
_REPO_WALK_LIMIT = 30
_GIT_TIMEOUT_S = 5


def _iso_epoch(value: Any) -> Optional[float]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip()).timestamp()
    except ValueError:
        return None


def _in_window(ts: Optional[float], start: float, end: float) -> bool:
    return ts is not None and start <= ts < end


# ── cron ─────────────────────────────────────────────────────────────────────


def read_cron_jobs(home: Path) -> dict[str, dict]:
    """``{job id: job}`` from the profile's ``cron/jobs.json``; {} when absent or unreadable."""
    path = home / "cron" / "jobs.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("Hoy: cannot read %s", path, exc_info=True)
        return {}
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    if isinstance(jobs, dict):
        jobs = [
            {**v, "id": v.get("id") or k}
            for k, v in jobs.items()
            if isinstance(v, dict)
        ]
    if not isinstance(jobs, list):
        return {}
    return {str(j["id"]): j for j in jobs if isinstance(j, dict) and j.get("id")}


def job_label(job: Optional[dict], job_id: str) -> str:
    return str((job or {}).get("name") or job_id)


def _schedule_display(job: dict) -> str:
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    return str(
        job.get("schedule_display")
        or schedule.get("display")
        or schedule.get("expr")
        or ""
    )


def cron_jobs_created(jobs: dict[str, dict], start: float, end: float) -> list[dict]:
    created = []
    for job_id, job in jobs.items():
        at = _iso_epoch(job.get("created_at"))
        if _in_window(at, start, end):
            created.append(
                {
                    "id": job_id,
                    "name": job_label(job, job_id),
                    "schedule": _schedule_display(job),
                    "deliver": str(job.get("deliver") or ""),
                    "at": at,
                }
            )
    return sorted(created, key=lambda j: j["at"])


def _ledger_rows(home: Path) -> list[dict]:
    path = home / "cron" / "executions.db"
    if not path.is_file():
        return []
    try:
        conn = sqlite3.connect(
            f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=2
        )
    except sqlite3.Error:
        logger.warning("Hoy: cannot open %s", path, exc_info=True)
        return []
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM executions ORDER BY rowid DESC LIMIT ?",
            (_LEDGER_SCAN_LIMIT,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        logger.warning("Hoy: cannot read %s", path, exc_info=True)
        return []
    finally:
        conn.close()


_RUN_STATUS = {"completed": "ok", "failed": "failed", "unknown": "unknown"}


def cron_runs(
    home: Path, jobs: dict[str, dict], start: float, end: float
) -> list[dict]:
    """The day's cron attempts from the execution ledger, oldest first."""
    runs = []
    for row in _ledger_rows(home):
        at = _iso_epoch(row.get("claimed_at"))
        if not _in_window(at, start, end):
            continue
        job_id = str(row.get("job_id") or "")
        runs.append(
            {
                "execution_id": str(row.get("id") or ""),
                "job_id": job_id,
                "job_name": job_label(jobs.get(job_id), job_id),
                "status": _RUN_STATUS.get(str(row.get("status")), "running"),
                "at": at,
                "finished_at": _iso_epoch(row.get("finished_at")),
                "error": (row.get("error") or "")[:400] or None,
                "session_id": None,
            }
        )
    return sorted(runs, key=lambda r: r["at"])


# ── git ──────────────────────────────────────────────────────────────────────


def project_root(directory: str, cache: dict[str, Optional[str]]) -> Optional[str]:
    """The git work tree holding ``directory`` (nearest ancestor with a ``.git``), else None."""
    probe = Path(directory)
    walked: list[str] = []
    for _ in range(_REPO_WALK_LIMIT):
        key = str(probe)
        if key in cache:
            found = cache[key]
            break
        walked.append(key)
        if (probe / ".git").exists():
            found = key
            break
        if probe.parent == probe:
            found = None
            break
        probe = probe.parent
    else:
        found = None
    for key in walked:
        cache[key] = found
    return found


def git_commits(repos: Iterable[str], start: float, end: float) -> list[dict]:
    """Commits made in the window on the local branches of up to ``_MAX_REPOS`` work trees."""
    from clawk_cli.web_git import commits_in_window

    commits: dict[tuple[str, str], dict] = {}
    for repo in list(dict.fromkeys(r for r in repos if r))[:_MAX_REPOS]:
        if not os.path.isdir(repo):
            continue
        for commit in reversed(  # oldest first, so same-second commits keep their order
            commits_in_window(
                repo, start, end, limit=_COMMITS_PER_REPO, timeout=_GIT_TIMEOUT_S
            )
        ):
            # The same change on several branches (cherry-pick, rebase) is one piece of work:
            # keep its latest copy.
            commits.pop((repo, commit["subject"]), None)
            commits[(repo, commit["subject"])] = {
                **commit,
                "repo": repo,
                "repo_name": Path(repo).name,
            }
    return sorted(commits.values(), key=lambda c: c["at"])


# ── skill dashboards ─────────────────────────────────────────────────────────


def _headline(snapshot: Optional[dict]) -> list[dict]:
    for panel in (snapshot or {}).get("panels", []):
        if panel.get("type") == "stats":
            return [
                {
                    "label": i.get("label", ""),
                    "value": i.get("value"),
                    "tone": i.get("tone", "neutral"),
                }
                for i in panel.get("items", [])[:3]
            ]
    return []


def skill_dashboard_updates(home: Path, start: float, end: float) -> list[dict]:
    """Enabled skill dashboards whose snapshot was rewritten in the window, with its first stats.

    Needs the request's full profile scope (skill discovery reads the skills-module globals that
    ``_profile_scope`` retargets)."""
    from clawk_cli.skill_dashboard_snapshot import (
        SnapshotError,
        read_snapshot,
        snapshot_mtime,
        snapshot_path,
    )
    from clawk_cli.web_routers.skill_dashboards import _declared

    declared, disabled = _declared()
    updates = []
    for name, declaration in declared.items():
        path = snapshot_path(home, name)
        mtime = snapshot_mtime(path) if path else None
        if name in disabled or not _in_window(mtime, start, end):
            continue
        try:
            snapshot = read_snapshot(path)
        except SnapshotError:
            snapshot = None
        updates.append(
            {
                "name": name,
                "title": (snapshot or {}).get("title")
                or declaration.get("title")
                or name,
                "emoji": declaration.get("emoji", ""),
                "subtitle": (snapshot or {}).get("subtitle", ""),
                "at": mtime,
                "stats": _headline(snapshot),
            }
        )
    return sorted(updates, key=lambda d: d["at"])
