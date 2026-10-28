"""Crypto and meme-coin buckets for Kronos trading: settings, classification and caps.

Every buy belongs to one bucket, each with its own limits from config.yaml:

- ``stock``: everything that is not crypto (stocks, ETFs, indices...), capped by
  ``skills.config.kronos.trading.*`` exactly as before crypto had its own bucket.
- ``crypto``: needs ``kronos.crypto.enabled`` (off by default) and counts against
  ``kronos.crypto.max_order_usd`` / ``max_daily_usd`` / ``max_orders_per_day``.
- ``meme``: a crypto whose symbol is in ``kronos.crypto.meme.symbols``. It also needs
  ``kronos.crypto.meme.enabled`` (off by default), counts against the meme caps AND the crypto
  caps, and must be listed by eToro (the buy refuses symbols eToro's search does not know).

Classification fails closed: eToro's ``instrumentTypeID`` 10 (cryptocurrencies) or, when eToro
did not send a type, Saturday trading in the price history marks crypto; a symbol on the meme
list is a meme coin whatever eToro calls it. Ledger rows written before the buckets existed have
no ``bucket`` and count as ``stock``, as they always did.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from _kronos_common import SkillError

STOCK, CRYPTO, MEME = "stock", "crypto", "meme"
BUCKETS = (STOCK, CRYPTO, MEME)
# eToro instrument types (instrumentTypeID): 1 currencies, 2 commodities, 4 indices, 5 stocks,
# 6 ETFs, 10 cryptocurrencies. See references/etoro-api.md.
CRYPTO_TYPE_ID = 10
DEFAULT_MEME_SYMBOLS = ("DOGE", "SHIB", "PEPE", "BONK", "FLOKI", "WIF")
# eToro lists some low-priced coins per million units (SHIB as SHIBxM); the meme list matches
# both spellings so the suffix can never route a meme coin into the plain crypto bucket.
_PER_MILLION_SUFFIX = "XM"
SET_CMD = "clawk config set skills.config.kronos.crypto"


class CryptoConfigError(SkillError):
    """A kronos.crypto.* value is not usable; callers refuse to trade crypto."""


@dataclass(frozen=True)
class CryptoConfig:
    enabled: bool
    max_order_usd: float
    max_daily_usd: float
    max_orders_per_day: int
    watchlist: tuple[str, ...]
    meme_enabled: bool
    meme_max_order_usd: float
    meme_max_daily_usd: float
    meme_symbols: tuple[str, ...]


CRYPTO_DEFAULTS = CryptoConfig(
    enabled=False,
    max_order_usd=50.0,
    max_daily_usd=150.0,
    max_orders_per_day=3,
    watchlist=(),
    meme_enabled=False,
    meme_max_order_usd=20.0,
    meme_max_daily_usd=50.0,
    meme_symbols=DEFAULT_MEME_SYMBOLS,
)


@dataclass(frozen=True)
class Cap:
    """One set of limits and the buckets whose buys count against it."""

    name: str  # stock | crypto | meme
    max_order_usd: float
    max_daily_usd: float
    max_orders_per_day: int | None
    counts: frozenset[str]


def parse_symbols(value: Any) -> tuple[str, ...]:
    """Upper-cased, de-duplicated symbols from "BTC, eth; SOL" or a YAML list."""
    if isinstance(value, (list, tuple)):
        value = ",".join(str(v) for v in value)
    seen: list[str] = []
    for token in re.split(r"[,\s;]+", "" if value is None else str(value)):
        symbol = token.strip().upper()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return tuple(seen)


def _bool(value: Any, key: str) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "1", "on"}:
        return True
    if text in {"false", "no", "0", "off", "", "none"}:
        return False
    raise CryptoConfigError(f"skills.config.kronos.crypto.{key} must be true or false.")


def _positive(value: Any, key: str, kind: type) -> Any:
    try:
        number = kind(float(str(value).strip()))
    except (TypeError, ValueError, OverflowError):
        number = None
    if number is None or number <= 0:
        raise CryptoConfigError(
            f"skills.config.kronos.crypto.{key} must be a positive number."
        )
    return number


def parse_crypto_config(section: Mapping[str, Any] | None) -> CryptoConfig:
    """The ``skills.config.kronos.crypto`` node as a CryptoConfig; defaults for what is unset."""
    raw = section if isinstance(section, Mapping) else {}
    meme = raw.get("meme") if isinstance(raw.get("meme"), Mapping) else {}
    d = CRYPTO_DEFAULTS
    symbols = meme.get("symbols")
    return CryptoConfig(
        enabled=_bool(raw.get("enabled", d.enabled), "enabled"),
        max_order_usd=_positive(
            raw.get("max_order_usd", d.max_order_usd), "max_order_usd", float
        ),
        max_daily_usd=_positive(
            raw.get("max_daily_usd", d.max_daily_usd), "max_daily_usd", float
        ),
        max_orders_per_day=_positive(
            raw.get("max_orders_per_day", d.max_orders_per_day),
            "max_orders_per_day",
            int,
        ),
        watchlist=parse_symbols(raw.get("watchlist")),
        meme_enabled=_bool(meme.get("enabled", d.meme_enabled), "meme.enabled"),
        meme_max_order_usd=_positive(
            meme.get("max_order_usd", d.meme_max_order_usd),
            "meme.max_order_usd",
            float,
        ),
        meme_max_daily_usd=_positive(
            meme.get("max_daily_usd", d.meme_max_daily_usd),
            "meme.max_daily_usd",
            float,
        ),
        meme_symbols=d.meme_symbols if symbols is None else parse_symbols(symbols),
    )


# ── Classification ──


def _spellings(symbol: str) -> set[str]:
    upper = str(symbol or "").strip().upper()
    names = {upper}
    if upper.endswith(_PER_MILLION_SUFFIX) and len(upper) > len(_PER_MILLION_SUFFIX):
        names.add(upper.removesuffix(_PER_MILLION_SUFFIX))
    return names


def is_meme(symbol: str, config: CryptoConfig) -> bool:
    listed = set(config.meme_symbols)
    return any(name in listed for name in _spellings(symbol))


def hint_bucket(symbol: str, config: CryptoConfig) -> str | None:
    """The bucket the user's own lists put *symbol* in before eToro is asked; None if unknown."""
    if is_meme(symbol, config):
        return MEME
    if _spellings(symbol) & set(config.watchlist):
        return CRYPTO
    return None


def _type_id(instrument: Mapping[str, Any]) -> int | None:
    try:
        return int(instrument.get("instrumentTypeID"))
    except (TypeError, ValueError):
        return None


def is_crypto_instrument(
    instrument: Mapping[str, Any], trades_weekends: bool | None
) -> bool:
    """eToro's instrument type when it sent one, else trading on Saturdays (fails closed)."""
    type_id = _type_id(instrument)
    if type_id is not None:
        return type_id == CRYPTO_TYPE_ID
    return bool(trades_weekends)


def classify(
    symbols: tuple[str, ...],
    instrument: Mapping[str, Any],
    trades_weekends: bool | None,
    config: CryptoConfig,
) -> str:
    """stock, crypto or meme for a resolved instrument; *symbols* = how it was asked for and
    how eToro spells it (a meme listing on either one wins)."""
    if any(is_meme(s, config) for s in symbols if s):
        return MEME
    return CRYPTO if is_crypto_instrument(instrument, trades_weekends) else STOCK


def bucket_of(entry: Mapping[str, Any]) -> str:
    bucket = entry.get("bucket")
    return bucket if bucket in BUCKETS else STOCK


# ── Caps ──


def caps_for(bucket: str, trading: Any, crypto: CryptoConfig | None) -> list[Cap]:
    """Every cap a buy in *bucket* must fit, its own first. *trading* is a TradingConfig
    (``trading.*``, the stock caps); *crypto* is only read for crypto and meme buckets."""
    if bucket == STOCK:
        return [
            Cap(
                STOCK,
                trading.max_order_usd,
                trading.max_daily_usd,
                trading.max_orders_per_day,
                frozenset({STOCK}),
            )
        ]
    crypto_cap = Cap(
        CRYPTO,
        crypto.max_order_usd,
        crypto.max_daily_usd,
        crypto.max_orders_per_day,
        frozenset({CRYPTO, MEME}),
    )
    if bucket != MEME:
        return [crypto_cap]
    meme_cap = Cap(
        MEME,
        crypto.meme_max_order_usd,
        crypto.meme_max_daily_usd,
        None,
        frozenset({MEME}),
    )
    return [meme_cap, crypto_cap]
