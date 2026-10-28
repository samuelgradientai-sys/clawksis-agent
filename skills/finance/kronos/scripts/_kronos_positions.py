"""Open positions per bucket and each bucket's stop rule, for Kronos trading.

Positions are counted from the trade ledger (``trades.jsonl``), per account and instrument, in
the order its rows were written:

- a buy that may have spent money opens one: ``filled``/``placed``, but also ``submitting``,
  ``unknown`` and ``not_found`` (fail closed, as for the daily caps);
- a ``close`` of all units that eToro took (not ``failed``, not left ``submitting``) closes one;
  a partial close closes none;
- a ``flat`` row closes them all. ``etoro_trade.py reconcile`` writes it when eToro's portfolio
  has no position or pending order of the instrument left (its stop-loss or take-profit hit, or
  the user closed it in the app) and no counted buy of it is under a minute old.

Every bucket counts only its own positions (a meme coin does not take a crypto slot), unlike
the daily caps, where meme buys also count as crypto. Rows without a bucket are stocks.

Stop rule per bucket: ``stop_pct`` 0 keeps the ATR stop (``ATR_MULT`` ATRs below the entry, the
stock default); above 0 the stop is ``entry x (1 - stop_pct / 100)``. It is capped at
``MAX_STOP_PCT``, the farthest stop ``etoro_trade.py`` accepts.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from _kronos_common import UTC, parse_timestamp
from _kronos_crypto import CRYPTO, MEME, STOCK, bucket_of

# Buy statuses where no money moved: they open no position and do not count toward the daily
# limits. Every other status counts, including "unknown" and the "not_found" a reconcile gives it.
NOT_COUNTED = frozenset({"rejected", "canceled", "expired", "dry_run"})
# A close that eToro refused or whose outcome is unknown may not have closed anything.
CLOSE_NOT_DONE = frozenset({"failed", "submitting"})
FLAT = "flat"  # ledger action: eToro holds nothing of the instrument any more
FLAT_MIN_AGE = timedelta(seconds=60)  # fills and the cached portfolio lag behind a buy
MAX_STOP_PCT = 50.0
ATR_MULT = 2.0
# Room for the price to move between sizing a buy and placing it, in percentage points.
STOP_PCT_SLACK = 1.0


@dataclass(frozen=True)
class BucketRules:
    bucket: str
    max_positions: int
    stop_pct: float  # 0 = ATR stop


def bucket_rules(bucket: str, trading: Any, crypto: Any) -> BucketRules:
    """*trading* is a TradingConfig; *crypto* a CryptoConfig, read only for crypto buckets."""
    if bucket == MEME:
        return BucketRules(MEME, crypto.meme_max_positions, crypto.meme_stop_pct)
    if bucket == CRYPTO:
        return BucketRules(CRYPTO, crypto.max_positions, crypto.stop_pct)
    return BucketRules(STOCK, trading.max_positions, trading.stop_pct)


def parse_stop_pct(value: Any) -> float | None:
    """A stop percentage from 0 to MAX_STOP_PCT; None when the value is not one."""
    try:
        pct = float(str(value).strip())
    except (TypeError, ValueError, OverflowError):
        return None
    return pct if math.isfinite(pct) and 0 <= pct <= MAX_STOP_PCT else None


def fixed_stop(entry: float, stop_pct: float) -> float:
    return round(entry * (1 - stop_pct / 100.0), 6)


def stop_rule(stop_pct: float) -> dict[str, Any]:
    if stop_pct > 0:
        return {"kind": "fixed_pct", "stop_pct": stop_pct}
    return {"kind": "atr", "atr_mult": ATR_MULT}


def widest_stop(price: float, stop_pct: float) -> float | None:
    """The lowest stop a fixed *stop_pct* allows at *price* (with STOP_PCT_SLACK); None = ATR."""
    if stop_pct <= 0:
        return None
    return price * (1 - min(stop_pct + STOP_PCT_SLACK, MAX_STOP_PCT) / 100.0)


@dataclass
class Holding:
    count: int = 0
    bucket: str = STOCK
    symbol: str | None = None
    last_open: str = ""


def holdings(entries: Iterable[Mapping[str, Any]], account: str) -> dict[Any, Holding]:
    """Open positions per instrument id on *account*, from ledger rows in written order. A buy
    logged without an instrument id stays open on its own key: nothing can close it."""
    held: dict[Any, Holding] = {}
    for entry in entries:
        if entry.get("account") != account:
            continue
        action = entry.get("action")
        key = entry.get("instrument_id")
        if key is None:
            if action != "open":
                continue
            key = ("row", entry.get("id"))
        holding = held.setdefault(key, Holding())
        if action == "open" and entry.get("status") not in NOT_COUNTED:
            holding.count += 1
            holding.bucket = bucket_of(entry)
            holding.symbol = entry.get("symbol") or holding.symbol
            holding.last_open = str(entry.get("ts") or "")
        elif action == "close" and entry.get("units") == "all":
            if entry.get("status") not in CLOSE_NOT_DONE:
                holding.count = max(holding.count - 1, 0)
        elif action == FLAT:
            holding.count = 0
    return held


def open_positions(
    entries: Iterable[Mapping[str, Any]], account: str, bucket: str
) -> int:
    return sum(
        h.count for h in holdings(entries, account).values() if h.bucket == bucket
    )


def positions_usage(
    rules: BucketRules, entries: Iterable[Mapping[str, Any]], account: str
) -> dict[str, Any]:
    """Open positions of the bucket against its maximum, and its stop rule."""
    count = open_positions(entries, account, rules.bucket)
    return {
        "open": count,
        "max": rules.max_positions,
        "left": max(rules.max_positions - count, 0),
        "stop": stop_rule(rules.stop_pct),
    }


def _too_recent(ts: str, now: datetime) -> bool:
    try:
        age = now.astimezone(UTC).replace(tzinfo=None) - parse_timestamp(ts)
    except (TypeError, ValueError, OverflowError, OSError):
        return True  # fail closed: keep counting it
    return age < FLAT_MIN_AGE


def flat_rows(
    entries: Iterable[Mapping[str, Any]],
    account: str,
    portfolio: Mapping[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    """``flat`` ledger rows for instruments Kronos still counts but eToro no longer holds."""
    present = {
        str(row.get("instrumentID"))
        for key in ("positions", "ordersForOpen")
        for row in portfolio.get(key) or []
        if isinstance(row, dict)
    }
    rows = []
    for instrument, holding in holdings(entries, account).items():
        if holding.count <= 0 or isinstance(instrument, tuple):
            continue
        if str(instrument) in present:
            continue
        if _too_recent(holding.last_open, now):
            continue
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "ts": now.astimezone(UTC).isoformat(),
                "action": FLAT,
                "account": account,
                "instrument_id": instrument,
                "symbol": holding.symbol,
                "bucket": holding.bucket,
                "positions": holding.count,
                "note": "no position or pending order of it in the eToro portfolio any more "
                "(stop-loss or take-profit hit, or closed in the app); it no longer counts "
                "toward the open positions",
            }
        )
    return rows
