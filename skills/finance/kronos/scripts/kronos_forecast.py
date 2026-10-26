#!/usr/bin/env python3
"""Forecast the next N OHLCV candles with Kronos (CPU-friendly defaults).

Input: --input FILE (CSV or JSON: timestamps/date + open/high/low/close [+volume];
the stocks skill's history JSON and etoro_data.py output both work) or
--etoro SYMBOL --interval OneDay --lookback 400 (read-only eToro candles).

Output: table (chat), json or csv; K sampled paths give a p10–p90 close band; --plot
writes a PNG for MEDIA: delivery. Always carries a not-financial-advice disclaimer.
The script starts under any Python and re-launches itself inside the skill venv that
kronos_setup.py built; --dry-run validates data and timestamps without the model.

Every real forecast is appended to the forecast journal ($CLAWK_HOME/kronos/forecasts.jsonl,
skip with --no-journal) so kronos_review.py can later score it; the output then carries the
symbol's recent track record and active lessons, and the dashboard snapshot is refreshed.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    CALENDARS,
    DEFAULT_MODEL,
    DISCLAIMER,
    MAX_CONTEXT,
    MIN_BARS,
    MODEL_NAMES,
    UTC,
    Bar,
    SkillError,
    describe_step,
    dump_json,
    future_timestamps,
    kronos_home,
    load_bars,
    reexec_in_skill_venv,
    render_table,
    require_state,
    run_cli,
    summarize_paths,
)
from _kronos_journal import (
    append_locked,
    forecast_record,
    forecasts_path,
    gate_status,
    read_forecasts,
    symbol_key,
)
from _kronos_lessons import active_lessons, lessons_for_symbol, lessons_path

DEFAULT_LOOKBACK = 400
MAX_HORIZON = 240
HONESTY_NOTE = (
    "Run kronos_backtest.py on this instrument before presenting this forecast as useful; "
    "Kronos often fails to beat a repeat-the-last-close baseline."
)


def _bounded(low: int, high: int):
    def parse(value: str) -> int:
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number

    return parse


def add_data_args(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="CSV or JSON file with OHLCV bars")
    source.add_argument(
        "--etoro", metavar="SYMBOL", help="fetch candles from eToro (read-only)"
    )
    parser.add_argument(
        "--interval",
        default="OneDay",
        help="eToro interval: OneDay, OneHour, FifteenMinutes, ...",
    )


def add_model_args(
    parser: argparse.ArgumentParser, *, samples: int, lookback: int | None
) -> None:
    parser.add_argument(
        "--lookback",
        type=_bounded(MIN_BARS, 2048),
        default=lookback,
        help="history bars fed to the model",
    )
    parser.add_argument("--model", choices=MODEL_NAMES, default=DEFAULT_MODEL)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    parser.add_argument(
        "--samples",
        type=_bounded(1, 64),
        default=samples,
        help="sampled paths (CPU cost grows linearly)",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--threads",
        type=_bounded(1, 256),
        default=None,
        help="torch CPU threads (default: all cores)",
    )
    parser.add_argument(
        "--timeout",
        type=_bounded(30, 86400),
        default=1800,
        help="seconds before the model run is aborted",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate data and plan; do not load the model",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Forecast the next candles with Kronos. Not financial advice."
    )
    add_data_args(parser)
    parser.add_argument(
        "--horizon",
        type=_bounded(1, MAX_HORIZON),
        default=10,
        help="candles to forecast",
    )
    add_model_args(parser, samples=8, lookback=None)
    parser.add_argument(
        "--calendar",
        choices=CALENDARS,
        default="auto",
        help="future timestamps: auto (24x7 or nyse), nyse, weekdays, 24x7, sessions",
    )
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument(
        "--plot",
        metavar="PNG",
        help="write a chart; 'auto' saves under $CLAWK_HOME/kronos/charts/",
    )
    parser.add_argument(
        "--symbol",
        metavar="LABEL",
        help="symbol recorded in the journal (default: the eToro symbol or the file name)",
    )
    parser.add_argument(
        "--no-journal",
        action="store_true",
        help="do not record this forecast for later review (ad-hoc experiments)",
    )
    return parser


def load_input(
    args: argparse.Namespace, fetch_count: int
) -> tuple[list[Bar], dict[str, Any], list[str]]:
    if args.input:
        bars, warnings = load_bars(args.input)
        return (
            bars,
            {"source": "file", "input": str(Path(args.input).resolve())},
            warnings,
        )
    from etoro_data import fetch_bars

    bars, meta, warnings = fetch_bars(args.etoro, args.interval, fetch_count)
    return bars, meta, warnings


def resolve_lookback(
    requested: int | None, model: str, available: int
) -> tuple[int, list[str]]:
    """Clamp to the checkpoint's context window and the history on hand."""
    warnings = []
    max_ctx = MAX_CONTEXT[model]
    lookback = requested or min(DEFAULT_LOOKBACK, max_ctx)
    if lookback > max_ctx:
        warnings.append(
            f"lookback {lookback} exceeds Kronos-{model}'s context; using {max_ctx}"
        )
        lookback = max_ctx
    if available < MIN_BARS:
        raise SkillError(
            f"Only {available} bars of history; Kronos needs at least {MIN_BARS} (ideally 300+).",
            hint="Fetch a longer range or a shorter interval.",
        )
    if available < lookback:
        warnings.append(
            f"only {available} bars available; lookback reduced from {lookback}"
        )
        lookback = available
    return lookback, warnings


def plan_forecast(bars: list[Bar], args: argparse.Namespace) -> dict[str, Any]:
    lookback, warnings = resolve_lookback(args.lookback, args.model, len(bars))
    window = bars[-lookback:]
    future, calendar, step = future_timestamps(
        [b.ts for b in bars], args.horizon, args.calendar
    )
    if args.horizon > lookback // 4:
        warnings.append(
            f"horizon {args.horizon} is long relative to lookback {lookback}; accuracy drops with distance"
        )
    if lookback < 200:
        warnings.append("under 200 bars of context; forecasts are less stable")
    return {
        "window": window,
        "future": future,
        "lookback": lookback,
        "calendar": calendar,
        "interval": describe_step(step),
        "step_seconds": int(step.total_seconds()),
        "warnings": warnings,
    }


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "series"


def plot_path(value: str, label: str) -> Path:
    if value != "auto":
        return Path(value).expanduser().resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return kronos_home() / "charts" / f"{_slug(label)}-{stamp}.png"


def build_result(
    args: argparse.Namespace,
    meta: dict[str, Any],
    plan: dict[str, Any],
    paths: list[list[dict[str, float]]],
    state: dict[str, Any],
) -> dict[str, Any]:
    last = plan["window"][-1]
    summary = summarize_paths(paths, plan["future"], last.close)
    warnings = list(plan["warnings"])
    if summary.pop("inconsistent_rows"):
        warnings.append(
            "some forecast rows have high/low outside open/close (Kronos does not enforce OHLC rules)"
        )
    if args.samples > 1:
        warnings.append(
            "the p10–p90 band reflects model sampling only and has been ~2.7x too narrow in independent tests"
        )
    entry = (state.get("models") or {}).get(args.model, {})
    return {
        "ok": True,
        **meta,
        "model": f"Kronos-{args.model}",
        "model_revision": entry.get("model_revision"),
        "upstream_sha": state.get("upstream_sha"),
        "device": args.device,
        "interval": plan["interval"],
        "calendar": plan["calendar"],
        "lookback": plan["lookback"],
        "horizon": args.horizon,
        "samples": args.samples,
        "seed": args.seed,
        "last_timestamp": last.ts.isoformat(),
        "last_close": last.close,
        **summary,
        "warnings": warnings,
        "honesty_check": HONESTY_NOTE,
        "disclaimer": DISCLAIMER,
    }


def journal_label(args: argparse.Namespace, meta: dict[str, Any]) -> str:
    raw = args.symbol or meta.get("symbol") or Path(str(meta.get("input", ""))).stem
    return symbol_key(raw) or "SERIES"


def journal_forecast(
    result: dict[str, Any],
    *,
    label: str,
    source: str,
    step_seconds: int,
    kronos_dir: Path | None = None,
    now: datetime | None = None,
) -> None:
    """Record the forecast for later review and attach the symbol's record and lessons.

    A journal failure only adds a warning: the forecast itself is already computed.
    """
    path = forecasts_path(kronos_dir)
    record = forecast_record(
        result,
        label=label,
        source=source,
        step_seconds=step_seconds,
        now=now or datetime.now(UTC),
    )
    try:
        append_locked(path, [record])
        gate = gate_status(read_forecasts(path), label)
        lessons = lessons_for_symbol(active_lessons(lessons_path(kronos_dir)), label)
    except (OSError, ValueError, SkillError) as exc:
        result["warnings"].append(f"forecast not journaled: {exc}")
        return
    result["journal"] = {"id": record["id"], "symbol": label, "path": str(path)}
    result["track_record"] = {
        k: gate[k] for k in ("matured", "hits", "hit_rate", "blocked")
    }
    result["lessons"] = [str(lesson.get("text")) for lesson in lessons]


def _track_record_lines(result: dict[str, Any]) -> list[str]:
    record = result.get("track_record") or {}
    lines = []
    if record.get("matured"):
        lines.append(
            f"track record: direction right {record['hits']}/{record['matured']} in the "
            "last reviewed forecasts"
            + (" (automatic buys blocked)" if record.get("blocked") else "")
        )
    lines.extend(f"lesson: {text}" for text in result.get("lessons") or [])
    return lines


def render_text(result: dict[str, Any]) -> str:
    label = result.get("symbol") or Path(str(result.get("input", "series"))).stem
    rows = [
        (r["timestamp"], r["close"], r["close_p10"], r["close_p90"])
        for r in result["forecast"]
    ]
    summary = result["summary"]
    lines = [
        f"{label}: {result['model']} forecast, {result['horizon']} x {result['interval']} bars "
        f"(lookback {result['lookback']}, {result['samples']} samples)",
        f"last close {result['last_close']:,.4f} at {result['last_timestamp']}",
        render_table(("timestamp", "close", "p10", "p90"), rows),
        f"at horizon: {summary['close_at_horizon']:,.4f} ({summary['pct_change']:+.2f}%, {summary['direction']}), "
        f"band {summary['band_at_horizon'][0]:,.4f} – {summary['band_at_horizon'][1]:,.4f}",
    ]
    if result.get("chart_path"):
        lines.append(f"chart: {result['chart_path']}")
    lines.extend(_track_record_lines(result))
    lines.extend(f"warning: {w}" for w in result["warnings"])
    lines.extend([result["honesty_check"], result["disclaimer"]])
    return "\n".join(lines)


def render_csv(result: dict[str, Any]) -> str:
    columns = (
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_p10",
        "close_p50",
        "close_p90",
    )
    lines = [",".join(columns)]
    lines.extend(",".join(str(row[c]) for c in columns) for row in result["forecast"])
    return "\n".join(lines)


_RENDERERS = {"table": render_text, "json": dump_json, "csv": render_csv}


def emit(result: dict[str, Any], fmt: str) -> None:
    print(_RENDERERS[fmt](result))
    if fmt == "csv":
        print(DISCLAIMER, file=sys.stderr)


def dry_run_payload(
    meta: dict[str, Any], plan: dict[str, Any], bars: list[Bar]
) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": True,
        **meta,
        "bars": len(bars),
        "first_timestamp": bars[0].ts.isoformat(),
        "last_timestamp": bars[-1].ts.isoformat(),
        "last_close": bars[-1].close,
        "interval": plan["interval"],
        "calendar": plan["calendar"],
        "lookback": plan["lookback"],
        "future_timestamps": [ts.isoformat() for ts in plan["future"]],
        "warnings": plan["warnings"],
        "disclaimer": DISCLAIMER,
    }


def run(args: argparse.Namespace, argv: list[str]) -> int:
    if not args.dry_run:
        code = reexec_in_skill_venv(Path(__file__).resolve(), argv, args.timeout)
        if code is not None:
            return code
    # +1: the still-forming newest eToro candle is dropped after the fetch.
    fetch_count = (args.lookback or min(DEFAULT_LOOKBACK, MAX_CONTEXT[args.model])) + 1
    bars, meta, warnings = load_input(args, fetch_count)
    plan = plan_forecast(bars, args)
    plan["warnings"] = warnings + plan["warnings"]
    if args.dry_run:
        print(dump_json(dry_run_payload(meta, plan, bars)))
        return 0
    state = require_state()
    from _kronos_model import load_predictor, predict_paths, render_chart

    started = time.monotonic()
    predictor = load_predictor(
        state, args.model, device=args.device, threads=args.threads, seed=args.seed
    )
    paths = predict_paths(
        predictor,
        [plan["window"]] * args.samples,
        [plan["future"]] * args.samples,
        args.horizon,
        sample_count=1,
        temperature=args.temperature,
        top_p=args.top_p,
    )
    result = build_result(args, meta, plan, paths, state)
    result["elapsed_s"] = round(time.monotonic() - started, 1)
    if args.plot:
        label = str(meta.get("symbol") or Path(str(meta.get("input", "series"))).stem)
        title = f"{label} — Kronos-{args.model}, next {args.horizon} x {plan['interval']} (not financial advice)"
        result["chart_path"] = str(
            render_chart(bars, result, plot_path(args.plot, label), title)
        )
    if not args.no_journal:
        journal_forecast(
            result,
            label=journal_label(args, meta),
            source="etoro" if args.etoro else "file",
            step_seconds=plan["step_seconds"],
        )
    emit(result, args.format)
    if not args.no_journal:
        from kronos_dashboard import refresh_safely

        refresh_safely()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    return run_cli(lambda: run(args, argv))


if __name__ == "__main__":
    sys.exit(main())
