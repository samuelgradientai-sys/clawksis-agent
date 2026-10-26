#!/usr/bin/env python3
"""Honesty check: walk-forward Kronos vs two baselines, "repeat the last close" and ETS.

For each origin in the instrument's recent history, Kronos sees only the bars up to that origin
and forecasts the next --horizon closes. The naive baseline repeats the origin's close; the
classical baseline is an exponential-smoothing forecast fitted on the same window
(statsforecast AutoETS when installed, else a built-in Holt fit; see _kronos_baselines.py).
Reports MAE/MAPE (all steps), direction hit-rate at the horizon, the "always up" base rate, MAE
skill vs each baseline, and a plain-language verdict the agent relays before presenting any
Kronos forecast as useful. ``adds_value`` needs a 2%+ lower MAE than BOTH baselines.

Every finished run is appended to ``$CLAWK_HOME/kronos/backtests.jsonl`` (skip with
--no-record): ``etoro_trade.py buy`` refuses automatic buys of a symbol unless its backtests of
the last 7 days say ``adds_value``. Origins are batched into a few predict_batch calls.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_baselines import ENGINE_BUILTIN, ets_forecasts
from _kronos_common import (
    DISCLAIMER,
    MAX_CONTEXT,
    UTC,
    Bar,
    SkillError,
    describe_step,
    dump_json,
    infer_step,
    reexec_in_skill_venv,
    render_table,
    require_state,
    run_cli,
    score_origins,
    verdict,
    verdict_detail,
)
from _kronos_journal import append_locked, backtest_record, backtests_path
from kronos_forecast import (
    _bounded,
    add_data_args,
    add_model_args,
    journal_label,
    load_input,
)

MIN_ORIGINS = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Walk-forward Kronos vs naive last-close backtest."
    )
    add_data_args(parser)
    parser.add_argument(
        "--origins",
        type=_bounded(MIN_ORIGINS, 200),
        default=20,
        help="forecast origins to test",
    )
    parser.add_argument(
        "--horizon",
        type=_bounded(1, 60),
        default=5,
        help="bars ahead scored at each origin",
    )
    parser.add_argument(
        "--stride",
        type=_bounded(1, 500),
        default=None,
        help="bars between origins (default: horizon)",
    )
    add_model_args(parser, samples=4, lookback=256)
    parser.add_argument(
        "--symbol",
        metavar="LABEL",
        help="symbol the verdict is recorded under (default: the eToro symbol or the file "
        "name); must match the symbol etoro_trade.py buys",
    )
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="do not record the verdict (it then cannot unlock automatic buys)",
    )
    parser.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def plan_origins(
    n_bars: int, lookback: int, horizon: int, origins: int, stride: int
) -> list[int]:
    """Indices of the last observed bar per origin, ascending; each has a full future."""
    last = n_bars - 1 - horizon
    picks = [last - i * stride for i in range(origins)]
    feasible = sorted(i for i in picks if i >= lookback - 1)
    if len(feasible) < MIN_ORIGINS:
        raise SkillError(
            f"History too short: {n_bars} bars allow {len(feasible)} origin(s) with lookback "
            f"{lookback}, horizon {horizon}, stride {stride} (need {MIN_ORIGINS}).",
            hint="Lower --lookback/--stride/--origins or fetch more bars.",
        )
    return feasible


def origin_windows(
    bars: list[Bar], indices: list[int], lookback: int, horizon: int
) -> list[dict[str, Any]]:
    return [
        {
            "window": bars[i - lookback + 1 : i + 1],
            "future_ts": [b.ts for b in bars[i + 1 : i + 1 + horizon]],
            "actual": [b.close for b in bars[i + 1 : i + 1 + horizon]],
            "last_close": bars[i].close,
            "origin_ts": bars[i].ts.isoformat(),
        }
        for i in indices
    ]


def render_text(result: dict[str, Any]) -> str:
    metrics = result["metrics"]
    k, n, e = metrics["kronos"], metrics["naive_last_close"], metrics.get("ets") or {}
    rows = [
        ("Kronos", k["mae"], k["mape_pct"], k["direction_hit_rate"]),
        ("repeat last close", n["mae"], n["mape_pct"], None),
        ("ETS", e.get("mae"), e.get("mape_pct"), e.get("direction_hit_rate")),
        ("always up (base rate)", None, None, metrics["always_up_hit_rate"]),
    ]
    ets_skill = metrics.get("mae_skill_vs_ets")
    ets_text = f"{ets_skill:+.1%}" if ets_skill is not None else "n/a"
    label = result.get("symbol") or Path(str(result.get("input", "series"))).stem
    return "\n".join(
        [
            f"{label}: {result['origins']} origins, horizon {result['horizon']}, lookback "
            f"{result['lookback']}, {result['model']} ({result['first_origin']} → {result['last_origin']})",
            render_table(("forecaster", "MAE", "MAPE_%", "direction_hit"), rows),
            f"MAE skill vs naive: {metrics['mae_skill_vs_naive']:+.1%}; vs ETS: {ets_text} "
            f"({result['ets_engine']})",
            f"verdict: {result['verdict']} — {result['verdict_text']}",
            *(f"warning: {w}" for w in result["warnings"]),
            result["disclaimer"],
        ]
    )


def record_verdict(
    result: dict[str, Any],
    args: argparse.Namespace,
    meta: dict[str, Any],
    *,
    kronos_dir: Path | None = None,
    now: datetime | None = None,
) -> None:
    """Append the verdict to the backtest log; a write failure only adds a warning."""
    label = journal_label(args, meta)
    row = backtest_record(result, label=label, now=now or datetime.now(UTC))
    try:
        append_locked(backtests_path(kronos_dir), [row])
    except (OSError, SkillError) as exc:
        result["warnings"].append(f"verdict not recorded: {exc}")
        return
    result["recorded_as"] = label


def run(args: argparse.Namespace, argv: list[str]) -> int:
    if not args.dry_run:
        code = reexec_in_skill_venv(Path(__file__).resolve(), argv, args.timeout)
        if code is not None:
            return code
    stride = args.stride or args.horizon
    lookback = min(args.lookback, MAX_CONTEXT[args.model])
    needed = lookback + (args.origins - 1) * stride + args.horizon + 1
    bars, meta, warnings = load_input(args, min(needed, 1000))
    interval = describe_step(infer_step([b.ts for b in bars]))
    indices = plan_origins(len(bars), lookback, args.horizon, args.origins, stride)
    if len(indices) < args.origins:
        warnings.append(
            f"only {len(indices)} of {args.origins} origins fit the available history"
        )
    windows = origin_windows(bars, indices, lookback, args.horizon)
    base = {
        "ok": True,
        **meta,
        "interval": interval,
        "origins": len(windows),
        "horizon": args.horizon,
        "lookback": lookback,
    }
    base.update(
        {
            "first_origin": windows[0]["origin_ts"],
            "last_origin": windows[-1]["origin_ts"],
        }
    )
    if args.dry_run:
        print(
            dump_json({**base, "dry_run": True, "stride": stride, "warnings": warnings})
        )
        return 0
    state = require_state()
    from _kronos_model import load_predictor, predict_paths

    started = time.monotonic()
    ets, ets_engine = ets_forecasts(
        [[b.close for b in w["window"]] for w in windows], args.horizon
    )
    if ets_engine == ENGINE_BUILTIN:
        warnings.append(
            "statsforecast is not installed in the Kronos venv; the ETS baseline used the "
            "built-in Holt fit (kronos_setup.py adds statsforecast)"
        )
    predictor = load_predictor(
        state, args.model, device=args.device, threads=args.threads, seed=args.seed
    )
    paths = predict_paths(
        predictor,
        [w["window"] for w in windows],
        [w["future_ts"] for w in windows],
        args.horizon,
        sample_count=args.samples,  # mean of K samples per origin, like a forecast's mean path
        temperature=args.temperature,
        top_p=args.top_p,
    )
    scored = [
        {
            "last_close": w["last_close"],
            "actual": w["actual"],
            "kronos": [row["close"] for row in path],
            "ets": baseline,
        }
        for w, path, baseline in zip(windows, paths, ets)
    ]
    metrics = score_origins(scored)
    code, text = verdict(metrics)
    result = {
        **base,
        "model": f"Kronos-{args.model}",
        "samples": args.samples,
        "stride": stride,
        "metrics": metrics,
        "ets_engine": ets_engine,
        "verdict": code,
        "verdict_detail": verdict_detail(metrics),
        "verdict_text": text,
        "warnings": warnings,
        "elapsed_s": round(time.monotonic() - started, 1),
        "disclaimer": DISCLAIMER,
    }
    if not args.no_record:
        record_verdict(result, args, meta)
    print(render_text(result) if args.format == "table" else dump_json(result))
    if not args.no_record:
        from kronos_dashboard import refresh_safely

        refresh_safely()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    return run_cli(lambda: run(args, argv))


if __name__ == "__main__":
    sys.exit(main())
