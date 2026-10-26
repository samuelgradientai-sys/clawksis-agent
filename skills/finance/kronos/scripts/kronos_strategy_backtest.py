#!/usr/bin/env python3
"""Strategy backtest: replay the playbook's buy and sell rules on past bars, under the real limits.

At every decision bar the rules of references/trading-playbook.md § 3–4 run on the bars known
at that moment, and every order goes through the same guards ``etoro_trade.py`` applies:

- Buy when flat, the forecast (ETS by default, Kronos with ``--forecaster kronos``) is up by at
  least half the ATR, the indicator signal is bullish or neutral with RSI ≤ 70, and the lesson
  gate passes (``check_lessons`` over a journal of the simulated forecasts, scored as they
  mature). The size comes from ``kronos_risk.plan_position`` (stop ``--atr-mult`` ATRs below
  the entry, target at ``--rr``:1) capped by the user's trading limits (``DEFAULTS`` when
  config.yaml has none), then ``check_limits`` must accept it. The order fills at the next
  bar's open, and only if ``check_price_levels`` accepts the stop and target at that price.
- Exits: the stop and target execute inside later bars (a gap through one fills at the open; a
  bar touching both counts as the stop); a forecast turning down with bearish indicators, or
  ``--max-hold`` bars without progress, closes at the next open. ``--fee-pct`` is charged on
  both sides.

Reports CAGR, max drawdown, Sharpe, win rate and exposure against buying and holding the same
instrument and, when given, a benchmark (``--benchmark SPY`` from eToro or
``--benchmark-input FILE``). ``--report`` writes a quantstats HTML tear sheet when quantstats is
installed in the skill venv; the metrics themselves are pure Python. The summary is appended to
``$CLAWK_HOME/kronos/strategy.jsonl`` for the dashboard (skip with ``--no-record``). It reads
prices only; it never places an order. What it cannot replay: the weekly backtest verdict the
real buys also need (this is itself a backtest) and intrabar order of stop vs target.

Usage:
  kronos_strategy_backtest.py --etoro AAPL [--interval OneDay] [--benchmark SPY] [--report auto]
  kronos_strategy_backtest.py --input aapl.csv --symbol AAPL [--forecaster kronos] [--json]
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
import tempfile
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_baselines import ets_forecasts
from _kronos_common import (
    DISCLAIMER,
    MAX_CONTEXT,
    UTC,
    Bar,
    SkillError,
    append_jsonl,
    describe_step,
    dump_json,
    future_timestamps,
    infer_step,
    iso_z,
    kronos_home,
    load_bars,
    load_state,
    reexec_in_skill_venv,
    render_table,
    require_state,
    run_cli,
)
from _kronos_config import RISK_PCT, config_path, goals, load_config, risk_profile
from _kronos_journal import evaluate, strategy_path, symbol_key
from _kronos_metrics import summarize
from etoro_trade import (
    DEFAULTS,
    LessonRefused,
    ProtectionRefused,
    TradingConfig,
    TradingRefused,
    check_lessons,
    check_limits,
    check_price_levels,
    load_trading_config,
    usage_today,
)
from kronos_forecast import _bounded, add_data_args, add_model_args, journal_label
from kronos_indicators import analyze
from kronos_risk import plan_position

FORECASTERS = ("ets", "kronos")
INDICATOR_WINDOW = 300  # bars fed to the indicators at each decision (SMA200 needs 200)
MIN_HISTORY = 64
NOTE = (
    "A replay of past prices under today's rules and limits, not a promise: fills are "
    "assumed at the next open and at the stop or target, and the weekly backtest verdict real "
    "buys also need is not simulated. Not financial advice."
)


# ── Arguments ──


def _percent(value: str) -> float:
    number = float(value)
    if not 0 <= number < 10:
        raise argparse.ArgumentTypeError("must be between 0 and 10 (percent)")
    return number


def _positive(value: str) -> float:
    number = float(value)
    if not number > 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay the Kronos playbook on past bars under the trading limits."
    )
    add_data_args(parser)
    parser.add_argument(
        "--count", type=_bounded(MIN_HISTORY, 1000), default=1000, help="eToro bars"
    )
    parser.add_argument("--symbol", metavar="LABEL", help="name in reports")
    parser.add_argument("--forecaster", choices=FORECASTERS, default="ets")
    parser.add_argument("--horizon", type=_bounded(1, 60), default=5)
    parser.add_argument(
        "--stride", type=_bounded(1, 100), default=1, help="bars between decisions"
    )
    parser.add_argument("--account-size", type=_positive, default=10_000.0)
    parser.add_argument("--risk-pct", type=_positive, help="default: goals.risk")
    parser.add_argument("--atr-mult", type=_positive, default=2.0)
    parser.add_argument("--rr", type=_positive, default=2.0)
    parser.add_argument("--max-hold", type=_bounded(1, 1000), default=20)
    parser.add_argument("--fee-pct", type=_percent, default=0.1, help="per side")
    bench = parser.add_mutually_exclusive_group()
    bench.add_argument(
        "--benchmark", metavar="SYMBOL", help="eToro benchmark, e.g. SPY"
    )
    bench.add_argument("--benchmark-input", type=Path, metavar="FILE")
    parser.add_argument(
        "--report",
        metavar="PATH|auto",
        help="quantstats HTML tear sheet (if installed)",
    )
    parser.add_argument("--no-record", action="store_true")
    add_model_args(parser, samples=1, lookback=256)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--json",
        dest="format",
        action="store_const",
        const="json",
        help="--format json",
    )
    return parser


# ── Inputs ──


def load_strategy_bars(
    args: argparse.Namespace,
) -> tuple[list[Bar], dict[str, Any], list[str]]:
    if args.input:
        bars, warnings = load_bars(args.input)
        return (
            bars,
            {"source": "file", "input": str(Path(args.input).resolve())},
            warnings,
        )
    from etoro_data import fetch_bars

    return fetch_bars(args.etoro, args.interval, args.count)


def load_benchmark(args: argparse.Namespace) -> tuple[list[Bar], str] | None:
    if args.benchmark_input:
        bars, _warnings = load_bars(args.benchmark_input)
        return bars, Path(args.benchmark_input).stem.upper()
    if args.benchmark:
        from etoro_data import fetch_bars

        bars, meta, _warnings = fetch_bars(args.benchmark, args.interval, args.count)
        return bars, str(meta.get("symbol") or args.benchmark).upper()
    return None


def trading_limits() -> tuple[TradingConfig, str, list[str]]:
    """The user's limits (the simulation ignores the on/off switch); DEFAULTS without them."""
    try:
        config = load_trading_config()
    except TradingRefused as exc:
        return (
            DEFAULTS,
            "defaults",
            [f"trading settings unreadable ({exc}); used defaults"],
        )
    return config, "config.yaml" if config_path().exists() else "defaults", []


def default_risk_pct() -> float:
    try:
        return RISK_PCT[risk_profile(goals(load_config()))]
    except SkillError:
        return RISK_PCT["low"]


# ── Forecasts at the decision bars ──


def decision_points(n_bars: int, start: int, stride: int) -> list[int]:
    """Bars at whose close a decision is taken; each needs a next bar to fill at."""
    return list(range(start, n_bars - 1, stride))


def _kronos_closes(
    bars: list[Bar], points: list[int], lookback: int, args: argparse.Namespace
) -> dict[int, float]:
    from _kronos_model import load_predictor, predict_paths

    state = require_state()
    windows = [bars[i - lookback + 1 : i + 1] for i in points]
    futures = [future_timestamps([b.ts for b in w], args.horizon)[0] for w in windows]
    predictor = load_predictor(
        state, args.model, device=args.device, threads=args.threads, seed=args.seed
    )
    paths = predict_paths(
        predictor,
        windows,
        futures,
        args.horizon,
        sample_count=args.samples,
        temperature=args.temperature,
        top_p=args.top_p,
    )
    return {i: path[-1]["close"] for i, path in zip(points, paths)}


def forecast_closes(
    bars: list[Bar], points: list[int], lookback: int, args: argparse.Namespace
) -> tuple[dict[int, float], str]:
    """Predicted close at the horizon for every decision bar, and the forecaster's name."""
    if args.forecaster == "kronos":
        return _kronos_closes(bars, points, lookback, args), f"Kronos-{args.model}"
    windows = [[b.close for b in bars[i - lookback + 1 : i + 1]] for i in points]
    closes, engine = ets_forecasts(windows, args.horizon)
    return {i: c[-1] for i, c in zip(points, closes)}, engine


# ── Simulation ──


@dataclass
class Position:
    entry_index: int
    entry_price: float
    units: float
    amount: float
    stop: float
    target: float


@dataclass
class Rules:
    account_size: float
    risk_pct: float
    atr_mult: float
    rr: float
    max_hold: int
    fee: float
    horizon: int


@dataclass
class Sim:
    bars: list[Bar]
    forecasts: dict[int, float]
    rules: Rules
    config: TradingConfig
    journal: Path
    label: str
    interval: str
    cash: float
    position: Position | None = None
    pending_buy: dict[str, Any] | None = None
    pending_exit: str | None = None
    ledger: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    refusals: Counter = field(default_factory=Counter)
    signals: int = 0  # decisions where the buy rules said yes, before the guards
    due: dict[int, list[dict[str, Any]]] = field(default_factory=dict)


def _utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC)


def _close_position(sim: Sim, index: int, price: float, reason: str) -> None:
    pos = sim.position
    assert pos is not None
    proceeds = pos.units * price * (1 - sim.rules.fee)
    sim.cash += proceeds
    sim.trades.append(
        {
            "entry": iso_z(sim.bars[pos.entry_index].ts),
            "exit": iso_z(sim.bars[index].ts),
            "entry_price": round(pos.entry_price, 6),
            "exit_price": round(price, 6),
            "amount": pos.amount,
            "pnl": round(proceeds - pos.amount, 2),
            "return_pct": round((proceeds / pos.amount - 1) * 100, 2),
            "bars_held": index - pos.entry_index,
            "reason": reason,
        }
    )
    sim.position, sim.pending_exit = None, None


def _protective_exit(pos: Position, bar: Bar) -> tuple[float, str] | None:
    """The stop or target hit inside *bar* (gaps fill at the open; both touched: the stop)."""
    if bar.open <= pos.stop:
        return bar.open, "stop"
    if bar.open >= pos.target:
        return bar.open, "target"
    if bar.low <= pos.stop:
        return pos.stop, "stop"
    if bar.high >= pos.target:
        return pos.target, "target"
    return None


def _fill_buy(sim: Sim, index: int) -> None:
    """Open the pending buy at this bar's open, if the stop and target still bracket it."""
    order, sim.pending_buy = sim.pending_buy, None
    assert order is not None
    price = sim.bars[index].open
    try:
        check_price_levels(order["stop"], order["target"], price)
    except ProtectionRefused:
        sim.refusals["stop"] += 1
        return
    amount = order["amount"]
    sim.cash -= amount
    units = amount * (1 - sim.rules.fee) / price
    sim.position = Position(index, price, units, amount, order["stop"], order["target"])
    sim.ledger.append(
        {
            "id": str(uuid.uuid4()),
            "ts": _utc(sim.bars[index].ts).isoformat(),
            "action": "open",
            "account": sim.config.account,
            "amount": amount,
            "status": "filled",
        }
    )


def _settle_bar(sim: Sim, index: int) -> None:
    """Everything that happens during bar *index* before its close."""
    bar = sim.bars[index]
    if sim.position and sim.pending_exit:
        _close_position(sim, index, bar.open, sim.pending_exit)
    if sim.pending_buy:
        _fill_buy(sim, index)
    if sim.position:
        hit = _protective_exit(sim.position, bar)
        if hit:
            _close_position(sim, index, *hit)


def _journal_forecast(sim: Sim, index: int, predicted: float) -> None:
    """Record the simulated forecast; it is scored once its horizon bar has closed."""
    bar = sim.bars[index]
    change = (predicted - bar.close) / bar.close * 100.0
    record = {
        "id": f"sim-{index}",
        "symbol": sim.label,
        "interval": sim.interval,
        "horizon": sim.rules.horizon,
        "last_timestamp": bar.ts.isoformat(),
        "last_close": bar.close,
        "predicted_close": predicted,
        "direction": "up" if change > 0.1 else "down" if change < -0.1 else "flat",
        "band": [],
    }
    append_jsonl(sim.journal, record)
    sim.due.setdefault(index + sim.rules.horizon, []).append(record)


def _score_matured(sim: Sim, index: int) -> None:
    for record in sim.due.pop(index, []):
        start = index - sim.rules.horizon
        outcome = evaluate(
            record, sim.bars[start : index + 1], _utc(sim.bars[index].ts)
        )
        if outcome is not None:
            append_jsonl(sim.journal, {"id": record["id"], "outcome": outcome})


def _limits(sim: Sim, now: datetime) -> dict[str, Any]:
    count, spent = usage_today(sim.ledger, sim.config.account, now)
    return {
        "max_order_usd": sim.config.max_order_usd,
        "usd_left_today": max(sim.config.max_daily_usd - spent, 0.0),
        "buys_left_today": max(sim.config.max_orders_per_day - count, 0),
    }


def _wants_to_buy(signal: dict[str, Any], change_pct: float) -> bool:
    values = signal["indicators"]
    atr_pct, rsi = values.get("atr_pct"), values.get("rsi14")
    if atr_pct is None or not (values.get("atr14") or 0) > 0:
        return False
    if signal["signal"] == "bearish" or (rsi is not None and rsi > 70):
        return False
    return change_pct >= 0.5 * atr_pct and change_pct > 0


def _try_buy(sim: Sim, index: int, signal: dict[str, Any]) -> None:
    """Size the buy and run it through the real guards; it fills at the next open."""
    bar, rules = sim.bars[index], sim.rules
    fill_time = _utc(sim.bars[index + 1].ts)
    stop = bar.close - rules.atr_mult * signal["indicators"]["atr14"]
    if stop <= 0:
        sim.refusals["stop"] += 1
        return
    plan = plan_position(
        account_size=sim.cash,
        risk_pct=rules.risk_pct,
        entry=bar.close,
        stop=stop,
        rr=rules.rr,
        limits=_limits(sim, fill_time),
    )
    try:
        check_limits(sim.config, plan["suggested_amount_usd"], sim.ledger, fill_time)
        check_lessons(sim.label, sim.journal, user_requested=False)
    except LessonRefused:
        sim.refusals["lesson"] += 1
        return
    except TradingRefused:
        sim.refusals["limit"] += 1
        return
    sim.pending_buy = {
        "amount": plan["suggested_amount_usd"],
        "stop": plan["stop_loss"],
        "target": plan["take_profit"],
    }


def _decide(sim: Sim, index: int) -> None:
    """The playbook's decision at the close of bar *index*."""
    predicted = sim.forecasts.get(index)
    if predicted is None:
        return
    _journal_forecast(sim, index, predicted)
    bar = sim.bars[index]
    change_pct = (predicted - bar.close) / bar.close * 100.0
    signal = analyze(sim.bars[max(0, index - INDICATOR_WINDOW + 1) : index + 1])
    pos = sim.position
    if pos is None:
        if _wants_to_buy(signal, change_pct):
            sim.signals += 1
            _try_buy(sim, index, signal)
        return
    if change_pct < 0 and signal["signal"] == "bearish":
        sim.pending_exit = "thesis"
    elif index - pos.entry_index >= sim.rules.max_hold and bar.close <= pos.entry_price:
        sim.pending_exit = "time"


def simulate(sim: Sim, start: int) -> list[float]:
    """Run bar by bar from *start*; returns the equity at every close from *start* on."""
    equity = []
    for index in range(start, len(sim.bars)):
        if index > start:
            _settle_bar(sim, index)
        _score_matured(sim, index)
        if index < len(sim.bars) - 1:
            _decide(sim, index)
        held = sim.position.units * sim.bars[index].close if sim.position else 0.0
        equity.append(sim.cash + held)
    if sim.position:
        _close_position(sim, len(sim.bars) - 1, sim.bars[-1].close, "end")
    return equity


# ── Results ──


def trade_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    wins = [t for t in trades if t["pnl"] > 0]
    return {
        "trades": len(trades),
        "win_rate_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "avg_trade_pct": round(sum(t["return_pct"] for t in trades) / len(trades), 2)
        if trades
        else None,
        "exits": dict(Counter(t["reason"] for t in trades)),
    }


def busiest_day(ledger: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The UTC day with the most money opened: evidence the daily caps held."""
    days: dict[str, list[float]] = {}
    for entry in ledger:
        days.setdefault(str(entry["ts"])[:10], []).append(float(entry["amount"]))
    if not days:
        return None
    day, amounts = max(days.items(), key=lambda kv: (sum(kv[1]), len(kv[1])))
    return {"date": day, "buys": len(amounts), "usd": round(sum(amounts), 2)}


def benchmark_curve(
    bench: list[Bar], stamps: list[datetime], account: float
) -> list[float] | None:
    """Buy and hold of *bench* over the same days (last close on or before each day)."""
    closes, pointer, curve = sorted((b.ts.date(), b.close) for b in bench), 0, []
    last = None
    for stamp in stamps:
        while pointer < len(closes) and closes[pointer][0] <= stamp.date():
            last = closes[pointer][1]
            pointer += 1
        if last is None:
            return None
        curve.append(last)
    return [account * c / curve[0] for c in curve]


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "series"


def write_tear_sheet(
    path: Path,
    stamps: list[datetime],
    equity: list[float],
    benchmark: list[float],
    title: str,
    per_year: float,
) -> Path:
    """quantstats HTML tear sheet (raises ImportError when quantstats is not installed)."""
    import matplotlib

    matplotlib.use("Agg")
    import pandas as pd
    import quantstats as qs

    index = pd.DatetimeIndex(stamps)
    returns = pd.Series(equity, index=index).pct_change().fillna(0.0)
    bench = pd.Series(benchmark, index=index).pct_change().fillna(0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.redirect_stdout(
        sys.stderr
    ):  # quantstats prints; stdout may be JSON
        qs.reports.html(
            returns,
            benchmark=bench,
            output=str(path),
            title=title,
            periods_per_year=max(round(per_year), 1),
        )
    return path


def report_path(value: str, label: str) -> Path:
    if value != "auto":
        return Path(value).expanduser().resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return kronos_home() / "reports" / f"{_slug(label)}-strategy-{stamp}.html"


# ── CLI ──


def _plan(args: argparse.Namespace, bars: list[Bar]) -> tuple[int, int]:
    lookback = min(args.lookback, MAX_CONTEXT[args.model])
    start = max(lookback, MIN_HISTORY) - 1
    if len(bars) - start < 2 * args.horizon + 2:
        raise SkillError(
            f"{len(bars)} bars leave too little after the {start + 1}-bar warm-up.",
            hint="Fetch more bars (--count) or lower --lookback.",
        )
    return lookback, start


def _maybe_reexec(args: argparse.Namespace, argv: list[str]) -> int | None:
    """Run inside the skill venv when it exists (statsforecast, quantstats, Kronos live there);
    the ETS forecaster also runs without it, on the built-in Holt fit."""
    if args.dry_run:
        return None
    state = load_state()
    if args.forecaster == "kronos" or (state and state.get("venv_python")):
        return reexec_in_skill_venv(Path(__file__).resolve(), argv, args.timeout)
    return None


def _comparisons(
    args: argparse.Namespace, stamps: list[datetime], bars: list[Bar], start: int
) -> tuple[dict[str, Any], dict[str, Any] | None, list[float], list[str]]:
    account = args.account_size
    hold = [account * b.close / bars[start].close for b in bars[start:]]
    warnings: list[str] = []
    bench_result, bench_curve = None, hold
    loaded = load_benchmark(args)
    if loaded:
        bench_bars, name = loaded
        curve = benchmark_curve(bench_bars, stamps, account)
        if curve is None:
            warnings.append(
                f"the benchmark {name} starts after the test period; skipped"
            )
        else:
            bench_result, bench_curve = (
                {"symbol": name, **summarize(stamps, curve)},
                curve,
            )
    return summarize(stamps, hold), bench_result, bench_curve, warnings


def run(args: argparse.Namespace) -> dict[str, Any]:
    bars, meta, warnings = load_strategy_bars(args)
    lookback, start = _plan(args, bars)
    points = decision_points(len(bars), start, args.stride)
    label = journal_label(args, meta)
    interval = describe_step(infer_step([b.ts for b in bars]))
    config, limits_source, notes = trading_limits()
    warnings += notes
    base = {
        "ok": True,
        "symbol": label,
        "interval": interval,
        "bars": len(bars),
        "decisions": len(points),
        "period": [iso_z(bars[start].ts), iso_z(bars[-1].ts)],
    }
    if args.dry_run:
        return {**base, "dry_run": True, "warnings": warnings}
    started = time.monotonic()
    forecasts, engine = forecast_closes(bars, points, lookback, args)
    rules = Rules(
        account_size=args.account_size,
        risk_pct=args.risk_pct or default_risk_pct(),
        atr_mult=args.atr_mult,
        rr=args.rr,
        max_hold=args.max_hold,
        fee=args.fee_pct / 100.0,
        horizon=args.horizon,
    )
    with tempfile.TemporaryDirectory(prefix="kronos-strategy-") as scratch:
        sim = Sim(
            bars=bars,
            forecasts=forecasts,
            rules=rules,
            config=config,
            journal=Path(scratch) / "forecasts.jsonl",
            label=label,
            interval=interval,
            cash=args.account_size,
        )
        equity = simulate(sim, start)
    stamps = [b.ts for b in bars[start:]]
    hold, bench, bench_curve, more = _comparisons(args, stamps, bars, start)
    warnings += more
    strategy = summarize(stamps, equity)
    exposure = sum(t["bars_held"] for t in sim.trades) / max(len(stamps) - 1, 1)
    result = {
        **base,
        "forecaster": engine,
        "method": args.forecaster,
        "horizon": args.horizon,
        "lookback": lookback,
        "stride": args.stride,
        "rules": {
            "risk_pct": rules.risk_pct,
            "atr_mult": rules.atr_mult,
            "reward_risk": rules.rr,
            "max_hold_bars": rules.max_hold,
            "fee_pct_per_side": args.fee_pct,
            "min_forecast_move": "half the ATR",
        },
        "limits": {
            "source": limits_source,
            "account": config.account,
            "max_order_usd": config.max_order_usd,
            "max_daily_usd": config.max_daily_usd,
            "max_orders_per_day": config.max_orders_per_day,
        },
        "strategy": {
            **strategy,
            **trade_stats(sim.trades),
            "exposure_pct": round(exposure * 100, 1),
            "final_equity": round(equity[-1], 2),
        },
        "buy_and_hold": hold,
        "benchmark": bench,
        "buy_signals": sim.signals,
        "refusals": dict(sim.refusals),
        "busiest_day": busiest_day(sim.ledger),
        "recent_trades": sim.trades[-10:],
        "warnings": warnings,
        "elapsed_s": round(time.monotonic() - started, 1),
        "note": NOTE,
        "disclaimer": DISCLAIMER,
    }
    if args.report:
        _attach_report(result, args, stamps, equity, bench_curve)
    return result


def _attach_report(
    result: dict[str, Any],
    args: argparse.Namespace,
    stamps: list[datetime],
    equity: list[float],
    benchmark: list[float],
) -> None:
    title = f"{result['symbol']} — Kronos playbook replay ({result['forecaster']})"
    try:
        path = write_tear_sheet(
            report_path(args.report, result["symbol"]),
            stamps,
            equity,
            benchmark,
            title,
            result["strategy"]["bars_per_year"],
        )
    except ImportError:
        result["warnings"].append(
            "quantstats is not installed in the Kronos venv: no HTML tear sheet "
            "(kronos_setup.py adds it); the metrics above are complete"
        )
        return
    result["report_path"] = str(path)


def record_summary(result: dict[str, Any], kronos_dir: Path | None = None) -> None:
    strategy, hold = result["strategy"], result["buy_and_hold"]
    row = {
        "id": str(uuid.uuid4()),
        "made_at": iso_z(datetime.now(UTC)),
        "symbol": symbol_key(result["symbol"]),
        "interval": result["interval"],
        "forecaster": result["forecaster"],
        "method": result["method"],
        "period": result["period"],
        "trades": strategy["trades"],
        "win_rate_pct": strategy["win_rate_pct"],
        "cagr_pct": strategy["cagr_pct"],
        "max_drawdown_pct": strategy["max_drawdown_pct"],
        "sharpe": strategy["sharpe"],
        "exposure_pct": strategy["exposure_pct"],
        "hold_cagr_pct": hold["cagr_pct"],
        "hold_max_drawdown_pct": hold["max_drawdown_pct"],
        "benchmark": result["benchmark"],
        "report_path": result.get("report_path"),
    }
    try:
        append_jsonl(strategy_path(kronos_dir), row)
    except OSError as exc:
        result["warnings"].append(f"summary not recorded: {exc}")


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def render_text(result: dict[str, Any]) -> str:
    s, h, b = result["strategy"], result["buy_and_hold"], result["benchmark"]
    rows = [
        ("playbook", _pct(s["cagr_pct"]), _pct(s["max_drawdown_pct"]), s["sharpe"]),
        ("buy & hold", _pct(h["cagr_pct"]), _pct(h["max_drawdown_pct"]), h["sharpe"]),
    ]
    if b:
        rows.append(
            (
                f"{b['symbol']} hold",
                _pct(b["cagr_pct"]),
                _pct(b["max_drawdown_pct"]),
                b["sharpe"],
            )
        )
    limits, busiest = result["limits"], result["busiest_day"]
    lines = [
        f"{result['symbol']}: playbook replay on {result['bars']} x {result['interval']} bars "
        f"({result['period'][0]} → {result['period'][1]}), forecaster {result['forecaster']}",
        render_table(("strategy", "CAGR", "max drawdown", "Sharpe"), rows),
        f"trades {s['trades']}, win rate "
        + ("n/a" if s["win_rate_pct"] is None else f"{s['win_rate_pct']}%")
        + f", avg trade {_pct(s['avg_trade_pct'])}, exposure {s['exposure_pct']}%, exits "
        f"{s['exits'] or 'none'}; buy signals {result['buy_signals']}",
        f"limits ({limits['source']}): {limits['max_order_usd']:g} USD/order, "
        f"{limits['max_daily_usd']:g} USD and {limits['max_orders_per_day']} buys per day; "
        f"refused {result['refusals'] or 'none'}"
        + (
            f"; busiest day {busiest['date']}: {busiest['usd']:g} USD"
            if busiest
            else ""
        ),
    ]
    if result.get("report_path"):
        lines.append(f"tear sheet: {result['report_path']}")
    lines += [f"warning: {w}" for w in result["warnings"]]
    lines += [result["note"], result["disclaimer"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    def _go() -> int:
        code = _maybe_reexec(args, argv)
        if code is not None:
            return code
        result = run(args)
        if not result.get("dry_run") and not args.no_record:
            record_summary(result)
        if args.format == "json" or result.get("dry_run"):
            print(dump_json(result))
        else:
            print(render_text(result))
        if not result.get("dry_run") and not args.no_record:
            from kronos_dashboard import refresh_safely

            refresh_safely()
        return 0

    return run_cli(_go)


if __name__ == "__main__":
    sys.exit(main())
