#!/usr/bin/env python3
"""Dashboard snapshot for the Kronos skill: what it bought, sold, refused and learned.

Writes ``$CLAWK_HOME/dashboards/kronos.json`` (contract version 1, rendered by the Clawksis web
dashboard): ``{"version": 1, "title", "subtitle", "updated_at", "panels": [...]}`` with stats,
table, list, chart and text panels. The write is atomic (temp file in the same directory, then
``os.replace``) and capped at 512 KiB. It reads only local files (config.yaml, the trade ledger,
the forecast journal, the lessons, the refusal log, the backtest verdicts and the strategy
replays), never the network. Labels follow ``display.language`` (Spanish when it starts with
"es", English otherwise).

``etoro_trade.py buy/close/reconcile``, ``kronos_review.py``, ``kronos_forecast.py``,
``kronos_backtest.py`` and ``kronos_strategy_backtest.py`` refresh it on their own (best
effort); run it by hand to rebuild the snapshot.

Usage:
  kronos_dashboard.py [--print]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from _kronos_common import (
    UTC,
    SkillError,
    clawk_home,
    dump_json,
    fold_rows,
    iso_z,
    kronos_home,
    read_jsonl,
    run_cli,
)
from _kronos_config import (
    ConfigError,
    display_language,
    goals,
    load_config,
    watchlist,
)
from _kronos_crypto import CRYPTO, MEME, STOCK, CryptoConfig, bucket_of, caps_for
from _kronos_dashboard_labels import LABELS, SCOPES, STATUS_ES
from _kronos_journal import (
    BACKTEST_MAX_AGE,
    MIN_MATURED,
    RECENT_WINDOW,
    backtests_path,
    forecasts_path,
    group_accuracy,
    read_backtests,
    read_forecasts,
    scored,
    strategy_path,
    symbol_key,
)
from _kronos_lessons import all_lessons, interval_label, lessons_path, money, render
from _kronos_positions import BucketRules, bucket_rules, positions_usage
from etoro_data import portfolio_history_path
from etoro_trade import (
    TradingConfig,
    cap_usage,
    ledger_path,
    load_crypto_config,
    load_trading_config,
    refused_path,
    usage_today,
)

VERSION = 1
MAX_BYTES = 512 * 1024
MAX_PANELS = 24
TABLE_ROWS = 50
FORECAST_ROWS = 60
CHART_POINTS = 500
OVERALL_WINDOW = 20
IN_FLIGHT = {"submitting", "submitted", "received", "placed", "unknown"}
STATUS_TONE = {
    "filled": "positive",
    "partially_filled": "positive",
    "rejected": "negative",
    "canceled": "negative",
    "expired": "negative",
    "failed": "negative",
    "unknown": "warning",
    "not_found": "warning",
}
VERDICT_TONE = {
    "adds_value": "positive",
    "worse_than_naive": "negative",
    "no_clear_edge": "warning",
}


def dashboard_path() -> Path:
    return clawk_home() / "dashboards" / "kronos.json"


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _plain_money(value: float) -> str:
    return f"${value:,.0f}" if float(value).is_integer() else f"${value:,.2f}"


# ── Inputs ──


@dataclass
class Inputs:
    """Everything the snapshot shows, read from disk once."""

    lang: str
    trading: TradingConfig | None
    config_error: str | None
    goals: dict[str, str]
    ledger: list[dict[str, Any]]
    records: list[dict[str, Any]]
    lessons: list[dict[str, Any]]
    refused: list[dict[str, Any]]
    backtests: list[dict[str, Any]]
    strategies: list[dict[str, Any]]
    key_check: dict[str, Any] | None = None
    crypto: CryptoConfig | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


def key_check_path(kronos_dir: Path | None = None) -> Path:
    """Where ``etoro_data.py check`` leaves the scopes it saw (no keys, no account data)."""
    return (kronos_dir or kronos_home()) / "etoro_key_check.json"


def _read_key_check(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_inputs(config_path: Path | None, kronos_dir: Path) -> Inputs:
    lang, trading, error, goal_values, crypto = "en", None, None, goals({}), None
    try:
        config = load_config(config_path)
        lang, goal_values = display_language(config), goals(config)
        trading = load_trading_config(config_path)
        crypto = load_crypto_config(config_path)
    except (ConfigError, SkillError) as exc:
        error = str(exc)
    return Inputs(
        lang=lang,
        trading=trading,
        config_error=error,
        goals=goal_values,
        ledger=fold_rows(read_jsonl(kronos_dir / ledger_path().name)),
        records=read_forecasts(forecasts_path(kronos_dir)),
        lessons=all_lessons(lessons_path(kronos_dir)),
        refused=read_jsonl(refused_path(kronos_dir)),
        backtests=read_backtests(backtests_path(kronos_dir)),
        strategies=read_jsonl(strategy_path(kronos_dir)),
        key_check=_read_key_check(key_check_path(kronos_dir)),
        crypto=crypto,
        history=read_jsonl(portfolio_history_path(kronos_dir)),
    )


# ── Panels ──


def _rate_tone(hit_rate: float, count: int) -> str:
    """Green from 55% right, red under 50%, once there are enough reviewed forecasts."""
    if count < MIN_MATURED or 0.5 <= hit_rate < 0.55:
        return "neutral"
    return "positive" if hit_rate >= 0.55 else "negative"


def _sign_tone(value: float | None) -> str:
    if not value:
        return "neutral"
    return "positive" if value > 0 else "negative"


def _hit_rate_item(inputs: Inputs, t: dict[str, str]) -> dict[str, Any]:
    recent = scored(inputs.records)[-OVERALL_WINDOW:]
    if not recent:
        return {"label": t["hit_rate"], "value": "—", "hint": t["no_reviews"]}
    hits = sum(bool(r["outcome"].get("direction_hit")) for r in recent)
    return {
        "label": t["hit_rate"],
        "value": f"{hits / len(recent) * 100:.0f}% ({hits}/{len(recent)})",
        "hint": t["hit_rate_hint"].format(n=len(recent)),
        "tone": _rate_tone(hits / len(recent), len(recent)),
    }


def _trading_items(inputs: Inputs, now: datetime, t: dict[str, str]) -> list[dict]:
    config = inputs.trading
    if config is None:
        return [
            {
                "label": t["trading"],
                "value": "?",
                "hint": t["config_error"],
                "tone": "warning",
            }
        ]
    count, spent = usage_today(inputs.ledger, config.account, now)
    return [
        {
            "label": t["account"],
            "value": config.account.capitalize(),
            "tone": "warning" if config.account == "real" else "neutral",
        },
        {
            "label": t["trading"],
            "value": t["on"] if config.enabled else t["off"],
            "tone": "positive" if config.enabled else "neutral",
        },
        {
            "label": t["buys_today"],
            "value": f"{count} / {config.max_orders_per_day}",
            "hint": t["stock_hint"],
            "tone": "warning" if count >= config.max_orders_per_day else "neutral",
        },
        {
            "label": t["spent_today"],
            "value": f"{_plain_money(spent)} / {_plain_money(config.max_daily_usd)}",
            "hint": t["stock_hint"],
            "tone": "warning" if spent >= 0.8 * config.max_daily_usd else "neutral",
        },
        *_bucket_items(
            bucket_rules(STOCK, config, None),
            inputs,
            ("positions", "stop_rule"),
            t,
            hint=t["positions_hint"],
        ),
        _crypto_summary_item(inputs, now, t),
    ]


def _stop_text(stop_pct: float, t: dict[str, str]) -> str:
    return (
        t["stop_fixed"].format(pct=f"{stop_pct:g}") if stop_pct > 0 else t["stop_atr"]
    )


def _bucket_items(
    rules: BucketRules,
    inputs: Inputs,
    labels: tuple[str, str],
    t: dict[str, str],
    hint: str | None = None,
) -> list[dict[str, Any]]:
    """A bucket's open positions against its maximum, and its stop rule."""
    usage = positions_usage(rules, inputs.ledger, inputs.trading.account)
    positions = {
        "label": t[labels[0]],
        "value": f"{usage['open']} / {usage['max']}",
        "tone": "warning" if usage["left"] == 0 else "neutral",
    }
    if hint:
        positions["hint"] = hint
    return [positions, {"label": t[labels[1]], "value": _stop_text(rules.stop_pct, t)}]


def _crypto_summary_item(inputs: Inputs, now: datetime, t: dict[str, str]) -> dict:
    """One line for the overview: crypto off, or what it spent today of its own cap."""
    crypto, config = inputs.crypto, inputs.trading
    if crypto is None or config is None or not crypto.enabled:
        return {"label": t["crypto_today"], "value": t["off"], "tone": "neutral"}
    (cap,) = caps_for(CRYPTO, config, crypto)
    spent = cap_usage(cap, config.account, inputs.ledger, now)["usd"]
    return {
        "label": t["crypto_today"],
        "value": f"{_plain_money(spent)} / {_plain_money(cap.max_daily_usd)}",
        "hint": t["crypto_today_hint"],
        "tone": "warning" if spent >= 0.8 * cap.max_daily_usd else "neutral",
    }


def _switch_item(label: str, on: bool, t: dict[str, str], tone_on: str) -> dict:
    return {
        "label": label,
        "value": t["on"] if on else t["off"],
        "tone": tone_on if on else "neutral",
    }


def _cap_items(
    cap: Any, usage: dict[str, Any], labels: tuple[str, str, str], t: dict[str, str]
) -> list[dict[str, Any]]:
    """Buys and USD spent today of one cap, with its per-order maximum as the hint."""
    buys_label, spent_label, order_label = labels
    return [
        {
            "label": t[buys_label],
            "value": f"{usage['buys']} / {cap.max_orders_per_day}",
            "tone": "warning" if usage["buys"] >= cap.max_orders_per_day else "neutral",
        },
        {
            "label": t[spent_label],
            "value": f"{_plain_money(usage['usd'])} / {_plain_money(cap.max_daily_usd)}",
            "hint": f"{t[order_label]}: {_plain_money(cap.max_order_usd)}",
            "tone": "warning" if usage["usd"] >= 0.8 * cap.max_daily_usd else "neutral",
        },
    ]


def crypto_panel(inputs: Inputs, now: datetime) -> dict[str, Any]:
    """Crypto and meme coins: their switches, their own caps and today's use of them."""
    t = LABELS[inputs.lang]
    panel: dict[str, Any] = {
        "id": "crypto",
        "type": "stats",
        "title": t["crypto"],
        "description": t["crypto_desc"],
        "width": "half",
    }
    crypto, config = inputs.crypto, inputs.trading
    if crypto is None or config is None:
        panel["items"] = [
            {
                "label": t["crypto_trading"],
                "value": "?",
                "hint": t["config_error"],
                "tone": "warning",
            }
        ]
        return panel
    meme_cap, crypto_cap = caps_for(MEME, config, crypto)
    usage = {
        cap.name: cap_usage(cap, config.account, inputs.ledger, now)
        for cap in (crypto_cap, meme_cap)
    }
    items = [_switch_item(t["crypto_trading"], crypto.enabled, t, "positive")]
    if crypto.enabled and not config.enabled:
        items[0]["hint"] = t["crypto_needs_trading"]
        items[0]["tone"] = "warning"
    items += _cap_items(
        crypto_cap,
        usage[CRYPTO],
        ("crypto_buys", "crypto_spent", "crypto_max_order"),
        t,
    )
    items += _bucket_items(
        bucket_rules(CRYPTO, config, crypto),
        inputs,
        ("crypto_positions", "crypto_stop"),
        t,
    )
    items.append(_switch_item(t["meme_trading"], crypto.meme_enabled, t, "warning"))
    items += _cap_items(
        meme_cap, usage[MEME], ("meme_buys", "meme_spent", "meme_max_order"), t
    )
    items += _bucket_items(
        bucket_rules(MEME, config, crypto),
        inputs,
        ("meme_positions", "meme_stop"),
        t,
    )
    items += [
        {
            "label": t["crypto_watchlist"],
            "value": ", ".join(crypto.watchlist) or "—",
        },
        {"label": t["meme_symbols"], "value": ", ".join(crypto.meme_symbols) or "—"},
    ]
    panel["items"] = items[:12]
    return panel


def summary_panel(inputs: Inputs, now: datetime) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    opens = [e for e in inputs.ledger if e.get("action") == "open"]
    in_flight = [e for e in opens if e.get("status") in IN_FLIGHT]
    pnls = [
        _num(e.get("pnl_usd"))
        for e in inputs.ledger
        if e.get("action") == "close" and e.get("status") != "failed"
    ]
    known = [p for p in pnls if p is not None]
    items = _trading_items(inputs, now, t)
    items.append(
        {
            "label": t["in_flight"],
            "value": len(in_flight),
            "hint": t["in_flight_hint"],
            "tone": "warning"
            if any(e.get("status") == "unknown" for e in in_flight)
            else "neutral",
        }
    )
    items.append(_hit_rate_item(inputs, t))
    if known:
        total = round(sum(known), 2)
        items.append(
            {"label": t["realized"], "value": money(total), "tone": _sign_tone(total)}
        )
    items.append(
        {
            "label": t["lessons_count"],
            "value": sum(1 for lesson in inputs.lessons if lesson.get("active")),
        }
    )
    return {
        "id": "summary",
        "type": "stats",
        "title": t["summary"],
        "items": items[:12],
    }


def goals_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    values = {**inputs.goals, "watchlist": ", ".join(watchlist(inputs.goals))}
    items = [
        {"label": t[key], "value": values.get(key) or "—"}
        for key in ("watchlist", "objective", "risk", "horizon", "schedule")
    ]
    panel: dict[str, Any] = {
        "id": "goals",
        "type": "stats",
        "title": t["goals"],
        "width": "half",
        "items": items,
    }
    if not inputs.goals.get("watchlist"):
        panel["description"] = t["goals_unset"]
    return panel


_TONE_ORDER = {"negative": 0, "warning": 1, "neutral": 2}


def key_panel(inputs: Inputs) -> dict[str, Any]:
    """The scopes the eToro key pair carries, riskiest first; read-only by design."""
    t = LABELS[inputs.lang]
    check = inputs.key_check or {}
    scopes = check.get("scopes") if isinstance(check.get("scopes"), list) else []
    items = []
    for scope in scopes:
        name = str(scope).strip()
        short = name.removeprefix("etoro-public:")
        tone, text = SCOPES.get(short, ("neutral", {}))
        items.append(
            {
                "title": text.get(inputs.lang) or t["key_unknown"],
                "body": name,
                "tone": tone,
            }
        )
    items.sort(key=lambda item: (_TONE_ORDER.get(item["tone"], 3), item["body"]))
    panel: dict[str, Any] = {
        "id": "etoro_key",
        "type": "list",
        "title": t["key"],
        "width": "half",
        "items": items[:60],
        "empty": t["key_empty"],
    }
    checked = (iso_z(check.get("checked_at")) or "")[:16].replace("T", " ")
    if checked:
        panel["description"] = t["key_desc"].format(when=checked)
    return panel


def _lesson_item(lesson: dict[str, Any], lang: str, t: dict[str, str]) -> dict:
    head = " ".join(
        part
        for part in (
            str(lesson.get("symbol") or ""),
            interval_label(str(lesson.get("interval") or ""), lang),
        )
        if part
    )
    kind = t.get(str(lesson.get("kind")), str(lesson.get("kind") or ""))
    stamp = (iso_z(lesson.get("updated_at")) or "")[:16].replace("T", " ")
    active = bool(lesson.get("active"))
    return {
        "title": f"{head} · {kind}" if head else kind,
        "body": _text(render(lesson, lang), 400),
        "meta": f"{t['updated'] if active else t['resolved']} {stamp} UTC".strip(),
        "tone": str(lesson.get("tone") or "neutral") if active else "neutral",
    }


def lessons_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    by_recency = sorted(
        inputs.lessons, key=lambda r: str(r.get("updated_at") or ""), reverse=True
    )
    active = [lesson for lesson in by_recency if lesson.get("active")]
    resolved = [lesson for lesson in by_recency if not lesson.get("active")][:10]
    return {
        "id": "lessons",
        "type": "list",
        "title": t["lessons"],
        "description": t["lessons_desc"],
        "width": "half",
        "items": [_lesson_item(r, inputs.lang, t) for r in (active + resolved)[:100]],
        "empty": t["lessons_empty"],
    }


def _status(value: Any, lang: str) -> str:
    status = str(value or "")
    return STATUS_ES.get(status, status) if lang == "es" else status


def _col(
    key: str, label: str, fmt: str = "text", align: str | None = None
) -> dict[str, str]:
    """A table column; numeric formats are right-aligned."""
    column = {"key": key, "label": label}
    if fmt != "text":
        column["format"] = fmt
    if align or fmt in {"number", "money", "percent"}:
        column["align"] = align or "right"
    return column


def _price(value: Any) -> float | None:
    number = _num(value)
    return round(number, 4) if number is not None else None


def _asset(bucket: str | None, t: dict[str, str]) -> str | None:
    """Stock/ETF, Crypto or Meme coin; None when the bucket is unknown."""
    return t[f"asset_{bucket}"] if bucket in (STOCK, CRYPTO, MEME) else None


def bought_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    opens = [e for e in inputs.ledger if e.get("action") == "open"]
    rows = [
        {
            "time": iso_z(e.get("ts")),
            "symbol": e.get("symbol"),
            "asset": _asset(bucket_of(e), t),
            "amount": _num(e.get("amount")),
            "status": _status(e.get("status"), inputs.lang),
            "who": t["user"] if e.get("user_requested") else t["auto"],
            "reason": _text(e.get("reason")),
            "_tone": STATUS_TONE.get(str(e.get("status")), "neutral"),
        }
        for e in reversed(opens[-TABLE_ROWS:])
    ]
    return {
        "id": "bought",
        "type": "table",
        "title": t["bought"],
        "columns": [
            _col("time", t["time"], "datetime"),
            _col("symbol", t["symbol"]),
            _col("asset", t["asset"]),
            _col("amount", t["amount"], "money"),
            _col("status", t["status"]),
            _col("who", t["who"]),
            _col("reason", t["reason"]),
        ],
        "rows": rows,
        "empty": t["bought_empty"],
    }


def _close_row(
    entry: dict[str, Any],
    names: dict[Any, Any],
    buckets: dict[Any, str],
    t: dict[str, str],
) -> dict:
    pnl = _num(entry.get("pnl_usd"))
    units = entry.get("units")
    symbol = entry.get("symbol") or names.get(entry.get("instrument_id"))
    return {
        "time": iso_z(entry.get("ts")),
        "symbol": symbol or f"#{entry.get('instrument_id')}",
        "asset": _asset(buckets.get(entry.get("instrument_id")), t),
        "units": t["all_units"] if units == "all" else _num(units),
        "pnl": pnl,
        "reason": _text(entry.get("reason")),
        "_tone": _sign_tone(pnl),
    }


def _unique_closes(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Full closes, one per position: a second order to close a position already being
    closed (a retry while the market was shut) is not a second sale."""
    seen: set[Any] = set()
    closes = []
    for entry in ledger:
        if entry.get("action") != "close":
            continue
        position = entry.get("position_id")
        if entry.get("units") == "all" and position is not None:
            if position in seen:
                continue
            seen.add(position)
        closes.append(entry)
    return closes


def sold_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    opens = [e for e in inputs.ledger if e.get("action") == "open"]
    names = {e.get("instrument_id"): e.get("symbol") for e in opens if e.get("symbol")}
    # A close is in the bucket of the buys of the same instrument (positions bought in the
    # eToro app have no buy here and show no type).
    buckets = {e.get("instrument_id"): bucket_of(e) for e in opens}
    closes = _unique_closes(inputs.ledger)
    return {
        "id": "sold",
        "type": "table",
        "title": t["sold"],
        "columns": [
            _col("time", t["time"], "datetime"),
            _col("symbol", t["symbol"]),
            _col("asset", t["asset"]),
            _col("units", t["units"], align="right"),
            _col("pnl", t["pnl"], "money"),
            _col("reason", t["reason"]),
        ],
        "rows": [
            _close_row(e, names, buckets, t) for e in reversed(closes[-TABLE_ROWS:])
        ],
        "empty": t["sold_empty"],
    }


def refused_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    rows = [
        {
            "time": iso_z(e.get("ts")),
            "symbol": e.get("symbol"),
            "asset": _asset(e.get("bucket"), t),
            "amount": _num(e.get("amount")),
            "kind": t.get(f"kind_{e.get('kind')}", t["kind_limit"]),
            "why": _text(e.get("refusal")),
            "_tone": "warning",
        }
        for e in reversed(inputs.refused[-TABLE_ROWS:])
    ]
    return {
        "id": "refused",
        "type": "table",
        "title": t["refused"],
        "description": t["refused_desc"],
        "columns": [
            _col("time", t["time"], "datetime"),
            _col("symbol", t["symbol"]),
            _col("asset", t["asset"]),
            _col("amount", t["amount"], "money"),
            _col("kind", t["kind"]),
            _col("why", t["why"]),
        ],
        "rows": rows,
        "empty": t["refused_empty"],
    }


def _rolling(rows: list[dict[str, Any]], window: int = RECENT_WINDOW) -> list[list]:
    points = []
    for index in range(len(rows)):
        chunk = rows[max(0, index - window + 1) : index + 1]
        if len(chunk) < 3:
            continue
        hits = sum(bool(r["outcome"].get("direction_hit")) for r in chunk)
        when = iso_z(rows[index]["outcome"].get("actual_timestamp"))
        if when:
            points.append([when, round(hits / len(chunk) * 100.0, 1)])
    return points[-CHART_POINTS:]


def _account_history(inputs: Inputs) -> list[dict[str, Any]]:
    account = inputs.trading.account if inputs.trading is not None else None
    return [
        row
        for row in inputs.history
        if account is None or row.get("account") in (None, account)
    ]


def portfolio_chart_panel(inputs: Inputs) -> dict[str, Any]:
    """Portfolio value (cash + invested + open P&L) at every recorded snapshot."""
    t = LABELS[inputs.lang]
    points = [
        [when, value]
        for row in _account_history(inputs)
        if (when := iso_z(row.get("ts"))) and (value := _num(row.get("equity_usd")))
    ]
    return {
        "id": "portfolio_chart",
        "type": "chart",
        "title": t["portfolio_chart"],
        "description": t["portfolio_desc"],
        "kind": "line",
        "x_label": t["time"],
        "y_label": t["portfolio_y"],
        "series": [{"name": t["portfolio_series"], "points": points[-CHART_POINTS:]}],
    }


def pnl_chart_panel(inputs: Inputs) -> dict[str, Any]:
    """Gain or loss per symbol: open positions from the latest snapshot, closed ones from
    the ledger's estimates."""
    t = LABELS[inputs.lang]
    history = _account_history(inputs)
    open_points = [
        [str(p.get("symbol")), round(pnl, 2)]
        for p in (history[-1].get("positions") or [] if history else [])
        if (pnl := _num(p.get("unrealized_pnl"))) is not None
    ]
    opens = [e for e in inputs.ledger if e.get("action") == "open"]
    names = {e.get("instrument_id"): e.get("symbol") for e in opens if e.get("symbol")}
    closed: dict[str, float] = {}
    for entry in _unique_closes(inputs.ledger):
        pnl = _num(entry.get("pnl_usd"))
        if pnl is None:
            continue
        symbol = entry.get("symbol") or names.get(entry.get("instrument_id"))
        key = str(symbol or f"#{entry.get('instrument_id')}")
        closed[key] = closed.get(key, 0.0) + pnl
    return {
        "id": "pnl_chart",
        "type": "chart",
        "title": t["pnl_chart"],
        "description": t["pnl_desc"],
        "kind": "bar",
        "x_label": t["symbol"],
        "y_label": t["pnl_y"],
        "series": [
            {"name": t["pnl_open"], "points": open_points},
            {
                "name": t["pnl_closed"],
                "points": [[k, round(v, 2)] for k, v in closed.items()],
            },
        ],
    }


def accuracy_chart_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    rows = scored(inputs.records)
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_symbol.setdefault(symbol_key(row.get("symbol")), []).append(row)
    series = [{"name": t["all_symbols"], "points": _rolling(rows)}]
    if len(by_symbol) > 1:
        busiest = sorted(by_symbol.items(), key=lambda kv: -len(kv[1]))[:3]
        series += [
            {"name": symbol, "points": _rolling(own)}
            for symbol, own in busiest
            if len(own) >= 3
        ]
    return {
        "id": "accuracy_chart",
        "type": "chart",
        "title": t["accuracy_chart"],
        "description": t["accuracy_desc"].format(n=RECENT_WINDOW),
        "kind": "line",
        "x_label": t["x_label"],
        "y_label": t["y_label"],
        "series": series[:4],
    }


def by_symbol_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    rows = [
        {
            "symbol": symbol,
            "interval": interval_label(interval, inputs.lang),
            "matured": s["matured"],
            "hit_rate": round(s["hit_rate"] * 100.0, 1),
            "beat_naive": round(s["beat_naive"] / s["matured"] * 100.0, 1),
            "mean_error": round(s["mean_error_pct"], 2),
            "_tone": _rate_tone(s["hit_rate"], s["matured"]),
        }
        for (symbol, interval), s in sorted(group_accuracy(inputs.records).items())
    ]
    return {
        "id": "accuracy_by_symbol",
        "type": "table",
        "title": t["by_symbol"],
        "columns": [
            _col("symbol", t["symbol"]),
            _col("interval", t["interval"]),
            _col("matured", t["matured"], "number"),
            _col("hit_rate", t["hit_rate"], "percent"),
            _col("beat_naive", t["beat_naive"], "percent"),
            _col("mean_error", t["mean_error"], "percent"),
        ],
        "rows": rows[:TABLE_ROWS],
        "empty": t["by_symbol_empty"],
    }


def _forecast_row(record: dict[str, Any], lang: str, t: dict[str, str]) -> dict:
    outcome = record.get("outcome") if isinstance(record.get("outcome"), dict) else {}
    result, tone = t["pending"], "neutral"
    if outcome:
        hit = bool(outcome.get("direction_hit"))
        result, tone = (t["hit"], "positive") if hit else (t["miss"], "negative")
    direction = str(record.get("direction") or "")
    error = _num(outcome.get("error_pct"))
    horizon = _num(record.get("horizon"))
    return {
        "made": iso_z(record.get("made_at")),
        "symbol": record.get("symbol"),
        "interval": interval_label(str(record.get("interval") or ""), lang),
        "horizon": int(horizon) if horizon is not None else None,
        "last": _price(record.get("last_close")),
        "predicted": _price(record.get("predicted_close")),
        "direction": t.get(direction, direction),
        "actual": _price(outcome.get("actual_close")),
        "error": round(error, 2) if error is not None else None,
        "result": result,
        "_tone": tone,
    }


def forecasts_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    recent = sorted(inputs.records, key=lambda r: str(r.get("made_at") or ""))
    return {
        "id": "forecasts",
        "type": "table",
        "title": t["forecasts"],
        "columns": [
            _col("made", t["made"], "datetime"),
            _col("symbol", t["symbol"]),
            _col("interval", t["interval"]),
            _col("horizon", t["horizon_bars"], "number"),
            _col("last", t["last"], "number"),
            _col("predicted", t["predicted"], "number"),
            _col("direction", t["direction"]),
            _col("actual", t["actual"], "number"),
            _col("error", t["error"], "percent"),
            _col("result", t["result"]),
        ],
        "rows": [
            _forecast_row(r, inputs.lang, t) for r in reversed(recent[-FORECAST_ROWS:])
        ],
        "empty": t["forecasts_empty"],
    }


def _latest(rows: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    """The newest row per combination of *keys*, newest first."""
    latest: dict[tuple, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: str(r.get("made_at") or "")):
        latest[tuple(str(row.get(k) or "") for k in keys)] = row
    return sorted(
        latest.values(), key=lambda r: str(r.get("made_at") or ""), reverse=True
    )


def _skill_pct(value: Any) -> float | None:
    number = _num(value)
    return round(number * 100.0, 1) if number is not None else None


def _backtest_row(row: dict[str, Any], now: datetime, t: dict[str, str]) -> dict:
    verdict = str(row.get("verdict") or "")
    made = iso_z(row.get("made_at"))
    fresh = False
    if made:
        age = now.astimezone(UTC).replace(tzinfo=None) - datetime.fromisoformat(
            made[:-1]
        )
        fresh = age <= BACKTEST_MAX_AGE
    return {
        "made": made,
        "symbol": row.get("symbol"),
        "interval": row.get("interval"),
        "origins": _num(row.get("origins")),
        "vs_naive": _skill_pct(row.get("mae_skill_vs_naive")),
        "vs_ets": _skill_pct(row.get("mae_skill_vs_ets")),
        "hit_rate": _skill_pct(row.get("hit_rate")),
        "verdict": t.get(f"verdict_{verdict}", verdict)
        + ("" if fresh else f" ({t['stale']})"),
        "_tone": VERDICT_TONE.get(verdict, "neutral") if fresh else "neutral",
    }


def backtests_panel(inputs: Inputs, now: datetime) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    rows = _latest(inputs.backtests, "symbol", "interval")
    return {
        "id": "backtests",
        "type": "table",
        "title": t["backtests"],
        "description": t["backtests_desc"],
        "columns": [
            _col("made", t["made"], "datetime"),
            _col("symbol", t["symbol"]),
            _col("interval", t["interval"]),
            _col("origins", t["origins"], "number"),
            _col("vs_naive", t["vs_naive"], "percent"),
            _col("vs_ets", t["vs_ets"], "percent"),
            _col("hit_rate", t["hit_rate"], "percent"),
            _col("verdict", t["verdict"]),
        ],
        "rows": [_backtest_row(r, now, t) for r in rows[:TABLE_ROWS]],
        "empty": t["backtests_empty"],
    }


def _benchmark_text(row: dict[str, Any]) -> str | None:
    bench = row.get("benchmark") if isinstance(row.get("benchmark"), dict) else None
    if not bench or _num(bench.get("cagr_pct")) is None:
        return None
    return f"{bench.get('symbol')} {float(bench['cagr_pct']):+.1f}%"


def _count(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _forecaster_label(row: dict[str, Any]) -> str:
    """'ETS (AutoETS)', 'ETS (built-in)' or the Kronos model name."""
    engine = str(row.get("forecaster") or "")
    if row.get("method") == "ets":
        return (
            "ETS (AutoETS)" if engine.startswith("statsforecast") else "ETS (built-in)"
        )
    return _text(engine, 40)


def strategy_panel(inputs: Inputs) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    rows = [
        {
            "made": iso_z(r.get("made_at")),
            "symbol": r.get("symbol"),
            "forecaster": _forecaster_label(r),
            "trades": _count(r.get("trades")),
            "win_rate": _num(r.get("win_rate_pct")),
            "cagr": _num(r.get("cagr_pct")),
            "max_dd": _num(r.get("max_drawdown_pct")),
            "sharpe": _num(r.get("sharpe")),
            "hold_cagr": _num(r.get("hold_cagr_pct")),
            "benchmark": _benchmark_text(r),
            "_tone": _sign_tone(_num(r.get("cagr_pct"))),
        }
        for r in _latest(inputs.strategies, "symbol", "interval", "method")
    ]
    return {
        "id": "strategy",
        "type": "table",
        "title": t["strategy"],
        "description": t["strategy_desc"],
        "columns": [
            _col("made", t["made"], "datetime"),
            _col("symbol", t["symbol"]),
            _col("forecaster", t["forecaster"]),
            _col("trades", t["trades"], "number"),
            _col("win_rate", t["win_rate"], "percent"),
            _col("cagr", t["cagr"], "percent"),
            _col("max_dd", t["max_dd"], "percent"),
            _col("sharpe", t["sharpe"], "number"),
            _col("hold_cagr", t["hold_cagr"], "percent"),
            _col("benchmark", t["benchmark"]),
        ],
        "rows": rows[:TABLE_ROWS],
        "empty": t["strategy_empty"],
    }


def build_snapshot(inputs: Inputs, now: datetime) -> dict[str, Any]:
    t = LABELS[inputs.lang]
    subtitle = None
    if inputs.trading is not None:
        subtitle = t["subtitle"].format(
            account=inputs.trading.account,
            cap=f"{inputs.trading.max_order_usd:g}",
        )
        if not inputs.trading.enabled:
            subtitle += f" · {t['trading_off']}"
    panels = [
        summary_panel(inputs, now),
        crypto_panel(inputs, now),
        goals_panel(inputs),
        key_panel(inputs),
        lessons_panel(inputs),
        portfolio_chart_panel(inputs),
        pnl_chart_panel(inputs),
        bought_panel(inputs),
        sold_panel(inputs),
        refused_panel(inputs),
        accuracy_chart_panel(inputs),
        by_symbol_panel(inputs),
        backtests_panel(inputs, now),
        strategy_panel(inputs),
        forecasts_panel(inputs),
        {
            "id": "disclaimer",
            "type": "text",
            "title": t["disclaimer"],
            "body": t["disclaimer_body"],
        },
    ]
    snapshot: dict[str, Any] = {
        "version": VERSION,
        "title": "Kronos",
        "updated_at": iso_z(now),
        "panels": panels[:MAX_PANELS],
    }
    if subtitle:
        snapshot["subtitle"] = subtitle
    return snapshot


# ── Writing ──


def _shrink(snapshot: dict[str, Any]) -> None:
    """Halve every table, list and chart series (keeping the newest data)."""
    for panel in snapshot["panels"]:
        kind = panel.get("type")
        if kind == "table":
            panel["rows"] = panel["rows"][: max(len(panel["rows"]) // 2, 1)]
        elif kind == "list":
            panel["items"] = panel["items"][: max(len(panel["items"]) // 2, 1)]
        elif kind == "chart":
            for series in panel["series"]:
                series["points"] = series["points"][len(series["points"]) // 2 :]


def encode(snapshot: dict[str, Any]) -> bytes:
    """UTF-8 JSON no larger than MAX_BYTES, trimming the long panels when needed."""
    for _ in range(16):
        data = json.dumps(
            snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if len(data) <= MAX_BYTES:
            return data
        _shrink(snapshot)
    raise SkillError("The dashboard snapshot does not fit in 512 KiB.")


def write_snapshot(snapshot: dict[str, Any], out: Path) -> Path:
    data = encode(snapshot)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".kronos-", suffix=".tmp", dir=out.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return out


def refresh(
    *,
    config_path: Path | None = None,
    kronos_dir: Path | None = None,
    out: Path | None = None,
    now: datetime | None = None,
) -> Path:
    moment = now or datetime.now(UTC)
    inputs = load_inputs(config_path, kronos_dir or kronos_home())
    return write_snapshot(build_snapshot(inputs, moment), out or dashboard_path())


def refresh_safely(**kwargs: Any) -> Path | None:
    """``refresh`` for callers whose own result is already final; never raises."""
    try:
        return refresh(**kwargs)
    except Exception:  # health: allow BLE001 -- runs after an order or forecast is final; a dashboard bug must not turn that result into an error the agent retries
        print("The Kronos dashboard was not refreshed:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the Kronos dashboard snapshot."
    )
    parser.add_argument("--print", action="store_true", help="also print the snapshot")
    args = parser.parse_args(argv)
    path = refresh()
    out: dict[str, Any] = {"ok": True, "path": str(path)}
    if args.print:
        out["snapshot"] = json.loads(path.read_text(encoding="utf-8"))
    print(dump_json(out))
    return 0


if __name__ == "__main__":
    sys.exit(run_cli(main))
