"""Lessons: short, actionable rules Kronos derives from its own scored forecasts and trades.

``kronos_review.py`` rebuilds the full set from the journal and the trade ledger on every run
and writes only the differences to ``$CLAWK_HOME/kronos/lessons.jsonl`` (append-only, folded by
``key``): a new or changed lesson appends a line, a lesson whose condition no longer holds gets
``"active": false``. Text is rendered from ``kind`` + ``evidence`` so the dashboard can show it
in the user's language; ``text`` keeps the English rendering for agents reading the file.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from _kronos_common import fold_rows, iso_z, kronos_home, read_jsonl
from _kronos_journal import (
    GATE_MIN_HIT_RATE,
    MIN_MATURED,
    RECENT_WINDOW,
    append_locked,
    gate_status,
    group_accuracy,
    symbol_key,
)

TEMPLATES = {
    "en": {
        "buy_blocked": "{symbol}: automatic buys are blocked — direction right only "
        "{hits}/{n} in its last reviewed forecasts (needs 50%+). Buy only if the user asks "
        "for that trade.",
        "low_accuracy": "{label}: direction right only {hits}/{n} recently — don't trade on "
        "the forecast alone.",
        "good_accuracy": "{label}: direction right {hits}/{n} recently and closer than "
        "'no change' in {beat}/{n} — usable as one input; still confirm with indicators.",
        "worse_than_naive": "{label}: 'no change' was closer than Kronos in {worse}/{n} — "
        "treat its price targets as noise.",
        "narrow_band": "{label}: the price ended outside the p10–p90 band in "
        "{outside}/{banded} — real risk is wider than the band; size smaller.",
        "bullish_bias": "{label}: Kronos said 'up' {predicted_up}/{n} times but the price "
        "rose {actual_up}/{n} — discount its 'up' calls.",
        "losing_trades": "{symbol}: {losses} of {n} closed trades lost money ({net}) — "
        "require a backtest 'adds_value' verdict and bullish indicators before buying again.",
        "winning_trades": "{symbol}: {wins} of {n} closed trades made money ({net}) — keep "
        "following the playbook; don't raise the size on a streak.",
        "unknown_orders": "{count} buy(s) ended with an unknown status — check the eToro "
        "positions before buying again.",
    },
    "es": {
        "buy_blocked": "{symbol}: compras automáticas bloqueadas — acertó la dirección solo "
        "{hits}/{n} en sus últimos pronósticos revisados (necesita 50%+). Comprar solo si el "
        "usuario pide esa operación.",
        "low_accuracy": "{label}: acertó la dirección solo {hits}/{n} veces últimamente — no "
        "operar solo con el pronóstico.",
        "good_accuracy": "{label}: acertó la dirección {hits}/{n} veces y estuvo más cerca que "
        "'sin cambio' en {beat}/{n} — sirve como una señal más; confirmar con indicadores.",
        "worse_than_naive": "{label}: 'sin cambio' estuvo más cerca que Kronos en {worse}/{n} "
        "— sus precios objetivo son ruido.",
        "narrow_band": "{label}: el precio terminó fuera de la banda p10–p90 en "
        "{outside}/{banded} — el riesgo real es mayor que la banda; usar montos menores.",
        "bullish_bias": "{label}: Kronos dijo 'sube' {predicted_up}/{n} veces pero el precio "
        "subió {actual_up}/{n} — desconfiar de sus 'sube'.",
        "losing_trades": "{symbol}: {losses} de {n} operaciones cerradas perdieron dinero "
        "({net}) — exigir veredicto 'adds_value' e indicadores alcistas antes de volver a "
        "comprar.",
        "winning_trades": "{symbol}: {wins} de {n} operaciones cerradas ganaron dinero ({net}) "
        "— seguir el playbook; no subir el monto por una racha.",
        "unknown_orders": "{count} compra(s) quedaron con estado desconocido — revisar las "
        "posiciones en eToro antes de volver a comprar.",
    },
}
_UNITS_ES = {
    "week": ("semana", "semanas"),
    "day": ("día", "días"),
    "hour": ("hora", "horas"),
    "minute": ("minuto", "minutos"),
}
TONE_ORDER = {"negative": 0, "warning": 1, "positive": 2, "neutral": 3}


def lessons_path(kronos_dir: Path | None = None) -> Path:
    return (kronos_dir or kronos_home()) / "lessons.jsonl"


def interval_label(interval: str, lang: str) -> str:
    match = re.fullmatch(r"(\d+) (week|day|hour|minute)s?", str(interval or ""))
    if lang != "es" or not match:
        return str(interval or "")
    count = int(match.group(1))
    singular, plural = _UNITS_ES[match.group(2)]
    return f"{count} {singular if count == 1 else plural}"


def money(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def render(lesson: dict[str, Any], lang: str = "en") -> str:
    kind = str(lesson.get("kind") or "")
    template = TEMPLATES.get(lang, TEMPLATES["en"]).get(kind)
    evidence = (
        lesson.get("evidence") if isinstance(lesson.get("evidence"), dict) else {}
    )
    if template is None:
        return str(lesson.get("text") or "")
    symbol = str(lesson.get("symbol") or "")
    values: dict[str, Any] = {
        **evidence,
        "symbol": symbol,
        "label": f"{symbol} {interval_label(str(lesson.get('interval') or ''), lang)}".strip(),
    }
    if isinstance(evidence.get("net"), (int, float)):
        values["net"] = money(float(evidence["net"]))
    try:
        return template.format(**values)
    except (KeyError, ValueError, IndexError):
        return str(lesson.get("text") or "")


def _lesson(
    kind: str, tone: str, symbol: str, interval: str, evidence: dict[str, Any]
) -> dict[str, Any]:
    lesson = {
        "key": f"{kind}|{symbol}|{interval}",
        "kind": kind,
        "symbol": symbol,
        "interval": interval,
        "tone": tone,
        "evidence": evidence,
    }
    lesson["text"] = render(lesson, "en")
    return lesson


# ── Rules over one (symbol, interval) group's recent accuracy ──


def _low_accuracy(s: dict[str, Any]) -> dict[str, Any] | None:
    if s["hit_rate"] < GATE_MIN_HIT_RATE:
        return {"hits": s["hits"], "n": s["matured"]}
    return None


def _good_accuracy(s: dict[str, Any]) -> dict[str, Any] | None:
    if s["hit_rate"] >= 0.6 and s["beat_naive"] / s["matured"] >= 0.5:
        return {"hits": s["hits"], "beat": s["beat_naive"], "n": s["matured"]}
    return None


def _worse_than_naive(s: dict[str, Any]) -> dict[str, Any] | None:
    worse = s["matured"] - s["beat_naive"]
    if worse / s["matured"] >= 0.6:
        return {"worse": worse, "n": s["matured"]}
    return None


def _narrow_band(s: dict[str, Any]) -> dict[str, Any] | None:
    if s["banded"] >= MIN_MATURED and s["outside_band"] / s["banded"] >= 0.4:
        return {"outside": s["outside_band"], "banded": s["banded"]}
    return None


def _bullish_bias(s: dict[str, Any]) -> dict[str, Any] | None:
    n = s["matured"]
    if s["predicted_up"] / n >= 0.8 and s["actual_up"] / n <= 0.5:
        return {"predicted_up": s["predicted_up"], "actual_up": s["actual_up"], "n": n}
    return None


GROUP_RULES: tuple[tuple[str, str, Callable[[dict[str, Any]], dict | None]], ...] = (
    ("low_accuracy", "negative", _low_accuracy),
    ("good_accuracy", "positive", _good_accuracy),
    ("worse_than_naive", "negative", _worse_than_naive),
    ("narrow_band", "warning", _narrow_band),
    ("bullish_bias", "warning", _bullish_bias),
)


def _group_lessons(records: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    lessons = []
    for (symbol, interval), stats in group_accuracy(records, window).items():
        if stats["matured"] < MIN_MATURED:
            continue
        for kind, tone, rule in GROUP_RULES:
            evidence = rule(stats)
            if evidence is not None:
                lessons.append(_lesson(kind, tone, symbol, interval, evidence))
    return lessons


def _gate_lessons(records: list[dict[str, Any]], window: int) -> list[dict[str, Any]]:
    lessons = []
    for symbol in sorted({symbol_key(r.get("symbol")) for r in records} - {""}):
        gate = gate_status(records, symbol, window)
        if gate["blocked"]:
            evidence = {"hits": gate["hits"], "n": gate["matured"]}
            lessons.append(_lesson("buy_blocked", "negative", symbol, "", evidence))
    return lessons


# ── Rules over the trade ledger ──


def trade_stats(ledger: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Closed trades with a known P&L, per symbol: count, wins, losses, net USD."""
    rows = list(ledger)
    names = {
        e.get("instrument_id"): e.get("symbol")
        for e in rows
        if e.get("action") == "open" and e.get("symbol")
    }
    stats: dict[str, dict[str, Any]] = {}
    for entry in rows:
        pnl = entry.get("pnl_usd")
        if entry.get("action") != "close" or not isinstance(pnl, (int, float)):
            continue
        if entry.get("status") == "failed":
            continue
        symbol = symbol_key(
            entry.get("symbol")
            or names.get(entry.get("instrument_id"))
            or f"#{entry.get('instrument_id')}"
        )
        row = stats.setdefault(symbol, {"n": 0, "wins": 0, "losses": 0, "net": 0.0})
        row["n"] += 1
        row["wins"] += int(pnl > 0)
        row["losses"] += int(pnl < 0)
        row["net"] = round(row["net"] + float(pnl), 2)
    return stats


def _trade_lessons(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lessons = []
    for symbol, s in trade_stats(ledger).items():
        if s["n"] < 2:
            continue
        if s["net"] < 0 and s["losses"] > s["wins"]:
            lessons.append(_lesson("losing_trades", "negative", symbol, "", dict(s)))
        elif s["net"] > 0 and s["wins"] >= s["losses"]:
            lessons.append(_lesson("winning_trades", "positive", symbol, "", dict(s)))
    unknown = sum(
        1 for e in ledger if e.get("action") == "open" and e.get("status") == "unknown"
    )
    if unknown:
        lessons.append(_lesson("unknown_orders", "warning", "", "", {"count": unknown}))
    return lessons


def build_lessons(
    records: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
    window: int = RECENT_WINDOW,
) -> dict[str, dict[str, Any]]:
    """Every lesson that holds right now, by key."""
    lessons = (
        _gate_lessons(records, window)
        + _group_lessons(records, window)
        + _trade_lessons(ledger)
    )
    return {lesson["key"]: lesson for lesson in lessons}


# ── Storage ──


def all_lessons(path: Path | None = None) -> list[dict[str, Any]]:
    return fold_rows(read_jsonl(path or lessons_path()), key="key")


def active_lessons(path: Path | None = None) -> list[dict[str, Any]]:
    rows = [lesson for lesson in all_lessons(path) if lesson.get("active")]
    rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    return sorted(rows, key=lambda r: TONE_ORDER.get(str(r.get("tone")), 9))


def lessons_for_symbol(
    lessons: Iterable[dict[str, Any]], symbol: str
) -> list[dict[str, Any]]:
    key = symbol_key(symbol)
    return [
        lesson for lesson in lessons if symbol_key(lesson.get("symbol")) in {key, ""}
    ]


def update_lessons(
    current: dict[str, dict[str, Any]], now: datetime, path: Path | None = None
) -> list[dict[str, Any]]:
    """Append new/changed lessons and retire the ones that stopped holding; returns the rows."""
    path = path or lessons_path()
    existing = {str(row["key"]): row for row in all_lessons(path)}
    stamp = iso_z(now)
    rows = []
    for key, lesson in current.items():
        old = existing.get(key) or {}
        still_active = bool(old.get("active"))
        if still_active and old.get("evidence") == lesson["evidence"]:
            continue  # dedupe: same lesson, same numbers
        created = old.get("created_at") if still_active else None
        rows.append(
            {
                **lesson,
                "active": True,
                "created_at": created or stamp,
                "updated_at": stamp,
            }
        )
    for key, old in existing.items():
        if old.get("active") and key not in current:
            rows.append({"key": key, "active": False, "updated_at": stamp})
    append_locked(path, rows)
    return rows
