#!/usr/bin/env python3
"""eToro order placement for the Kronos skill: market buys by amount and position closes,
inside hard limits the user sets in config.yaml.

OFF BY DEFAULT. Every guard runs here, before any order leaves the machine:

- ``skills.config.kronos.trading.enabled`` must be true; an unreadable config.yaml means off.
- ``skills.config.kronos.trading.account`` picks ``demo`` (default) or ``real``.
- A buy is long-only and unleveraged (leverage 1, real-asset settlement), at most
  ``max_order_usd``; today's (UTC) opened total stays within ``max_daily_usd`` and
  ``max_orders_per_day``, counted from a local ledger under a file lock so two concurrent
  runs cannot both slip under the cap. A buy whose outcome is unknown keeps counting.
- Crypto is its own bucket (``_kronos_crypto.py``): a crypto buy (eToro instrument type 10,
  else Saturday trading) needs ``skills.config.kronos.crypto.enabled`` and counts only against
  the ``kronos.crypto.*`` caps; a meme coin (symbol in ``kronos.crypto.meme.symbols``) also
  needs ``kronos.crypto.meme.enabled``, must be listed by eToro, and counts against the meme
  caps and the crypto caps. The ``trading.*`` caps then cover the other (stock) buys only.
- Open positions: each bucket holds at most its ``max_positions`` (``trading.``,
  ``crypto.``, ``crypto.meme.``), counted from the ledger under the same lock
  (``_kronos_positions.py``; a meme coin takes a meme slot only). ``reconcile`` drops the
  positions eToro closed on its own (stop-loss, take-profit, closed in the app).
- Lessons bite: an automatic buy is refused while Kronos got the symbol's direction right in
  under half of its last reviewed forecasts (at least 5, scored by kronos_review.py into the
  forecast journal), and unless the symbol's backtests of the last 7 days say ``adds_value``
  (Kronos beat both "repeat the last close" and the ETS baseline). ``--user-requested`` skips
  only these two checks, and only for a buy the user explicitly asked for; every other guard
  still applies. An unreadable journal refuses automatic buys.
- Protection: an automatic buy must carry a stop-loss (``--stop``; ``--target`` optional),
  sent with the order so eToro executes it. Before the order, the instrument's current eToro
  price is read: the stop must sit below it (by at most 50%) and the target above it. A bucket
  with a fixed ``stop_pct`` also refuses any stop farther below the price than that (plus one
  point for the price moving since the buy was sized).
- Market hours: the newest eToro price must be under 2 hours old, and an instrument with no
  Saturday trading (anything but crypto-like 24/7 markets) is bought only inside the New York
  Stock Exchange regular session (holidays and early closes included).
- At most once: an order POST is retried only after HTTP 429 (eToro did not process it), with
  the Retry-After wait or a 15/30/60 s backoff. A timeout, dropped connection, unreadable answer
  or 5xx is never resent: the buy is logged ``unknown`` (it keeps counting toward the limits)
  and ``reconcile`` later looks it up by its request id and in the portfolio.
- A close only reduces risk, so it is not capped, but the position must exist in the
  configured account. Refused buys are logged to ``refused.jsonl`` for the dashboard.

The trading client reaches exactly the routes in TRADE_ROUTES (open order, close position,
order lookup); reads (symbol search, candles, portfolio) go through the read-only
``etoro_data`` client. Endpoint notes: references/etoro-api.md § Trading.

Usage:
  etoro_trade.py status
  etoro_trade.py positions [--format table|json]
  etoro_trade.py buy SYMBOL --amount USD --reason TEXT [--stop RATE] [--target RATE]
                 [--trailing] [--user-requested] [--dry-run]
  etoro_trade.py close POSITION_ID [--units N] --reason TEXT [--dry-run]
  etoro_trade.py set-stop POSITION_ID --stop RATE [--target RATE] [--trailing] --reason TEXT
                 [--dry-run]
  etoro_trade.py reconcile
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_calendar import market_status
from _kronos_common import (
    UTC,
    FileLock,
    SkillError,
    append_jsonl,
    display_home,
    dump_json,
    fold_rows,
    iso_z,
    kronos_home,
    parse_timestamp,
    read_jsonl,
    render_table,
    rows_to_bars,
    run_cli,
)
from _kronos_config import ConfigError, kronos_settings, load_config
from _kronos_crypto import (
    CRYPTO,
    MEME,
    STOCK,
    Cap,
    CryptoConfig,
    CryptoConfigError,
    bucket_of,
    caps_for,
    classify,
    hint_bucket,
    is_meme,
    parse_crypto_config,
)
from _kronos_crypto import SET_CMD as CRYPTO_SET_CMD
from _kronos_positions import (
    MAX_STOP_PCT,
    NOT_COUNTED,
    BucketRules,
    bucket_rules,
    flat_rows,
    holdings,
    open_positions,
    parse_stop_pct,
    positions_usage,
    widest_stop,
)
from _kronos_journal import (
    BACKTEST_MAX_AGE,
    GATE_MIN_HIT_RATE,
    backtest_gate,
    backtests_path,
    forecasts_path,
    gate_status,
    read_backtests,
    read_forecasts,
)
from etoro_data import (
    BASE_URL,
    MAX_RETRY_AFTER,
    USER_AGENT,
    EtoroClient,
    EtoroError,
    _default_opener,
    _error_detail,
    _lookup_names,
    load_keys,
    pick_exact,
    search_candidates,
)

SET_CMD = "clawk config set skills.config.kronos.trading"
TRADE_ROUTES = (
    ("POST", re.compile(r"^/api/v2/trading/execution/(?:demo/)?orders$")),
    (
        "POST",
        re.compile(
            r"^/api/v1/trading/execution/(?:demo/)?market-open-orders/by-amount$"
        ),
    ),
    (
        "POST",
        re.compile(
            r"^/api/v1/trading/execution/(?:demo/)?market-close-orders/positions/\d+$"
        ),
    ),
    ("GET", re.compile(r"^/api/v2/trading/info/(?:demo/)?orders:lookup$")),
    # Stop-loss / take-profit of an open position, changed in place (eToro, June 2026).
    ("PATCH", re.compile(r"^/api/v2/trading/(?:demo/)?positions/\d+$")),
)
# v2 order lookup status ids (etoro-go); see references/etoro-api.md.
ORDER_STATUS = {
    1: "received",
    2: "placed",
    3: "filled",
    4: "rejected",
    5: "partially_filled",
    6: "pending_cancel",
    7: "canceled",
    8: "expired",
    9: "canceled_partially_filled",
    10: "rejected_partially_filled",
}
FINAL_STATUSES = {"filled", "rejected", "canceled", "expired", "partially_filled"}
# Buys whose outcome is not known: a failed or unanswered request, or a run that stopped mid-order.
IN_DOUBT = {"unknown", "submitting"}
LANDED = {"filled", "partially_filled", "received", "placed"}
POLL_ATTEMPTS = 3
POLL_INTERVAL = 2.0
# HTTP 429 is the only answer that proves eToro did not process a request, so it is the only one
# retried. Order POSTs wait Retry-After (capped) or this backoff (eToro builders' guidance);
# reads retry once.
WRITE_RETRY_WAITS = (15.0, 30.0, 60.0)
READ_RETRY_WAITS = (2.0,)
MAX_WRITE_RETRY_AFTER = 60.0
# Current price for the protection and market checks: hourly candles, the newest of which is the
# still-forming one; 200 of them span 8+ days, so a 24/7 instrument always shows Saturday bars.
# Saturday, not Sunday: 24/5 stock sessions and forex open on Sunday evening (UTC Monday or late
# Sunday) and must stay under the New York hours rule.
PRICE_INTERVAL = "OneHour"
PRICE_BARS = 200
PRICE_MAX_AGE = timedelta(hours=2)
MAX_STOP_DISTANCE_PCT = MAX_STOP_PCT
# /pnl answers are cached ~10 s and fills are asynchronous: reconcile only older buys.
RECONCILE_MIN_AGE = timedelta(seconds=60)
RECONCILE_TIME_SLACK = timedelta(minutes=2)
_HTTP_HINTS = {
    400: "eToro rejected the order (amount under the instrument minimum, stop or target too "
    "close to the price, market closed for this order type, or invalid parameters). Nothing "
    "was bought.",
    401: "eToro rejected the API keys.",
    403: "eToro refused: the key pair lacks trading permission, or its environment (real vs "
    "demo) does not match skills.config.kronos.trading.account.",
    404: "eToro has no such route or resource.",
    429: "eToro rate limit hit (20 order requests and 60 reads per minute per user key); it "
    "did not process the request, so nothing was bought. Try again in a few minutes.",
}


class TradingRefused(SkillError):
    """A guard stopped the order before any order request was made."""

    kind = "limit"  # what the dashboard's refusal log calls it
    bucket: str | None = None  # stock / crypto / meme once known, for the refusal log


class LessonRefused(TradingRefused):
    """The symbol's recent forecast accuracy is too low for an automatic buy."""

    kind = "lesson"


class BacktestRefused(TradingRefused):
    """No fresh backtest says Kronos beats both baselines for the symbol."""

    kind = "backtest"


class ProtectionRefused(TradingRefused):
    """The stop-loss / take-profit is missing or on the wrong side of the price."""

    kind = "stop"


class MarketRefused(TradingRefused):
    """The instrument's market is closed or its price is stale."""

    kind = "market"


class CryptoRefused(TradingRefused):
    """Crypto or meme-coin trading is off, or eToro does not list the meme coin."""

    kind = "crypto"


class _RateLimited(Exception):
    """HTTP 429: eToro did not process the request."""

    def __init__(self, retry_after: str | None) -> None:
        super().__init__("rate limited")
        self.retry_after = retry_after


# ── Config ──


@dataclass(frozen=True)
class TradingConfig:
    enabled: bool
    account: str
    max_order_usd: float
    max_daily_usd: float
    max_orders_per_day: int
    max_positions: int = 5
    stop_pct: float = 0.0  # 0 = ATR stop


DEFAULTS = TradingConfig(False, "demo", 100.0, 300.0, 5)


def _as_bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off", "", "none"}:
        return False
    raise TradingRefused(f"skills.config.kronos.trading.{key} must be true or false.")


def _as_number(value: Any, key: str, kind: type) -> float | int:
    try:
        number = kind(float(str(value).strip()))
    except (TypeError, ValueError):
        number = None
    if number is None or number <= 0:
        raise TradingRefused(
            f"skills.config.kronos.trading.{key} must be a positive number."
        )
    return number


def _as_stop_pct(value: Any) -> float:
    pct = parse_stop_pct(value)
    if pct is None:
        raise TradingRefused(
            "skills.config.kronos.trading.stop_pct must be a number from 0 (ATR stop) to "
            f"{MAX_STOP_PCT:g}."
        )
    return pct


def _trading_section(path: Path | None) -> dict[str, Any]:
    try:
        node = kronos_settings(load_config(path)).get("trading")
    except ConfigError as exc:
        raise TradingRefused(f"{exc}; trading stays off.", hint=exc.hint) from None
    return node if isinstance(node, dict) else {}


def load_trading_config(path: Path | None = None) -> TradingConfig:
    raw = _trading_section(path)
    account = str(raw.get("account") or DEFAULTS.account).strip().lower()
    if account not in {"demo", "real"}:
        raise TradingRefused(
            "skills.config.kronos.trading.account must be demo or real."
        )
    return TradingConfig(
        enabled=_as_bool(raw.get("enabled", DEFAULTS.enabled), "enabled"),
        account=account,
        max_order_usd=float(
            _as_number(
                raw.get("max_order_usd", DEFAULTS.max_order_usd), "max_order_usd", float
            )
        ),
        max_daily_usd=float(
            _as_number(
                raw.get("max_daily_usd", DEFAULTS.max_daily_usd), "max_daily_usd", float
            )
        ),
        max_orders_per_day=int(
            _as_number(
                raw.get("max_orders_per_day", DEFAULTS.max_orders_per_day),
                "max_orders_per_day",
                int,
            )
        ),
        max_positions=int(
            _as_number(
                raw.get("max_positions", DEFAULTS.max_positions), "max_positions", int
            )
        ),
        stop_pct=_as_stop_pct(raw.get("stop_pct", DEFAULTS.stop_pct)),
    )


def load_crypto_config(path: Path | None = None) -> CryptoConfig:
    """``skills.config.kronos.crypto`` (defaults: off, $50/order, $150/day, 3 buys; meme coins
    off, $20/order, $50/day); an unreadable or invalid value refuses instead of guessing."""
    try:
        return parse_crypto_config(kronos_settings(load_config(path)).get("crypto"))
    except ConfigError as exc:
        raise TradingRefused(f"{exc}; trading stays off.", hint=exc.hint) from None
    except CryptoConfigError as exc:
        raise TradingRefused(str(exc), hint="Only the user fixes it.") from None


def require_enabled(config: TradingConfig) -> None:
    if not config.enabled:
        raise TradingRefused(
            "Trading is turned off for this profile.",
            hint=f"Only the user turns it on: `{SET_CMD}.enabled true` (account "
            f"defaults to demo). Do not change trading settings on your own.",
        )


# ── Ledger (append-only JSONL; later lines with the same id update earlier ones) ──


def ledger_path() -> Path:
    return kronos_home() / "trades.jsonl"


def refused_path(kronos_dir: Path | None = None) -> Path:
    return (kronos_dir or kronos_home()) / "refused.jsonl"


class LedgerLock(FileLock):
    """The ledger's lock; a busy lock refuses the order instead of waiting forever.

    It is held from the last limit check until the outcome is logged. With 429 backoff that can
    take minutes (two routes x four attempts x 30 s timeout, plus waits of at most 60 s each),
    so it only counts as abandoned after 15 minutes: a lock reclaimed too early would let a
    second run slip under the daily cap.
    """

    stale_after = 900.0

    def busy_error(self) -> SkillError:
        return TradingRefused(
            "Another order is still being placed; try again in a minute."
        )


def read_ledger(path: Path | None = None) -> list[dict[str, Any]]:
    """Entries folded by id, in first-seen order; malformed lines are skipped."""
    return fold_rows(read_jsonl(path or ledger_path()))


def ledger_for_limits(path: Path | None = None) -> list[dict[str, Any]]:
    """The ledger a buy is checked against; unreadable means no buy (fail closed)."""
    try:
        return read_ledger(path)
    except (OSError, ValueError) as exc:
        raise TradingRefused(
            f"The trade ledger could not be read ({exc}), so today's limits and the open "
            "positions cannot be counted; nothing is bought.",
            hint=f"Repair {path or ledger_path()}; never delete it, the limits are counted "
            "from it.",
        ) from None


def append_ledger(row: Mapping[str, Any], path: Path | None = None) -> None:
    append_jsonl(path or ledger_path(), dict(row))


STOCK_ONLY = frozenset({STOCK})
# How a refusal names each bucket's limits ("the crypto daily limit"); stocks keep the old text.
_CAP_WORD = {STOCK: "", CRYPTO: "crypto ", MEME: "meme-coin "}


def usage_today(
    entries: list[dict[str, Any]],
    account: str,
    now: datetime,
    buckets: frozenset[str] = STOCK_ONLY,
) -> tuple[int, float]:
    """(orders opened, USD opened) today in UTC on *account* in *buckets* (stock by default;
    rows from before the buckets count as stock), excluding no-money outcomes."""
    today = now.astimezone(UTC).date().isoformat()
    opened = [
        e
        for e in entries
        if e.get("action") == "open"
        and e.get("account") == account
        and str(e.get("ts", "")).startswith(today)
        and e.get("status") not in NOT_COUNTED
        and bucket_of(e) in buckets
    ]
    return len(opened), round(sum(float(e.get("amount") or 0.0) for e in opened), 2)


def check_cap(
    cap: Cap,
    account: str,
    amount: float,
    entries: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """Refuse *amount* when it breaks one bucket's per-order, daily-count or daily-USD cap."""
    word = _CAP_WORD.get(cap.name, "")
    if amount <= 0:
        raise TradingRefused("The amount must be a positive number of USD.")
    if amount > cap.max_order_usd:
        raise TradingRefused(
            f"{amount:.2f} USD is over the {word}per-order limit of "
            f"{cap.max_order_usd:.2f} USD.",
            hint="Use a smaller amount. Only the user can raise the limit.",
        )
    count, spent = usage_today(entries, account, now, cap.counts)
    if count >= cap.max_orders_per_day:
        raise TradingRefused(
            f"Today's limit of {cap.max_orders_per_day} {word}buys on the {account} "
            "account is used up.",
            hint="Limits reset at 00:00 UTC. Only the user can raise them.",
        )
    if spent + amount > cap.max_daily_usd + 1e-9:
        left = max(cap.max_daily_usd - spent, 0.0)
        raise TradingRefused(
            f"This buy would take today's {word}total to {spent + amount:.2f} USD; the "
            f"{word}daily limit is {cap.max_daily_usd:.2f} USD ({left:.2f} USD left).",
            hint="Limits reset at 00:00 UTC. Only the user can raise them.",
        )
    return {
        "orders_today": count,
        "usd_today": spent,
        "usd_left_after": round(cap.max_daily_usd - spent - amount, 2),
    }


def check_limits(
    config: TradingConfig, amount: float, entries: list[dict[str, Any]], now: datetime
) -> dict[str, Any]:
    """The stock bucket's caps (``trading.*``)."""
    (cap,) = caps_for(STOCK, config, None)
    return check_cap(cap, config.account, amount, entries, now)


def check_bucket_limits(
    config: TradingConfig,
    crypto: CryptoConfig,
    bucket: str,
    amount: float,
    entries: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """Every cap of *bucket* (a meme coin: the meme caps, then the crypto caps), then its
    maximum of open positions. The result describes the bucket's own cap and, for a meme coin,
    what the crypto cap leaves too."""
    own, *others = caps_for(bucket, config, crypto)
    result = {"bucket": bucket, **check_cap(own, config.account, amount, entries, now)}
    for cap in others:
        left = check_cap(cap, config.account, amount, entries, now)["usd_left_after"]
        result[f"{cap.name}_usd_left_after"] = left
    rules = bucket_rules(bucket, config, crypto)
    result["positions_open"] = check_positions(rules, config.account, entries)
    result["max_positions"] = rules.max_positions
    return result


def check_positions(
    rules: BucketRules, account: str, entries: list[dict[str, Any]]
) -> int:
    """Refuse a buy that would hold more than the bucket's maximum of open positions."""
    held = open_positions(entries, account, rules.bucket)
    if held >= rules.max_positions:
        word = _CAP_WORD.get(rules.bucket) or "stock "
        raise TradingRefused(
            f"Kronos already holds {held} {word}position(s) on the {account} account; the "
            f"maximum is {rules.max_positions}.",
            hint="Close one first, or wait for its stop or target. If eToro already closed "
            "one, run `etoro_trade.py reconcile` to update the count. Only the user can raise "
            "the maximum.",
        )
    return held


def require_bucket_enabled(bucket: str, crypto: CryptoConfig) -> None:
    """Crypto and meme coins each have their own switch, off until the user turns it on."""
    if bucket in {CRYPTO, MEME} and not crypto.enabled:
        raise CryptoRefused(
            "Crypto trading is turned off for this profile.",
            hint=f"Only the user turns it on: `{CRYPTO_SET_CMD}.enabled true` (or Settings "
            "in the Kronos dashboard); it has its own limits, separate from the stock ones. "
            "Do not change trading settings on your own.",
        )
    if bucket == MEME and not crypto.meme_enabled:
        raise CryptoRefused(
            "Meme-coin trading is turned off for this profile: meme coins are extremely "
            "volatile and have their own, smaller limits.",
            hint=f"Only the user turns it on: `{CRYPTO_SET_CMD}.meme.enabled true` (or "
            "Settings in the Kronos dashboard). Do not change trading settings on your own.",
        )


def check_lessons(
    symbol: str, journal: Path, *, user_requested: bool
) -> dict[str, Any]:
    """Refuse an automatic buy while the symbol's recent forecasts mostly missed (fail closed).

    Returns the track record logged with the order. ``user_requested`` (the user named this
    trade) skips the refusal only; the limits are checked separately and always apply.
    """
    try:
        gate = gate_status(read_forecasts(journal), symbol)
    except (OSError, ValueError, TypeError) as exc:
        if user_requested:
            return {"user_requested": True, "checked": False, "error": str(exc)}
        raise LessonRefused(
            f"The forecast journal could not be read ({exc}), so Kronos cannot check its "
            "track record; automatic buys stay off.",
            hint=f"Repair or remove {journal}. Buy only if the user explicitly asks for "
            "this trade (then add --user-requested).",
        ) from None
    record = {
        "user_requested": user_requested,
        "checked": True,
        "matured": gate["matured"],
        "hits": gate["hits"],
        "blocked": gate["blocked"],
    }
    if gate["blocked"] and not user_requested:
        raise LessonRefused(
            f"Kronos got the direction of {gate['symbol']} right in only {gate['hits']} of "
            f"its last {gate['matured']} reviewed forecasts; automatic buys need "
            f"{GATE_MIN_HIT_RATE:.0%} or better.",
            hint="Do not buy it on the forecast. Only if the user explicitly asks for this "
            "exact buy, run it again with --user-requested.",
        )
    return record


_USER_ONLY_HINT = (
    "Do not buy it on the forecast. Only if the user explicitly asks for this exact buy, "
    "run it again with --user-requested."
)


def _backtest_refusal(gate: dict[str, Any]) -> BacktestRefused:
    days = BACKTEST_MAX_AGE.days
    if not gate["verdicts"]:
        last = gate["last_backtest"] or "never"
        return BacktestRefused(
            f"No backtest of {gate['symbol']} in the last {days} days (last: {last}); "
            "automatic buys need a fresh 'adds_value' verdict.",
            hint=f"Run kronos_backtest.py for {gate['symbol']} (--etoro, or --symbol "
            f"{gate['symbol']} for file data) and decide again. {_USER_ONLY_HINT}",
        )
    row = gate["failing"][0]
    return BacktestRefused(
        f"The latest backtest of {gate['symbol']} ({row.get('interval')}, "
        f"{row.get('made_at')}) says {row.get('verdict')}: Kronos did not beat both 'repeat "
        "the last close' and the ETS baseline, so automatic buys stay off.",
        hint=_USER_ONLY_HINT,
    )


def check_backtest(
    symbol: str, path: Path, now: datetime, *, user_requested: bool
) -> dict[str, Any]:
    """Refuse an automatic buy unless the symbol's recent backtests say ``adds_value``."""
    try:
        gate = backtest_gate(read_backtests(path), symbol, now)
    except (OSError, ValueError, TypeError) as exc:
        if user_requested:
            return {"user_requested": True, "checked": False, "error": str(exc)}
        raise BacktestRefused(
            f"The backtest log could not be read ({exc}); automatic buys stay off.",
            hint=f"Repair or remove {path}, then re-run kronos_backtest.py.",
        ) from None
    if gate["blocked"] and not user_requested:
        raise _backtest_refusal(gate)
    return {
        "user_requested": user_requested,
        "checked": True,
        "verdicts": gate["verdicts"],
        "blocked": gate["blocked"],
    }


def check_protection(
    stop: float | None, target: float | None, *, user_requested: bool
) -> None:
    """Static stop-loss / take-profit checks; no price needed, no request made."""
    if stop is None and not user_requested:
        raise ProtectionRefused(
            "An automatic buy needs a stop-loss: pass --stop RATE (and --target RATE).",
            hint="Size the trade with kronos_risk.py and pass its stop_loss as --stop and "
            "take_profit as --target; eToro then executes them even between runs.",
        )
    for flag, value in (("--stop", stop), ("--target", target)):
        if value is not None and not (math.isfinite(value) and value > 0):
            raise ProtectionRefused(f"{flag} must be a positive price.")
    if stop is not None and target is not None and target <= stop:
        raise ProtectionRefused(
            f"--target ({target:g}) must be above --stop ({stop:g}) for a long buy."
        )


def check_price_levels(stop: float | None, target: float | None, price: float) -> None:
    """The stop below the current price (by at most 50%), the target above it."""
    if stop is not None and stop >= price:
        raise ProtectionRefused(
            f"The stop ({stop:g}) is not below the current price ({price:g}); eToro would "
            "close the position at once.",
            hint="Recompute the stop with kronos_risk.py from fresh bars.",
        )
    floor = price * (1 - MAX_STOP_DISTANCE_PCT / 100.0)
    if stop is not None and stop < floor:
        raise ProtectionRefused(
            f"The stop ({stop:g}) is more than {MAX_STOP_DISTANCE_PCT:g}% below the current "
            f"price ({price:g}); that looks like a typo.",
            hint="Recompute the stop with kronos_risk.py from fresh bars.",
        )
    if target is not None and target <= price:
        raise ProtectionRefused(
            f"The target ({target:g}) is not above the current price ({price:g}).",
            hint="Recompute the target with kronos_risk.py from fresh bars.",
        )


def check_stop_rule(stop: float | None, price: float, stop_pct: float) -> None:
    """A bucket with a fixed stop_pct accepts no stop farther below the price than that."""
    floor = widest_stop(price, stop_pct)
    if stop is not None and floor is not None and stop < floor:
        raise ProtectionRefused(
            f"The stop ({stop:g}) is {(1 - stop / price) * 100:.1f}% below the current price "
            f"({price:g}); this asset type's stop-loss is {stop_pct:g}%.",
            hint="Recompute the stop with kronos_risk.py, which applies the stop_pct. Only "
            "the user changes stop_pct.",
        )


def market_snapshot(reader: EtoroClient, instrument_id: int) -> dict[str, Any]:
    """Current price (the forming candle's close), its time, and whether it trades on Saturdays."""
    bars, _warnings = rows_to_bars(
        reader.candles(instrument_id, PRICE_INTERVAL, PRICE_BARS)
    )
    newest = bars[-1]
    return {
        "price": newest.close,
        "price_time": newest.ts,
        "trades_weekends": any(bar.ts.weekday() == 5 for bar in bars),
    }


def check_market(
    symbol: str, instrument: Mapping[str, Any], snapshot: dict[str, Any], now: datetime
) -> dict[str, Any]:
    """Refuse when eToro marks the instrument untradable, its price is stale, or (for an
    instrument with no Saturday trading) the NYSE regular session is closed."""
    if (
        instrument.get("isDelisted") is True
        or instrument.get("isCurrentlyTradable") is False
    ):
        raise MarketRefused(f"eToro lists {symbol} as not tradable right now.")
    moment = now.astimezone(UTC).replace(tzinfo=None)
    newest = snapshot["price_time"]
    if moment - newest > PRICE_MAX_AGE:
        raise MarketRefused(
            f"No eToro price for {symbol} since {iso_z(newest)}: its market looks closed.",
            hint="Try again during its trading hours.",
        )
    market = {
        "price": snapshot["price"],
        "price_time": iso_z(newest),
        "calendar": "24x7" if snapshot["trades_weekends"] else "nyse",
    }
    if snapshot["trades_weekends"]:
        return market
    status = market_status(now)
    if not status["open"]:
        raise MarketRefused(
            "The New York stock market is closed now (weekend, holiday or after the close); "
            "a stock order would wait for the open and fill far from today's price.",
            hint=f"The next regular session opens {status['next_open']} (UTC). Instruments "
            "that trade on Saturdays, like crypto, are not limited to these hours.",
        )
    return {**market, "calendar_source": status["source"]}


# ── Trading client ──


def _segment(account: str) -> str:
    return "demo/" if account == "demo" else ""


def _retry_wait(header: str | None, default: float, cap: float) -> float:
    """Seconds to wait after a 429: Retry-After in seconds when readable, else *default*."""
    try:
        seconds = float(header) if header else default
    except ValueError:  # an HTTP-date or junk
        seconds = default
    if not math.isfinite(seconds):
        seconds = default
    return min(max(seconds, 0.0), cap)


def _protection_fields(order: Mapping[str, Any]) -> dict[str, Any]:
    """v2 order fields for a stop-loss and a take-profit (absolute rates); {} when none.

    A trailing stop starts at the given rate and eToro moves it up with the price."""
    fields: dict[str, Any] = {}
    if order.get("stop_loss") is not None:
        fields["stopLossRate"] = order["stop_loss"]
        fields["stopLossType"] = "trailing" if order.get("trailing_stop") else "fixed"
    if order.get("take_profit") is not None:
        fields["takeProfitRate"] = order["take_profit"]
    return fields


class TradeClient:
    """Reaches only TRADE_ROUTES; *opener* and *sleep* are injectable for tests."""

    def __init__(
        self,
        api_key: str,
        user_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key, self._user_key = api_key, user_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._open = opener or _default_opener()
        self._sleep = sleep

    def build_request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        request_id: str | None = None,
    ) -> urllib.request.Request:
        if not any(m == method and rx.match(path) for m, rx in TRADE_ROUTES):
            raise TradingRefused(
                f"Refusing {method} {path}: not a known trading route."
            )
        url = self._base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {
            "x-api-key": self._api_key,
            "x-user-key": self._user_key,
            # Correlation id, echoed back as referenceId and usable to look the order up when
            # its answer is lost. The v2 reference calls it an idempotency key, but eToro's own
            # builder guidance says trade requests have none; never rely on it: an order is
            # resent only after a 429.
            "x-request-id": request_id or str(uuid.uuid4()),
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(dict(body)).encode("utf-8")
        return urllib.request.Request(url, data=data, headers=headers, method=method)

    def _once(self, request: urllib.request.Request) -> Any:
        try:
            with self._open(request, timeout=self._timeout) as response:
                raw = response.read()
            return json.loads(raw.decode("utf-8") or "null") if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            if exc.code == 429:
                headers = exc.headers
                raise _RateLimited(
                    headers.get("Retry-After") if headers else None
                ) from None
            raise EtoroError(
                f"HTTP {exc.code} from eToro: {_error_detail(raw) or 'no detail'}",
                hint=_HTTP_HINTS.get(exc.code),
                status=exc.code,
            ) from None
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            reason = getattr(exc, "reason", None) or exc
            raise EtoroError(f"No answer from eToro: {reason}") from None
        except ValueError as exc:
            raise EtoroError(f"eToro returned a non-JSON response: {exc}") from None

    def send(self, method: str, path: str, **kwargs: Any) -> Any:
        """One request, resent only after HTTP 429 (eToro did not process it).

        Order POSTs are retried up to three times, waiting Retry-After (at most 60 s) or 15, 30
        and 60 s; reads once. Any other failure raises at once: after a timeout, a dropped
        connection, an unreadable answer or a 5xx an order may have gone through, and sending it
        again could open a second position.
        """
        request = self.build_request(method, path, **kwargs)
        waits = WRITE_RETRY_WAITS if method == "POST" else READ_RETRY_WAITS
        cap = MAX_WRITE_RETRY_AFTER if method == "POST" else MAX_RETRY_AFTER
        for wait in (*waits, None):
            try:
                return self._once(request)
            except _RateLimited as limited:
                if wait is None:
                    break
                self._sleep(_retry_wait(limited.retry_after, wait, cap))
        raise EtoroError(
            f"eToro kept answering 429 after {len(waits)} retries.",
            hint=_HTTP_HINTS[429],
            status=429,
        )

    def open_buy(self, order: Mapping[str, Any]) -> tuple[Any, str]:
        """Market buy by amount with the order's stop-loss and take-profit.

        The deprecated v1 route is tried only when the v2 route is missing (404/405) and the
        order carries no stop or target: v1 is not known to keep them, and a position without
        its stop must never be opened by accident.
        """
        seg = _segment(order["account"])
        body = {
            "action": "open",
            "transaction": "buy",
            "instrumentId": order["instrument_id"],
            "settlementType": "real",
            "orderType": "mkt",
            "leverage": 1,
            "amount": order["amount"],
            **_protection_fields(order),
        }
        try:
            path = f"/api/v2/trading/execution/{seg}orders"
            return self.send("POST", path, body=body, request_id=order["id"]), "v2"
        except EtoroError as exc:
            if exc.status not in (404, 405):
                raise
            if _protection_fields(order):
                raise EtoroError(
                    "eToro's v2 order route is missing and the older route is not known to "
                    "keep a stop-loss or take-profit, so nothing was bought.",
                    hint="Check references/etoro-api.md § Trading; do not retry without a stop.",
                    status=exc.status,
                ) from None
        legacy = {
            "InstrumentID": order["instrument_id"],
            "IsBuy": True,
            "Leverage": 1,
            "Amount": order["amount"],
        }
        path = f"/api/v1/trading/execution/{seg}market-open-orders/by-amount"
        request_id = order["legacy_request_id"]
        return self.send("POST", path, body=legacy, request_id=request_id), "v1"

    def close_position(
        self, account: str, position_id: int, instrument_id: int, units: float | None
    ) -> Any:
        path = (
            f"/api/v1/trading/execution/{_segment(account)}market-close-orders/"
            f"positions/{int(position_id)}"
        )
        body = {"InstrumentId": instrument_id, "UnitsToDeduct": units}
        return self.send("POST", path, body=body, request_id=str(uuid.uuid4()))

    def set_protection(
        self,
        account: str,
        position_id: int,
        stop: float,
        target: float | None,
        *,
        trailing: bool = False,
    ) -> Any:
        """Set an open position's stop-loss (and take-profit) in place. Asynchronous at eToro:
        the answer only says the change was accepted; `positions` shows when it applies."""
        body: dict[str, Any] = {
            "stopLossRate": stop,
            "stopLossType": "trailing" if trailing else "fixed",
        }
        if target is not None:
            body["takeProfitRate"] = target
        path = f"/api/v2/trading/{_segment(account)}positions/{int(position_id)}"
        return self.send("PATCH", path, body=body, request_id=str(uuid.uuid4()))

    def order_status(
        self, account: str, query: Mapping[str, Any]
    ) -> tuple[str | None, str | None, int | None]:
        """(status, error message, order id) from the v2 lookup; Nones when eToro cannot say.

        *query* is ``{"orderId": ...}`` or ``{"referenceId": <the x-request-id it was sent
        with>}``, the only handle left when an order's answer was lost.
        """
        try:
            payload = self.send(
                "GET",
                f"/api/v2/trading/info/{_segment(account)}orders:lookup",
                query=query,
            )
        except EtoroError:
            return None, None, None
        if not isinstance(payload, dict):
            return None, None, None
        status = payload.get("status")
        name = None
        if isinstance(status, dict):
            try:
                name = ORDER_STATUS.get(int(status.get("id")))
            except (TypeError, ValueError):
                name = None
        error = status.get("errorMessage") if isinstance(status, dict) else None
        return name, error or None, order_id_of(payload)

    def lookup(self, account: str, order_id: int) -> tuple[str, str | None]:
        """(status, error message) of an order; ``("submitted", None)`` when unknown."""
        name, error, _order_id = self.order_status(account, {"orderId": int(order_id)})
        return name or "submitted", error


def order_id_of(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for value in (
        payload.get("orderId"),
        payload.get("orderID"),
        (payload.get("orderForOpen") or {}).get("orderID"),
        (payload.get("orderForClose") or {}).get("orderID"),
    ):
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


# ── Commands ──


@dataclass
class Deps:
    """Everything a command touches outside this module, injectable for tests."""

    config_path: Path | None = None
    ledger: Path | None = None
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    reader: EtoroClient | None = None
    trader: TradeClient | None = None
    sleep: Callable[[float], None] = time.sleep
    # Dashboard snapshot file; None = $CLAWK_HOME/dashboards/kronos.json.
    dashboard: Path | None = None

    def clients(self) -> tuple[EtoroClient, TradeClient]:
        if self.reader is None or self.trader is None:
            keys = load_keys()
            self.reader = self.reader or EtoroClient(*keys)
            self.trader = self.trader or TradeClient(*keys)
        return self.reader, self.trader

    def lock(self) -> LedgerLock:
        target = self.ledger or ledger_path()
        return LedgerLock(target.with_suffix(".lock"), sleep=self.sleep)

    def kronos_dir(self) -> Path:
        """Where the ledger lives; the journal and refusal log sit next to it."""
        return (self.ledger or ledger_path()).parent

    def refresh_dashboard(self) -> None:
        from kronos_dashboard import refresh_safely

        refresh_safely(
            config_path=self.config_path,
            kronos_dir=self.kronos_dir(),
            out=self.dashboard,
            now=self.now(),
        )


def cap_usage(
    cap: Cap, account: str, entries: list[dict[str, Any]], now: datetime
) -> dict[str, Any]:
    """Today's (UTC) use of one cap and what is left of it."""
    count, spent = usage_today(entries, account, now, cap.counts)
    return {
        "buys": count,
        "usd": spent,
        "buys_left": max(cap.max_orders_per_day - count, 0),
        "usd_left": round(max(cap.max_daily_usd - spent, 0.0), 2),
    }


def _crypto_status(
    config: TradingConfig, deps: Deps, entries: list[dict[str, Any]]
) -> dict[str, Any]:
    try:
        crypto = load_crypto_config(deps.config_path)
    except TradingRefused as exc:
        return {"error": str(exc)}
    meme_cap, crypto_cap = caps_for(MEME, config, crypto)
    account, now = config.account, deps.now()
    return {
        "config": asdict(crypto),
        "today_utc": cap_usage(crypto_cap, account, entries, now),
        "meme_today_utc": cap_usage(meme_cap, account, entries, now),
        "positions": positions_usage(
            bucket_rules(CRYPTO, config, crypto), entries, account
        ),
        "meme_positions": positions_usage(
            bucket_rules(MEME, config, crypto), entries, account
        ),
        "note": "Crypto buys count only against these caps, meme coins against both the "
        "meme and the crypto caps; the stock limits above cover everything else. Open "
        "positions are counted per type: a meme coin takes a meme slot only.",
        "change_settings": f"{CRYPTO_SET_CMD}.<enabled|watchlist|max_order_usd|"
        "max_daily_usd|max_orders_per_day|max_positions|stop_pct|meme.enabled|"
        "meme.symbols|meme.max_order_usd|meme.max_daily_usd|meme.max_orders_per_day|"
        "meme.max_positions|meme.stop_pct> <value> (the user decides)",
    }


def cmd_status(_args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    entries = read_ledger(deps.ledger)
    (stock_cap,) = caps_for(STOCK, config, None)
    return {
        "ok": True,
        "config": asdict(config),
        "today_utc": cap_usage(stock_cap, config.account, entries, deps.now()),
        "positions": positions_usage(
            bucket_rules(STOCK, config, None), entries, config.account
        ),
        "crypto": _crypto_status(config, deps, entries),
        "ledger": str(deps.ledger or ledger_path()),
        "change_settings": f"{SET_CMD}.<enabled|account|max_order_usd|max_daily_usd|"
        "max_orders_per_day|max_positions|stop_pct> <value> (the user decides; config.yaml in "
        f"{display_home()}; these cover stocks, ETFs and everything but crypto)",
    }


def _position_row(pos: Mapping[str, Any], names: Mapping[int, Any]) -> dict[str, Any]:
    instrument_id = int(pos.get("instrumentID") or 0)
    info = names.get(instrument_id) or {}
    pnl = pos.get("unrealizedPnL")
    return {
        "position_id": pos.get("positionID"),
        "symbol": info.get("symbolFull"),
        "instrument_id": instrument_id,
        "direction": "long" if pos.get("isBuy", True) else "short",
        "units": pos.get("units"),
        "invested_usd": pos.get("amount"),
        "open_rate": pos.get("openRate"),
        "stop_loss": pos.get("stopLossRate"),
        "trailing_stop": bool(pos.get("isTslEnabled")),
        "take_profit": pos.get("takeProfitRate"),
        "opened": pos.get("openDateTime"),
        "leverage": pos.get("leverage"),
        "unrealized_pnl": pnl.get("pnL") if isinstance(pnl, dict) else None,
    }


def cmd_positions(_args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    reader, _ = deps.clients()
    portfolio, _path = reader.portfolio(config.account)
    positions = [p for p in portfolio.get("positions") or [] if isinstance(p, dict)]
    ids = sorted({int(p.get("instrumentID") or 0) for p in positions} - {0})
    names, _failed = _lookup_names(reader, ids[:60])
    return {
        "ok": True,
        "account": config.account,
        "positions": [_position_row(p, names) for p in positions],
        "note": "Copy-trading positions are not listed: close them in the eToro app.",
    }


def _poll(trader: TradeClient, account: str, order_id: int, sleep: Callable) -> tuple:
    status, error = "submitted", None
    for _ in range(POLL_ATTEMPTS):
        sleep(POLL_INTERVAL)
        status, error = trader.lookup(account, order_id)
        if status in FINAL_STATUSES:
            break
    return status, error


def _explicitly_refused(exc: EtoroError) -> bool:
    """A 4xx answer (429 included: retries exhausted) means eToro did not take the order."""
    return exc.status is not None and 400 <= exc.status < 500


def _submit_buy(
    deps: Deps, trader: TradeClient, entry: dict[str, Any]
) -> tuple[int | None, str]:
    """Send the order inside the lock; record the outcome before the lock is released."""
    try:
        payload, api = trader.open_buy(entry)
    except EtoroError as exc:
        status = "rejected" if _explicitly_refused(exc) else "unknown"
        append_ledger(
            {"id": entry["id"], "status": status, "error": str(exc)}, deps.ledger
        )
        if status == "unknown":
            exc.hint = (
                "The order may or may not have reached eToro, so it was not sent again. It "
                "counts toward today's limits; run `etoro_trade.py reconcile` in a minute to "
                "find out, and never buy it again before that."
            )
        raise
    order_id = order_id_of(payload)
    append_ledger(
        {"id": entry["id"], "status": "submitted", "order_id": order_id, "api": api},
        deps.ledger,
    )
    return order_id, api


def log_refusal(deps: Deps, args: argparse.Namespace, exc: TradingRefused) -> None:
    """Record a refused buy for the dashboard; a write failure never hides the refusal."""
    row = {
        "id": str(uuid.uuid4()),
        "ts": deps.now().astimezone(UTC).isoformat(),
        "symbol": str(args.symbol).upper(),
        "amount": args.amount,
        "reason": args.reason,
        "kind": exc.kind,
        "refusal": str(exc),
        "user_requested": args.user_requested,
    }
    if exc.bucket:
        row["bucket"] = exc.bucket
    try:
        append_jsonl(refused_path(deps.kronos_dir()), row)
    except OSError as err:
        print(f"could not log the refused buy: {err}", file=sys.stderr)


def cmd_buy(args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    try:
        return _buy(args, deps)
    except TradingRefused as exc:
        if not args.dry_run:
            log_refusal(deps, args, exc)
        raise


@dataclass
class BucketGate:
    """Which bucket a buy belongs to and whether its switch and caps let it through.

    Before any request the user's own lists (meme symbols, crypto watchlist) give a hint and
    that bucket is checked; an unlisted symbol is checked as a stock. Once eToro has named the
    instrument the real bucket is checked too. A stock-limit refusal of an unlisted symbol waits
    for that answer while crypto trading is on, so a crypto buy is never refused by the stock
    caps it does not count against.
    """

    trading: TradingConfig
    crypto: CryptoConfig
    amount: float
    symbol: str
    hint: str | None = field(init=False, default=None)
    deferred: TradingRefused | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.hint = hint_bucket(self.symbol, self.crypto)

    def enforce(self, bucket: str, deps: Deps) -> dict[str, Any]:
        try:
            require_bucket_enabled(bucket, self.crypto)
            return check_bucket_limits(
                self.trading,
                self.crypto,
                bucket,
                self.amount,
                ledger_for_limits(deps.ledger),
                deps.now(),
            )
        except TradingRefused as exc:
            exc.bucket = bucket
            raise

    def precheck(self, deps: Deps) -> None:
        try:
            self.enforce(self.hint or STOCK, deps)
        except TradingRefused as exc:
            if self.hint is not None or not self.crypto.enabled:
                raise
            self.deferred = exc

    def settle(self, bucket: str, deps: Deps) -> None:
        if bucket == (self.hint or STOCK) and self.deferred is not None:
            raise self.deferred
        if bucket != (self.hint or STOCK):
            self.enforce(bucket, deps)


def resolve_instrument(
    reader: EtoroClient, symbol: str, crypto: CryptoConfig
) -> dict[str, Any]:
    """eToro's exact instrument for *symbol*; a meme coin eToro does not list is a refusal."""
    items = reader.search(symbol)
    try:
        return pick_exact(items, symbol)
    except EtoroError:
        if not is_meme(symbol, crypto):
            raise
    refusal = CryptoRefused(
        f"eToro does not list the meme coin {symbol} under that exact symbol (search "
        f"returned: {search_candidates(items)}); nothing was bought.",
        hint="Use the exact eToro symbol from `etoro_data.py search` (some coins are listed "
        "per million units, e.g. SHIBxM). Tell the user if eToro does not offer the coin.",
    )
    refusal.bucket = MEME
    raise refusal


def _local_checks(args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    """The guards after the limits that need no network, most useful refusal first."""
    track_record = check_lessons(
        args.symbol,
        forecasts_path(deps.kronos_dir()),
        user_requested=args.user_requested,
    )
    backtest = check_backtest(
        args.symbol,
        backtests_path(deps.kronos_dir()),
        deps.now(),
        user_requested=args.user_requested,
    )
    check_protection(args.stop, args.target, user_requested=args.user_requested)
    return {"track_record": track_record, "backtest": backtest}


def _market_checks(
    args: argparse.Namespace, deps: Deps, reader: EtoroClient, gate: BucketGate
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """(instrument, market, bucket) after the read-only checks: the instrument's bucket with
    its switch and caps, then tradable, open, fresh price, levels."""
    instrument = resolve_instrument(reader, args.symbol, gate.crypto)
    snapshot = market_snapshot(reader, int(instrument["instrumentId"]))
    names = (args.symbol, str(instrument.get("internalSymbolFull") or ""))
    bucket = classify(names, instrument, snapshot["trades_weekends"], gate.crypto)
    gate.settle(bucket, deps)
    try:
        market = check_market(args.symbol, instrument, snapshot, deps.now())
        check_price_levels(args.stop, args.target, market["price"])
        rules = bucket_rules(bucket, gate.trading, gate.crypto)
        check_stop_rule(args.stop, market["price"], rules.stop_pct)
    except TradingRefused as exc:
        exc.bucket = bucket
        raise
    return instrument, market, bucket


def _buy(args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    if args.trailing and args.stop is None:
        raise TradingRefused("--trailing needs --stop: it is where the trailing stop starts.")
    config = load_trading_config(deps.config_path)
    require_enabled(config)
    amount = round(float(args.amount), 2)
    gate = BucketGate(config, load_crypto_config(deps.config_path), amount, args.symbol)
    gate.precheck(deps)
    try:
        checks = _local_checks(args, deps)
    except TradingRefused as exc:
        exc.bucket = gate.hint
        raise
    reader, trader = deps.clients()
    instrument, market, bucket = _market_checks(args, deps, reader, gate)
    entry = {
        "id": str(uuid.uuid4()),  # also the v2 order's x-request-id (its lookup handle)
        "legacy_request_id": str(uuid.uuid4()),
        "ts": deps.now().astimezone(UTC).isoformat(),
        "action": "open",
        "account": config.account,
        "symbol": instrument.get("internalSymbolFull") or args.symbol,
        "instrument_id": int(instrument["instrumentId"]),
        "amount": amount,
        "leverage": 1,
        "stop_loss": args.stop,
        "trailing_stop": args.trailing,
        "take_profit": args.target,
        "reason": args.reason,
        "user_requested": args.user_requested,
        "bucket": bucket,
        **checks,
        "market": market,
    }
    if args.dry_run:
        return {"ok": True, "dry_run": True, "would_buy": entry}
    with deps.lock():
        limits = gate.enforce(bucket, deps)
        append_ledger({**entry, "status": "submitting"}, deps.ledger)
        order_id, api = _submit_buy(deps, trader, entry)
    status, error = "submitted", None
    if order_id is not None:
        status, error = _poll(trader, config.account, order_id, deps.sleep)
        append_ledger(
            {"id": entry["id"], "status": status, "error": error}, deps.ledger
        )
    return {
        "ok": status not in {"rejected", "canceled", "expired"},
        "order": {**entry, "order_id": order_id, "status": status, "api": api},
        "error": error,
        "limits": limits,
        "disclaimer": "Automated order inside the user's limits; not financial advice.",
    }


def _find_position(portfolio: Mapping[str, Any], position_id: int) -> dict[str, Any]:
    for pos in portfolio.get("positions") or []:
        if isinstance(pos, dict) and str(pos.get("positionID")) == str(position_id):
            return pos
    raise TradingRefused(
        f"No open position {position_id} in the account.",
        hint="List them with `etoro_trade.py positions`.",
    )


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close_economics(
    position: Mapping[str, Any], units: float | None, held: float
) -> dict[str, Any]:
    """Invested USD and P&L of the closed part, from the last valuation before the close."""
    share = units / held if units is not None and held else 1.0
    pnl = position.get("unrealizedPnL")
    pnl_value = _number(pnl.get("pnL")) if isinstance(pnl, dict) else None
    invested = _number(position.get("amount"))
    return {
        "open_rate": _number(position.get("openRate")),
        "invested_usd": round(invested * share, 2) if invested is not None else None,
        "pnl_usd": round(pnl_value * share, 2) if pnl_value is not None else None,
    }


def _symbol_from_ledger(
    entries: list[dict[str, Any]], instrument_id: int
) -> str | None:
    for entry in reversed(entries):
        if entry.get("instrument_id") == instrument_id and entry.get("symbol"):
            return str(entry["symbol"])
    return None


def cmd_close(args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    config = load_trading_config(deps.config_path)
    require_enabled(config)
    reader, trader = deps.clients()
    portfolio, _path = reader.portfolio(config.account)
    position = _find_position(portfolio, args.position_id)
    held = float(position.get("units") or 0.0)
    units = args.units
    if units is not None and not 0 < units <= held:
        raise TradingRefused(f"--units must be above 0 and at most {held}.")
    instrument_id = int(position.get("instrumentID") or 0)
    entry = {
        "id": str(uuid.uuid4()),
        "ts": deps.now().astimezone(UTC).isoformat(),
        "action": "close",
        "account": config.account,
        "position_id": int(args.position_id),
        "instrument_id": instrument_id,
        "symbol": _symbol_from_ledger(read_ledger(deps.ledger), instrument_id),
        "units": units if units is not None else "all",
        **_close_economics(position, units, held),
        "reason": args.reason,
    }
    if args.dry_run:
        return {"ok": True, "dry_run": True, "would_close": entry}
    with deps.lock():
        append_ledger({**entry, "status": "submitting"}, deps.ledger)
        try:
            payload = trader.close_position(
                config.account, entry["position_id"], entry["instrument_id"], units
            )
        except EtoroError as exc:
            in_doubt = not _explicitly_refused(exc)
            append_ledger(
                {
                    "id": entry["id"],
                    "status": "failed",
                    "in_doubt": in_doubt,
                    "error": str(exc),
                },
                deps.ledger,
            )
            if in_doubt:
                exc.hint = (
                    "The close may or may not have reached eToro, so it was not sent again. "
                    "Check `etoro_trade.py positions` in a minute before closing again: a "
                    "repeated partial close would sell twice."
                )
            raise
        order_id = order_id_of(payload)
        append_ledger(
            {"id": entry["id"], "status": "submitted", "order_id": order_id},
            deps.ledger,
        )
    return {
        "ok": True,
        "close": {**entry, "order_id": order_id, "status": "submitted"},
        "note": "eToro fills the close asynchronously; confirm with `etoro_trade.py positions`. "
        "pnl_usd is estimated from the last valuation before the close.",
    }


def _current_rate(position: Mapping[str, Any]) -> float | None:
    """The long position's current rate, from its open rate and unrealized P&L (leverage 1)."""
    open_rate = _number(position.get("openRate"))
    pnl = position.get("unrealizedPnL")
    pnl_value = _number(pnl.get("pnL")) if isinstance(pnl, dict) else None
    invested = _number(position.get("amount"))
    if not open_rate or pnl_value is None or not invested:
        return None
    return open_rate * (1 + pnl_value / invested)


def _check_protection(
    position: Mapping[str, Any], stop: float, target: float | None
) -> None:
    """A stop at or above the price would close the position at once; refuse it."""
    if position.get("isBuy") is False:
        raise TradingRefused("Only long positions are supported.")
    if stop <= 0:
        raise TradingRefused("--stop must be above 0.")
    current = _current_rate(position)
    if current is not None and stop >= current:
        raise TradingRefused(
            f"--stop {stop} is not below the current price (~{current:.4g}): eToro would close "
            "the position at once.",
            hint="Use a stop under the price, e.g. from kronos_risk.py.",
        )
    if target is not None and target <= max(stop, current or 0):
        raise TradingRefused("--target must be above the current price and the stop.")


def cmd_set_stop(args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    """Put a broker-side stop-loss on an open position, so eToro closes it even between runs."""
    config = load_trading_config(deps.config_path)
    require_enabled(config)
    reader, trader = deps.clients()
    portfolio, _path = reader.portfolio(config.account)
    position = _find_position(portfolio, args.position_id)
    _check_protection(position, args.stop, args.target)
    instrument_id = int(position.get("instrumentID") or 0)
    entry = {
        "id": str(uuid.uuid4()),
        "ts": deps.now().astimezone(UTC).isoformat(),
        "action": "protect",
        "account": config.account,
        "position_id": int(args.position_id),
        "instrument_id": instrument_id,
        "symbol": _symbol_from_ledger(read_ledger(deps.ledger), instrument_id),
        "stop_loss": args.stop,
        "trailing_stop": args.trailing,
        "take_profit": args.target,
        "previous_stop_loss": _number(position.get("stopLossRate")),
        "reason": args.reason,
    }
    if args.dry_run:
        return {"ok": True, "dry_run": True, "would_protect": entry}
    with deps.lock():
        try:
            trader.set_protection(
                config.account,
                entry["position_id"],
                args.stop,
                args.target,
                trailing=args.trailing,
            )
        except EtoroError as exc:
            append_ledger({**entry, "status": "failed", "error": str(exc)}, deps.ledger)
            raise
        append_ledger({**entry, "status": "submitted"}, deps.ledger)
    return {
        "ok": True,
        "protect": {**entry, "status": "submitted"},
        "note": "eToro applies the change asynchronously; confirm the stop_loss with "
        "`etoro_trade.py positions --format json`.",
    }


# ── Reconcile buys whose outcome is unknown (read-only: never places an order) ──


def _row_matches(row: Any, entry: Mapping[str, Any], order_id: int | None) -> bool:
    """A portfolio position or pending order that is this buy: same order id, or same
    instrument opened from shortly before the buy on, for the same amount."""
    if not isinstance(row, dict) or row.get("mirrorID"):
        return False
    if int(row.get("instrumentID") or 0) != int(entry.get("instrument_id") or -1):
        return False
    if order_id is not None and str(row.get("orderID")) == str(order_id):
        return True
    try:
        opened = parse_timestamp(row["openDateTime"])
        since = parse_timestamp(entry["ts"]) - RECONCILE_TIME_SLACK
        amount, wanted = float(row.get("amount") or 0.0), float(entry["amount"])
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return False
    return opened >= since and abs(amount - wanted) <= max(0.01, 0.01 * wanted)


def _landed_where(
    portfolio: Mapping[str, Any], entry: Mapping[str, Any], order_id: int | None
) -> str | None:
    for key, where in (("positions", "filled"), ("ordersForOpen", "placed")):
        if any(_row_matches(r, entry, order_id) for r in portfolio.get(key) or []):
            return where
    return None


def _reconciled_status(lookup: str | None, landed: str | None) -> tuple[str, str]:
    """(new ledger status, plain explanation). Never a status that stops counting."""
    if landed:
        return landed, f"found in the eToro portfolio ({landed})"
    if lookup in LANDED:
        return lookup, f"eToro's order lookup says {lookup}"
    note = f"eToro's order lookup says {lookup}" if lookup else "no order lookup answer"
    return "not_found", (
        f"not in the portfolio and {note}: it most likely never went through. It keeps "
        "counting toward that day's limits; tell the user and buy it again only if they ask."
    )


def _reconcile_entry(
    entry: dict[str, Any],
    portfolio: Mapping[str, Any],
    trader: TradeClient,
    now: datetime,
) -> dict[str, Any] | None:
    """The ledger update for one in-doubt buy, or None while it is too recent to judge."""
    try:
        age = now.astimezone(UTC).replace(tzinfo=None) - parse_timestamp(entry["ts"])
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        age = RECONCILE_MIN_AGE
    if age < RECONCILE_MIN_AGE:
        return None
    lookup, order_id = None, entry.get("order_id")
    for reference in (entry.get("id"), entry.get("legacy_request_id")):
        if reference and lookup is None:
            lookup, _error, found_id = trader.order_status(
                entry["account"], {"referenceId": reference}
            )
            order_id = order_id or found_id
    status, note = _reconciled_status(lookup, _landed_where(portfolio, entry, order_id))
    return {
        "id": entry["id"],
        "status": status,
        "order_id": order_id,
        "reconciled_at": iso_z(now),
        "reconcile_note": note,
    }


def _drop_closed_positions(
    deps: Deps, account: str, portfolio: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Log ``flat`` for instruments eToro no longer holds (stop, target or app close)."""
    rows = flat_rows(read_ledger(deps.ledger), account, portfolio, deps.now())
    for row in rows:
        append_ledger(row, deps.ledger)
    return [
        {k: row[k] for k in ("symbol", "bucket", "instrument_id", "positions")}
        for row in rows
    ]


def cmd_reconcile(_args: argparse.Namespace, deps: Deps) -> dict[str, Any]:
    """Settle buys logged ``unknown`` (or left ``submitting``) from eToro's own records, and
    stop counting positions eToro has closed on its own."""
    config = load_trading_config(deps.config_path)
    results, waiting, closed = [], [], []
    with deps.lock():  # no buy can be half-logged while the ledger is read and updated
        entries = read_ledger(deps.ledger)
        doubtful = [
            e
            for e in entries
            if e.get("action") == "open"
            and e.get("account") == config.account
            and e.get("status") in IN_DOUBT
        ]
        held = any(h.count for h in holdings(entries, config.account).values())
        if doubtful or held:
            reader, trader = deps.clients()
            portfolio, _path = reader.portfolio(config.account)
        for entry in doubtful:
            update = _reconcile_entry(entry, portfolio, trader, deps.now())
            if update is None:
                waiting.append(entry["id"])
                continue
            append_ledger(update, deps.ledger)
            results.append({"symbol": entry.get("symbol"), **update})
        if doubtful or held:
            closed = _drop_closed_positions(deps, config.account, portfolio)
    return {
        "ok": True,
        "account": config.account,
        "reconciled": results,
        "too_recent": waiting,
        "closed_on_etoro": closed,
        "note": "Read-only: nothing was bought or sold. Every one of these buys keeps counting "
        "toward the limits of the day it was sent; closed_on_etoro lists positions eToro "
        "closed by itself (stop-loss, take-profit or the app), which no longer count toward "
        "the maximum of open positions.",
    }


def _positions_table(result: dict[str, Any]) -> str:
    headers = [
        "position_id",
        "symbol",
        "direction",
        "units",
        "invested_usd",
        "unrealized_pnl",
    ]
    rows = [[row.get(h) for h in headers] for row in result["positions"]]
    return render_table(headers, rows) if rows else "No open positions."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="trading settings and today's usage (no network)")
    positions = sub.add_parser("positions", help="open positions with their ids")
    positions.add_argument("--format", choices=("json", "table"), default="table")
    buy = sub.add_parser("buy", help="market buy by USD amount (long, leverage 1)")
    buy.add_argument("symbol")
    buy.add_argument("--amount", type=float, required=True, help="USD to invest")
    buy.add_argument("--reason", required=True, help="why, for the trade log")
    buy.add_argument(
        "--stop",
        type=float,
        default=None,
        metavar="RATE",
        help="stop-loss price sent with the order (kronos_risk.py stop_loss); required for "
        "automatic buys",
    )
    buy.add_argument(
        "--target",
        type=float,
        default=None,
        metavar="RATE",
        help="take-profit price sent with the order (kronos_risk.py take_profit)",
    )
    buy.add_argument(
        "--trailing",
        action="store_true",
        help="trailing stop: starts at --stop and eToro raises it as the price rises",
    )
    buy.add_argument(
        "--user-requested",
        action="store_true",
        help="the user explicitly asked for this exact buy: skip the lesson and backtest "
        "checks and allow it without --stop (limits, market hours and price checks still "
        "apply). Never set it for an automatic decision.",
    )
    buy.add_argument("--dry-run", action="store_true")
    close = sub.add_parser("close", help="close a position (all units unless --units)")
    close.add_argument("position_id", type=int)
    close.add_argument("--units", type=float, default=None)
    close.add_argument("--reason", required=True, help="why, for the trade log")
    close.add_argument("--dry-run", action="store_true")
    protect = sub.add_parser(
        "set-stop",
        help="put a broker-side stop-loss (and take-profit) on an open position",
    )
    protect.add_argument("position_id", type=int)
    protect.add_argument("--stop", type=float, required=True, metavar="RATE")
    protect.add_argument("--target", type=float, default=None, metavar="RATE")
    protect.add_argument(
        "--trailing",
        action="store_true",
        help="trailing stop: starts at --stop and eToro raises it as the price rises",
    )
    protect.add_argument("--reason", required=True, help="why, for the trade log")
    protect.add_argument("--dry-run", action="store_true")
    sub.add_parser(
        "reconcile",
        help="settle buys whose outcome is unknown from eToro's order lookup and portfolio "
        "(read-only)",
    )
    return parser


COMMANDS = {
    "status": cmd_status,
    "positions": cmd_positions,
    "buy": cmd_buy,
    "close": cmd_close,
    "set-stop": cmd_set_stop,
    "reconcile": cmd_reconcile,
}
WRITES_LEDGER = {"buy", "close", "set-stop", "reconcile"}


def main(argv: list[str] | None = None, deps: Deps | None = None) -> int:
    args = build_parser().parse_args(argv)
    deps = deps or Deps()
    try:
        result = COMMANDS[args.command](args, deps)
    finally:
        if args.command in WRITES_LEDGER and not getattr(args, "dry_run", False):
            deps.refresh_dashboard()  # best effort; also after a refused or failed order
    if args.command == "positions" and args.format == "table":
        print(_positions_table(result))
    else:
        print(dump_json(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(run_cli(main))
