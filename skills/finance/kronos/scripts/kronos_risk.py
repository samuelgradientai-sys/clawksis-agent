#!/usr/bin/env python3
"""Position sizing for a long trade: how much to buy, where the stop and the target go.

risk USD   = account size x risk %          (risk % from --risk-pct, else the user's goals.risk:
                                             low 0.5%, medium 1%, high 2%)
stop       = entry x (1 - stop_pct / 100) when the bucket's stop_pct is above 0, else
             entry - ATR multiple x ATR14   (or --stop PRICE)
target     = entry + reward:risk x (entry - stop)
amount USD = risk USD / (entry - stop) x entry, then capped by the account size, the per-order
             limit, what is left of today's limits in config.yaml, and 0 when the bucket
             already holds its maximum of open positions.

It only reads the limits and the trade ledger; it never changes them and places no order.
The limits are the bucket's (``--asset``; auto: a symbol on the meme list is a meme coin, eToro
instrument type 10, Saturday bars or a symbol on ``kronos.crypto.watchlist`` mean crypto, else
stock): ``trading.*`` for stocks, ``crypto.*`` for crypto, and for a meme coin the tighter of
the meme and crypto caps, with the meme coins' own stop_pct and max_positions. ``buy_args`` is
ready for ``etoro_trade.py buy``: the stop
and target travel with the order (``--stop``/``--target``) and eToro executes them, and an
automatic buy without a stop is refused.

Usage:
  kronos_risk.py --account-size 10000 --etoro AAPL [--interval OneDay] [--risk-pct 1]
  kronos_risk.py --account-size 10000 --entry 187.2 --stop 180 [--rr 2] [--format json]
  kronos_risk.py --account-size 10000 --etoro DOGE --interval OneHour [--asset meme]
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import UTC, SkillError, dump_json, load_bars, run_cli
from _kronos_config import RISK_PCT, goals, load_config, risk_profile
from _kronos_crypto import (
    BUCKETS,
    CRYPTO,
    MEME,
    STOCK,
    hint_bucket,
    is_crypto_instrument,
)
from _kronos_positions import bucket_rules, fixed_stop, positions_usage, widest_stop
from etoro_trade import (
    cap_usage,
    caps_for,
    load_crypto_config,
    load_trading_config,
    read_ledger,
)
from kronos_indicators import atr

NOTE = (
    "Sizing caps the loss if the stop is hit; it does not make the trade a good idea. "
    "Not financial advice."
)


@dataclass
class RiskDeps:
    config_path: Path | None = None
    ledger: Path | None = None
    now: Callable[[], datetime] = lambda: datetime.now(UTC)


def _positive(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Position size, stop and target for a long trade."
    )
    parser.add_argument(
        "--account-size", type=_positive, required=True, help="account value in USD"
    )
    parser.add_argument(
        "--risk-pct", type=_positive, help="max loss per trade, %% of the account"
    )
    parser.add_argument(
        "--entry", type=_positive, help="entry price (default: last close)"
    )
    parser.add_argument(
        "--stop",
        type=_positive,
        help="stop price (default: the bucket's stop_pct, else ATR based)",
    )
    parser.add_argument(
        "--atr-mult",
        type=_positive,
        default=2.0,
        help="stop distance in ATRs when the bucket's stop_pct is 0",
    )
    parser.add_argument(
        "--rr", type=_positive, default=2.0, help="reward:risk for the target"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--input", type=Path, help="CSV/JSON bars for the ATR and last close"
    )
    source.add_argument("--etoro", metavar="SYMBOL", help="eToro candles (read-only)")
    parser.add_argument("--interval", default="OneDay", help="eToro interval")
    parser.add_argument(
        "--asset",
        choices=("auto", *BUCKETS),
        default="auto",
        help="whose limits cap the amount: stock (trading.*), crypto (crypto.*) or meme "
        "(meme and crypto caps); auto decides from the symbol and eToro",
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


def _market(
    args: argparse.Namespace,
) -> tuple[float | None, float | None, str | None, bool]:
    """(last close, ATR14, symbol, eToro says crypto) from the bars, when bars were given."""
    if args.input:
        bars, _warnings = load_bars(args.input)
        return bars[-1].close, atr(bars)[-1], None, False
    if not args.etoro:
        return None, None, None, False
    from etoro_data import fetch_bars

    bars, meta, _warnings = fetch_bars(args.etoro, args.interval, 120)
    crypto = is_crypto_instrument(
        {"instrumentTypeID": meta.get("instrument_type_id")},
        any(bar.ts.weekday() == 5 for bar in bars),
    )
    return bars[-1].close, atr(bars)[-1], meta.get("symbol"), crypto


def asset_bucket(
    args: argparse.Namespace, symbol: str | None, crypto: bool, deps: RiskDeps
) -> str:
    """--asset, else as etoro_trade.py decides: the meme list first, then what eToro said
    (``--etoro``), else the crypto watchlist."""
    if args.asset != "auto":
        return args.asset
    names = [n for n in (args.etoro, symbol) if n]
    hints = set()
    if names:
        settings = load_crypto_config(deps.config_path)
        hints = {hint_bucket(n, settings) for n in names}
    if MEME in hints:
        return MEME
    if crypto or (not args.etoro and CRYPTO in hints):
        return CRYPTO
    return STOCK


def _limits(deps: RiskDeps, bucket: str = STOCK) -> dict[str, Any]:
    """The bucket's tightest per-order cap, what is left today of every cap it counts in, its
    open positions against their maximum, and its stop_pct."""
    config = load_trading_config(deps.config_path)
    crypto = None if bucket == STOCK else load_crypto_config(deps.config_path)
    entries, now = read_ledger(deps.ledger), deps.now()
    caps = caps_for(bucket, config, crypto)
    usage = [cap_usage(cap, config.account, entries, now) for cap in caps]
    enabled = config.enabled and (
        crypto is None or (crypto.enabled and (bucket != MEME or crypto.meme_enabled))
    )
    rules = bucket_rules(bucket, config, crypto)
    positions = positions_usage(rules, entries, config.account)
    return {
        "bucket": bucket,
        "account": config.account,
        "trading_enabled": enabled,
        "max_order_usd": min(cap.max_order_usd for cap in caps),
        "usd_left_today": min(u["usd_left"] for u in usage),
        "buys_left_today": min(u["buys_left"] for u in usage),
        "open_positions": positions["open"],
        "max_positions": positions["max"],
        "positions_left": positions["left"],
        "stop_pct": rules.stop_pct,
    }


def choose_stop(
    args: argparse.Namespace, entry: float, atr14: float | None, stop_pct: float
) -> tuple[float, str]:
    """(stop, how): --stop, else the bucket's fixed stop_pct, else ATR multiple x ATR14."""
    if args.stop is not None:
        return args.stop, "given"
    if stop_pct > 0:
        return fixed_stop(entry, stop_pct), "fixed_pct"
    if atr14 is None:
        raise SkillError(
            "No stop price and no ATR to derive one.",
            hint="Pass --stop PRICE, or bars with --input/--etoro (14+ bars).",
        )
    return entry - args.atr_mult * atr14, "atr"


def plan_position(
    *,
    account_size: float,
    risk_pct: float,
    entry: float,
    stop: float,
    rr: float,
    limits: dict[str, Any],
) -> dict[str, Any]:
    if stop >= entry:
        raise SkillError(
            f"The stop ({stop:g}) must be below the entry ({entry:g}): trades are long-only."
        )
    risk_usd = account_size * risk_pct / 100.0
    per_unit = entry - stop
    caps = {
        "risk": risk_usd / per_unit * entry,
        "account": account_size,
        "max_order_usd": float(limits["max_order_usd"]),
        "usd_left_today": float(limits["usd_left_today"]),
    }
    if limits["buys_left_today"] <= 0:
        caps["buys_left_today"] = 0.0
    if limits.get("positions_left", 1) <= 0:  # the strategy replay holds one at a time
        caps["positions_left"] = 0.0
    binding = min(caps, key=caps.get)
    amount = math.floor(caps[binding] * 100) / 100
    return {
        "suggested_amount_usd": amount,
        "binding_cap": binding,
        "caps_usd": {k: round(v, 2) for k, v in caps.items()},
        "entry": entry,
        "stop_loss": round(stop, 6),
        "take_profit": round(entry + rr * per_unit, 6),
        "stop_distance_pct": round(per_unit / entry * 100.0, 2),
        "risk_pct": risk_pct,
        "max_loss_usd": round(amount / entry * per_unit, 2),
        "units": round(amount / entry, 6),
        "reward_risk": rr,
        "buy_args": f"--amount {amount:.2f} --stop {round(stop, 6)} --target "
        f"{round(entry + rr * per_unit, 6)}",
    }


def _warnings(
    limits: dict[str, Any], plan: dict[str, Any], risk_pct: float, stop_from: str
) -> list[str]:
    bucket, warnings = limits["bucket"], []
    if not limits["trading_enabled"]:
        warnings.append(f"{bucket} trading is off: this sizing is informational only")
    if bucket == MEME:
        warnings.append(
            "meme coins are extremely volatile: a wide stop is normal, and the whole amount "
            "can be lost if the price gaps through it"
        )
    if limits["positions_left"] <= 0:
        warnings.append(
            f"Kronos already holds {limits['open_positions']} {bucket} position(s), the "
            f"maximum of {limits['max_positions']}: no buy until one closes"
        )
    if plan["suggested_amount_usd"] <= 0:
        warnings.append("no buy fits today's limits")
    floor = widest_stop(plan["entry"], limits["stop_pct"])
    if stop_from == "given" and floor is not None and plan["stop_loss"] < floor:
        warnings.append(
            f"this stop is farther than the {bucket} stop-loss of {limits['stop_pct']:g}%: "
            "etoro_trade.py will refuse it; leave out --stop to use the stop_pct"
        )
    if risk_pct > RISK_PCT["high"]:
        warnings.append(
            f"risking {risk_pct:g}% of the account on one trade is aggressive"
        )
    return warnings


def run(args: argparse.Namespace, deps: RiskDeps) -> dict[str, Any]:
    close, atr14, symbol, crypto = _market(args)
    entry = args.entry or close
    if entry is None:
        raise SkillError(
            "No entry price.", hint="Pass --entry PRICE, or bars with --input/--etoro."
        )
    limits = _limits(deps, asset_bucket(args, symbol, crypto, deps))
    stop, stop_from = choose_stop(args, entry, atr14, limits["stop_pct"])
    profile = risk_profile(goals(load_config(deps.config_path)))
    risk_pct = args.risk_pct or RISK_PCT[profile]
    plan = plan_position(
        account_size=args.account_size,
        risk_pct=risk_pct,
        entry=entry,
        stop=stop,
        rr=args.rr,
        limits=limits,
    )
    return {
        "ok": True,
        "symbol": symbol,
        "atr14": atr14,
        "risk_profile": None if args.risk_pct else profile,
        **plan,
        "stop_rule": stop_from,
        "limits": limits,
        "warnings": _warnings(limits, plan, risk_pct, stop_from),
        "note": NOTE,
    }


_STOP_FROM = {
    "given": "--stop",
    "fixed_pct": "the bucket's stop_pct",
    "atr": "ATR based",
}


def render_text(result: dict[str, Any]) -> str:
    head = f"{result['symbol']}: " if result.get("symbol") else ""
    lines = [
        f"{head}buy up to {result['suggested_amount_usd']:,.2f} USD "
        f"(capped by {result['binding_cap']}), about {result['units']:g} units at "
        f"{result['entry']:,.4f}",
        f"stop {result['stop_loss']:,.4f} (-{result['stop_distance_pct']}%, "
        f"{_STOP_FROM[result['stop_rule']]}), target "
        f"{result['take_profit']:,.4f} ({result['reward_risk']:g}:1), max loss "
        f"{result['max_loss_usd']:,.2f} USD at {result['risk_pct']:g}% risk",
        f"order: etoro_trade.py buy SYMBOL {result['buy_args']}",
        f"{result['limits']['bucket']} limits: {result['limits']['max_order_usd']:g} USD/order, "
        f"{result['limits']['usd_left_today']:g} USD and "
        f"{result['limits']['buys_left_today']} buys left today, "
        f"{result['limits']['open_positions']} of {result['limits']['max_positions']} "
        "positions open",
        *(f"warning: {w}" for w in result["warnings"]),
        result["note"],
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None, deps: RiskDeps | None = None) -> int:
    args = build_parser().parse_args(argv)

    def _go() -> int:
        result = run(args, deps or RiskDeps())
        print(render_text(result) if args.format == "text" else dump_json(result))
        return 0

    return run_cli(_go)


if __name__ == "__main__":
    sys.exit(main())
