"""Behaviour contracts for the NYSE calendar in ``finance/kronos`` (``_kronos_calendar.py``).

The calendar decides two things: which future timestamps a forecast gets (exchange holidays and
early closes skipped) and whether ``etoro_trade.py`` may buy a stock right now. The built-in
rules must give the published NYSE schedule (holidays with weekend observance, Good Friday,
Juneteenth, 13:00 early closes, New York daylight saving with or without a tz database), and
``pandas_market_calendars`` must take over when importable. Stdlib only; the optional library is
replaced by a fake module.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "skills" / "finance" / "kronos" / "scripts"
)


def _load(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # siblings import each other by these names
    spec.loader.exec_module(module)
    return module


cal = _load("_kronos_calendar")
kc = _load("_kronos_common")


@pytest.fixture(autouse=True)
def _no_optional_calendar(monkeypatch):
    """The built-in rules answer unless a test installs the fake library."""
    monkeypatch.setitem(sys.modules, "pandas_market_calendars", None)


# ── Holidays and early closes ──


def test_2026_holidays_follow_the_published_nyse_schedule():
    assert cal.nyse_holidays(2026) == {
        date(2026, 1, 1),
        date(2026, 1, 19),  # Martin Luther King Jr. Day
        date(2026, 2, 16),  # Washington's Birthday
        date(2026, 4, 3),  # Good Friday
        date(2026, 5, 25),  # Memorial Day
        date(2026, 6, 19),  # Juneteenth
        date(2026, 7, 3),  # Independence Day falls on a Saturday
        date(2026, 9, 7),  # Labor Day
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),
    }
    assert cal.nyse_early_closes(2026) == {date(2026, 11, 27), date(2026, 12, 24)}


def test_weekend_observance_and_the_new_years_exception():
    assert date(2027, 12, 24) in cal.nyse_holidays(2027)  # Christmas on a Saturday
    assert date(2027, 7, 5) in cal.nyse_holidays(2027)  # July 4 on a Sunday
    assert date(2022, 6, 20) in cal.nyse_holidays(2022)  # first Juneteenth, observed
    assert not any(
        d.month == 6 and d.day in (18, 19, 20) for d in cal.nyse_holidays(2021)
    )
    # New Year's Day 2022 was a Saturday: the market stayed open on Friday Dec 31, 2021.
    assert cal.nyse_session(date(2021, 12, 31)) is not None
    assert date(2025, 7, 3) in cal.nyse_early_closes(2025)


@pytest.mark.parametrize(
    ("year", "easter"),
    [(2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2038, date(2038, 4, 25))],
)
def test_good_friday_comes_from_the_easter_date(year, easter):
    assert cal.easter_sunday(year) == easter
    assert easter - timedelta(days=2) in cal.nyse_holidays(year)


# ── Session times and New York daylight saving ──


def test_sessions_are_in_utc_across_daylight_saving_and_early_closes():
    winter = cal.nyse_session(date(2026, 3, 6))  # Friday before DST starts
    summer = cal.nyse_session(date(2026, 3, 9))  # Monday after
    early = cal.nyse_session(date(2026, 11, 27))
    assert winter == (datetime(2026, 3, 6, 14, 30), datetime(2026, 3, 6, 21, 0))
    assert summer == (datetime(2026, 3, 9, 13, 30), datetime(2026, 3, 9, 20, 0))
    assert early == (datetime(2026, 11, 27, 14, 30), datetime(2026, 11, 27, 18, 0))
    assert cal.nyse_session(date(2026, 11, 26)) is None
    assert cal.nyse_session(date(2026, 10, 24)) is None  # a Saturday


def test_without_a_tz_database_the_us_dst_rule_gives_the_same_times(monkeypatch):
    days = [date(2008, 1, 2) + timedelta(days=11 * i) for i in range(1200)]
    with_zone = [cal.new_york_to_utc(d, cal.REGULAR_OPEN) for d in days]
    monkeypatch.setattr(cal, "_zone_utc_offset", lambda _day, _local: None)
    assert [cal.new_york_to_utc(d, cal.REGULAR_OPEN) for d in days] == with_zone


def test_market_status_knows_open_closed_and_the_next_open():
    def at(*args):
        return cal.market_status(datetime(*args, tzinfo=cal.UTC))

    assert at(2026, 10, 26, 15, 0)["open"] is True  # Monday 11:00 New York
    assert at(2026, 10, 26, 13, 29)["open"] is False  # 9:29, before the bell
    friday_evening = at(2026, 10, 23, 20, 0)  # 16:00 New York: closed
    assert friday_evening["open"] is False
    assert friday_evening["next_open"] == "2026-10-26T13:30:00Z"
    assert at(2026, 11, 27, 17, 59)["open"] is True
    assert at(2026, 11, 27, 18, 0)["open"] is False  # early close at 13:00
    assert at(2026, 11, 26, 16, 0)["source"] == "built-in NYSE rules"


# ── pandas_market_calendars takes over when installed ──


class _Stamp:
    def __init__(self, moment: datetime):
        self.moment = moment

    def to_pydatetime(self) -> datetime:
        return self.moment.replace(tzinfo=cal.UTC)

    def date(self) -> date:
        return self.moment.date()


class _Schedule:
    def __init__(self, rows):
        self.rows = rows

    def iterrows(self):
        for day, (opens, closes) in self.rows:
            yield (
                _Stamp(datetime.combine(day, datetime.min.time())),
                {"market_open": _Stamp(opens), "market_close": _Stamp(closes)},
            )


def _fake_library(closed: set[date]) -> types.ModuleType:
    """A pandas_market_calendars stand-in that also knows ad hoc closures."""

    class Calendar:
        def schedule(self, start_date, end_date):
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
            rows = sorted(cal.builtin_sessions(start, end).items())
            return _Schedule([(d, s) for d, s in rows if d not in closed])

    module = types.ModuleType("pandas_market_calendars")
    module.get_calendar = lambda name: Calendar() if name == "NYSE" else None
    return module


def test_the_installed_library_wins_and_knows_unscheduled_closures(monkeypatch):
    mourning = date(2025, 1, 9)  # closed for a national day of mourning
    assert cal.nyse_session(mourning) is not None  # rules cannot know it
    monkeypatch.setitem(
        sys.modules, "pandas_market_calendars", _fake_library({mourning})
    )
    status = cal.market_status(datetime(2025, 1, 9, 16, 0, tzinfo=cal.UTC))
    assert status["open"] is False and status["source"] == "pandas_market_calendars"
    assert status["next_open"] == "2025-01-10T14:30:00Z"


# ── Future timestamps of a forecast ──


def test_daily_forecasts_skip_exchange_holidays():
    history = [datetime(2026, 11, 16) + timedelta(days=i) for i in range(10)]
    history = [d for d in history if d.weekday() < 5]  # ends Wednesday Nov 25
    future, calendar, _ = kc.future_timestamps(history, 3)
    assert calendar == "nyse"
    assert future == [
        datetime(2026, 11, 27),
        datetime(2026, 11, 30),
        datetime(2026, 12, 1),
    ]
    plain, _, _ = kc.future_timestamps(history, 1, "weekdays")
    assert plain == [datetime(2026, 11, 26)]  # opt-out for markets that trade that day


def test_intraday_forecasts_skip_holidays_and_bars_after_an_early_close():
    days = [datetime(2026, 11, 23) + timedelta(days=d) for d in range(3)]  # Mon..Wed
    history = [d.replace(hour=h, minute=30) for d in days for h in range(14, 21)]
    future, calendar, _ = kc.future_timestamps(history, 6)
    assert calendar == "nyse"
    assert future == [
        datetime(2026, 11, 27, h, 30)
        for h in (14, 15, 16, 17)  # closes 18:00 UTC
    ] + [datetime(2026, 11, 30, 14, 30), datetime(2026, 11, 30, 15, 30)]


def test_series_that_trade_on_weekends_stay_continuous():
    history = [datetime(2026, 10, 23, 20) + timedelta(hours=i) for i in range(30)]
    future, calendar, _ = kc.future_timestamps(history, 2)
    assert calendar == "24x7" and future[0] == history[-1] + timedelta(hours=1)
