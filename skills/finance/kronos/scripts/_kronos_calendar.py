"""New York Stock Exchange sessions: trading days, holidays, early closes, open/closed now.

``pandas_market_calendars`` (MIT; installed in the skill venv by ``kronos_setup.py`` when it can
be) is used when importable, so its maintained list of special closures applies. Otherwise the
built-in NYSE rules below answer: the ten full-day holidays with their weekend observance
(New Year's Day is not moved back to a Friday, NYSE Rule 7.2), Good Friday from the Easter date,
Juneteenth from 2022, and the 13:00 New York early closes on July 3, the day after Thanksgiving
and December 24. Unscheduled closures (a national day of mourning, a storm) cannot be known in
advance by either source.

Session times are naive UTC, like every timestamp in the skill. Stdlib only, no imports from the
other skill modules, so ``etoro_trade.py`` can ask "is the market open now?" under the system
``python3`` without the skill venv.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
NEW_YORK = "America/New_York"
UTC = timezone.utc  # noqa: UP017 -- the system python3 may be 3.10, which has no datetime.UTC
JUNETEENTH_FROM = 2022

Session = tuple[datetime, datetime]  # (open, close) in naive UTC

_MON, _TUE, _THU, _FRI, _SAT, _SUN = 0, 1, 3, 4, 5, 6


# ── Holiday rules ──


def easter_sunday(year: int) -> date:
    """Gregorian Easter (anonymous algorithm, Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    lv = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lv) // 451
    month, day = divmod(h + lv - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The *n*-th *weekday* of the month (``n=-1``: the last one)."""
    if n > 0:
        first = date(year, month, 1)
        return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    following = date(year + month // 12, month % 12 + 1, 1)
    last = following - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(day: date) -> date:
    """Saturday holidays move to Friday, Sunday holidays to Monday."""
    if day.weekday() == _SAT:
        return day - timedelta(days=1)
    if day.weekday() == _SUN:
        return day + timedelta(days=1)
    return day


def nyse_holidays(year: int) -> set[date]:
    """Full-day NYSE closures of *year* from the standing rules."""
    days = {
        _nth_weekday(year, 1, _MON, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, _MON, 3),  # Washington's Birthday
        easter_sunday(year) - timedelta(days=2),  # Good Friday
        _nth_weekday(year, 5, _MON, -1),  # Memorial Day
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, _MON, 1),  # Labor Day
        _nth_weekday(year, 11, _THU, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),  # Christmas
    }
    new_year = date(year, 1, 1)
    if (
        new_year.weekday() != _SAT
    ):  # a Saturday New Year's Day is not observed (Rule 7.2)
        days.add(_observed(new_year))
    if year >= JUNETEENTH_FROM:
        days.add(_observed(date(year, 6, 19)))
    return days


def nyse_early_closes(year: int) -> set[date]:
    """Days that close at 13:00 New York time."""
    days = {
        _nth_weekday(year, 11, _THU, 4) + timedelta(days=1)
    }  # day after Thanksgiving
    if date(year, 7, 4).weekday() in range(_TUE, _SAT):
        days.add(date(year, 7, 3))
    if date(year, 12, 25).weekday() in range(_TUE, _SAT):
        days.add(date(year, 12, 24))
    return days


# ── New York time ──


def _manual_utc_offset(day: date) -> timedelta:
    """US Eastern offset from the 2007 DST rule (2nd Sunday of March to 1st Sunday of November)."""
    starts = _nth_weekday(day.year, 3, _SUN, 2)
    ends = _nth_weekday(day.year, 11, _SUN, 1)
    return timedelta(hours=-4) if starts <= day < ends else timedelta(hours=-5)


def _zone_utc_offset(day: date, local: time) -> timedelta | None:
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:
        return None
    try:
        zone = ZoneInfo(NEW_YORK)
    except (ZoneInfoNotFoundError, ValueError):
        return None  # no tz database (e.g. Windows without the tzdata package)
    return datetime.combine(day, local, tzinfo=zone).utcoffset()


def new_york_to_utc(day: date, local: time) -> datetime:
    """Naive UTC for a New York wall-clock time on *day*."""
    offset = _zone_utc_offset(day, local)
    if offset is None:
        offset = _manual_utc_offset(day)
    return datetime.combine(day, local) - offset


def _builtin_session(day: date) -> Session | None:
    if day.weekday() >= _SAT or day in nyse_holidays(day.year):
        return None
    close = EARLY_CLOSE if day in nyse_early_closes(day.year) else REGULAR_CLOSE
    return new_york_to_utc(day, REGULAR_OPEN), new_york_to_utc(day, close)


def builtin_sessions(start: date, end: date) -> dict[date, Session]:
    """Sessions from the standing rules, *start* to *end* inclusive."""
    out: dict[date, Session] = {}
    day = start
    while day <= end:
        session = _builtin_session(day)
        if session is not None:
            out[day] = session
        day += timedelta(days=1)
    return out


# ── pandas_market_calendars (optional) ──


def _naive_utc(stamp: Any) -> datetime:
    moment = stamp.to_pydatetime()  # a tz-aware pandas Timestamp
    return moment.astimezone(UTC).replace(tzinfo=None)


def _pmc_sessions(start: date, end: date) -> dict[date, Session] | None:
    try:
        import pandas_market_calendars as mcal
    except ImportError:
        return None
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=start.isoformat(), end_date=end.isoformat()
    )
    return {
        stamp.date(): (_naive_utc(row["market_open"]), _naive_utc(row["market_close"]))
        for stamp, row in schedule.iterrows()
    }


def nyse_sessions(start: date, end: date) -> tuple[dict[date, Session], str]:
    """(sessions by date, which source answered) for *start* to *end* inclusive."""
    sessions = _pmc_sessions(start, end)
    if sessions is not None:
        return sessions, "pandas_market_calendars"
    return builtin_sessions(start, end), "built-in NYSE rules"


def nyse_session(day: date) -> Session | None:
    return nyse_sessions(day, day)[0].get(day)


def market_status(now: datetime) -> dict[str, object]:
    """Whether the NYSE regular session is open at *now* (aware or naive UTC), and the next open."""
    moment = now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now
    sessions, source = nyse_sessions(moment.date(), moment.date() + timedelta(days=10))
    today = sessions.get(moment.date())
    is_open = today is not None and today[0] <= moment < today[1]
    upcoming = [s for d, s in sorted(sessions.items()) if s[0] > moment]
    return {
        "open": is_open,
        "session": [t.isoformat() + "Z" for t in today] if today else None,
        "next_open": upcoming[0][0].isoformat() + "Z" if upcoming else None,
        "source": source,
    }
