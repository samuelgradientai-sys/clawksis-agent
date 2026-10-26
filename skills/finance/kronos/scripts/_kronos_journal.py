"""Forecast journal: every Kronos forecast, later scored against what the price really did.

``$CLAWK_HOME/kronos/forecasts.jsonl`` is append-only. ``kronos_forecast.py`` writes one line per
forecast; ``kronos_review.py`` appends ``{"id", "outcome"}`` lines that fold into it once the
forecast's horizon has passed. The recent directional hit rate per symbol computed here is what
``etoro_trade.py buy`` consults before an automatic buy (``gate_status``). Stdlib only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

from _kronos_common import (
    UTC,
    Bar,
    FileLock,
    append_jsonl,
    direction_of,
    fold_rows,
    iso_z,
    kronos_home,
    parse_timestamp,
    read_jsonl,
)

FLAT_BAND_PCT = 0.1  # moves within ±0.1% count as "flat" (direction_of's default)
RECENT_WINDOW = 10  # matured forecasts per symbol that "recent accuracy" looks at
MIN_MATURED = 5  # fewer than this and no accuracy claim is made either way
GATE_MIN_HIT_RATE = 0.5  # below this, automatic buys of the symbol are refused


class JournalLock(FileLock):
    busy_message = "Another Kronos run is updating the journal; try again in a minute."


def forecasts_path(kronos_dir: Path | None = None) -> Path:
    return (kronos_dir or kronos_home()) / "forecasts.jsonl"


def lock_for(path: Path) -> JournalLock:
    return JournalLock(path.with_suffix(".lock"))


def symbol_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(tzinfo=None) if moment.tzinfo else moment


# ── Writing ──


def forecast_record(
    result: dict[str, Any],
    *,
    label: str,
    source: str,
    step_seconds: int,
    now: datetime,
) -> dict[str, Any]:
    """The journal line for one forecast result (``kronos_forecast.build_result`` output)."""
    summary = result["summary"]
    return {
        "id": str(uuid.uuid4()),
        "made_at": iso_z(now),
        "symbol": label,
        "source": source,
        "interval": result["interval"],
        "step_seconds": int(step_seconds),
        "horizon": int(result["horizon"]),
        "model": result.get("model"),
        "last_timestamp": result["last_timestamp"],
        "last_close": float(result["last_close"]),
        "target_timestamp": result["forecast"][-1]["timestamp"],
        "predicted_close": float(summary["close_at_horizon"]),
        "pct_change": float(summary["pct_change"]),
        "direction": summary["direction"],
        "band": [float(v) for v in summary["band_at_horizon"]],
    }


def append_locked(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    with lock_for(path):
        for row in rows:
            append_jsonl(path, row)


def read_forecasts(path: Path | None = None) -> list[dict[str, Any]]:
    return fold_rows(read_jsonl(path or forecasts_path()))


# ── Scoring ──


def is_due(record: dict[str, Any], now: datetime) -> bool:
    """True once the target bar has closed (target open time + one bar)."""
    try:
        target = parse_timestamp(record["target_timestamp"])
        step = timedelta(seconds=int(record.get("step_seconds") or 0))
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return False
    return target + step <= _naive_utc(now)


def evaluate(
    record: dict[str, Any], bars: Sequence[Bar], now: datetime
) -> dict[str, Any] | None:
    """Outcome of *record* from closed *bars*; ``None`` while the horizon bar is not in them.

    The actual price is the close of the horizon-th bar after the forecast's last bar, so an
    exchange holiday the forecast calendar did not know about shifts nothing.
    """
    last_ts = parse_timestamp(record["last_timestamp"])
    if not bars or bars[0].ts > last_ts:
        return None  # the bars start after the forecast was made: cannot line them up
    after = [b for b in bars if b.ts > last_ts]
    horizon = int(record["horizon"])
    if len(after) < horizon:
        return None
    actual = after[horizon - 1]
    last, predicted = float(record["last_close"]), float(record["predicted_close"])
    change = (actual.close - last) / last * 100.0 if last else 0.0
    actual_direction = direction_of(change, FLAT_BAND_PCT)
    error = abs(predicted - actual.close) / abs(actual.close) * 100.0
    naive_error = abs(last - actual.close) / abs(actual.close) * 100.0
    band = record.get("band") or []
    return {
        "actual_close": actual.close,
        "actual_timestamp": actual.ts.isoformat(),
        "actual_pct_change": change,
        "actual_direction": actual_direction,
        "direction_hit": actual_direction == record.get("direction"),
        "error_pct": error,
        "naive_error_pct": naive_error,
        "beat_naive": error < naive_error,
        "in_band": (band[0] <= actual.close <= band[1]) if len(band) == 2 else None,
        "reviewed_at": iso_z(now),
    }


def scored(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Records that have an outcome, oldest outcome first."""
    rows = [r for r in records if isinstance(r.get("outcome"), dict)]
    return sorted(rows, key=lambda r: str(r["outcome"].get("actual_timestamp", "")))


def accuracy(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Direction hits, error and band coverage over scored *rows*."""
    outcomes = [r["outcome"] for r in rows]
    count = len(outcomes)
    if not count:
        return {"matured": 0, "hits": 0, "hit_rate": None}
    hits = sum(bool(o.get("direction_hit")) for o in outcomes)
    banded = [o for o in outcomes if o.get("in_band") is not None]
    return {
        "matured": count,
        "hits": hits,
        "hit_rate": hits / count,
        "beat_naive": sum(bool(o.get("beat_naive")) for o in outcomes),
        "mean_error_pct": sum(float(o.get("error_pct") or 0.0) for o in outcomes)
        / count,
        "banded": len(banded),
        "outside_band": sum(not o["in_band"] for o in banded),
        "predicted_up": sum(r.get("direction") == "up" for r in rows),
        "actual_up": sum(o.get("actual_direction") == "up" for o in outcomes),
    }


def group_accuracy(
    records: Iterable[dict[str, Any]], window: int = RECENT_WINDOW
) -> dict[tuple[str, str], dict[str, Any]]:
    """Recent accuracy per (symbol, interval) over the last *window* scored forecasts."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in scored(records):
        key = (symbol_key(row.get("symbol")), str(row.get("interval") or ""))
        groups.setdefault(key, []).append(row)
    return {key: accuracy(rows[-window:]) for key, rows in groups.items()}


def gate_status(
    records: Iterable[dict[str, Any]], symbol: str, window: int = RECENT_WINDOW
) -> dict[str, Any]:
    """Recent directional accuracy of *symbol* (any interval) and whether it blocks buys."""
    rows = [
        r for r in scored(records) if symbol_key(r.get("symbol")) == symbol_key(symbol)
    ]
    stats = accuracy(rows[-window:])
    blocked = stats["matured"] >= MIN_MATURED and stats["hit_rate"] < GATE_MIN_HIT_RATE
    return {
        "symbol": symbol_key(symbol),
        "matured": stats["matured"],
        "hits": stats["hits"],
        "hit_rate": stats["hit_rate"],
        "min_matured": MIN_MATURED,
        "min_hit_rate": GATE_MIN_HIT_RATE,
        "blocked": blocked,
    }
