"""The dashboard's "Hoy" page: what the agent did on one day, for the selected profile.

Mounted through ``web_routers.analytics.router`` under ``/api/analytics/today`` so the SPA's
management-profile scope (``?profile=``) rides on it like every other analytics read. Everything is
read off the event loop inside the request's profile scope; the only write is the summary cache
the POST keeps under the profile's ``cache/today/``. Aggregation: ``clawk_cli.today_activity``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from clawk_cli import today_summary as summaries
from clawk_cli.today_activity import DayWindow, collect_day, day_window
from clawk_cli.web_deps import late
from clawk_cli.web_routers._common import (
    config_scoped_to_thread,
    corrupt_store_as_status,
    scoped_to_thread,
)

router = APIRouter()

# Late-bound so a test's monkeypatch on the owning module wins at call time.
_open_session_db_for_profile = late(
    "_open_session_db_for_profile", "clawk_cli.web_server_sessions"
)
_session_db_path_for_profile = late(
    "_session_db_path_for_profile", "clawk_cli.web_server_sessions"
)


class TodaySummaryRequest(BaseModel):
    date: Optional[str] = None
    tz: Optional[str] = None
    lang: Optional[str] = None
    regenerate: bool = False


def _window(day: Optional[str], tz: Optional[str]) -> DayWindow:
    try:
        return day_window(day, tz)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid date (use YYYY-MM-DD): {exc}"
        )


def _home() -> Path:
    from clawk_constants import get_clawk_home

    return get_clawk_home()


def _store_initialized(path: Path) -> bool:
    try:
        return path.stat().st_size > 0
    except OSError:
        return False


def _collect(profile: Optional[str], window: DayWindow) -> dict:
    """The day's activity; runs inside the request's profile scope on a worker thread."""
    db_path = _session_db_path_for_profile(profile)
    with corrupt_store_as_status(db_path):
        db = (
            _open_session_db_for_profile(profile, read_only=True)
            if _store_initialized(db_path)
            else None
        )
        try:
            return collect_day(db, window, _home())
        finally:
            if db is not None:
                db.close()


def _has_activity(data: dict) -> bool:
    stats = data["stats"]
    return bool(
        stats["messages"]
        or stats["tool_calls"]
        or data["cron_runs"]
        or data["commits"]
        or data["cron_jobs_created"]
    )


@router.get("/api/analytics/today")
async def get_today(
    date: Optional[str] = None,
    tz: Optional[str] = None,
    profile: Optional[str] = None,
):
    """``date`` (YYYY-MM-DD, default today) is a calendar day in ``tz`` (IANA; the browser's zone,
    default the server's). The cached summary rides along; generating one is the POST."""
    window = _window(date, tz)

    def _run():
        data = _collect(profile, window)
        data["summary"] = summaries.with_staleness(
            summaries.read_cached(_home(), window.date), data["fingerprint"]
        )
        return data

    def _dashboards():
        from clawk_cli.today_sources import skill_dashboard_updates

        return skill_dashboard_updates(_home(), window.start, window.end)

    # The day's stores need only home + secrets; skill discovery needs the full scope (it retargets
    # the skills-module globals under _SKILLS_PROFILE_LOCK), so only that part holds the lock.
    data = await config_scoped_to_thread(profile, _run)
    data["dashboards"] = await scoped_to_thread(profile, _dashboards)
    data["has_activity"] = _has_activity(data) or bool(data["dashboards"])
    return data


@router.post("/api/analytics/today/summary")
async def post_today_summary(body: TodaySummaryRequest, profile: Optional[str] = None):
    """Write (or, with ``regenerate``, rewrite) the day's summary with the ``daily_summary``
    auxiliary model and cache it. A model failure is ``{"summary": <cached or null>, "error": …}``,
    never a 5xx: the page keeps rendering everything else."""
    window = _window(body.date, body.tz)

    def _run():
        home = _home()
        data = _collect(profile, window)
        cached = summaries.read_cached(home, window.date)
        if cached is not None and not body.regenerate:
            return {
                "summary": summaries.with_staleness(cached, data["fingerprint"]),
                "error": None,
            }
        if not _has_activity(data):
            return {"summary": None, "error": None}
        try:
            summary = summaries.generate(data, window, body.lang)
        except summaries.SummaryUnavailable as exc:
            return {
                "summary": summaries.with_staleness(cached, data["fingerprint"]),
                "error": str(exc)[:300],
            }
        summaries.write_cached(home, window.date, summary)
        return {
            "summary": summaries.with_staleness(summary, data["fingerprint"]),
            "error": None,
        }

    # Home + secret scope without the skills-module swap: the model call can take a while and
    # must not hold _SKILLS_PROFILE_LOCK for it.
    return await config_scoped_to_thread(profile, _run)
