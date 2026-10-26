"""Stdlib-only helpers shared by the Kronos skill scripts.

Everything here runs on any Python 3.10+ with no third-party packages, so the pure logic
(input parsing, trading calendars, bands, baseline metrics, output) is testable without
torch, and the entry scripts can start under the system interpreter before re-launching
themselves inside the skill's own venv (``$CLAWK_HOME/kronos/venv``).
"""

from __future__ import annotations

import csv
import io
import itertools
import json
import math
import os
import re
import subprocess
import sys
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# The terminal's system python3 may be 3.10, which has no datetime.UTC.
UTC = timezone.utc  # noqa: UP017

DISCLAIMER = (
    "Not financial advice. Kronos is an experimental research model; independent tests "
    "found it often does no better than repeating the last close. Never trade on it alone."
)

# Upstream code pin: shiyu-coder/Kronos is not packaged, so kronos_setup.py fetches this
# commit's tarball and keeps only these files, each verified against the sha256 of the git
# blob at UPSTREAM_SHA (computed when the pin was taken). Any mismatch, missing file or empty
# entry aborts the install, and the loader re-verifies before importing (fail closed).
UPSTREAM_REPO = "shiyu-coder/Kronos"
UPSTREAM_SHA = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
UPSTREAM_FILES = {
    "LICENSE": "acb2d194d378204e5f2be4dcd24d39ecac437903620c790c3315a96dab388fdc",
    "model/__init__.py": "f8f856ca3fedadcaac97e196be23d1aeda1c3c9ffe8903d66d43ea3bcac6240c",
    "model/kronos.py": "0a5f90282e2039c2de0771473419715c845def154896dbd0f5747837e6241032",
    "model/module.py": "a07edbadc0e96804c8158c021bbc6063bb7cc43b34d7fc470d5c8ff2005a409f",
}

# Context window (bars) of each released checkpoint; Kronos-large is not public.
MAX_CONTEXT = {"mini": 2048, "small": 512, "base": 512}
MODEL_NAMES = tuple(MAX_CONTEXT)
DEFAULT_MODEL = "small"
MIN_BARS = 64
CALENDARS = ("auto", "nyse", "weekdays", "24x7", "sessions")

PRICE_COLUMNS = ("open", "high", "low", "close")
_COLUMN_ALIASES = {
    "timestamps": "ts",
    "timestamp": "ts",
    "date": "ts",
    "datetime": "ts",
    "time": "ts",
    "fromdate": "ts",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "price": "price",  # investing.com exports call the close "Price"
    "volume": "volume",
    "vol": "volume",
    "vol.": "volume",
}
_VOLUME_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9}
_SLASH_DATE_FORMATS = (
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M",
    "%d.%m.%Y %H:%M",
)


class SkillError(Exception):
    """A user-facing failure, printed as ``{"error": ...}`` JSON with exit code 2."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint

    def payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": str(self)}
        if self.hint:
            out["hint"] = self.hint
        return out


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


# ── Paths (profile-aware: CLAWK_HOME is set for terminal children of every profile) ──


def clawk_home() -> Path:
    raw = os.environ.get("CLAWK_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".clawksis"


def display_home() -> str:
    home = clawk_home()
    try:
        return "~/" + home.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(home)


def kronos_home() -> Path:
    return clawk_home() / "kronos"


def state_file() -> Path:
    return kronos_home() / "state.json"


def venv_python_path(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def load_state() -> dict[str, Any] | None:
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def setup_command() -> str:
    return f"python3 {Path(__file__).resolve().parent / 'kronos_setup.py'}"


# ── Append-only JSONL files (trade ledger, forecast journal, lessons) and their lock ──

LOCK_TIMEOUT = 30.0
STALE_LOCK_SECONDS = 120.0


class FileLock:
    """Cross-platform exclusive lock: an O_EXCL lock file, stale after ``stale_after`` seconds."""

    busy_message = "Another Kronos run is writing the same file; try again in a minute."
    stale_after = STALE_LOCK_SECONDS

    def __init__(
        self,
        path: Path,
        *,
        timeout: float = LOCK_TIMEOUT,
        sleep: Callable[[float], None] = _time.sleep,
        clock: Callable[[], float] = _time.time,
    ) -> None:
        self.path, self.timeout, self._sleep, self._clock = path, timeout, sleep, clock

    def busy_error(self) -> SkillError:
        return SkillError(self.busy_message)

    def __enter__(self) -> FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = self._clock() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_stale():
                    self.path.unlink(missing_ok=True)
                    continue
                if self._clock() >= deadline:
                    raise self.busy_error() from None
                self._sleep(0.2)
                continue
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return self

    def _is_stale(self) -> bool:
        try:
            return self._clock() - self.path.stat().st_mtime > self.stale_after
        except FileNotFoundError:
            return False

    def __exit__(self, *exc: object) -> None:
        self.path.unlink(missing_ok=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Every JSON-object line of *path*; malformed lines are skipped, a missing file is []."""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def fold_rows(rows: Iterable[dict[str, Any]], key: str = "id") -> list[dict[str, Any]]:
    """Later rows with the same *key* update earlier ones; first-seen order is kept."""
    folded: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get(key):
            folded.setdefault(str(row[key]), {}).update(row)
    return list(folded.values())


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(row), ensure_ascii=False, default=str) + "\n")


def iso_z(value: Any) -> str | None:
    """ISO-8601 UTC with a ``Z`` suffix (seconds precision); ``None`` when unparsable."""
    if value in (None, ""):
        return None
    try:
        moment = parse_timestamp(value)
    except (ValueError, OverflowError, OSError):
        return None
    return moment.isoformat(timespec="seconds") + "Z"


def require_state() -> dict[str, Any]:
    state = load_state()
    if state is None or not state.get("venv_python"):
        raise SkillError(
            "The Kronos runtime is not installed for this Clawksis profile.",
            hint=f"Run `{setup_command()}` once (about 1.2 GB, a few minutes), "
            "or add --dry-run to validate the data without the model.",
        )
    return state


def running_in_skill_venv(state: dict[str, Any]) -> bool:
    venv_dir = state.get("venv_dir")
    if not venv_dir:
        return False
    try:
        return Path(sys.prefix).resolve() == Path(venv_dir).resolve()
    except OSError:
        return False


def reexec_in_skill_venv(
    script: Path, argv: Sequence[str], timeout: float
) -> int | None:
    """Re-run *script* under the skill venv's Python; ``None`` when already inside it."""
    state = require_state()
    if running_in_skill_venv(state):
        return None
    python = Path(state["venv_python"])
    if not python.exists():
        raise SkillError(
            f"The Kronos venv interpreter is missing ({python}).",
            hint=f"Re-run `{setup_command()} --force`.",
        )
    try:
        proc = subprocess.run(
            [str(python), str(script), *argv], check=False, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise SkillError(
            f"Kronos did not finish within {int(timeout)} s.",
            hint="Lower --samples, --lookback or --horizon, use --model mini, or raise --timeout.",
        ) from exc
    return proc.returncode


# ── Parsing ──


def parse_number(value: Any, *, decimal_comma: bool = False) -> float | None:
    """Float from a CSV/JSON cell; ``None`` for blank/NaN. Raises ValueError on garbage."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace(" ", "").replace(" ", "")
    if not text or text.lower() in {"nan", "null", "none", "-", "n/a"}:
        return None
    scale = 1.0
    if text[-1].lower() in _VOLUME_SUFFIX:
        scale = _VOLUME_SUFFIX[text[-1].lower()]
        text = text[:-1]
    if decimal_comma:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    number = float(text) * scale
    return number if math.isfinite(number) else None


def _normalize_iso(text: str) -> str:
    text = text.strip()
    if text[-1:] in {"Z", "z"}:
        text = text[:-1] + "+00:00"
    # Python 3.10's fromisoformat takes only 3 or 6 fractional digits; .NET emits 7.
    return re.sub(
        r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text, count=1
    )


def _naive_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def parse_timestamp(value: Any) -> datetime:
    """ISO 8601 (``Z``, offsets, 7-digit fractions), date-only, or epoch s/ms -> naive UTC."""
    if isinstance(value, datetime):
        return _naive_utc(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000.0 if abs(value) > 1e11 else float(value)
        return datetime.fromtimestamp(seconds, tz=UTC).replace(tzinfo=None)
    text = str(value).strip()
    if re.fullmatch(r"(19|20)\d{6}", text):  # YYYYMMDD, not an epoch
        return datetime.strptime(text, "%Y%m%d")
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return parse_timestamp(float(text))
    return _naive_utc(datetime.fromisoformat(_normalize_iso(text)))


def parse_time_column(values: Sequence[Any]) -> tuple[list[datetime], str | None]:
    """Parse every value with one format; returns (timestamps, warning-or-None)."""
    try:
        return [parse_timestamp(v) for v in values], None
    except (ValueError, OverflowError, OSError):
        pass
    for fmt in _SLASH_DATE_FORMATS:
        try:
            parsed = [datetime.strptime(str(v).strip(), fmt) for v in values]
        except ValueError:
            continue
        warning = None
        if fmt.startswith("%m/%d") and all(p.day <= 12 for p in parsed):
            warning = "dates like 03/04/2026 were read as month/day (US order)"
        return parsed, warning
    sample = ", ".join(str(v) for v in list(values)[:3])
    raise SkillError(
        f"Could not parse the time column (examples: {sample}).",
        hint="Use ISO dates such as 2026-10-22 or 2026-10-22T14:30:00Z.",
    )


def _map_columns(fieldnames: Iterable[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for name in fieldnames:
        key = _COLUMN_ALIASES.get(str(name).strip().lower().lstrip("﻿"))
        if key and key not in mapping:
            mapping[key] = name
    if "close" not in mapping and "price" in mapping:
        mapping["close"] = mapping["price"]
    return mapping


def _require_columns(mapping: dict[str, str], found: Iterable[str]) -> None:
    missing = [c for c in ("ts", *PRICE_COLUMNS) if c not in mapping]
    if missing:
        names = ["timestamps" if c == "ts" else c for c in missing]
        raise SkillError(
            f"Input is missing column(s): {', '.join(names)} (found: {', '.join(map(str, found))}).",
            hint="Expected timestamps/date plus open, high, low, close and optional volume.",
        )


def _row_prices(
    row: dict[str, Any], mapping: dict[str, str], decimal_comma: bool
) -> dict[str, float | None]:
    return {
        col: parse_number(row.get(mapping[col]), decimal_comma=decimal_comma)
        for col in PRICE_COLUMNS
    }


def rows_to_bars(
    rows: Sequence[dict[str, Any]], *, decimal_comma: bool = False
) -> tuple[list[Bar], list[str]]:
    """Validate raw rows into chronologically sorted, de-duplicated bars plus warnings."""
    if not rows:
        raise SkillError("Input has no rows.")
    mapping = _map_columns(rows[0].keys())
    _require_columns(mapping, rows[0].keys())
    times, time_warning = parse_time_column([r.get(mapping["ts"]) for r in rows])
    warnings = [time_warning] if time_warning else []
    bars: list[Bar] = []
    bad_rows: list[int] = []
    dropped = blank_volume = 0
    for index, (row, ts) in enumerate(zip(rows, times), start=1):
        try:
            prices = _row_prices(row, mapping, decimal_comma)
            volume = (
                parse_number(row.get(mapping["volume"]), decimal_comma=decimal_comma)
                if "volume" in mapping
                else None
            )
        except ValueError:
            bad_rows.append(index)
            continue
        if any(prices[c] is None for c in PRICE_COLUMNS):
            dropped += 1
            continue
        if "volume" in mapping and volume is None:
            blank_volume += 1
            volume = 0.0
        bars.append(Bar(ts, *(prices[c] for c in PRICE_COLUMNS), volume=volume))
    if bad_rows:
        raise SkillError(
            f"Non-numeric price or volume values in data rows {bad_rows[:5]}."
        )
    if dropped:
        warnings.append(f"dropped {dropped} row(s) with missing prices")
    if blank_volume:
        warnings.append(f"{blank_volume} blank volume value(s) were set to 0")
    bars, dupes = _sort_dedupe(bars)
    if dupes:
        warnings.append(f"dropped {dupes} duplicate timestamp(s) (kept the last)")
    inconsistent = sum(
        1 for b in bars if b.high < max(b.open, b.close) or b.low > min(b.open, b.close)
    )
    if inconsistent:
        warnings.append(f"{inconsistent} bar(s) have high/low outside open/close")
    return bars, warnings


def _sort_dedupe(bars: list[Bar]) -> tuple[list[Bar], int]:
    by_ts: dict[datetime, Bar] = {}
    for bar in bars:
        by_ts[bar.ts] = bar
    return [by_ts[ts] for ts in sorted(by_ts)], len(bars) - len(by_ts)


def _json_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("bars", "history", "candles", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
        raise SkillError("JSON input has no bars/history/candles/data list.")
    if isinstance(payload, list):
        return payload
    raise SkillError("JSON input must be a list of bars or an object holding one.")


def read_csv_text(text: str) -> tuple[list[dict[str, Any]], bool]:
    """CSV rows plus whether decimals use commas (``;``-delimited European exports)."""
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [dict(r) for r in reader], delimiter == ";"


def load_bars(path: Path) -> tuple[list[Bar], list[str]]:
    """Bars from a CSV or JSON file (stocks-skill history JSON and etoro_data JSON included)."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SkillError(
            f"Cannot read input file {path}: {exc.strerror or exc}"
        ) from exc
    stripped = text.lstrip()
    if Path(path).suffix.lower() == ".json" or stripped.startswith(("{", "[")):
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise SkillError(f"Input {path} is not valid JSON: {exc}") from exc
        return rows_to_bars(_json_rows(payload))
    rows, decimal_comma = read_csv_text(text)
    return rows_to_bars(rows, decimal_comma=decimal_comma)


# ── Intervals and trading calendars ──


def infer_step(timestamps: Sequence[datetime]) -> timedelta:
    """Bar size: the median positive gap (weekend gaps don't move the median of daily bars)."""
    gaps = sorted(
        (b - a).total_seconds() for a, b in itertools.pairwise(timestamps) if b > a
    )
    if not gaps:
        raise SkillError(
            "Need at least two distinct timestamps to infer the bar interval."
        )
    return timedelta(seconds=gaps[len(gaps) // 2])


def detect_calendar(timestamps: Sequence[datetime], step: timedelta) -> str:
    """24x7 when any bar falls on a weekend (crypto); otherwise the NYSE calendar."""
    if any(ts.weekday() >= 5 for ts in timestamps):
        return "24x7"
    return "nyse"


def describe_step(step: timedelta) -> str:
    seconds = int(step.total_seconds())
    for unit, size in (
        ("week", 604800),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
    ):
        if seconds >= size and seconds % size == 0:
            count = seconds // size
            return f"{count} {unit}{'s' if count != 1 else ''}"
    return f"{seconds} seconds"


def _next_weekday(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _following_days(
    after: date, count: int, nyse: bool
) -> list[tuple[date, datetime | None]]:
    """The *count* trading days after *after* with their close: weekdays (close unknown) or
    NYSE sessions (holidays skipped, early closes known)."""
    if not nyse:
        out: list[tuple[date, datetime | None]] = []
        day = after
        while len(out) < count:
            day = _next_weekday(day)
            out.append((day, None))
        return out
    from _kronos_calendar import nyse_sessions

    span = 2 * count + 10
    while True:
        sessions, _source = nyse_sessions(
            after + timedelta(days=1), after + timedelta(days=span)
        )
        if len(sessions) >= count:
            return [(day, close) for day, (_o, close) in sorted(sessions.items())][
                :count
            ]
        span *= 2


def _continuous(history: Sequence[datetime], step: timedelta, n: int) -> list[datetime]:
    return [history[-1] + step * (i + 1) for i in range(n)]


def _weekdays(history: Sequence[datetime], step: timedelta, n: int) -> list[datetime]:
    if step >= timedelta(days=6):  # weekly bars keep their weekday
        return _continuous(history, step, n)
    out: list[datetime] = []
    current = history[-1]
    while len(out) < n:
        current += step
        if current.weekday() < 5:
            out.append(current)
    return out


def _nyse_days(history: Sequence[datetime], step: timedelta, n: int) -> list[datetime]:
    if step >= timedelta(days=6):  # weekly bars keep their weekday
        return _continuous(history, step, n)
    last = history[-1]
    days = _following_days(last.date(), n, nyse=True)
    return [datetime.combine(day, last.time()) for day, _close in days]


def _session_slots(history: Sequence[datetime], days: int = 20) -> list[time]:
    weekday_bars = [ts for ts in history if ts.weekday() < 5]
    recent_days = sorted({ts.date() for ts in weekday_bars})[-days:]
    keep = set(recent_days)
    return sorted({ts.time() for ts in weekday_bars if ts.date() in keep})


def _day_slots(
    day: date, slots: Sequence[time], close: datetime | None
) -> list[datetime]:
    stamps = [datetime.combine(day, slot) for slot in slots]
    return [t for t in stamps if close is None or t < close]


def _nyse_close(day: date) -> datetime | None:
    from _kronos_calendar import nyse_session

    session = nyse_session(day)
    return session[1] if session else None


def _sessions(
    history: Sequence[datetime], step: timedelta, n: int, *, nyse: bool = False
) -> list[datetime]:
    """Replay the intraday bar times seen on recent weekdays; with *nyse*, holidays are skipped
    and bars at or after an early close are dropped."""
    slots = _session_slots(history)
    if len(slots) <= 1:
        return _nyse_days(history, step, n) if nyse else _weekdays(history, step, n)
    last = history[-1]
    close = _nyse_close(last.date()) if nyse else None
    out = [t for t in _day_slots(last.date(), slots, close) if t > last]
    cursor = last.date()
    while len(out) < n:
        wanted = -(-(n - len(out)) // len(slots)) + 1
        batch = _following_days(cursor, wanted, nyse)
        for day, close_at in batch:
            out.extend(_day_slots(day, slots, close_at))
        cursor = batch[-1][0]
    return out[:n]


def _nyse(history: Sequence[datetime], step: timedelta, n: int) -> list[datetime]:
    """NYSE trading days for daily bars, NYSE sessions for intraday bars."""
    if step >= timedelta(days=1):
        return _nyse_days(history, step, n)
    return _sessions(history, step, n, nyse=True)


_CALENDAR_GENERATORS: dict[
    str, Callable[[Sequence[datetime], timedelta, int], list[datetime]]
] = {
    "nyse": _nyse,
    "24x7": _continuous,
    "weekdays": _weekdays,
    "sessions": _sessions,
}


def future_timestamps(
    history: Sequence[datetime], n: int, calendar: str = "auto"
) -> tuple[list[datetime], str, timedelta]:
    """The next *n* bar timestamps after *history*; returns (timestamps, calendar, step).

    ``auto`` picks 24x7 for series with weekend bars and the NYSE calendar otherwise (exchange
    holidays and early closes skipped; pass ``weekdays`` or ``sessions`` for other markets).
    """
    step = infer_step(history)
    resolved = detect_calendar(history, step) if calendar == "auto" else calendar
    if resolved not in _CALENDAR_GENERATORS:
        raise SkillError(
            f"Unknown calendar {calendar!r}; choose one of {', '.join(CALENDARS)}."
        )
    return _CALENDAR_GENERATORS[resolved](history, step, n), resolved, step


def drop_unclosed_bar(bars: list[Bar], now: datetime) -> tuple[list[Bar], bool]:
    """Drop the newest bar when its period has not ended yet (a still-forming candle)."""
    if len(bars) < 2:
        return bars, False
    step = infer_step([b.ts for b in bars])
    if bars[-1].ts + step > _naive_utc(now):
        return bars[:-1], True
    return bars, False


# ── Bands, baseline and metrics ──


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (numpy's default method)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile of an empty sequence")
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def direction_of(change_pct: float, flat_band_pct: float = 0.1) -> str:
    if change_pct > flat_band_pct:
        return "up"
    if change_pct < -flat_band_pct:
        return "down"
    return "flat"


def summarize_paths(
    paths: Sequence[Sequence[dict[str, float]]],
    future: Sequence[datetime],
    last_close: float,
) -> dict[str, Any]:
    """Mean OHLCV per step across sampled paths, a p10–p90 close band, and a summary."""
    if not paths or any(len(p) != len(future) for p in paths):
        raise SkillError("Model returned paths that do not match the forecast horizon.")
    rows = []
    for step, ts in enumerate(future):
        closes = [p[step]["close"] for p in paths]
        row: dict[str, Any] = {"timestamp": ts.isoformat()}
        for col in (*PRICE_COLUMNS, "volume"):
            values = [p[step].get(col, 0.0) for p in paths]
            row[col] = sum(values) / len(values)
        row["close_p10"] = quantile(closes, 0.1)
        row["close_p50"] = quantile(closes, 0.5)
        row["close_p90"] = quantile(closes, 0.9)
        rows.append(row)
    final = rows[-1]["close"]
    change = (final - last_close) / last_close * 100.0 if last_close else 0.0
    inconsistent = sum(
        1
        for r in rows
        if r["high"] < max(r["open"], r["close"])
        or r["low"] > min(r["open"], r["close"])
    )
    return {
        "forecast": rows,
        "summary": {
            "close_at_horizon": final,
            "pct_change": change,
            "direction": direction_of(change),
            "band_at_horizon": [rows[-1]["close_p10"], rows[-1]["close_p90"]],
        },
        "inconsistent_rows": inconsistent,
    }


def naive_forecast(last_close: float, horizon: int) -> list[float]:
    """The persistence baseline: tomorrow (and every later step) equals the last close."""
    return [last_close] * horizon


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def _errors(
    predicted: Sequence[float], actual: Sequence[float]
) -> tuple[list[float], list[float]]:
    abs_err = [abs(p - a) for p, a in zip(predicted, actual)]
    pct_err = [abs(p - a) / abs(a) * 100.0 for p, a in zip(predicted, actual) if a]
    return abs_err, pct_err


def _hit(predicted_end: float, last: float, actual_move: int) -> int:
    return int(_sign(predicted_end - last) == actual_move and actual_move != 0)


def _forecaster_scores(origins: Sequence[dict[str, Any]], key: str) -> dict[str, Any]:
    """MAE/MAPE over all steps and direction hit rate at the horizon of ``origin[key]``."""
    abs_err: list[float] = []
    pct_err: list[float] = []
    hits = 0
    for origin in origins:
        last, actual, predicted = origin["last_close"], origin["actual"], origin[key]
        errors = _errors(predicted, actual)
        abs_err.extend(errors[0])
        pct_err.extend(errors[1])
        hits += _hit(predicted[-1], last, _sign(actual[-1] - last))
    return {
        "mae": sum(abs_err) / len(abs_err),
        "mape_pct": sum(pct_err) / len(pct_err) if pct_err else None,
        "direction_hit_rate": hits / len(origins),
    }


def _skill(model_mae: float, baseline_mae: float) -> float:
    return 1.0 - model_mae / baseline_mae if baseline_mae else 0.0


def score_origins(origins: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """MAE/MAPE (all horizon steps) and direction hit-rate (at the horizon) vs the baselines.

    Each origin is ``{"last_close": float, "actual": [...], "kronos": [...]}`` plus, when the
    classical baseline ran, ``"ets": [...]``. ETS scores appear only when every origin has one.
    """
    if not origins:
        raise SkillError("No backtest origins to score.")
    with_naive = [
        {**o, "naive": naive_forecast(o["last_close"], len(o["actual"]))}
        for o in origins
    ]
    kronos = _forecaster_scores(with_naive, "kronos")
    naive = _forecaster_scores(with_naive, "naive")
    naive["direction_hit_rate"] = None  # a flat forecast never calls a direction
    ups = sum(int(o["actual"][-1] > o["last_close"]) for o in origins)
    scores: dict[str, Any] = {
        "origins": len(origins),
        "kronos": kronos,
        "naive_last_close": naive,
        "always_up_hit_rate": ups / len(origins),
        "mae_skill_vs_naive": _skill(kronos["mae"], naive["mae"]),
        "ets": None,
        "mae_skill_vs_ets": None,
    }
    if all(o.get("ets") for o in origins):
        ets = _forecaster_scores(with_naive, "ets")
        scores["ets"] = ets
        scores["mae_skill_vs_ets"] = _skill(kronos["mae"], ets["mae"])
    return scores


MIN_VERDICT_ORIGINS = 10
MIN_SKILL = 0.02  # MAE at least 2% lower than a baseline counts as beating it
MIN_HIT_RATE = 0.5
_VERDICT_TEXT = {
    "adds_value": "Kronos beat both baselines here: MAE {skill:.0%} lower than repeating the last "
    "close and {ets_skill:.0%} lower than the classical ETS forecast, direction right {hit:.0%} of "
    "the time. Still noisy: one input among many, not a signal to trade.",
    "no_clear_edge": "Kronos was about as accurate as simply repeating the last close (MAE skill "
    "{skill:+.0%}); its forecast adds little for this instrument.",
    "no_edge_over_ets": "Kronos beat repeating the last close (MAE skill {skill:+.0%}) but not the "
    "classical ETS forecast (MAE skill {ets_skill:+.0%}) or not often enough in direction "
    "({hit:.0%}); a plain statistical model does as well, so its forecast adds little here.",
    "no_ets_baseline": "Kronos beat repeating the last close (MAE skill {skill:+.0%}), but the "
    "classical ETS baseline did not run, so it cannot be called useful; re-run the backtest.",
    "worse_than_naive": "Kronos was LESS accurate than repeating the last close (MAE skill "
    "{skill:+.0%}); do not present its forecast as useful for this instrument.",
    "inconclusive": "Too few test windows ({origins}) to judge; fetch more history or lower --stride.",
}
# Detail code -> verdict code: anything short of beating both baselines is "no_clear_edge".
_VERDICT_CODE = {
    "no_edge_over_ets": "no_clear_edge",
    "no_ets_baseline": "no_clear_edge",
}


def verdict_detail(scores: dict[str, Any]) -> str:
    """The verdict with the reason a forecast that beat "no change" still falls short."""
    skill, ets_skill = scores["mae_skill_vs_naive"], scores.get("mae_skill_vs_ets")
    hit = scores["kronos"]["direction_hit_rate"]
    if scores["origins"] < MIN_VERDICT_ORIGINS:
        return "inconclusive"
    if skill <= -MIN_SKILL:
        return "worse_than_naive"
    if skill <= MIN_SKILL:
        return "no_clear_edge"
    if ets_skill is None:
        return "no_ets_baseline"
    if ets_skill > MIN_SKILL and hit >= MIN_HIT_RATE:
        return "adds_value"
    return "no_edge_over_ets"


def verdict(scores: dict[str, Any]) -> tuple[str, str]:
    """(code, plain-language text). ``adds_value`` needs a 2%+ lower MAE than BOTH repeating the
    last close and the ETS baseline, and the direction right at least half the time."""
    detail = verdict_detail(scores)
    text = _VERDICT_TEXT[detail].format(
        skill=scores["mae_skill_vs_naive"],
        ets_skill=scores.get("mae_skill_vs_ets") or 0.0,
        hit=scores["kronos"]["direction_hit_rate"],
        origins=scores["origins"],
    )
    return _VERDICT_CODE.get(detail, detail), text


# ── Output ──


def _fmt_cell(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.4f}" if abs(value) < 10 else f"{value:,.2f}"
    return "" if value is None else str(value)


def render_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Fixed-width text table: numbers right-aligned, everything else left-aligned."""
    cells = [[_fmt_cell(v) for v in row] for row in rows]
    widths = [
        max(len(h), *(len(r[i]) for r in cells)) if cells else len(h)
        for i, h in enumerate(headers)
    ]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths))]
    lines.append("  ".join("-" * w for w in widths))
    for raw, row in zip(rows, cells):
        lines.append(
            "  ".join(
                c.rjust(w) if isinstance(v, (int, float)) else c.ljust(w)
                for v, c, w in zip(raw, row, widths)
            ).rstrip()
        )
    return "\n".join(lines)


def dump_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def run_cli(main: Callable[[], int]) -> int:
    """Entry wrapper: SkillError -> JSON error on stdout, exit code 2."""
    try:
        return main()
    except SkillError as exc:
        print(dump_json(exc.payload()))
        return 2
