#!/usr/bin/env python3
"""Position sizing for a long trade: how much to buy, where the stop and the target go.

risk USD   = account size x risk %          (risk % from --risk-pct, else the user's goals.risk:
                                             low 0.5%, medium 1%, high 2%)
stop       = entry - ATR multiple x ATR14   (or --stop PRICE)
target     = entry + reward:risk x (entry - stop)
amount USD = risk USD / (entry - stop) x entry, then capped by the account size, the per-order
             limit and what is left of today's limits in config.yaml.

It only reads the limits (skills.config.kronos.trading.*) and the trade ledger; it never
changes them and places no order. ``buy_args`` is ready for ``etoro_trade.py buy``: the stop
and target travel with the order (``--stop``/``--target``) and eToro executes them, and an
automatic buy without a stop is refused.

Usage:
  kronos_risk.py --account-size 10000 --etoro AAPL [--interval OneDay] [--risk-pct 1]
  kronos_risk.py --account-size 10000 --entry 187.2 --stop 180 [--rr 2] [--format json]
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
from etoro_trade import load_trading_config, read_ledger, usage_today
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
        "--stop", type=_positive, help="stop price (default: ATR based)"
    )
    parser.add_argument(
        "--atr-mult", type=_positive, default=2.0, help="stop distance in ATRs"
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
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--json",
        dest="format",
        action="store_const",
        const="json",
        help="--format json",
    )
    return parser


def _market(args: argparse.Namespace) -> tuple[float | None, float | None, str | None]:
    """(last close, ATR14, symbol) from the bars, when bars were given."""
    if args.input:
        bars, _warnings = load_bars(args.input)
        symbol = None
    elif args.etoro:
        from etoro_data import fetch_bars

        bars, meta, _warnings = fetch_bars(args.etoro, args.interval, 120)
        symbol = meta.get("symbol")
    else:
        return None, None, None
    return bars[-1].close, atr(bars)[-1], symbol


def _limits(deps: RiskDeps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    count, spent = usage_today(read_ledger(deps.ledger), config.account, deps.now())
    return {
        "account": config.account,
        "trading_enabled": config.enabled,
        "max_order_usd": config.max_order_usd,
        "usd_left_today": round(max(config.max_daily_usd - spent, 0.0), 2),
        "buys_left_today": max(config.max_orders_per_day - count, 0),
    }


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


def run(args: argparse.Namespace, deps: RiskDeps) -> dict[str, Any]:
    close, atr14, symbol = _market(args)
    entry = args.entry or close
    if entry is None:
        raise SkillError(
            "No entry price.", hint="Pass --entry PRICE, or bars with --input/--etoro."
        )
    stop = args.stop
    if stop is None:
        if atr14 is None:
            raise SkillError(
                "No stop price and no ATR to derive one.",
                hint="Pass --stop PRICE, or bars with --input/--etoro (14+ bars).",
            )
        stop = entry - args.atr_mult * atr14
    profile = risk_profile(goals(load_config(deps.config_path)))
    risk_pct = args.risk_pct or RISK_PCT[profile]
    limits = _limits(deps)
    plan = plan_position(
        account_size=args.account_size,
        risk_pct=risk_pct,
        entry=entry,
        stop=stop,
        rr=args.rr,
        limits=limits,
    )
    warnings = []
    if not limits["trading_enabled"]:
        warnings.append("trading is off: this sizing is informational only")
    if plan["suggested_amount_usd"] <= 0:
        warnings.append("no buy fits today's limits")
    if risk_pct > RISK_PCT["high"]:
        warnings.append(
            f"risking {risk_pct:g}% of the account on one trade is aggressive"
        )
    return {
        "ok": True,
        "symbol": symbol,
        "atr14": atr14,
        "risk_profile": None if args.risk_pct else profile,
        **plan,
        "limits": limits,
        "warnings": warnings,
        "note": NOTE,
    }


def render_text(result: dict[str, Any]) -> str:
    head = f"{result['symbol']}: " if result.get("symbol") else ""
    lines = [
        f"{head}buy up to {result['suggested_amount_usd']:,.2f} USD "
        f"(capped by {result['binding_cap']}), about {result['units']:g} units at "
        f"{result['entry']:,.4f}",
        f"stop {result['stop_loss']:,.4f} (-{result['stop_distance_pct']}%), target "
        f"{result['take_profit']:,.4f} ({result['reward_risk']:g}:1), max loss "
        f"{result['max_loss_usd']:,.2f} USD at {result['risk_pct']:g}% risk",
        f"order: etoro_trade.py buy SYMBOL {result['buy_args']}",
        f"limits: {result['limits']['max_order_usd']:g} USD/order, "
        f"{result['limits']['usd_left_today']:g} USD and "
        f"{result['limits']['buys_left_today']} buys left today",
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
