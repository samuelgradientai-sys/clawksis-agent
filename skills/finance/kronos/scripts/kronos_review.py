#!/usr/bin/env python3
"""Learning loop: score matured Kronos forecasts, review closed trades, write lessons.

1. Every journaled forecast whose horizon bar has closed is scored against real prices: the
   close of the horizon-th bar after the forecast (direction hit or miss, error %, whether it
   beat "no change", whether the price stayed inside the p10–p90 band). Prices come from bar
   files the agent passes (``--bars AAPL=aapl_1d.csv``, any format kronos_forecast.py reads)
   and/or eToro candles (``--etoro``, read-only, interval matched to each forecast).
2. Recent accuracy per symbol and bar size (last ``--window`` scored forecasts), the buy gate
   per symbol (what ``etoro_trade.py buy`` will enforce), and closed trades with their
   estimated P&L from the trade ledger.
3. Lessons rebuilt from all of the above; only new, changed or retired ones are written to
   ``$CLAWK_HOME/kronos/lessons.jsonl``. Then the dashboard snapshot is refreshed.

Usage:
  kronos_review.py [--bars SYMBOL=FILE ...] [--etoro] [--window 10] [--format text|json]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    DISCLAIMER,
    UTC,
    Bar,
    SkillError,
    describe_step,
    dump_json,
    infer_step,
    kronos_home,
    load_bars,
    parse_timestamp,
    run_cli,
)
from _kronos_journal import (
    MIN_MATURED,
    RECENT_WINDOW,
    append_locked,
    evaluate,
    forecasts_path,
    gate_status,
    group_accuracy,
    is_due,
    read_forecasts,
    symbol_key,
)
from _kronos_lessons import (
    active_lessons,
    build_lessons,
    lessons_path,
    trade_stats,
    update_lessons,
)
from etoro_trade import ledger_path, read_ledger

ETORO_INTERVALS = {
    60: "OneMinute",
    300: "FiveMinutes",
    600: "TenMinutes",
    900: "FifteenMinutes",
    1800: "ThirtyMinutes",
    3600: "OneHour",
    14400: "FourHours",
    86400: "OneDay",
    604800: "OneWeek",
}
MAX_CANDLES = 1000

Fetcher = Callable[[str, str, int], tuple[list[Bar], dict[str, Any], list[str]]]


@dataclass
class ReviewDeps:
    """Files, clock and the eToro candle fetcher, injectable for tests."""

    kronos_dir: Path | None = None
    config_path: Path | None = None
    dashboard: Path | None = None
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    fetch: Fetcher | None = None

    def home(self) -> Path:
        return self.kronos_dir or kronos_home()

    def fetcher(self) -> Fetcher:
        if self.fetch is None:
            from etoro_data import fetch_bars

            self.fetch = fetch_bars
        return self.fetch


def bars_arg(value: str) -> tuple[str, Path]:
    symbol, sep, path = value.partition("=")
    if not sep or not symbol.strip() or not path.strip():
        raise argparse.ArgumentTypeError("use SYMBOL=FILE, e.g. AAPL=aapl_1d.csv")
    return symbol_key(symbol), Path(path.strip()).expanduser()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score matured Kronos forecasts and update the lessons."
    )
    parser.add_argument(
        "--bars",
        type=bars_arg,
        action="append",
        default=[],
        metavar="SYMBOL=FILE",
        help="closed bars for SYMBOL (CSV/JSON); repeat per symbol",
    )
    parser.add_argument(
        "--etoro",
        action="store_true",
        help="fetch candles from eToro (read-only) for symbols without --bars",
    )
    parser.add_argument(
        "--window",
        type=int,
        choices=range(MIN_MATURED, 51),
        default=RECENT_WINDOW,
        metavar=f"{MIN_MATURED}-50",
        help="recent scored forecasts per symbol used for accuracy and lessons",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--json",
        dest="format",
        action="store_const",
        const="json",
        help="--format json",
    )
    return parser


# ── Prices ──


def _check_step(bars: list[Bar], step_seconds: int, origin: str) -> None:
    found = int(infer_step([b.ts for b in bars]).total_seconds())
    if found != step_seconds:
        raise SkillError(
            f"{origin} has {describe_step(timedelta(seconds=found))} bars, but the forecasts "
            f"used {describe_step(timedelta(seconds=step_seconds))} bars."
        )


def _fetch_count(
    records: list[dict[str, Any]], step_seconds: int, now: datetime
) -> int:
    oldest = min(parse_timestamp(r["last_timestamp"]) for r in records)
    span = (now.astimezone(UTC).replace(tzinfo=None) - oldest).total_seconds()
    longest = max(int(r.get("horizon") or 1) for r in records)
    return int(min(MAX_CANDLES, max(span / step_seconds, longest) + 10))


def _bars_for(
    key: tuple[str, int],
    records: list[dict[str, Any]],
    files: dict[str, Path],
    args: argparse.Namespace,
    deps: ReviewDeps,
) -> list[Bar] | str:
    """Bars for one (symbol, bar size), or a note saying why there are none."""
    symbol, step = key
    if symbol in files:
        bars, _warnings = load_bars(files[symbol])
        _check_step(bars, step, str(files[symbol]))
        return bars
    if not args.etoro:
        return f"{symbol}: no prices; pass --bars {symbol}=FILE or --etoro."
    interval = ETORO_INTERVALS.get(step)
    if interval is None:
        return (
            f"{symbol}: eToro has no {describe_step(timedelta(seconds=step))} candles."
        )
    count = _fetch_count(records, step, deps.now())
    bars, _meta, _warnings = deps.fetcher()(symbol, interval, count)
    return bars


def load_prices(
    due: list[dict[str, Any]], args: argparse.Namespace, deps: ReviewDeps
) -> tuple[dict[tuple[str, int], list[Bar]], list[str]]:
    files = dict(args.bars)
    groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for record in due:
        key = (symbol_key(record.get("symbol")), int(record.get("step_seconds") or 0))
        groups.setdefault(key, []).append(record)
    prices: dict[tuple[str, int], list[Bar]] = {}
    notes: list[str] = []
    for key, records in groups.items():
        try:
            found = _bars_for(key, records, files, args, deps)
        except SkillError as exc:
            notes.append(f"{key[0]}: {exc}")
            continue
        if isinstance(found, str):
            notes.append(found)
        else:
            prices[key] = found
    return prices, notes


# ── Review ──


def score_due(
    due: list[dict[str, Any]],
    prices: dict[tuple[str, int], list[Bar]],
    now: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(outcome rows to append, the scored forecasts with their outcome)."""
    rows, scored_now = [], []
    for record in due:
        key = (symbol_key(record.get("symbol")), int(record.get("step_seconds") or 0))
        if key not in prices:
            continue
        outcome = evaluate(record, prices[key], now)
        if outcome is None:
            continue
        rows.append({"id": record["id"], "outcome": outcome})
        scored_now.append({**record, "outcome": outcome})
    return rows, scored_now


def _scored_summary(row: dict[str, Any]) -> dict[str, Any]:
    outcome = row["outcome"]
    return {
        "symbol": row.get("symbol"),
        "interval": row.get("interval"),
        "made_at": row.get("made_at"),
        "last_close": row.get("last_close"),
        "predicted_close": row.get("predicted_close"),
        "direction": row.get("direction"),
        "actual_close": outcome["actual_close"],
        "actual_direction": outcome["actual_direction"],
        "hit": outcome["direction_hit"],
        "error_pct": round(outcome["error_pct"], 2),
    }


def _accuracy_rows(records: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    rows = []
    for (symbol, interval), stats in sorted(group_accuracy(records, window).items()):
        rows.append(
            {
                "symbol": symbol,
                "interval": interval,
                "matured": stats["matured"],
                "hits": stats["hits"],
                "hit_rate": round(stats["hit_rate"], 3),
                "beat_naive": stats["beat_naive"],
                "mean_error_pct": round(stats["mean_error_pct"], 2),
            }
        )
    return rows


def review(args: argparse.Namespace, deps: ReviewDeps) -> dict[str, Any]:
    home = deps.home()
    journal = forecasts_path(home)
    now = deps.now()
    records = read_forecasts(journal)
    due = [r for r in records if "outcome" not in r and is_due(r, now)]
    prices, notes = load_prices(due, args, deps)
    rows, scored_now = score_due(due, prices, now)
    append_locked(journal, rows)
    records = read_forecasts(journal)
    ledger = read_ledger(home / ledger_path().name)
    changes = update_lessons(
        build_lessons(records, ledger, args.window), now, lessons_path(home)
    )
    symbols = sorted({symbol_key(r.get("symbol")) for r in records} - {""})
    hits = sum(bool(r["outcome"]["direction_hit"]) for r in scored_now)
    return {
        "ok": True,
        "reviewed_now": len(scored_now),
        "hits_now": hits,
        "misses_now": len(scored_now) - hits,
        "waiting": sum(1 for r in records if "outcome" not in r),
        "scored": [_scored_summary(r) for r in scored_now],
        "accuracy": _accuracy_rows(records, args.window),
        "buy_gate": [gate_status(records, s, args.window) for s in symbols],
        "closed_trades": trade_stats(ledger),
        "lessons": [
            {
                "text": lesson.get("text"),
                "tone": lesson.get("tone"),
                "symbol": lesson.get("symbol"),
            }
            for lesson in active_lessons(lessons_path(home))
        ],
        "lesson_changes": len(changes),
        "notes": notes,
        "journal": str(journal),
        "disclaimer": DISCLAIMER,
    }


def render_text(result: dict[str, Any]) -> str:
    lines = [
        f"Reviewed {result['reviewed_now']} matured forecast(s) now: {result['hits_now']} "
        f"right, {result['misses_now']} wrong; {result['waiting']} still waiting for prices "
        "or for their horizon.",
    ]
    for row in result["accuracy"]:
        lines.append(
            f"- {row['symbol']} {row['interval']}: direction right {row['hits']}/"
            f"{row['matured']}, avg error {row['mean_error_pct']:.2f}%, beat 'no change' "
            f"{row['beat_naive']}/{row['matured']}"
        )
    blocked = [g["symbol"] for g in result["buy_gate"] if g["blocked"]]
    if blocked:
        lines.append(f"Automatic buys blocked for: {', '.join(blocked)}")
    for symbol, s in result["closed_trades"].items():
        lines.append(
            f"- closed trades {symbol}: {s['n']} ({s['wins']} won, {s['losses']} lost, "
            f"net {s['net']:+.2f} USD est.)"
        )
    if result["lessons"]:
        lines.append("Lessons (active):")
        lines.extend(f"- {lesson['text']}" for lesson in result["lessons"])
    lines.append(f"Lesson changes this run: {result['lesson_changes']}")
    lines.extend(f"note: {note}" for note in result["notes"])
    if result.get("dashboard"):
        lines.append(f"dashboard: {result['dashboard']}")
    lines.append(result["disclaimer"])
    return "\n".join(lines)


def main(argv: list[str] | None = None, deps: ReviewDeps | None = None) -> int:
    args = build_parser().parse_args(argv)
    deps = deps or ReviewDeps()
    result = review(args, deps)
    from kronos_dashboard import refresh_safely

    path = refresh_safely(
        config_path=deps.config_path,
        kronos_dir=deps.home(),
        out=deps.dashboard,
        now=deps.now(),
    )
    result["dashboard"] = str(path) if path else None
    print(render_text(result) if args.format == "text" else dump_json(result))
    return 0


if __name__ == "__main__":
    sys.exit(run_cli(main))
